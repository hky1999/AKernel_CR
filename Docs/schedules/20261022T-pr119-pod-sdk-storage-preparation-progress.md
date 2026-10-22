# PR #119 SDK 工具及 JuiceFS 离线配置准备进度

## 开发内容

inotify 宿主参数变更仍待确认，三个任务 Kind 容器保持停止。继续完成不需要集群启动的真实准备工作，不把渲染或 CLI 帮助当作 SDK 验收。编译测试没有在本地执行。

## 修改内容

- `tools/pr119-pod-20261022/prepare_storage.py::main`：校验固定 Rook 包 SHA，生成小容量隔离配置，远端离线渲染并检查 CSI 禁用、设备发现禁用、原始 Block PVC 和控制节点放置；不安装服务、不分配设备。
- `tools/pr119-pod-20261022/storage_placement.py::place`：给 Ceph、PostgreSQL、格式化 Job 补本任务控制节点的调度容忍项，不修改原 PR 模板。
- `tools/pr119-pod-20261022/{acceptance.py,guest_probe.go}`：复用已有通用 SDK 与状态探针源码快照；远端二进制复用并记录摘要，二进制不入库。
- 更新 `VERSION.md` 及归一化证据；原 PR、组件 gitlink、镜像没有改变。

## 测试结果

- 远端 SDK CLI 帮助预检返回 0；支持两种运行时，但未发起 Sandbox 请求。
- 远端存储离线准备返回 0；Rook 59 对象、JuiceFS 9 对象；未生成 CSI 驱动工作负载，自动设备发现禁用，Block PVC 要求保留。
- 三个 Kind 容器仍 Exited，inotify 上限 128；XFS 可用约 833 GiB，未清理旧环境。
- 三条完整 SDK 链路仍未通过，没有本轮性能结果。静态配置检查不能证明 Ceph、JuiceFS 或跨节点恢复已运行。

## 可复现步骤

命令、版本摘要、失败保留与后续验收边界见 `Docs/checks/20261022T-pr119-pod-sdk-storage-preparation.md`；集群恢复门禁见 `Docs/checks/20261022T-pr119-pod-inotify-startup-blocker.md`。
