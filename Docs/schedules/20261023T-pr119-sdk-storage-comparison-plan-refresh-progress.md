# PR #119 SDK 验收与私有可写层对照计划更新

日期：2026-10-23。状态：仅更新计划与执行入口，没有启动实现或验收。

## 开发内容

根据用户要求和侧边讨论的架构分析，调整下一阶段顺序：先完成 PR #119 固定版本的完整公共 SDK 验收，再比较 JuiceFS 卷内克隆与远端只读基线加本地差异层，最后按运行时选择产品后端。

旧计划面向历史同卷运行 filestore 方案；当前 PR 已采用本地运行、共享 checkpoint，不能继续把两种布局当作同一个开发基线。历史文档保留，不重写实验结论。

## 修改内容

- 新增 `Docs/plans/20261023T-pr119-sdk-juicefs-clone-local-delta-next-phase-plan.md`：阶段一验收矩阵、版本冻结、CI 与分相基线；阶段二克隆对照；阶段三 FC 块级后端和 gVisor 后台恢复/必要页面适配；阶段四选择、兼容和生产验收。
- 在 `Docs/plans/20261015T-adx-crossnode-shared-storage-next-phase-plan.md` 顶部增加历史定位及新入口，原正文保留。
- 更新 `AGENTS.md` 的当前执行计划链接，其余工作区规则不变。
- 更新 `VERSION.md` 的计划入口及 changelog；没有新组件提交、二进制、部署或验收状态变化。
- 创建私有语雀计划：ADX CrossNode 开发计划 PR119 完整 SDK 验收与私有可写层对照（内部文档；外部复现以本仓计划和证据为准），沿用 AKernel_Drafts，不修改原架构分析的内容或权限。
- 新增本进度记录。没有组件函数/API 变更，没有提交或推送。

## 测试结果

本轮没有运行编译、单测、格式化、race、SDK 或性能测试，没有操作远端服务。计划列出的未来验收不能计作通过。

计划中区分旧组合已通过的核心 SDK、新版未完成的组合验收、辅助测试和未来后端原型；未新增或挪用性能数字。原 CI 根因和独立部署 helper 阻塞仍按台账披露，未以计划更新宣称解决。

## 可复现步骤

查看仓库执行计划及已有状态：

```bash
cat Docs/plans/20261023T-pr119-sdk-juicefs-clone-local-delta-next-phase-plan.md
cat Docs/plans/20261015T-adx-crossnode-shared-storage-next-phase-plan.md
cat Docs/checks/20261023T-juicefs-rwfs-lazy-restore-sidebar-analysis.md
```

本轮只执行了旧计划与相关入口的读取、语雀计划创建和文档编辑。之后实现时必须先固定远端实际版本和任务身份，再按阶段执行；本文不提供未经实现的新 SDK 调用。

## 现场清理披露

没有创建进程、Pod、块设备或挂载，没有修改共享服务、宿主参数和已有实验。没有需要回收的运行资源。原文件、既有修改、失败证据和运行现场保留。
