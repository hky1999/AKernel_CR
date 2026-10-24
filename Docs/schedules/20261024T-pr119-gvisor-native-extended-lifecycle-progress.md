# gVisor 原生私有文件布局扩展验收进度

## 开发内容

沿用已经通过完整 SDK 的 gVisor 218d85378357f9726fc3c0f7cf878cf19772d360 / sandboxd 21fb4668431cef88d05b7a789a2bd9a5e19e827c，补新布局的分支和跨进程重启生命周期验证。主进程存活不等于后台输入已经结束，因此正常匿名私有文件与真实 `pages.img` 输入分别识别、分别验证。

所有执行仅 BareMetal 本任务独立 Pod/命名空间。无本地编译测试，无产品代码/制品替换，无共享服务或宿主参数变更。部署已采用真实就绪门：除 Pod Ready 外，核对新 ADX 会话、当前 Pod 路由、运行时能力和可调度资源，并连续稳定观察后才启动 SDK；本轮沿用已通过的部署，不重复滚动。

## 修改内容

新增验收脚本目录 `tools/pr119-pod-20261024/experiments/gvisor-native-extended/`：

- `driver01.py` / `sdk-two-branches01.py`：复用既有复杂私有文件测试，增加同一快照两个实际恢复分支、各自持续写/保存恢复、原快照再恢复及忙删除。
- `driver02.py` / `sdk-role-restart01.py`：三个角色独立 SIGKILL 验收；按私有文件设备号/inode 验证匿名文件，保留真实检查点名字检查。首次探针在信号前重复计数辅助进程，失败记录保留。
- `recover-role-preflight01.py`：只处理首次失败终态指向的独占 SDK 实例，先证明没有故障注入、验证未保存根文件和 512 MiB 负载仍可读，再由 SDK 删除，不直接删磁盘或杀运行时。
- `driver03.py` / `sdk-role-restart02.py`：同时匹配 `runsc-sandbox` argv 与 `gvisor_sentry` 实际 ELF，排除共用 ELF 的辅助进程；不削弱输入/匿名文件身份或权威引用断言。
- `hold-reader-role01.py` / `sdk-held-reader01.py` / `driver04.py`：准备严格匹配实际命名 `pages.img` 的短停屏障；从 `/proc/<pid>/root` 校验对应名字/inode，校验角色/运行时 ELF、PID 开始时间、任务 cgroup 和容器身份，最多短停三秒后在 finally 恢复。当前准备不等于已验收。
- `hold-reader-role02.py` / `sdk-held-reader02.py` / `driver05.py` / `recover-held-preflight01.py`：首次严格输入检查在信号前因 Sentry 隔离根目录而查错视图，另存为使用目标 Pod sandboxd 的挂载视图；与真正输入 FD 比较设备号/inode。只读证明同一目录在 sandboxd 可见、Sentry 根视图不可见；失败报错不能据此算作后台已完成。先校验并删除首轮独占资源，再执行新测试。

新增七节检查 `Docs/checks/20261024T-pr119-gvisor-native-extended-lifecycle.md`，同步 `VERSION.md`；不改移交文档或正式默认值。

## 测试结果

| 测试 | 结果与口径 |
|---|---|
| 双恢复分支 | extended01 rc=0；三次同节点回滚，同一快照两个恢复分支独立写，分支再次保存/恢复、原快照重新恢复和忙删除通过；总六次保存、五次显式 reload |
| 首次角色探针 | restart01 rc=1，断言“应有一个运行时”失败，发生于任何信号之前。只读 /proc 确认一个主进程与空 argv 的辅助子进程；失败保留，不计产品回归 |
| 失败实例恢复/清理 | restart02 recovery-terminal rc=0，未保存根文件、512 MiB 负载、一个真实主进程及匿名文件身份通过，SDK 删除实例 |
| sandboxd 重启 | restart02 的 sandboxd 子用例 rc=0：原 VM PID、未保存状态、匿名私有文件 inode、两份保护引用及后续保存恢复通过 |
| adxlet / Coordinator | 两个子用例均 rc=0，原进程/私有文件身份、未保存状态、两份引用与后续保存恢复均通过；三个角色整轮 rc=0 |
| 真正仍打开的页输入跨重启 | held-reader02 已实际注入且同一读者恢复，但之后原实例退出，整轮 rc=1；后续两个角色未执行。不能拿上述普通重启替代 |
| 只短停读者的控制组 | control01 因原失败记录已自动退休而在预检退出，未注入；control02 rc=0，使用新独立生产者/快照，相同制品、1 GiB 负载，只短停恢复而不杀角色；完整状态、引用和后续保存恢复通过，SDK 已清理 |

正确性样本使用 1 CPU、2 GiB 配置内存、1 GiB 私有盘。进程重启测试为 512 MiB 应用负载；两个节点仍在同一 BareMetal 物理机，不作为性能数据或真实多机故障域结论。其他故障、同代码性能配对与远端只读基线加本地差异仍未完成。

### 可复现步骤

先只读核对已有输出，不覆盖原目录：

```sh
cat "$ROUND/tap-checksum-fix/gvisor-native-extended01/terminal.json"
cat "$ROUND/tap-checksum-fix/gvisor-native-role-restart01/terminal.json"
cat "$ROUND/tap-checksum-fix/gvisor-native-role-restart02/recovery-terminal.json"
cat "$ROUND/tap-checksum-fix/gvisor-native-role-restart02/launch.json"
cat "$ROUND/tap-checksum-fix/gvisor-native-role-restart02/terminal.json"
cat "$TASK/acceptance/runs/shared-gvisor-native-role-restart02-sandboxd/terminal.json"
```

远端启动前解析脚本与嵌入探针语法、核对输入档案和每文件 SHA；实际命令与固定任务路径见目录内驱动。包含凭据的 SDK 环境文件只在远端引用，不复制其内容。保留失败时先查实例/进程身份和终态，不能直接重启整个驱动。

现场：双分支资源和首次失败实例已由 SDK 删除；在途重启用例不清理依赖。保留旧实验的一份失败盘，不误删别人的资源。无共享服务重启或全局缓存清理；继续保留 650 GiB 宿主可用空间门。
