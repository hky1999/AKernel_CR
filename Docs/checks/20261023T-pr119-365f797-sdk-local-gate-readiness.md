# PR #119 固定版本 365f797：本地回滚通过，完整 SDK 门禁仍阻塞

日期：2026-10-23。本文记录实测进度，不是下一阶段计划，也不是生产验收结论。

## 1. 问题

用户要求：先完成 PR #119 的 gVisor、Firecracker 和 JuiceFS 跨节点完整 SDK 验收，再做 JuiceFS 原生克隆与“远端只读基线＋本地差异层”的对照。编译测试全部在 BareMetal 独立环境执行，不修改共享服务。

本轮另获批准：修正独立部署 helper 的字符串生成错误，以及独立存储配置转换的 YAML 解析错误；保留旧文件和失败记录，继续验收。

## 2. 方法

- 固定 PR head 为 `365f7971f895f2b94cf390eefaab436600f005f0`。通过 Git tree 对比核实它相对前次 `8cfb67e` 的实际文件变化，而不是把 force-push 后的 merge-base 比较结果误当作两个快照的差异。
- 在新任务自己的网络、挂载命名空间与资源限额内，从固定源码远端构建镜像、准备 SDK、部署两个执行节点及控制面。旧的已验收环境没有升级。
- 先执行自有公共 SDK checkpoint/reload 探针，再执行上游 SDK 集成套件；两类结果分开记账。
- 完整 SDK 创建失败后，执行受控参数对照、只读服务检查和创建过程中的运行时状态采集。没有靠重启节点绕过失败。
- 源码证据：`src/sandboxd/pkg/runtime/runsc/network.go:115` 的 `OpenTAP`；`BuildNetworkArgs` 位于同文件第 143 行。这里只确认 TAP 网络接入方式，未据此认定超时根因。
- 根目录三个运行时 submodule 指针没有因本轮试验而变更。测试源码位于远端独立 clone，非本地组件工作树。

远端任务根目录：

```text
/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
└── round-365f797-20261023.clPWh2h0/
    ├── source/AKernel/
    ├── image-build/
    ├── sdk/
    ├── cluster/core365/
    ├── acceptance/
    ├── tests/
    └── storage/
```

以下命令用 `N` 表示任务根目录，用 `Q` 表示本轮目录。原始日志与凭据留在远端私有目录，父仓只收脱敏的小型证据。

## 3. 数据

### 3.1 固定组件与上游状态

| 项目 | 本轮实际版本或状态 |
|---|---|
| AKernel PR #119 | `365f7971f895f2b94cf390eefaab436600f005f0`，本轮从该固定源码构建 |
| ADX 源码 gitlink | `52bfc0998773b88df5aeb2e1b655b8e73ffd578b`；不能拿它代表镜像中的实际平台版本 |
| 实际 ADX 平台和 Execd 发布包 | `6fb53d7331811535b6be5787ba026e03072f427b`，来自 Dockerfile 固定下载与发布包清单 |
| 实际编译的 sandboxd | `d5acc3b5b673074e20fd8b7733d4035dbaeae1b0` |
| 公共 Python SDK / 原生 SDK | `0.2.0rc3` / `0.1.0rc3` |
| 本轮上游 CI 查询 | 10 项成功、1 项跳过；Standalone E2E 成功。此结果不能解释旧 head 的具体失败原因，也不能替代本环境验收 |
| 自有缓存路径保护提交 `787131c` | 仍单独保留、未推送；没有混入本轮原始 PR head 的构建 |

