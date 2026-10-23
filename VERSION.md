# CrossNode 源码交付版本台账

## 2026-10-24 后续：FC 异步盘一致性修复已完成源码和真实 SDK 验收

sandboxd e3f402c0a18be3ff0b7d90674daae9459464772a（父 10312f2），分支 codex/pr119-fc-drain-order-20261024，已普通 push 并核对远端。三文件将盘复制放到 VMM 保存后、盘失败时失效已消耗的内存基线并更新计时/合同；源码与远端已测文件 SHA 一致，实际 ELF c85d58b2efe8c141394877cc73cdb33cd796d7760770a31c808fbd6c22fb5dce 为提交整理前构建。没有重新发布 runtime bundle。

组件旧红/三轮新绿、fmt/vet、全仓单测、FC 包 race、生产构建通过；当前制品官方 SDK 8+30 / 8+30 共 76，无跳过，两运行时各三轮完整状态及四条双向自动接管通过。真实 FC guest 4 KiB O_DIRECT 写/同步/直接读回、5 次保存/4 次恢复、跨节点双分支持续写和再次保存通过。实际内核完成时机未被人为卡住，与组件确定性屏障分开。

任务镜像 365f7971f895-io-cut01，config 6d3ec747…，实际 CRI ff06cd24…→叶 d5a31f72…→config 已三节点证明，两 Node ELF 均核对。仍用原 Full/Async/Writeback、本地 XFS RWFS/共享 JuiceFS checkpoint；配套 VMM/kernel/initrd/runsc/ADX 未改，实际 VMM manifest 是 b9a362d 的 fork-source-build。

Changelog：补当前源码清单、最终检查/进度/阶段总结、7 份小型回执与 10 个实际验收/构建脚本。组件产品源码从其提交获取，没有把嵌入整份源码的临时构建器复制到父仓。此前 9c74060c… 的十组/80 条性能和本地 XFS checkpoint 官方 SDK 结果移入 previous_pr119_candidate，不混成新制品已重测。当前一次三轮 Full 仍约 3 GiB PUT，无稳定性能收益结论。全部实例/快照删除、Environment=0；旧环境和共享服务未改。生产 HA、VMM I/O 错误传播、内部删除屏障/多 collector 和两条新后端仍有剩余；本次 GitHub check-runs 查询为 0，不冒充云端 CI 已通过。

## 2026-10-24：PR #119 完整 SDK、故障与十组性能复现交付

本节是独立 PR 候选输入，不替换下方 10 月 21 日五个子模块的源码组合。新清单 `delivery/pr119-20261024.json` 固定 AKernel 365f7971f895f2b94cf390eefaab436600f005f0、实际 ADX/Execd 6fb53d7331811535b6be5787ba026e03072f427b、sandboxd 10312f28c9b3286545eb2e97070cdd08fe994cee、公共/原生 SDK 0.2.0rc3 / 0.1.0rc3。10312f2 已正常 push 到 hky1999/sandboxd 的 codex/pr119-tap-reset-20261024，只有两文件 TAP 修复；与远端原验收源码相同，实际 ELF 仍为提交整理前构建的 9c74060c…，不是另一次重建已复测。

全部编译测试在 BareMetal 任务独占容器/Pod、独立 Kind 和真实 JuiceFS 中执行。官方 SDK 本地 XFS 与共享 profile 分别 76/76，无跳过；两运行时双向公共 SDK 自动接管，读者/控制角色崩溃、忙删除、复杂 RWFS、配额/超时/调用者死亡/S3 暂停/挂载替换/并发恢复均有分项证据。内部物理删除屏障与多 collector、旧 CI 特定对账竞争原样重放、PG/Redis 真崩溃持久化及生产 HA 未完成。

十组 AB/BA、40 实例各两轮，共 80 次完整状态保存/恢复通过，最终恢复新组。512 MiB 应用内存、64 MiB 根文件、2 GiB 配置、1 GiB 私有盘、JuiceFS 无压缩/4 GiB 缓存：旧→新首次 checkpoint P50 为 gVisor 1557→1498 ms、FC 8317→8305 ms；恢复后再次保存为 1599.5→1656.5 / 10970→11054 ms，没有稳定提速结论。FC 每次约 3 GiB PUT，恢复后再次保存另约 978 MiB GET，尚未逐对象归因。80 条白名单原始样本和分组/配对统计均已保存。

