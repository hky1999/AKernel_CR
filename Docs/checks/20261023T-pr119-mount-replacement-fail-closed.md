# PR #119：JuiceFS 挂载被普通本地目录替换时拒绝发布
日期：2026-10-23。gVisor、Firecracker 均通过，未变更产品制品。

## 1. 问题
共享检查点挂载消失或被替换后，checkpoint 会不会静默写到路径下面的普通本地目录，并误报为跨节点可用？

## 2. 方法
沿用当前固定版本与独立 Pod 环境。预检真实 Node Pod mountinfo：根挂载为 private、JuiceFS 为 slave/HostToContainer，无向宿主传播的 shared 祖先。Kind 中 /home/akernel/variants/tapfix 对应 Node Pod 中 /home/akernel，不能混用。

公共 SDK 创建配置 2 GiB 的源沙箱，512 MiB 内存和 1 MiB 根文件；保存一个已知成功快照，再修改未保存状态。只在源 Node Pod 内，以本任务可写 XFS 目录 bind 遮住 /mnt/akernel-shared，保留底层 FUSE 挂载与已打开句柄。替代目录预建完整 artifacts/manifests 树并验证可写，排除仅因路径不存在而被拒绝的假通过。

独立 watchdog 根据 namespace、原 mount ID、替代目录 inode/device 校验后，维持 20 秒，再只卸载本任务顶部 bind；不用强制或 lazy 卸载。发起新的唯一名原生 Snapshot 请求，要求在遮挡期间拒绝，没有 Ready 快照或新本地文件。恢复原 mount ID 后，核对源未保存状态，再做新的独立快照。

## 3. 数据
| 运行时 | 遮挡期间请求 | 新 Ready 快照/本地替代文件 | 原挂载 | 源未保存状态 | 恢复后新快照与清理 |
|---|---|---|---|---|---|
| gVisor | 拒绝 | 无 / 无 | 恢复 | 保留 | 通过 |
| Firecracker | 拒绝 | 无 / 无 | 恢复 | 保留 | 通过 |

storage/mount-shadow01/terminal.json 为 rc=0，两组 watchdog 恢复成功。[小型回执](evidence/pr119-juicefs-tapfix-20261023/mount-replacement.json)。全部测试远端执行，源及已知/恢复后快照由 SDK 删除。

## 4. 结论
【实测】即使路径存在、可写且目录结构完整，两个后端均拒绝向本地替代目录发布检查点；原挂载恢复后源状态与新请求正常。

【边界】这是受控挂载替换，不是 FUSE 进程永久死亡、PostgreSQL 故障、断电或存储 HA 验收。没有停止真实 FUSE 客户端或卸载原始共享挂载。

## 5. 建议与改进项
将此类检查保留为发布前置门；新后端不能只检查目录存在。后续仍需按生产故障域验证存储恢复，性能对照另开样本。

## 6. 可复现步骤
```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
S="$N/round-365f797-20261023.clPWh2h0/tap-checksum-fix/storage"
cat "$S/mount-shadow01-launch-receipt.json"
cat "$S/mount-shadow01/terminal.json"
cat "$N/acceptance/runs/shared-mount-shadow01-runsc/terminal.json"
cat "$N/acceptance/runs/shared-mount-shadow01-firecracker/terminal.json"
```
脚本为 shadow-owned-shared-mount01.py、sdk-mount-shadow01.py、run-mount-shadow01.py。复测使用新的私有目录并重新核对传播属性；不能将旧 mount ID 或 PID 用于新现场。

## 7. 现场清理披露
两组均已移除本任务顶部 bind，并确认回到原 JuiceFS mount ID。SDK 资源已删除；任务私有脚本、替代目录及日志留存，未动旧环境、共享服务或宿主挂载。没有新增产品提交、构建、模板或父仓组件指针变化。
