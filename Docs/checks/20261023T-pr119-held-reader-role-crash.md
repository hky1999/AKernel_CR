# PR #119：gVisor 仍打开检查点输入时的控制角色崩溃
日期：2026-10-23。两组通过；这是固定时序的一致性实验，不是产品停顿或恢复耗时。

## 1. 问题
恢复进程还在使用共享检查点时，adxlet 或 Coordinator 崩溃并重启，会不会丢失读者保护，误删仍需使用的文件？早先健康运行时重启实验中，gVisor 后台读取已经结束，不能回答此问题。

## 2. 方法
沿用固定 AKernel 365f797、ADX/Execd 6fb53d7、sandboxd d5acc3b 加已验收且未提交的 TAP 修复，镜像与运行时均未更换。环境、制品摘要见 VERSION.md。

公共 SDK 创建 2 GiB 配置的沙箱，运行 1 GiB 确定性内存与 1 MiB 根文件探针；经现有原生 Snapshot API 捕获，源退出，在另一节点恢复。根据 OCI 的环境/运行时注解找到 sandboxd UUID，再匹配完整任务、Kind、Pod cgroup、进程可执行文件和启动代次。

只有目标 sentry 仍持有该快照的普通文件句柄才注入：独立 helper 短停此任务读者三秒，在句柄仍开时终止指定 Rust 角色子进程，finally 恢复同一个读者。不是停止 Pod PID 1，也不以服务正常 restart 代替崩溃，因为正常停止会主动 drain 沙箱。

## 3. 数据
| 被终止角色 | 崩溃点共享输入句柄 | 角色恢复后的原运行时 | 引用、目录及清单 | 删除忙快照 | 状态与后续操作 |
|---|---:|---|---|---|---|
| 目标节点 adxlet | 2 | 同一进程与启动代次 | 保留 | 拒绝并列出读者 | 1 GiB 完整状态、继续写和 checkpoint/reload 通过 |
| Coordinator | 2 | 同一进程与启动代次 | 保留 | 拒绝并列出读者 | 同上 |

终态 storage/held-reader-restart03/terminal.json 为 rc=0，两个 SDK 读者和快照最终删除，Environment 归零。[小型回执](evidence/pr119-juicefs-tapfix-20261023/held-reader-role-crash.json)。

保留两次夹具失败：01 的应用内存设置超过现有探针 1 GiB 上限；02 的 /proc 扫描碰到瞬态空 argv，在任何信号注入前抛出 IndexError。03 跳过空 argv，仍保留所有身份检查，使用新输出目录；未修改产品代码。02 的元数据根和角色容器身份检查经只读核对正确，不能将其写成产品或 cgroup 缺陷。

## 4. 结论
【实测】两类控制角色崩溃时，确有未关闭的共享输入；角色重启后的原读者、权威引用与物理输入仍在，忙删除被拒绝，完整恢复及后续操作通过。

【边界】三秒暂停是确定性交错夹具，不计为产品性能。打开文件不等于所有字节均尚未读取。没有内部物理删除屏障或双 collector 实测，不据此声称整个生命周期故障矩阵关闭。

## 5. 建议与改进项
保留此夹具供新存储后端重复使用；内部删除入口与多个 collector 的竞争仍须单独验收。随后建立同条件、分相和新旧交替性能，避免继续将正确性诊断样本混入性能统计。

## 6. 可复现步骤
```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
S="$N/round-365f797-20261023.clPWh2h0/tap-checksum-fix/storage"
cat "$S/held-reader-restart03-launch-receipt.json"
cat "$S/held-reader-restart03/terminal.json"
cat "$N/acceptance/runs/shared-held-reader-restart03-adxlet/barrier/terminal.json"
cat "$N/acceptance/runs/shared-held-reader-restart03-coordinator/barrier/terminal.json"
```
脚本为 hold-reader-crash-role03.py、sdk-held-reader-restart03.py、run-held-reader-restart03.py。复测必须使用新资源和输出目录；不可对照旧 PID 再发信号。所有语法检查与实验仅在远端执行。

## 7. 现场清理披露
读者由独立 finally 路径恢复；SDK 删除本轮实例和快照。旧失败现场保留，不改写原记录。没有修改共享服务、宿主参数、产品制品、父仓 gitlink 或他人资源。集群和任务存储留给后续验收；脚本尚未整理为提交交付。