JuiceFS 同卷原生克隆与 FC 现有 Go 函数的 64 MiB 能力门分别约 10.4 / 4.6 ms 含同步、S3 GET/PUT 为零；分支、匿名 FD、mmap、截断/打洞通过。不是实际新后端 SDK 通过。产品、ELF、模板及当前默认布局没有因此变化。

Changelog：补中文复现、阶段总结、下一阶段计划、七节检查、白名单 JSON、38 个历史执行脚本和来源索引；内部文档链接在外发副本中省略，不含凭据/原始服务日志/二进制。历史脚本有固定任务身份，需在新独立环境另存适配，并非任意主机的一键启动器。尚未在另一台全新机器重放完整矩阵。旧环境、共享服务和其他未验收工作未改；父仓 gitlink 继续保留历史组合。

## 2026-10-22 本轮收尾：固定 PR #119 的核心 SDK 链路通过

- 组件二进制不变。两种运行时的本地 checkpoint/reload、真实 JuiceFS 同节点回滚、公共 SDK 跨逻辑节点故障接管通过；1 MiB 根 RWFS、512 MiB 完整内存、进程身份和打开文件一致。
- gVisor A→B 两轮、Firecracker B→A 一轮根 RWFS 用例通过；源节点重新加入后，目标内容和运行时身份未变，测试沙箱删除成功。此前另有 gVisor B→A、Firecracker A→B 内存用例通过。
- 首轮 gVisor EIO 受到 DNS 与故障节点共址污染：已仅将本任务 CoreDNS 迁至控制节点，相同方向重测通过。三次更早的创建就绪超时仍未归因，未用后续成功静默关闭。
- 实际 FD/maps：恢复后 Firecracker overlay.ext4 位于目标 XFS；memory 位于 JuiceFS，rw-p 私有写时复制映射。gVisor 根文件语义通过，但未采到恢复后的 filestore FD，实际介质路径不能只靠配置推断。
- 最终 etcd/API 健康、三个节点和任务 Pod Ready，现有权威目录没有 Environment 记录。rook-ceph 为 Ready/HEALTH_WARN，单副本及认证兼容告警不构成生产验收。宿主可用约 789 GiB。
- 临时 inotify=1024 未持久化；独立集群仍保留，退役且确认全局依赖后再恢复原值 128。没有重启其他使用者的共享服务。

### Changelog（本轮）

新增真实存储、DNS 故障域、公共 SDK 故障接管及只读运行时观察工具，补根 RWFS 覆盖和中文复现入口。全量并发、超时、上传失败、断连、目标进程重启及 GC 门禁未全部执行；没有 guest 停顿/S3 字节/SOTA 或生产高可用结论。只交付父仓工具与脱敏证据，不产生产品运行时新提交、不修改三个 gitlink。

复现入口：Docs/stages/20261022T-pr119-pod-baremetal-reproduction-stage-summary.md；检查与数据见同日 juicefs-sdk-failover 文档及 evidence/pr119-pod-20261022/juicefs-sdk-failover.json。

## 2026-10-22：Firecracker 公共 SDK 故障接管通过，独立集群 DNS 故障域已修正

- 固定组件及二进制不变。源执行节点 A 停止时，同一个公共 AKernel SDK 对象在节点 B 恢复了 Firecracker 的私有文件、512 MiB 完整内存、进程身份和已打开文件；源节点恢复健康，沙箱删除。单样本 checkpoint 5845 ms，故障开始到完整内存校验 48389.492106 ms，含故障处理和路由/SDK 重试，不是 VMM 核心耗时。
- gVisor 首次目标节点内存读取 EIO 与 JuiceFS 无法解析 PostgreSQL 同时出现；两个 CoreDNS 副本原来均位于故障节点 B。已仅修正本任务集群 DNS 的放置位置，并通过两端服务名解析检查，正在重测，未把原失败算作数据损坏证据。
- Firecracker 后 gVisor 创建超时、节点重启后通过的混合运行时现象仍待定位。私有 RWFS filestore 配置为本地 XFS，不代表已确认 Firecracker 所有运行态内存映射与 I/O 也都在本地。


## 2026-10-22：真实 JuiceFS 已接入独立 Pod 集群，跨节点验收进行中

