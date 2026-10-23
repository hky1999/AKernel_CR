# PR #119 十组版本交替：完整状态、停顿观测与 S3 读写
日期：2026-10-24。十组全部通过、80 次 checkpoint/reload 完整状态校验通过，最终恢复新组。未观察到稳定提速。

## 1. 问题
新版本完整 SDK 的性能变化是否稳定？时间花在控制面、内存、私有盘还是共享存储？不能将不同负载或热缓存的几次样本当作优化收益。

## 2. 方法
全部实验在 BareMetal 本任务独立 Kind/Pod 环境执行；同一物理机的两个逻辑节点，未停止其他使用者任务。旧组为 AKernel 6ea0041、ADX/Execd 59fa791、原生 SDK 0.1.0rc2；新组为 365f797、6fb53d7、0.1.0rc3。公共 SDK 两组版本号均 0.2.0rc3，源码/安装包摘要不同，来自各自 AKernel 提交。因此比较包括 SDK、控制面、Execd 和配套根镜像，不是单独一个 ADX 改动。

两组共同使用同一修复后的 sandboxd ELF、同一完整 runsc/FC/kernel/initrd，JuiceFS 1.4.1、1 MiB 数据块、4 GiB 客户端缓存、compression=none、writeback=false。默认镜像为固定 EROFS 路线，配置启用 virtio-fs 能力不等于本样本一定使用了该通道。

十组交替：奇数组先旧后新，偶数组先新后旧；奇数组在节点 A，偶数组在节点 B。每次部署都检查空 Environment、新节点会话、可路由、容量、四个实际 Pod 镜像及十个实际文件摘要，再启动两种运行时。每个沙箱 1 vCPU、2 GiB 配置、1 GiB 私有盘；应用探针 512 MiB 确定性内存、64 MiB 根文件。每实例连续两轮，两版本/运行时各十个实例，两个实例内轮次分开统计，合计 80 次保存和 80 次 reload。

第一轮保存后修改内存与小标记，再恢复并检查 PID/身份、打开文件、全部应用内存和 64 MiB 根文件。第二轮是完整校验后再保存，没有主动大范围重写应用内存。两轮 FC 日志均为 Full；不将其称为增量窗口。

2 ms guest 观测器记录最大调度间隙，包含停顿、调度和时钟行为；不是精确宿主 pause。RGW（Ceph 提供 S3 接口的网关）计数覆盖保存，以及 reload 开始到完整校验；不先做全量读取来伪造 lazy 启动。没有清全局缓存，这组不是对象存储冷恢复。

## 3. 数据
单位均为 ms，每个单元 P50 的 n=10；箭头为旧组→新组。配对比值是每对新/旧耗时比的中位数，大于 1 表示新组更慢。

| 运行时 | 操作位置 | checkpoint HTTP 完成 | SDK reload | checkpoint 配对比值中位数 |
|---|---|---:|---:|---:|
| gVisor | 新建后首次保存 | 1557.0 → 1498.0 | 1788.0 → 1771.7 | 1.042 |
| gVisor | 恢复后再次保存 | 1599.5 → 1656.5 | 1726.9 → 1732.4 | 1.067 |
| Firecracker | 新建后首次保存 | 8317.0 → 8305.0 | 4716.0 → 4587.1 | 1.008 |
| Firecracker | 恢复后再次保存 | 10970.0 → 11054.0 | 5034.1 → 5166.7 | 1.001 |

首次 gVisor checkpoint 的组间 P50 看似降低 3.8%，但配对比值中位数为 1.042，不能宣布提速。恢复后再次 checkpoint 配对差值中位数为 +98 ms、比值 1.067；有慢样本，尚未定位为确定的代码退化。FC 初次与下一轮的 SDK reload 配对比值分别约 0.997 / 1.042，方向也不一致。

新组 FC 的分相与读写：
| 条件 | guest 最大间隙 P50 | 私有盘复制 P50 | 内存快照 P50 | 保存期间 S3 GET P50 | 保存期间 S3 PUT P50 |
|---|---:|---:|---:|---:|---:|
| 首次保存 | 7771.2 ms | 2552.5 ms | 5292.0 ms | 0 MiB | 3072.0 MiB |
| 恢复后再次保存 | 10605.1 ms | 2482.0 ms | 8074.0 ms | 978.0 MiB | 3072.0 MiB |

