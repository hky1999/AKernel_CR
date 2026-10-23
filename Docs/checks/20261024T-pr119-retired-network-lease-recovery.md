# PR #119 节点重新加入：退出证明、网卡租约退休与网络规则恢复

最新状态：组件门、原故障源救援、相同 Pod 的 FC 两方向即时节点退出通过；固定镜像官方 76 项、两运行时状态/双向接管、持续直接 I/O 和两运行时 sandboxd 崩溃重启均通过。源码 fdb145c 已推个人 fork。FC 实验布局功能门完成，后端交替性能和产品晋升仍待完成，不默认启用；见 [完整功能验收](20261024T-pr119-native-rwfs-full-sdk-acceptance.md)。

## 1. 问题

用户要求补齐“新节点会话已注册、可路由且资源可调度”的真实就绪门，再完成 gVisor、Firecracker 和 JuiceFS 跨节点完整 SDK 验收。本检查继续追查就绪门拦住的源节点恢复失败；不能用 Pod Ready、systemd active 或清空旧状态替代产品恢复证明。

## 2. 方法

所有编译和测试均在 BareMetal 的原任务独占容器、私有 Kind 集群中执行。AKernel 固定 365f797，实际 ADX/Execd 固定 6fb53d7，SDK 和 VMM/内核/initrd/runsc 元组不变。组合源码在独立组件工作树 `codex-pr119-native-rwfs-rejoin-20261024`，基于已交付 e3f402c，后续整理提交为 fdb145c 并推个人 fork，实际 ELF 保持远端 qa02 的 debbf268…。

源码证据（qa02）：`internal/server/server.go:892` 在 InterfaceManager 初始化前调用退休核对；`network_retirement.go:52/81/120` 分别为运行时列表、退出状态与 PID/cgroup 证明，`:256/346` 为池账/原 OCI 文件的提交与目录同步。`server.go:1004` 的 `activeACLBindings()` 在缺少网卡归属时调用 `network_retirement.go:94` 的 `confirmNetworkOwnerStopped()`，重新证明退出。`network_retirement_test.go` 覆盖落盘边界与迟到归还；`network_retirement_acl_linux_test.go` 调用真实 `activeACLBindings()` 验证第二个启动失败。

真实交错：本任务源 Kind 容器即时停止，公共 SDK 自动切至另一节点，随后启动原 Kind，要求源 Node Pod UID 不变、退出租约由产品退休、目标内存与文件保持正确。原始日志和含内部环境的 OCI 元数据只保留远端私有目录，不复制入外发仓库。

## 3. 数据

| 检查 | 结果与适用范围 |
|---|---|
| 组合 qa01 | 全仓 fmt/vet/test、相关三轮回归与 server/network/FC race 通过；ELF 12402074…，已经部署到任务五个业务 Pod |
| 首次组合 SDK 驱动 | 在额外的“原失败所有者确由产品退休”门停止，官方 SDK 尚未开始。Helm 滚动改变 Pod 名，触发基线 `resetStateOnPodChange` 自动清理旧状态，因此不能拿此次启动成功证明新恢复逻辑有效 |
| 相同 Pod 的即时节点停止实验 force01 | 目标 SDK 自动接管成功；源的旧网卡归属和退休日志已由产品移除，但源 sandboxd 在网络规则恢复时报“sandbox … has no network resource”。整轮 rc=1，未改写通过 |
| 网络规则恢复旧红 | 原代码调用真实 `activeACLBindings()`，确认已退出的旧所有者缺网卡时失败；测试退出 1，驱动确认是预期断言而非编译错误 |
| 组合 qa02 | 修复网络规则恢复后的三轮相关回归、全仓格式/vet/单测、server/network/FC race 和生产构建全部通过；ELF debbf268d1b1a8d4a07b9ac02be7084c3fa53c7cf794f0b1887ec65f7ace313b。组件质量门不能代替真实 SDK 验收 |
| 原现场救援 helper 02 | 选错 ConfigMap 中 Python 脚本，远端 shell 语法门拒绝；只复制并核对任务候选 ELF，未改 ConfigMap、未停服务，失败现场保留 |
| 修正后的 helper 03 | 固定选择 `prepare_node.sh`，复用摘要相符的已暂存 ELF，先做远端语法检查再更新任务 ConfigMap；在相同 Pod 内替换源服务，真实就绪结果另续记 |

后续实测：rescue03 rc=0，原故障源相同 Pod 恢复。complete04 rc=0，在目标 Environment 与实际运行时均为空后，只更新目标 sandboxd；两端实际 ELF 都为 debbf268…，Pod UID 不变，真实能力/容量/路由稳定观察通过。`force02` 开始两个方向的即时节点退出与产品退休验证；`sdk02` 已登记等待，仅在 force02 整轮成功后才允许部署固定镜像。

image02 构建导入通过：CRI 53669406…、叶 manifest 2c28b22e…、config 6b4f0d92…，三个 Kind 节点一致。当时实际仍为 image01 基底和 ELF 覆盖，不能将“镜像已导入”写成“已部署或验收”。