- `fs.inotify.max_user_instances` 经用户批准临时从 128 调到 1024，未持久化，未重启共享服务；独立集群 etcd、API Server、三个 Kubernetes 节点健康检查通过。
- 固定 PR #119 的组件与二进制不变。本地磁盘 SDK 验收共 14 次 checkpoint/reload，包含两种运行时各五轮连续回滚、八项非法参数及 512 MiB 内存、进程身份和打开文件校验。
- 本任务 Rook/Ceph、PostgreSQL、JuiceFS 已实际启动。三个节点真实挂载 `fuse.juicefs`；4 KiB 文件经 `fsync` 后跨客户端摘要一致；PostgreSQL 三项持久化设置均为 `on`。ADX checkpoint 使用 `distributed_fs`，私有运行文件仍为节点本地 XFS。
- 共享存储配置下，gVisor 和 Firecracker 各通过一次基本 SDK 回滚和一次 512 MiB 内存完整校验；源节点离线后的跨节点恢复及剩余故障、并发、引用回收验收尚未据此关闭。
- 单 OSD、单副本和专属 40 GiB loop 镜像仅用于独立测试；Ceph 为 `HEALTH_WARN`，不代表生产高可用或原生裸盘性能。原始失败和凭据不入库，独立集群使用中，暂不恢复 inotify 原值。


## 2026-10-22：runsc/Firecracker 本地 SDK 基础回滚通过，JuiceFS 验收尚未完成

两种运行时各通过首轮、5 轮回滚及 8 个非法参数用例、完整 512 MiB 内存/PID/进程身份/打开文件内容校验；合计 14 次 checkpoint/reload，测试沙箱已删除。每实例 1 vCPU/2 GiB、本地 XFS；未额外填内存的 5 轮 checkpoint 请求总耗时 P50 为 runsc 64 ms、Firecracker 2590 ms，不是 guest 停顿或竞品对比。

JuiceFS 测试使用任务专属 40 GiB loop 和静态 PV，不使用其他宿主盘。首次存储 Helm 安装等待返回 1，失败记录保留；已补 Kind 私有 loop 设备节点与 6 个 CSI API 定义，不开启驱动、不加载新模块。OSD、RGW、真实挂载及源节点失联恢复还在验收，不能称完整通过。

运行时版本、镜像与 submodule 指针不变；新增的是隔离环境及验收脚本。inotify 1024 仍为临时设置。详细口径及完整交接矩阵未完成项见 `Docs/checks/20261022T-pr119-pod-resume-local-sdk-acceptance.md`。本轮 changelog 仅将已取得的动态结果归档，不把准备和失败写成通过。

## 2026-10-22：授权后的临时配额变更与集群恢复

仅临时将 `fs.inotify.max_user_instances` 从 128 改为 1024，其他两个 inotify 参数不变，未持久化或重启共享服务。原三个 Kind 容器已恢复，没有重建数据；API Server readyz 全项通过，etcd endpoint health/status 通过，三个节点 Ready。上述检查通过后才解除执行 DaemonSet 暂停，两个执行 Pod rollout 返回 0，五个 AKernel Pod Running。

正在继续运行时服务、TLS 和三条完整 SDK 验收，Pod Running 不等于验收完成。PR 源码、镜像、二进制和 submodule 指针未改变；先前 blocked 是获准恢复之前的历史记录。原值、变更、健康检查证据留在任务 `cluster/resume18/`，最终中文报告随后补齐。

## 2026-10-22 14:28：任务因宿主参数确认受阻，未完成验收

远端复查：`fs.inotify.max_user_instances=128`，宿主监听器探针成功，三个实验 Kind 容器仍 Exited。没有恢复集群，没有部署/SDK 验收后台任务；三条完整 checkpoint/reload 链路仍未完成。

SDK 工具与存储离线准备已在实验分支提交 `0cb6523`。新增宿主参数变更尚待确认，同一阻塞连续三轮后任务已登记 blocked，停止自动重启尝试；这不是已完成交付。组件版本和 gitlink 均未变化。

检查见 `Docs/checks/20261022T-pr119-pod-blocked-recheck.md`。本轮 changelog 仅记录当前阻塞与保留现场，不将重复状态确认包装为功能进展。

## 2026-10-22 补充准备：SDK 工具和 JuiceFS 离线配置

三个本任务 Kind 容器仍停止，inotify 上限仍为 128。未执行新增宿主参数变更，也未恢复集群。远端已准备 SDK 脚本与状态探针，CLI 帮助预检通过，但 Sandbox 请求数仍为 0。

