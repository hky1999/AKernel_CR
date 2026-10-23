# PR #119 TAP 修复组合的 JuiceFS SDK 与跨节点验收

日期：2026-10-23。状态：官方完整 SDK、附加状态负载及两种运行时双向故障接管主链路通过；完整生命周期故障矩阵尚未完成。阶段结论见 [阶段总结](../stages/20261023T-pr119-tapfix-juicefs-bidirectional-sdk-stage-summary.md)。

## 1. 问题

按用户批准补齐“ADX 新节点会话已注册、可路由且资源可调度”的等待条件，在 BareMetal 独立环境继续 gVisor、Firecracker 完整 SDK 和 JuiceFS 跨节点 checkpoint/reload。编译测试全部远端执行，不修改旧环境和共享服务。完整验收通过后再开展 JuiceFS 原生克隆与远端只读基线加本地差异层的对照。

## 2. 方法

【实测】沿用前轮已通过本地 SDK 的固定组合：AKernel `365f797`、实际 ADX/Execd 发布包 `6fb53d7`、sandboxd `d5acc3b` 加未提交的 TAP 状态复位补丁，公共/原生 SDK `0.2.0rc3 / 0.1.0rc3`。完整摘要和本地 76 用例结果见 [前轮检查](20261023T-pr119-tap-offload-local-sdk-acceptance.md)。本轮不追随浮动 PR head。

本任务远端路径：

```bash
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
Q="$N/round-365f797-20261023.clPWh2h0"
D="$Q/tap-checksum-fix"
S="$D/storage"
```

使用任务私有 Kubernetes 集群的两个执行节点及一个控制节点。所有 kubectl/Podman 操作经 `N/cluster/namespace-lab07.py` 进入已有私有命名空间。复用此前 Rook、静态 PV、真实 udev 描述复制和 JuiceFS 安装工具，另存本轮执行器，保留旧脚本和失败记录。

真实就绪条件沿用 `D/wait-adx-ready01.py`：两个新会话区别于部署前会话，均可路由、可调度、容量满足 SDK 资源要求；地址对应当前 Pod，实际镜像和 sandboxd 摘要正确，连续三个稳定样本，且没有其他活跃 Environment。Pod Ready 和 systemd active 只作为其中的检查项。

## 3. 数据与证据链

