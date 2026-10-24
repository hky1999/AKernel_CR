# PR119 资源归属崩溃恢复修复进度

## 开发内容

上一轮严格用例在后台页输入仍打开时杀 sandboxd，gVisor 完成后台恢复后原实例却退出。原日志显示 daemon 重启时落盘的使用 cgroup 数为 0，而物理分组存在；源码将这些分组当空闲资源清理，包含杀进程。cgroup 是 Linux 按实例组织进程并约束资源的内核分组，本次处理其归属与恢复，不重写内存或私有文件数据协议。

修复在独立 sandboxd 工作树 `codex-pr119-cgroup-durable-leases-20261024` 中，基线 21fb466。所有编译、格式化与测试在 BareMetal 本任务独立环境执行；本地只编辑/取回源码和记录证据，不改共享服务。

## 修改内容

组件变更共八个文件，已提交并推送个人fork：91dff2f686d4f3f18540d33c0851b127212d8567（父21fb466）：

- `pkg/cgroupmanager/cgroup.go`：`Allocate` 的缓存与新建路径统一调用 `activate`，在调用者可启动进程前同步提交归属；提交失败不返回资源名，并回收尚未使用的池容量。`store` 用 `storeMu` 串行快照捕获与写库，防旧定时写覆盖新分配。`recoverUsingIDs` 保留旧快照遗漏但仍被进程占用的分组；恢复后的修复集合在清理空闲组前提交。
- `pkg/cgroupmanager/ops.go`、`ops_v1.go`、`ops_v2.go`：增加占用状态查询。v1 读取递归进程列表，v2 严格读取内核 cgroup.events 的 populated 字段；不可读、缺字段或畸形值均停止恢复，不能默认为空。
- `pkg/cgroupmanager/ops_test.go`：更新测试替身接口，不放宽原断言。
- `leases_persistence_test.go`：成功前提交、阻塞提交、写失败容量恢复、旧异步快照覆盖新分配的确定性测试。
- `leases_recovery_test.go`：遗漏但仍有进程的分组保留、已记录归属保留/失效项过滤、未知占用拒绝，以及真实 v2 状态文件边界测试。
- `doc/checkpoint-restore.md`：同一变更明确 daemon 崩溃下资源归属的持久化与恢复契约，保留未知活跃孤儿对账要求。

父仓新增远端 old-red/candidate 质量门、只替换 sandboxd 的固定镜像生成/导入和 SDK 驱动；SDK 先固定原失败节点，再做对向及另两角色的真实输入崩溃。复用已经工作的 Snapshot/Environment、身份屏障、真实就绪门、官方 SDK 与状态/接管脚本，不增加 catalog 或公开 API。

## 测试结果

| 项目 | 状态与判定 |
|---|---|
| 原版确定性回归 | 原 21fb466 只加测试，四组均预期失败，go test rc=1；没有编译错误冒充旧红 |
| 候选 cgroup 包 | 三轮全包测试通过，包含恢复和提交边界 |
| 全仓门 | fmt、vet、make test 全部通过；相关 cgroup/sandbox/资源/runsc/FC/server race 通过 |
| 候选二进制 | 远端 release 构建通过，SHA-256 433574033952b1ad9106b125e085302b9c5268fea179609975de7d722c2f6c83 |
| 固定镜像导入 | image01 rc=0，三个 Kind CRI 均 0bde46ba…；其他 gVisor/ADX/FC/SDK 字节不变，不是正式 release |
| SDK/故障 | 已完成本任务滚动、真实就绪/15制品/Secret/诊断快照检查，四组严格输入崩溃全部通过；官方76项全部通过。两种运行时各三轮状态与各A→B/B→A接管均通过，整轮rc=0；后置FC/gVisor原进程/未保存状态及原失败快照恢复/SDK退休也全通过 |

八份远端格式化后的源码已按门禁 SHA 取回本地，未本地运行 gofmt/构建/测试。镜像为 `365f7971f895-cgroup-leases01`，只 COPY 同一被测 sandboxd；CRI 0bde46ba… → leaf 2e6fba41… → config 8990eb27…，OCI 942070272 字节、SHA 7c001a2e…。源码、二进制和部署分别记账，不把构建通过当作动态修复完成。

### 可复现步骤

仅在远端独立任务观察现有输出，禁止覆盖或盲目重跑：

```sh
cat "$ROUND/tap-checksum-fix/cgroup-durable-leases-qa01/terminal.json"
cat "$ROUND/tap-checksum-fix/cgroup-durable-leases-qa01/out-old-red/regression.stdout"
cat "$ROUND/tap-checksum-fix/cgroup-durable-leases-image01/terminal.json"
cat "$ROUND/tap-checksum-fix/cgroup-durable-leases-sdk-input01/launch.json"
cat "$ROUND/tap-checksum-fix/cgroup-durable-leases-sdk01/current.json"
cat "$ROUND/tap-checksum-fix/cgroup-durable-leases-sdk01/terminal.json"
```

驱动源码在 `tools/pr119-pod-20261024/candidates/cgroup-durable-leases/`，仅对应固定任务的身份/路径，不能当作其他机器的一键部署。共享凭据不复制到仓库；原服务 debug 日志只留远端私有目录，导出采用白名单。

现场：滚动只涉及本任务五个业务 Pod（包含 Redis），持久化配置和数据不清空；前后验证原诊断快照可查询且 Secret UID 不变。未修改共享服务、旧环境、内核/模块/sysctl 或全局缓存，维持 650 GiB 宿主可用空间门，保留原失败快照和旧失败盘。本轮已全部成功终态，Environment/运行时/相关僵尸均0，原诊断快照已完整核验后SDK退休，旧失败盘仍保留。来源整理时修复构建复制的CLAUDE链接类型，原复制件保留，编译源码/二进制未变；只补离线元数据，不重复测试。
