# JuiceFS 原生克隆与 Firecracker 现有复制函数复用检查

日期：2026-10-24。原语和现有 Go 辅助函数通过；尚未完成新的运行时配置或完整 SDK 路线验收。

## 1. 问题

在完成 PR #119 主链路和当前版本性能基线后，JuiceFS 原生克隆是否能直接复用？Firecracker 是否需要新造复制函数？gVisor 的 FICLONE 接口能否直接套用？

## 2. 方法

全部运行、编译和测试在 BareMetal 本任务独立环境执行。保持 AKernel 365f797 / ADX 6fb53d7 / sandboxd 已测源码 10312f2、实际 ELF 和共享服务不变。两独立执行节点 Pod 访问同一 JuiceFS 1.4.1 命名空间；测试目录不在 ADX artifacts 内，仅存带随机任务身份和 inode 记录的自有文件。未创建沙箱、设备或新服务。

源客户端创建并同步 64 MiB 确定性随机文件，目标客户端仅检查小型 owner 记录与源文件属性，克隆前不读源数据。分别尝试 FICLONE（整文件写时复制 ioctl）与 copy_file_range（Linux 文件间范围复制系统调用），核对真实 fuse.juicefs 挂载、源目标不同 inode、完整摘要和 S3 网关计数。clone 到 fsync 前后的计数单列，后续完整读校验不混入这段窗口。

另从已验收源码复制未经修改的 `pkg/runtime/firecracker/reflink.go` 到独立编译目录，SHA-256 为 `81d641cc729863f33e03f0f89866981cb8c0dbd837ef22239c112631c8654227`。通过只依赖 Go 标准库的测试夹具调用实际 `cloneFileNoSync`，再显式 fsync 模拟后续持久化边界。Go 1.25.5 编译容器限制 2 CPU / 2 GiB，网络关闭；测试二进制只在本任务 Node Pod 执行。这是原函数的独立能力测试，不冒充整个包或真实 VMM 的验收。

## 3. 数据

| 检查 | 结果与口径 |
|---|---|
| FICLONE | 返回 EOPNOTSUPP，errno=95；当前挂载不支持此入口 |
| 目标客户端未读源数据的 copy_file_range | 64 MiB，一次系统调用，包含目标 fsync 10.410 ms，S3 GET/PUT 请求和字节均为 0 |
| 两客户端、两独立可写分支及下一代恢复 | 完整摘要通过；父文件不变；修改不会串到另一个分支或已保存版本 |
| 打开后删除源文件的 FD | nlink=0 的 64 MiB 文件可克隆，完整摘要通过 |
| 未刷新 mmap 修改 | 克隆前 smaps 观察到 8 KiB 脏页；克隆保存当时内容，源随后继续修改不会改变保存版本 |
| 截断后扩展、打洞 | 扩展区和打洞区读零，下一份克隆内容正确，原父文件不变 |
| 现有 cloneFileNoSync | 64 MiB，函数 3.500 ms，随后 fsync 总计 4.642 ms，返回 reflinked=false，S3 GET/PUT 均为 0，完整源/目标摘要相同 |
| 目的文件已存在 | 原函数拒绝覆盖，O_EXCL 契约保留 |

这些耗时各为一次功能能力样本，不是 P50、尾延迟或完整 checkpoint 提速。Go 测试时源数据可能已在缓存中；它的零 PUT 与 Python 冷目标克隆相互补充，但不将 Go 这一轮单独称为冷读测试。没有 syscall 跟踪，不泛化为所有 Go/内核版本的行为。

证据：[原语回执](evidence/pr119-juicefs-tapfix-20261023/native-clone-primitives.json)、[实际 Go 函数回执](evidence/pr119-juicefs-tapfix-20261023/go-clone-helper.json)。测试源码和执行脚本见 `tools/pr119-pod-20261024/`。

## 4. 结论

【实测】本挂载能做卷内元数据克隆并隔离后续写入。FICLONE 不支持不等于 JuiceFS 没有克隆能力，也不等于现有 Go 回退路径一定上传整个文件。

【源码与实测】FC 当前函数先尝试 FICLONE，再 `io.Copy`；后者在本工具链/挂载实测没有搬运 S3 对象数据。可以优先复用，不必先写第二套复制函数。

【边界】尚未验证 FUSE 文件在真实 FC Async 引擎下的完整 SDK、新运行目录的崩溃对账或 gVisor sentry 的系统调用过滤。当前旧 runsc 也不等于后续 filestore 保存/采纳 bundle。单文件克隆不能替代 guest 内存、设备与全部文件的一致切面。

JuiceFS [原生克隆说明](https://juicefs.com/docs/community/guide/clone/)提供了共享数据块、写入后分离的设计依据；不是所有重新完整写出的相同文件都会自动按内容去重。本地 XFS 到 JuiceFS 也不属于本轮零数据传输的同卷克隆。

## 5. 建议与改进项

1. FC 先用现有克隆函数验证实际 JuiceFS 私有运行文件、保存、跨节点恢复、继续写及再次保存，记录首轮迁移和稳态成本；不默认改生产布局。
2. gVisor 固定后续正式 filestore bundle，核对保存和非消费采纳接口、copy_file_range、系统调用过滤和错误处理。先利用已有实现，再决定最小补丁，不复制整个运行时。
3. 克隆前的同步、一致切面、ADX 引用和失败清理仍要在真实 SDK 中验证。当前秒级 FC 内存保存并未由 RWFS 克隆解决，按下一阶段计划另做一致本地捕获后远端提交对照。

## 6. 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
S="$N/round-365f797-20261023.clPWh2h0/tap-checksum-fix/storage"
cat "$S/native-clone-capability01/terminal.json"
cat "$S/go-clone-helper01/terminal.json"
cat "$S/native-clone-cleanup01/terminal.json"
```

独立新环境可用 `native-clone-helper01.py <任务独占路径> <nonce> <role>` 重放原语；必须两个客户端同一 JuiceFS 卷、先 init，再目标 preflight / cold-clone，再后续分支测试。Go 夹具和未经修改的 `reflink.go` 放在同一个私有编译目录，在远端 Go 1.25.5 容器执行 `go test -c -o clone-helper.test reflink.go clone_probe_test.go`；根据夹具设置独占目录、nonce 和 copy/verify 角色。历史驱动包含固定任务路径/身份，不能在别人现场原样执行。

## 7. 现场清理披露

测试结束后按原 nonce、目录 inode、真实挂载和原 Pod UID 核验，仅删除本轮自有共享目录；两客户端确认目录已不存在。Node Pod 内临时测试二进制已按摘要移除。保留远端源码、构建证据和小型回执，不更换现役制品、模板或 profile，不改共享服务、旧环境、宿主参数；没有本地编译测试。
