# PR #119：集群暂停期间的 SDK 工具及 JuiceFS 部署前检查

## 1. 问题

继续完成 Pod 方案的 runsc、Firecracker、JuiceFS 双节点 checkpoint/reload。宿主 inotify 配额变更仍待确认，不能擅自恢复会再次耗尽共享配额的集群；先完成不依赖集群运行的验收工具准备和存储配置检查。

## 2. 方法

【实测】通过任务私有 Podman 查询三个 Kind 容器，读取宿主参数与磁盘容量；不启动容器。将已有验收工具复制到远端独立任务，使用已安装的公共 SDK `0.2.0rc3` / 原生 SDK `0.1.0rc2` 运行 CLI 帮助预检，不创建 Sandbox。

【源码】读取固定 AKernel `6ea004125eb4365ba06ba3c7b21c4fd80e4cdaac` 的 `deploy/shared-storage/charts/juicefs/templates/{ceph,clients,format,postgres}.yaml`。核对固定 Rook chart `1.21.0` 的配置模板，然后在远端执行 `helm template --include-crds` 和对象断言；没有 `helm install` 或 `kubectl apply`。

新增脚本只在任务目录写配置和检查记录；不修改共享服务，不分配块设备，不执行 sysctl。存储接口 CSI 指 Kubernetes 的存储驱动接口；本实验仅需要 Ceph 的 S3 对象接口，不需要 RBD/CephFS CSI 驱动。

## 3. 数据与证据

| 检查 | 本轮结果 |
|---|---|
| 实际集群状态 | 三个本任务 Kind 容器 Exited；没有恢复集群 |
| 宿主参数 | `fs.inotify.max_user_instances=128`，未变更 |
| XFS 空间 | 采样可用 `894866792448` 字节，约 833 GiB，占用 34%；未清理旧产物 |
| SDK 脚本 | `acceptance.py --help` 返回 0，支持 `runsc`、`firecracker`、轮数、参数检查、内存大小及初始节点选择；不是 API 验收 |
| Rook 包 | chart `1.21.0`，SHA-256 `c070c7985deee72d7620e0377c07ce2afba28f566fbefe47bf934d00a5692cde` |
| Rook 渲染 | 59 对象；工作负载只有 `Deployment/rook-ceph-operator`；CSI operator 安装关闭，配置中 `ROOK_CREATE_CSI_OPERATOR_RESOURCES=false` |
| 设备发现 | `ROOK_ENABLE_DISCOVERY_DAEMON=false`；CephCluster 的 `useAllDevices=false`、`useAllNodes=false` |
| JuiceFS 渲染 | 9 对象；单 OSD、单 monitor、单 RGW，复制数 1；只用于非高可用功能实验 |
| 卷配置 | Ceph monitor 为 4 GiB 文件系统卷，OSD 为 40 GiB 原始 Block 卷；PostgreSQL 使用独立 4 GiB 文件系统卷及已命名 Secret 引用 |
| 实际创建 | 块设备、PV、存储服务、JuiceFS 挂载均为 0；Sandbox 请求数 0 |

SDK 材料的 SHA-256：

```text
acceptance.py  ce9b8cd994eb9b297239007d545002eb99a8e0e45976231cb1860b5717f2252b
guest_probe.go 14ab534bfa8527f0bb2986f156c1121fee8578dba9d964083b7b868355b29792
guest-probe    8779ebeb60652c8552710fa7246506c0846a5421fe50bd3b4ab1619a0f1a7b91
```

二进制 `guest-probe` 复用前一独立实验的通用状态探针，不是 Firecracker guest agent，不替换 PR 固定 initrd。二进制不入 Git；发布源码快照，不把它标成新编译或本轮 SDK 验收产物。

【源码】固定 Rook `templates/configmap.yaml` 使用 `csi.createCsiOperatorResources`，chart 依赖条件使用 `csi.installCsiOperator`；不能沿用旧版本 `enableRbdDriver` 一类配置并假设有效。本轮同时检查最终渲染结果，避免 Helm 静默忽略不存在的值。

【源码】JuiceFS 模板 `ceph.yaml` 明确要求 OSD `volumeMode: Block`，monitor 和 PostgreSQL 则是文件系统 PVC。`clients.yaml` 在节点上创建独立 FUSE 挂载并使用 OnDelete 更新。`format.yaml` 仅首次格式化、使用 S3 后端，未开启 writeback；`postgres.yaml` 保留 `fsync=on`、`synchronous_commit=on`、`full_page_writes=on`。本轮不改这些持久化语义。

