# Firecracker 源节点重新加入失败：持久化网卡租约与设备不一致

日期：2026-10-24。本篇保留首次发现时的失败与修复要求。后续组合 qa02 已修复退出租约及网络规则恢复，原故障源救援、两个方向相同 Pod 的即时节点退出均通过，见 [后续修复检查](20261024T-pr119-retired-network-lease-recovery.md)。新后端整体验收仍须等待固定镜像完整矩阵；不以修复后的结论改写原失败结果。

## 1. 问题

继续真实会话、路由与可调度等待门后的 SDK 和跨节点验收。在 Firecracker 运行态可写盘放 JuiceFS 的实验中，目标节点已成功恢复，源节点重新加入却超时；检查根因和安全修复边界。

## 2. 方法

仅在原 BareMetal 私有 Kind 集群的本任务 namespace 内检查。实际实验 ELF efa639832d602aced279071deacf81fb334c0adba1d401883c6fa43e5170a3f9，AKernel 365f797、实际 ADX 6fb53d7，FC/内核/initrd/runsc 与上一轮一致。读 SDK 终态、逐事件回执、源节点 systemd 属性、限量脱敏 sandboxd 文件日志、mountinfo 和进程列表；没有读取或输出凭据。

源码：sandboxd 基线 e3f402c 的 pkg/networkmanager/tap_recovery.go，InterfaceManager.load 从 durable usingInterfaces 还原 activeTapByIP，发现租约对应 TAP 不存在即返回错误（约 194–197 行）。internal/server/server.go 在 sandbox.Manager 建立和旧沙箱退出清理前初始化 InterfaceManager（约 890–949 行）。因此，旧运行时已经退出的场景，也可能先被旧网卡租约挡在服务启动之前。

## 3. 数据

| 项目 | 观察与口径 |
|---|---|
| 原生克隆候选官方 SDK | FC 8+30、gVisor 8+30，共 76 全通过、无跳过 |
| 三轮状态回滚 | 两种运行时各 3 次，512 MiB 应用内存、64 MiB 根文件、2 GiB VM、1 GiB 私有盘，完整内存/PID/文件校验通过 |
| gVisor 节点故障 | A→B 与 B→A、源重新加入、目标继续正确和删除均通过 |
| FC 第一方向 | 源 B 离线后目标 A 通过 512 MiB 内存与 1 MiB 根文件校验；源 B 重新加入等待 240 秒失败，未关闭此方向，第二方向未执行 |
| 源 sandboxd | ExecMainStatus=1，activating/auto-restart；文件日志反复出现 active pooled TAP … is missing |
| 源 ADX | systemd active，但权威会话 routable=false、available=false，不能因 Pod Ready/进程 active 就发 SDK |
| 挂载 | checkpoint 与实验 RWFS 根均真实 fuse.juicefs；原 filestore 为 xfs，目录存在 |
| 后续压力与进程重启 | 依赖整轮 SDK 失败，驱动拒绝开始，没有新的压力 VM |
| 后续只读盘点 | Environment=0，两端均未发现 FC/runsc 运行时进程；实验 JuiceFS 根仍保留 1 份私有可写盘。未人工清扫，不能写成全部清理完成 |

证据为 evidence/pr119-juicefs-tapfix-20261023/fc-writable-{sdk-pilot,cross-pilot,rejoin-failure,postsdk01}.json；远端原始失败目录保留。脱敏日志只保留错误含义，省略内网 IP、完整租约和运行时凭据。

## 4. 结论

【实测】就绪门有效，且本轮出现了 Pod Ready 但 sandboxd 无法启动、ADX 不可路由的具体案例。目标恢复成功不足以关闭包含源重新加入的整条验收。

【源码】缺失 TAP 时拒绝恢复活跃租约是既有保护，避免把仍有使用者的旧租约重新发放。不能直接移除这个检查，也不能仅凭“没有设备”清空租约。尚未证明故障由 JuiceFS 字节克隆导致；观察到的启动失败直接原因是网卡租约与设备不一致，运行态远端存储可能改变关机耗时，但其因果关系未实测。

