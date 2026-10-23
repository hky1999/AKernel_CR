# PR #119：TAP 卸载状态修复与本地完整 SDK 验收

日期：2026-10-23。状态：本地磁盘组合通过；JuiceFS 跨节点与两条存储路线对照尚未完成。本文接续 `20261023T-pr119-365f797-sdk-local-gate-readiness.md`，不改写旧轮失败记录。

## 1. 问题

用户批准将诊断脚本的 `runsc list -q` 改为 `-quiet`，要求继续定位并解决 gVisor 的 Execd 就绪超时，再完成完整 SDK 和 JuiceFS 跨节点验收；编译测试全部在 BareMetal 独立环境执行，不修改旧环境和共享服务。

Execd 是沙箱内的命令执行服务。TAP 是宿主提供给沙箱的虚拟网卡。本轮同时发现并补齐了验收环境的文件创建权限、Firecracker OCI 镜像能力开关和真实 ADX 节点就绪条件。

## 2. 方法

- 固定 AKernel `365f7971f895f2b94cf390eefaab436600f005f0`、sandboxd 基线 `d5acc3b5b673074e20fd8b7733d4035dbaeae1b0`、实际 ADX 发布包 `6fb53d7331811535b6be5787ba026e03072f427b`；公共 Python SDK `0.2.0rc3`、原生 SDK `0.1.0rc3`。ADX 源码 gitlink `52bfc09` 不能代替实际发布包身份。
- 原失败脚本和输出保留，另存 `observe-create-internal-quiet01.py`。在创建超时期间通过 runsc 控制接口观察进程、socket 与监听端口。
- 在原始未修复镜像中，只临时改变本任务一块 TAP 的发送校验和卸载状态，比较同一沙箱的 TCP 连接和 SDK 创建结果；最后恢复原开关。
- 源码证据为 sandboxd `pkg/runtime/runsc/network.go` 的 `OpenTAP`：此前只切换 TAP 头格式，没有清除持久设备遗留的卸载状态。修改点位于 `TUNSETIFF` 成功后、设置非阻塞前。
- 增加独立内核回归，使用原生产代码和修复生产代码分别运行；同一持久 TAP 连续三轮切换原始以太网模式与 vnet 模式。
- 在专属 QA 容器中执行格式、vet、全仓单测、runsc race 和生产参数编译；随后构建单独镜像，只替换 sandboxd。
- 在本任务两个 Node Pod 验证实际 ELF 摘要；先补真实 ADX 就绪门，再以公共 SDK 验证两节点混合启动、官方集成/standalone 和完整内存回滚。没有直接用底层 CLI 替代 SDK 验收。

工作目录：

```text
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
Q=$N/round-365f797-20261023.clPWh2h0
D=$Q/tap-checksum-fix
```

旧环境 `akernel-pr119-repro-20261022.XfboxUgq` 未升级。当前工作仍是同物理机上的逻辑双执行节点，不是双物理机或生产高可用证明。

## 3. 数据

### 3.1 根因的直接证据

原始镜像中，Execd 父子进程均存活，子进程监听 50090，内部 Unix socket 已创建。宿主能解析沙箱 MAC 地址，但 TCP 连接超时。

| 同一沙箱的受控变化 | 结果 |
|---|---|
| 发送校验和卸载开启，值为 1 | TCP 连接在约 1.001 s 后超时 |
| 只将该开关关闭，值为 0 | 同一端口约 0.303 ms 连接成功，SDK 创建和命令执行成功 |
| 测试收尾 | 测试沙箱删除成功，原开关恢复为 1 |

校验和卸载是把部分网络校验和计算交给接收端的机制。Firecracker 的队列会启用这些特性；gVisor 本接入路径读取没有 vnet 元数据头的普通以太网帧，不能沿用前一个消费者的卸载契约。原接管代码未复位，导致持久 TAP 在跨运行时复用后出现不兼容状态。

【实测】已经证明该开关是当前连接失败的直接触发因素。【源码】修复恢复了 gVisor 队列所需的契约。本轮没有抓取并逐包证明每个错误校验和，不把这部分细节冒充抓包结论。

诊断中的 SDK 总耗时约 6.266 s，包含人工安排的等待及超时探测，不是正常启动性能样本。

### 3.2 组件修改与候选制品

仅修改远端独立源码：

| 文件 | 修改 |
|---|---|
| `pkg/runtime/runsc/network.go` | `OpenTAP` 在接管成功后执行 `TUNSETOFFLOAD=0`，失败返回带上下文错误并关闭 FD |
| `pkg/runtime/runsc/network_tap_reuse_linux_test.go` | 显式启用的隔离 TAP 回归；先模拟上一位 vnet 消费者开启卸载，检查 runsc 清除，再验证后续消费者能重新启用；循环三轮并按设备身份清理 |

