# PR #119 读者依赖与控制进程重启验收进度

日期：2026-10-23。状态：组件基线与四组真实 SDK 角色崩溃接管通过；另已完成两运行时的真实 JuiceFS 多读者删除保护。完整生命周期故障门仍未关闭。

## 开发内容

SDK 和双向源节点故障接管主链路已通过。下一步验证运行时已经恢复、最新 checkpoint 又推进后，旧恢复文件仍被运行时使用时，ADX 进程重启是否保留引用，并正确接管仍在运行的沙箱。先完成这些正确性门，再进入存储路线性能对照。

## 修改内容

- 固定 ADX 源码未改；远端只读独占容器执行两个组件契约测试目标，源码 1320 文件前后摘要一致。
- 远端 `storage/sdk-reader-restart01.py`：复用既有 Go 状态探针和公共 SDK。创建 512 MiB 状态与 1 MiB 根文件，checkpoint/reload 后再生成第二版 checkpoint，使运行时可能仍依赖第一版；随后保留未 checkpoint 的新状态，分别重启任务 adxlet/Coordinator，核对运行时进程、权威引用、最新内存/文件，再次 checkpoint/reload。
- `storage/run-restart-matrix01.py`：串行执行 FC/gVisor × adxlet/Coordinator 四组；每组前等真实可调度就绪，失败保留沙箱和证据，不自动重试。重启只针对本任务私有 Pod 内服务/Deployment，未变更镜像或共享服务。
- 这些为任务验收辅助脚本，远端语法检查通过，尚未作为已交付脚本提交推送；没有修改产品调度或回收规则。

## 测试结果

固定 ADX 的 checkpoint-storage 10 项、snapshot_busy 2 项组件测试通过，0 跳过；详见 [组件基线检查](../checks/20261023T-pr119-adx-storage-contract-baseline.md)。不能代替真实存储竞争。

`restart-matrix02/terminal.json` 退出 0，FC/gVisor × adxlet/Coordinator 四组通过。每组 3 次 checkpoint、2 次 SDK reload，进程启动身份和未 checkpoint 的新状态保留，最终四个沙箱均删除；FC 两组观察到仍打开旧 checkpoint 的 VMM，gVisor 两组该时点后台读取已结束，不外推其活跃后台读者崩溃安全。

首次使用 `systemctl restart adx` 触发带 drain 语义的正常停止，测试沙箱已被清理，不满足“后端仍存活”前提；原矩阵返回 1，不能归因为读者保护 bug，也不能继续声称沙箱已保留。另存 `sdk-reader-restart02.py / run-restart-matrix02.py`，仅使身份匹配的角色 Rust 子进程 SIGKILL，由现有监督器恢复。见 [故障方式检查](../checks/20261023T-pr119-controller-restart-fault-mode-review.md)。

`snapshot-gc02/terminal.json` 退出 0：两种运行时各创建 1 GiB 确定性内存和 1 MiB 根文件的可复用快照，源退出后在两个独立客户端分别创建读者。读者存在时删除返回 `SNAPSHOT_IN_USE/never/not_started`，列出准确使用者，物理文件保留；第一个读者退出后仍保护第二个，最后退出后两请求并发删除，实际工件目录和清单均消失，新读者被拒绝。两种运行时都在首次删除前观察到共享输入 FD。使用既有 ADX 原生 Snapshot API 管目录控制，源创建与 I/O 使用公共 SDK，没有新增公共 catalog API。内部删除屏障和两个独立 collector 的交错未测试，不能用两条并发 API 请求替代。详见对应新检查文档。

此外，固定源码既有 Coordinator Redis 契约 6 项全部通过；与前述 12 项合计 18 个不同测试。它们直接调用 RedisStore/RedisSession，不是 SDK 或真实 Coordinator 进程重启的替代证据。超时取消、存储失败、复杂 RWFS、并发唤醒与分相交替性能仍待执行。

## 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
Q="$N/round-365f797-20261023.clPWh2h0"
S="$Q/tap-checksum-fix/storage"
cat "$S/restart-matrix01/terminal.json"  # 已保存的正常停止注入失败
cat "$S/restart-matrix02/current.json"
cat "$S/restart-matrix02/terminal.json"  # 仅存在且 rc=0 才是修正轮终态
```

事件和 before/after 原始记录在 `N/acceptance/runs/shared-tapfix-restart01-*`。测试中有活跃沙箱时不能重跑部署器或清理存储依赖。版本与前轮双向故障接管相同，全部编译测试仅远端执行，尚无新增产品提交。