新增 `tools/pr119-pod-20261022/{prepare_storage.py,storage_placement.py}`，复用并保存 `acceptance.py`、`guest_probe.go` 工具快照。固定 Rook chart `1.21.0`，SHA-256 `c070c7985deee72d7620e0377c07ce2afba28f566fbefe47bf934d00a5692cde`；远端离线渲染通过，Rook 59 对象、JuiceFS 9 对象。CSI 安装/资源生成和设备自动发现禁用，Ceph OSD 仍要求原始 Block PVC，不用普通目录替代。

未创建块设备或存储服务；三条 SDK 链路、跨节点一致性及性能均未验收。XFS 最近采样可用约 833 GiB，不清理旧环境。PR 业务源码、镜像和 submodule 指针没有变化。检查见 `Docs/checks/20261022T-pr119-pod-sdk-storage-preparation.md`；本轮 changelog 仅为上述准备工作，不代表产品集成完成。

## 2026-10-22 最新现场：inotify 配额阻塞，实验集群已停止并保留数据

执行 Pod 的早期 systemd 日志显示创建 inotify 监听器失败，退出 255。宿主 `fs.inotify.max_user_instances=128`；独立探针在仅打开 5 个文件、文件描述符上限 65535 时仍返回 `EMFILE`。本任务停止三个 Kind 节点容器后，宿主探针恢复成功，参数未改。当前集群已停止，下面 Ready/网络通过为停止前的历史实测，不是当前运行状态。

控制节点停止超时 30 秒后由 Podman SIGKILL，仅作用于本任务容器，数据未删除；恢复前必须先验 etcd/API Server 健康。新的宿主全局参数变更尚未执行：建议确认后临时将 `fs.inotify.max_user_instances=1024`，不持久化、不改其他参数、不重启共享服务。源码和镜像未改变，三条完整 SDK 验收仍未通过。

详见 `Docs/checks/20261022T-pr119-pod-inotify-startup-blocker.md`、`Docs/schedules/20261022T-pr119-pod-inotify-pause-progress.md`。本轮 changelog：定位并释放本任务造成的共享 root 监听器配额压力，保留停止状态等待宿主参数变更确认。

## 2026-10-22：独立 Pod 集群与网络验证完成，执行 Pod 启动阻塞

本节更新前次预检进度；不改变既有交付版本或三个 submodule 指针。

| 项目 | 本次实际状态 |
|---|---|
| 实验源码 | AKernel PR #119 固定 `6ea004125eb4365ba06ba3c7b21c4fd80e4cdaac`；sandboxd `d5acc3b5b673074e20fd8b7733d4035dbaeae1b0`；ADX `59fa7912f875832c8ab053148ae8fd17b7c25a23` |
| 客户端 | 公共 SDK `0.2.0rc3`、原生 SDK `0.1.0rc2`；已安装，尚无成功的 Sandbox 验收请求 |
| Kubernetes | Kind `v0.33.0`、Kubernetes `v1.35.8`，同一 BareMetal 上三个容器节点 Ready；未创建额外测试虚拟机 |
| 网络 | Calico `v3.32.2` 原生 nftables；跨节点允许/拒绝/撤销策略验证通过，探针已回收 |
| 镜像 | 官方两阶段 Dockerfile 已远端构建并导入；镜像配置 SHA-256 `d1316b767b570f12a2eb5156fd0af80dfbcd783a9ba853a308fe872a4394dee0` |
| 服务 | Coordinator、Ingress API、Redis 正常；两个执行 Pod 退出码 255，根因尚未确认，不能将 Helm deployed 视为产品验收通过 |
| 三条完整链路 | runsc、Firecracker、JuiceFS 双节点 checkpoint/reload 均尚未通过；JuiceFS 配套存储尚未部署，无本轮性能结果 |
| 共享环境边界 | 用户授权网络模块加载；不修改共享服务、全局 sysctl 或共享防火墙规则；清理仅限本任务失败集群，保留失败证据 |

详细检查见 `Docs/checks/20261022T-pr119-pod-cluster-network-and-node-startup.md`；进度见 `Docs/schedules/20261022T-pr119-pod-cluster-network-progress.md`。私有凭据、kubeconfig、原始 Helm 渲染件不入库。

