# CrossNode 源码交付版本台账

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

