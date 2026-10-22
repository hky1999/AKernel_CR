# PR #119 执行 Pod 启动失败：inotify 配额归因与现场暂停

## 1. 问题

继续受控网络模块变更后的独立集群部署与 runsc、Firecracker、JuiceFS 双节点验收时，两个执行 Pod 立即退出，表面错误为 PostStartHookError。需要确认实际阻塞，且不能为继续实验静默调整新的宿主全局参数。

## 2. 方法

【实测】沿用前篇固定的 PR #119 `6ea004125eb4365ba06ba3c7b21c4fd80e4cdaac` 镜像，未修改业务源码或重建二进制。先读取实际 bootstrap、CRI 参数及状态；再在本任务 namespace 创建一次性诊断 Pod，使用同一镜像、相同 privileged 属性，直接以 systemd PID 1 启动，目标为 emergency.target，启用控制台 debug 日志，不启动 sandboxd/ADX。

【实测】读取宿主 inotify 参数，用 `inotify_init1` 测试新建监听器，扫描 `/proc/*/fd` 的 inotify 文件描述符，并依次暂停本任务的失败执行 Pod、停止本任务三个 Kind 容器，再次测试。未改宿主参数，未操作他人服务。

inotify 是 Linux 文件/目录事件通知机制，systemd 和 Kubernetes 等进程也用它监听内核对象。`max_user_instances` 限制每个用户可创建的监听器实例数量；它不同于文件系统容量、文件描述符上限和 `max_user_watches`。

## 3. 数据与证据链

| 证据 | 实测结果与含义 |
|---|---|
| systemd 早期日志 | `Failed to create control group inotify object: Too many open files`，随后分配 manager 失败、PID 1 退出 255；尚未启动 sandboxd |
| 实际进程参数 | 只有 `/usr/local/bin/akernel-entrypoint`，没有被追加 `/bin/bash`；排除先前默认 CMD 的猜测 |
| 宿主参数 | `fs.inotify.max_user_instances=128`；`max_user_watches=1048576`；`max_queued_events=16384`，均未修改 |
| 宿主直接探针 | 新建 inotify 返回 errno 24 / EMFILE |
| 文件描述符扫描 | 0.084 秒扫描 8902 个 FD；UID 0 可见 inotify FD 129 个，其中本任务 94 个。这是 FD 数，可能包含共享/继承引用，不冒充去重后的实例总数 |
| 仅暂停执行 Pod 后 | DaemonSet desired/current/ready 为 0/0/0，诊断 Pod 已删除；宿主探针仍失败；探针自身仅 5 个打开文件，RLIMIT_NOFILE 为 65535，排除探针自身 FD 耗尽 |
| 停止三个任务 Kind 容器后 | 停止返回 0；宿主 inotify 探针成功；上限仍是 128，直接证明释放本任务资源可消除此刻的宿主阻塞 |
| 停止过程 | 控制节点超过 30 秒未响应停止信号，被 Podman SIGKILL；必须披露，不写成全程优雅退出 |

原始证据在远端本任务 `cluster/diag14/`：`init-diagnostic.log`、`inotify-host-diagnosis.json`、`pause-and-host-probe.json`、`cluster-pause-identity.json`、`cluster-paused-for-inotify.json`。公开材料仅保留归一化数字，不包含进程命令行、主机地址、凭据或 kubeconfig。

## 4. 结论

【实测】本轮执行 Pod 的第一个实际启动阻塞是共享 root 用户的 inotify 实例配额压力。不是“磁盘文件太多”，也不能从 PostStartHookError 推断 DNS 脚本错误。仅暂停两个失败执行 Pod 不足以释放压力，停止整个本任务集群后宿主探针恢复。

【实测】当前三个 Kind 容器均停止、数据保留，未删除集群。停止前三个 Kubernetes 节点和跨节点网络策略的通过结论保留为历史结果；不能说集群当前 Ready。runsc、Firecracker、JuiceFS 双节点完整 SDK checkpoint/reload 仍未通过，没有性能数据。

【边界】配额问题解除后可能出现后续配置或运行时问题；不能把首个阻塞定位等同于 PR 全链路已验证。未检查他人应用层健康，不宣称配额耗尽期间对其他工作零影响。

## 5. 建议与改进项

