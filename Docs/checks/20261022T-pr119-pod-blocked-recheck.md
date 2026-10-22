# PR #119 Pod 实验：inotify 阻塞复查

## 1. 问题

持续目标要求完成 runsc、Firecracker、JuiceFS 双节点 checkpoint/reload，并交付中文复现文档。前两轮已定位宿主监听器配额不足、停止本任务集群并补齐离线材料；本轮确认外部状态是否已变化，判断能否安全恢复。

## 2. 方法

【实测】2026-10-22 06:28:31 UTC（北京时间 14:28:31），远端读取宿主 `fs.inotify.max_user_instances`，创建并立即关闭一个 inotify 探针，经带 PID/namespace 身份校验的私有 helper 查询本任务 Kind 容器状态。没有启动或删除容器。

SDK、镜像与业务源码没有更换，版本仍以 `VERSION.md` 和前两篇检查为准；本轮不做 SDK、性能或存储测试。

## 3. 数据

| 项目 | 本轮直接证据 |
|---|---|
| 宿主实例上限 | 128，未修改 |
| 宿主新建监听器 | 成功，errno 0；说明停掉本任务集群后此刻仍可创建，不证明有足够余量重启整个集群 |
| 实验控制节点 | Exited 137，与上轮停止超时后 SIGKILL 一致 |
| 实验两个执行节点 | 均 Exited 130 |
| 私有状态查询 | 返回 0；未发现本任务节点容器在运行 |
| 完整 SDK 三条链路 | 仍未完成；本轮未启动新的请求或后台验收任务 |

远端记录：本任务 `cluster/diag14/blocked-recheck17.json`。公开记录不包含服务器地址、凭据、kubeconfig 或其他任务进程信息。

## 4. 结论

【实测】外部配额条件没有变化，实验现场保持停止，不能假定上限已获调整或集群已经恢复。

【判断】同一“新增宿主全局参数变更待确认”的阻塞已经连续三轮出现。离线 SDK 工具与存储配置已准备，接下来的完整验收依赖恢复集群；不能继续重复启动并耗尽共享资源，也不能把帮助命令或离线渲染替代 SDK 验收。任务状态已登记 blocked，保留原完整目标。

## 5. 建议与改进项

1. 等待明确确认临时调整 `fs.inotify.max_user_instances` 至 1024；不把自动续跑消息当成对新增宿主参数的确认。
2. 确认后按 inotify 启动阻塞检查中的恢复门禁执行：先核对当前参数，恢复本任务容器，检查 etcd/API Server、节点和网络，再恢复执行 DaemonSet。
3. 完成 runsc、Firecracker SDK 验收及 JuiceFS 真正跨节点状态验证后，才编写最终“跑通”总结。当前阶段文档已经推送，但不是完整交付完成证明。

## 6. 可复现步骤

在远端已有本任务环境执行，不会启动集群：

```bash
export TASK_ROOT=/path/to/your/private/pr119-task
cat /proc/sys/fs/inotify/max_user_instances
python3 "$TASK_ROOT/cluster/namespace-lab07.py" run --task "$TASK_ROOT" -- \
  podman ps -a --filter label=io.x-k8s.kind.cluster=akcr119-20261022 \
  --format '{{.Names}} {{.Status}}'
```

监听器只读诊断及待授权恢复命令见 `Docs/checks/20261022T-pr119-pod-inotify-startup-blocker.md`。本轮没有执行其中的 sysctl 或恢复命令。

## 7. 现场清理披露

没有创建块设备、挂载、Pod、Sandbox 或后台任务，没有改变全局参数或共享服务。探针创建的单个监听器已关闭。保留三个停止容器及原数据；没有重复清理或删除任何旧环境内容。
