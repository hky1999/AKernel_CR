# PR #119 失败发布与复杂私有文件恢复进度

日期：2026-10-23。失败发布、复杂 RWFS、超时救援、SDK 调用者退出后的结果对账、S3 停顿、并发恢复、未关闭共享输入的角色崩溃和挂载替换均通过；内部删除竞争与分相交替性能仍有剩余，不能据此关闭计划阶段一。

## 开发内容

完整 SDK、双向接管和读者引用已有证据后，补“最后发布失败不报成功”和真实私有文件系统语义，避免在正确性门缺失时直接用 clone 演示决定生产后端。仍使用既有 ADX 控制面和公共 SDK，不重写运行时或存储索引。

## 修改内容

运行版本不变，无产品源码改动。新增远端辅助脚本：

- `storage/sdk-seal-quota02.py / run-seal-quota02.py`：只给本任务 JuiceFS manifests 目录临时 inode 配额；同源客户端探针确认 EDQUOT，注入快照请求，校对未发布、源状态、配额恢复和新请求成功；不重放未知请求，finally 限定恢复本轮配额。
- `storage/guest-rwfs-contract02.py / sdk-rwfs-contract02.py / run-rwfs-contract02.py`：复用固定 OCI 镜像和原有 checkpoint 探针，比较根目录文件、映射和打开文件的完整内容，连续三代回滚，另一节点分支隔离，再次捕获/恢复。
- `storage/sdk-snapshot-timeout01.py` 首次在进程匹配预检失败，尚未注入超时；源和成功快照保留。修正版 `02` 改由 OCI 注解精确映射 ADX runtime ID 与 sandboxd UUID，并支持验证后继续原现场。没有按模糊进程名杀进程。

全部语法检查和实际验收远端执行。脚本尚未整理为已提交交付；不将私有任务路径或未提交补丁当作外部已经可获取的版本。

## 测试结果

| 用例 | 结果与边界 |
|---|---|
| 清单目录失败，两运行时 | `seal-quota02` rc=0；非空未封存输出没有成功确认或 Ready 快照，配额撤销后源新状态保留且新请求成功；资源退出后失败输出也已回收。外部是通用 CONFLICT，未得到原始存储错误栈，不代表所有上传/挂载故障已测 |
| 复杂 RWFS，两运行时 | `rwfs-contract02` rc=0；各 5 次 checkpoint、4 次 reload，三代同节点与另一节点分支、64 MiB 文件、128 MiB 逻辑稀疏文件、追加/截断、链接、4 MiB mmap、打开后删除/重命名均正确。完整读校验不计按需恢复性能 |
| 超时 | `snapshot-timeout02` 两运行时 rc=0；首次预检失败保留，gVisor 继续同一源。1 秒捕获参数返回错误总耗时约 1.95 / 6.41 秒，源显式删除后原进程消失，已知快照可在另一节点恢复、继续 checkpoint/reload；不把超时返回当作全部 I/O 已结束 |
| SDK 调用者退出 | `caller-death01` 两运行时 rc=0；观察未封存捕获后仅杀本任务 SDK 子进程，两个后端均随后提交成功，按唯一名对账而未重放；新快照跨节点完整恢复、后续捕获和清理通过 |

S3 故障只针对本任务唯一 RGW 进程，使用 Pod UID、容器 ID、任务/Kind cgroup、可执行文件和启动代次核验，独立 watchdog 最多停顿 20 秒后恢复；不停止 MON/OSD/PG，不修改共享服务。`s3-pause01` 两组 rc=0：HTTP 确认可用→超时→恢复，期间不提前确认，没有新 Ready 快照，旧快照跨节点恢复与后续写/捕获通过，资源正常收尾。见 [S3 故障检查](../checks/20261023T-pr119-owned-s3-pause-fault.md)。

并发恢复脚本先因 SSH 连接中断未落地；重新连接后核实文件、驱动和结果目录均不存在，才部署 `sdk-concurrent-resume01.py / run-concurrent-resume01.py`。远端语法检查通过，并写入持久启动回执。最终两运行时各三轮，每轮八个独立 SDK 句柄同时 resume，48 个逻辑请求全部成功、0 冲突；每轮仅一条底层 Start 和一个最终关联运行时，完整状态通过，源退出。见 [并发恢复检查](../checks/20261023T-pr119-concurrent-resume-sdk-acceptance.md)。远端完整回执已取回，本地一次等待超时不将其改成失败，也不据此重跑。

后续 `held-reader-restart01` 已通过远端语法门并登记启动：只在本任务目标 gVisor 恢复进程仍有共享输入 FD 时，短停三秒并在同一受控进程中使所选 Rust 角色崩溃，再 finally 恢复原读者。按完整任务/Kind/容器 cgroup、OCI 环境注解、PID/启动代次验证，不按名称批量杀进程；若输入已关闭则拒绝注入，不记通过。分别覆盖 adxlet/Coordinator，终态待取。

后续终态：01 失败于应用探针 1 GiB 上限，02 失败于瞬态空 argv，均没有角色信号注入。另存 03，跳过空 argv 且保持身份检查；两角色均 rc=0，崩溃点共享输入 FD 各 2 个，原读者、引用和目录保留，忙删除拒绝，1 GiB 完整状态与后续捕获恢复通过，最终 SDK 清理。见 [未关闭输入的崩溃检查](../checks/20261023T-pr119-held-reader-role-crash.md)。

`mount-shadow01` 两运行时 rc=0：独立 watchdog 只在本任务 Pod 内，以完整可写本地目录遮住 JuiceFS 20 秒；请求在此期间拒绝，没有发布或本地替代输出。finally 恢复原 mount ID，源未保存状态保留，新独立快照成功，资源删除。见 [挂载替换检查](../checks/20261023T-pr119-mount-replacement-fail-closed.md)。未改共享服务和宿主挂载。

原生克隆复用的只读源码检查已完成，见 [复用边界](../checks/20261023T-pr119-native-clone-reuse-source-boundary.md)：FC 先验证现有 io.Copy 路径，gVisor 需区分当前验收版与后续 filestore 候选，后者的 FICLONE 不能直接当作 JuiceFS copy_file_range。尚无阶段二部署/新性能数据。

详见 [失败发布检查](../checks/20261023T-pr119-juicefs-manifest-quota-failure.md)、[复杂 RWFS 检查](../checks/20261023T-pr119-complex-rwfs-sdk-acceptance.md) 及同目录 evidence JSON。完整生命周期矩阵、分相交替性能、两条新存储路线和组件发布仍未完成。

## 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
S="$N/round-365f797-20261023.clPWh2h0/tap-checksum-fix/storage"
cat "$S/seal-quota02/terminal.json"
cat "$S/rwfs-contract02/terminal.json"
cat "$S/snapshot-timeout01/terminal.json"
cat "$S/snapshot-timeout02/terminal.json"  # 只在存在且 rc=0 时记通过
```

复测先确认没有其他活跃验收，以新输出目录串行执行；所有 kubectl/SDK 经本任务 namespace helper。当前任务集群、存储、代理保留，不能在超时用例仍持有依赖时清理。既有共享环境、宿主参数和父仓三个组件指针未变。
