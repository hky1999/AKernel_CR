# PR #119 捕获超时与已有快照跨节点救援检查

日期：2026-10-23。两运行时受控救援通过；不是“一秒内完成整个操作”，也不是所有主机 I/O 活动均已独立跟踪。

## 1. 问题

验证 Snapshot 捕获超时后不产生假成功；明确结束源实例后，已有成功快照仍可在另一个节点恢复、继续写入并再次 checkpoint/reload，失败输出不遗留成可恢复工件。

## 2. 方法

固定候选与独立环境不变，无产品代码或镜像更换。源由公共 SDK 创建，持有 1 GiB 确定性应用内存和根文件；先通过既有 ADX 原生 Snapshot API 建立成功快照。修改源后以 `timeout_seconds=1` 创建另一唯一名称的快照，遇错误不重放，查询目录确认无 Ready 快照。

随后显式通过 SDK 删除源，确认权威记录移除、原 VMM/runsc-sandbox PID/启动代次不再存在，再从先前成功快照恢复到另一节点。核对完整内存/进程/打开文件和根文件，目标新写入后再 checkpoint/reload，最后删除资源。

进程身份必须由 OCI `config.json` 的 `adx.runtime_id`、`adx.environment_id` 注解将 ADX 逻辑执行 ID 映射到 sandboxd 的 sbox UUID，再关联真实进程，不能直接将逻辑 ID 当 VMM argv 中的 UUID。

## 3. 数据

| 项目 | gVisor | Firecracker |
|---|---|---|
| 1 秒参数确实到达 sandboxd | Checkpoint 请求 `timeout_seconds:1` | 同左 |
| 请求至错误返回 | 1945.963 ms | 6411.305 ms |
| 返回契约 | CONFLICT/409、retry=never、outcome=not_started | 同左 |
| 返回后权威状态 | Failed，非 Ready 快照，无匿名 checkpoint | 同左 |
| 错误后查询新捕获目录 | 0 个；不等于已逐个跟踪全部后台 I/O | 同左 |
| 显式源删除后的确认 | 原运行时进程/权威记录消失 | 同左 |
| 已有成功快照在另一节点恢复 | 1 GiB 完整内存/进程/打开文件与根文件正确 | 同左 |
| 目标继续写、新 checkpoint/reload | 通过 | 通过 |
| 最终清理 | 无 Environment、已知快照不可查询、失败目录未遗留 | 同左 |

`storage/snapshot-timeout02/terminal.json` 两组 rc=0；[脱敏小型证据](evidence/pr119-juicefs-tapfix-20261023/snapshot-timeout-rescue.json) 保留事件与证明范围。

首次 `snapshot-timeout01` 在进程匹配预检失败，未注入超时；保留源和已知成功快照。修正版先验证只剩这一个属于本任务的 Environment、已知快照存在且源内容未变，直接继续原现场，没有重新创建或冒充原轮已通过。FC 是随后全新的一组。

## 4. 结论

【实测】超时捕获没有报成功或留下 Ready 快照；通过显式源删除完成受控救援，原成功快照仍可跨节点恢复，目标后续捕获/恢复正确。

【边界】1 秒限制的是捕获路径参数，API 总耗时还包含恢复/清理/对账。原回执的 `source_writer_exit_verified` 只由原 VMM/runsc-sandbox 消失和目录回收证据支撑，不外推为所有 sandboxd I/O goroutine 均已逐一跟踪；没有宣称仅靠客户端超时就可以删除输入，也没有测试任意未知结果自动重试。

【待改进】底层超时最终被通用 CONFLICT 表达，不能从外部错误码判断具体存储或捕获原因；需要改善请求关联和错误传播，独立于本轮恢复一致性通过。

## 5. 建议与改进项

继续验证调用 SDK 的进程突然退出时，后端可能仍成功提交的结果对账；不将断开客户端视作取消确认。补后台 I/O 生命周期观测与错误分类，然后进行受控性能对照。

## 6. 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
S="$N/round-365f797-20261023.clPWh2h0/tap-checksum-fix/storage"
cat "$S/snapshot-timeout01/terminal.json"
cat "$S/snapshot-timeout02/terminal.json"
cat "$N/acceptance/runs/shared-snapshot-timeout02-runsc/events.jsonl"
cat "$N/acceptance/runs/shared-snapshot-timeout02-firecracker/events.jsonl"
```

辅助脚本为 `sdk-snapshot-timeout02.py / run-snapshot-timeout02.py`。其中 `--resume-from` 只用于经身份验证继续本轮未注入故障的旧预检现场；全新复测用新目录、新资源名，不能对不存在或已改变的旧资源盲目继续。所有编译、语法检查和测试仍只在远端。

## 7. 现场清理披露

两组源、两个救援目标和两个已知快照均通过 SDK 正常删除；任务集群/存储/代理保留用于后续门禁，没有改共享服务、宿主参数、制品或父仓 gitlink。

补充日志诊断的筛选过宽，一次输出混入启动/spec 日志中的本任务临时运行控制凭据；没有纳入本文、证据 JSON 或 Git。后续只导出白名单字段，原日志保持远端私有。

范围核对已完成：【源码】`platform/adxlet/src/sandboxd.rs:612` 按 Environment ID、runtime ID、ownership generation 三元组生成执行凭据，未将节点 secret 交给 guest；不是 SDK 管理凭据。`controller.rs:1154` 的 cleanup 在移除运行时前调用 `control.retire`；`control_stream.rs:175` 删除该身份 slot 并关闭会话，`open_control:420` 同时检查凭据和当前预期身份。两份日志对应的恢复实例在本轮 SDK 清理中均已删除，相关代次已退休，不能跨实例/代次复用。没有为此重启共享服务或改其他任务凭据；源日志和运行数据仅留本任务私有现场，最终交付必须继续按白名单导出。
