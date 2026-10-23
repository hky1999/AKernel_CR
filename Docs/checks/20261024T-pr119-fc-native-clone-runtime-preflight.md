# Firecracker 原生克隆路线：实际 VMM 与异步磁盘一致性前检

日期：2026-10-24。前检发现顺序缺口，远端组件旧红/新绿、完整 SDK、双向接管及实际 guest 持续直接 I/O 验收通过。源码 e3f402c 已提交推送；本任务改用修复后的 sandboxd，没有切换 RWFS 后端、I/O 引擎或 checkpoint 模式。

## 1. 问题

JuiceFS 原语及 FC 现有 Go 克隆函数通过后，能否直接将实际 SDK 的私有 RWFS 改到 JuiceFS？当前运行制品是否有已有增量能力？历史原型覆盖了哪些前提？

## 2. 方法

在任务独立集群只读取得当前 Node Pod 的 `/opt/firecracker/manifest.json`，核对实际 VMM SHA-256 与此前 SDK 候选一致。源码检查使用该 manifest 对应的 b9a362d1070ee17991e7388d3b53a9ccce25ecca，而非任意本地旧 fork。

同时读取 sandboxd 10312f2 的 Checkpoint、pause 和 createSnapshot 调用顺序，以及本仓历史 FC/JuiceFS 脚本。随后在远端独占容器调用真实 Handler.Checkpoint，Unix HTTP 后端夹具在 snapshot/create 中完成一项原已提交的固定大小写入，并把其摘要保存为设备/内存状态。逐字比较真实克隆盘与该状态，不依赖时间竞争。2 CPU / 6 GiB、私有 cgroup/网络命名空间，未操作共享服务；这不是实际 KVM/io_uring 注入。

## 3. 数据与源码链

| 项目 | 证据 |
|---|---|
| 实际 VMM 来源 | manifest.vmm.source=fork-source-build，commit=b9a362d…，ELF SHA-256=41133331123c05d635a1a4a61a1eb41f078e9a216b5a197c1398e4e64e957cbf；不能仅从 v1.16.1 版本字符串推断为未经修改的官方 ELF |
| 当前 I/O 引擎 | 私有 profile 显式 Async/Writeback；历史 `tools/cn-f1jfs-20261011/f1-jfs-rwfs-v2b.sh` 的真实 VMM 原型为 Sync，且明确未证明通用在途 I/O 排空 |
| sandboxd 捕获顺序 | checkpoint_handler.go:186 暂停；:230 克隆 overlay；:244 发起 VMM 内存/设备快照。guest sync 发生在暂停前，而且失败不阻止捕获 |
| pause 的实际含义 | VMM rpc_interface.rs:896 调 pause_vm；lib.rs:483 只暂停 vCPU，没有在该路径排空块引擎 |
| 块队列排空位置 | lib.rs:514 调设备保存；device_manager/persist.rs:242 调 prepare_save；block/virtio/device.rs:599 才 drain_and_flush(false)，并处理异步完成队列。该阶段在上述 overlay 克隆之后 |
| 排空失败传播 | 同 device.rs:588 的 drain_and_flush 包装只记录错误；不能从该调用存在就推断 I/O 错误一定使快照失败 |
| 已有内存能力 | vmm_config/snapshot.rs 明确包含 Full、Incremental、SoftDirty；配套 sandboxd 有父内存克隆与增量选择。当前 SDK/十组性能 profile 仍用 Full，未验这些模式 |
| 确定性组件旧红 | fc-io-cut-regression02 驱动 rc=0，实际旧代码测试 rc=1；默认克隆与强制复制回退均失败到“盘副本漏掉保存的设备/内存已完成写入”的内容断言，非编译/权限失败 |
| 修复后的源码门 | fc-io-cut-fix02 rc=0；默认/强制回退及失败基线处理各三轮，fmt/vet、全仓 make test、FC 包 race、生产构建通过 |
| 实际 SDK | fc-io-cut-sdk02 rc=0；官方 8+30 / 8+30 共 76，无跳过，两运行时各三轮 512 MiB 内存/64 MiB 根文件、四条双向自动接管通过 |
| 实际持续磁盘写 | fc-direct-io-accept01 rc=0；FC guest 在 1 MiB 环形文件内不断 4 KiB O_DIRECT 写、fdatasync、直接读回；5 次保存、4 次恢复、跨节点两个分支持续写及再保存，内容与进程身份通过 |
| 当前实测制品 | sandboxd c85d58b2efe8c141394877cc73cdb33cd796d7760770a31c808fbd6c22fb5dce；VMM/kernel/initrd/runsc/ADX/Execd 未变；与提交 e3f402c 的三文件逐 SHA 相同，二进制于提交前已构建验收 |

