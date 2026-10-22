# PR #119 Pod 复现准备进度

日期：2026-10-22。状态：**镜像与 SDK 准备完成，宿主共享内核变更待确认，尚未部署。**

## 开发内容

按用户要求改用 Pod 方案，不用额外测试虚拟机；在 BareMetal 建立独立任务输入，先核对当前 PR 版本、Kubernetes 条件和磁盘。不能把旧版本原生环境、构建容器或 SDK 安装，算成本轮 Pod 与 checkpoint/reload 验收。

## 修改内容

- 固定 AKernel PR #119 `6ea004125eb4365ba06ba3c7b21c4fd80e4cdaac` 与其 sandboxd `d5acc3b5b673074e20fd8b7733d4035dbaeae1b0`，保持产品源码未修改。
- 在远端私有 Podman 状态中执行官方 `deploy/scripts/build-image.sh` 两阶段构建，准备完整 runsc 与 Firecracker 载荷并导出 OCI 镜像。
- 安装公共 SDK `0.2.0rc3` 和匹配原生依赖 `0.1.0rc2`，只做依赖与打包检查，没有创建 Sandbox。
- 只读核对最新 sandboxd 的 `newIPTablesBackend`、`ensureBridgeNetfilter` 和 `validatePrerequisites`，确认需要先对齐共享宿主网络模块变更。
- 新增中文预检文档、构建/SDK 命令附录与脱敏汇总；更新版本台账。交付使用独立 GitHub 分支 `repro/pr119-pod-baremetal-20261022`，不推送原父仓内部历史或无关脏文件，不替换已验收子模块指针。

## 测试结果

| 项目 | 结果与适用范围 |
|---|---|
| 远端官方镜像构建 | 两阶段返回码均为 0，合计约 371.7 秒；不是 checkpoint/reload 延迟 |
| 远端镜像静态载荷检查 / OCI 导出 | 返回码均为 0，导出归档约 623 MiB |
| SDK 安装与依赖检查 | 九阶段返回码为 0，`pip check` 通过；实际 SDK Sandbox 请求 0 |
| Kubernetes、Pod、runsc/FC checkpoint/reload | 未执行，不计通过 |
| JuiceFS 双节点恢复、性能与读取量对比 | 未执行，无新增数据 |

只读模块依赖解析通过不表示模块已加载或产品已启动。`br_netfilter`、`ip_set`、`ip_set_hash_ip`、`xt_set`、`xt_conntrack` 尚未具备；没有加载模块、写共享 sysctl/NAT 或关闭访问策略。

磁盘审计：新任务约 7.17 GiB，XFS 当时可用约 844.7 GiB，删除数据 0 字节。只回收一个身份已核对、无进程无子组的本任务空 cgroup，不动旧环境和现有证据。

## 可复现步骤

1. 依 `Docs/checks/20261022T-pr119-pod-baremetal-preflight.md` 执行远端只读依赖与磁盘预检。
2. 依 `Docs/checks/20261022T-pr119-pod-build-sdk-command-appendix.md` 固定源码、构建参数及 SDK；任务专属 shim/监督器仍未通用化，不能当作一键部署脚本。
3. 在共享宿主模块操作获确认前保持停止，不启动可能自动加载模块的集群或 privileged Pod。
4. 确认后先 runsc，再 Firecracker，再 JuiceFS 双逻辑节点验收；保留真实目标节点身份、文件与内存校验及分相耗时。完成动态验收后另写跑通报告，本篇不提前宣告完成。

详细证据与清理披露见本轮预检文档；原件保存在 BareMetal 本任务根，凭据、镜像与运行数据不入 Git。
