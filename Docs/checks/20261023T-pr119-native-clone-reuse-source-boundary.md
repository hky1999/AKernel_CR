# 私有 RWFS 原生克隆的复用边界检查

日期：2026-10-23。仅源码检查，没有部署新候选或产生新的性能样本。

## 1. 问题

在 PR #119 SDK 验收之后比较 JuiceFS 原生克隆与远端只读基线＋本地差异层，先确定哪些现有代码可以直接复用，不能把修改 filestore 路径或启用 XFS reflink 当作已具备 JuiceFS 原生克隆。

## 2. 方法

只读检查以下精确源码/导出记录，没有本地编译测试：

- 实际验收的 sandboxd 基线 `d5acc3b5b673074e20fd8b7733d4035dbaeae1b0` 的 `pkg/runtime/firecracker/reflink.go`。
- 现有 runsc 制品报告的源码标识 `7fdef444b108` 对应 Git tree；实际 ELF 已在前轮按发布包摘要验证，新增开关是否存在仍需远端能力预检，版本字符串不单独代替载荷证明。
- 另一个本地可读候选 gVisor `7c087665fde39b6659ca3f21b14b42c16198619d` 的 filestore 捕获/采纳代码。这是后续候选，不能把其能力或门禁转记为当前 PR 组合已具备。
- `akernel-fs/sandboxd/patches/0001-shared-filesystem-support.patch` 及其 README 的历史 JuiceFS 克隆约定。它们是可复用的源码/实验参考，不代替本轮实测。

## 3. 数据

| 位置 | 源码事实 | 对下一步的含义 |
|---|---|---|
| sandboxd `reflink.go:51/64/99` | `cloneFileOpts` 首选 FICLONE，遇不支持后调用 `io.Copy`，同步版本还调用 `destination.Sync` | 可复用现有克隆和持久化外壳；Go 可能使用 copy_file_range，必须以实际 syscall 与对象读写计数验证 |
| akernel-fs 对该文件的补丁 | 修正“fallback 必为全量复制”的注释，说明 Go 可经 copy_file_range 进入 JuiceFS 元数据克隆 | 不必新造文件复制器；也不能仅凭返回 reflinked=false 判定发生全量搬运 |
| `7fdef444b108` | tree 中无 `runsc/container/filestore_snapshot.go`；搜索 FilestoreAdoptDir、SkipFilestorePages 和相应 CLI 开关无匹配 | 当前报告源码不具备后续候选的独立 filestore 捕获/采纳接口；先对实际 ELF 做能力门，再固定兼容新版本 |
| `7c087665f` `pgalloc/save_restore.go:238/255` | 冻结内的 SnapshotToFd 直接 FICLONE，错误即失败，随后 Sync 和 fingerprint | 文件数据与内核元数据同一时刻捕获的边界可复用；现有实现没有 JuiceFS copy_file_range 分支 |
| 同候选 `runsc/container/filestore_snapshot.go:191` | 非消费式采纳也直接 FICLONE；失败不自动走其他复制路径 | 不能把现有 XFS 测试当作 JuiceFS 支持证明 |
| 同文件 clone-on-adopt=false | 直接返回原 artifact 的可写 FD，属于消费式恢复 | 不能用此开关绕过克隆失败并继续宣称父快照不可变、多分支互不影响 |
| `runsc/boot/filter/config/config_main.go:125` | 捕获发生于受 seccomp 约束的 sentry，现有规则显式允许 FICLONE | 如补 host copy_file_range，需要审查完整过滤策略与 FD 约束，不能关闭隔离来做实验 |

FICLONE 是文件系统 reflink 的 ioctl，copy_file_range 是另一系统调用。akernel-fs 历史记录明确 JuiceFS 支持其文件范围克隆、不支持当时实验中的 FICLONE；本轮固定客户端/内核组合仍要实测，不能把历史结果写成当前验证。

## 4. 结论

【源码】FC 有可以直接复用的宿主文件克隆入口；是否实际进入 JuiceFS 元数据克隆，取决于同卷布局、Go/内核路径与 FUSE 能力，需要远端证明。

【源码】gVisor 的现有验收版、后续 filestore 候选和 JuiceFS 克隆支持是三件不同的事。后续候选能复用资源 ID、冻结内捕获、清单和私有采纳，但不能仅改目录就完成 JuiceFS 支持。

【外推，待测】FC 路线可能只需布局/生命周期适配，gVisor 至少需版本能力门和克隆入口适配。若成本过高，先保留已工作的后台恢复并测读量，符合原计划，不为统一后端引入新的暂停/恢复协议。

## 5. 建议与改进项

1. 先跑固定客户端的 FICLONE/copy_file_range 小型能力门；记录两个 FD 的真实挂载、返回值、分支隔离和 RGW 字节，不能只报耗时。
2. FC 先复用当前 cloneFile，保留 guest ext4、virtio-blk、VMM 和内存机制；证明 io.Copy 的实际路径后再安排公共 SDK 对照。
3. gVisor 先固定具备既有 filestore 能力的整组候选，并以其 Full 路径建立对照，再评估在同一冻结窗口内补 native clone。需要支持捕获与采纳两端，不只修其中一个。
4. 不使用消费式原件采纳绕过失败，不把完整性读取先做完再称为按需恢复；克隆后复用本轮复杂 RWFS、多读者、失败发布、超时和跨进程测试。

## 6. 可复现步骤

以下是只读 Git 对象检查，不编译或运行产品代码：

```bash
git -C /home/keyang/AKernelWorkspace/sandboxd-pr79-ci-fix-20261023 show \
  d5acc3b5b673074e20fd8b7733d4035dbaeae1b0:pkg/runtime/firecracker/reflink.go
git -C /home/keyang/AKernelWorkspace/runtime-integration-20261023/gvisor grep -n -E \
  'FilestoreAdoptDir|SkipFilestorePages|filestore-snapshot-dir|skip-filestore-pages' \
  7fdef444b108 -- runsc pkg/sentry
git -C /home/keyang/AKernelWorkspace/runtime-integration-20261023/gvisor show \
  7c087665fde39b6659ca3f21b14b42c16198619d:runsc/container/filestore_snapshot.go
git -C /home/keyang/AKernelWorkspace/runtime-integration-20261023/gvisor show \
  7c087665fde39b6659ca3f21b14b42c16198619d:pkg/sentry/pgalloc/save_restore.go
```

第二条无匹配退出 1 是源码搜索结果，不是构建或功能测试失败。实际能力探针与编译/测试后续只在 BareMetal 独立环境执行。

## 7. 现场清理披露

没有 checkout、修改或提交上述并行工作树，没有启动沙箱、挂载、克隆或编译，没有更换当前运行制品或父仓 gitlink。仅新增本检查文档；旧实验和共享服务未改。
