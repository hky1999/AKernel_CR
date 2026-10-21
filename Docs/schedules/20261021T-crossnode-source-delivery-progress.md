# CrossNode source publication progress (2026-10-21)

## 开发内容

将此前已经验收但散落在工作树/冻结目录中的 ADX CrossNode 集成、共享卷链路、运行时读者退出确认与 Firecracker 完整摘要并行校验优化，整理成外部可获取的固定版本组合。不把“历史验收”当成“任意新构建已经部署通过”。

## 修改内容

- agent-dx: `d66150a0d37c1413f22499e81d95a88e297ead7a`，ADX control plane, native Environment SDK, persisted checkpoint reader and shared-volume lifecycle。
- AKernel: `2163fc77390c1ddc2aa66ac6a9d6f0d7a9bd1459`，Public AKernel SDK and isolated JuiceFS/ADX deployment helpers。
- sandboxd: `3da34daf860de80a0adea64a457646cd208d4aa4`，Runtime integration, durable operation identities, bounded integrity verification。
- gvisor-akernel-dev: `93425aec2c93d07a38e021916dda8967743c46b0`，Execution retirement proof and restore-worker synchronization。
- firecracker: `b9a362d1070ee17991e7388d3b53a9ccce25ecca`，Existing accepted VMM release baseline; no new VMM changes or build。
- sandboxd 串行校验对照单独保留 `fc5eda63350f5bd106104176011370a14611d951`，新版本仅将独立文件 SHA-256 校验并发限制为2，不跳过完整性。
- ADX 两处 LabelSelector 测试初始化器做等价 lint 清理；不改变产品逻辑。公共 SDK 公开受控共享卷能力，新增 JuiceFS 独立实验部署辅助脚本，并固定嵌套组件指针。
- 父仓新增配置片段、架构/复现/验收边界说明、诊断脚本、六组配对性能样本、脱敏门禁汇总及精确版本清单；内部父仓历史与私有运行产物不发布。
- 未验收 Coordinator shutdown 候选、无关 AFS 修改及他人的修改不进入交付。原工作区继续保留。

## 测试结果

仅远端独立环境执行。ADX 单元234通过/1忽略、集成45通过；原生 SDK306、公共 SDK305、共享卷6、部署 helper56、诊断 helper19全部通过。sandboxd 全仓906通过/5特权跳过/零失败，3组 race 通过；gVisor 两组针对性普通/race及构建通过。严格 ADX 全工作区 clippy 因可选 AFS RDMA 头文件缺失未通过，不能算全绿。新编译产物未部署，完整新环境端到端矩阵未重跑。

历史六组对照：Firecracker 公共 SDK 创建至首次业务就绪的配对几何均值耗时减少约44%，gVisor 收益不确定。原始耗时和二进制身份已公开；本轮只重算点估计。

## 可复现步骤

```bash
git clone --recurse-submodules git@github.com:hky1999/AKernel_CR.git
cd AKernel_CR
# 阅读后只在远端独立环境执行门禁/部署
cat Docs/reproduction.md
cat Docs/juicefs-lab-runbook.md
python3 tools/performance/recompute.py evidence/performance-six-pairs.json
```

不能将诊断探针成功替代完整公共 SDK、读者崩溃重启和安全回收验收。失败尝试、环境边界和清理记录见同日检查文档。

