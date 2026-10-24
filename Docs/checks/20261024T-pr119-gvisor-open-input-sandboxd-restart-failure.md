# gVisor 后台页输入仍打开时 sandboxd 重启失败检查

后续状态：本文保留218d85378/21fb466组合的原始观察；资源归属五秒落盘窗口已在sandboxd91dff2f修复，完整SDK及严格输入回归通过。见[根因与修复验收](20261024T-pr119-cgroup-lease-crash-recovery.md)。


## 1. 问题

继续 PR #119 / JuiceFS 原生私有文件布局验收：在真实内存页输入仍被恢复运行时使用时，控制进程死亡重启后，读者及其保护是否保留？普通重启通过不能代替这一时序。

## 2. 方法

固定 gVisor `218d85378357f9726fc3c0f7cf878cf19772d360`、sandboxd `21fb4668431cef88d05b7a789a2bd9a5e19e827c` 和已经完成 SDK 验收的相同六程序包、sandboxd ELF、镜像。未重编译或部署。只在 BareMetal 本任务独立双逻辑节点环境测试，配置 1 CPU / 2 GiB 内存 / 1 GiB 私有盘，应用持有 1 GiB 确定性内存。

`held-reader02` 使用公共 Snapshot/Environment SDK：保存、删除生产者，在对端恢复；严格匹配该 artifact 的命名 `pages.img`，由同 Pod sandboxd 的根视图核对文件与 Sentry FD 的设备号/inode；再按任务 cgroup、容器、PID 开始时间与 ELF 校验，只短停 Sentry 三秒，杀本任务 sandboxd，finally 恢复同一 Sentry。匿名私有文件不算输入。

源码检查：sandboxd `pkg/sandbox/manager.go:489` 附近的 `__startMonitor` 把运行时 Wait 错误转换为退出码 128；`pkg/runtime/runsc/client.go:553` 的 `Client.Wait` 先连接控制 socket，失败直接返回错误。故 128 不能反向证明沙箱的真实退出信号。

gVisor `pkg/sentry/kernel/kernel_restore.go:335` 的 `AsyncMFLoader.backgroundGoroutine` 把 pages 输入交给异步加载器；`pkg/sentry/pgalloc/save_restore.go` 的 `AsyncPagesFileLoad.main` 先关闭异步读者再发布完成。`runsc/boot/restore.go:605` 的 `postRestore` 等待输入完成后记录成功；日志显示本次确实到达成功，未看到同窗口加载失败证据。

## 3. 数据

| 事件 | 本轮观察；时间为远端日志的北京时间 |
|---|---|
| 开始后台加载 | 11:42:33.015，主 MemoryFile 异步加载 1088843776 字节 |
| 真实输入与故障屏障 | 11:42:35.679，仍打开一个命名 pages.img，身份一致；随后 SIGKILL 本任务 sandboxd |
| 恢复读者 | 11:42:38.680，同 PID/开始时间的 Sentry 已 SIGCONT；不是另起读者 |
| 后台完成 | 11:42:38.726，页输入完成；11:42:38.727 记录 Restore successful |
| sandboxd 恢复监控 | 11:42:41.101，启动原实例监控；41.102 连接 runsc 控制 socket 被拒绝，转为退出码 128 |
| SDK/ADX | 原 Environment 后来为 Failed/Exited，原读者进程消失；完整用例 rc=1，后续两个角色未执行 |
| 受保护快照 | 原 READY 用户快照仍存在，失败记录当时保留 snapshot_source；没有本轮“误删对象已复现”的证据 |
| 普通重启对照 | 相同制品、512 MiB 应用负载下三个角色各一次崩溃均通过；当时真实旧页输入已经关闭，不能与本例互换 |
| 只短停读者的控制组 | control02 rc=0，真实页输入打开时短停三秒，不杀任何角色；同进程 1 GiB 完整内存、根文件、引用与命名文件、忙删除及后续 checkpoint/reload 通过，资源由 SDK 删除 |

首轮 `held-reader01` 是探针路径视图错误、未注入信号，其完整内存核验和 SDK 删除已完成；不得与上述真实失败混记。`reader-barrier-control01` 只读预检发现失败 Environment 已自动退休，因旧记录不存在而退出，未新建恢复者或发送信号；另存 control02 改用新独立生产者/快照，避免依赖已经退休的记录。

## 4. 结论

【实测】真实输入仍打开时的“短停读者＋sandboxd 崩溃”组合没有通过，不能关闭后台恢复期间重启保护，也不能开始以功能门全绿为前提的性能比较。

【源码】退出码 128 来自 Wait 错误路径；它不是本次进程真实退出原因。已有日志只能定位到“后台加载成功之后、重启监控连接时控制 socket 已不可连接”的窗口。

【未确定】短停屏障本身、资源边界、真实进程死亡与控制 socket 生命周期各占什么作用，仍需对照；不能未经证明修改监控为忽略错误或简单重试，也不能先归因 JuiceFS 数据丢失。父任务 memory.events 存在历史 OOM 计数，没有本例前后增量，不能据此认定或排除本例 OOM。

【实测对照】新独立生产者/快照的 control02 已通过相同制品、2 GiB 配置/1 GiB 应用负载的真实输入短停恢复，并完成完整状态和后续保存恢复。它排除了“这套短停方法在所有同规格样本必然失败”，但失败样本在节点 A、控制组在节点 B，快照数据和实际时序也不同；不能把一轮成功等同于已经唯一定位 sandboxd 或完全排除资源因素。后续应固定节点 A 并采集进程/cgroup/socket 的退出顺序。

## 5. 建议与改进项

读者短停/恢复对照已通过。下一步固定节点 A，记录故障前后 Sentry/gofer、sandboxd、cgroup 和控制 socket 的身份与存活时序；对比只短停、只早期杀 sandboxd 和组合，监测本例 OOM 增量，缩小 socket/进程消失的原因。保留当前正式默认值和已发布核心 SDK 边界，不将未验收补丁混入交付。

## 6. 可复现步骤

只读观察终态，禁止覆盖旧输出或直接重跑失败驱动：

```sh
cat "$ROUND/tap-checksum-fix/gvisor-native-held-reader02/terminal.json"
cat "$TASK/acceptance/runs/shared-gvisor-native-held-reader02-sandboxd/terminal.json"
cat "$TASK/acceptance/runs/shared-gvisor-native-held-reader02-sandboxd/barrier/terminal.json"
cat "$TASK/acceptance/runs/shared-gvisor-native-reader-barrier-control02/terminal.json"
```

脚本在 `tools/pr119-pod-20261024/experiments/gvisor-native-extended/`。实际启动前只在远端解析语法、校验档案和逐文件 SHA。完整 debug 日志只留远端私有目录，其中可能含运行时凭据；复现材料仅导出白名单字段，不复制原始日志或配置。

## 7. 现场清理披露

held-reader02 已在 finally 恢复读者，后续失败进程确已退出，不遗留被停止的读者；其失败 Environment 后来由既有生命周期自动退休。该用户快照仍保留用于诊断，不直接删物理文件。三个普通重启、双分支和 control02 资源均已由 SDK 删除。共享服务、旧环境、内核/模块/sysctl 与宿主 cgroup 设置均未修改，宿主约 670 GiB 可用，高于 650 GiB 预留。
