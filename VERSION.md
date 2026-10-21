# CrossNode 源码交付版本台账

日期：2026-10-21。本文件是本次脱敏 GitHub 交付的版本事实来源。源码提交、历史实测二进制和新构建产物是不同身份，不能混记。

## 可获取的源码

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

### 2026-10-21：文档统一中文

交付入口、架构、部署、复现、验收边界、后续工作、版本台账，以及 ADX/公共 SDK 新增说明统一使用中文。命令、配置字段、接口及历史测试/性能数据保持原样。更新文档提交对应的组件指针，不改运行时，不编译测试，不改共享服务。

### 2026-10-21：已验收源码发布

将 ADX、公共 SDK、sandboxd 和 gVisor 已验收源码发布到独立 GitHub 分支，补齐已有 Firecracker 发布对应源码、脱敏配置、部署辅助脚本、诊断探针、门禁汇总和六组原始耗时。未验收候选保留在原工作区。新父仓历史不包含内部父仓历史或私有证据，未生产部署或修改共享服务。

