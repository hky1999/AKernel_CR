# PR #119 Firecracker 私有可写盘独立目录接入检查

后续状态：本篇记录目录候选的首次接入和失败。停止未确认时保留目录的保护已与网络恢复修复合入 qa02，组合 ELF debbf268… 已部署；相同 Pod 双向即时故障与固定镜像官方 76 项 SDK 通过，后续完整矩阵仍在执行。独立 qa04 的 932adc2f… 仍未单独部署，不能与组合制品混记。详见 [网络恢复与后续验证](20261024T-pr119-retired-network-lease-recovery.md)。

## 1. 问题

继续已完成真实就绪门的完整 SDK 验收，并推进计划中的“JuiceFS 原生克隆”对照。检查能否只将 Firecracker 的私有可写盘 overlay.ext4 放在 JuiceFS，保留内存和运行状态位置，使后续差异可以归因。

## 2. 方法

源码基线为 sandboxd e3f402c（已修复设备 I/O 完成后再复制盘的顺序）。独立开发分支 codex/pr119-fc-writable-directory-20261024。沿用已验收 AKernel 365f797 / 实际 ADX 6fb53d7、公共 SDK 0.2.0rc3 / 原生 SDK 0.1.0rc3，当前运行 sandboxd c85d58b2… 不变。

新代码在 config/config.go 增加 writable_storage_dir / writable_storage_filesystem；writable_directory_linux.go 验证挂载 ID、目录 inode、实例随机代次和归属标记，使用持有目录句柄定位实际复制/删除目标。handler.go / checkpoint_handler.go 仅分离 overlay 路径，运行内存、virtio-fs staging 和状态不随之搬迁。Delete 在外部盘清理成功前保留所有权和重试状态；已有默认路径不变。

全部编译测试在 BareMetal 自有 Podman graph 的独占容器，2 CPU / 6 GiB、私有 cgroup 和 mount namespace、网络 none。没有本地编译测试或共享环境修改。

## 3. 数据

| 执行 | 结果与口径 |
|---|---|
| fc-writable-qa01 | 新代码成功编译；归属/位置、错误配置和重启清理重试通过；设备顺序既有回归仍通过。挂载替换已拒绝，但测试自身未先关闭目录 FD，卸载 EBUSY 导致测试清理失败；不是产品损坏或挂载保护失败。原件保留，容器已退出，其私有挂载不作用于宿主。 |
| fc-writable-qa02 | rc=0：修正测试清理顺序后，选定三轮回归、全仓格式/vet/单测、FC race、生产构建通过。ELF efa639832d602aced279071deacf81fb334c0adba1d401883c6fa43e5170a3f9。 |
| fc-writable-image-proof01 | rc=0：三节点逐层核对 CRI 48d1321c… → leaf 336cdaf9… → config c63d9f0f…，实际平台 linux/amd64。准备器最初误要求单镜像描述符含 platform，失败保留，未部署即停；只读核对实际 config 后继续，未关闭摘要门。 |
| fc-writable-sdk01 | 76 项官方 SDK 与各三轮完整状态通过，gVisor 双向节点故障/重入通过。FC 目标恢复后源重入因缺失 TAP 租约失败，整轮 rc=1；压力/进程重启未启动。 |
| fc-writable-qa04 | 加上 Start/Restore 停止未确认时的目录/状态保留保护，全仓源码门与 race 通过；新 ELF 932adc2f… 未部署，不与 efa63983… 的 SDK 结果混记。 |

## 4. 结论

【源码】独立 RWFS 目录是当前 FC 做公平后端对照所需的小范围接入；整体 bind filestore 会同时改变内存与 virtio-fs 数据位置，不适合作为仅 RWFS 的实验。

【实测】现有就绪门与完整 SDK 的通过记录见 20261024T-pr119-fc-disk-cut-fix-stage-summary.md。初始候选 efa63983… 已在独立集群完成官方 SDK 与状态回滚，但源重入失败；新的停止保留保护只过源码门。不能把部分结果计为整条原生克隆路线通过。

## 5. 建议与改进项

优先处理已在真实节点退出/重入暴露的缺失 TAP 租约，详见 20261024T-pr119-fc-kind-rejoin-missing-tap.md；之后补 FC 反方向、持续写和进程重启。计量必须包括普通运行写入、checkpoint 与恢复阶段的对象读取/写入；Full 内存保存保持原实现。宿主改挂载或改路径前必须排空实例，本选项不提供运行中的存储迁移协议。当前节点可写容量公告仍来自原 filestore；独立实验限制容量/并发，生产接入前须把实际远端后端的空间纳入 ADX 配额和准入，不能将原本地磁盘可用量当作 JuiceFS 可用量。

## 6. 可复现步骤

源码候选尚未提交，不将其作为已交付版本。远端任务位于原 PR119 独立实验目录 tap-checksum-fix/fc-writable-qa0{1,2}；各有 source/、qa.sh、driver.py、launch.json 和 terminal.json。执行核心为：

```sh
gofmt -l .
SANDBOXD_FC_WRITABLE_MOUNT_TEST=1 SANDBOXD_FC_CAPTURE_IO_TEST=1 go test -count=3 -run '^TestFirecracker(Writable|CheckpointIncludesWriteCompleted|CheckpointInvalidatesBase)' ./pkg/runtime/firecracker
make vet
make test TESTFLAGS='-count=1'
SANDBOXD_FC_WRITABLE_MOUNT_TEST=1 SANDBOXD_FC_CAPTURE_IO_TEST=1 go test -race -count=1 ./pkg/runtime/firecracker
make release-binary
```

必须在独占特权容器及私有 cgroup/mount namespace 执行显式挂载门；不得在共享宿主直接运行测试 helper。

## 7. 现场清理披露

qa01 的测试容器及辅助进程已经退出；失败原件留在任务目录，没有改写。qa02 只构建自有候选；后续 sdk01 已切换本任务五个业务角色 Pod，并创建任务专有 JuiceFS 根目录，官方和状态实例均完成；跨节点失败时保留依赖，后续盘点 Environment=0/VM=0，但实验根仍有 1 份私有盘。未人工清扫或清空资源 DB。未修改旧环境、共享服务或宿主参数。任务 XFS 预留至少 650 GiB；后续部署和回收另记实际结果。

### 本轮性能与内存口径补充

一实例三轮 FC Full 保存 5462/7516/7960 ms，盘保存 15/15/14 ms、恢复准备盘 12/12/13 ms；约 2 GiB PUT/轮。旧本地盘样本分别 8602/11223/11657、2863/3135/3298 ms 和约 3 GiB PUT。这不是交替后端性能结论；两组各为一实例连续三轮。新实例创建约 1073 ms、64 MiB 根文件随机字节写入并同步约 516 ms，普通运行流量也进入对象存储。

“内存位置不变”不表示所有内存文件都本地：普通 File 恢复仍私有映射 JuiceFS checkpoint；启用 virtio-fs 的 SharedFile 才把 memory.live 留在本地 XFS。原始 SDK 驱动的 memory_placement 字段硬编码为 unchanged local filestore，不够准确；脱敏回执已附元数据更正，执行原件保留。内存保存仍为 Full，没有按这次盘克隆结果宣称内存优化或全 VM 按需恢复已经达标。
