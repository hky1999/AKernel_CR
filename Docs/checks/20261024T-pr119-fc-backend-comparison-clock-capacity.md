# FC 同代码后端对照：计时口径与实时容量前检

续记：正式十组整体 rc=0，20 实例/40 次完整状态通过，最终恢复 native；见 [正式性能检查](20261024T-pr119-fc-backend-ten-pair-performance.md)。下文保留测量准备与 n=1 试跑的口径，不与正式样本合并。

## 1. 问题

按既定计划继续比较本地运行私有盘与 JuiceFS 运行私有盘。必须区分运行写入成本、checkpoint 停顿/完成及恢复读取量，不能只比较克隆；本检查先确认测量时钟和试验存储容量可信。

## 2. 方法

源码和已测镜像保持 fdb145c / native-rejoin02 / sandboxd debbf268…，VMM、内核、initrd、runsc、ADX 和 SDK 不变。对照仅移除或恢复 FC 的 writable_storage_dir / writable_storage_filesystem 两项；其他 TOML 结构逐项相同。两组都 Full、无压缩、4 GiB JuiceFS 缓存，guest 为 2 GiB 配置/512 MiB 应用状态/64 MiB 根文件/1 GiB 私有盘。

复读已执行的 `sdk-writable-performance01.py`：root_write_begin 包住一次 SDK commands.run，命令为 `dd if=/dev/urandom ... conv=fsync`；create_ms 还包住了一次操作后 RGW 查询。原数值没算错，但此前“SDK 文件写入加 guest sync”的文字不精确，不能当作纯存储 fsync 或纯启动时间。

新 Go 验收负载 `guest-storage-io.go` 在 guest 内用单调时钟分别记录生成数据、创建、64 MiB 顺序写、文件 fsync、目录 fsync，以及 64 次 4 KiB 随机覆盖/逐次 fsync；数据生成与最终校验不计入写入时钟。固定种子使两后端的字节和位置序列相同，外部再校验完整文件 SHA。新 SDK 测量把构造函数时钟停在 RGW 查询之前，并在保存前、恢复后都验证实际 VMM 盘 FD、文件系统和归属。

所有编译测试仅在 BareMetal 任务私有容器。新负载以 Go 1.25.5、2 CPU/2 GiB、网络 none 编译；不是修改或重建产品运行时。容量先检查 CephCluster status 时间，再用本任务 RGW 已有客户端身份及其现有 MON 连接参数查询实时 ceph df，不读取/输出密钥值、不新增授权。

## 3. 数据

| 项目 | 结果与口径 |
|---|---|
| 旧 513 ms 写入样本 | SDK 命令往返 + guest 中随机数据生成/write/fsync；非纯后端 fsync，原始时长不变 |
| Ceph CR 缓存 | lastChecked 停在 2026-10-23，不能当作本轮实时容量 |
| OSD admin perf | 返回空字典，不当作“占用为零”；其他不支持的命令结果保留，不修改 daemon |
| 实时 ceph df | 已有 RGW 身份带现有 MON 连接参数查询成功；总计 42949672960 字节，可用 41819127808 字节，约 38.95 GiB；数据池 max_avail 39671644160 字节 |
| guest 探针构建 | rc=0；ELF f11e2a32602ef80cadecb664086562f4367e92bd79a8df63c934088e8f13cc94；格式化源码 844a7d60… |
| 探针独立校验 | 两次 64 KiB/4 次覆盖，独立文件 SHA 与内部读回一致、固定种子内容/位置相同、各计时边界和字节数通过。不是实际 guest SDK 后端性能样本 |
| 两布局 SDK 试跑 | 整轮 rc=0；两实例各两次 checkpoint/reload，文件完整 SHA 相同，实际 VMM 盘 FD/文件系统与四次介质证明通过 |

试跑 n=1/后端，仅用于确认测量链路：本地→JuiceFS 的 64 MiB 创建/顺序写/文件与目录同步为 191.6→211.2 ms；64 次 4 KiB 随机覆盖加逐次同步，实例内中位数为 0.293→9.495 ms。首次 checkpoint 为 8583→5439 ms，恢复后再次保存为 11102→7506 ms。此时钟含义与旧 513 ms 不同；试跑不与正式样本混合，也不据此声明稳定收益。实际数据见 [试跑回执](evidence/pr119-juicefs-tapfix-20261023/fc-backend-compare-smoke01.json)。

## 4. 结论

【源码】此前写入和创建的文字口径需更正；checkpoint、reload、guest 调度间隙等原始时钟没有因此重算或伪造。保留原报告，在后续对照中使用明确拆分的新时钟，旧/新测量负载不拼接为同一统计样本。

【实测】两个布局的 SDK 试跑已经通过，准备时十组在途，曾完成 9/20 个实例、18 次状态校验；最终二十实例整轮已通过，数据单列正式性能检查。每个后续 case 前仍从实时后端查询，要求对象存储至少 10 GiB、宿主至少 650 GiB；不凭过期 CR 容量或本地 XFS 公告量推断对象存储可用量。

## 5. 建议与改进项

两布局试跑完成、相同字节通过后，已用同一 fixture 启动十组 AB/BA；每组两种后端在同一执行节点，各创建一个独立实例、连续两轮保存恢复。首次与恢复后再次保存分组，64 次 fsync 是实例内相关操作，不冒充独立实例。每个 case 都重建本任务 Node Pod，控制/API/Redis Pod 必须保持身份，基础设施缓存不宣称全冷，也不清宿主缓存。

此项是 FC 的当前本地基线与原生克隆对照。gVisor 原生克隆和远端只读基线＋本地差异仍需独立完成，不能缩小整个目标或拿当前基线比较代替两条新路线的最终裁决。

## 6. 可复现步骤

以下仅在本任务远端私有环境执行；先检查已有进程/终态，不能因观察超时重复启动。

```sh
cat "$ROUND/tap-checksum-fix/fc-backend-io-build01/terminal.json"
cat "$ROUND/tap-checksum-fix/fc-backend-compare-smoke01/terminal.json"
# 仅在原任务试跑确已完成、源码/探针摘要相同且 Environment=0 时另存启动：
python3 "$ROUND/tap-checksum-fix/run-fc-backend-compare01.py" \
  --output "$ROUND/tap-checksum-fix/fc-backend-compare-pairs01" --pairs 10 \
  --require-smoke "$ROUND/tap-checksum-fix/fc-backend-compare-smoke01/terminal.json"
```

探针源码与实际执行脚本将收录 `tools/pr119-pod-20261024/experiments/fc-backend-compare/`；二进制、私有 YAML 和凭据不入库。实时容量查询使用现有客户端身份，不能删除鉴权来修复连接失败。

## 7. 现场清理披露

已创建任务探针构建目录和文件，编译容器已退出，64 KiB 校验文件保留作小型证据。两个实际 SDK 试跑实例及各自快照均删除；十组正式测量在途，不能宣称场景已清理。产品源码/二进制未变，没有修改共享服务、宿主模块/sysctl 或隔离。SDK 对照仅在任务范围修改 Node 配置与 Pod；失败则保留布局和资源，不为恢复默认外观而清除未知操作；成功后恢复本任务 native 布局。历史单份私有盘仍保留，不计入新样本清理成功。
