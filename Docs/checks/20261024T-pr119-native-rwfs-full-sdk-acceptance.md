# Firecracker 的 JuiceFS 私有可写盘：固定镜像完整 SDK 与状态验收

## 1. 问题

按用户批准补齐 ADX 真实就绪门，保留冷启动失败，再继续 gVisor、Firecracker 和 JuiceFS 跨节点完整 SDK 验收。此次检验的是可选实验布局：**Firecracker 的私有可写盘放 JuiceFS；gVisor 的私有可写层仍在本地 XFS**。不是两种运行时都已迁移的新架构。

私有可写盘保存单个沙箱对根目录的修改。Firecracker guest 仍使用 ext4/virtio-blk，改变的是宿主后台 `overlay.ext4` 文件的位置；不改变 guest 磁盘格式，也不增加宿主 loop 设备。

## 2. 方法

所有构建、单测、SDK 和故障测试仅在 BareMetal 原任务独立容器/私有 Kind 集群执行。两个执行节点位于同一物理机；不是两台物理机或存储高可用验收。

固定 AKernel 365f797、实际 ADX/Execd 6fb53d7、公共 SDK 0.2.0rc3、原生 SDK 0.1.0rc3。sandboxd 为基于 e3f402c 的 11 文件组合，已整理为 fdb145cf51f340dc46ebea3713c342b4ec93b127 并推个人 fork；实际 ELF `debbf268d1b1a8d4a07b9ac02be7084c3fa53c7cf794f0b1887ec65f7ace313b` 在提交整理前构建，源码 SHA 逐一一致，没有重建冒充。VMM/内核/initrd/runsc/根镜像和 ADX 载荷都保持固定，两个 Node 实际十个文件摘要逐一核对。

镜像 native-rejoin02：CRI 53669406… → 叶 manifest 2c28b22e… → config 6b4f0d92…，三个 Kind 节点一致。先在原故障源相同 Pod 内救援并完成两个方向即时退出，再按原 ConfigMap UID、资源版本和内容摘要移除临时 bootstrap 覆盖，最后部署固定镜像。不能用 Pod 名变化触发的基线清理来证明旧租约恢复成功。

SDK 前确认新会话已注册、可路由、未暂停调度、运行时能力与公告 CPU/内存/磁盘容量达标，连续三次保持同一身份；同时要求无遗留 Environment、真实挂载/路径、实际镜像及 ELF 正确、Secret UID 未变。没有改变调度语义。JuiceFS 1.4.1、1 MiB 块、4 GiB 客户端缓存、无压缩、writeback=false；PG 元数据与 Ceph RGW S3 仍为本任务独立测试后端。

## 3. 数据

| 验收项 | 结果与边界 |
|---|---|
| 源码质量门 | qa02 相关三轮回归、全仓 fmt/vet/test、server/network/FC race、生产构建通过 |
| 官方完整 SDK | FC integration 8 / standalone 30，gVisor 8 / 30，共 76，全通过、无跳过 |
| 三轮完整状态 | 每运行时各一实例连续 3 次 checkpoint/reload；512 MiB 应用内存、64 MiB 根文件、2 GiB 配置内存、1 GiB 私有盘，完整内存/根文件/进程身份回滚通过 |
| 正常节点故障 | 两运行时各 A→B/B→A，无显式 reload 的公共 SDK 自动接管、源重新加入、目标内容保持与最终删除均通过；sdk02 整轮 rc=0 |
| 即时节点退出 | 此前独立 force02 的 FC 两方向均通过，要求原源 Pod UID 不变且产品自行退休旧租约；不与普通正常关闭故障混作同一注入 |
| 真实持续直接 I/O | directio02 rc=0，guest 1 MiB 环形文件中 4 KiB 直接写入、同步和读回；5 次 checkpoint / 4 次恢复，跨节点两个分支各自继续写与再次保存通过 |
| sandboxd 进程死亡 | postSDK02 rc=0：FC 与 gVisor 各注入一次 SIGKILL，原 VM/运行进程和未 checkpoint 新状态保留，两份保护引用保留，随后 checkpoint/reload 正确并正常删除 |

性能只是分相试跑：每运行时一个实例的连续三轮，非后端交替、非三个独立实例，基础设施缓存已暖。单位毫秒。

| 操作/阶段 | 第一次保存 | 恢复后第二次保存 | 再次恢复后第三次保存 |
|---|---:|---:|---:|
| FC checkpoint 请求完成 | 5185 | 7689 | 7856 |
| FC 内存保存阶段 | 4847 | 7368 | 7556 |
| FC 私有盘保存阶段 | 15 | 14 | 15 |
| FC guest 观察到的最大调度间隙 | 4865.7 | 7384.5 | 7572.7 |
| gVisor checkpoint 请求完成，私有可写层仍本地 | 1531 | 1373 | 1594 |

FC 保存仍为 Full，即保存配置内存的全量映像：每轮约 2 GiB S3 PUT。恢复后再次保存还有约 0.65 / 0.77 GiB GET，未逐对象归因。新布局的 64 MiB 根文件写入并同步约 513.3 ms，计时包含 SDK 文件写入与 guest sync，不是纯后端单次 fsync。

