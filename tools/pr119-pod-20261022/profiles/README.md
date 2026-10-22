# 独立 Pod 测试配置参考

这些文件来自 PR #119 固定版本在独立 BareMetal 实验中的实际配置，不包含凭据。它们不是生产配置，也不是可直接套用到任意机器的一键安装包。

- `kind-reference.yaml`：一个控制节点、两个执行节点；Kind 节点是容器，不是基础设施虚拟机。控制面、数据盘目录和缓存相互隔离，但三节点仍共享同一物理宿主机与内核。
- `local-values.yaml`：固定本任务镜像、普通目录模式的本地 XFS filestore、运行时和资源限制；TLS 使用私有 Secret 引用，不提供私钥或 API key。
- `control-placement.py`：把 ADX 控制组件放到控制节点，避免停止执行节点时误停控制面。
- `calico-installation.yaml`、`calico-apiserver.yaml`：固定实验采用的原生 nftables、BGP、不封装的 CNI 配置；它们不包含 Calico 的 CRD 或 operator 安装文件。

## 使用前必须重新生成的值

`@TASK_ROOT@` 必须替换为新建的独立任务目录。`@KUBE_RESERVED_MEMORY_BYTES@` 和 `@KUBE_RESERVED_STORAGE_BYTES@` 必须按当前宿主容量、节点 cgroup 限额及目标可调度容量重新计算。本次实测值分别为 `192630583296` 和 `1321115058176`，它们是该宿主机专用的容量扣除量，不是每节点实际消耗，不能照搬到小机器。

已有 helper 中的 Kind 容器 ID、PID、启动时钟、文件摘要等是所有权保护凭证。新环境须使用自己的实际凭证，不能绕过保护或把旧 ID 当成固定配置。构建、部署和测试都应在远端独立环境执行。

共享存储配置仍从固定 AKernel 提交中的 `deploy/shared-storage/juicefs-values.yaml` 和本目录上一级的 `prepare_storage.py` 生成；不能只改挂载目录、留下 ADX 的旧本地 checkpoint 策略。

旧失败目录需保留。私钥、SDK 环境文件、kubeconfig、JuiceFS 带凭据的状态输出和原始 sandboxd 调试日志不得提交。清理时先退出本任务读者和块设备使用者，再回收本任务设备，不得全局 prune。
