# PR #119 独立 S3 网关短时不可用验收

日期：2026-10-23。gVisor、Firecracker 两组通过，网关原进程恢复；未修改共享服务或宿主网络。

## 1. 问题

验证 checkpoint 必要数据尚不能送达 S3 时，是否错误返回成功；存储恢复后，原有快照能否继续跨节点恢复，失败输出与引用能否正常收尾。

## 2. 方法

固定版本与前轮一致。在本任务独立 Kind 的唯一 Ceph RGW（S3 网关）上做最多 20 秒进程停顿，不改配置、不重启进程。事前匹配 Kubernetes Pod UID、容器 ID、宿主 PID/启动代次、`radosgw` 可执行文件、完整任务和 Kind cgroup，确认不是其他服务；确认 liveness 不会因本次时长杀进程。

独立 watchdog 验证后 SIGSTOP，确认进程处于停止状态，再于 20 秒后通过 finally 对同一身份 SIGCONT；测试主进程退出也不终止 watchdog。没有操作 MON/OSD/PostgreSQL、共享 S3 服务或任何宿主网络规则。

源持有 1 GiB 确定性应用内存，先生成已知成功 Snapshot，再修改状态。源节点不带凭据的 HTTP 探针先获得网关正常响应；停顿后探针超时，确认故障有效，随后发起新快照。请求结束后等 watchdog 终态和 HTTP 恢复，按唯一名对账，不重放。源显式退出后，从已有快照在另一节点验证完整状态、新写入和再次 checkpoint/reload。

## 3. 数据

| 项目 | gVisor | Firecracker |
|---|---|---|
| 故障 | 同一 RGW 进程停顿约 20 秒，HTTP 探针超时 | 同左 |
| 停顿期间提前成功确认 | 无 | 无 |
| 新请求最终结果 | CONFLICT/409、retry=never、outcome=not_started | 同左 |
| 新 Ready 快照 | 无 | 无 |
| 网关恢复 | 同 PID/启动代次 SIGCONT，HTTP 返回原状态码 | 同左 |
| 已有快照另一节点完整恢复 | 通过，1 GiB 内存/进程/打开文件/根文件正确 | 同左 |
| 目标继续写、新 checkpoint/reload | 通过 | 通过 |
| 清理 | 源/目标退出，已知快照删除，失败目录无遗留 | 同左 |

`storage/s3-pause01/terminal.json` 两组均 rc=0，`storage_fault_restored=true`；[小型回执](evidence/pr119-juicefs-tapfix-20261023/s3-pause-recovery.json) 保留原结果和实际停顿时长。

## 4. 结论

【实测】该短时 S3 不可用场景没有产生假成功；后端恢复后已有快照仍可用，后续写入与捕获正常。两个 watchdog 都确认恢复原进程，没有依赖重启替代进程掩盖清理问题。

【边界】这是本任务单 RGW、单 OSD 的有限停顿，不是永久断网、PG 故障、存储 HA 或断电持久性验收。通用 CONFLICT 仍未准确暴露底层原因。原运行时退出检查只覆盖已绑定 VMM/runsc-sandbox 和目录回收，不声称所有主机 I/O goroutine 已独立跟踪。

## 5. 建议与改进项

保持错误结果先对账的策略，继续补元数据/挂载故障与内部交错。生产部署仍需真实故障域、HA 和备份恢复，不能把本次单副本测试记为生产可用验收。

## 6. 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
S="$N/round-365f797-20261023.clPWh2h0/tap-checksum-fix/storage"
cat "$S/s3-pause01/terminal.json"
cat "$N/acceptance/runs/shared-s3-pause01-runsc/watchdog/terminal.json"
cat "$N/acceptance/runs/shared-s3-pause01-firecracker/watchdog/terminal.json"
```

远端脚本 `pause-owned-rgw01.py / sdk-s3-pause01.py / run-s3-pause01.py`。故障脚本固定本轮身份，资源重建后必须重新盘点，不能直接替换一个 PID 就执行，也不能用于共享或生产网关。编译、语法检查和实际测试全在远端。

## 7. 现场清理披露

两次 SIGSTOP 均由独立 watchdog 撤销，原 RGW 继续服务；未改 Deployment、副本数、Pod、MON/OSD/PG、网络或宿主参数。沙箱与快照通过 SDK 清理，任务存储继续保留供下一项。

随后 SSH 发生短暂连接超时，尚无证据确定根因，不能归因于 RGW 停顿：此前两份 watchdog 回执已确认恢复。绕过本任务 SSH 复用连接的新连接成功，确认下一项并发脚本尚未落地/启动后才继续部署，未盲目重复实验，没有重启 SSH 或共享服务。