此前 e3f402c 本地私有盘样本的三轮 FC checkpoint 为 8602/11223/11657 ms，盘复制 2863/3135/3298 ms、约 3 GiB PUT。现在盘阶段和上传量明显降低，但两个批次没有交替配对，不能把差值写成稳定整体提速。gVisor 没有迁移私有可写层，不将它的数值当作 gVisor 原生 JuiceFS 克隆结果。

小型白名单证据位于 `evidence/pr119-juicefs-tapfix-20261023/native-rwfs-rejoin-{sdk02,cross02,directio02,force02}.json`；原始配置、Secret、服务日志及 OCI 内部环境留在远端私有目录。`shared-native-rejoin-sdk01-…` 是本轮沿用的输出名，实际执行归 sdk02 / native-rejoin02，不表示第一版 ELF。

## 4. 结论

【实测】真实就绪门、固定镜像的官方 SDK、两运行时三轮状态与双向跨节点接管已通过。FC 的可选 JuiceFS 运行态私有盘具备功能验证依据，原缺失网卡租约与网络规则恢复问题有单独闭环证据。

【实测】同卷克隆将此次盘保存降到约 14–15 ms，但 guest 仍会因全量内存保存暂停数秒。当前结果不支持宣称整体达到或超过 E2B、AgentEnv、CubeSandbox，也不能用盘克隆时间代替 checkpoint 完成或 guest 停顿。

【源码/范围】普通运行写入也会到 JuiceFS/S3，不是只在 publish 时上传。普通 File 内存恢复仍私有映射 JuiceFS checkpoint；virtio-fs SharedFile 的 `memory.live` 保持本地 XFS。本轮没有重写内存机制、ROFS 或公共 SDK API。

## 5. 建议与改进项

postSDK02 已完成；FC 崩溃时观察到旧 checkpoint 输入仍打开，gVisor 当时旧输入已读完，只证明其运行实例/引用保留，不外推后台读取尚未结束的边界（该边界另有旧版 held-reader 验收）。组合源码 fdb145c 已推 fork，与远端 qa02 的 11 文件 SHA 完全相同。随后使用相同代码、相同内存模式，只切换 FC 私有盘后端，交替测量本地运行与 JuiceFS 运行：同时计普通写入、小块同步写、checkpoint 停顿/完成、恢复首读/完整验证及 S3 字节，不能只选元数据克隆耗时。

gVisor 的 JuiceFS 原生克隆仍需要独立接口/完整 bundle 适配及 SDK 验收；远端只读基线加本地差异层仍未实现。内存保存优化应另做一致捕获与远端提交分相对照，远端可靠提交前不能发布成功。保留内部删除屏障、多 collector、后端真实容量准入、旧 Pod 状态清理后的孤儿归属回收和真实故障域等生产剩余；不切换默认后端。

## 6. 可复现步骤

固定组件和镜像身份，不直接在旧环境重放。以下 TASK / ROUND 必须是调用者独占任务；任务特定脚本中的身份/目录要先按新现场改写并校验。

```sh
python3 "$TASK/cluster/namespace-lab07.py" run --task "$TASK" -- \
  kubectl -n akernel get pods -o wide
cat "$ROUND/tap-checksum-fix/native-rwfs-rejoin-sdk02/terminal.json"
cat "$ROUND/tap-checksum-fix/native-rwfs-rejoin-force02/terminal.json"
cat "$ROUND/tap-checksum-fix/native-rwfs-rejoin-directio02/terminal.json"
python3 "$ROUND/tap-checksum-fix/collect-native-rwfs-rejoin-reports.py" \
  --round-dir "$ROUND" > "$ROUND/native-rwfs-rejoin-public-reports.json"
```

实际执行脚本在 `tools/pr119-pod-20261024/candidates/native-rwfs-rejoin/`。`run-full-sdk02.py` 内有严格依赖、原覆盖恢复、镜像/ELF/就绪门和 SDK/状态/跨节点顺序；`run-native-rwfs-rejoin-postsdk02.py` 依赖整轮成功才执行后续压力与两类运行时重启。已有驱动未结束时只能读取状态，不重复运行或覆盖原输出。

## 7. 现场清理披露

仅滚动本任务五个业务 Pod，包含任务 Redis；没有修改旧环境、共享服务、宿主模块/sysctl、调度语义或资源隔离。SDK、直接 I/O 与两运行时进程重启批次均成功并正常删除其资源；最终 Environment 与进程盘点另附回执，不因驱动返回就推断所有历史失败目录均已回收。

临时 bootstrap 覆盖已恢复，实际制品来自固定 image02。保留失败脚本和私有原始证据；初始 Pod 名变化导致状态清理后遗留的私有盘不人工批量清扫，待明确归属回收契约。未将本轮候选混入已发布的 e3f402c / 父仓 97e5d13，尚未完成后端交替性能或默认产品晋升。

最终只读盘点 rc=0：Environment=0，两端运行时进程=0，五个业务 Pod 均为 image02、实际 sandboxd debbf268…，两节点可路由/可调度。共享根两端均看到同一份初始失败遗留盘，未人工删除。原 bootstrap SHA 恢复、临时覆盖不存在；宿主空闲 733385678848 字节（约 683.0 GiB）。最终回执为 `native-rwfs-rejoin-final-state01.json`，没有读取或导出文件内容。
