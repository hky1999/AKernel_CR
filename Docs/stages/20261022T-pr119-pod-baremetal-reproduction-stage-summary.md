# PR #119 BareMetal 独立 Pod 复现阶段总结

日期：2026-10-22。

**核心SDK链路已打通，不是生产验收，也不是下一阶段性能优化完成。** 详细数据和逐命令步骤见[检查文档](../checks/20261022T-pr119-pod-juicefs-sdk-failover-acceptance.md)，修改见[进度记录](../schedules/20261022T-pr119-pod-juicefs-sdk-progress.md)，事件见[脱敏JSON](../../evidence/pr119-pod-20261022/juicefs-sdk-failover.json)。

## 1. 完成了什么

固定PR #119的6ea004125eb4365ba06ba3c7b21c4fd80e4cdaac及配对组件；版本/摘要见[VERSION.md](../../VERSION.md)，不能拿父仓历史gitlink混搭另一套运行时。

| 项 | 本轮状态 |
|---|---|
| 环境 | 一台BareMetal上独立Kind集群，1个控制节点容器+2个执行节点容器，没有新增基础设施VM |
| 控制面 | etcd/API实测健康，ADX控制组件在控制节点 |
| 本地保存/主动回滚 | gVisor、FC公共SDK通过，含连续五轮、非法参数、完整内存 |
| 真共享存储 | JuiceFS+PostgreSQL+Ceph RGW，三个真实挂载，跨客户端内容和持久化配置通过 |
| 共享主动回滚 | 两运行时基本及512 MiB内存用例通过 |
| 跨逻辑节点接管 | 同一个公共SDK对象、不硬绑节点，两运行时均通过 |
| 根可写层与重新加入 | /tmp外1 MiB根文件、512 MiB内存、目标继续写；源重新加入后目标身份/内容不变，删除成功 |
| 全量故障/并发/GC | 未全执行，不能关闭所有正确性门禁 |
| 生产HA和性能领先 | 未验收；单物理宿主、单存储副本、测试块设备 |

## 2. 当前架构

~~~mermaid
flowchart LR
  SDK["公共 AKernel SDK"] --> API["API / 数据入口 Pod"]
  API --> CO["ADX Coordinator Pod"]
  CO --> REDIS["Redis：归属、恢复点、执行引用"]
  API --> A["执行节点 A 的 Node Pod：ADX / sandboxd / runsc或FC"]
  API --> B["执行节点 B 的 Node Pod：ADX / sandboxd / runsc或FC"]
  A --> XA["A 的独立 XFS filestore 配置"]
  B --> XB["B 的独立 XFS filestore 配置"]
  A --> JA["A 的 JuiceFS 客户端"]
  B --> JB["B 的 JuiceFS 客户端"]
  JA --> PG["PostgreSQL：文件系统元数据"]
  JB --> PG
  JA --> S3["Ceph RGW S3：文件数据块"]
  JB --> S3
  S3 --> OSD["单 OSD / 单副本 /40GiB测试镜像"]
  DNS["CoreDNS在本任务控制节点"] --> PG
  DNS --> S3
~~~

Kind节点是容器，Node Pod在其中运行；一个agent sandbox不等于再建一个Kubernetes Pod。Firecracker沙箱本身仍是被测microVM，这是运行时机制，不是为模拟节点额外造VM。

AKernel命名空间有5个长期Pod：两个Node、Coordinator、入口、Redis。存储有三个JuiceFS客户端、一个PG，以及operator、mon、mgr、OSD、RGW、exporter；安装完成Job和Kubernetes/CNI/DNS另计。

### 谁管元数据，什么时候进S3

ADX/Redis维护实例归属、匿名恢复点及执行引用；JuiceFS/PG维护目录、inode、数据块引用；S3存文件数据块。不是“只有一个S3”，也不是JuiceFS替ADX做catalog或调度。

沙箱内通过Unix socket发checkpoint，ADX决定capture/publish目录与恢复点。共享profile是distributed_fs；Node Pod挂载/mnt/akernel-shared，Kind节点挂载/srv/akernel-shared。目录名称不能替代持久化策略。

JuiceFS writeback关闭、block cache=0。文件写入可能在正式发布前就产生S3 I/O，发布确认和权威状态提交是另一层；不是所有数据只在publish最后一刻上传。本轮未测完分相字节与ACK瞬间断电语义。

### 私有可写层与恢复后写入

RWFS是沙箱私有可写层，不是多agent共享卷。配置的filestore是各节点普通XFS目录，没有为它再套loop；Ceph测试OSD的loop设备是另一件事。