【边界】普通 SDK 和性能样本可保留为部分结果；新的运行态存储路线尚未整体验收、提交、推送或晋升默认值。

## 5. 建议与改进项

下一轮优先补已退出运行时的网卡租约恢复，再继续 FC 反向迁移、持续写和 sandboxd 进程死亡验证。修复必须满足：

1. 从精确沙箱/运行时身份、资源归属和实际进程/cgroup 状态取得退出证明；未知、读取失败或仍有任务时保留租约，不扩大为删除共享环境。
2. 保留“设备缺失”和“设备 ifindex 被替换”时对活跃或未知使用者的拒绝。本轮独立分支 codex/pr119-retired-tap-recovery-20261024 先增加这条缺失设备的保护回归；三轮 race 通过只是保护基线，不是修复完成。
3. 防止旧沙箱迟到的 Release 把新借用者的相同资源字符串归还（旧值再次出现的竞争）。仅删除池 DB 条目而保留 OCI config 中原资源归属，会留下此风险。
4. 把旧归属退休与池账更新做成可恢复的顺序；任一落盘边界崩溃后，既不能重新归还新租约，也不能失去旧租约的证据。可复用沙箱已有持久化元数据和原子写，不建平行 catalog。
5. 先补确定性交错/失败落盘回归，再在本任务两个方向的真实节点退出/重入验收。手动清库或换新目录不等于产品自动恢复通过。

另一个源码边界：Start/Restore 失败清理原先依赖 best-effort stopInstance。已在目录候选补 preserveRunningWritable，停止后若 VMM/virtiofsd 身份仍匹配则保留状态、目录和实例；显式 Delete 同样拒绝删除。qa04 的真实匹配子进程回归与全仓门通过，但不是实际内核不可中断 I/O 注入，且新 ELF 932adc2f… 尚未部署，不能与 efa63983… 的 SDK 结果混记。

## 6. 可复现步骤

所有编译测试仅 BareMetal 独占容器。历史路径与 PID/UID 先核对；不得重复启动已有驱动或在共享宿主重放挂载测试。

```sh
# TASK 为原独立任务目录；以下 helper 进入该任务 namespace
python3 "$TASK/cluster/namespace-lab07.py" run --task "$TASK" -- \
  kubectl -n akernel get pods -o wide
python3 "$TASK/cluster/namespace-lab07.py" run --task "$TASK" -- \
  kubectl -n akernel exec <本任务源Pod> -- \
  systemctl show sandboxd adx -p ActiveState -p SubState -p MainPID -p ExecMainStatus
# 在独占编译容器 /src 内验证保护基线（不需要宿主网络访问）：
go test -race -count=3 -run '^TestRecovery(RejectsMissingActiveTapWithoutRetirementProof|RejectsExternallyReplacedActiveTap|RepairsIdleOrphanMacAndBridgeDrift)$' ./pkg/networkmanager
```

原始故障入口为 tap-checksum-fix/fc-writable-sdk01/cross-node01；读取其 terminal.json 与逐轮事件，不根据某条成功事件重写整轮结果。SDK 探针和最小回执已入父仓工作树，产品候选代码仍在独立组件工作树、未交付。

## 7. 现场清理披露

没有清空资源 DB、修改租约或重放未知 checkpoint；没有手动删除保留的私有盘或更换旧环境。源 sandboxd 仍在其自有 Pod 中失败重试，目标任务 Pod/存储仍保留，后续 Environment=0 和运行时进程=0 是只读观察，不是本轮新增的清理动作。自有派生压力驱动已终止于依赖失败。宿主空闲 737045630976 字节（约 686.4 GiB），仍高于 650 GiB 预留。共享服务、宿主模块/sysctl、其他任务和旧实验均未修改。
