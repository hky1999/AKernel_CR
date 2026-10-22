# PR #119：独立集群恢复与两种运行时的本地 SDK 基础验收

## 1. 问题

用户允许临时将 `fs.inotify.max_user_instances` 调至 1024，不持久化、不重启共享服务；要求恢复独立集群，先确认 etcd/API Server，再完成 runsc、Firecracker、JuiceFS 双节点完整 SDK 验收。全部编译测试在远端，最终交付中文复现材料并推送。

本篇只记录已经取得的集群恢复和本地基础 SDK 结果，以及存储部署失败及处理。不是全部交接用例完成报告。

## 2. 方法

【实测】BareMetal 上原任务的一个控制节点、两个执行节点均是 Kind 容器，没有新增测试虚拟机。任务外层 cgroup 为 12 CPU/40 GiB，每节点容器 4 CPU/10 GiB；Sandbox 测试规格 1 vCPU/2 GiB。Firecracker 自身启动 microVM 是被测试运行时，不是另建一套虚拟机测试基础设施。

固定 AKernel `6ea004125eb4365ba06ba3c7b21c4fd80e4cdaac`、sandboxd `d5acc3b5b673074e20fd8b7733d4035dbaeae1b0`、ADX `59fa7912f875832c8ab053148ae8fd17b7c25a23`；公共 SDK `0.2.0rc3`、原生 SDK `0.1.0rc2`。镜像配置 SHA-256 为 `d1316b767b570f12a2eb5156fd0af80dfbcd783a9ba853a308fe872a4394dee0`。未更换源码、镜像或 guest initrd。

SDK 经私有 namespace 内的端口转发连接真实 ADX Ingress/API Server，TLS 验证成功，协议 TLS 1.3。token 与 SDK 环境文件仅在远端权限受控目录，没有关闭证书验证。

【源码】状态探针 `guest_probe.go::memoryState.snapshot` 每次对整个 `data` 重新计算 `sha256.Sum256`，不是返回缓存摘要；同时读取原进程持有的打开文件。`ServeHTTP` 在 checkpoint 后修改每个 4 KiB 页以及该文件。`acceptance.py::same_state` 核对 PID、随机进程身份、内存大小、全量摘要、打开文件内容，排除“新建进程恰好文件相同”的假通过。

## 3. 数据与证据链

### 3.1 集群恢复

- 变更前 inotify 实例上限 128，变更后 1024；watches 1048576、queue 16384 均不变。没有写 sysctl 持久化文件。
- 原三个容器恢复返回 0，没有删除或重建 etcd 数据。API `/readyz?verbose` 全项通过，含 etcd/etcd-readiness；独立 `etcdctl endpoint health` 为 true。etcd 3.6.6，raftIndex 与 appliedIndex 均为 14021。
- 健康检查之后才解除执行 DaemonSet 暂停；两个执行 Pod rollout 返回 0，sandboxd、adx 两个 systemd 服务均 active，两个必要 socket 可用。
- Calico 四项状态 Available=true、Degraded=false。私有 SDK TLS 握手成功后才发起 Sandbox 请求。

### 3.2 本地 SDK 与计时

两种运行时均通过：首轮 smoke 1 次、5 轮覆盖及 8 个非法参数、完整 512 MiB 工作集 1 次。每轮 checkpoint 返回 HTTP 200/`completed`，源实例继续运行；随后写入新状态、reload，确认回滚、逻辑 ID 和 SDK facade 不变。共 14 次成功 checkpoint/reload，均有测试沙箱删除记录。

下表的“checkpoint 总耗时”是**沙箱内请求开始到 HTTP 完成**，包含后端捕获和元数据提交，不是单独的 guest 停顿。存储为各节点本地 XFS，尚未接 JuiceFS。未清空共享宿主 page cache，没有宣称冷缓存。

| 场景 | 样本 | checkpoint 总耗时 | SDK reload 返回 | reload 到文件回滚确认 | reload 到完整内存校验 |
|---|---|---:|---:|---:|---:|
| runsc，未额外填充工作集 | 5 轮 P50 | 64 ms | 243.450 ms | 286.158 ms | 不适用 |
| Firecracker，未额外填充工作集 | 5 轮 P50 | 2590 ms | 2655.709 ms | 2700.594 ms | 不适用 |
| runsc，512 MiB 全量内存校验 | 1 次，不称 P50 | 729 ms | 1014.590 ms | 1057.441 ms | 2752.881 ms |
| Firecracker，512 MiB 全量内存校验 | 1 次，不称 P50 | 2668 ms | 2681.094 ms | 2725.392 ms | 4619.319 ms |

“未额外填充工作集”不等于 guest 没有内存，更不等于 2 GiB 脏页；两种运行时的内部捕获策略不同。不能把这些数据直接并入旧的 512 MiB/64 MiB 脏页窗口、公开竞品冷启动或暂停时间矩阵。

远端原始数据：`acceptance/runs/{runsc-smoke19,runsc-five20,runsc-memory20,fc-smoke20,fc-five21,fc-memory21}/`。每组保留 `worker.json`、`terminal.json`、events 和 stdout/stderr。SDK 与状态探针源码/二进制摘要见前篇准备检查，未改探针二进制。

### 3.3 JuiceFS 部署尚未通过

