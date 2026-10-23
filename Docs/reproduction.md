# 已验收源码交付的复现说明

本文对应 2026-10-21 的五子模块交付。PR #119 的 2026-10-24 固定候选请使用 [另一份复现说明](reproduction-pr119-20261024.md) 和 `delivery/pr119-20261024.json`；两套版本及数据不能混用。

## 1. 安全边界与前置条件

使用专用 Linux x86_64 远端测试机或任务独立环境，不在本地开发机编译测试。不停止或修改他人的 sandboxd、Redis、JuiceFS、容器、挂载和网络规则。

运行时实验需要 KVM、FUSE、cgroup v2、挂载/网络命名空间，以及支持 reflink（共享数据块的快速文件克隆）的 XFS 文件系统。filestore 和模板必须满足所选运行时的文件系统约束。使用短而稳定的挂载路径：Linux Unix socket 地址上限为108字节。两节点挂载命名空间中的 filestore 路径必须一致。

每个任务使用新状态和新凭据。不复制历史私有配置，不复用 kernel/initrd/VMM 兼容摘要不同的旧 checkpoint。

## 2. 源码与组件门禁

精确命令和环境要求见 `Docs/reproduction-adx-sdk.md`、`Docs/reproduction-runtime.md`。附录区分直接运行的仓库测试、临时测试辅助入口及私有材料前置条件。

递归克隆仓库，保持 `delivery/manifest.json` 中的提交。以下命令只在远端执行：

```bash
cd sandboxd
GOMAXPROCS=2 make check-fmt
GOMAXPROCS=2 make vet
GOMAXPROCS=2 make test
cd ../agent-dx
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features -- -D warnings
```

ADX 可选 all-features 依赖需要额外系统库。库缺失或无关基线失败必须记为失败/无法执行，不能修改共享服务来绕过，也不能静默报告全绿。

按 ADX 原生 Makefile/包工作流构建。历史组件使用固定 Rust 工具链，Coordinator 命令为 `cargo build --locked --release -p adx-coordinator --bin adx-coordinator`，API Server/adxlet 使用各自目标。按 sandboxd Makefile 构建 sandboxd 及匹配的静态 Firecracker guest agent。initrd 必须与 sandboxd 匹配，字节变化会使旧模板失效，不能使用动态链接 guest agent。

gVisor 使用固定源码、Bazel 版本和配套打包规则构建，不能混用不同发布版本的 runsc 与辅助程序。`sandboxd/third_party/runtime-versions.env` 的正式发布固定版本，与本实验源码提交分别管理。

## 3. 安装匹配的 SDK 源码

在远端新建虚拟环境：

```bash
python3 -m venv out/client
out/client/bin/pip install -e ./agent-dx/platform/sdk/environment/python
out/client/bin/pip install -e ./AKernel/sdk/python
```

已验收实验使用源码扩展，仅安装已发布 `akernel-sdk` / `adx-environment` 包，可能缺少这些能力。

## 4. JuiceFS 部署辅助脚本

可复用、按任务生成私有凭据的部署辅助脚本及其测试位于：

`AKernel/deploy/experimental/juicefs-adx/`

包含 `lab.py`、`node_network.py`、`runtime_nodes.py`、`private_pki.py`、`native_profile.py`、`short_profile.py`、运行时下载和 initrd 构建。创建任务前先看 `--help`。生成的环境文件、密码、证书和真实部署 YAML 不进入仓库。

实验使用预留地址和端口并拒绝冲突，不为实验修改既有环境。应在空闲专用主机或独立外层命名空间运行。PostgreSQL 开启 fsync/synchronous commit，两节点 JuiceFS 挂载同一格式 UUID，验收中不启用 writeback。

`configs/adx-shared-storage.example.json` 是部分存储配置，不能直接启动完整系统。通过 ADX 部署工具合并并生成 `.yaml`，启动前用 `adxctl` 校验。不能同时保留旧 `checkpoint_dir` 和 `checkpoint_storage`，也不能关闭 cgroup 或证书校验。

原 A0 生成器保留为已测试的源码材料，不代表其旧默认运行时二进制已经包含当前提交。应放置新构建版本，重新生成部署配置及 guest 兼容摘要，并验收后再认可新配置。

## 5. checkpoint/restore 诊断探针

`tools/acceptance/shared_fs_probe.py` 和 `probe_cleanup.py` 复用已验收 A0 诊断链，调用真实原生 ADX SDK 的 pause/resume/snapshot/clone，检查实际源/目标节点、私有文件系统分支隔离，并记录本任务资源清理。

```bash
out/client/bin/python tools/acceptance/shared_fs_probe.py \
  --endpoint https://YOUR-TEST-ENDPOINT \
  --token-file /YOUR-PRIVATE-DIR/token \
  --ca /YOUR-PRIVATE-DIR/ca.pem \
  --runtime runsc \
  --source-node YOUR-SOURCE-NODE --target-node YOUR-TARGET-NODE \
  --shared-root /YOUR-SHARED-MOUNT/checkpoints \
  --output /YOUR-TASK-DIR/results/runsc-01
```

使用新的输出目录，以 `--runtime firecracker` 重复，并提供匹配运行时的 rootfs/启动配置。该原生探针不等于完整公共 SDK 验收，也不能证明重启/故障安全。

## 6. 公共 SDK 与读者保护验收

历史完整链路通过公共 `Sandbox` 入口创建；内部 checkpoint 协调和克隆仍使用现有原生 Environment 接口，不新增公开 checkpoint catalog API。

必须保留的证据包括实际节点落点、恢复的内存与已打开文件描述符、不可变父快照/私有克隆隔离、读写者与独立租户只读者行为、显式拒绝向 EROFS 写入、启动前持久化读者预留，以及回收前的可靠运行时退出证明。进程退出码或 SDK 删除成功不能单独替代这些证据。

历史验收边界见 `Docs/acceptance-scope.md`。绑定原主机身份的编排与私有记录不包装成可移植的一键入口。全新主机完整 SDK/读者退出矩阵需单独验收，不能从组件单测推导完成。

## 7. 重算公开性能样本的点估计

```bash
python3 tools/performance/recompute.py evidence/performance-six-pairs.json
```

脚本核对全部配对样本的中位数与配对几何均值耗时比。登记的置信区间保留为历史结果；此最小脚本不重放 bootstrap 随机流。计算不需要在线环境或凭据。新增采样必须沿用原指标定义与登记的新旧版本交替方案。

## 8. 清理

只通过正常 API 清理本任务资源，并确认与执行实例绑定的退出证明。结果不确定时保留依赖。不能按进程名全局杀进程、运行全局 GC、强制卸载共享挂载，或以按年龄删除代替所有权证明。

