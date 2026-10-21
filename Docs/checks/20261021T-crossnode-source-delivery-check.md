# CrossNode 已验收源码交付检查（2026-10-21）

## 1. 问题

检查并整理已经验收的 CrossNode 集成与性能优化代码，分别提交推送，固定父仓版本，补齐脱敏 JuiceFS 配置、验收脚本与性能数据；未验收改动不能混入。编译测试仅在远端独立环境执行，不修改共享服务。

## 2. 方法

【源码】从已经验收的冻结源码分别对齐 ADX、sandboxd、gVisor 和公共 SDK 的真正基线；在独立交付 worktree 建提交，不重置原开发现场。ADX 的 checkpoint/shared_fs、Coordinator checkpoint_readers/shared_volumes 和 sandboxd durable operation 链路按各自提交保留；gVisor 的 runsc/container/retirement.go 与 pkg/sentry/kernel/kernel_restore.go 保留运行时退出确认和后台恢复等待机制。排除未验收 Coordinator shutdown 候选与三个无关 AFS 修改。

【实测】远端新任务目录独立编译、测试；仅复用只读工具/下载缓存，不部署新服务或重跑历史完整 SDK 实验。明确区分本轮源码门禁和历史端到端/性能验收。脱敏交付另建父仓历史，不镜像原父仓。

## 3. 数据

| 范围 | 本轮实际结果 |
|---|---|
| ADX | 7组件单元234通过、1忽略；5组集成45通过；fmt、针对7组件的严格 clippy、文档检查通过；Coordinator/API release 构建通过 |
| 原生 Environment SDK | 306通过、零跳过 |
| 公共 AKernel SDK | 全部 unit 文件305通过、共享卷独立6通过，零跳过 |
| 部署及诊断辅助脚本 | 56及19通过，5个 CLI help 通过 |
| sandboxd | fmt/vet通过；默认全仓906个顶层测试通过、5个特权集成跳过、零失败；server/FC/runsc 选定 race 各81/35/12通过；release 等价构建通过 |
| gVisor | retirement/serialization 普通与 race 每轮14个顶层测试通过；后台恢复等待普通与 race 每轮3通过；optimized runsc 构建通过 |
| ADX 严格全工作区 clippy | 未通过：可选 AFS 组件缺少 infiniband/verbs.h；没有为通过门禁修改共享系统依赖 |

完整提交与新旧二进制摘要见 VERSION.md 和 evidence/delivery-gates.json。历史六组新旧版本交替对照为同一物理机、两个隔离逻辑节点：Firecracker 从公共 SDK create 开始到恢复业务首次就绪的中位数4.187秒→2.349秒，配对几何均值耗时比0.5600；gVisor 3.199秒→3.141秒，但95%区间0.6635–1.3051跨越无变化，不能宣称收益或零退化。本轮只重算公开样本的点估计，没有新增性能采样，也没有重算登记的 bootstrap 随机流。

## 4. 结论

【源码】已验收实现已整理为独立、可获取的 GitHub 提交，五个组件由父仓精确固定。公共 SDK 与原生 SDK 都需要从固定源码安装。

【实测】本轮相关源码门禁通过，例外和跳过已逐项披露；历史 Firecracker 优化收益成立，gVisor 性能仍不确定。

【未完成】全新主机的完整公共 SDK/读者保护故障矩阵尚未重新验收；现有 native SDK 诊断脚本不等于完整产品验收。未部署、未发布运行时 bundle、未证明物理跨主机迁移或生产可用。不能宣称已经全面超过 E2B/AgentEnv/CubeSandbox。

## 5. 建议与改进项

- 完成当前固定版本的独立部署包和全新环境 SDK/读者退出确认矩阵；不复用历史私有身份记录冒充新验收。
- 保持自动 GC 关闭，直到读者预留、崩溃重启与执行退出确认的完整删除链在新环境过门禁。
- 再安排 gVisor 变慢的进程级 CPU/读 I/O 归因、冷 S3 读取量和真实跨主机恢复；不要把性能不确定改写为没有退化。
- 可选 AFS 的全工作区 lint 在有 RDMA 开发依赖的专用环境单独补齐；保留当前阻塞状态。

## 6. 可复现步骤

```bash
git clone --recurse-submodules git@github.com:hky1999/AKernel_CR.git
cd AKernel_CR
cat VERSION.md
cat Docs/reproduction.md
# 以下命令仅在远端独立环境运行
python3 tools/performance/recompute.py evidence/performance-six-pairs.json
# 更精确的组件命令见 Docs/reproduction-adx-sdk.md、Docs/reproduction-runtime.md
```

JuiceFS 的独立部署步骤见 Docs/juicefs-lab-runbook.md；生成私有配置、凭据和 TLS 材料，不从历史现场复制。configs/ 下的存储配置是必须合并验证的片段，不是可直接启动整个集群的配置。

## 7. 现场清理披露

原始父仓、原组件分支及全部既有脏文件保留。只对新建交付 worktree 提交推送；未验收候选留在原开发现场。远端构建缓存、失败尝试和二进制留在独占任务目录，不入 Git；没有启动 SDK/VM 集成实验或修改共享服务。曾因自有测试挂起，在固定 PID/启动代次/ELF/cwd 后只终止本任务 server.test；没有按进程名杀进程或停止其他任务。短 /tmp 映射只在私有 mount namespace 内存在，宿主挂载未改。长路径、依赖缺失等失败尝试保留并在脱敏门禁汇总披露。

