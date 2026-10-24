# gVisor JuiceFS 原生克隆：精确版本与候选边界

## 1. 问题

完成 PR #119 的 SDK 验收后，如何复用 gVisor 的私有文件数据保存/恢复接入 JuiceFS 原生克隆，并避免无关升级或把应用内存也迁到共享卷。

## 2. 方法

只读官方 GitHub release、annotated tag 与本地精确 Git 对象。`.5` 标签对象 aeef96cde3f944b291bf066664d52b5b83967af5 指向源码 `87e8441b6db18219fbb941378cfcb2883750b07c`，发布包 SHA-256 a7d47e52e842d478494cf92892110d18d3f320040087aaa1ba64dbe257a139ef。候选工作树 `codex-pr119-gvisor-native-clone-20261024` 从该源码创建；不是将另一条 release-20261012 rebase 的 7c087665f 混入当前对照。

官方来源：[发布说明](https://github.com/akernel-dev/gvisor/releases/tag/release-20260817.0-akernel.5)、[精确基线](https://github.com/akernel-dev/gvisor/tree/87e8441b6db18219fbb941378cfcb2883750b07c)。发布说明中的 CI 是上游消费组合的历史记录，不代替本任务的完整 SDK。当前运行中仍是原 `.4` bundle 和 fdb145c；没有更换制品。

## 3. 数据

| 位置 | 源码事实及当前状态 |
|---|---|
| pgalloc/save_restore.go:SnapshotToFd | 已有冻结窗口内 FICLONE、目标同步与指纹。候选改为共享 CloneFilestore 入口；尚未远端编译或执行 |
| runsc/container/filestore_snapshot.go:adopt | 已有按资源 ID/大小/指纹核对与非消费式私有克隆。候选复用全部检查，仅替换克隆入口，并补失败分支的源 FD 关闭；不使用消费原件绕过克隆 |
| 新 checkpoint/clone_filestore.go | 先 FICLONE；只对不支持/同文件系统挂载边界错误尝试 copy_file_range。要求不同 inode、空目标、普通文件与同文件系统，不做用户态整文件复制回退；短复制继续，EINTR 重试，零进度/部分错误失败。调用者仍负责冻结、失败目标弃置、发布前同步 |
| sentry seccomp | 增加两个非负已持有 FD、flags=0 的 copy_file_range 规则；不关闭过滤。仍需真正 sentry 运行证明 |
| kernel/kernel.go:saveMemoryFiles | 先以原选项保存 k.mf 应用内存，再对 private MemoryFiles 设置 ExternalContent；原生克隆只替代私有文件数据的序列化，应用内存捕获/恢复逻辑不改 |
| 新回归源码 | 准备短复制/中断、读写错误不得吞掉、部分失败与零进度、空文件、同 inode/非空目标拒绝。尚未执行，不算通过 |
| sandboxd 消费层 | 现役 fdb145c 尚不含 #78 的 reflink 模式。可从已存在的 #78 复用 client/handler、清单验证和对应回归；不整包混入别的修复或控制面 |

copy_file_range 是内核文件范围复制入口，本身不保证元数据克隆；本任务已有 JuiceFS 原语实测为零对象 GET/PUT，但候选 gVisor 仍须重新验证实际 FD、S3 流量和暂停时钟。

## 4. 结论

【源码】可以沿已有冻结与采纳协议做小范围适配，无需重写 gVisor 文件系统或应用内存恢复。必须同时覆盖捕获与非消费式采纳，不能只把 filestore 路径改成 JuiceFS 就宣布完成。

【状态】只有未提交候选，尚未编译、测试、部署或推送。FC 的当前十组对照仍在跑，为避免资源竞争，此时不在 BareMetal 编译候选。

## 5. 建议与改进项

正式 FC 测量结束、恢复布局并确认无 Environment 后，在远端独立容器依次验证克隆 helper、pgalloc/采纳/seccomp 相关回归，构建完整匹配的 runsc/四 helper/shim bundle。再以精确版本接入 sandboxd 的已有 #78 适配，保留默认 full 分支，更新合同与制品清单。

SDK 必须覆盖两代、两分支、打开后删除、mmap、截断/打洞、恢复后再写、保存失败与进程死亡；核对文件数据位置与应用内存位置，确认原工件不变。原 `.5` 与候选的能力/错误对照单列，不能把替换整个 bundle 的变化当成一个配置开关收益。

## 6. 可复现步骤

以下仅源码核验，不在本地构建测试：

```sh
git -C /home/keyang/AKernelWorkspace/codex-pr119-gvisor-native-clone-20261024 show -s --format=%H HEAD
git -C /home/keyang/AKernelWorkspace/codex-pr119-gvisor-native-clone-20261024 diff -- pkg/sentry/pgalloc/save_restore.go runsc/container/filestore_snapshot.go runsc/boot/filter/config/config_main.go
# 新增未提交文件另按 git status 与工作树内容核对，git diff 不会显示未跟踪文件：
git -C /home/keyang/AKernelWorkspace/codex-pr119-gvisor-native-clone-20261024 status --short
```

后续远端 Bazel 至少执行 `//pkg/sentry/checkpoint:clone_filestore_test`、pgalloc 外部内容保存/恢复、`//runsc/container:filestore_snapshot_test`、`//runsc/boot/filter/config:config_test` 与完整 `//debian:gvisor-release-tar`。这些是待执行门，不是本轮已通过记录。

## 7. 现场清理披露

只创建独立本地 Git 工作树和未提交源码/文档，不修改原开发工作树、子模块、运行制品或共享环境；没有本地编译测试。远端唯一在途测量仍为 FC 本地/原生布局十组对照，候选构建不会与其重叠。
