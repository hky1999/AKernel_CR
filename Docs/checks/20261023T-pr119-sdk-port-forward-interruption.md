# PR #119 JuiceFS 连续回滚时 SDK 转发中断诊断

日期：2026-10-23。状态：中断已定位、任务入口已恢复、失败沙箱已核对清理；新入口完整 SDK、状态负载及双向故障接管主链路通过。

## 1. 问题

在独立 BareMetal JuiceFS 环境完成官方 SDK 后，Firecracker 五轮连续 checkpoint/reload 的第四轮调用失败。需要区分产品恢复错误、存储故障与验收入口故障，不能直接重放结果未知的 checkpoint 或把三轮通过写成五轮通过。

## 2. 方法

版本与前轮一致：AKernel `365f797`、实际 ADX `6fb53d7`、sandboxd `d5acc3b` 加未提交 TAP 补丁。运行文件在节点本地 XFS，checkpoint 在真实 JuiceFS；没有为排查换二进制。

检查失败事件、SDK 私有转发进程的 PID/启动代次、转发日志、所有任务 Pod 的重启与 Ready 状态、ADX 权威记录、Ceph 容量/健康及本任务私有端口。证据位于本轮远端 `tap-checksum-fix/storage/fc-five-diagnosis01/02`。

## 3. 数据

| 项目 | 实测 |
|---|---|
| 官方 SDK | 转发中断前，两个运行时的 76 个 integration/standalone 用例全部通过、无跳过 |
| 附加 gVisor 状态负载 | 五轮连续回滚和一轮 512 MiB 完整状态校验通过，并有删除成功记录 |
| 附加 FC 连续回滚 | 前三轮通过；checkpoint 请求到完成为 8696、12546、15410 ms，SDK reload 为 4149.527、5571.412、4922.454 ms；只作失败前原始样本，不汇总为五轮成绩或性能收益 |
| 第四轮错误 | SDK command 报 frontend invoke outcome unknown / Connection refused，脚本停止并保留沙箱；尚无第四轮成功确认 |
| 转发进程 | 私有 kubectl port-forward 已退出；其日志明确出现 `error: lost connection to pod`，私有 18443 端口连接被拒绝 |
| 任务服务 | 两节点 ADX 可用且可路由；AKernel 与存储 Pod 均未重启；失败沙箱仍为 Running，运行时身份未被替换 |
| 存储与容量 | 专属 Ceph 40 GiB 总容量、当时约 6.69 GB 已用；没有满盘告警；XFS 可用 735203917824 字节。单副本及认证兼容健康告警仍在，不是生产 HA 验收 |
| 只读采集小错 | 首次采集在比较 nullable lastTimestamp 时 TypeError；原输出保留，使用空值兜底离线分析已保存事件，再继续未完成的只读项 |
| 恢复与清理 | 新入口通过 TLSv1.3 和原受信证书校验；原生 ADX SDK 重新读到 `checkpoint-before-3`，核对身份后删除该沙箱，权威记录消失；没有重放结果未知的 checkpoint |

## 4. 结论

【实测】这次脚本中断由 SDK 入口的 kubectl port-forward 退出引起，不能据此判断 FC 数据恢复失败。未证明导致该转发退出的底层单连接 reset 的更深原因；不能将它静默计作无故障样本。

【实测】保留沙箱可读、运行时身份未变，已受控清理；诊断使用原生 ADX SDK，不把这次救援记作原公共 SDK 五轮通过。

【改动】为避免长套件持续依赖 Kubernetes 调试转发，只在本任务私有集群创建独立 NodePort Service，复用现有 ingress-api selector，未修改原 Service。任务私有网络中运行现成的 `systemd-socket-activate` / `systemd-socket-proxyd`，把本地控制/数据端口转到私有控制节点的 NodePort，保留原 TLS 端到端校验，没有新写 TCP 数据代理。

新 Service UID、任务节点 ID、代理 PID/启动代次和 TLS 证书摘要均记录在 `storage/direct-transport01/`。创建后立即探测曾早于 kube-proxy 编程完成而被拒绝，该失败保留；随后通过既有有界 TLS 就绪探针，没有再次创建 Service 或修改证书。`terminal.json` 保留最初探测失败，后续成功以独立 `ready.json` 为证据。

【后续实测】新入口上的整套 SDK、五轮状态负载和 512 MiB 状态校验已完整重测通过，输出为 `storage/sdk-full02` / `run06` / `shared-tapfix-direct01-*`。以此为前置，两种运行时 A→B/B→A 四条故障接管也已通过，输出 `storage/cross-node05`。原失败仍为失败，不计入成功性能样本。完整生命周期故障矩阵和新存储路线没有因此完成，见 [阶段总结](../stages/20261023T-pr119-tapfix-juicefs-bidirectional-sdk-stage-summary.md)。

## 5. 建议与改进项

1. 产品和性能测试使用任务私有稳定网络入口，显式记录传输路径；kubectl 调试转发中断应作为独立失败类别。
2. 对“请求结果未知”的捕获操作先核对权威记录和沙箱，不自动重放。新样本用新编号，旧失败保留。
3. 对照的两侧使用相同 SDK 入口；不能将入口变化、缓存热度和存储路径变化合并宣称运行时优化收益。

## 6. 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
Q="$N/round-365f797-20261023.clPWh2h0"
S="$Q/tap-checksum-fix/storage"
cat "$N/acceptance/runs/shared-tapfix01-fc-five/terminal.json"
cat "$S/fc-five-rescue01/terminal.json"
cat "$S/direct-transport01/ready.json"
cat "$S/run06/steps.json"
python3 "$N/cluster/namespace-lab07.py" run --task "$N" -- \
  kubectl -n akernel get service akernel-sdk-direct-tapfix01
```

创建/恢复的准确操作保存在 `S/prepare-direct-transport01.py` 和 `S/rescue-fc-five01.py`。直连探测使用既有 `Q/prepare-auth.py --tls-probe` 和任务私有证书；认证文件不入库。已创建资源不能无检查地重复运行创建器。

## 7. 现场清理披露

本轮新增的 Service 和两个 socket 代理只属于本任务私有 Kubernetes/网络命名空间，没有绑定宿主公共接口、修改旧集群、重启共享服务、关闭证书校验或重建存储。失败沙箱已删除；代理与 JuiceFS 保留供后续验收。原失败事件、转发日志、诊断结果和旧配置均保留。父仓组件指针、运行时及模板制品未变。