精确源码：[sandboxd Checkpoint](https://github.com/hky1999/sandboxd/blob/10312f28c9b3286545eb2e97070cdd08fe994cee/pkg/runtime/firecracker/checkpoint_handler.go)、[VMM pause/save](https://github.com/hky1999/firecracker/blob/b9a362d1070ee17991e7388d3b53a9ccce25ecca/src/vmm/src/lib.rs)、[设备保存](https://github.com/hky1999/firecracker/blob/b9a362d1070ee17991e7388d3b53a9ccce25ecca/src/vmm/src/device_manager/persist.rs)、[块引擎准备](https://github.com/hky1999/firecracker/blob/b9a362d1070ee17991e7388d3b53a9ccce25ecca/src/vmm/src/devices/virtio/block/virtio/device.rs)、[内存模式](https://github.com/hky1999/firecracker/blob/b9a362d1070ee17991e7388d3b53a9ccce25ecca/src/vmm/src/vmm_config/snapshot.rs)。

## 4. 结论

【实测身份与源码】当前制品确为固定 fork 构建，已有增量能力可继续复用；并非必须先重写内存机制。但仅凭源码有选项，不能宣布本轮已通过增量模式的 SDK/恢复后再次保存。

【源码确认的顺序缺口】当前 overlay 克隆发生在 VMM 保存时的块 I/O 排空之前。vCPU 暂停和先前一次 guest sync 不能单独证明这个间隙没有在途写完成；慢后端或持续写入时应补确定性交错，检查盘副本与保存的内存/设备是否属于同一切面。

【组件实测】真实 Handler 与确定性后端完成夹具已复现该内容不一致，两条复制路径都失败。没有将仅检查函数调用顺序作为回归结论。原语和此前无此屏障的 SDK 样本通过，不覆盖这个交错。

【源码修复与实测】盘复制已移到 VMM 保存后、继续保持暂停；若随后盘复制失败，立即使已消耗的内存窗口失效，并修正阶段计时。e3f402c0a18be3ff0b7d90674daae9459464772a 已普通 push 到 hky1999/sandboxd 的 codex/pr119-fc-drain-order-20261024。完整 SDK 与实际持续写负载均通过，旧 faa725f 的原测量组合保留为历史输入。

【边界】真实持续写测试没有人为卡住内核 io_uring 的完成时机，不能冒充真实 KVM 的确定性故障注入；确定性交错由组件层真实 Handler + 后端夹具验证。O_DIRECT 指 guest 文件 FD，host 仍按原 Async/Writeback 配置。未关闭 VMM 内部排空错误只记日志的传播问题，也未据此关闭整个生产故障矩阵。

新制品的一实例三轮诊断为 FC checkpoint 8602 / 11223 / 11657 ms、SDK reload 3847.9 / 3785.8 / 3808.9 ms；内存阶段 5289 / 7746 / 8080 ms、盘复制 2863 / 3135 / 3298 ms。每轮约 3 GiB PUT，后两轮仍有约 0.91 / 1.01 GB GET。这些是同实例相关样本，不是三独立实例，不与原十组统计宣称稳定收益；说明一致性修复没有解决全量上传瓶颈。

证据见同目录 evidence 下 `fc-async-disk-cut-{old-red,source-gates,image-identity,official-sdk,sdk,direct-io}.json`。单文件原生克隆通过仍不等于运行期 RWFS 已迁入 JuiceFS。

## 5. 建议与改进项

1. 在相同修复制品下进入 FC Async + JuiceFS 私有运行文件实验，明确首轮迁移、分支、再次保存、退出清理和 I/O 故障。只改变 RWFS 放置，gVisor 另按 filestore 接口推进。
2. 当前采用“设备/内存保存后再克隆盘”的修复。保持计量写回和克隆顺序成本；源 VMM 内部排空错误传播仍需单独故障验证及必要修改，不能用更多 guest sync 或 HEAD 代替。
3. 在独立配置验证已有 Incremental/SoftDirty 与同卷父内存克隆，和 Full 分组记账；不将模式改变混成后端收益。保留 Full 对照和恢复输入保护。

## 6. 可复现步骤

```bash
# 远端任务命名空间中，先查询本任务当前 Node Pod 和 UID。
kubectl -n akernel get pods -o wide
kubectl -n akernel exec <本任务当前NodePod> -- cat /opt/firecracker/manifest.json
# 在固定 sandboxd 源码中只读查看捕获顺序。
git show 10312f28c9b3286545eb2e97070cdd08fe994cee:pkg/runtime/firecracker/checkpoint_handler.go
git show 10312f28c9b3286545eb2e97070cdd08fe994cee:pkg/runtime/firecracker/api.go
```

当前现场所有 kubectl 经 `N/cluster/namespace-lab07.py run --task N --` 进入独立集群，不直接使用宿主默认 kubeconfig。组件证据位于 `Q/tap-checksum-fix/fc-io-cut-regression02/{terminal.json,out/regression.stdout}`；通过的源码门为 fc-io-cut-fix02，完整 SDK 为 fc-io-cut-sdk02，实际持续写为 fc-direct-io-accept01。三个 terminal.json 均 rc=0。

新远端源码可 fetch codex/pr119-fc-drain-order-20261024 后 checkout e3f402c；在两个独立源码目录分别取 10312f2 和 e3f402c，旧目录只拷贝新提交的该回归文件，显式运行 `SANDBOXD_FC_CAPTURE_IO_TEST=1 go test ./pkg/runtime/firecracker -run '^TestFirecrackerCheckpointIncludesWriteCompletedDuringDeviceSave$'`，旧应失败、新应通过。必须在任务独占、可写私有 cgroup 命名空间的受限容器内运行，不在宿主默认 cgroup 或开发机执行。

## 7. 现场清理披露

前检仅只读；组件测试只操作自己的子进程/cgroup。首个夹具漏初始化退出通道而 panic，regression01 保留、不计产品红；fix01 的故障断言误以为失效后路径仍保留，查明既有契约要求清空后，加强为 flag=true/path空/incremental=false 且旧物理文件不变，fix02 全通过。

私有 SDK 替换首次被 CRI 索引/叶 manifest 的差异拦住，未创建 SDK 实例；随后三个节点逐层证明 ff06cd24…→d5a31f72…→config 6d3ec747…，实际 daemon 是 c85d58b2…。复用既有部署和原部署前会话，未重启碰运气，sdk02 完整通过。全部实际沙箱、分支和具名快照已删除，Environment=0；任务集群/存储保留、当前运行修复制品，空闲 738466033664 字节。旧环境、共享服务、宿主参数不变，没有本地编译测试。