当前为 `d5acc3b + 两文件未提交补丁`，不是原始 PR 不经修改就通过。没有修改 CR API、快照格式、guest agent、gVisor 或 Firecracker VMM 源码，故本次不是 CR 接口语义变更。

| 项目 | 固定身份 |
|---|---|
| 修改后的 network.go SHA-256 | `f873f94d6bebd993f25ea23a106bdd83277283c0acacf31fb77fd958a889e0c2` |
| 新回归文件 SHA-256 | `4c6f5a0a16c863993dc01f6a889d81a087a69827dfccc874ec908451136fbf81` |
| 新 sandboxd ELF SHA-256 | `9c74060c3c4edceed6edb746e6b42bdd21116e3663427238fb1dd5067f3c964b` |
| 候选镜像 | `localhost/akernel-pr119:365f7971f895-tapoffload01` |
| 镜像 config ID | `7c54b002aaebec6fc6b837d05f8f6eaa9f71e155173b281511c094fa978978c1` |
| Kind 导入后 Pod 实际 imageID 的 manifest 摘要 | `sha256:20257a27de0137383b1141709fb15dc87f81520f7fe0e41ba17b4e5ee31194a7` |
| OCI 导出归档 | 689912832 字节，SHA-256 `404719cabb4d5404685cfb1aa7bfa1928be8baf305c96ad5d22af22df42df008` |

config ID、manifest 摘要和归档 SHA-256 是不同对象，不混用。实际节点上的 sandboxd 摘要已核对；runsc、Firecracker、initrd、Execd 和 EROFS 根镜像均与原固定镜像一致。原镜像标签及归档未覆盖。

节点运行目录为 `/home/akernel/variants/tapfix`，仍是普通 XFS 目录布局。当前启用已有的 `virtiofs_enabled=true`，用于只读 OCI 根文件系统；不表示私有 RWFS 已迁到 JuiceFS。配置基线为 `D/virtiofs-enabled01-values.yaml`。

### 3.3 质量门与失败披露

| 验证 | 结果 |
|---|---|
| 原代码＋新内核回归 | 按预期失败：发送校验和卸载仍为 true |
| 修复代码＋同一回归 | 通过，三轮模式复用及后续重新启用卸载均通过 |
| 全仓格式检查 | 无未格式化文件 |
| `go vet ./...` | 通过 |
| `make test TESTFLAGS='-count=1'` | 通过；使用项目 Makefile 的单测范围，不能据此宣称特权 E2E 全部执行 |
| runsc 包 race，含显式启用的新 TAP 回归 | 通过 |
| `make release-binary` | 通过，保留原生产 CGO/tags 编译方式 |

所有编译测试均在 BareMetal 专属容器，Go 1.25.5，独立网络与 cgroup 命名空间，2 CPU、6 GiB 内存限额内进行。

保留的中间失败：

- 首轮缺少测试依赖，编译阶段停止；在任务独立模块缓存补下载固定依赖，再用新输出目录运行。
- 第二轮 3 个文件权限断言失败：测试要求 0640，但脚本全局 `umask 077` 使其变成 0600。按用户批准仅让单测和 race 子进程采用 022，外层日志仍私有；第三轮全部通过，没有修改断言或生产权限行为。这不是历史 ParseFlags 失败。
- 一次额外的旧代码权限对照因登录 shell 的 PATH 中没有 Go 而未执行；不拿它证明“旧代码也失败”。
- 一次诊断 SSH 连接中断，核对原进程已不存在且没有结果后才使用新的脱离 SSH 会话的监督进程。未把观察中断当作产品失败。
- 原 `-q` 参数错误和全部失败目录保留，不混入成功计数。

### 3.4 两项环境缺口及修正

第一项：原实验配置关闭 virtio-fs，Firecracker 官方 standalone 中 5 个错误均为“OCI image rootfs requires virtio-fs”。没有跳过用例或改为空镜像；确认已有 virtiofsd 1.14.0、guest 内核内建 FUSE/virtio-fs 后，仅打开本任务已有配置。

第二项：Pod Ready、systemctl active 不等于 ADX 可调度。两次冷部署首个请求被 `node_available` 等条件拒绝，稍后相同节点约束能成功。读取实际 SDK 编码和发布包同提交源码，确认 NODE_ID 标签及目标节点约束一致，没有据此修改调度器。

