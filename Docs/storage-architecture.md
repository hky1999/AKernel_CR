# 存储架构与生命周期边界

## 控制面与元数据

公共 AKernel SDK 调用 ADX Environment API，由 API Server 和 Coordinator 将工作调度到 adxlet，再由 adxlet 驱动 sandboxd。Coordinator 的任务 Redis 保存 Environment 所有权、快照引用、checkpoint 读者预留和共享卷挂载关系，不是 JuiceFS 的 inode/数据块数据库。

读者保护必须在运行时启动前持久化。删除请求返回成功，不足以释放 checkpoint 读者；必须获得与具体执行实例绑定的可靠退出证明。超时、进程暂时不可见、租约经过一段时间或控制面重启，都不能单独充当退出证明。gVisor 会等待相关 namespace 持有者和后代进程退出，sandboxd 则保留跨重启所需的操作记录和身份信息。

## JuiceFS

每个逻辑节点拥有独立的 JuiceFS 客户端及挂载命名空间，但两者挂载同一个格式 UUID（标识同一个 JuiceFS 卷）。功能实验使用 PostgreSQL 保存文件元数据、Ceph RGW 提供 S3 对象数据服务；换成其他 S3 兼容后端前，需要另行验证持久性与故障行为。

不可变 checkpoint 必须在完成规定写入和同步屏障后才能发布。存在中间目录不等于已经发布或 READY。恢复后的运行时可能继续持有共享文件引用，因此回收前必须确认读者已退出，不能只按文件年龄自动删除。

JuiceFS 根据客户端配置和同步语义上传数据。已验收实验关闭 writeback（写回模式），但这不等于 AKernel 实现了独立后台发布队列，也不能把对象 PUT 次数当作 checkpoint 已经持久化的证明。

## 各类文件系统

- 只读根镜像：保留所选运行时现有的 EROFS / Nydus / virtio-fs 路线。
- gVisor 私有可写层：使用基于文件描述符的 filestore，明确配置 checkpoint 处理及后台恢复。
- Firecracker 私有可写层：使用已验收的本地 XFS 布局上的每实例 ext4 镜像；checkpoint 副本与运行中的磁盘不是同一个对象。
- 应用共享卷：对 JuiceFS 目录执行受控准入、所有者/被授权者校验及读写/只读挂载，不是私有 checkpoint 分支。
- 内存：保留各运行时现有机制。完整性校验可能在按需内存缺页读取前产生数据读取；API 返回快，不等于冷 S3 读取量少。

## 已验收的优化

sandboxd 对独立组件执行完整 SHA-256 校验，并发上限为2。不跳过完整性校验，不降低同步要求，也不声称文件大小或 mtime 缓存能够证明不可变代次身份。

实际已验收组合以源码清单和配对样本为准；未验收的 Coordinator 退出候选明确排除。

