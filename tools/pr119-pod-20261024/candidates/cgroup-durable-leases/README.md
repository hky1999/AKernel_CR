# PR119 cgroup 归属崩溃恢复：执行来源与复现说明

本目录保存本任务实际执行的脚本及证据整理工具。修复源码为 `hky1999/sandboxd:codex/pr119-cgroup-durable-leases-20261024` 的 `91dff2f686d4f3f18540d33c0851b127212d8567`，父版本21fb466；不是在旧控制面新增功能。当前可选组合见 `delivery/pr119-cgroup-durable-leases-20261024.json`。

| 文件 | 实际执行与结果 |
|---|---|
| driver01.py / qa01.sh | 原版仅加测试，四组持久化回归实际失败；候选三轮包、全仓fmt/vet/test、相关race和构建通过 |
| prepare-image01.py | 仅替换已测sandboxd，保留原完整运行时包；构建和三Kind导入/摘要链验证通过 |
| run-full-sdk01.py | 本任务滚动、真实就绪/15制品/Secret/原快照核验；四组严格输入崩溃、官方76项、各三轮状态和双向接管全通过 |
| sdk-held-reader03.py / hold-reader-role02.py | 固定源/目标节点，以真正命名pages输入及inode为依据；sandboxd A/B、adxlet A、Coordinator B均保留原读者和完整状态 |
| check-preserved-snapshot01.py | 滚动前后原失败快照身份一致、可查询 |
| run-postsdk01.py / sdk-ordinary-restart01.py | 等待完整SDK成功，随后FC/gVisor各一次daemon崩溃，原进程、未保存状态和引用保留，后续保存恢复通过 |
| sdk-retire-diagnostic01.py | 修复版恢复原失败快照，1GiB内存和根文件完整一致，再由SDK删除读者和诊断快照 |
| final-state01.py | 无Environment/运行时/相关僵尸，五Pod镜像、两Node15制品、路由/资源/目录与磁盘余量检查通过 |
| collect-delivery01.py | 首次离线来源检查因CLAUDE链接类型差异停止；没有重新运行应用或修改服务 |
| restore-source-alias01.py | 确认构建复制把CLAUDE→AGENTS链接变为同内容普通文件，保留复制原件后恢复原链接；编译源码/二进制不变 |
| collect-delivery02.py | 只读现有结果，导出9份/20492字节白名单，核对11份实际构建/验收脚本；不复制原日志/配置/凭据 |

脚本固定原任务目录、节点/容器身份和二进制摘要，是可审计的执行配方，不能直接在另一台机器运行。新环境先按父仓中文Pod复现文档与已提交的脱敏JuiceFS配置建立独立任务，再替换这些身份绑定并在远端解析语法/校验源摘要。不可复制原认证环境文件、重建旧输出目录或盲目重跑失败驱动。

编译/测试始终在远端；本地只编辑、核对摘要、整理Git。代码在提交前已构建，最终八份变更源码逐一匹配门禁摘要，提交后没有重建。镜像 `localhost/akernel-pr119:365f7971f895-cgroup-leases01` 只导入本任务Kind，未发布到镜像仓，也未提升正式release/pin/default；外部复现应按固定源码构建后使用自己的镜像地址。

只读复核已有终态（变量对应你自己的独立任务）：

```sh
cat "$ROUND/tap-checksum-fix/cgroup-durable-leases-qa01/terminal.json"
cat "$ROUND/tap-checksum-fix/cgroup-durable-leases-image01/terminal.json"
cat "$ROUND/tap-checksum-fix/cgroup-durable-leases-sdk01/terminal.json"
cat "$ROUND/tap-checksum-fix/cgroup-durable-leases-postsdk01/terminal.json"
cat "$ROUND/tap-checksum-fix/cgroup-durable-leases-final-state01/terminal.json"
```

源码与测试脚本摘要、四组故障时序、日志白名单和最后现场见 `Docs/checks/evidence/pr119-cgroup-durable-leases-20261024/`。严格页输入和未保存状态是两种不同的验证，不互相替代；这些正确性结果也不构成性能配对、生产HA或整条存储路线完成。
