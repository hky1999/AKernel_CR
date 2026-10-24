# gVisor 原生克隆候选的完整 SDK 部署就绪检查

## 1. 问题

用户允许补齐“新节点会话已注册、可路由且资源可调度”的真实等待门，再使用新输出完成 SDK。延续该门，将通过组件质量检查的 gVisor 原生克隆及 sandboxd 专有目录候选接入本任务环境，不能以 Pod Ready 或服务 active 代替业务就绪。

## 2. 方法

全部编译、测试、镜像制作和 SDK 在 BareMetal 独立任务进行。复用既有 SDK 驱动与真实就绪脚本；新输出为 `gvisor-native-consumer-sdk01`，PID3799802/start_ticks215591412。匹配运行时来自 bazel05，消费层来自 qa02，完整输入/格式化源码和实际 ELF 通过 SHA 对照。

部署前确认空 Environment、原镜像、两 Node 无旧运行时，创建有任务身份标记的 JuiceFS 专用目录；将 runsc 的模式、专有目录、文件系统三个配置项逐项修改，并用 TOML 解析树对比，证明 FC 与公共 filestore 配置未连带变化。先核对原 bootstrap 和 Secret UID，再滚动本任务 chart。

## 3. 数据

| 检查 | 实际结果与口径 |
|---|---|
| gVisor 组件 | 克隆、pgalloc、采纳和系统调用过滤普通/race相关门通过；两项真实后台加载顺序旧红已复现并修复，pgalloc最终三轮race通过。旧测试OOM失败保留，非静默忽略 |
| 匹配完整包 | 67566256字节，SHA-256 `63aa235350012e44020c8a9b404c677d2ce8894f167249ca7e5516ba3970cafa`；runsc、shim与四helper均为amd64 ELF |
| sandboxd 消费层 | fdb145c加11文件候选，fmt/vet/全仓单测/相关race/build通过；ELF `f81eec47352f3ec71843f585da758b75862e8139f2025c0db9159cd29b8c059b` |
| 候选镜像 | `365f7971f895-gvisor-native02`；三个Kind节点CRI均为 `sha256:0806341c5c1939a52497c4dfb28d6b111819322405b33e0f1bb344145fc38660`；leaf `4d18c0fa…`、config `f8036516…`；OCI907290112字节 |
| 实际部署 | 本任务Helm revision45，四角色rollout通过。两个Node、Coordinator、API和Redis使用候选镜像，不能说Redis未滚动 |
| 会话与路由 | 两Node新ADX会话均不同于部署前，routable=true，地址指向各自当前Pod，available=true且未暂停调度；连续三次同一身份观察通过 |
| 可调度资源 | 每Node可用CPU3000毫核、内存7679770624字节、磁盘719798022144字节，满足本轮1CPU/2GiB RAM/1GiB私有盘的最低资源门；此磁盘值仍是现有节点容量账，不表示共享卷有同样容量 |
| 制品核验 | 两Node各15个实际文件的SHA与固定清单一致，包括新runsc和全部配套程序；VMM、内核、initrd、ADX/Execd和只读根镜像保持原字节 |
| 配置与凭据 | Secret UID一致；原bootstrap内容摘要一致且本轮不写；gVisor private-root在两客户端均为JuiceFS且不同于公共本地XFS |
| SDK进展 | 官方76项全部OK；两运行时各三轮512MiB内存/64MiB根文件回滚、各A→B/B→A的512MiB内存/1MiB根文件接管通过，整轮rc=0 |

实际runsc SHA为`0a7c6571cac94b861ec857190dc5b9c168c2026e08a27eb5ba7e92a2f3317ab3`，sentry SHA为`30bf445ce1c5f09ab7a28582fe0cebd7390cb49f27211d503390f33bef1cbd10`。gVisor源码整理为218d85378357f9726fc3c0f7cf878cf19772d360（87e8441b6加10文件），sandboxd为21fb4668431cef88d05b7a789a2bd9a5e19e827c（fdb145c加11文件），均已推个人fork并核对。实际字节均在提交前构建、源逐一SHA匹配，未重建冒充；正式发布pin和默认产品路径未变。

## 4. 结论

【实测】本轮已通过真实就绪门，再发首个SDK请求；不是把Pod Ready作为可调度证明。候选组合的组件质量门、完整包、镜像导入及实际字节核验通过；SDK01最终76项、各三轮状态和双向接管整轮rc=0。最终只读盘点Environment0、两端VM/runsc及僵尸0，所有15文件SHA仍一致，原一份失败盘保留。

【尚未完成】新gVisor布局的完整分支/持续写、后台恢复故障与读者重启保护、进程死亡及同代码性能对照仍需补齐。不能把核心SDK通过当整条路线产品化；当前没有新的性能提升结论。

## 5. 建议与改进项

已完成官方76项、各三轮状态和正常双向接管，不重复已过门。继续按计划补gVisor专属分支/后台期间写入/再次捕获、挂载与同步故障、进程死亡和读者保护，再安排配对性能。远端只读基线加本地差异仍是下一阶段，没有被本轮Native克隆替代。

## 6. 可复现步骤

只在远端独立环境执行，不覆盖已有输出：

```sh
cat "$ROUND/tap-checksum-fix/gvisor-native-clone-bazel05/terminal.json"
cat "$ROUND/tap-checksum-fix/gvisor-native-consumer-qa02/terminal.json"
cat "$ROUND/tap-checksum-fix/gvisor-native-consumer-image02/terminal.json"
cat "$ROUND/tap-checksum-fix/gvisor-native-consumer-sdk01/ready/terminal.json"
cat "$ROUND/tap-checksum-fix/gvisor-native-consumer-sdk01/official-sdk/steps.jsonl"
cat "$ROUND/tap-checksum-fix/gvisor-native-consumer-sdk01/terminal.json"
```

实际驱动保存在 `tools/pr119-pod-20261024/candidates/gvisor-native-consumer/`；运行前按本任务地址和固定清单生成私有配置，不提交含身份和凭据的原始YAML或服务日志。

## 7. 现场清理披露

仅滚动独立集群本任务业务Pod、使用任务JuiceFS目录；没有改旧环境、共享服务、宿主内核/模块/sysctl或全局cgroup配置。image01新增RUN因cgroup父目录约束失败，原件保留；image02只检查停止的任务基底容器、验证完整旧四helper后COPY六程序，该检查容器已按身份删除。Bazel/消费层构建容器按任务标签退出，最终SDK与只读盘点已结束，环境和运行时0；gVisor根仅marker，FC旧失败盘一份明确保留，没有删除未知数据。所有编译测试均远端，未本地编译测试，未将待验收产品源码混入已发布交付。