新门禁 `D/wait-adx-ready01.py` 在受控重启前记录旧会话哈希，重启后要求：

- 两端新会话与旧会话不同，且 session.routable=true；
- 节点未暂停调度且 available=true，NODE_ID 与实际节点一致；
- RPC/代理地址对应当前 Pod，Pod 与候选镜像身份正确；
- 两种运行时能力存在、资源容量足够，且没有活动或待重启 Environment；
- 连续三个稳定样本通过，并核对两端实际 sandboxd ELF。

门禁通过后，两节点各执行 gVisor→Firecracker→gVisor，6 次创建、命令和真实根目录文件读写全部通过，6 个沙箱均删除。它们不是 checkpoint 性能样本，也不单独证明冷启动等待错误在所有环境都已消失；后续部署必须继续采用该门禁。

### 3.5 本地完整 SDK 与完整内存回滚

`D/sdk-ready03/terminal.json` 为 rc=0。使用固定 Linux/amd64 OCI 镜像：

```text
docker.io/library/python@sha256:e8a38829209aea82774882e5157e1f7c3e8c8393ff53a697b3580896e57f345c
```

| 官方套件 | 结果 |
|---|---|
| Firecracker integration | 8 个通过，无跳过 |
| Firecracker standalone | 30 个通过 |
| gVisor integration | 8 个通过，无跳过 |
| gVisor standalone | 30 个通过 |
| 合计 | 76 个通过，四组 rc 均为 0 |

私有镜像写入隔离、PTY、命令、文件、网络策略、反向隧道、checkpoint/reload 等原有用例按原断言执行。首次未配 OCI 镜像时的跳过结果不作为最终通过证据。

另有两种运行时各 5 次连续回滚、各 8 项非法参数检查，以及各 1 次 512 MiB 确定性内存状态回滚，共 12 次 checkpoint/reload。校验完整内存摘要、PID、进程随机身份与已打开文件内容；四组均记录删除成功。

这些是本地 XFS 模式，不是 JuiceFS 跨节点、完整故障矩阵或共享卷产品验收。

### 3.6 性能观察：不宣称优化收益

条件：1 vCPU、2 GiB 内存、1 GiB 私有存储，节点本地 XFS；基础组未额外填充内存，各 5 个样本取 P50。checkpoint 为内部请求至 HTTP 返回完成，reload 为 SDK 调用耗时，均不是 guest 停顿。

| 场景 | 原轮 365f797、virtio-fs 关闭 | 本轮网络补丁、virtio-fs 开启 |
|---|---:|---:|
| gVisor checkpoint 请求完成 P50 | 77 ms | 74 ms |
| gVisor SDK reload P50 | 226.480 ms | 245.293 ms |
| Firecracker checkpoint 请求完成 P50 | 2448 ms | 2285 ms |
| Firecracker SDK reload P50 | 2696.639 ms | 2665.381 ms |

两轮不是交替对照，缓存历史和配置不同；不能把这些差值归因于网络补丁，也不能据此宣布提速或零回归。

本轮额外写入 512 MiB 内存的单样本：

| 运行时 | checkpoint 完成 | SDK reload | reload 起至完整内存校验 |
|---|---:|---:|---:|
| gVisor | 789 ms | 1027.361 ms | 2755.866 ms |
| Firecracker | 2309 ms | 2698.081 ms | 4623.370 ms |

本轮解决的是稳定性问题，不是 publish、RWFS 按需读取或内存捕获窗口优化；没有新的 SOTA 比较结论。

## 4. 结论

- 【实测＋源码】持久 TAP 的遗留卸载状态是当前 gVisor 就绪超时的直接触发因素；候选修复已通过内核回归、质量门及双节点真实混合启动。
- 【实测】补足现有 virtio-fs 能力和真实 ADX 就绪前提后，本地模式 76 个官方 SDK 用例及 12 次额外状态回滚全部通过。
- 【边界】当前为 PR #119 固定源码＋独立 sandboxd 网络补丁，不是原始 PR 原样通过；补丁尚未整理为可获取提交。
- 【未完成】本任务 JuiceFS 服务尚未据此宣称已安装或通过跨节点验收；旧环境的通过不能转记为本轮通过。两条存储路线对照、严格新旧性能对照、完整生命周期故障矩阵和生产验收仍未完成。

## 5. 建议与改进项

