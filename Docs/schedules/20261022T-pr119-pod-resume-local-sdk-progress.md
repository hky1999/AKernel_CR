# PR #119 集群恢复及本地 SDK 基础链路进度

## 开发内容

用户授权临时提高 inotify 上限后恢复独立 Pod 集群；先验证 etcd/API Server，再执行真实公共 SDK 测试。全部运行在 BareMetal，不增加测试虚拟机、不改共享服务。

## 修改内容

- `prepare_sdk.py::main`：读取私有凭据、建立任务端口转发并验证 TLS；不输出 token。
- `run_sdk_recorded.py::main`：记录实际 SDK 子进程、真实退出码与单独输出目录，避免 SSH 断开丢失终态。
- `prepare_block_pvs.py::main`：只分配任务 40 GiB loop 后端、验证身份容量并创建显式静态 PV；不选其他宿主盘。
- `install_storage_recorded.py::main`：在本地测试结束且清理后启动 Rook/PostgreSQL/JuiceFS，逐步记录终态；首轮 JuiceFS 等待失败如实保留。
- `repair_private_loop_node.py::main`：仅在 Kind 私有 `/dev` 补 `losetup` 报 lost 的节点。
- `install_csi_schema_only.py::main`：仅从固定 chart 安装 Rook 需要的 6 个 CSI API 定义，不启动驱动。
- 更新 `VERSION.md`、检查文档和归一化证据；未修改运行时源码、镜像或 submodule 指针。

## 测试结果

- 临时 inotify 128→1024，其他参数不变；API readyz、etcd health/status、三节点 Ready、执行 DaemonSet 和 TLS 通过。
- runsc/Firecracker 各 7 次 checkpoint/reload 通过，含 5 轮覆盖、8 个非法参数和完整 512 MiB 内存/PID/随机身份/打开文件内容校验；测试沙箱删除成功。
- 5 轮未额外填内存的 checkpoint 请求总耗时 P50 为 runsc 64 ms、Firecracker 2590 ms。不是 guest 停顿或竞品比较；完整时序、单样本内存数据和规格见检查。
- JuiceFS 完整链路未通过，存储部署仍在处理 OSD/控制器依赖；并发和故障注入矩阵也未全部完成，不宣布最终交付。

## 可复现步骤

见 `Docs/checks/20261022T-pr119-pod-resume-local-sdk-acceptance.md`。原始证据保留任务的 `cluster/resume18/`、`acceptance/runs/`、`storage/`。本轮脚本和文档发布到独立实验分支，不混入已验收主线。