| 项目 | 本轮实际状态与边界 |
|---|---|
| 配置预检 | `S/preflight01/terminal.json` 返回 0；保留 TAP 修复镜像、virtio-fs、独立 cgroup 和 distributed_fs，禁用物理磁盘自动发现 |
| 存储规格 | 一个 40 GiB 任务文件，经 loop 设备提供测试原始块卷；一个 MON、一个 OSD、一个数据副本；不是生产高可用或原生裸盘性能环境 |
| 持久化及缓存 | 已实际核对 PostgreSQL 的 fsync、synchronous_commit、full_page_writes 全为 on；JuiceFS 1.4.1，1024 KiB 块、trash=0；配置为 `writeback=false`、4096 MiB 节点磁盘缓存 |
| 运行数据布局 | checkpoint 通过 JuiceFS；FC 恢复后 overlay.ext4 的实际 FD 在目标 filestore/XFS。额外 gVisor 介质检查也确认根 RWFS 是 XFS 上匿名 filestore，应用内存另为 tmpfs memfd，详见本篇后续链接 |
| 首次驱动失败 | `S/run01/terminal.json` 为 1，停在预检；尚未分配块设备或启动存储。错误地对外层 Python 包装进程核验私有网络命名空间 |
| 身份检查修正 | `prepare-and-accept02.py::snapshot_forward` 同时验证原包装进程 PID/启动代次、直接 kubectl 子进程、任务网络命名空间和命令摘要；发信号前再次核对父子身份，只结束该转发 |
| 标准设备路径遗漏 | 初次 OSD 准备日志指出 `/dev/loop150` 不存在；任务别名对应的块设备、后端文件和容量均正确。只在本任务 Kind 控制节点补标准设备入口 |
| OSD 重试 | 保存原 Job 定义和日志，按 UID 前置条件删除已结束 Job，再以原规格重试。后续日志确认配置了一个 raw OSD；此结果仍不代表 JuiceFS/SDK 已通过 |
| 控制器与测试池修正 | 核对 Helm release 后只重启本任务 Rook operator 促使重新对账；核对 Ceph FSID 后，将本任务 `.rgw.root` 的 pg_num 从 1 增至控制器要求的 8，未降低副本/持久化要求 |
| 安装结果 | 初次 Helm 等待 12 分钟超时、返回 1，原件保留；复用既有盘和 PostgreSQL Secret 的 `install02` 返回 0，不重建数据 |
| 客户端等待门 | `run03` 在最后一个客户端 Ready 前拒绝接入；`run04` 误用了不支持 OnDelete DaemonSet 的 rollout status，返回 1；`run05` 改为等待客户端 Pod Ready，再独立检查数量、挂载和读写 |
| 实际挂载和接入 | `verify02/receipt.json` 确认三客户端均为 JuiceFS、4 KiB 跨客户端同步写 SHA-256 一致，已接入 ADX；两执行 Pod 实际 filestore 为 XFS，checkpoint 挂载为 JuiceFS |
| 真实 ADX 就绪 | `run05` 的新会话、可路由、资源可调度、实际载荷和三个稳定样本检查返回 0 |
| 官方完整 SDK | 任务私有直连入口上的 `sdk-full02` 返回 0：Firecracker integration 8 / standalone 30，gVisor integration 8 / standalone 30，全通过、无跳过；此前 sdk-full01 也通过，不能把重复套件计作更多性能样本 |
| 连续回滚、完整内存 | `run06` 返回 0：两运行时各五轮回滚、八项参数拒绝、一次 512 MiB 完整内存/PID/打开文件校验，共 12 次 checkpoint/reload，四组沙箱均删除成功 |
| 双向跨节点 | `cross-node05` 返回 0：两运行时分别 B→A、A→B，均验证源离线、1 MiB 根 RWFS、512 MiB 内存、目标持续写入、源重新加入不改变目标以及最终删除 |

保留失败：`run05` 在附加 FC 连续回滚第四轮因 kubectl 转发退出而失败。该轮 FC 只有前三轮通过，没有补写成五轮成功；核对清理保留沙箱、未重放未知操作后，使用新编号和私有稳定入口的 `run06` / `sdk-full02` 完整重测通过。跨节点驱动严格等待新状态门完成，详见 [转发中断检查](20261023T-pr119-sdk-port-forward-interruption.md)。

本轮脱敏证据为 [同节点](evidence/pr119-juicefs-tapfix-20261023/same-node.json)、[跨节点](evidence/pr119-juicefs-tapfix-20261023/cross-node.json)。每方向一个跨节点功能样本，未做冷缓存控制、十次交替或百次尾延迟统计。FC B→A 在 SDK 读计时前已经发生约 1133.90 MiB GET，92 ms 的末段读请求不能当作总恢复时间；四例故障操作至完整校验为 33.620–36.455 s，含受控停止、撤路由/检测和完整验证，也不是运行时纯恢复耗时。

原始设备信息、日志和失败文件位于远端 `S/device-repair01/`。原始渲染、数据库密码和 SDK 凭据留在任务私有目录，不进入父仓证据。

## 4. 结论

【实测】本轮配置合并、任务块存储分配和私有设备路径修正已有证据。首个驱动在预检退出的原因是验收辅助脚本的进程身份判断错误，不是产品存储故障。Ceph 准备任务曾返回成功但实际配置零个 OSD，因此后续门禁必须核对实际 OSD 和挂载，不能只依赖进程退出码。

