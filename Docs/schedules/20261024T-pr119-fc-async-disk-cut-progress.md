# Firecracker 异步磁盘与内存一致切面进度

日期：2026-10-24。旧代码确定性组件回归确认不一致；源码门、完整 SDK、双向接管及实际持续直接 I/O 全通过，e3f402c 已提交推送。新的 RWFS 后端尚未实现/验收。

## 开发内容

原生克隆能力通过之后，检查实际 FC/JuiceFS 运行布局的前提。历史原型为 Sync，当前 SDK 为 Async；固定 sandboxd 在 VMM 排空异步 I/O 前复制可写盘，可能漏掉保存的内存/设备已认为完成的写。必须先验证并修正切面，再比较新存储布局，不能仅靠更快克隆数值推进。

## 修改内容

- 独立组件工作树 `codex-pr119-fc-drain-order-20261024`，分支 `codex/pr119-fc-drain-order-20261024`，基于 10312f2，三文件提交 e3f402c0a18be3ff0b7d90674daae9459464772a 已普通 push 并核对远端；不混入其他工作树。
- `checkpoint_io_cut_linux_test.go`：调用真实 Handler.Checkpoint，后端 HTTP 夹具在保存设备时完成固定大小写并记录摘要；比较真实克隆结果，覆盖默认克隆和强制回退。额外验证内存窗口消耗后盘失败时，旧基线文件仍在但失效标记必须置位、失败代无清单、源进程仍存活。不是 KVM/io_uring 真实故障注入。
- `Checkpoint`：VMM 快照成功后、仍保持暂停时复制盘；失败则标记内存谱系失效并清理本代；同步调整 snapshot/overlay/resume 日志计时的实际区间。
- `doc/checkpoint-restore.md`：同步捕获顺序、失败基线处理、可能增加的写回成本与独立 I/O 错误传播边界。
- 远端 regression01 夹具因退出通道未初始化而 panic，保留原件；regression02 初始化正确后取得内容断言旧红。新候选另存 fc-io-cut-fix01，未修改已验收源码树或现役服务。

## 测试结果

fc-io-cut-regression02 驱动 rc=0：旧测试实际 rc=1，默认/回退两子例均失败到内容断言，完整 Handler 返回成功但盘遗漏后端保存时已完成的写。此前 regression01 是无效夹具失败，未计入该结论。

fc-io-cut-fix02 rc=0：三次指定回归、fmt/vet、全仓 make test、FC 包 race 和生产构建通过，远端 2 CPU / 6 GiB / 1024 PID 私有容器。fix01 原件保留，其失败断言错误要求失效后保留路径；按已有契约加强为失效、清空路径/增量标记且物理旧文件不变，未改状态实现迁就测试。

fc-io-cut-sdk02 rc=0：官方 gVisor/FC 8+30 各一组、共 76 全通过无跳过；各三轮 512 MiB 完整内存、64 MiB 根文件回滚，以及 A→B/B→A 自动接管四方向通过。首次 SDK 替换身份门失败保留，0 个 SDK 请求；随后证明 CRI 索引→叶 manifest→config，沿用已部署候选通过，没有跳过摘要或反复重启。实际 ELF c85d58b2…，余下十项载荷/Secret UID 等保持核验。

fc-direct-io-accept01 rc=0：真实 FC guest 不断执行 4 KiB O_DIRECT 写、fdatasync、直接读回，5 次保存、4 次恢复、跨节点分支同时写、再次保存/恢复通过。与组件确定性夹具分开，不称真实内核停顿注入或性能样本。当前一次三轮 Full 状态样本为 FC checkpoint 8602/11223/11657 ms，仍每轮约 3 GiB PUT；不是三独立实例或稳定性能结论，旧十组记录不改写。

源码、实际制品、SDK 和持续写分别留证。VMM 排空错误传播、内部删除屏障/多 collector、生产 HA 与两条新后端仍有剩余；没有将本轮验收升级为生产完整关闭。

## 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
D="$N/round-365f797-20261023.clPWh2h0/tap-checksum-fix"
cat "$D/fc-io-cut-regression02/terminal.json"
cat "$D/fc-io-cut-regression02/out/regression.stdout"
cat "$D/fc-io-cut-fix02/terminal.json"
cat "$D/fc-io-cut-sdk02/terminal.json"
cat "$D/fc-direct-io-accept01/terminal.json"
```

读取不到终态时检查原回执和进程启动代次，不重发编译/测试。完整检查见 `Docs/checks/20261024T-pr119-fc-native-clone-runtime-preflight.md`。本任务独立 Node/控制 Pod 已改用候选镜像，但 RWFS/内存模式、运行时 bundle、共享服务、旧环境和宿主参数未改。全部实例和快照删除，Environment=0，空闲约 687.8 GiB；不在本地编译测试。
