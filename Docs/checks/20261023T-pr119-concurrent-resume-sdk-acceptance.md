# PR #119 同一暂停实例的八路并发恢复验收

日期：2026-10-23。gVisor、Firecracker 各三轮均通过；共 48 次逻辑 resume 调用，每轮实际只有一条 sandboxd Start 请求。

## 1. 问题

多个调用方同时恢复同一个实例时，不能重复创建运行时或混用代次，最终内存、文件与落点必须一致。失败/冲突需要按契约分类，不能把任意异常当作安全通过。

## 2. 方法

固定 PR #119 候选和独立 JuiceFS 双节点环境不变，全部在远端执行。公共 SDK 创建源、写入根文件并运行 512 MiB 确定性内存探针；恢复控制复用现有 ADX 原生 pause/resume API，不新增公开接口。

每轮先为同一 Running 实例建立八个独立的原生 SDK 句柄，然后 pause，确认权威 Paused、所关联运行时已不在观察结果中。八个线程通过 Barrier 同时发起 resume；分别记录成功，或明确的 CONFLICT/never/not_started。未知错误直接使测试失败，不自动生成新操作重试。

恢复后核对所有成功响应的 Environment ID/节点相同、权威 Running；在两节点日志内部仅提取本实例 sandboxd Start 请求的 trace 摘要计数，绝不导出含 env 的原日志；检查最终关联运行时只有一个。公共 SDK 再校验根文件、512 MiB 完整内存、PID/随机身份和打开文件，三轮之间继续修改后再捕获。

## 3. 数据

| 运行时 | 轮次 | 逻辑 resume 成功 | 未开始冲突 | 新 Start 请求 | 最终关联运行时 | 完整状态 |
|---|---:|---:|---:|---:|---:|---|
| gVisor | 1 | 8/8 | 0 | 1 | 1 | 通过 |
| gVisor | 2 | 8/8 | 0 | 1 | 1 | 通过 |
| gVisor | 3 | 8/8 | 0 | 1 | 1 | 通过 |
| Firecracker | 1 | 8/8 | 0 | 1 | 1 | 通过 |
| Firecracker | 2 | 8/8 | 0 | 1 | 1 | 通过 |
| Firecracker | 3 | 8/8 | 0 | 1 | 1 | 通过 |

`storage/concurrent-resume01/terminal.json` 两组均 rc=0；[小型回执](evidence/pr119-juicefs-tapfix-20261023/concurrent-resume.json) 包含脚本 SHA-256 与所有轮次。两个源通过 SDK 删除，Environment 归零。

启动前 SSH 中断的第一次下发没有落地：新连接逐项确认脚本、输出目录和驱动进程均不存在后，才重新部署。真正执行的版本写入持久启动回执，结果取回前没有重复运行。后来读取时远端已完整打印回执，本地持续连接的等待超时不改变这份已得到的 rc=0 终态。

## 4. 结论

【实测】在六轮并发中，48 个逻辑请求全部成功，且每轮仅对应一次底层 Start；最终状态和落点一致，没有由这组并发产生多次启动的证据。

删除后补充只读复核：六轮前后去重得到八个运行时 PID/启动代次；在各自原 Node Pod 中读取 /proc，八个 PID 均已不存在，见 [回执](evidence/pr119-juicefs-tapfix-20261023/concurrent-resume-retired-pids.json)。没有发送额外信号。

【边界】这是已有原生 pause/resume 控制加公共 SDK I/O 的并发验收，不是声称公共 SDK 新增了 pause/resume API，也没有对并发 reload 的线程安全或任意故障时序作泛化保证。进程核对不等于所有 mount、FD、cgroup 内核资源都已逐项核销。该组不是性能数据。

## 5. 建议与改进项

后续对两条存储路线复用相同的并发入口和启动计数方法。旧 PID 只读检查、未关闭输入的角色崩溃与挂载替换已补齐；内部删除屏障和分相交替性能仍单列待办。

## 6. 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
S="$N/round-365f797-20261023.clPWh2h0/tap-checksum-fix/storage"
cat "$S/concurrent-resume01-launch-receipt.json"
cat "$S/concurrent-resume01/terminal.json"
cat "$N/acceptance/runs/shared-concurrent-resume01-runsc/events.jsonl"
cat "$N/acceptance/runs/shared-concurrent-resume01-firecracker/events.jsonl"
```

脚本为 `sdk-concurrent-resume01.py / run-concurrent-resume01.py`。八个句柄必须在 Running 时创建，因为固定原生 SDK from_id 不接受 Paused；close 只关闭这些 detached 本地句柄，远端退出由源 SDK 显式负责。复测使用新资源/目录并先过真实就绪门。

## 7. 现场清理披露

两组源经 SDK 删除，权威 Environment 为零，独立 SDK 句柄正常关闭。未手工删工件或强制结束运行时，未更换制品、配置、模板、父仓 gitlink、宿主参数或共享服务。集群和任务存储保留给后续用例；全部语法检查和测试远端执行。
