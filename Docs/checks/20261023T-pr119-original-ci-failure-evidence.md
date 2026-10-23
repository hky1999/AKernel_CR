# PR #119 原始 CI 失败日志核查

日期：2026-10-23。范围：只读取得 GitHub 原始日志，区分历史 CI 失败与本任务独立环境故障。

## 1. 问题

用户要求先查清 PR #119 的 CI 失败原因，再继续独立 BareMetal 完整 SDK 和跨节点验收。此前完整日志因访问失败未取得，不能用本任务部署辅助脚本错误或 Execd 就绪超时替代原 CI 归因。

## 2. 方法

使用已连接 GitHub 的只读工具，按精确提交查询工作流、任务和原始日志；没有触发工作流、修改 PR、发送评论或部署新版本。

- 原失败提交：`8cfb67ea9a6d1124905a4b94d87edeacc1850769`。
- [原工作流 39777006476](https://github.com/inclusionAI/AKernel/actions/runs/39777006476)，Standalone E2E job `119819024441`。
- 当前本任务固定原始 PR 提交：`365f7971f895f2b94cf390eefaab436600f005f0`。
- [对应工作流 39873571800](https://github.com/inclusionAI/AKernel/actions/runs/39873571800)，Standalone E2E job `120154066374`。

本轮 BareMetal 候选额外带有 sandboxd TAP 状态复位补丁，必须与上游原始提交的 CI 分开记账。

## 3. 数据

| 检查 | 原始日志事实 |
|---|---|
| 旧提交 CI 构建 | 镜像构建、启动及 SDK examples 均成功；不是镜像构建失败 |
| 旧提交 integration | `Ran 8 tests in 48.243s`，`OK` |
| 旧提交 standalone | 执行 30 用例，1 个 error；失败名为 `test_dynamic_block_and_clear_preserve_control_operations` |
| 失败所在步骤 | 用例退出 `with Sandbox(...)` 时执行 SDK `kill`，底层 Environment.delete 三次尝试均收到 HTTP 503：`environment authority reconciliation pending` |
| 同期平台日志 | 同一实例在网络策略更新后出现 `environment authority reconciliation incomplete` / `request conflicts with existing state`；随后节点对账返回 `identity or version conflict` |
| 另一个预期错误 | `test_reload_without_checkpoint_does_not_create_a_new_runtime` 的“没有恢复点”503 最后为 `ok`，不是本次 CI 失败用例 |
| 当前固定提交 CI | 工作流 completed/success；Standalone E2E 中同名 SDK integration/standalone 步骤 success |

日志位置按工具取得的原文计数：integration 总结约第 6931 行；失败用例输出约 6953 行；异常栈及 30 用例失败总结为 6996–7030 行；同一实例对账冲突为 9232–9233 行。只保留必要摘要，不将完整日志中的环境标识、临时访问数据和大体积构建输出搬入父仓。

## 4. 结论

【原始日志】旧 CI 的直接失败点已经查清：动态网络策略用例清理沙箱时，ADX 拒绝处于权威对账未完成状态的删除请求，SDK 三次短重试耗尽。这是清理操作返回错误，不是用例创建时 Execd 无法就绪。

【原始日志】同期存在实例/节点权威版本冲突；足以把后续根因调查定位到 ADX 对账与生命周期操作的交错。仅凭日志不能进一步宣称是哪一处源码提交完全消除该竞争。

【版本事实】当前固定 `365f797` 的上游 CI 已成功；其中的 ADX 发布制品与旧失败轮不同。当前 BareMetal 本地完整 SDK 也已通过，但带额外 TAP 修复，且 JuiceFS 完整链路仍在执行。上述结果不抹去旧失败，也不证明相同交错永远不会再出现。

【区别】本任务中 FC→gVisor 复用持久 TAP 导致的校验和状态问题具有独立实测证据。旧 CI 验证的是 gVisor-only 载荷，不能将 FC 复用链解释强加给这份日志。

## 5. 建议与改进项

1. 后续若专门关闭旧 ADX 竞争问题，应固定旧/新实际发布包，以网络策略更新与周期对账交错构造确定性回归，再验证删除，不以扩大重试次数掩盖。
2. 后续性能表继续固定实际平台、Execd、SDK 与运行时载荷，不能只按 AKernel PR head 归因。
3. 当前不为取得更好结果切换浮动上游，完成既定候选的 JuiceFS SDK、双向故障接管和引用生命周期门。

## 6. 可复现步骤

已登录并有相同权限时，可用 GitHub API 或 CLI 只读取得同一日志；命令不触发构建或测试：

```bash
gh api 'repos/inclusionAI/AKernel/actions/runs?event=pull_request&head_sha=8cfb67ea9a6d1124905a4b94d87edeacc1850769'
gh api repos/inclusionAI/AKernel/actions/runs/39777006476/jobs
gh run view 39777006476 --repo inclusionAI/AKernel --job 119819024441 --log
gh api 'repos/inclusionAI/AKernel/actions/runs?event=pull_request&head_sha=365f7971f895f2b94cf390eefaab436600f005f0'
gh api repos/inclusionAI/AKernel/actions/runs/39873571800/jobs
```

本轮实际使用 GitHub 连接器相应的 `fetch_commit_workflow_runs`、`fetch_workflow_run_jobs`、`fetch_workflow_job_logs`，没有在本地编译或运行测试。

## 7. 现场清理披露

只读网络访问及新增本篇文档；没有修改 GitHub 状态、任务集群、共享服务、运行时二进制或父仓组件指针。完整原日志未公开入库。
