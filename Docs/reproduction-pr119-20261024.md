# PR #119 固定候选的远端 Pod 复现与验收

日期：2026-10-24。使用中文说明，代码及接口名称保留原样。本轮是 10 月 22 日复现的后续，不替换 10 月 21 日那套独立交付。

## 1. 先选择正确的源码组合

本仓现有五个子模块属于 `delivery/manifest.json` 的历史交付；**复现本文使用单独清单 `delivery/pr119-20261024.json`**。不要只把其中一个子模块升级后与另外四个旧版本混搭。

| 输入 | 本轮固定版本 |
|---|---|
| AKernel PR 候选 | 365f7971f895f2b94cf390eefaab436600f005f0 |
| sandboxd | e3f402c0a18be3ff0b7d90674daae9459464772a；继承 TAP 修复，并修正异步 I/O 的盘/内存切面 |
| 实际 ADX/Execd 发布包 | 6fb53d7331811535b6be5787ba026e03072f427b；不要用 AKernel 源码里的另一个 gitlink 代替 |
| SDK | 从固定 AKernel 源码构建公共 0.2.0rc3，安装固定 ADX 包内原生 0.1.0rc3 |
| runsc | 完整 release-20260817.0-akernel.4 包；实际版本输出 .3-2-g7fdef444b108，所有 sidecar 必须配套 |
| Firecracker | v1.16.1-akernel.3 完整包，guest initrd 从匹配 sandboxd 构建，不复用另一版协议模板 |

在远端新任务目录获取源码；以下是新工作区命令，不应在已有使用者的目录执行：

```bash
ssh BareMetal
set -euo pipefail
umask 077
TASK=$(mktemp -d /mnt/m0-xfs/pr119-reproduce.XXXXXXXX)
export TASK
git init "$TASK/AKernel"
git -C "$TASK/AKernel" remote add origin https://github.com/WenYuLuo/akernel.git
git -C "$TASK/AKernel" fetch --depth=1 origin 365f7971f895f2b94cf390eefaab436600f005f0
git -C "$TASK/AKernel" checkout --detach FETCH_HEAD
git -C "$TASK/AKernel" submodule update --init src/sandboxd
git -C "$TASK/AKernel/src/sandboxd" fetch https://github.com/hky1999/sandboxd.git codex/pr119-fc-drain-order-20261024
git -C "$TASK/AKernel/src/sandboxd" checkout --detach e3f402c0a18be3ff0b7d90674daae9459464772a
git -C "$TASK/AKernel/src/sandboxd" show --stat HEAD
```

源码包含明确的 TAP 修复及盘/内存一致性修复，不声称原始 PR 未修改就通过。源码门、官方 76、双向接管与真实 guest 持续直接 I/O 均通过，见新增修复阶段总结。需要审阅 ADX 实现时，可另取 `openJiuwen-ai/agent-dx` 的 6fb53d7；镜像本轮使用已固定发布包，不要求先另编译 Rust 控制面。

## 2. 构建、环境与存储

基础流程复用 [固定构建命令附录](checks/20261022T-pr119-pod-build-sdk-command-appendix.md) 与 `tools/pr119-pod-20261022/`，但源码 SHA、SDK 包及实际摘要以本清单覆盖。所有构建在远端私有 Podman graph 和受限容器完成；新构建要登记自己的摘要，不要求与历史含时间信息的 wheel/EROFS 位级相同。

使用固定源码的 `deploy/scripts/build-image.sh`，开启 Firecracker、关闭未测的 Kata/runc，保持正式完整运行时 pin。其 builder/node.Dockerfile 与 runtime.Dockerfile 已固定 ADX/Execd 6fb53d7 的下载地址及摘要，不要改成 latest。TAP 修复不更改 guest 协议；SDK 运行时须核验实际镜像和 ELF。单元测试子进程使用通常的 umask 022，外层日志和凭据仍用 077。

新建独立 Kind：一个控制节点容器、两个执行节点容器；AKernel 命名空间长期为两个 Node Pod、Coordinator、入口和 Redis 五个 Pod。运行时沙箱由 Node Pod 内 sandboxd 启动，不是每个沙箱另建 Kubernetes Pod。FC 自身仍是被测 microVM。

采用任务独立 root/socket、cgroup、网段、挂载和凭据。已有 Kubernetes、旧测试集群、宿主模块、inotify、共享服务均先只读检查；脚本不默认授权修改宿主全局设置。磁盘先记录可用量与预算；本轮守卫保留至少 650 GiB，外部环境应按其容量另定明确低水位，不能全局 prune 或清其他人的数据。

共享存储使用 AKernel 固定源码已有 `deploy/shared-storage/` 路线：PostgreSQL 管 JuiceFS 文件元数据，Ceph RGW 提供 S3 文件数据，ADX 的 Redis 管实例与引用。实际本轮为单 MON/OSD/数据副本、任务专属 40 GiB 文件块设备，属于功能环境，不是生产 HA。复用既有工具前必须替换任务设备身份，不允许自动发现/格式化任意磁盘。

