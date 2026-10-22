# PR #119 执行 Pod 的 inotify 阻塞定位与现场暂停

## 开发内容

在网络和控制面部署后，定位两个执行 Pod 启动立即退出的问题，并防止实验继续耗尽共享 root 用户的内核事件监听器配额。没有修改业务源码，没有本地编译测试。

## 修改内容

- 远端任务 `cluster/diag14/`：保存原始 DaemonSet、bootstrap 和 CRI 状态；新建一次性 systemd 控制台诊断 Pod，获得 PID 1 真实退出原因，随后删除诊断 Pod。
- 对本任务执行 DaemonSet 增加暂停 selector，desired/current/ready 为 0/0/0；保留恢复所需原始配置。
- 核验任务归属后停止三个本任务 Kind 节点容器，未删除容器、集群数据或其他工作者资源；更新 `VERSION.md` 为“停止保留数据”，不继续报告当前 Ready。
- 新增检查文档 `Docs/checks/20261022T-pr119-pod-inotify-startup-blocker.md`，包含参数边界、只读探针、恢复命令和强制停止披露。

## 测试结果

- systemd 因创建 inotify 失败退出 255。宿主实例上限 128，独立探针 errno 24；探针本身仅 5 个 FD、上限 65535。
- 仅暂停执行 Pod 后探针仍失败；停止本任务三个 Kind 容器后探针成功，宿主参数仍为 128，确认本任务的监听器压力参与了阻塞。
- Podman stop 返回 0，但控制节点超过 30 秒后被 SIGKILL；恢复必须先验 etcd/API Server，不把停止动作写成全程优雅退出。
- 三条完整 SDK checkpoint/reload 尚未通过，JuiceFS 后端尚未部署，没有本轮性能结果。已完成的网络验证为暂停前历史实测。

## 可复现步骤

见上述检查文档第 6 节。本轮未执行建议中的 `sysctl -w fs.inotify.max_user_instances=1024`；这是新增共享宿主参数变更，等待用户确认后才能恢复集群继续验收。