随后 force02 rc=0：B→A、A→B 均通过；各验证 512 MiB 完整应用内存和 1 MiB 根文件、无显式 reload 的自动接管、原源 Pod UID 不变、产品退休证明、目标持续正确与最终 SDK 删除。首次 checkpoint 分别 5601 / 5683 ms，从读请求触发自动恢复到完整内存验证分别 3060.8 / 2346.8 ms（不含之前节点失联探测的全部时间）；这些各一例的故障验证不进入稳定性能结论。sdk02 已在核对原 ConfigMap UID/资源版本与脚本摘要后移除临时覆盖，部署同 ELF 的固定 native-rejoin02 镜像；实际摘要和双端十个文件 pin 核对通过，官方 SDK 执行中。

固定镜像官方 SDK 随后全通过：FC 8+30、gVisor 8+30，共 76，无跳过。两运行时各一实例三轮 checkpoint/reload 的内存、根文件及进程身份校验也通过；这些是功能与分相试跑，不是三个独立实例或交替后端性能结论。正常双向故障、真实直接写与 sandboxd 进程死亡另待终态。`shared-native-rejoin-sdk01-…` 是本轮驱动沿用的输出命名，实际由 sdk02 生成并记录 native-rejoin02 镜像，不表示使用第一版 ELF。

## 4. 结论

【源码】安全退休必须同时证明运行时 stopped、记录的 PID 已退出，以及本任务受管 cgroup-v2 已空或不存在。仅仅 TAP 设备消失不足以回收；未知、歧义或仍活跃的所有者继续阻止启动。网络规则恢复必须采用同样的退出证明，不能对所有缺网卡记录一概忽略。

【源码和回归】落盘顺序为：从原 OCI 资源归属中移走网卡并写退休日志、更新原资源池账、移除日志并同步目录；完成三步后才允许新分配。这样既可重放崩溃边界，也避免旧沙箱稍后归还同值资源而误释放新使用者。不另建 catalog，不重置资源 DB。

【实测】qa02 已通过组件门、原故障源救援，以及两个方向的全新即时节点退出与相同 Pod 自动恢复。本轮关闭该具体网络恢复缺口；固定镜像的完整 SDK、持续写和服务重启仍待完成，不能将整个新后端路线关闭。

## 5. 建议与改进项

先在原故障源节点的相同 Pod 内验证 qa02，保留目标运行时与失败证据。源恢复后，仅在目标无分配实例时更新它，再完成两个方向的即时节点退出、源重入、完整状态校验。随后固定候选镜像重新跑官方 SDK、持续直接 I/O 与服务进程死亡测试。

原实验的公共 JuiceFS 私有盘根仍有旧状态重置后遗留目录；当前归属标记不足以授权按节点整体扫描删除，不能贸然清空公共目录。需要明确节点/实例代次与孤儿回收契约后，再考虑默认启用。内存普通 File 恢复仍私有映射 JuiceFS 快照；virtio-fs SharedFile 的 `memory.live` 保持本地 XFS。本轮只迁移私有可写盘，不改变内存模式。

## 6. 可复现步骤

以下命令仅适用于身份已核对的原任务目录；先确认已有驱动终态，不重复执行正在运行的故障注入。

```sh
# TASK、ROUND 指向原独占任务；候选代码在 ROUND/tap-checksum-fix。
python3 "$TASK/cluster/namespace-lab07.py" run --task "$TASK" -- \
  kubectl -n akernel get pods -o wide
cat "$ROUND/tap-checksum-fix/native-rwfs-rejoin-qa02/terminal.json"
cat "$ROUND/tap-checksum-fix/native-rwfs-rejoin-force01/terminal.json"
cat "$ROUND/tap-checksum-fix/network-retirement-acl-oldred01/terminal.json"
# 完整 qa02 驱动已在远端依次执行格式、vet、全仓单测、相关 race 和构建。
# 查看落盘回执；不输出含凭据的 OCI config、Secret 或 bootstrap 原文。
cat "$ROUND/tap-checksum-fix/native-rwfs-rejoin-rescue03/terminal.json"
```

## 7. 现场清理披露

不手工清库、不换实例目录绕过失败，也不删除仍未知归属的私有盘。组合 image01 已通过本任务 Helm 滚动，五个任务业务 Pod 包含 Redis 都可能重启；其自动 Pod 名变更清理是基线行为，已如实排除出恢复证明。force01 只停止本任务身份匹配的 Kind 节点；其失败源保持原 Pod，依赖保留。

helper 03 只改本任务 bootstrap ConfigMap 和源 Pod 的 sandboxd，并在 `/home/akernel` 暂存固定摘要候选；目标服务不在该 helper 的停止范围内。候选覆盖层与镜像基底分别记账。共享服务、旧测试环境、宿主模块/sysctl 和资源隔离均不修改。原 helper 02 的失败文件保留，不外发私有配置原文。后续成功状态与覆盖层恢复动作须继续补记。