【实测】真实存储、ADX 可调度门、当前 JuiceFS 配置下官方完整 SDK 76 用例、附加 12 次 checkpoint/reload 及四条双向故障接管均通过。没有为了验收把运行态目录改放 JuiceFS；FC 的实际本地盘/远端内存 FD 已核实。额外 [gVisor 介质检查](20261023T-pr119-gvisor-restored-rwfs-backing-media.md) 确认恢复后的匿名 filestore 属于 XFS，补齐原路径过滤缺口，诊断样本不并入性能统计。

【未完成】确定性后台读者/删除竞争、ADX 进程重启、超时取消、存储故障和复杂 RWFS 等完整生命周期矩阵、同条件性能对照及两条新存储路线仍未完成。原 CI 日志的独立结论见 [CI 核查](20261023T-pr119-original-ci-failure-evidence.md)，不能将它与 TAP 故障合并归因。

## 5. 建议与改进项

1. 安装器在创建专属设备别名之外，同时核对实际消费者需要的标准设备路径；仅处理任务设备，不枚举或创建其他宿主设备。
2. 以实际 OSD 数、对象桶就绪、三客户端真实 `fuse.juicefs`、跨客户端同步写和 PostgreSQL 持久化开关作为接入前提。
3. 完整 SDK 成功后，分别取得两种运行时的两个迁移方向，检验 512 MiB 确定性内存、1 MiB 根 RWFS 回滚、目标继续写入和源节点重新加入。
4. 引用保护、后台读者与删除竞争等故障门保留为独立待办；基础 SDK 成功不能替代这些门禁。

## 6. 可复现步骤

以下为本轮**已有现场**的入口，不可直接在新任务套用硬编码节点身份或对已经创建的块设备重复分配。

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
Q="$N/round-365f797-20261023.clPWh2h0"
S="$Q/tap-checksum-fix/storage"
cat "$S/run01/terminal.json"         # 已保存的预检失败
cat "$S/run06/terminal.json"
cat "$S/sdk-full02/terminal.json"
cat "$S/cross-node05/terminal.json"
python3 "$N/cluster/namespace-lab07.py" run --task "$N" -- \
  kubectl -n akernel-pr119-storage get pods,cephclusters,cephobjectstores,pvc
```

本轮原始顺序记录在 `S/prepare-and-accept02.py`，失败后另存 `03/04/05`，复用已有存储并保留各轮结果。最终 `prepare-and-accept06.py` 复用真实挂载与已接入配置、任务私有直连入口，经过真实 ADX 就绪再运行官方完整 SDK 和状态负载。`S/cross-node05.py` 仅在 run06 全通过后启动，调用 `sdk-failover03.py`；后者复用原故障测试，增加只读目标 FD/maps 与网关计数，原功能判断没有放宽。较早已暂存的 cross-node01–04 未启动。

## 7. 现场清理披露

新增一份 40 GiB 任务后端文件、专属 loop、静态 PV 和本任务存储资源。只在任务 Kind 私有 `/dev` 创建对应设备入口，重启了经 Helm 身份核验的本任务 Rook operator，调整了经 FSID 核验的本任务测试池 PG 数。首次控制器归属检查使用了错误 release 名，拒绝执行，核对安装器和实际元数据后才继续。未格式化其他物理盘，未修改宿主 udev、加载新内核模块、修改全局参数或重启共享服务。已有 inotify 临时值未改。

失败脚本、已结束准备 Job 的定义/日志和配置均保留；设备、存储及任务私有 NodePort/socket 代理仍用于后续验收，不提前删除。所有本轮成功沙箱及保留诊断沙箱已删除，最终权威 Environment 记录为 0，任务 API/节点/Pod 健康，XFS 可用 739762581504 字节（约 689 GiB）。旧已验收环境、其他运行时实验和父仓三个组件 gitlink 未改。产品补丁仍未提交或推送，不宣称已发布。
