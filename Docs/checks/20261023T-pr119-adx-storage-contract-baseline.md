# PR #119 固定 ADX 共享存储与快照引用契约测试

日期：2026-10-23。结论：既有组件契约测试 12 项通过；不是实际 JuiceFS 竞争、进程重启或完整 SDK 故障矩阵的替代证据。

## 1. 问题

在固定 PR #119 的 SDK 与双向故障接管主链路通过后，先补引用生命周期的组件基线，再继续真实进程重启和后台读者保护验收。所有编译测试必须在远端独立环境执行，不修改共享服务。

## 2. 方法

固定实际发布包对应 ADX 源码 `6fb53d7331811535b6be5787ba026e03072f427b`。按该仓 [AGENTS.md](https://github.com/openJiuwen-ai/agent-dx/blob/6fb53d7331811535b6be5787ba026e03072f427b/AGENTS.md) 的长构建/测试委派规则，由窄范围工作者执行只读源码基线测试，不改产品代码、不部署。

BareMetal 本任务独占容器限制 2 CPU、6 GiB、2048 PID、两个编译 job；只读源码挂载，独占 Cargo/target 缓存。源码要求的 Rust/Cargo 1.95.0 只安装到任务缓存；获取 locked 依赖后，实际测试容器网络为 `none`。源工作树 1320 文件的前后 SHA-256 一致，没有新增文件。

基础 Rust 镜像摘要 `sha256:3914072ca0c3b8aad871db9169a651ccfce30cf58303e5d6f2db16d1d8a7e58f`；实际编译器 `rustc 1.95.0 (59807616e 2026-04-14)`。这不是运行时镜像或现役 ADX 二进制的替换。

## 3. 数据

| 命令 | 结果 | 覆盖边界 |
|---|---|---|
| `cargo test --locked -p adx-checkpoint-storage --lib -- --test-threads=2` | 10 passed、0 failed、0 ignored，退出 0 | 挂载身份/替换拒绝、普通目录回退拒绝、工件路径和清单大小、未完成捕获、符号链接、节点 release 不删共享数据、精确回收等组件行为 |
| `cargo test --locked -p adx-core --test snapshot_busy -- --test-threads=2` | 2 passed、0 failed、0 ignored，退出 0 | 纯内存状态模型中的忙快照删除拒绝、无引用删除关闭新用户 |

完整名称、命令、工具链、镜像、资源与原始 stdout 摘要见 [小型证据](evidence/pr119-juicefs-tapfix-20261023/adx-contract-baseline.json)。没有 Redis 依赖，也没有实际挂载 JuiceFS。

峰值内存 2404335616 字节；OOM、PID 触顶事件均为 0。包含编译的 wall time 不作为产品性能。

第一次准备失败保留：旧 rustup 在安装固定工具链后尝试自更新镜像内只读 `/usr/local/cargo/bin`，退出 1，测试未运行。只修任务辅助脚本，显式关闭 rustup 自更新，复用私有缓存后第二次通过；没有更改源码的 toolchain 或 Cargo.lock。

## 4. 结论

【远端组件实测】固定源的 12 个既有契约测试全部通过，产品源码未改，现役二进制未变。

【边界】这些测试没有证明真实跨客户端 JuiceFS 锁、后台恢复与删除交错、ADX/Coordinator 重启或未知结果重试安全。不能用它们关闭开发计划的全部读者保护门。

## 5. 建议与改进项

下一步在实际 SDK 沙箱中保留旧 checkpoint 的活跃文件读者，推进最新 checkpoint，再重启任务 adxlet/Coordinator，验证旧文件依赖、权威引用和未 checkpoint 的新状态。确定性删除竞争、超时取消、上传/元数据/挂载故障仍需各自验收，不只扩大单测数量。

## 6. 可复现步骤

现有远端证据目录：

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
Q="$N/round-365f797-20261023.clPWh2h0"
T="$Q/tap-checksum-fix/storage/contract-tests01"
cat "$T/terminal-receipt.json"
cat "$T/attempt02/logs/checkpoint-storage-lib.stdout"
cat "$T/attempt02/logs/snapshot-busy.stdout"
```

完整隔离启动、容器/进程身份、构建命令、工具链获取、监测和清理日志保存在该目录；复测必须沿用只读源码与独占容器/cgroup，不可直接在共享宿主执行 Cargo 测试。

## 7. 现场清理披露

工作者自己的 bootstrap/测试容器与独占 cgroup 已回收，缓存保留约 2.6 GiB。三个测试完成后的空闲 sleep PID1 容器未在 Podman stop 的 10 秒内退出，由 Podman SIGKILL；原 stderr 保留，测试进程先前均已正常返回 0，没有误杀其他任务。

未修改现役集群、JuiceFS、源/目标 VM、宿主参数、共享服务、组件版本或父仓 gitlink。原始证据压缩包保留远端，未把构建缓存、二进制或整个源码压缩包加入父仓。
