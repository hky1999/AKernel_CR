# PR #119 gVisor 跨节点恢复后 RWFS 的实际介质检查

日期：2026-10-23。结论：本轮固定组合恢复后的私有 RWFS 文件后端确实位于 XFS；此前观察器漏掉了 `/filestore/` 别名。应用内存 memfd 与私有 RWFS 后端是两份不同的文件，不能混为一谈。

## 1. 问题

在补齐 PR #119 SDK 后，需要确认 gVisor 跨节点恢复后的 RWFS 实际在哪里，作为后续 JuiceFS 原生克隆适配依据。不能仅凭 `/home/akernel/filestore` 配置在 XFS，或仅看到内存 memfd，就推出 RWFS 的介质。

## 2. 方法

【实测】沿用 AKernel `365f797`、实际 ADX `6fb53d7`、sandboxd `d5acc3b` 加 TAP 补丁和已验收镜像；runsc 实际输出对应源码 `7fdef444b108`。没有换二进制或本地编译测试。

额外运行一条 B→A 公共 SDK 故障接管，保留 512 MiB 确定性内存、1 MiB 根 RWFS、源离线、源重入和删除判断，仅将只读观察器改为枚举运行时所有普通文件 FD。对 `/proc/<pid>/fd/<n>` 使用 `stat -f -L` 核验实际文件系统，不依赖父进程能否按文件名找到该文件。

【源码】读取与实际 runsc 版本匹配的固定提交，区分根 overlay 的私有 MemoryFile 与应用内存 MemoryFile。源码阅读不是新的运行时构建或验收版本。

## 3. 数据

| 对象 | 目标节点实测 |
|---|---|
| 根 RWFS 文件后端 | runsc-sandbox 持有 `/filestore/runsc-filestore-<id> (deleted)`，FD 的文件系统为 `xfs`，逻辑大小 1073741824 字节，与沙箱 1 GiB 存储配置一致 |
| 应用内存文件 | 同一 runsc-sandbox 另持有 `/memfd:runsc-memory (deleted)`，文件系统为 `tmpfs` |
| 功能负载 | 536870912 字节内存、1048576 字节根文件验证通过；源节点离线时目标继续执行，源重新加入后目标不变 |
| 清理 | 源健康恢复，测试沙箱删除成功；此额外样本是介质诊断，不并入五轮性能样本或原四例跨节点性能统计 |
| 原观察缺口 | 原过滤器只选 `/home/akernel/`、`/mnt/akernel-shared/`、memfd，漏掉运行时命名空间内的 `/filestore/` 路径 |

源码证据链：

- sandboxd `pkg/runtime/runsc/client.go::RootFileOverlay` 生成 `root:dir=<filestore>`；Handler 的 Start/Restore 都调用 `resolveRootOverlay`，并创建相应 runsc 实例。
- 固定 gVisor [vfs.go::configureOverlay](https://github.com/akernel-dev/gvisor/blob/7fdef444b108/runsc/boot/vfs.go#L763) 在存在 filestore FD 时创建专用私有 MemoryFile，交给 upper tmpfs。
- [vfs.go::configureRestore](https://github.com/akernel-dev/gvisor/blob/7fdef444b108/runsc/boot/vfs.go#L1789) 按资源身份 `/` 建立私有 MemoryFile 映射；[tmpfs::loadMf](https://github.com/akernel-dev/gvisor/blob/7fdef444b108/pkg/sentry/fsimpl/tmpfs/save_restore.go#L38) 按该身份取回文件后端。
- [loader.go::createMemoryFile](https://github.com/akernel-dev/gvisor/blob/7fdef444b108/runsc/boot/loader.go#L1074) 创建的是另一份 `runsc-memory` memfd；不能据此推断根 RWFS 也使用这一份文件。

原始记录在远端 `acceptance/runs/shared-tapfix-direct01-runsc-media-cross-1/target-storage.private.json`，成功终态在 `tap-checksum-fix/storage/media-diagnostic01/terminal.json`。脱敏证据见 [gvisor-media.json](evidence/pr119-juicefs-tapfix-20261023/gvisor-media.json)。

## 4. 结论

【实测】当前组合跨节点恢复后的私有 RWFS 使用目标节点 XFS 文件后端；应用内存使用 tmpfs 上的 memfd，二者分开。checkpoint 仍由 JuiceFS 提供。

【解释】`(deleted)` 表示文件名已移除，运行时仍通过打开的 FD 持有文件及数据，并不表示正在运行的 RWFS 已丢失。这一生命周期不能简单替换为靠路径重新打开文件。

【边界】本次没有证明 JuiceFS 原生克隆已经接入，也没有证明可直接把 checkpoint pages 采纳为 RWFS。后续仍需对保存格式、私有 MemoryFile 载入和 FD 生命周期做适配与故障验收。

## 5. 建议与改进项

1. 长期观察器按运行时身份选进程，再检查 FD 的实际文件系统；不要仅按宿主路径前缀判断介质。
2. 原生克隆优先复用现有私有 MemoryFile/filestore FD 接口及已实现的后端能力，保留匿名文件和进程重启语义。不要重写应用内存机制来凑统一后端。
3. 后续在独立配置中比较文件型后端，完整覆盖克隆隔离、恢复后写入、再次 checkpoint 和跨进程引用保护。

## 6. 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
Q="$N/round-365f797-20261023.clPWh2h0"
S="$Q/tap-checksum-fix/storage"
cat "$S/media-diagnostic01/terminal.json"
cat "$S/gvisor-media-summary01.json"
```

本轮夹具为 `S/sdk-failover04.py`，调用入口 `S/run-media-diagnostic01.py`；复用原 SDK 故障接管，仅替换 FD 观察代码。完整原始事件和已删除沙箱的观察结果已保存，不能对已经退出的 PID 重做活体判断。

## 7. 现场清理披露

只停止并重新启动身份匹配的本任务源 Kind 节点；目标和控制节点保持运行。测试沙箱已删除，未替换运行时、修改共享服务或宿主参数。存储、代理和任务集群保留供后续故障门，组件提交指针未变。