## 4. 结论

【实测】SDK 工具已就位，固定存储模板可以在本任务的小容量、控制节点放置配置下离线渲染；不需要为完成这些准备工作修改宿主参数。

【边界】离线模板正确不证明块设备可用、数据库/对象数据持久化、FUSE 跨客户端一致性或运行时没有加载额外模块。三条完整 SDK checkpoint/reload 仍未通过，也没有本轮性能结果。

【源码】公共 Python SDK `Sandbox.reload()` 的接口说明是回滚到最近的本地匿名 checkpoint。现有探针验证 reload 及状态回滚，不能只凭返回 `True` 声称跨节点恢复。JuiceFS 链路必须额外记录恢复前后实际节点、同一实例身份和完整状态校验，并证明读取共享恢复点。

## 5. 建议与改进项

1. 等待 inotify 临时上限变更确认，恢复集群后先检查上轮强制停止过的控制节点 etcd/API Server，再恢复执行 DaemonSet。
2. 完成 TLS 校验、私有端口转发和 SDK 凭据配置后，执行两种运行时的完整 SDK 创建、checkpoint、reload、文件和内存一致性测试。
3. 为 JuiceFS 创建明确归属本任务的原始 Block PV 和文件系统 PV，不能使用现有未知宿主盘；本实验若使用 loop 后端，仅代表功能验证，不能当成生产 Ceph 磁盘性能。
4. 部署后再核验 CSI 驱动未运行、Ceph 健康、PostgreSQL 持久化、格式化 Job 与三端真实挂载；不能用本轮渲染检查替代。
5. 双节点探针补充源/目标节点身份断言和受控源节点退出场景；同节点 SDK reload 与跨节点自动恢复分别报告。

## 6. 可复现步骤

所有命令在远端执行。`TASK_ROOT` 指已按前篇准备的独立目录；本轮没有启动集群的步骤。

```bash
export TASK_ROOT=/path/to/your/private/pr119-task
python3 "$TASK_ROOT/cluster/namespace-lab07.py" run --task "$TASK_ROOT" -- \
  podman ps -a --filter label=io.x-k8s.kind.cluster=akcr119-20261022
cat /proc/sys/fs/inotify/max_user_instances
df -B1 --output=size,used,avail,pcent /mnt/m0-xfs

# 使用已经安装好的 SDK，只查看帮助，不发起 Sandbox 请求。
"$TASK_ROOT/sdk/client/bin/python" \
  tools/pr119-pod-20261022/acceptance.py --help

# 固定 chart；下载文件实际版本名为 1.21.0（无 v 前缀）。
mkdir -p "$TASK_ROOT/storage/preflight15"
python3 "$TASK_ROOT/cluster/namespace-lab07.py" run --task "$TASK_ROOT" -- \
  helm pull rook-ceph --repo https://charts.rook.io/release \
  --version v1.21.0 --destination "$TASK_ROOT/storage/preflight15"

# 新输出目录必须不存在；脚本校验 chart SHA，不安装任何对象。
python3 tools/pr119-pod-20261022/prepare_storage.py \
  --task "$TASK_ROOT" --output "$TASK_ROOT/storage/preflight-new"
```

需要系统 Python 的 PyYAML；本轮远端原已安装，未进行全局依赖安装。脚本输出 `rook-values.yaml`、`juicefs-values.yaml`、原始/调整后渲染文件和 `receipt.json`。配置引用 Secret 名称，不写密码；原始渲染文件默认仍保留在私有现场，不直接公开。

## 7. 现场清理披露

- 仅新增本任务 `acceptance/`、`storage/preflight15/`、`storage/preflight16/` 及两个准备脚本；没有启动 Pod、分配 loop、格式化卷或清理共享磁盘。
- 第一次存储路径引用错误地使用了 `charts/shared-storage`，查找失败；随后改读实际 `deploy/shared-storage/charts/juicefs`，没有业务环境变更。
- Rook 下载成功后，首次摘要命令误用带 `v` 的文件名；保留已有包并使用实际文件名，没有重复下载或覆盖失败记录。首次猜测旧模板名不存在，随后按包成员读取实际 `templates/configmap.yaml`。
- 一次只读 SSH 在 banner 阶段超时，未进入远端执行；重试读取成功，没有根据超时重启任何服务。
- 集群仍停在上轮保留数据状态，新增全局参数变更尚待确认。未改原 PR 业务源码和运行时产物。
