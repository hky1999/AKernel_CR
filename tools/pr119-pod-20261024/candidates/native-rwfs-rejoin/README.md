# 本轮实际执行脚本与新环境用法

产品代码只在 sandboxd fdb145c，不内嵌到父仓。这里保留本轮实际执行的部署、诊断和验收脚本，固定的任务目录、Kind 容器 ID、Pod 身份和摘要都是历史执行身份；不能直接对旧环境重放，也不是任意服务器的一键启动器。

新独立环境应从基础复现文档准备 ADX、运行时和 JuiceFS，然后用 fdb145c 构建任务镜像、合并私有盘配置片段并确认真实就绪。**新环境不需要重建历史坏版本或执行原现场救援。** `rescue-in-place0{2,3}.py`、`complete-in-place04.py` 与带历史依赖的驱动仅用于解释此次故障如何恢复。

直接执行的测试入口为：

- `executed/wait-ready01.py`：实际已执行的会话、路由、资源、Pod/镜像与二进制检查。新构建的镜像/ELF 摘要会不同，应把自己的完整构建回执固定进去；不能删除检查或允许任意摘要。
- `executed/sdk-full01.sh`：本轮直接运行的官方 76 项，无须原现场故障依赖。执行前适配任务路径、SDK Python、源码路径、凭据环境文件和全新输出目录；保留 TLS 与原隔离。
- `sdk-writable-performance01.py`：每运行时一个实例、可配置节点和轮数的完整内存/根文件及分相测量。每轮相互依赖，不能标成独立实例；普通写入时间含 SDK 写入与 guest sync。
- `sdk-forced-failover02.py`：即时停止身份匹配的源 Kind、公共 SDK 自动接管、相同源 Pod 的产品退休与重新加入。先按新现场固定节点和容器身份，仅在独占任务执行。
- `sdk-writable-restart01.py`：只杀身份已核对的任务管理进程，验证原 VM/运行实例、未保存状态、快照保护和后续保存恢复。
- 真实直接 I/O 复用 `../../executed/fc-async-disk-cut/sdk-direct-io02.py` 及配套 guest 脚本；本轮没有重复实现。

`qa.sh` 是远端独占容器的源码门脚本，绑定 `/src`、`/out`、`/gomodcache`、`/gocache`，使用 Go 1.25.5，2 CPU/6 GiB，依赖已按 go.sum 在远端准备，执行时网络 none。显式挂载测试要求私有 mount/cgroup namespace 和权限，不能直接在共享宿主执行；日志/凭据目录 0700，测试子进程 umask 022。默认全仓单测不能替代显式启用的三轮内核/挂载回归。

`run-full-sdk02.py` 记录这次“历史故障恢复通过→移除临时覆盖→固定镜像→官方 SDK→三轮状态→双向故障”的完整顺序；其原现场依赖不应照搬到全新环境。`run-native-rwfs-rejoin-postsdk02.py` 在该整轮成功后才做持续直接写和两运行时管理进程崩溃。`collect-reports.py` 只导出白名单；不复制原始 OCI 配置、Secret 或服务日志。`final-state01.py` 是同一次远端只读命令的另存原文，不是额外重跑结果。

路径和身份适配并保留原失败脚本后，在远端执行以下顺序。CR_TASK、CR_SCRIPTS、CR_PREVIOUS、CR_IMAGE_DIGEST、CR_RESULTS 均指调用者的新独占任务；CR_PREVIOUS 是部署前两节点会话 ID 的 SHA-256 字典，不能留空冒充新会话。

```sh
# qa.sh 仅在上述私有构建容器内执行；不要在共享宿主直接执行。
bash "$CR_SCRIPTS/qa.sh"
# 任务镜像部署完成后，先过真实会话/镜像/资源等待门，再发 SDK。
python3 "$CR_SCRIPTS/executed/wait-ready01.py" \
  --expected-digest "$CR_IMAGE_DIGEST" \
  --previous-session-hashes "$CR_PREVIOUS" \
  --output "$CR_RESULTS/ready" --timeout 360
python3 "$CR_TASK/cluster/namespace-lab07.py" run --task "$CR_TASK" -- \
  bash "$CR_SCRIPTS/executed/sdk-full01.sh"
```

新环境直接 SDK 脚本里的输出目录必须全新，不能沿用本轮历史目录；其余强身份故障探针同样先适配再执行。源恢复和完整状态断言不可删减来制造通过结果。

配置片段和版本分别见 `deploy/experiments/README-pr119-fc-native-rwfs.md`、`delivery/pr119-native-rwfs-20261024.json`；功能结论与限制见 `Docs/checks/20261024T-pr119-native-rwfs-full-sdk-acceptance.md`。所有编译测试都应在调用者新建的远端独立环境完成，不修改共享服务。
