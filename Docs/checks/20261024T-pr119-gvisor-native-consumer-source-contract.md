# gVisor 私有可写层消费适配的源码边界检查

## 1. 问题

继续 JuiceFS 原生克隆对照，复用已有实现；区分 gVisor 私有可写层与应用内存，不能通过移动公共 filestore 顺带改变 Firecracker 的内存、运行目录和其他运行时。新候选须通过完整运行时与 SDK 验收后才算交付。

## 2. 方法

【源码】独立 sandboxd 工作树 `codex-pr119-gvisor-native-consumer-20261024`，基于已验收 fdb145cf51f340dc46ebea3713c342b4ec93b127，选择复用 PR #78 的 ed73291288f66f39ee9ff7c924d83479dc9f9062 中已有 checkpoint_mode、工件清单及非消费式采纳；保留现役 BackgroundRestore 和 CheckpointSyncConfig。未改正式运行时制品 pin。

检查 `config.RunscConfig`、`runsc.NewHandler`、`Client.Create`、`filestoreRestoreDirectory`、`openRunscWritableRoot` 和 `verifyProcessFilestores`。gVisor 匹配候选精确基于 .5 源码 87e8441b6，包含原生 copy_file_range 克隆和复制前等待后台输入；完整组件门尚在执行。本检查只说明当前未验收源码合同，不冒充测试结果。

## 3. 数据与证据链

| 项目 | 当前源码行为 |
|---|---|
| 默认行为 | 不配置新目录时维持公共 filestore，checkpoint_mode 默认 full；现役部署未切换 |
| 私有目录选择 | RunscConfig 新增 writable_storage_dir 与 writable_storage_filesystem，要求成对提供；Handler 只改变自己的 RootFileOverlay、OCI RootfsOverlayDir 和客户端 FilestoreDir，不改全局配置 |
| 挂载缺失与替换 | 复用 Firecracker 已有持目录描述符、inode 与 mount ID 的合同；目录必须预先存在、无符号链接、文件系统类型正确，后续目录被替换则报错 |
| 运行中的实际文件 | Client.Create 完成后、用户程序启动前，读取已创建 Sentry 的实际私有文件描述符，检查常规文件、设备身份和 mount ID，防止配置名与实际路径不一致。进程开始时间前后校验；失败调用原有 Delete 并保留清理错误 |
| 恢复副本位置 | 沿用非消费式采纳，私有匿名副本可位于 checkpoint 的 filestores 目录；允许其在同一卷上，不要求必须放到新运行目录，不修改原工件 |
| 后台读者 | 私有克隆完成不等于完整 checkpoint 不再使用；应用内存仍可能继续读取旧页文件，必须保留现有 ADX 引用和结束证明 |
| 发布前持久化 | 冻结内捕获等待上一轮私有文件后台输入；副本 Sync、清单校验及现有最终输出同步/ADX 提交仍保留，不以克隆返回代替发布成功 |
| 容量 | 本候选没有改变节点容量账或把共享卷容量当节点本地容量；生产远端空间准入与孤儿处理仍是后续工作 |

新增回归覆盖错误文件系统、缺失目录、符号链接、同一文件系统上的目录替换、打开后删除的匿名文件描述符、采纳目录授权及不同运行时配置隔离。消费qa02远端已执行这些回归三轮，并通过fmt/vet/全仓单测、runsc/config/server/network/FC race及生产构建；实际Sentry/SDK尚待候选部署验收。

## 4. 结论

【源码】消费层复用了已有模式与清单，不另建 checkpoint catalog，不重写 gVisor 的私有 tmpfs/MemoryFile，也不改变公共 SDK 边界。专有目录将本次实验变量限定为 gVisor 私有文件数据后端。

【质量门实测】完整匹配六ELF包与消费层远端完整源码门均通过，新sandboxd SHA-256 f81eec47352f3ec71843f585da758b75862e8139f2025c0db9159cd29b8c059b。两运行时SDK、真实Sentry目录核验、三代状态/分支隔离、进程重启与性能对照尚需实际完成。现役仍 fdb145c/image02/旧 runsc .4，源码未提交推送；不能把四个 gVisor 相关组件测试通过等同本消费层或完整 SDK 通过。

## 5. 建议与改进项

先等完整 gVisor 组件/race/bundle 成功，再运行消费层 fmt/vet/全仓单测/相关 race/生产构建；失败只在新任务输出修复，不覆盖原证据。质量门通过后，制作固定完整六 ELF 包加该 sandboxd 的独立镜像，核对实际字节，使用新会话/真实路由/可调度等待门执行完整 SDK。之后才做同代码/内存模式的 full 与原生克隆交替数据，不改默认后端；文件克隆也不替代尚未实现的远端只读基线加本地差异路线。

## 6. 可复现步骤

以下源码检查可本地执行，所有编译测试必须远端：

```sh
git -C "$SANDBOXD_CANDIDATE" rev-parse HEAD
git -C "$SANDBOXD_CANDIDATE" diff HEAD -- config/config.go pkg/runtime/runsc/handler.go pkg/runtime/runsc/client.go doc/checkpoint-restore.md
# 远端独立任务，先看 terminal 再看 current，不覆盖已有输出：
cat "$ROUND/tap-checksum-fix/gvisor-native-clone-bazel04/terminal.json"
cat "$ROUND/tap-checksum-fix/gvisor-native-consumer-qa01/launch.json"
cat "$ROUND/tap-checksum-fix/gvisor-native-consumer-qa01/terminal.json"
```

实际消费层驱动与门命令位于 `tools/pr119-pod-20261024/candidates/gvisor-native-consumer/`。输入清单记录精确基线和每个候选文件 SHA，远端格式化后另记摘要；不得在本地运行该质量脚本。

## 7. 现场清理披露

本轮只在独立源码工作树及任务远端目录写候选/脚本，消费层驱动登记等待完整运行时依赖；没有部署新制品、创建 SDK 实例、移动公共 filestore 或修改共享服务。源码不混入已验收交付，失败目录原件保留。远端只按本任务 CID/标签处理构建进程，保留宿主 650 GiB 余量；没有本地编译测试或宿主包安装。

## 续记：核心 SDK 与源码交付

消费层最终提交21fb4668431cef88d05b7a789a2bd9a5e19e827c、匹配gVisor218d85378357f9726fc3c0f7cf878cf19772d360，均推个人fork且核对。实际sandboxd f81eec47…/完整运行时包63aa2353…未重建；官方76项、两种运行时各三轮512MiB内存/64MiB根文件回滚和双向接管通过。最终实例/运行时/僵尸0、15文件SHA一致。前文未提交/待SDK状态为当时检查状态；完整故障/分支矩阵与同代码性能尚未完成。见[阶段总结](../stages/20261024T-pr119-gvisor-native-sdk-stage-summary.md)。
