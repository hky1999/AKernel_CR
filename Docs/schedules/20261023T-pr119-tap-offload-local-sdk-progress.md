# PR #119 网络修复与本地完整 SDK 进度

日期：2026-10-23。定位：完成本地模式门禁，继续准备本任务 JuiceFS 跨节点验收，不代表下一阶段后端对照完成。

## 开发内容

修复 Firecracker 与 gVisor 复用持久 TAP 虚拟网卡后出现的 Execd（沙箱内命令执行服务）就绪超时。保证完整 SDK 在正确的节点可调度前提下验收，不靠重启后碰巧成功、跳过 OCI 镜像或弱化断言关闭问题。

## 修改内容

- 远端独立 sandboxd 源码基于 `d5acc3b`：`pkg/runtime/runsc/network.go::OpenTAP` 增加卸载状态复位；新增 `network_tap_reuse_linux_test.go::TestOpenTAPClearsPersistentChecksumOffload`，覆盖三轮跨模式复用及后续重新启用。
- 构建独立候选镜像 `localhost/akernel-pr119:365f7971f895-tapoffload01`，只替换 sandboxd；ELF SHA-256 `9c74060c3c4edceed6edb746e6b42bdd21116e3663427238fb1dd5067f3c964b`。运行时、Execd、EROFS、initrd 未变。
- 本任务实际部署基线为 `D/virtiofs-enabled01-values.yaml`，运行目录 `/home/akernel/variants/tapfix`；打开已有 virtio-fs 以支持 OCI 只读根，不改变私有 RWFS 的本地 XFS 布局。
- 获批后修复诊断参数、QA 测试子进程 umask，并新增 `D/wait-adx-ready01.py`：验证新会话、可路由、节点可用、容量、当前 Pod/镜像身份，连续三个样本稳定后才执行 SDK。
- 新增 `D/sdk-ready03.py`、`sdk-full03.sh`，固定 OCI 镜像摘要，保留全部中间失败与原配置。没有改调度器、公共 API 或节点标签来绕过失败。
- 源码补丁当前在远端独立 clone，未提交/推送；没有改父仓三个组件指针，也没有混入另一路 upstream rebase 工作。

`N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp`；
`Q=N/round-365f797-20261023.clPWh2h0`；
`D=Q/tap-checksum-fix`。

## 测试结果

| 项目 | 结果与口径 |
|---|---|
| 原镜像单变量诊断 | 只关闭本任务 TAP 的发送校验和卸载，TCP 从超时变为约 0.303 ms 连接成功；SDK 创建/执行成功，开关恢复 |
| 内核回归 | 原代码按目标断言失败，修复后三轮复用通过；不是直接 VM 性能样本 |
| 质量门 | 全仓格式/vet/make test、runsc race、生产参数编译通过；全部远端隔离容器执行 |
| 双节点混合启动 | 每节点 gVisor→Firecracker→gVisor，共 6 次通过，全部删除 |
| 本地官方 SDK | 两种运行时各 integration 8＋standalone 30，共 76 个通过且无跳过，包含固定 OCI 镜像 |
| 额外 checkpoint/reload | 共 12 次通过，含两种运行时各 5 轮连续回滚、各 8 项非法参数、各 1 次 512 MiB 完整内存/PID/打开文件校验；四组删除成功 |
| JuiceFS 跨节点 | 本轮尚未验收；不能套用旧环境数字 |
| 两条存储路线与性能裁决 | 尚未开始 |

本轮本地 XFS、1 vCPU/2 GiB、1 GiB 存储的基础 5 样本 P50：gVisor checkpoint 请求完成 74 ms、SDK reload 245.293 ms；Firecracker 分别 2285 ms、2665.381 ms。不是 guest 停顿或跨节点时间。旧轮对应 77/226.480 ms 和 2448/2696.639 ms，但不是交替对照且配置不同，不据此宣称优化收益。

保留失败：缺测试依赖、QA 的 077 权限影响、一次无 Go PATH 的额外对照、virtio-fs 关闭导致 OCI 被拒，以及未等 ADX 可调度的冷启动超时。它们没有被计成通过或归因于源码新回归。

## 可复现步骤

详见检查文档 `Docs/checks/20261023T-pr119-tap-offload-local-sdk-acceptance.md` 第 6 节。固定源码、镜像、完整官方测试和事件路径均在其中；原始认证和私有配置不入库。

下一步在本任务安装独立 JuiceFS/PostgreSQL/S3 兼容后端，先做真实挂载、同步持久化和跨客户端检查，再在本轮候选与真实 ADX 就绪门之上验收跨节点 SDK。原 `Q/storage/verify-attach.py` 引用旧镜像配置，必须先迁移到本轮配置，不能原样执行并回退网络修复。读者保护与故障矩阵、两条存储路线仍是后续必需工作。
