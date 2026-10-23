# CrossNode checkpoint/restore：已验收源码交付

**本轮后续修复已验收**：[sandboxd e3f402c](https://github.com/hky1999/sandboxd/commit/e3f402c0a18be3ff0b7d90674daae9459464772a) 修正异步磁盘完成与内存保存顺序，源码门、官方 SDK 76、双向接管、真实持续直接 I/O 均通过。[最新修复总结](Docs/stages/20261024T-pr119-fc-disk-cut-fix-stage-summary.md) 与独立清单固定当前 c85d58b2… 制品。此前十组性能仍属于 9c74060c…，分开记账；两条新 RWFS 后端尚未接入。

**2026-10-24 PR #119 后续复现**：先读 [本轮中文复现](Docs/reproduction-pr119-20261024.md)、[阶段总结](Docs/stages/20261024T-pr119-sdk-faults-performance-stage-summary.md) 和 [独立版本清单](delivery/pr119-20261024.json)。本轮完整 SDK、双向接管、列出的故障用例及十组 80 次状态回滚通过；没有稳定提速或生产高可用结论。新运行时存储路线尚未通过 SDK。

下面的五个子模块和 `delivery/manifest.json` 保留 10 月 21 日那套历史交付；PR #119 固定候选按新清单另取源码。不要只升级一个子模块后与其他旧组件混用。两份性能数据也属于不同组合，分别阅读。

本仓库管理 ADX / JuiceFS CrossNode 实验的脱敏交付清单、组件 Git submodule（子模块）、部署辅助脚本、验收探针和配对性能数据。

## 从这里开始

```bash
git clone --recurse-submodules git@github.com:hky1999/AKernel_CR.git
cd AKernel_CR
cat VERSION.md
cat Docs/reproduction.md
```

不要使用 `git submodule update --remote`：父仓的子模块提交指针已经固定交付版本。两套 SDK 都应从指定源码安装，不能仅安装当前 PyPI 包。详见 `Docs/reproduction.md`。

## 范围与边界

- ADX 负责 Environment 生命周期、快照引用、持久化的读者预留和共享卷挂载准入。
- JuiceFS 通过各节点独立挂载提供共同命名空间。JuiceFS 的文件元数据与 S3 对象数据，不等同于 ADX 使用的 Redis 控制状态。
- 应用共享卷与沙箱私有可写根文件系统是不同契约。恢复 checkpoint 不会回滚共享卷内容。
- 已验收性能实验中，Firecracker 的私有可写盘仍为本地 XFS 上的 ext4 镜像，checkpoint 工件发布到 JuiceFS；不是生产 OverlayBD 集成。
- 已验收环境是一台物理机上的两个隔离逻辑节点，不能据此宣称真实跨物理机迁移、存储高可用或生产尾延迟已经验收。
- Firecracker 在登记的恢复指标上有收益；gVisor 的收益仍不确定。原始样本见 `evidence/performance-six-pairs.json`。
- 未验收的 Coordinator 退出候选、无关 AFS 修改、私有配置、凭据、进程清单和内部历史文档，不进入本次交付。

这是已验收实验源码的整理交付，不代表生产发布或正式运行时版本升级已经完成。本轮真实门禁及未通过/无法执行的项目见 `evidence/delivery-gates.json`。

仓库说明文档默认使用中文；配置字段、接口名、命令、路径和必要的技术标识保持原样。

