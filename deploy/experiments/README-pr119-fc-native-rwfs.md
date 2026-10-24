# Firecracker 私有可写盘的 JuiceFS 实验配置

本配置用于可选功能实验，搭配 `delivery/pr119-native-rwfs-20261024.json` 固定的 sandboxd fdb145c。默认复现组合仍按 `delivery/pr119-20261024.json`；不要混用两份清单里的源码与已测 ELF，也不要将本实验标成默认生产后端。

guest 保持 ext4/virtio-blk，宿主的每实例 `overlay.ext4` 放本任务 JuiceFS 目录。普通运行写入也会上传 S3；不是只在 checkpoint 发布时上传。gVisor 私有层仍本地，内存的现有机制不变，ROFS 仍沿用原路线。

`pr119-fc-native-rwfs.toml` 是两个新增字段的片段。必须合并进现有 `[plugin.runtime.firecracker]` 小节；不能把该片段直接作为 Helm 的整段 `node.config.sandboxd.config`，否则会丢掉原有配置。字段不配置时，沿用既有本地 filestore，实际文件系统由部署决定；本轮对照使用普通 XFS 目录。

在每个任务 Node 的私有命名空间中确认真实 JuiceFS 挂载，然后创建共享的独占目录。两端使用同一绝对目录；TASK_ID 必须替换为本轮唯一身份，不复用他人目录。

```sh
# 以下仅是本任务 Node 内的准备步骤，不在共享宿主直接挂载或改服务。
test "$(findmnt -n -T /mnt/akernel-shared -o FSTYPE)" = fuse.juicefs
CR_RWFS_ROOT=/mnt/akernel-shared/experiments/替换为本任务唯一ID/fc-rwfs
install -d -m 0700 "$CR_RWFS_ROOT"
# 将该绝对路径写入配置片段，合并至本任务原配置；保持原隔离与 TLS。
```

本实验沿用 JuiceFS 1.4.1、1 MiB 块、4 GiB 缓存、无压缩、writeback=false；元数据 PostgreSQL、数据 Ceph RGW S3。基础部署与凭据来源沿用固定复现文档中的 Secret，不在片段中填入密码、密钥或私有端点。

仅在本任务实例排空后替换其服务/Pod。除 Pod Ready 之外，要确认 ADX 新会话已注册、可路由、未暂停调度、运行时能力与公告资源达标并连续稳定，以及镜像、实际 ELF、挂载和 Secret 身份正确。任务专用执行脚本位于 `tools/pr119-pod-20261024/candidates/native-rwfs-rejoin/`，含历史固定路径和身份；新环境执行前必须适配，不能直接对旧任务重放。

功能验收包含官方 76 项、各三轮状态、两运行时双向接管、FC 相同 Pod 的即时节点退出、持续直接 I/O 和两运行时 sandboxd 崩溃重启。同代码十组后端交替已完成，20 实例/40 次状态通过，首次/再次 checkpoint 约 8.40→5.51 / 11.31→7.57 秒，但 4 KiB 逐次同步从约 0.300→9.588 ms；数据和口径见同日正式性能检查。真实多物理机/存储 HA、生产容量准入和旧 Pod 状态清理后的孤儿回收尚未完成。当前不能以节点本地盘的可用量代表 JuiceFS 后端真实容量，也不能按公共目录扫描批量删除未知归属的可写盘。

详情见 `Docs/checks/20261024T-pr119-native-rwfs-full-sdk-acceptance.md`；保留此前失败与诊断记录，不用换目录或清库将失败改写为通过。
