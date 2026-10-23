# PR #119 两运行时复杂私有文件系统验收

日期：2026-10-23。gVisor、Firecracker 均通过，属于功能/一致性验收，不是性能样本。

## 1. 问题

补计划阶段一的真实 RWFS 大文件与恢复后写入覆盖：追加、删除重建、截断、稀疏区、mmap、打开后删除/重命名，以及跨节点恢复后再次 checkpoint。小文件回滚通过不能替代这些语义。

## 2. 方法

沿用固定候选和本任务独立 JuiceFS 双节点。OCI 镜像固定 `docker.io/library/python@sha256:e8a38829209aea82774882e5157e1f7c3e8c8393ff53a697b3580896e57f345c`，由正常公共 SDK 启动，未更换 VMM、runsc、guest kernel/initrd 或关闭校验。

Guest Python 进程创建真实根目录 `/pr119-rwfs-contract`，持有打开文件和 mmap，控制请求经沙箱内 HTTP 回环；checkpoint 使用既有沙箱内接口，reload 走公共 SDK。每次比较完整文件 SHA-256、大小、模式、链接数/目标、打开 FD 内容、mmap 内容、PID 与随机身份标记。

先连续三代同节点捕获、修改、reload，并在每次成功后生成下一代新状态；再用既有 ADX Snapshot API 生成可复用基线，恢复至另一逻辑节点。在分支写入后验证源未变，再对分支 checkpoint、修改、reload，验证第二代和源隔离。没有新增公共 catalog API。

## 3. 数据

| 覆盖 | 固定数据与断言 | 两运行时结果 |
|---|---|---|
| 较大文件 | 64 MiB 文件、跨页边界覆盖；硬链接引用同一文件 | 通过 |
| 稀疏文件 | 128 MiB 逻辑长度、头尾内容、中心新写入与空洞读回 | 通过；不宣称物理稀疏分配保留 |
| 截断与扩展 | 截短后再增长，新增区域与末尾数据完整哈希 | 通过 |
| 追加 | 反复追加和 fsync 后回滚至捕获版本 | 通过 |
| mmap | 4 MiB 映射，包含未显式 flush 的新修改，跨页边界写入 | 通过 |
| 打开后删除 | 1 MiB 文件仍由 FD 持有；同路径新建文件与旧 FD 内容分别检查 | 通过 |
| 打开后重命名 | FD 与新路径数据一致，后续写入/恢复正确 | 通过 |
| 符号链接 | 链接目标和目标内容正确 | 通过 |
| 进程与分支 | PID/身份、三代回滚、另一节点分支写入不改变父状态、分支再次回滚 | 通过 |

每种运行时 5 次 checkpoint（含一次原生可复用快照）、4 次 reload（公共 SDK 三次、原生分支一次）。两组源与分支均退出，可复用快照最终删除。[小型回执](evidence/pr119-juicefs-tapfix-20261023/complex-rwfs.json) 与远端 `rwfs-contract02/terminal.json` 均 rc=0。

## 4. 结论

【实测】当前“本地私有运行文件＋JuiceFS checkpoint”路径在两种运行时上，通过上述文件语义和跨节点分支的后续两代恢复。没有只用共享目录替代根 RWFS。

【边界】稀疏文件校验的是逻辑内容，未证明物理洞保留；没有测 discard、容量耗尽、文件锁透明迁移或外部共享卷回滚。该测试读取全部内容验证正确性，耗时不能用作按需恢复或业务首读性能。

## 5. 建议与改进项

将同一夹具用于后续 JuiceFS 原生克隆和远端基线＋本地差异层，不再为新后端重造较弱的小文件测试。新后端另补容量、写零/discard、后台读取时写相同页面与依赖回收。

## 6. 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
Q="$N/round-365f797-20261023.clPWh2h0"
S="$Q/tap-checksum-fix/storage"
cat "$S/rwfs-contract02/terminal.json"
cat "$N/acceptance/runs/shared-rwfs-contract02-runsc/events.jsonl"
cat "$N/acceptance/runs/shared-rwfs-contract02-firecracker/events.jsonl"
```

远端源为 `guest-rwfs-contract02.py`、`sdk-rwfs-contract02.py` 和 `run-rwfs-contract02.py`。全部语法检查和实际运行在 BareMetal；复测须经本任务 helper 进入独立环境、使用新输出名并先过真实调度就绪门。

## 7. 现场清理披露

两组源、两个跨节点分支和两个 Snapshot 均通过所属 SDK 正常退出/删除，Environment 归零。测试文件随各自沙箱退出，未手工清理共享 checkpoint。集群、任务存储和代理继续供下一项验收；未改变共享服务、宿主参数、组件制品、父仓 gitlink，没有本地编译测试。
