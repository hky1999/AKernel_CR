# FC 私有盘本地 XFS 与 JuiceFS 原生克隆：十组配对验收

## 1. 问题

按计划在同一产品版本下比较 FC 的本地运行盘与 JuiceFS 运行盘。需要同时回答：checkpoint 与恢复是否变快、正常写入是否变慢、上传/读取量如何变化。不是用单次克隆耗时决定后端，也不是两条新存储路线的最终裁决。

## 2. 方法

固定 sandboxd fdb145cf51f340dc46ebea3713c342b4ec93b127、实际 ELF debbf268…、native-rejoin02（CRI 53669406…）。VMM/kernel/initrd/runsc/ADX/SDK 全部保持上一轮固定字节。仅删除/恢复 writable_storage_dir 与 writable_storage_filesystem 两个配置字段；TOML 其他结构相同。每 case 核对十个载荷摘要、镜像、实际盘 FD/挂载与运行归属，不能只看配置。

十组 AB/BA，共二十个独立实例；每后端 n=10，每实例连续两次完整保存/reload。每对在相同执行节点，节点逐组轮换；顺序与节点相关，无法分别估计两种效应。两个逻辑 Node 位于同一 BareMetal；这里的 reload 在同一逻辑节点，不是跨物理机性能。此前 SDK 双向故障接管功能另行验收。

每实例 1 vCPU/2 GiB 配置内存、512 MiB 应用状态、64 MiB 固定随机根文件、1 GiB 私有盘。Full、无压缩、JuiceFS 4 GiB 缓存/writeback=false。每 case 重建本任务 Node Pod 和新会话，控制/API/Redis Pod 与 Secret UID 不变；真实可路由/可调度连续观察通过后才发 SDK。自然基础设施/Linux 缓存，不清共享缓存、不宣称全冷；物理主机共享，未证明其他使用者负载为零。

编译测试全部 BareMetal 独立容器/Pod。正式测量期间没有并行编译；gVisor helper 构建严格等待本轮二十实例成功和最终 native 布局终态。容量每 case 用实时 Ceph df，要求对象后端至少 10 GiB、宿主保留 650 GiB。旧试跑和旧计时 fixture 均未并入本统计。

## 3. 数据

### 3.1 完整业务链路

以下单位均为毫秒、每后端每轮 n=10 的组中位数。guest 观察为独立 2 ms 调度探针的最大间隙；宿主 pause 字段只是一段 API 调用，不代替整段停止时间。

| 轮次 | 操作及计时边界 | 本地 XFS | JuiceFS 运行盘 |
|---|---|---:|---:|
| 新实例的第一次保存 | checkpoint 请求完成 | 8404.5 | 5507.5 |
| 新实例的第一次保存 | guest 最大调度间隙（观察到的暂停） | 7819.8 | 5029.7 |
| 新实例的第一次保存 | 公共 SDK reload 返回 | 3982.4 | 3011.9 |
| 新实例的第一次保存 | 恢复到完整内存和根文件校验完成 | 6741.6 | 5681.2 |
| 恢复后的再次保存 | checkpoint 请求完成 | 11307.0 | 7574.0 |
| 恢复后的再次保存 | guest 最大调度间隙（观察到的暂停） | 10960.3 | 7302.5 |
| 恢复后的再次保存 | 公共 SDK reload 返回 | 4416.0 | 3078.7 |
| 恢复后的再次保存 | 恢复到完整内存和根文件校验完成 | 7087.3 | 5688.8 |

首次 checkpoint 的 Q1–Q3 为本地 8289.0–8567.5 / JuiceFS 5427.25–5810.0 ms；再次保存为 11141.25–11358.0 / 7380.0–7722.5 ms。按每对计算 JuiceFS/本地时间比，再取中位数，首次为 0.664（Q1–Q3 0.659–0.686），再次为 0.680（0.656–0.691），两轮均 10/10 对更快。组中位数之比与配对比不是同一统计，不能混用百分比。

### 3.2 正常写入与分相

| 操作与口径 | 本地 XFS | JuiceFS 运行盘 |
|---|---:|---:|
| guest 内创建/顺序写 64 MiB/文件与目录同步，组中位数 | 181.3 ms | 209.7 ms |
| 64 次 4 KiB 随机覆盖并逐次 fsync；先取每实例中位数，再取十实例中位数 | 0.300 ms | 9.588 ms |
| 同一组操作每实例最大耗时，再取十实例中位数 | 1.556 ms | 21.763 ms |
| 准备阶段 S3 PUT 字节，含根盘创建/写入/同步等，非纯单次操作 | 0 | 68890624（65.7 MiB） |
| 第一次 checkpoint 的盘保存阶段 | 2738.5 ms | 47.5 ms |
| 恢复后再次 checkpoint 的盘保存阶段 | 3423.5 ms | 51.0 ms |
| 第一次 checkpoint 的内存捕获阶段 | 5080.0 ms | 4978.5 ms |
| 恢复后再次 checkpoint 的内存捕获阶段 | 7447.0 ms | 7227.0 ms |

64 次同步属于同一实例的相关操作，不当作 640 个独立沙箱；此处约 32 倍是该“小块覆盖＋逐次同步”的延迟比，不是所有写入都慢 32 倍，也不是字节写放大 32 倍。生成输入、SDK 命令往返和最终读回不进入 guest 写入时钟。

