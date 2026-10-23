# PR #119 JuiceFS 清单目录失败发布检查

日期：2026-10-23。结论：两运行时在本任务清单目录不能创建文件时均未发布成功；解除故障后保留源状态并能创建新快照。不是 S3 断网或整个挂载消失验收。

## 1. 问题

验证“捕获已有输出，但最终清单不能创建”时，是否错误返回成功、损坏原沙箱或旧恢复点，能否恢复正常发布，以及失败输出是否仍可受控回收。

## 2. 方法

版本与前轮一致：AKernel `365f797`、实际 ADX `6fb53d7`、sandboxd `d5acc3b + TAP 未提交补丁`。仅在远端独立 JuiceFS 卷的 `/akernel/checkpoints/manifests` 目录临时设置原生 inode 配额，不修改 PostgreSQL、RGW、共享服务、宿主网络或挂载。设置前确认本任务没有其他 Environment，且卷内没有已有配额，避免覆盖原配置。

创建 512 MiB 确定性内存的源沙箱及一个成功的可复用快照；再修改内存和根文件。目录内建立任务独占哨兵，将 inode 上限设为 1，等待源节点同一 JuiceFS 客户端实际新建探针返回 EDQUOT/122，之后才调用原生 SDK 创建新快照。请求失败后不重放，撤销本轮配额，按唯一名称确认未出现 Ready 快照，再验证源新状态和一个全新发布请求。最后通过 SDK 删除资源。

固定 ADX 的 `platform/crates/checkpoint-storage/src/filesystem.rs:208` 中，`seal` 先扫描/同步工件文件，再于 manifests 创建临时清单、同步并 rename；`lib.rs::io_error` 把存储错误包装为 Unavailable。测试没有修改该路径。辅助脚本 `sdk-seal-quota02.py` 及串行驱动均仅远端语法检查/执行。

## 3. 数据

| 项目 | gVisor | Firecracker |
|---|---|---|
| 源客户端新建清单目录探针 | EDQUOT / errno 122 | 同左 |
| 失败请求后新出现的非空、无清单捕获目录 | 1 个，逻辑文件合计 551822092 字节 | 1 个，逻辑文件合计 3221240291 字节 |
| SDK 成功返回 / Ready 快照 | 均无 | 均无 |
| 实际接口错误 | CONFLICT / HTTP 409，retry=never、outcome=not_started | 同左 |
| 撤销配额后的源内存/根文件 | 未 checkpoint 新状态仍保留 | 同左 |
| 新的独立快照请求 | 成功 | 成功 |
| 删除源与已知成功快照后 | Environment 为零，已知快照不可查询 | 同左 |
| 补充只读清理核对 | 失败输出目录和清单均不存在，卷配额列表为空 | 同左 |

上述字节是逻辑文件大小，不是对象上传量或磁盘实际占用。FC 当前是 Full 模式，不能把此数字当增量脏页成本。[原始小型回执](evidence/pr119-juicefs-tapfix-20261023/manifest-quota-fault.json) 两组均 rc=0。

脚本初版尚未执行时，源码检查发现原生 SDK 的 list_snapshots 返回 `(items, next_page)` 元组；另存修正版精确检查两个字段后才执行。没有把未知返回类型当作空列表。

## 4. 结论

【实测】清单目录故障有效时，有非空未封存输出，但没有成功确认或可复用快照。故障恢复后源状态未丢，新请求成功，失败输出在源退出后被实际回收。配额通过 finally 救援路径确保撤销，本轮正常路径也已确认列表为空。

【源码与边界】代码把存储 I/O 包装为 Unavailable，但外部最终得到通用 CONFLICT。没有拿到含 EDQUOT 的原始服务错误栈，不将这个外部错误码说成精确的存储诊断；失败语义与错误传播仍需后续澄清。此例不覆盖 S3 上传中断、PostgreSQL 故障、挂载被替换，也未覆盖未知结果重放。

## 5. 建议与改进项

保留当前失败关闭行为；补齐从存储原始错误到 API 的请求关联和错误分类，避免把实际发布失败解释成普通版本冲突。其余故障必须分别注入和验收，不从目录配额推导所有存储失败都已通过。

## 6. 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
Q="$N/round-365f797-20261023.clPWh2h0"
S="$Q/tap-checksum-fix/storage"
cat "$S/seal-quota02/terminal.json"
cat "$N/acceptance/runs/shared-seal-quota02-runsc/events.jsonl"
cat "$N/acceptance/runs/shared-seal-quota02-firecracker/events.jsonl"
```

完整指令由 `run-seal-quota02.py` 经任务 namespace helper 执行；JuiceFS CLI 在本任务客户端 Pod 内复用既有 META_URL/META_PASSWORD，禁止将其打印或纳入仓库。复测使用唯一输出目录，先确认原配额为空且无其他用例；不能把命令改为全卷容量限制。

## 7. 现场清理披露

两组临时目录配额、哨兵、探针均撤销或删除；两源沙箱、四个已知成功快照通过 SDK 删除。补充只读检查确认两个失败捕获目录已不存在，未自行 rm 共享工件。第一次 journalctl 诊断读错日志入口，仅返回 No entries，不能据此声称服务没有报错；实际日志入口另定位到任务 adxlet 文件，仍没有匹配原始错误。未修改共享服务、宿主参数、产品代码、运行镜像或父仓组件指针。
