# PR #119 分相版本对照与源码交付进度

日期：2026-10-24。源码修复已独立提交推送；新旧十组交替全部通过，没有稳定提速结论。JuiceFS 原生克隆与 FC 现有 Go 函数的能力门随后通过，尚不是两条新运行时存储路线已完成。

## 开发内容

前轮已补齐完整 SDK、双向故障接管、多读者、控制进程崩溃、复杂 RWFS、失败发布、超时和挂载替换。继续先建立可解释的当前架构基线，不把不同负载/缓存/版本的单次耗时写成优化收益。源码交付消除远端未提交 TAP 补丁依赖。

## 修改内容

- sandboxd 10312f2，d5acc3b 上的两文件 TAP 修复，已普通 push 到 hky1999/sandboxd:codex/pr119-tap-reset-20261024；与远端已验收源文件摘要完全相同，没有混入并行 Kata/rebase。
- 远端 performance-prepare04.py：只读复用历史旧 OCI，制作旧控制面/Execd + 共同 TAP 修复的候选；固定 SDK 旧原生 0.1.0rc2、新原生 0.1.0rc3。观测器与镜像只远端构建，前三次 helper 失败保留。
- sdk-performance01.py / 2 ms guest observer：单独计 checkpoint HTTP、SDK reload、首次根文件、完整内存与 64 MiB 根文件；RGW 增量和 FC 分相日志仅导出白名单字段，pause 日志字段不等于全部停顿。
- run-performance-pairs02.py / wait-perf-ready02.py：十组 AB/BA 顺序，每次部署以新会话、路由、容量、Pod/镜像和十个真实文件摘要过门，两个运行时各两轮。目录为 performance-pairs02，每组/运行时/轮次分别保留，不把实例内两轮视为独立实例样本。
- 首版配对驱动在镜像摘要门停止，正式样本为 0。逐层确认三个 Kind 节点的 CRI 索引 9840a277 指向既定 manifest a46c88b9、config fbfba99f，才修正门继续；没有通过接受任意摘要解决。首个只读探针误以为 Kind 节点自带 Python，返回 127；改在宿主解析 ctr 结果，未修改镜像或安装软件。

## 测试结果

测量试跑 performance-smoke01 两运行时 rc=0，512 MiB 应用内存、64 MiB 根文件、2 GiB 配置、1 GiB 私有存储：gVisor checkpoint 1750 ms、SDK reload 1968.672 ms；FC 7790 / 4317.746 ms。FC overlay 2371 ms、内存 snapshot 5025 ms，guest 最大调度间隙 7399.210 ms。完整状态和 SDK 清理通过。这是试跑，不纳入正式配对或冷恢复结论。

FilesystemCheckpointStore::begin_capture 在共享 artifacts 下直接创建捕获目录，seal 再同步文件和提交清单；说明当前内存保存也可能受共享 I/O 约束。只优化 RWFS 不能自然消除内存阶段。后续应在相同内存路径和持久化语义下比较两种私有盘路线，是否增加本地一致捕获、恢复执行后远端提交的共同基线仍待设计/验收，不能靠提前成功确认降低数字。

performance-pairs02 终态 rc=0，40 个实例各两轮，80 次 checkpoint/reload 完整状态校验通过，最终恢复新组并清空 Environment。每运行时/版本/轮次 n=10，新组首次/恢复后再次保存 P50：gVisor 1498 / 1656.5 ms，FC 8305 / 11054 ms。配对统计没有稳定提速；FC 每次约 3 GiB PUT，恢复后再次保存另约 978 MiB GET。分相、样本边界与旧组数字见十组性能检查，不能将组间 P50 直接当作因果收益。

随后 native-clone-capability01 / go-clone-helper01 均 rc=0：同卷 copy_file_range 和现有 FC cloneFileNoSync 克隆 64 MiB 并 fsync 分别约 10.4 / 4.6 ms，S3 GET/PUT 为零。分支、匿名 FD、mmap、截断和打洞内容通过；当前 FICLONE 不支持，gVisor 仍需接口适配。所有原语目录和 Pod 内探针已定向清理，保留源码回执。没有新运行时配置、制品或共享服务变更。

仍缺内部物理删除屏障/多 collector 完整实测、冷读精确归因、两条新运行时存储路线、生产多机与存储 HA，以及父仓复现分支交付。原始旧 CI 的特定权威对账竞争仍没有原样确定性重放。

## 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
S="$N/round-365f797-20261023.clPWh2h0/tap-checksum-fix/storage"
cat "$S/performance-prepare04/terminal.json"
cat "$S/performance-image-identity02/terminal.json"
cat "$S/performance-smoke01/terminal.json"
cat "$S/performance-pairs02-launch-receipt.json"
cat "$S/performance-pairs02/current.json"
cat "$S/performance-pairs02/terminal.json"  # 只有实际存在且 rc=0 才记完整通过
```

成功结束后驱动必须恢复新组，期间不能启动额外 CPU/存储压力实验或清理任务依赖。仅使用本任务集群、Pod、目录与 cgroup，没有更改共享服务、旧环境或宿主参数；本地没有编译测试。
