# PR #119 TAP 修复组合：JuiceFS 验收进度

日期：2026-10-23。状态：实际存储、官方完整 SDK 76 用例、附加 12 次 checkpoint/reload 及四条双向故障接管通过；完整生命周期故障矩阵与两条新路线尚未完成。

## 开发内容

在已经通过本地完整 SDK 的固定候选上接入真实 JuiceFS，并沿用用户批准的 ADX 实际可调度就绪条件。私有运行文件仍在本地 XFS；本轮先验证 checkpoint 写 JuiceFS 和对端恢复，不提前切换新存储路线。

## 修改内容

- 远端 `tap-checksum-fix/storage/install01.py`、`verify-attach01.py`：复用已有安装/验证逻辑，替换本轮质量门和输出路径，以 `virtiofs-enabled01-values.yaml` 为基准合并，避免回退已验收修复。
- `prepare-and-accept01.py::snapshot_forward`：首次把 Python 包装进程误当作私有命名空间内的 kubectl，预检失败，原件保留。
- `prepare-and-accept02.py::snapshot_forward`：核对包装进程启动代次及直接 kubectl 子进程的命令、网络命名空间，结束转发前再核对父子身份。该脚本串联真实就绪与 SDK 门禁。
- `sdk-failover01.py`：复用现有 SDK 故障接管测试，允许通过已有环境变量选固定 OCI 镜像；默认镜像行为不变。
- `cross-node01.py`：另存双向跨节点驱动，只在共享存储同节点 SDK 完整通过后运行；未取得本轮跨节点通过证据。
- 仅在任务 Kind 控制节点补齐本任务 loop 的标准路径；保存原 OSD 准备 Job 后按 UID 受控重试，后端文件和设备身份不变。

上述为远端任务辅助脚本/配置，无新增组件提交；前轮 sandboxd 产品补丁仍未提交推送。

## 测试结果

配置合并/渲染预检、任务 PV 创建、设备容量/身份核验通过。首个驱动预检失败原样保留；初次 Ceph 准备虽退出 0，但日志确认零 OSD，不算安装通过。补标准路径后重试日志确认一个 raw OSD，完整存储与 SDK 仍待后续终态。

后续补充：只重启本任务 Rook 控制器促使重新对账，并在 FSID 核验后使测试池 PG 数满足控制器要求。首次安装超时保留；复用设备和 Secret 的第二轮安装成功。Ready 时序及 OnDelete 等待方式的两次辅助脚本失败保留，当前执行器为 `prepare-and-accept05.py`。

三客户端真实 JuiceFS、跨客户端同步写、PostgreSQL 三项持久化开关、ADX 新会话/路由/资源与载荷检查通过。当前共享 checkpoint 配置下官方 integration/standalone 共 76 用例全通过、无跳过。附加五轮回滚和 512 MiB 校验正在运行，双向跨节点尚未通过。旧 CI 的实际失败位于动态网络策略用例的沙箱删除/ADX 对账阶段，与 TAP 故障分开，见 [原始日志检查](../checks/20261023T-pr119-original-ci-failure-evidence.md)。

再补充：附加 FC 五轮在第四轮因任务 kubectl 转发退出而中断，先前三轮成功，不算五轮通过。存储和节点 Pod 未重启、Ceph 未满盘。已通过原生 SDK 核对保留文件、删除本任务失败沙箱，没有重放未知 checkpoint。现使用本任务私有 NodePort 与现成 systemd socket 代理，TLS 校验保持开启；`run06/sdk-full02` 重新执行完整 SDK 和四组状态负载，旧失败独立保存，见 [诊断检查](../checks/20261023T-pr119-sdk-port-forward-interruption.md)。

最终补充：`run06` 与 `sdk-full02` 均返回 0，76 用例、各五轮连续回滚/八项非法参数/一次完整 512 MiB 校验全部通过。`cross-node05` 返回 0，两运行时均 A→B/B→A，源离线、根 RWFS、内存、目标继续写、源重新加入与最终删除均通过。新增只读 FD/maps 和 RGW 计数，未修改运行时制品；当前 FC 默认为 Full checkpoint，不能与历史增量窗口混用。首次读请求前可能已有预取/恢复，计时和计数分窗口保留。完整数据、实际介质边界及后续门禁见 [阶段总结](../stages/20261023T-pr119-tapfix-juicefs-bidirectional-sdk-stage-summary.md)。

尚无本轮性能收益结论。前轮本地 76 个官方 SDK 用例和另外 12 次 checkpoint/reload 不等同于当前 JuiceFS 验收，也不能代替生命周期故障门。

## 可复现步骤

远端路径、命令、原始证据和清理边界见 [本轮检查](../checks/20261023T-pr119-juicefs-sdk-tapfix-acceptance.md)。最终入口为远端 `storage/run06/terminal.json`、`sdk-full02/terminal.json`、`cross-node05/terminal.json`；小型脱敏证据已进入父仓文档目录，原始凭据/大日志/运行数据仍留远端。任务集群和存储保留，Environment 记录为 0，空闲约 689 GiB。
