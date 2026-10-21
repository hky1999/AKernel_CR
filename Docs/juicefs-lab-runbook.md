# 独立 JuiceFS 功能实验部署说明

使用专用远端测试机，不占用原共享机器已使用的端口或服务。辅助脚本发现冲突时会拒绝继续，不会停止其他任务。

已验收客户端版本为 `juicefs version 1.4.1+2026-07-30.0b90c7d`。历史功能环境使用 PostgreSQL 17（实测17.11）和 Ceph 20.2.4 RGW。脚本中的历史镜像标签不是生产高可用设计，也不能替代不可变镜像摘要。

仅将辅助脚本源码放入新任务配置；不要把历史 `secrets/`、生成的 YAML、Redis 数据或 JuiceFS `.config` 内容放进 Git。将固定版本 JuiceFS 客户端安装到任务私有 `bin/` 并置于 PATH 前部。ADX、sandboxd 和运行时产物必须对应交付清单，并配套正确的静态 guest agent/initrd。

现有辅助脚本提供以下入口：

```text
lab.py --root ROOT {init,start,format,mount,unmount,stop,status,check-data,exec}
node_network.py --root ROOT {up,down}
native_profile.py --root ROOT --generation GEN --volume-uuid UUID --runtime {runsc,firecracker}
runtime_nodes.py --root ROOT --generation GEN --node {source,target} {setup,status,exec,stop,...}
short_profile.py --root ROOT --generation GEN [--node NODE] {prepare,activate,filestore,...}
```

节点专用的 mount/exec 参数见各入口的 `--help`。配置代次名采用 `native` 加两位数字。任务根目录必须以 `cn-a0-adx-juicefs-` 开头，使用规范化路径，且不可被组用户或其他用户写入。

部署顺序为：初始化/启动/格式化存储，创建本任务网络，启动两个独立客户端挂载，确认卷 UUID 相同，生成 native 配置，创建运行时命名空间与 cgroup，绑定短而稳定的 filestore 路径，校验配置，确认节点注册和资源就绪，最后运行 SDK 探针。两节点就绪前不运行 SDK。

配置 ADX 时只读取格式 UUID，不打印可能含对象存储凭据的完整 JuiceFS `.config`。两个挂载使用相同 UUID，但各自保留独立挂载和缓存状态。已验收持久化契约要求关闭 writeback，PostgreSQL 的 fsync 和 synchronous commit 保持开启。

`configs/` 下仅提供配置片段，不是完整部署配置。启用 `checkpoint_storage` 时不保留旧 `checkpoint_dir`。新环境相关读者退出确认门禁通过前，保持 checkpoint 自动 GC 关闭。不能通过关闭 cgroup 隔离、使用不安全路径别名或关闭 TLS 校验来绕过准入错误。

原配置生成器默认值属于历史实验骨架。应明确放置新构建组件，配置已验收的 Firecracker 本地 `storage_dir`，并在两个任务挂载命名空间内保持同一个短 gVisor filestore 路径。不能在运行中的 Firecracker 实例下更改 `storage_dir`；源码会拒绝存储身份/根目录不匹配，而不是掩盖存量状态。

交付内容包含辅助脚本和配置契约，不包含原私有环境。仅重跑纯单测，不能证明全新主机部署、读者退出证明与安全回收、完整公共 SDK 矩阵已经通过。新部署应单独验收并留档。
