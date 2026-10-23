# PR #119 固定组合部署与 SDK 门禁进度

日期：2026-10-23。

## 开发内容

按当前计划，先完成 PR #119 的完整公共 SDK 验收，再推进 JuiceFS 原生克隆与“远端只读基线＋本地差异层”对照。继续使用 BareMetal 的本任务独立 Pod 集群，编译测试全部远端执行，不修改共享服务。

本轮发现上游 head 已变为 `365f797`，实际 ADX 包升至 `6fb53d7`，原生 SDK 升至 `0.1.0rc3`。因此重新固定源码、制品和 SDK，而不是把旧组合的成功结果套给新版。

## 修改内容

- 远端 `Q/source/AKernel` 固定 `365f7971f895f2b94cf390eefaab436600f005f0`；sandboxd 源码固定 `d5acc3b`，实际 ADX/Execd 包固定 `6fb53d7`。源码 gitlink `52bfc09` 不代表镜像中的平台版本。
- 新建本轮镜像、SDK venv、配置、认证和输出目录；本轮基础部署已完成。普通目录 filestore 保持在节点本地 XFS，新 sandboxd cgroup 根为 `/akernel-pr119-followup-20261023`。
- 获批后另存修正版 `Q/deploy-core-fixed.py`：修复字符串替换错误，仅按身份条件处理本任务未消费的空 Secret，远端语法检查通过后完成部署。原失败脚本保留。
- 获批后修正独立存储配置转换：使用 YAML 解析器，从原配置生成新的 `Q/storage/juicefs-values.yaml`；缓存 4096 MiB、`writeback=false`。没有启动存储服务或块设备。
- 新增远端 `tests/run-official-sdk.sh`，将官方 integration/standalone 与自有 checkpoint 探针分开记账；新增只读服务诊断和创建过程采集。
- `observe-create-internal.py` 的 `runsc list -q` 参数错误已披露，已请求改为当前二进制支持的 `-quiet`；本文截止尚未修正，不将缺失采集算作运行时证据。
- 本地新增中文检查文档及脱敏 JSON，更新 `VERSION.md`。没有修改根目录三个运行时 submodule 指针，没有将自有未推送缓存保护提交 `787131c` 混入新 PR 构建。

`N`：`/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp`。
`Q`：`N/round-365f797-20261023.clPWh2h0`。

## 测试结果

| 项目 | 结果及边界 |
|---|---|
| 远端镜像构建与制品身份 | 通过，OCI SHA-256 `a1fa04515efd03b46dfcd775d532b0fac5459b0552f1ac619bc660aa90a8daef` |
| 自有本地 XFS checkpoint/reload | 两种运行时共 12 次通过，含各 5 轮连续回滚、各 1 轮 512 MiB 完整状态校验；成功探针沙箱已删除 |
| 非法参数 | 每种运行时 8 项通过 |
| 辅助/契约测试 | 私有工具环境 106 个通过；不是运行时全仓测试 |
| 官方完整 SDK 套件 | 未通过；runsc integration 两处创建报 Execd 就绪超时，后续 standalone 和 Firecracker 官方套件未运行 |
| 创建失败定位 | 相同成功探针资源、开关 failover 均不能消除超时；观察到 gVisor 沙箱 running，内部就绪状态尚缺 |
| JuiceFS 新配置 | 已生成、未部署；本轮跨节点及故障矩阵未开始 |
| 新旧性能对照 / 两条存储路线 | 未开始，没有可归因的优化收益结论 |

基础 5 样本 P50：gVisor checkpoint 请求至完成 77 ms、SDK reload 226.480 ms；Firecracker 分别 2448 ms、2696.639 ms。操作使用本地 XFS、1 vCPU/2 GiB、1 GiB 私有存储，未额外填充内存。不是 guest 停顿，也不是跨节点恢复时间，不与旧数据直接计算性能提升。

## 可复现步骤

详细命令、样本口径、固定摘要、失败路径与清理边界见：

- `Docs/checks/20261023T-pr119-365f797-sdk-local-gate-readiness.md`
- `Docs/checks/evidence/pr119-365f797-20261023/sdk-local-and-readiness.json`
- 当前执行计划：`Docs/plans/20261023T-pr119-sdk-juicefs-clone-local-delta-next-phase-plan.md`

官方套件须在 `namespace-lab07.py run --task "$N"` 内执行，使用本轮 SDK 和独立认证。重跑必须另开输出目录，保留失败记录；不得直接执行准备中的存储 runner 来跳过完整 SDK 门禁。

当前优先事项是定位并关闭 gVisor 就绪超时，再补完整 SDK、JuiceFS 跨节点及生命周期验收。本轮没有达到新的完整验收里程碑，故没有新增“完成阶段”总结或提交推送未验收脚本。