1. 后续部署复用真实 ADX 就绪门，不再仅等 systemd/Kubernetes Ready 后立即开始定点测试。
2. JuiceFS 接入必须保持本轮候选镜像、virtio-fs 和本地运行布局；不能直接运行仍引用原始配置的 `Q/storage/verify-attach.py`、`run-stage.py`，否则会回退网络修复。
3. 在新输出目录接入独立存储，再重复两运行时完整 SDK、真实根 RWFS 和 512 MiB 内存、A→B/B→A、源离线/重返、超时/重启/读者与回收竞争。
4. 按现有计划完成阶段一后，才进入 JuiceFS 卷内克隆与远端只读基线＋本地差异层的对照。所有失败、缓存冷热和读取/写入量分别统计。
5. 发布前将已验收的组件补丁提交到可获取分支，再更新父仓精确指针；未验收存储实验不混入组件交付。

## 6. 可复现步骤

仅针对本任务环境；不使用默认 kubeconfig。

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
Q="$N/round-365f797-20261023.clPWh2h0"
D="$Q/tap-checksum-fix"

# 查询本任务 Pod。
python3 "$N/cluster/namespace-lab07.py" run --task "$N" -- \
  kubectl -n akernel get pods -o wide

# 在独立网络/cgroup 容器中重复固定二进制的内核回归。
# 测试创建、删除自己的临时 TAP，不接管现役接口。
/usr/bin/podman --root "$N/image-build/graph" \
  --runroot "$N/image-build/runroot" --tmpdir "$N/image-build/libpod-tmp" \
  --cgroup-manager cgroupfs run --rm --network none --cgroupns private \
  --cgroup-parent /akernel-pr119-followup-20261022-qbGAw9tp \
  --cpus 2 --memory 6g --pids-limit 2048 --privileged --device /dev/net/tun \
  --mount "type=bind,source=$D/out03,destination=/out,ro=true" \
  --env SANDBOXD_RUNSC_TAP_REUSE_TEST=1 --entrypoint /out/tap-fixed.test \
  5f723febd2ba37977d45cf0eacf5a74b3acc45992b3e7e11053c41b61e338a2b \
  -test.v -test.run '^TestOpenTAPClearsPersistentChecksumOffload$'
```

原代码对照二进制为同目录 `tap-baseline.test`，按预期返回失败；不可把任意失败当成回归有效，必须匹配“卸载仍为 true”的断言。

原始输出索引：

```text
D/qa-runner/、out/                  缺测试依赖的原始失败
D/qa02-runner/、out02/              先红后绿回归及 umask 权限失败
D/qa03-runner/、out03/              全部质量门与新 ELF
D/permissions-baseline/            PATH 缺 Go 的无效对照
D/image01/receipt.json             镜像与 OCI 摘要
D/deploy-fixed01/                  候选替换、实际 ELF 与旧冷启动失败
D/sdk-full01/                      第一轮官方 SDK，virtio-fs 关闭
D/virtiofs-enable01/、sdk-full02/   配置启用及未等 ADX 可调度的失败
D/pin-probe01/                     温态相同节点约束的成功与实际调度策略
D/sdk-ready03/ready/               新会话、路由、资源、Pod 身份三样本门禁
D/mixed-sdk02/                     两节点 6 次真实混合启动
D/sdk-full03/                      76 个官方用例完整输出
N/acceptance/runs/tapfix-ready03-*/result/events.jsonl
```

重新运行一次性脚本前，必须分配新的脚本/输出名称，不能覆盖这些结果；不能在有活动 Environment 时重启 Node Pod。原始配置、认证文件及可能含敏感内容的日志只在远端私有目录，父仓仅保留脱敏摘要。

## 7. 现场清理披露

- 修改并重启的是本任务独立集群的 Pod；旧实验环境、共享服务及宿主内核模块/sysctl 未改动。Kind 容器身份未变。
- 镜像升级前后核对 TLS 和配置 Secret UID 未变，没有删除或打印凭据。公开 Registry 临时拉取 token 仅在内存中使用，父仓只记镜像摘要。
- 成功混合启动与四组附加回滚都记录沙箱删除；没有把失败记录或未知状态从 Redis 直接改成通过。
- 卸载开关的单变量诊断已恢复原值；内核回归按设备身份清理自己的 TAP。QA 退出容器及所有失败证据保留，没有清理其他任务数据。
- 原始运行目录、原始镜像和快照保留；本轮配置启用 virtio-fs 时没有删除或替换原数据目录。
- 尚未创建本轮 JuiceFS/Ceph/PostgreSQL 或 loop 设备。初始空间预检约 750 GiB 可用，无需清理他人文件。
- 本轮没有本地编译测试、没有组件提交推送、没有更新根目录三个组件 gitlink。当前父仓文档同样尚未提交。