### 本轮 changelog

- 2026-10-22：从“尚未部署”推进到独立 Kubernetes 和网络验证完成、控制面运行；执行 Pod 启动仍阻塞，SDK 验收未完成。

日期：2026-10-21。本文件是本次脱敏 GitHub 交付的版本事实来源。源码提交、历史实测二进制和新构建产物是不同身份，不能混记。

## 2026-10-22：PR #119 Pod 复现预检，尚未部署

本轮单独固定 PR #119 `6ea004125eb4365ba06ba3c7b21c4fd80e4cdaac`、sandboxd `d5acc3b5b673074e20fd8b7733d4035dbaeae1b0`、ADX `59fa7912f875832c8ab053148ae8fd17b7c25a23`，公共 SDK / 原生依赖 `0.2.0rc3` / `0.1.0rc2`。这组实验输入不同于下方 2026-10-21 已验收交付；没有替换父仓子模块指针，也没有修改产品源码。

远端私有 Podman 执行官方两阶段镜像构建、载荷检查及 OCI 导出，实际返回码均为 0。OCI 653,413,376 字节，SHA-256 `105c7c345407c853fe95f8d60f08540611276c405f5ac80a13bfa30644b76d87`。SDK 安装及 `pip check` 通过，但没有创建 Sandbox。新 Kubernetes 集群、Pod、SDK checkpoint/reload 和 JuiceFS 双节点验收均为 0，不计通过。

当前宿主缺少完整 ACL 链所需的活动网络模块。至少 `br_netfilter`、`ip_set`、`ip_set_hash_ip`、`xt_set`、`xt_conntrack` 及其依赖需要受控核对；模块加载会改变共享内核状态，尚未执行，等待操作边界确认。没有修改共享 sysctl/NAT、关闭网络策略或使用额外测试虚拟机。

新任务约 7.17 GiB，磁盘审计时 XFS 可用约 844.7 GiB，删除日志/缓存/构建数据 0 字节；仅回收一个本任务空 cgroup。详见 `Docs/checks/20261022T-pr119-pod-baremetal-preflight.md`、同目录命令附录、`Docs/schedules/20261022T-pr119-pod-preparation-progress.md` 和 `evidence/pr119-pod-20261022/preflight.json`。本分支是预检记录，不是已跑通部署或性能验收。

## 可获取的源码（2026-10-21 已验收交付）

