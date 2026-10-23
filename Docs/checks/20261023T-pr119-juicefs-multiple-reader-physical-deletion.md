# PR #119 JuiceFS 多读者保护与快照物理删除检查

日期：2026-10-23。结论：gVisor、Firecracker 两组真实存储验收通过；没有覆盖删除器内部屏障，也没有宣称完整生命周期矩阵通过。

## 1. 问题

按计划继续完成 PR #119 的共享 checkpoint 读者保护：多个节点引用同一恢复点时不得删除；所有读者退出后需要真正回收文件，删除完成后不能再建立新读者。不能以关闭自动回收或只检查引用计数代替。

## 2. 方法

固定 AKernel `365f797`、实际 ADX/Execd `6fb53d7`、sandboxd `d5acc3b + 未提交 TAP 补丁`，制品不变。只在 BareMetal 本任务独立 Kind/Pod、PostgreSQL、Ceph RGW、JuiceFS 环境执行；同物理机上的两个逻辑节点有不同 JuiceFS 客户端，不是双物理节点。

源沙箱由 AKernel 公共 SDK 创建，写入 1 GiB 确定性应用内存和 1 MiB 根文件。目录操作复用既有 ADX 原生 SDK Snapshot API：创建可复用快照、在两个节点分别创建引用者、拒绝忙快照删除、读者退出后删除。没有新增公共 AKernel checkpoint catalog API。读者通过 SDK 校验内存、进程、打开文件和真实 RWFS，并继续写入。

额外检查运行时的共享输入 FD、物理 `artifacts/<id>` 目录和 `manifests/<id>.json`；Snapshot ID 必须是本任务共享存储内的 UUID，禁止任意路径删除。脚本为远端 `storage/sdk-snapshot-gc02.py`，串行驱动为 `run-snapshot-gc02.py`。

## 3. 数据

| 检查 | gVisor | Firecracker |
|---|---|---|
| 第一个读者建立后、完整状态校验前观察到共享输入 FD | 是 | 是 |
| 一个读者时删除 | `SNAPSHOT_IN_USE`，准确列出一个使用者，物理目录和清单保留 | 同左 |
| 两个独立客户端同时引用时删除 | 准确列出两个使用者，文件保留 | 同左 |
| 第一个读者退出，第二个仍在运行 | 删除仍被拒绝，剩余读者完整状态和新写入正确 | 同左 |
| 最后读者退出后两条并发删除请求 | 本轮均接受；目录与清单最终均消失 | 同左 |
| 删除后查询 | `NOT_FOUND` / HTTP 404 | 同左 |
| 删除后创建新读者 | `CONFLICT` / HTTP 409，`retry=never`、`outcome=not_started` | 同左 |
| 清理 | 源和两个读者全部退出，无 Environment 遗留 | 同左 |

忙快照错误同样要求 `retry=never`、`outcome=not_started`，不能接受任意错误充当保护通过。[小型原始证据](evidence/pr119-juicefs-tapfix-20261023/snapshot-multiple-reader-gc.json) 中两组均为 rc=0。

首轮 `snapshot-gc01` 失败保留：实际删除与拒绝新读者已经正确，但脚本误以为“创建已删除快照的读者”只能返回 NOT_FOUND，拒绝了合法的 CONFLICT/409。独立只读/拒绝性确认后，另存修正版精确检查两种接口各自的错误契约；没有放宽为任意失败即通过，也没有重写原失败。

## 4. 结论

【实测】两个运行时均证明真实 JuiceFS 多读者保护、最后读者退出后的物理删除，以及删除完成后拒绝新引用。gVisor 此例在完整校验前也观察到了共享输入文件句柄。

【边界】两条并发删除 API 请求不等于两个独立 collector。没有在物理 DELETE 前挂内部屏障，尚不能关闭任意内部交错证明；本检查也不覆盖超时取消、挂载/上传失败或活跃 gVisor 后台读取时的控制进程崩溃。

## 5. 建议与改进项

保留固定源码组件层的 acquire/delete 原子竞争回归与本次真实文件验收，后续用内部屏障补交错，禁止用旧 S3 CAS sweep 的测试替代 JuiceFS 生命周期。继续验收失败发布、超时、并发唤醒和复杂 RWFS，之后再比较两条后端路线。

## 6. 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
Q="$N/round-365f797-20261023.clPWh2h0"
S="$Q/tap-checksum-fix/storage"
cat "$S/snapshot-gc01/terminal.json"  # 原断言失败，保持原件
cat "$S/snapshot-gc02/terminal.json"
cat "$N/acceptance/runs/shared-snapshot-gc02-runsc/events.jsonl"
cat "$N/acceptance/runs/shared-snapshot-gc02-firecracker/events.jsonl"
```

复测须使用新输出目录和唯一 Snapshot 名，先确认无其他活跃用例。执行入口经 `namespace-lab07.py run --task "$N"` 进入本任务网络/挂载空间，SDK 仍校验证书。原始记录含资源 ID，仅留远端私有目录，不包含于公开复现摘要。

## 7. 现场清理披露

两组源沙箱、四个读者和两个快照均通过所属 SDK 正常删除；物理目录/清单消失，权威 Environment 为零。可能保留内部已删除墓碑，不将其说成 Ready 快照。专属集群、存储和连接代理继续留给后续测试，没有提前拆除依赖。未修改共享服务、宿主参数、其他任务或父仓组件指针，无本地编译测试。
