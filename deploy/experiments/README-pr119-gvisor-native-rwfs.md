# gVisor 私有可写层 JuiceFS 原生克隆实验

本实验的核心 SDK 链路已通过，尚未推广为生产默认后端。先读[核心阶段总结](../../Docs/stages/20261024T-pr119-gvisor-native-sdk-stage-summary.md)、[独立清单](../../delivery/pr119-gvisor-native-rwfs-20261024.json)和[本轮白名单范围](../../Docs/checks/evidence/pr119-gvisor-native-20261024/scope.json)。

只给 gVisor 私有文件数据选择专用 JuiceFS 目录，复用现有 tmpfs/MemoryFile、冻结内捕获和非消费式恢复。公共filestore仍为XFS，FC保持上个实验已验收的布局，应用内存机制和只读镜像不随本字段迁移。正常文件写入会影响JuiceFS/S3，guest tmpfs的fsync也不等同远端持久化确认；checkpoint仍须完成实际同步和ADX提交。

使用组件候选分支，而不是更新父仓历史gitlink或正式runtime pin：

```sh
git -C "$GV_SRC" fetch https://github.com/hky1999/gvisor.git codex/pr119-juicefs-native-clone-20261024
git -C "$GV_SRC" checkout --detach 218d85378357f9726fc3c0f7cf878cf19772d360
git -C "$SDB_SRC" fetch https://github.com/hky1999/sandboxd.git codex/pr119-gvisor-native-consumer-20261024
git -C "$SDB_SRC" checkout --detach 21fb4668431cef88d05b7a789a2bd9a5e19e827c
```

在新建的远端独立环境编译测试。不要对共享或他人的工作树执行checkout。gVisor使用上游已有的构建依赖、Bazel8.3.1及固定源码中的依赖图；本轮私有构建容器4CPU/8GiB，Go基础镜像1.25.5，Bazel使用源码所固定的工具链。clang、libbpf和ARM64交叉编译器只安装在该私有镜像，不装宿主机。

```sh
# 仅在远端私有构建容器、固定源码中执行：
bazel test --jobs=4 //pkg/sentry/checkpoint:clone_filestore_test //pkg/sentry/pgalloc:pgalloc_test //runsc/container:filestore_snapshot_test //runsc/boot/filter/config:config_test
bazel test --jobs=4 --config=race --runs_per_test=3 //pkg/sentry/checkpoint:clone_filestore_test //pkg/sentry/pgalloc:pgalloc_test //runsc/container:filestore_snapshot_test //runsc/boot/filter/config:config_test
bazel build --jobs=4 //debian:gvisor-release-tar
# 远端 sandboxd 私有构建容器：
make check-fmt
make vet
make test TESTFLAGS='-count=1'
go test -race -count=1 ./pkg/runtime/runsc ./config ./internal/server ./pkg/networkmanager ./pkg/runtime/firecracker
make release-binary
```

本轮已测包与ELF在源码提交前构建，源逐文件一致；重新构建产生新摘要时，应登记自己的新制品并重新验收，不能称与本文原字节相同。完整包包括runsc、containerd shim及相邻`gvisor-bin/`内四个程序，必须一起安装。不要混装旧配套程序，也不要把未经完整兼容套件推广的候选写成正式release pin。

合并[配置片段](pr119-gvisor-native-rwfs.toml)前，管理员须在各任务客户端创建对应专有目录，核对它确实位于同一JuiceFS卷且不是符号链接；缺失或挂载替换应报错，不得退回本地。保留`writeback=false`和既有最终输出同步，不把公共filestore整体bind到JuiceFS。切换前排空旧实例，本配置不实现运行中存储迁移。

复用父仓既有Pod/ADX/SDK部署与JuiceFS配置，用固定完整包和新sandboxd制作独立镜像，再执行：新会话注册/路由/资源连续三次稳定、两端15个实际文件摘要、官方76项、各三轮状态、双向接管及最终盘点。历史实际驱动在`tools/pr119-pod-20261024/candidates/gvisor-native-consumer/`，含固定旧任务身份和目录；用于审计，不能在另一主机不经适配直接执行。新环境应生成独立配置和输出，凭据通过自己的Secret或环境注入，不入库。

当前仍需补新布局的完整分支/故障/读者重启与同代码性能对照；单物理机逻辑双节点结果不替代生产HA或真实双物理机验收。已有FC十组对照属于上一固定组合，不冒充本组合已重跑该性能矩阵。