- 在任务目录预分配 40 GiB 文件，绑定专用 loop；核对映射归属、块设备类型和容量 42949672960 字节后，创建本任务两个静态 PV。文件系统 PV 的 4 GiB 是调度容量，不是硬磁盘 quota。操作后 XFS 可用 851877122048 字节，约 793 GiB。
- Rook chart 1.21.0 安装返回 0，PostgreSQL、Ceph monitor/mgr 启动；首次 JuiceFS Helm 等待返回 1，完整终态记录为 `storage/install22/terminal.json`，没有把超时当作已部署成功。
- OSD 卷映射时 kubelet 调用 `losetup` 失败；直接诊断明确返回私有 Kind 节点 `/dev/loop148` 为 lost。仅在该容器私有 `/dev` 创建对应节点，未修改宿主设备节点。Kubernetes 的原始块映射会使用 loop 取得文件描述符锁，见固定 [v1.35.8 VolumePathHandler 源码](https://github.com/kubernetes/kubernetes/blob/v1.35.8/pkg/volume/util/volumepathhandler/volume_path_handler_linux.go)。
- 禁用 CSI 安装后，Rook 的 ClientProfile 缓存因缺少 API 定义而启动失败。已从固定包仅创建 6 个 CRD，未安装 CSI operator、Driver 工作负载或加载新模块。初轮 OSD 失败任务、现有卷和数据保留，不清空重造来掩盖失败。

## 4. 结论

【实测】授权后的集群恢复成功，runsc/Firecracker 的公共 SDK 基础 checkpoint/reload、5 轮覆盖和完整 512 MiB 内存校验已跑通。这个结论覆盖 SDK/API/ADX/sandboxd/真实运行时，不是独立后端探针。

【未完成】JuiceFS 真实挂载、共享后端数据与源节点失联恢复未通过，不能称三条链路全部完成。以下交接清单仍需补齐：合法空正文/边界、同沙箱 4 请求实际重叠与捕获次数、多沙箱并发、期限故障、客户端断开、存储失败、adxlet 重启、共享恢复点与执行引用回收。

【边界】本轮没有性能优化代码变更，也没有新旧版本交替对照；这些是固定 PR 的复现基线。测试集群仍只在一台物理机，不能宣布跨物理机、存储 HA 或超过 AgentEnv/E2B/Cube。

## 5. 建议与改进项

1. 先完成 OSD/RGW、PostgreSQL 持久化选项和三客户端真实 FUSE 挂载/读写检查；修复本任务部署缺项，不关闭持久化、隔离或证书校验。
2. 之后接入 PR 的 distributed_fs 配置，运行文件保持节点本地；不能照搬旧文档把私有 filestore 移到 JuiceFS，也不能以同名本地目录代替真实挂载。
3. 跨节点用例不硬绑定 node_id；checkpoint 后隔离源节点，只操作任务资源，记录权威分配节点改变、同一逻辑 ID、内存/私有文件回滚和最终引用回收。
4. 完整交接故障矩阵完成后，再形成最终复现总结；当前仅发布进度和可重复使用的实验脚本。

## 6. 可复现步骤

命令在远端已有独立任务执行，`TASK_ROOT` 不是共享服务目录。SDK 凭据由 `prepare_sdk.py` 写入私有目录，不能提交或打印该文件。

```bash
export TASK_ROOT=/path/to/your/private/pr119-task
# 先按本篇和阻塞检查执行获准的临时配额变更、集群恢复及 etcd/API 健康门禁。
python3 tools/pr119-pod-20261022/prepare_sdk.py --task "$TASK_ROOT"

# 每组输出目录必须是新名字，避免覆盖失败记录。
python3 tools/pr119-pod-20261022/run_sdk_recorded.py \
  --task "$TASK_ROOT" --auth "$TASK_ROOT/acceptance/auth19" \
  --job "$TASK_ROOT/acceptance/runs/runsc-new-five" --runtime runsc --rounds 5 --parameters
python3 tools/pr119-pod-20261022/run_sdk_recorded.py \
  --task "$TASK_ROOT" --auth "$TASK_ROOT/acceptance/auth19" \
  --job "$TASK_ROOT/acceptance/runs/runsc-new-memory" --runtime runsc --memory-bytes 536870912
# Firecracker 对照仅将 --runtime 改为 firecracker，另用新目录。
```

存储准备脚本依次为 `prepare_storage.py`、`prepare_block_pvs.py`、`install_storage_recorded.py`；诊断补齐脚本为 `repair_private_loop_node.py`、`install_csi_schema_only.py`。前篇记录固定输入与 SHA。脚本包含本轮任务所有权常量，另轮实验必须同步调整并核对任务、节点和 PV 标识，不允许用同名路径猜测他人资源归属。

## 7. 现场清理披露

- 全部本地 SDK 测试沙箱已有删除成功事件；没有以删除 Pod 冒充 API 正常回收。共享目录与物理 S3 GC 尚未验收。
- 任务 Kubernetes、私有端口转发和存储服务继续保留用于后续验收。inotify 1024 为临时值；集群运行时不提前恢复 128，最终退场时需核对当前值、资源释放和其他使用者后再处理。
- 新增一个任务 loop 文件及静态卷；只补 Kind 内的设备文件，没有格式化其他宿主盘、清理旧编译产物、重启共享 daemon 或全局 prune。
- 首轮 JuiceFS Helm 超时是真实失败；原始 stdout/stderr、失败 Job、设备诊断和 CRD 记录保留。未将“等待进程退出”或 Helm 状态作为恢复正确性的替代。
- 编译测试全部远端；父仓只加入源码脚本、脱敏证据与中文文档，不加入镜像、二进制、源码 tar 包或凭据。