| 组件 | GitHub 仓库及提交 | 交付分支 | 精确提交 |
|---|---|---|---|
| agent-dx | [hky1999/agent-dx](https://github.com/hky1999/agent-dx/commit/aac2b487c829aaf7d34b4bdce9a4a57c4c78841b) | `crossnode/accepted-20261021` | `aac2b487c829aaf7d34b4bdce9a4a57c4c78841b` |
| AKernel | [hky1999/AKernel](https://github.com/hky1999/AKernel/commit/645a07e061f649ecdbe3a86c686c445ea371f722) | `crossnode/accepted-20261021` | `645a07e061f649ecdbe3a86c686c445ea371f722` |
| sandboxd | [hky1999/sandboxd](https://github.com/hky1999/sandboxd/commit/3da34daf860de80a0adea64a457646cd208d4aa4) | `crossnode/accepted-20261021` | `3da34daf860de80a0adea64a457646cd208d4aa4` |
| gvisor-akernel-dev | [hky1999/gvisor](https://github.com/hky1999/gvisor/commit/93425aec2c93d07a38e021916dda8967743c46b0) | `crossnode/accepted-20261021` | `93425aec2c93d07a38e021916dda8967743c46b0` |
| firecracker | [hky1999/firecracker](https://github.com/hky1999/firecracker/commit/b9a362d1070ee17991e7388d3b53a9ccce25ecca) | `crossnode/runtime-baseline-20261021` | `b9a362d1070ee17991e7388d3b53a9ccce25ecca` |

由父仓子模块提交指针固定版本组合，而不是跟随分支最新提交。AKernel 内嵌的 ADX/sandboxd 指针也固定相应提交，未修改组织上游默认分支。

## 运行时与 SDK 来源

- 串行摘要校验对照：sandboxd `fc5eda63350f5bd106104176011370a14611d951`，分支 `crossnode/serial-baseline-20261021`。
- 并行摘要校验：sandboxd `3da34daf860de80a0adea64a457646cd208d4aa4`，保留完整 SHA-256 校验，独立组件并发上限为2。
- 历史实测 sandboxd ELF A：`9e555c43f0e2d8b33ead0ad8abd5cf5695cfb0c2145296e003f825f42a8f17ea`。
- 历史实测 sandboxd ELF B：`4806b036d23470c966265bce97986d36256cb223e0ab3792b35ac0173d1399af`。
- 新远端 sandboxd ELF：`6b2f5aca7e5ea42acdd10e798d7ffa999e791fcb807b543fa420a02d584d1f04`；仅构建，未运行、部署或重测性能。
- 新远端 runsc ELF：`a4c84b051a402ba07c169c71ac9784bfd2f54662d3c3271a5230d82fae9c8982`，与历史已验收 runsc 字节一致，本轮未部署。
- Firecracker 已有发布：`v1.16.1-akernel.3`，源码 `b9a362d1070ee17991e7388d3b53a9ccce25ecca`，本轮无新增 VMM 修改或构建。
- SDK 源码包版本仍为公共 `0.1.6rc9`、原生 `0.1.0rc1`，需从固定源码安装，不能用任意 PyPI 版本替代；未发布 SDK 包。
- 实验源码提交不等于正式运行时 bundle 已升级。新部署需重新生成匹配的 guest agent/initrd 与模板兼容摘要。

## 工具链与存储

- sandboxd：Go 1.27.2；gVisor：Go 1.26.3/Bazel 8.3.1；ADX：Rust/Cargo 1.95.0；SDK 门禁：Python 3.14.4。
- JuiceFS：`1.4.1+2026-07-30.0b90c7d`，关闭 writeback。PostgreSQL 保存元数据，Ceph RGW 提供 S3 数据服务，不是较早架构图中的 SeaweedFS 组合。
- 容器镜像及 JuiceFS 二进制摘要见 `delivery/manifest.json`；保留两个实测 RepoDigests，不猜测架构/索引角色。

## 验收与遗留项

上一轮所有构建测试均在远端独立任务环境执行。ADX 相关测试、两套 SDK、辅助脚本、sandboxd 默认全仓及选定 race、gVisor 针对性测试和构建通过。sandboxd 五个特权测试默认跳过，ADX 一个测试忽略。严格全工作区 all-features clippy 因可选 AFS 缺少 RDMA 头文件 `infiniband/verbs.h` 受阻，不计通过。

本次中文文档提交不改变产品源码，也不重新执行编译或测试。上述门禁仍对应 `evidence/delivery-gates.json` 中记录的原验收提交 ADX `d66150a`、公共 SDK `2163fc7`；最新提交只调整文档及关联子模块指针。

历史六组对照：Firecracker 从 SDK 发起恢复创建到首次业务就绪的中位数4.187秒→2.349秒，配对几何均值新/旧0.5600。gVisor 中位数3.199秒→3.141秒，但置信区间同时覆盖改善与变慢，不能证明收益。环境为同物理机两个逻辑节点，不能当作 guest 停顿或冷 S3 延迟。

全新主机的完整公共 SDK/读者退出故障矩阵仍待重放，公开探针与辅助脚本不直接关闭该门禁。见 `Docs/plans/20261021T-source-delivery-followups.md`。

## 变更记录

### 2026-10-22：新增 Pod 复现预检记录

独立分支 `repro/pr119-pod-baremetal-20261022` 整理当前 PR 的镜像、SDK、宿主与磁盘预检。所有编译检查在远端执行；未启动集群、未修改共享网络模块、未混入原父仓内部历史或未验收源码。动态验收待宿主前置条件对齐后继续。

### 2026-10-21：文档统一中文

交付入口、架构、部署、复现、验收边界、后续工作、版本台账，以及 ADX/公共 SDK 新增说明统一使用中文。命令、配置字段、接口及历史测试/性能数据保持原样。更新文档提交对应的组件指针，不改运行时，不编译测试，不改共享服务。

### 2026-10-21：已验收源码发布

将 ADX、公共 SDK、sandboxd 和 gVisor 已验收源码发布到独立 GitHub 分支，补齐已有 Firecracker 发布对应源码、脱敏配置、部署辅助脚本、诊断探针、门禁汇总和六组原始耗时。未验收候选保留在原工作区。新父仓历史不包含内部父仓历史或私有证据，未生产部署或修改共享服务。

