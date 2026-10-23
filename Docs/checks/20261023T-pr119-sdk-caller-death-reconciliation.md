# PR #119 SDK 调用进程退出后的快照结果对账

日期：2026-10-23。gVisor、Firecracker 两组通过；两次均为调用者退出、后端仍提交成功，未重放请求。

## 1. 问题

调用 checkpoint/Snapshot 的主进程突然消失时，不能把客户端退出当作后端取消，也不能直接释放输入或盲目重试。需要对账实际结果，并证明工件仍可恢复、可回收。

## 2. 方法

版本与前轮固定候选一致，全部在远端独立环境。公共 SDK 创建 1 GiB 确定性内存的源和根文件；既有 ADX 原生 API 创建一个已知成功快照。修改源状态后，由本任务独立 Python SDK 子进程发起新的唯一名称 Snapshot 请求。

观察该请求新产生的共享捕获目录且尚无清单，同时子进程未记录完成响应；核对 Popen 所属 PID、启动代次和存活，再仅 SIGKILL 本任务的这个 SDK 子进程。没有杀 adxlet、sandboxd、VMM、Pod PID1 或其他任务。按唯一名称查询结果，不重放失去响应的请求。

源显式退出、原运行时进程身份消失后，选择对账得到的成功快照，在另一节点恢复，比较修改后的完整内存/进程/打开文件与根文件。目标继续写入，再次 checkpoint/reload，最终删除源、读者和快照。

## 3. 数据

| 检查 | gVisor | Firecracker |
|---|---|---|
| 杀调用者前 | 新捕获目录已存在、观察时清单不存在，调用者未完成 | 同左 |
| 调用者退出 | 本任务 SDK 子进程返回 -9 | 同左 |
| 目录对账结果 | 新快照随后 Ready | 同左 |
| 是否重放请求 | 否 | 否 |
| 实际恢复对象 | 调用者退出后由后端提交的那份新快照 | 同左 |
| 另一节点完整状态与后续 checkpoint/reload | 通过 | 通过 |
| 清理 | 两份快照、源和读者退出；无 Environment/工件目录遗留 | 同左 |

远端 `storage/caller-death01/terminal.json` 两组均 rc=0，[小型证据](evidence/pr119-juicefs-tapfix-20261023/sdk-caller-death.json) 中 `published_snapshot_after_caller_death=true`。

## 4. 结论

【实测】客户端进程死亡并没有自动取消后端提交。通过唯一名称对账得到实际结果后，新快照仍能完整恢复和继续捕获；无需重新执行原操作。

【边界】这是观察到捕获目录尚未封存时的客户端退出，不是物理删除内部屏障；无法将“观察清单不存在”与发送 SIGKILL 之间的所有服务端指令锁成单一时刻。原运行时退出验证沿用超时检查的范围，不声称对每个主机 I/O goroutine 都独立跟踪。用户程序的网络事务不随快照自动回滚。

## 5. 建议与改进项

产品调用方应保留操作身份和可查询名称，未知结果先对账，不能将新请求 ID 的重试当作原操作续传。本次未引入新公开 API，复用现有 Snapshot 目录和幂等契约；仍需改善通用 CONFLICT 对底层失败原因的遮蔽。

## 6. 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
S="$N/round-365f797-20261023.clPWh2h0/tap-checksum-fix/storage"
cat "$S/caller-death01/terminal.json"
cat "$N/acceptance/runs/shared-caller-death01-runsc/events.jsonl"
cat "$N/acceptance/runs/shared-caller-death01-firecracker/events.jsonl"
```

脚本为 `sdk-capture-client01.py / sdk-caller-death01.py / run-caller-death01.py`。复测使用新输出目录和唯一名称；只杀由本轮 Popen 创建、启动代次核对一致的 SDK 子进程，不按进程名批量结束。

## 7. 现场清理披露

两组 SDK 子进程均已 wait/reap；源、恢复目标及两组各两份 Snapshot 均经 SDK 正常删除。已有任务集群、存储和代理保留给后续门禁，未修改宿主参数、共享服务、组件制品或父仓 gitlink，没有本地编译测试。
