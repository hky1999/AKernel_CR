# PR #119 控制进程重启验收的故障注入方式修正

日期：2026-10-23。状态：首次正常停止用例失败并保留；改为明确的进程崩溃后，两种运行时分别覆盖 adxlet、Coordinator，四组全部通过。

## 1. 问题

需要验证“sandboxd/虚拟机仍存活时，adxlet 或 Coordinator 重启不会丢失旧 checkpoint 读者保护”。首次辅助脚本使用 `systemctl restart adx`，结果未能保留虚拟机，需要先判定测试前提是否成立，不能直接归因为产品引用丢失。

## 2. 方法

沿用固定 `365f797 / 6fb53d7 / d5acc3b + TAP 补丁`，无制品变更。检查 SDK 原始事件、重启前权威记录和 VMM FD、任务 Node Pod 内的 systemd 单元、journal，以及当前运行时进程和权威目录；对照固定 ADX 源码的显式停止契约。

只操作本任务私有 Pod，没有在共享宿主执行 systemctl 或向其他进程发信号。

## 3. 数据

| 项目 | 实际结果 |
|---|---|
| 重启前场景 | FC 从第一版 checkpoint 恢复后生成第二版，VMM 仍打开第一版 JuiceFS `memory`，权威记录有两份工件引用；另写入未 checkpoint 的新文件/内存 |
| 初次注入 | 任务 Node Pod 内 `systemctl restart adx`；单元 `ExecStop=/usr/local/bin/adx-service stop`，`Restart=on-failure` |
| journal | 明确记录正常 Stopping / 服务 stopped / Stopped，再启动；不是单独的 adxlet 崩溃 |
| 实际后果 | 原 VMM 退出，权威 Environment 记录已移除；不满足“运行时仍存活”的前提 |
| 原始脚本结果 | `restart-matrix01` 返回 1，等待原运行时/引用恢复超时；其“preserved”字段只是保留意图，实际该沙箱已被正常停止路径清理，不能宣称仍存活 |
| 源码契约 | `platform/adxlet/src/admin.rs:1` 明确写明显式停止会先删除本地 Environment，再停止依赖；`Adxlet::drain` 为对应控制路径 |
| 修正方式 | 只在任务 Pod 内按角色、可执行路径、PID/启动代次验证 `/opt/adx/.../adxlet` 或 `adx-coordinator`，要求 PID>1，再对该 Rust 子进程 SIGKILL；观察监督进程将其重新启动 |
| 修正后 FC 两组 | adxlet、Coordinator 分别崩溃后均通过：旧 checkpoint 读者仍存在，权威两份引用保留，VMM PID/启动代次未变，未 checkpoint 的最新内存/根文件未回滚；随后新 checkpoint/reload 成功，沙箱删除成功 |
| 修正后 gVisor 两组 | adxlet、Coordinator 分别崩溃后均通过：原沙箱 PID/启动代次、两份权威引用、未 checkpoint 的最新内存/根文件保留；此时后台输入已读完，没有观察到仍打开旧 checkpoint 的 FD，不能据此宣称覆盖了 gVisor 未结束后台读取时的崩溃 |
| 四组操作数 | 每组 3 次 checkpoint、2 次 SDK reload；四个沙箱最终删除，权威 Environment 记录为 0。完整摘要见 [原始小型证据](evidence/pr119-juicefs-tapfix-20261023/controller-restart.json) |

原始失败与诊断目录：远端 `storage/restart-matrix01`、`storage/restart-diagnosis01`、`acceptance/runs/shared-tapfix-restart01-firecracker-adxlet`。修正后的独立结果进入 `storage/restart-matrix02` 和 `shared-tapfix-restart02-*`，不覆盖原失败。

## 4. 结论

【实测与源码】首次注入选择了带显式停止语义的服务重启，触发正常清理，不能用它证明“仍存活运行时的引用保护失败”。这是验收方式不符合目标前提，原脚本失败保持失败。

【实测】四组角色崩溃接管全部通过；FC 两组还确认旧 checkpoint 有实际 VMM 读者。gVisor 两组证明原运行进程和引用接管，后台读者仍活跃的前提未满足，单独保留这一覆盖边界。

【边界】未检验“正常停止服务必须无损保留沙箱”，本轮也没有更改显式停止契约；完整删除竞争、超时取消和其他故障矩阵仍未完成。

## 5. 建议与改进项

1. 将正常 drain、角色崩溃、整个节点故障分别命名和验收，不能统一写成“重启通过”。
2. 对旧依赖先确认实际运行时 FD，再确认权威引用；不能让最新 checkpoint 的引用掩盖旧依赖丢失。
3. 进程崩溃恢复后检查未 checkpoint 的最新状态和真实 VMM 身份，防止从旧恢复点重新创建实例冒充原进程接管。

## 6. 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
Q="$N/round-365f797-20261023.clPWh2h0"
S="$Q/tap-checksum-fix/storage"
cat "$S/restart-matrix01/terminal.json"
cat "$S/restart-diagnosis01/unit-shutdown.stdout"
cat "$S/restart-diagnosis01/vm-now.stdout"
cat "$S/restart-matrix02/current.json"
cat "$S/restart-matrix02/terminal.json"
```

修正版为 `sdk-reader-restart02.py::crash_owned_role` 和 `run-restart-matrix02.py`；信号前后目标身份、返回值、进程重新启动事件、before/after 权威记录和 VMM 观察均独立保存。不要在已有活跃用例上重复发信号。

## 7. 现场清理披露

首次正常停止仅清理了本任务专属测试沙箱，未误伤其他任务；原沙箱已不存活，不继续尝试读取或把它当作保留读者。新矩阵每次只使用一个专属沙箱，成功后删除、失败保留依赖及证据。监督进程、sandboxd、其他沙箱或共享服务不作为信号目标；运行时/模板、宿主参数与父仓组件指针未变。