上游成功记录：[GitHub Actions](https://github.com/inclusionAI/AKernel/actions/runs/39873571800)。

本轮镜像为 `localhost/akernel-pr119:365f7971f895-runsc-firecracker`：

| 制品 | SHA-256 |
|---|---|
| OCI 导出归档，655206912 字节 | `a1fa04515efd03b46dfcd775d532b0fac5459b0552f1ac619bc660aa90a8daef` |
| sandboxd ELF | `cc8f871d690b1c95017f92802bc95a0f079639ec618f39ce001ce9ba84338cfb` |
| runsc ELF | `59cdd94eb03dc33a6d4f0a085d76d0cb67bd830caceaa899dfeeebc5b0165656` |
| Firecracker ELF | `41133331123c05d635a1a4a61a1eb41f078e9a216b5a197c1398e4e64e957cbf` |
| firecracker-agent initrd | `360a0b3bc1faf51fefd2e389208622d1343e8e020aa271a306cf8fbf698cad1b` |
| 镜像实际生成的 EROFS 根文件系统 | `2ecf4e0144686702613e6649d200b175d52d463d55cddba2ee0c36922c95d1a3` |

### 3.2 已通过的本地 XFS 基础回滚

每个 Sandbox 请求 1 vCPU、2 GiB 内存、1 GiB 私有存储。运行文件与 checkpoint 使用节点本地 XFS，尚非本轮 JuiceFS 配置。顺序为 gVisor 两组，再 Firecracker 两组。

| 运行时和场景 | checkpoint 请求至返回完成 | SDK reload 调用耗时 | reload 起至首个文件内容校验完成 |
|---|---:|---:|---:|
| gVisor，未额外填充内存，连续 5 次回滚的 P50 | 77 ms | 226.480 ms | 269.266 ms |
| Firecracker，未额外填充内存，连续 5 次回滚的 P50 | 2448 ms | 2696.639 ms | 2740.603 ms |
| gVisor，另行写入并校验 512 MiB 内存，1 个样本 | 857 ms | 1104.119 ms | 1148.077 ms |
| Firecracker，另行写入并校验 512 MiB 内存，1 个样本 | 2761 ms | 2678.172 ms | 2723.490 ms |

- 共 12 次 checkpoint/reload：两种运行时各 5 次基础回滚，加各 1 次 512 MiB 完整状态回滚。
- 512 MiB 用例核对完整内存摘要、进程 PID、进程随机身份和已打开文件内容；两种运行时分别在 reload 开始后约 2857.623 ms、4619.551 ms 完成全量状态校验。
- 两种运行时各执行 8 项非法参数检查。四组自有探针均记录沙箱删除成功。
- 以上是客户端请求口径，不是 guest 停顿，也不是跨节点恢复时间。不能同旧版脏页窗口或竞品公开数字直接并排。
- 旧环境曾测得 gVisor 64 ms、Firecracker 2590 ms 的基础 checkpoint P50，但本轮不是新旧交替对照，不能据此宣称提升或退化百分比。

### 3.3 辅助门禁

在任务私有工具环境内，106 个辅助/契约测试通过：

| 套件 | 用例数 |
|---|---:|
| Runtime contract | 18 |
| ADX Helm chart | 27 |
| Shared checkpoint | 9 |
| Prepare storage | 6 |
| Build image helper | 42 |
| APT retry | 4 |

最初从普通宿主 PATH 运行时找不到 Helm，chart 套件在初始化阶段报错；保留原记录，改在已有的任务私有工具环境执行后通过。不是修改断言后转绿，也不是运行时全仓测试。

### 3.4 完整 SDK 门禁失败

标准 SDK 验收入口为 `tests/run-official-sdk.sh`，计划按运行时依次执行 integration 和 standalone。实际在第一组 runsc integration 即失败并停止：

```text
environment create timeout: Execd readiness deadline exceeded
Ran 1 test in 60.679s
FAILED (errors=2)
```

两个错误分别发生在基础集成测试类的 `setUpClass` 创建沙箱，以及 checkpoint/reload 集成用例创建沙箱时。尚未到业务断言；基础类的其他方法未运行。后续 runsc standalone、Firecracker 官方套件均未执行。

受控创建诊断结果：

| 对照 | 结果 |
|---|---|
| 与此前成功自有探针相同：runsc、1 vCPU/2 GiB、1 GiB 存储、failover=true | 约 30.163 s 后服务端就绪超时 |
| 相同资源，failover=false | 约 30.077 s 后同样超时 |
| 显式 storage_mb=0 | 客户端直接拒绝；该输入不等于“省略存储参数”，不作为服务端故障证据 |
| 创建过程中采集文件与网络状态 | 再次约 30.151 s 超时 |
| 创建过程中列举 gVisor 运行时 | 沙箱显示 running；再次约 30.148 s 超时 |

两端 sandboxd、ADX 服务仍 active，未发生为绕过错误而进行的重启。最新权威目录查询尚有两个 Failed Environment 记录，错误均为就绪超时；它们不是成功运行的业务沙箱，也没有被伪造为通过记录。

诊断脚本还存在一个已明确披露的工具参数错误：`observe-create-internal.py` 使用 `runsc list -q`，而当前二进制只支持 `-quiet`。因此该脚本已获得的 `list --format=json` 结果有效，但后续进程及沙箱内监听状态没有采集成功。已经请求仅修正参数、另存失败证据后再诊断；截至本文尚未执行修正。不能用缺失的内部采集结果认定 Execd 已退出或网络一定损坏。

### 3.5 JuiceFS 配置修正的边界

原配置是 YAML。最初转换步骤误用 JSON 解析，在写新配置和启动存储之前失败。用户批准后，使用 PyYAML 读取原配置，在新的私有文件中保留：

```yaml
cacheMiB: 4096
cacheHostPath: /var/cache/akernel-pr119-storage/akcr119-juicefs/juicefs
cacheLargeWrite: true
writeback: false
```

上述为配置要点，不是完整可直接部署的 values 文件。

新文件为 `Q/storage/juicefs-values.yaml`，权限 0600；原文件和失败记录保留。没有启动本轮 Rook/Ceph/PostgreSQL/JuiceFS，没有创建本轮 loop 块设备，也没有执行存储挂载切换。`storage/run-stage.py` 仍是未执行的准备脚本，不能当作已验收工具直接交付；它的启动条件也还需纳入完整 SDK 门禁，而非仅依赖自有回滚探针。

## 4. 结论

- 【实测】新固定组合的镜像构建、辅助测试和两种运行时的本地磁盘基础 checkpoint/reload 通过。
- 【实测】完整 SDK 验收未通过，阻塞为 gVisor 创建时 Execd 就绪超时。相同探针参数重试仍失败，不支持仅把问题归因于默认磁盘请求或 failover 开关。
- 【实测】至少一次超时期间 gVisor 运行时处于 running；尚缺沙箱内 Execd 状态及连接证据。没有认定根因。
- 【源码】gVisor 通过 TAP FD 接入，`OpenTAP` 不请求 vnet header，Firecracker/Kata 使用自己的队列模式；这只是排查线索，不是已经证实的混合运行时故障原因。
- 【未完成】本轮 JuiceFS 跨节点完整 SDK 验收、生命周期与故障矩阵、新旧受控性能对照、两条存储后端路线实验均未完成。
- 【未外推】不能宣布生产可用、优于旧版或超过 AgentEnv/E2B/Cube。

## 5. 建议与改进项

1. 保留超时原记录；完成获批后的内部采集，检查 Execd 是否存活、监听端口和 ADX 到它的连接。优先覆盖 gVisor→Firecracker→gVisor 的顺序，但先后发生不等于因果关系。
2. 若定位到产品缺陷，单独修复并远端回归；不得以重启节点或忽略套件失败代替关闭问题。
3. 通过公共管理 API 清理本任务残留的失败对象，禁止直接改 Redis 权威目录。
4. 完整 SDK 门禁通过后，再允许启动本轮独立 JuiceFS 服务，验证两种运行时的跨节点回滚、源节点离线和重新加入，以及完整私有根文件系统与内存状态。
5. 读者保护、并发、上传失败、超时、断连、进程重启及垃圾回收仍需独立矩阵；自有回滚成功不能替代这些验收。
6. 然后进行同版本、同资源、明确缓存冷热状态的新旧交替对照，最后推进 JuiceFS 卷内克隆和远端基线＋本地差异层。

## 6. 可复现步骤

仅在确认仍属于本任务的独立环境内运行；不得把本任务 kubeconfig 或资源名称用于旧环境。

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
Q="$N/round-365f797-20261023.clPWh2h0"

# 检查自己的 Pod，不使用默认集群。
python3 "$N/cluster/namespace-lab07.py" run --task "$N" -- \
  kubectl -n akernel get pods -o wide

# 官方完整 SDK 验收原始入口；当前已知会在 runsc 集成失败处停止。
# 保留既有输出，重新实验前必须为 runner 分配新的输出目录，不能覆盖原记录。
python3 "$N/cluster/namespace-lab07.py" run --task "$N" -- \
  bash "$Q/tests/run-official-sdk.sh"

# 单独重复官方 runsc 集成时，使用新目录保存输出，仍在私有 namespace 内执行。
OUT=$(mktemp -d "$Q/tests/runsc-integration-repeat.XXXXXXXX")
python3 "$N/cluster/namespace-lab07.py" run --task "$N" -- \
  bash -lc '
    set -eu
    set -a; source "$1/acceptance/auth-local365/sdk.env"; set +a
    export AKERNEL_RUN_INTEGRATION=1 AKERNEL_TEST_RUNTIME=runsc
    export PYTHONPATH="$1/source/AKernel/sdk/python"
    export HOME="$2/home"
    mkdir -p "$HOME"
    cd "$1/source/AKernel"
    "$1/sdk/client/bin/python" -m unittest discover \
      -s sdk/python/tests/integration -t sdk/python -v
  ' pr119 "$Q" "$OUT" >"$OUT/stdout" 2>"$OUT/stderr"
```

两段测试命令是不同入口，复现时选一个即可。原 runner 的既有输出不应直接覆盖；上方单套件入口已经使用新的输出目录。

原始证据位置：

```text
Q/receipts/images.json
Q/image-build/payload-receipt.json
Q/sdk/release-manifests.json
Q/cluster/core365/terminal.json
N/acceptance/runs/runsc-five20/
N/acceptance/runs/runsc-memory20/
N/acceptance/runs/fc-five21/
N/acceptance/runs/fc-memory21/
Q/tests/contracts-private-tools/
Q/tests/official-sdk-local/
Q/tests/create-diagnostic/
Q/tests/readiness-diagnostic/
Q/tests/runtime-log-diagnostic/
Q/tests/execd-state-diagnostic/
Q/tests/observe-create/
Q/tests/observe-create-internal/
```

目录中可能含运行配置或敏感日志，不直接提交或外发。父仓脱敏摘要见 `Docs/checks/evidence/pr119-365f797-20261023/sdk-local-and-readiness.json`。

## 7. 现场清理披露

- 仅构建、部署和诊断本任务独立集群；没有修改或重启旧环境、共享服务、宿主证书或 DNS。
- 只按 UID 条件删除本任务此前未被消费的空 Secret，再由原 Helm 创建正式配置。TLS Secret 保留，内容未输出。
- 本轮四组成功自有探针均已删除沙箱；失败 Environment 的残留状态如实保留，未写 Redis 改状态。
- 没有为规避就绪超时重启运行节点或服务。独立集群、私有认证/转发及镜像仍保留，供继续定位，不宣称已经全部回收。
- 没有启动本轮存储设备或服务，故没有本轮新增存储资源需要回收。没有清理其他任务日志、镜像或磁盘。
- 宿主 inotify=1024 为此前批准的临时设置，本轮未再次调整或持久化；依赖仍在使用，不擅自恢复。
- 除已披露的部署生成与 YAML 解析错误，诊断期间还出现只读命令的引号/字典访问错误、资源类型不匹配和宿主缺少 rg；没有产生共享环境写入。远端文本检索改用系统 grep。错误未当作产品测试失败统计。
- 没有本地编译测试，没有新的产品源码提交或推送；未验收 helper 不混入交付。