本次FC恢复后打开的overlay.ext4实测在目标XFS，guest根目录为Linux overlay，upper/work在可写ext4内；内存文件仍在JuiceFS checkpoint，以私有写时复制映射作为恢复输入。这不是“恢复后全部数据都变成本地文件”，也不代表下一次checkpoint后映射永远不切换。

gVisor根目录overlay、/tmp为tmpfs，已实测根数据回滚。filestore配置XFS；但校验后只采到runsc-memory等匿名内存文件，未观察到filestore FD，**不把配置推断冒充恢复后实际介质已经查清**。采样晚于完整内存校验，未看到共享输入不等于恢复时没读JuiceFS。

本轮没有OverlayBD、NBD、P2P、节点LRU服务，也没验收多agent共享卷的授权/实时可见性。固定profile用EROFS运行时镜像且FC virtiofs关闭，不代表重写已有Nydus路线。

## 3. 数字与局限

| 操作 / 负载 | gVisor | Firecracker |
|---|---:|---:|
| 同节点、本地XFS、额外512 MiB；checkpoint单样本 | 729 ms | 2668 ms |
| 同节点、JuiceFS、同负载；checkpoint单样本 | 1117 ms | 5973 ms |
| 同节点本地/共享；SDK reload单样本 | 1014.590 /3061.137 ms | 2681.094 /6712.452 ms |
| 根RWFS 1 MiB+内存512 MiB；读取触发至根文件校验 | 2030.716、3265.111 ms | 4861.988 ms |
| 同上；读取触发至全内存校验 | 3656.914、4880.728 ms | 7646.183 ms |
| 同上；停止源之前至全内存校验 | 约36.7、36.4秒 | 约37.7秒 |

无额外512 MiB负载的本地五轮checkpoint P50为gVisor64 ms、FC2590 ms，不能和上表负载混用。

checkpoint完成包含持久化和控制确认，不是guest停顿；故障接管含检测、路由、重试，不是VMM内部restore。没有清Linux page cache，也没有S3字节统计；同宿主逻辑双节点不是真实跨计算机冷恢复，不能宣称超过E2B、AgentEnv或CubeSandbox。

## 4. 外部复现入口

1. [宿主预检](../checks/20261022T-pr119-pod-baremetal-preflight.md)：设备、XFS、资源、隔离。
2. [固定构建与SDK附录](../checks/20261022T-pr119-pod-build-sdk-command-appendix.md)：远端准备对应源码、镜像、二进制、SDK，不在本地编译。
3. [集群网络](../checks/20261022T-pr119-pod-cluster-network-and-node-startup.md)：私有Kind/Calico、cgroup、独立目录。
4. [本地基线](../checks/20261022T-pr119-pod-resume-local-sdk-acceptance.md)：先本地保存/回滚，再切共享profile。
5. [本轮检查](../checks/20261022T-pr119-pod-juicefs-sdk-failover-acceptance.md)：真存储、DNS门禁、共享SDK、根RWFS故障接管及清理。

`tools/pr119-pod-20261022/profiles` 是脱敏参考配置，不是一键任意宿主安装包；容器ID/PID/容量必须使用新任务真实值。故障前运行 `pin_private_dns.py`，不要把存储依赖也停掉。

父仓只存工具、配置、文档和小型脱敏证据；固定产品源码仍各仓独立维护，不复制源码/二进制，不变更三个gitlink。外部同事需要私有GitHub父仓权限，并自行生成任务凭据；Git中没有真实私钥、S3 key或kubeconfig。

## 5. 知识、遗留和现场

- etcd/API活着不足以证明故障环境正确：DNS曾与源节点共址，导致JuiceFS解析PG失败；改放置后同方向通过，旧失败不覆盖。
- /tmp是tmpfs，不能代替磁盘RWFS；本轮两种运行时都补了根文件数据。
- 主动reload与节点失联failover分开测试，不重复发有副作用的请求碰运气。
- 真实块设备进Kind还依赖设备节点、API schema和udev输入，容器Running不够。
- 两DNS副本同在一个控制节点只保护本实验，不是生产HA；配置、FD采样、全生命周期I/O结论必须分开。

新增待办只记录在检查文档第5节，不另改移交文档。三次早期创建就绪超时未归因；全量故障/并发/GC、生产多机副本与安全告警仍未收口。

最终etcd/API、三节点及任务Pod健康，权威目录没有Environment记录。集群和存储保留，宿主可用约789 GiB，没有清他人资源。inotify=1024未持久化，退役且核对全局依赖后恢复128。原始日志可能含控制令牌，不上传；仅小型脱敏数据进入父仓。
