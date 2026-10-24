# PR #119 gVisor 原生克隆的核心 SDK 验收阶段总结

本阶段已通过组件质量门、完整匹配运行时包、官方 SDK 76 项、两种运行时各三轮完整状态回滚，以及各自两个方向的跨节点接管。源码已推送个人 fork。**这代表新组合的核心 SDK 链路跑通，尚不代表生产验收完成或性能已经优于旧路线。**

## 1. 阶段定位与版本

承接[下一阶段执行计划](../plans/20261023T-pr119-sdk-juicefs-clone-local-delta-next-phase-plan.md)的阶段二。上一阶段已完成 Firecracker 的 JuiceFS 私有盘接入及十组后端交替；本轮补 gVisor 的原生克隆和 sandboxd 消费适配，不修改 ADX/API/SDK，不改变应用共享卷与只读镜像路线。

| 项目 | 本轮实际版本 |
|---|---|
| gVisor 源码 | [218d85378357f9726fc3c0f7cf878cf19772d360](https://github.com/hky1999/gvisor/commit/218d85378357f9726fc3c0f7cf878cf19772d360)，分支`codex/pr119-juicefs-native-clone-20261024`；基于`.5`源码87e8441b6，10文件 |
| sandboxd 源码 | [21fb4668431cef88d05b7a789a2bd9a5e19e827c](https://github.com/hky1999/sandboxd/commit/21fb4668431cef88d05b7a789a2bd9a5e19e827c)，分支`codex/pr119-gvisor-native-consumer-20261024`；基于fdb145c，11文件 |
| 实际 sandboxd | SHA-256 `f81eec47352f3ec71843f585da758b75862e8139f2025c0db9159cd29b8c059b` |
| 完整 gVisor 包 | 67566256字节，SHA-256 `63aa235350012e44020c8a9b404c677d2ce8894f167249ca7e5516ba3970cafa`；包含runsc、shim与四个配套程序，全部amd64 ELF |
| 实际 runsc / sentry | `0a7c6571…` / `30bf445c…`，完整摘要见证据 |
| 业务镜像 | `365f7971f895-gvisor-native02`；CRI `sha256:0806341c5c1939a52497c4dfb28d6b111819322405b33e0f1bb344145fc38660`；三个Kind节点导入一致 |
| 其余组件 | 保持当前固定组合：AKernel365f797、实际ADX/Execd制品6fb53d7、SDK公共0.2.0rc3/原生0.1.0rc3；FC/内核/initrd/根镜像字节不变 |

两源码提交普通push后经ls-remote核对，两工作树干净。二进制在源码提交整理前构建，其被测源文件逐一匹配上述提交；没有提交后重建并冒充原验收字节。正式运行时release pin、默认产品后端和父仓历史gitlink均不因这个可选实验改变。

## 2. 完成项

1. 复用gVisor既有冻结内私有文件捕获、清单和非消费式采纳，在两个入口共享文件系统复制函数；先尝试FICLONE，再在规定的不支持错误下尝试copy_file_range，保留短复制、中断、部分失败和文件身份检查。补齐sentry所需的受限系统调用规则。
2. 修复真实后台装入与再次捕获的顺序窗口。旧版在输入仍阻塞、或后台输入失败时仍可能返回快照成功；复制前等待旧私有文件输入并传播错误。真实加载器屏障先复现两项旧行为，再转绿，最终pgalloc三轮race通过。
3. sandboxd复用已有full/reflink模式、严格清单与非消费式恢复，不另建catalog。新增runsc专用可写目录及文件系统配置；保留公共filestore、FC运行布局、背景恢复和最终输出同步。
4. 目录必须预先存在于指定文件系统。持目录FD/inode/mount身份，并在create后、用户程序启动前核验实际Sentry私有文件描述符；错误拒绝启动，不静默退回本地。
5. 完成远端组件质量检查、匹配完整包、消费层fmt/vet/全仓单测/相关race/生产构建，再制作固定镜像。
6. 本任务部署先通过新ADX会话、真实路由、可调度资源的三次稳定观察，核对两Node各15个组件文件摘要及Secret身份，再发SDK。

## 3. 当前存储位置

| 数据 | 本轮实验位置与方式 |
|---|---|
| gVisor私有文件数据 | 原有用户态tmpfs/私有MemoryFile机制，匿名后端文件选择JuiceFS；捕获和恢复采纳复用卷内克隆，恢复副本独立，不改原检查点文件 |
| FC私有RWFS | 延续已验收的JuiceFS独占overlay.ext4文件，guest ext4/virtio-blk、Async/Writeback不变 |
| 应用内存 | 保持各运行时既有机制；没有因为新runsc目录而搬迁FC live-memory或公共运行目录。完整检查点仍包含应用内存保存/恢复成本 |
| 公共filestore | `/home/akernel/filestore`仍是本地XFS |
| 检查点与共享存储 | 既有JuiceFS客户端、PostgreSQL元数据与S3/Ceph RGW数据后端；客户端缓存配置4GiB、writeback=false。没有节点间P2P缓存传送 |

只在runsc配置增加三个字段：checkpoint_mode、writable_storage_dir、writable_storage_filesystem。TOML解析树逐项对比，FC和其余配置不连带改变。gVisor的guest tmpfs fsync不等同远端持久化确认，不能与FC ext4同步写延迟直接等同。

## 4. 验收与数字

### 4.1 核心链路

| 检查 | 结果 |
|---|---|
| 官方SDK | FC 8集成+30独立端到端；gVisor 8+30，合计76全部OK |
| 三轮完整回滚 | 每运行时一实例三轮，512MiB应用内存+64MiB根文件逐轮校验；6/6通过 |
| 跨节点接管 | 每运行时A→B、B→A各一次；512MiB完整内存+1MiB根文件。源离线、未显式reload，由公共SDK恢复；源重新加入后目标内容保持；4/4通过 |
| 最终盘点 | Environment0，两Node运行时及僵尸进程均0；五个业务Pod为候选镜像，API/路由/资源正常，两Node各15文件摘要一致 |
| 遗留现场 | 原FC失败盘保留1份，目录哈希30386ede…；gVisor专有根只剩任务marker。没有清理未知旧数据 |

这是同一BareMetal上的逻辑双节点、独立JuiceFS客户端，不能替代双物理机或生产故障域验收。

### 4.2 本轮三次功能试跑耗时，不是性能前后对照

条件：单实例连续三次Full/无压缩，1CPU、配置2GiB RAM、512MiB应用状态、64MiB根文件、1GiB私有存储；自然/温缓存，无全局清缓存。源码/运行时已变化，**没有同代码旧后端配对样本，不能判稳定提速**。

| 操作 | gVisor三次，ms | FC三次，ms |
|---|---|---|
| checkpoint请求完成 | 1634 / 1426 / 1525 | 5403 / 7172 / 8022 |
| guest观察到的最大停止间隔 | 1534 / 1311 / 1406 | 5071 / 6850 / 7773 |
| SDK reload返回 | 1635 / 1612 / 1654 | 3040 / 3052 / 2536 |
| reload到完整内存和根文件校验结束 | 3877 / 3920 / 3886 | 5652 / 5682 / 5182 |

gVisor每轮捕获期间S3 PUT约563–564MB，FC约2GiB；运行期写入与恢复读取另计，不能只依据这些数字宣称克隆没有持久化代价。完整原始口径与字节计数见[状态回滚证据](../checks/evidence/pr119-gvisor-native-20261024/state-rounds.json)。上一轮FC十组配对数据仍是独立有效结论，本轮三次不替代它。

## 5. 本轮发现与处理

- 完整gVisor构建还需要clang/libbpf与ARM64交叉编译器，即便最终包为amd64；只在私有构建镜像补齐官方已有依赖，未安装宿主软件。
- 旧测试为了比较前1MiB，反复把1GiB稀疏文件整份读入，race时触发本任务8GiB cgroup OOM。通过Podman标签/CID和内核记录确认；仅改为读取所断言范围，保留字节及短读断言，三轮转绿，不增额或跳过测试。
- 镜像首轮新增RUN被任务cgroup父目录约束拒绝；保留失败。后续仅检查停止的基底容器、验证四helper清单，再COPY完整六程序，不改变宿主cgroup或降低隔离；检查容器已删除。
- 私有文件克隆独立后，完整检查点仍可能被应用内存后台读者使用。不能因clone完成就提前释放所有输入保护。

## 6. 遗留与下一步

1. 新gVisor原生布局仍需完整分支隔离、后台装入期间写入/再次捕获、挂载与同步故障、源持续写及sandboxd进程死亡/读者重启验证；既有旧版证据与本轮组件回归分开，不自动继承为新组合的全故障验收。
2. 以同一新代码、同一完整运行时包比较本地full与JuiceFS原生克隆，交替顺序并分别统计运行期写、guest停顿、远端提交、恢复首次可用、完整读取量；不拿旧.4和新.5的差值归因于存储开关。
3. 完成后再进入远端只读基线加本地差异路线，继续评估成熟后端，不把本轮功能通过算作该路线已实现。
4. 正式runtime候选推广、完整兼容套件、生产容量准入/孤儿对账、真实双物理机与存储HA保持独立门；不在本轮修改默认值。

详见[SDK就绪检查](../checks/20261024T-pr119-gvisor-native-sdk-readiness.md)、[组件回归检查](../checks/20261024T-pr119-gvisor-bazel-async-snapshot-regression.md)、[消费层检查](../checks/20261024T-pr119-gvisor-native-consumer-source-contract.md)和[脱敏证据范围](../checks/evidence/pr119-gvisor-native-20261024/scope.json)。编译测试、镜像制作和验收全部远端；旧环境、共享服务及宿主参数未改。