1. 等待用户确认新的共享宿主变更：临时将 `fs.inotify.max_user_instances` 从 128 提到 1024。此操作不重启服务，不写 sysctl 持久化文件，不改变 watches 或队列上限；本轮尚未执行。它提高可用资源上限，不预分配 1024 个监听器，但会扩大该用户可消耗资源的上界。
2. 获准后核对当前值是否仍为 128；若被他人改动，先对齐，不覆盖并发修改。恢复本任务三个容器后，先确认 etcd、API Server、节点与 CNI，再恢复执行 DaemonSet。
3. 实验结束仅在本任务资源已回收、确认不会影响其他并发使用者且当前值仍是本任务所设值后考虑恢复参数，不能盲目改回旧值。
4. 将“新建 inotify 是否成功”和配额余量纳入共享宿主启动预检；仅检查 CPU、内存、磁盘、KVM 不足以保证大量嵌套容器能启动。

## 6. 可复现步骤

以下只读探针在远端执行，不创建文件，也不修改配置：

```bash
sysctl fs.inotify.max_user_instances fs.inotify.max_user_watches fs.inotify.max_queued_events
python3 - <<'PY'
import ctypes, os, pathlib, resource
libc = ctypes.CDLL(None, use_errno=True)
fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
print({"success": fd >= 0, "errno": ctypes.get_errno() if fd < 0 else 0,
       "nofile": resource.getrlimit(resource.RLIMIT_NOFILE),
       "open_fds": len(list(pathlib.Path('/proc/self/fd').iterdir()))})
if fd >= 0:
    os.close(fd)
PY
```

以下为**待授权后的恢复命令**，本轮没有执行：

```bash
# 管理员确认当前值和变更范围后才执行；不写 /etc/sysctl*。
sysctl -w fs.inotify.max_user_instances=1024

export TASK_ROOT=/path/to/your/private/pr119-task
export LAB="$TASK_ROOT/cluster/namespace-lab07.py"
python3 "$LAB" run --task "$TASK_ROOT" -- podman start \
  akcr119-20261022-control-plane akcr119-20261022-worker akcr119-20261022-worker2
python3 "$LAB" run --task "$TASK_ROOT" -- kubectl get --raw='/readyz?verbose'
python3 "$LAB" run --task "$TASK_ROOT" -- kubectl wait --for=condition=Ready nodes --all --timeout=180s
python3 "$LAB" run --task "$TASK_ROOT" -- kubectl get tigerastatus

# 先确认这个 selector 的值仍是 await-inotify-authorization，再仅移除该任务暂停键。
python3 "$LAB" run --task "$TASK_ROOT" -- kubectl -n akernel get ds akernel-node \
  -o 'jsonpath={.spec.template.spec.nodeSelector}'
python3 "$LAB" run --task "$TASK_ROOT" -- kubectl -n akernel patch ds akernel-node --type=json \
  -p='[{"op":"remove","path":"/spec/template/spec/nodeSelector/akernel-pr119-acceptance"}]'
python3 "$LAB" run --task "$TASK_ROOT" -- kubectl -n akernel rollout status ds/akernel-node --timeout=180s
```

任务名称与 helper 路径为本轮现场，另建实验需更换任务标识，不能拿这些命令操作别人的集群。API Server readyz 必须包含 etcd 健康；如恢复失败，保留 WAL/日志，不删除数据重建来掩盖不干净停止。

## 7. 现场清理披露

- 诊断 Pod 已删除；执行 DaemonSet 通过本任务专用、无匹配节点的 selector 暂停。原始 DaemonSet JSON 和暂停 patch 均保留。
- 停止前核对三个 Kind 容器的 cluster label 和物理宿主 cgroup 归属；只停止本任务三个容器，没有停止其他人的 daemon、沙箱或容器。
- 控制节点停止超时被强制终止，etcd 数据仍保留，尚未重启或验完整性。其他两节点由同一次 Podman stop 处理；未执行容器删除或存储清理。
- 任务 namespace keeper、slirp 和磁盘现场保留，方便授权后恢复；没有卸载已获授权的网络模块，没有改全局 sysctl。
- 本任务确实导致共享 root 监听器资源压力；停止本任务集群后宿主探针恢复。未把该问题归为他人环境错误，也未声明期间零影响。
