# PR #119 本地 SDK 阶段总结：网络接管修复与完整本地门禁

日期：2026-10-23。

## 阶段定位

本阶段解决了 gVisor 的 Execd（沙箱内命令执行服务）就绪超时，并完成固定候选的本地磁盘完整 SDK 验收。**这不是整个阶段一完成：JuiceFS 跨节点、生命周期故障矩阵和存储路线对照仍需继续。**

当前组合：AKernel `365f797`、sandboxd `d5acc3b + 两文件网络补丁`、ADX 发布包 `6fb53d7`、公共/原生 SDK `0.2.0rc3 / 0.1.0rc3`。补丁尚未提交推送，父仓三个组件指针未改。

## 完成项

- 定位持久 TAP 虚拟网卡遗留的发送校验和卸载状态：同一沙箱只改变开关，TCP 立即恢复，说明不是靠重启偶然转绿。
- sandboxd 的 gVisor 接管路径显式清除旧卸载状态；原代码内核回归按目标断言失败，修复后三轮跨模式复用及后续重新启用均通过。
- 格式、vet、项目全仓单测、runsc race 和生产参数编译通过，全部在远端专属 QA 容器执行。
- 候选镜像部署到本任务两个 Node Pod，实际 sandboxd SHA-256 为 `9c74060c3c4edceed6edb746e6b42bdd21116e3663427238fb1dd5067f3c964b`；其余运行制品未变。
- 打开已有 virtio-fs 能力以覆盖 Firecracker 的 OCI 只读根，不跳过不支持的镜像场景，不更换内核或 VMM。
- 补真实 ADX 就绪门：新会话、可路由、节点可用、资源容量、当前 Pod/镜像身份，连续三个样本稳定后再测。
- 受控重启后，两端各 gVisor→Firecracker→gVisor，共 6 次通过且删除；官方 integration/standalone 共 76 个用例通过，无跳过。
- 两种运行时另各 5 轮连续回滚、各 8 个非法参数、各 1 次 512 MiB 完整状态校验，共 12 次 checkpoint/reload 通过。

## 关键数字及其边界

下表为 1 vCPU/2 GiB、1 GiB 私有存储、本地 XFS、未额外填充内存的 5 样本 P50。checkpoint 是请求至完成，reload 是 SDK 调用，不是 guest 停顿。

| 操作 | 原轮固定 PR | 本轮候选 |
|---|---:|---:|
| gVisor checkpoint | 77 ms | 74 ms |
| gVisor reload | 226.480 ms | 245.293 ms |
| Firecracker checkpoint | 2448 ms | 2285 ms |
| Firecracker reload | 2696.639 ms | 2665.381 ms |

两轮配置和缓存历史不同，且没有交替采样，不能归因或宣布提速。本轮主要成果是稳定性修复，不是 checkpoint 性能优化。

512 MiB 完整内存校验为每种运行时各 1 个样本：gVisor checkpoint 789 ms、reload 1027.361 ms；Firecracker 2309 ms、2698.081 ms。完整状态校验还需要读取全部测试内存，不能与首个业务响应混为一谈。

## 新知识与踩坑

- 持久网卡可复用不代表其运行模式会自动复位；消费者必须建立自己所需的头格式和卸载契约。
- K8s Pod Ready/systemd active 不能替代 ADX 新会话注册及可调度检查。
- `umask 077` 适合保护实验日志，却改变依赖 0640 的单测夹具；仅测试子进程采用 022，不能放宽凭据目录或修改生产权限断言。
- Firecracker 的 EROFS 基础路径成功不等于 OCI/virtio-fs 路径验收；最终用固定 OCI 摘要补齐了原先跳过的覆盖。
- 镜像 config ID、Pod manifest 摘要、OCI 归档摘要不同，台账分别记录；源码 gitlink 也不等于平台发布包版本。

## 遗留清单与交接

1. 在本任务安装独立 JuiceFS/PostgreSQL/S3 兼容存储，再完成两运行时 A→B/B→A、源离线/重返、真实根 RWFS 与完整内存的公共 SDK 验收。
2. 补齐超时、取消、进程重启、后台读取与删除竞争、引用和回收矩阵，不能把本地 76 用例替代生命周期验证。
3. 存储接入必须以 `Q/tap-checksum-fix/virtiofs-enabled01-values.yaml` 为基线；旧准备脚本还引用原始镜像，原样运行会回退修复。
4. 先完成当前路线验收和同条件基线，再做 JuiceFS 原生克隆与远端只读基线＋本地差异层；严格性能结论按计划进行新旧交替采样。
5. 将已验收补丁整理为组件仓可获取提交，再更新父仓指针；当前不宣称已发布或生产可用。

旧环境和共享服务未改，所有旧运行目录、原镜像和失败记录保留。源码、摘要、命令、完整测试输出索引及现场清理披露见：

- `Docs/checks/20261023T-pr119-tap-offload-local-sdk-acceptance.md`
- `Docs/schedules/20261023T-pr119-tap-offload-local-sdk-progress.md`
- `Docs/checks/evidence/pr119-tap-offload-20261023/local-sdk.json`

其中 `Q=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp/round-365f797-20261023.clPWh2h0`。原始凭据与私有日志不进入父仓。