### 3.3 对象流量与正确性

| 操作窗口，字节中位数 | 本地 XFS | JuiceFS 运行盘 |
|---|---:|---:|
| 每次 checkpoint 的 S3 PUT | 约 3 GiB | 约 2 GiB；普通运行写入另计 |
| 第一次 reload 至完整校验结束的 S3 GET | 356.2 MiB | 161.9 MiB |
| 第二次 reload 至完整校验结束的 S3 GET | 493.3 MiB | 321.2 MiB |
| 恢复后再次 Full checkpoint 的 S3 GET | 856.0 MiB | 579.6 MiB |

这些是该窗口实际服务端计数，并非逐对象唯一读量；自然缓存下的 GET 不能证明全冷恢复只需这些数据。再次 Full 保存仍有大量 GET，尚未逐对象拆解为内存、盘或元数据来源。

20/20 实例 rc=0，40/40 保存恢复的完整应用状态、64 MiB 根文件 SHA、实际介质证明通过，所有输入字节 SHA 一致。整轮 terminal rc=0，成功恢复 native 配置；逐实例白名单、分组四分位数和配对原始数见 [正式证据](evidence/pr119-juicefs-tapfix-20261023/fc-backend-pairs01.json)，原始远端终态 SHA 75b9dba774cc875a30fe1c71d20fd83067d317d55e658b5544f275572ab0b983。

## 4. 结论

【实测】在本固定配置/数据集/自然缓存条件下，JuiceFS 原生盘克隆稳定缩短了 FC 保存与 reload，两轮 checkpoint 的配对时长降低约 32%–34%。代价是频繁小块同步写显著变慢，顺序大写总耗时也有增加。不能直接晋升为所有业务的默认后端。

【源码＋实测分相】盘复制从数秒变为约 50 ms 后，剩余主要成本在 Full 内存捕获/持久化；guest 仍暂停约 5.0 / 7.3 秒。原生克隆不等于整个 checkpoint 达到几十毫秒，也没有据此证明超过 E2B/AgentEnv/Cube。

【边界】这不是 gVisor 的原生克隆结果，也没有实现远端只读基线＋本地差异。后一条仍有必要：它针对的是保留本地普通写延迟，同时恢复时按需访问远端基线。

## 5. 建议与改进项

继续 gVisor：独立克隆函数已完成真实客户端门，但匹配 bundle、后台恢复顺序、专有运行目录和完整 SDK 尚待完成。gVisor 私有 tmpfs upper 的 fsync 不等于远端持久化，不能与 FC ext4 的该延迟裸比。

再进入本地差异路线：优先成熟后端，先补同步错误、在线切层未知结果与宿主隔离门，再做两代/分支/空间耗尽/后台恢复与删除竞争，最后按同协议对照。不能仅增加缓存或比较 clone 原语后宣布完成。

后续停顿优化应单独比较一致捕获后恢复执行、异步持久化与增量内存保存；成功响应仍必须在远端持久化和 ADX 提交后。不混入当前 Full 同代码样本，不放宽 fsync 或完整性条件换数字。真实双物理机、全冷缓存与生产 HA 仍需独立环境。

## 6. 可复现步骤

使用 delivery 的固定基线和可选 FC 实验清单，在新的独立环境另存任务身份；实际执行源码位于 `tools/pr119-pod-20261024/experiments/fc-backend-compare/`，不是任意主机一键运行器。原任务不可重复覆盖：

```sh
cat "$ROUND/tap-checksum-fix/fc-backend-compare-pairs01/terminal.json"
python3 "$ROUND/tap-checksum-fix/summarize-fc-backend-pairs01.py" \
  --terminal "$ROUND/tap-checksum-fix/fc-backend-compare-pairs01/terminal.json" \
  --output "$ROUND/tap-checksum-fix/fc-backend-pairs01.another-public.json"
cat "$ROUND/tap-checksum-fix/fc-backend-final-state01/terminal.json"
```

新任务启动顺序、构建/负载与源索引见该目录 README。统计器在远端执行，不重跑 SDK；输出必须新路径。父仓仅保留白名单 JSON 和小型实际脚本，不入库私有 YAML、凭据、镜像、原始服务日志或二进制。

## 7. 现场清理披露

最终 [只读盘点](evidence/pr119-juicefs-tapfix-20261023/fc-backend-final-state01.json) rc=0：Environment=0；两节点的 VM/runsc/相关读取进程和僵尸计数均为 0；五个业务 Pod Ready、同一 image02，两节点可路由/可调度，Kubernetes API readyz=ok。实际公共 filestore 仍 XFS，FC 私有盘配置为任务 JuiceFS 根。

gVisor helper 在正式测量后执行，两客户端的临时二进制/测试目录均删除。原先一份失败遗留私有盘仍在，目录名称摘要 30386ede…f67，两客户端一致；未擅自删除，也不宣称所有历史孤儿已回收。宿主剩余 733599682560 字节，约 683.2 GiB，高于 650 GiB 预留。没有重启旧环境、共享服务或写入宿主模块/sysctl；只改了本任务 Node 配置、Pod 和测试数据。
