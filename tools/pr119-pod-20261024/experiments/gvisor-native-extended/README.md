# gVisor 原生私有文件布局：扩展验收脚本

这是固定任务环境的执行来源和失败审计，不是新机器的一键部署入口。产品源码/制品未变，版本固定在父仓可选清单 `delivery/pr119-gvisor-native-rwfs-20261024.json`。所有语法检查、SDK 与运行时测试均只在 BareMetal 独立环境执行。

| 脚本 | 本次执行状态 |
|---|---|
| driver01 / sdk-two-branches01 | 通过；两个真正恢复分支、复杂私有文件和多代回滚、原快照重新恢复 |
| driver02 / sdk-role-restart01 | 未注入前失败：共用 ELF 的辅助进程被重复计数，原件保留 |
| recover-role-preflight01 / driver03 / sdk-role-restart02 | 失败实例内容核验及 SDK 删除通过；三个普通角色崩溃全部通过，原进程、未保存状态、匿名文件和引用保留 |
| driver04 / sdk-held-reader01 / hold-reader-role01 | 未注入前失败：Sentry 已隔离根目录，命名输入的查找视图错误 |
| recover-held-preflight01 | 完整 1 GiB 内存、根文件、忙删除和首轮资源 SDK 删除通过 |
| driver05 / sdk-held-reader02 / hold-reader-role02 | 真实输入屏障及三秒恢复已执行；sandboxd 崩溃后原实例退出，整例失败；两个后续角色未执行，不作为已验收能力 |
| sdk-reader-barrier-control01 | 只读预检失败，旧 Failed Environment 已自动退休，未创建资源或注入信号 |
| sdk-reader-barrier-control02 / hold-reader-control01 | 通过；只短停读者，不杀任何角色，完整 1 GiB 状态、引用、忙删除及后续保存恢复通过 |

两次失败探针都发生在信号前；真实失败单独留档，不能互相替换。控制组在另一逻辑节点、使用新快照，不能据此唯一认定根因。

脚本固定了原任务目录、容器身份及 ELF；远端原始 SDK 凭据只通过环境注入，仓库不含实际凭据、配置或原始服务日志。不要直接在其他环境执行，也不要覆盖旧输出。复现应先建立新独立任务，更新身份绑定、解析语法、核对挂载/资源/制品和 SDK 路由，然后执行新输出；保留失败时先读 terminal 和进程身份，禁止盲目重跑驱动。

白名单结果和每份远端已执行脚本的 SHA/大小见 `Docs/checks/evidence/pr119-gvisor-native-extended-20261024/extended-whitelist-final01.json`。原来使用的 guest fixture、状态读取与存储检查辅助脚本复用父仓既有 `executed/storage/` 与部署材料，没有重复实现一套。

七节检查见 `Docs/checks/20261024T-pr119-gvisor-native-extended-lifecycle.md`、`Docs/checks/20261024T-pr119-gvisor-open-input-sandboxd-restart-failure.md`。下一步先固定失败节点采集进程/cgroup/socket 时序，不能把这批诊断结果宣传为生产或性能验收。
