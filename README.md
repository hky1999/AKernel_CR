# CrossNode checkpoint/restore：已验收源码交付

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