关键配置与门禁：

- 每节点独立真实 JuiceFS 挂载；1 MiB 数据块、4 GiB 客户端缓存、无压缩、writeback=false；PG 的 fsync/synchronous_commit/full_page_writes 实际查询为 on。
- 运行态 filestore 为本地 XFS 普通目录，filestore_dir_size 留空，避免额外 loop/ext4。checkpoint 为真实 JuiceFS 路径。
- `checkpoint_sync.sync_output=true`，gVisor `background_restore=true`；FC 默认 Full、Async/Writeback。OCI 官方用例需 `virtiofs_enabled=true` 和匹配 virtiofsd；不是将私有盘迁入 virtio-fs。
- CoreDNS 与存储控制组件位于故障时不会一起退出的任务控制节点；节点停止前先检查 DNS/PG/RGW 的放置。
- Pod Ready 后继续等待新的 ADX 会话、可路由、可调度、容量和两种运行时能力，实际地址对应当前 Pod，镜像/ELF 固定，连续三个稳定样本且没有活动 Environment。
- 任务独立 TLS 与管理凭据只写私有目录，不入库。最终验收使用任务私有稳定入口；长实验不依赖无监督 kubectl port-forward。保持证书校验。

这些配置须在新任务中生成；仓库不含历史 kubeconfig、S3 密钥、SDK token 或数据库密码。

## 3. 按顺序验收

1. 远端质量门：TAP 原代码按新回归失败、修复后三轮通过，再过 fmt/vet/全仓单测/runsc race/生产构建；记录源码、工具链和实际 ELF。
2. etcd/API、网络、真实存储和上述 ADX 就绪门。确认本任务以外的服务没有变更。
3. 官方 SDK，两个 runtime 分别执行 integration 与 e2e/standalone：共 76 用例，必须无跳过。源码命令如下；认证环境仅从自己的私有 sdk.env 读取，不写进命令文本。

```bash
cd "$TASK/AKernel"
# PY 指向本任务安装两套匹配 SDK 的私有 Python。
# AKERNEL_TEST_IMAGE/AKERNEL_TEST_HTTP_IMAGE 指向自己固定的 OCI 镜像摘要。
export AKERNEL_RUN_INTEGRATION=1
export PYTHONPATH="$TASK/AKernel/sdk/python"
for runtime in firecracker runsc; do
  export AKERNEL_TEST_RUNTIME="$runtime"
  for suite in integration e2e/standalone; do
    "$PY" -m unittest discover -s "sdk/python/tests/$suite" -t sdk/python -v
  done
done
```

4. 再跑连续保存/回滚、512 MiB 完整内存和真实根 RWFS、双向自动接管、源重新加入不覆盖目标、SDK 清理。/tmp 通常是 tmpfs，不能替代根私有盘测试。
5. 按 [故障进度](schedules/20261023T-pr119-storage-failure-rwfs-progress.md) 重放读者/角色崩溃、忙删除、复杂文件、失败发布、超时和救援、调用者死亡、S3 暂停、挂载替换、并发恢复。只有精确证明属于任务的进程或设备才可注入；保留失败目录，不重放未知有副作用请求。
6. 无额外压力时按 AB/BA 对照，首次和恢复后再次保存分开；每 runtime/version/round 至少十个探索样本，记录全部失败及完整内容校验。guest 调度间隙、HTTP 完成、SDK reload、S3 I/O、后台完成分开报告。

新脚本见 [脚本说明](../tools/pr119-pod-20261024/README.md)。`executed/` 是实际历史源码，有固定任务路径和身份门，便于审阅/适配，不是全新主机的一键安装器；新环境另存脚本和回执，不修改来源证据。尚未在另一台全新机器重放这套完整矩阵。

## 4. 结果、局限与下一步

当前修复制品结果见 [FC 一致性修复总结](stages/20261024T-pr119-fc-disk-cut-fix-stage-summary.md)；此前版本对照见 [10 月 24 日阶段总结](stages/20261024T-pr119-sdk-faults-performance-stage-summary.md)：官方 SDK、双向接管、列出的故障场景及十组 80 次完整状态回滚通过。新版本没有稳定提速；FC 每次约 3 GiB 上传、恢复后再次 Full 保存有约 978 MiB 额外读取。

JuiceFS 原生克隆与 FC 现有 Go 函数已通过零对象数据传输的 64 MiB 文件能力门，约 10.4 / 4.6 ms 含同步。这不是新的实际运行时布局已验收，更不能与完整 VM checkpoint 数字比较。运行时级原生克隆、远端基线加本地差异、以及本地一致捕获后远端提交均按 [下一阶段计划](plans/20261023T-pr119-sdk-juicefs-clone-local-delta-next-phase-plan.md) 继续。

未完成内部物理删除屏障/多 collector、旧 CI 特定对账竞争的确定性重放、PG/Redis 真实崩溃持久化、断电、双物理机、HA 和竞品同口径比较。不因这轮功能通过宣布生产验收或 SOTA 领先。
