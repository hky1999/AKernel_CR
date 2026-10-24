# gVisor 文件数据快照与后台恢复的顺序检查

## 1. 问题

复用现有 filestore 捕获/采纳时，后台恢复尚未装入全部私有文件数据就再次 checkpoint，是否仍能得到同一时刻的完整文件副本；不能仅证明空闲状态下 JuiceFS 克隆能成功。

## 2. 方法

只读 `.5` 精确源码 87e8441b6db18219fbb941378cfcb2883750b07c 和未提交原生克隆候选。沿 Loader.saveWithOpts→control.State→Kernel.SaveTo→snapshotFilestores→SnapshotToFd，再对照 AsyncMFLoader 和 MemoryFile.SaveTo。尚未构建/执行确定性交错测试，不将源码窗口冒充数据损坏实测。

## 3. 数据

| 位置 | 事实 |
|---|---|
| kernel_restore.go:AsyncMFLoader/backgroundGoroutine | 后台装入不仅包含应用内存，也包含 private MemoryFiles；pgalloc.LoadOpts.PagesFile 被传给相应 LoadFrom |
| boot/restore.go:postRestore | 应用在后台页全部加载完成之前已经可以执行，随后才等待 asyncMFLoader.Wait |
| tmpfs/save_restore.go:PrepareSave | 将 private MemoryFile 登记到保存集合，没有在这里等待后台装入 |
| kernel/kernel.go:SaveTo | 在序列化内存页之前先执行 snapshotFilestores；quiescePausedAnd 停任务/时间及应用内存淘汰，不等同停止后台私有页写入 |
| pgalloc/save_restore.go:SnapshotToFd | 克隆、Sync、指纹，没有先调用 AwaitLoadAll |
| 同文件 MemoryFile.SaveTo | 到后续序列化入口才调用 AwaitLoadAll；该等待晚于已经发生的外部文件克隆 |

这说明“运行任务已暂停”不能单独推出“后台恢复不会再写入 filestore”。尤其从旧 full 格式的异步恢复切到 external-content 捕获时，需要实际屏障回归验证。原生格式恢复可能没有相同的私有页装入任务，也不能因此跳过兼容场景。

## 4. 结论

【源码】存在必须补证的顺序窗口：外部副本可能在私有页后台装入结束之前捕获，后续 SaveTo 的等待无法把晚到页面补回旧副本。当前尚未动态复现，不宣称已经产生损坏，也未部署候选。

【待实测】正式接入前应让 SnapshotToFd 在复制之前完成 AwaitLoadAll，并传播加载失败；该等待本来就在随后 SaveTo 路径，调整到真实捕获之前才符合快照边界。仍需检查淘汰/后台写入的全部约束，而非只加一次调用便宣称验收。

## 5. 建议与改进项

下一步使用真实 pgalloc 异步页加载加可控读取屏障，先证明旧顺序会提前生成副本；修复后必须等屏障释放，再验证全部数据/指纹，加载失败不得发布。覆盖 full 后台恢复→外部格式再次保存，以及后台期间应用修改、早期 checkpoint、两分支和源继续执行。该回归与当前 CloneFilestore 的独立函数验证分开记账；函数通过不代表此顺序已修复。

## 6. 可复现步骤

只读检查当前工作树或精确 Git 对象；不在本地运行测试：

```sh
git -C /home/keyang/AKernelWorkspace/codex-pr119-gvisor-native-clone-20261024 show 87e8441b6db18219fbb941378cfcb2883750b07c:pkg/sentry/kernel/kernel_restore.go
git -C /home/keyang/AKernelWorkspace/codex-pr119-gvisor-native-clone-20261024 show 87e8441b6db18219fbb941378cfcb2883750b07c:pkg/sentry/kernel/kernel.go
git -C /home/keyang/AKernelWorkspace/codex-pr119-gvisor-native-clone-20261024 show 87e8441b6db18219fbb941378cfcb2883750b07c:pkg/sentry/pgalloc/save_restore.go
```

确定性交错、源码质量门及完整 SDK 只在 BareMetal 本任务新输出目录，尚待执行。

## 7. 现场清理披露

本检查只读源码和新增文档。没有改现役 runtime、模板、模块、共享服务或旧环境，没有启动额外测试。当前 helper 阶段仍只验证克隆函数，不把它标成整个 gVisor 候选已验收。
