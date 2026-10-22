# PR #119 独立 Pod 集群与网络验证进度

## 开发内容

用户授权必要网络模块后，继续 BareMetal 独立 Pod 路线。不新增测试虚拟机，不使用旧环境的控制面或存储，不在本地编译测试。目标仍为 runsc、Firecracker、JuiceFS 双节点的公共 SDK checkpoint/reload；本轮只完成其集群及网络前置条件，执行 Pod 启动仍受阻。

## 修改内容

- `tools/pr119-pod-20261022/prepare_tools.py`：固定版本和摘要下载 Kind、Helm、kubectl；兼容 Kind 版本输出中的 `v` 前缀差异。
- `tools/pr119-pod-20261022/namespace_lab.py`：任务私有 namespace、Podman、cgroup 和命令入口；外层 12 CPU / 40 GiB，每节点 4 CPU / 10 GiB，不使用共享图存储。
- `tools/pr119-pod-20261022/create_kind_recorded.sh`：独立后台创建 Kind，记录进程身份、真实退出码与终态，避免把 SSH 观察断开等同于创建失败。
- `tools/pr119-pod-20261022/network_policy_probe.py`：跨节点 HTTP 允许/拒绝/撤销验证，修正内联 shell 引号问题后通过；探针资源已回收。
- 远端私有配置：Kind 三节点与调度预算、Calico 原生 nftables、AKernel 小容量 profile、控制面节点放置；只解包私有 aardvark-dns，未全局安装。
- 原 PR 业务源码未修改。父仓 `VERSION.md` 已记录实验版本及真实阻塞；未把未验收实验替换为交付 submodule 指针。

## 测试结果

| 项目 | 结果 |
|---|---|
| 固定源码远端镜像构建、导出、导入 | 返回 0；镜像摘要与运行时配置身份已记录 |
| Kubernetes 注册与资源预算 | 三节点 Ready；4 CPU / 8092 MiB / 29 GiB 临时存储每节点；实际 cgroup 祖先限额已核对 |
| Calico 与网络访问控制 | 组件 Available；跨节点策略六项断言通过，探针资源已回收 |
| Helm 安装 | 返回 0，但不代表执行节点或功能可用 |
| AKernel 运行 | 三个控制面 Pod 正常；两个执行 Pod 启动退出 255，根因待确认 |
| runsc / Firecracker / JuiceFS 双节点完整 SDK | 均未通过；尚无本轮性能数据，JuiceFS 存储尚未部署 |

## 可复现步骤

源码、镜像、网络模块、命令入口及失败诊断步骤见 `Docs/checks/20261022T-pr119-pod-cluster-network-and-node-startup.md`。构建/SDK 安装见前次 `Docs/checks/20261022T-pr119-pod-build-sdk-command-appendix.md`。

下一步先获取 systemd 早期启动日志、恢复两个执行 Pod，再按 runsc、Firecracker、JuiceFS 双节点的顺序完成 SDK 验收。完整中文操作手册与性能结论尚未完成，不提前宣称交付。