各阶段分别求中位数，不能直接相加重建同一条样本。日志 pause=0 仅表示 pause API 调用阶段；完整停止区间还包含盘与内存捕获，guest 观测也确认了秒级间隙。

新组 gVisor 保存 PUT 约 601.5 / 601.9 MiB；完整校验结束时的 reload GET 约 6.9 / 7.9 MiB。此处大量数据已经在客户端或 Linux 缓存中，不能把几 MiB 的 GET 当作冷恢复只需几 MiB。FC 同一口径的 reload GET 约 708.5 / 1057.1 MiB，也不是逐对象唯一读取量。

结果见 [完整分组与配对统计](evidence/pr119-juicefs-tapfix-20261023/ten-pair-performance-summary.json)，包含 min/max、原始终态 SHA、配对差值与范围。另附 [80 条白名单样本](evidence/pr119-juicefs-tapfix-20261023/ten-pair-performance-samples.json)，可独立重算统计。没有丢弃慢样本，首次镜像身份门失败的试跑没有产生正式样本，另留失败记录。

## 4. 结论
【实测】两套版本均能完成这组完整状态负载，没有这组版本轮换带来的功能失败。新版本没有稳定的性能优势，也不能据此证明所有指标零回归。

【源码与实测】FilesystemCheckpointStore::begin_capture 在共享 artifacts 下直接分配目录，FC 捕获的盘和内存会在停止期间进入共享文件路径；当前 Full 保存约 2 GiB 内存加 1 GiB 可写盘，每次约 3 GiB PUT。内存和磁盘都需要处理，单做 RWFS 或调整缓存不能消除完整保存的上传。

【外推，待更细归因】恢复后再次 Full 保存的额外 GET 与尚未读热的恢复输入被再次访问相符；现有网关计数没有逐文件/对象标注，不能把全部 978 MiB 精确划归内存。SDK reload 还包含源退出、调度与路由，不能当成 VMM 内部恢复时间。

该数据不支持超过 E2B、AgentEnv、CubeSandbox 的结论。既有 64 MiB 脏量的历史增量窗口和本轮 Full/远端提交语义不同，不能直接并排排名。

## 5. 建议与改进项
1. 对照当前共享路径与“本地一致捕获，恢复执行后可靠提交到 JuiceFS”的停顿/提交分解；保留当前内存机制和成功确认条件。先证明输出不再写入、运行时依赖仍被保护，不能只改目录或提前返回成功。
2. 继续私有盘两路线对照：JuiceFS 同卷元数据克隆，以及不可变远端基线加本地差异。FC 已发布 OverlayBD v1.0.18 有在线快照 API，应先核查复用；不能把普通 raw ext4 镜像直接称为其已支持格式。
3. 先验当前客户端的 FICLONE / copy_file_range、匿名 FD、mmap 脏页与分支隔离原语，再做实际运行时适配。gVisor 当前旧 bundle 与后续 filestore bundle 分开固定。
4. 当前 Full 档位、无压缩、同节点热基础设施都是明确条件。后续若更改压缩或增量模式，应单独建立基线；增量需要匹配 VMM 能力，不盲目开关。
5. 内部物理删除/多 collector、精确冷读归因和生产故障域仍有未完成项，继续记录，不从本轮性能通过推导为生产安全验收。

## 6. 可复现步骤
```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
S="$N/round-365f797-20261023.clPWh2h0/tap-checksum-fix/storage"
cat "$S/performance-pairs02-launch-receipt.json"
cat "$S/performance-pairs02/terminal.json"
cat "$S/performance-pairs02/summary-v1.json"
sha256sum "$S/performance-pairs02/terminal.json"
```
驱动 run-performance-pairs02.py、SDK 夹具 sdk-performance01.py、就绪门 wait-perf-ready02.py。原始每实例事件与终态位于任务 acceptance/runs/shared-performance-pairs02-*；统计按 runtime、variant、round 分组，再按 pair 配对，不能把同实例两轮当成二十个独立实例。

## 7. 现场清理披露
40 个实例通过 SDK 删除、Environment 归零；最终部署回 new-common-tapfix，并再次核对会话、镜像与实际载荷。任务集群、存储及稳定代理保留，未动旧环境、共享服务、宿主参数。没有本地编译或测试，没有将诊断试跑混入正式样本；原始含环境变量的服务日志不入库。
