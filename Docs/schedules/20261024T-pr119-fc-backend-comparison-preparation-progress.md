# FC 同代码后端交替测量准备

## 开发内容

在 fdb145c 完整功能验收后，只切换私有盘位置，建立运行写入、保存停顿/完成、恢复与对象流量的公平对照。旧试跑写入包含 SDK 命令和数据生成，新增 guest 内拆分时钟；不拿单次克隆耗时替代业务性能。

## 修改内容

新增验收负载 guest-storage-io.go 和 sdk-backend-compare01.py；不改 sandboxd 或 VMM。固定随机种子和字节数、分开 write/fsync、两代完整 SHA/内存校验、保存前/恢复后实际 FD/介质核对。run-backend-compare01.py 只在原私有任务中删除/恢复两个后端字段，核对十个运行文件与镜像、真实新会话/资源、Secret UID 和控制/API/Redis Pod 身份；每步失败不继续。

容量前检改用现有 RGW 客户端的实时 ceph df。原 CR 缓存已过期，第一次 CLI 缺少 daemon 使用的 MON 连接参数；补继承现有参数后查询成功，没有改配置或授权。方法与字段口径见 `Docs/checks/20261024T-pr119-fc-backend-comparison-clock-capacity.md`。

## 测试结果

远端独占 Go 构建与两次 64 KiB/4 次覆盖的独立 SHA、确定性数据和计时形状校验通过；ELF f11e2a32…，源码 844a7d60…。对象后端实时可用约 38.95 GiB，试跑具备容量条件；每轮另设对象后端 10 GiB、宿主 650 GiB 门。两个实际 SDK 布局试跑整体 rc=0：相同 64 MiB 文件摘要、各两次 checkpoint/reload、完整应用内存和四次实际介质证明通过，实例与快照删除。正式十组交替已启动，续记时完成 9/20 个实例、18 次完整状态校验，尚待正式终态。试跑小块同步写显著变慢，须和 checkpoint 收益一起比较，不能只报快照提速。产品始终 fdb145c 对应 debbf268… / image02，不重建或更换。

## 可复现步骤

查看远端 fc-backend-io-build01、fc-backend-compare-smoke01 的 launch.json / terminal.json，正式任务已由依赖驱动在试跑成功后启动，先查 current/terminal 与 PID/start_ticks，不能重复运行 --pairs 10。命令级顺序见上述检查第 6 节。旧错误、原始配置和元数据留远端，外发仅白名单，全部编译测试只在 BareMetal 任务资源内。
