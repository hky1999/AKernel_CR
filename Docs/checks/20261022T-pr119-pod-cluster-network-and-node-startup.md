# PR #119：独立 Pod 集群、网络验证及执行节点启动检查

## 1. 问题

用户要求在 BareMetal 以 Pod 模拟环境，不新增测试虚拟机，跑通 runsc、Firecracker、JuiceFS 双节点的 checkpoint/reload；编译测试全部在远端独立环境，不影响旧环境。用户随后允许受控执行所需网络模块变更。

本篇记录本轮已完成的集群和网络工作，以及尚未解决的执行 Pod 启动阻塞。它不是三条 SDK 链路的通过报告。

## 2. 方法

【实测】所有编译、集群操作、网络探针均在 BareMetal。使用任务私有 mount/network/UTS/IPC namespace、Podman graph/runroot、kubeconfig 和 cgroup。slirp4netns 提供外连，未把实验网络桥接进旧环境。Kind 的三个容器节点共享一台物理机，不是三个物理故障域。

固定版本：AKernel PR #119 `6ea004125eb4365ba06ba3c7b21c4fd80e4cdaac`，其 sandboxd `d5acc3b5b673074e20fd8b7733d4035dbaeae1b0`，ADX `59fa7912f875832c8ab053148ae8fd17b7c25a23`；公共 SDK `0.2.0rc3`、原生 SDK `0.1.0rc2`。源码尚未为启动问题打补丁。

按官方 runtime/node 两阶段 Dockerfile 在远端构建镜像；私有 Podman 兼容包装用于构建，不声称与 BuildKit 的实现完全相同。工具为 Kind `v0.33.0`、Helm `v3.22.1`、kubectl/Kubernetes `v1.35.8`、Calico `v3.32.2`。

## 3. 数据与证据链

| 检查 | 本轮事实与口径 |
|---|---|
| 显式网络模块加载 | 14 项均返回 0，清单见下；依赖模块可能随之加载，不能把显式项数当成全部内核差异数 |
| 首批模块前后检查 | 归一化后的宿主 iptables、ip6tables、nftables 规则和桥标识/参数相等；不据此推断零丢包 |
| Kind | 一个控制节点、两个执行节点均 Ready；最终一次创建返回 0；第一次失败现场保留日志后仅回收自己的三个容器 |
| 资源隔离 | 外层 cgroup 上限 12 CPU / 40 GiB；每个节点容器上限 4 CPU / 10 GiB；调度器可分配 4 CPU / 8092 MiB / 29 GiB 临时盘。临时盘调度配额不是物理磁盘硬限额 |
| Calico | 原生 nftables，BGP，Pod 网段 `10.220.0.0/16`，不封装；状态 Available，未使用 VXLAN/IPIP |
| 网络策略 | 三个非 root HTTP 探针 Pod 分置两个执行节点。策略前两客户端 HTTP 200；策略生效后允许方 HTTP 200、拒绝方 3 秒超时；撤销后两方 HTTP 200。6 项断言通过，探针 namespace 已删除 |
| AKernel Helm | 安装命令返回 0，状态 deployed；Coordinator、Ingress API、Redis 正常；执行 DaemonSet 的两个 Pod 均立即退出 255 |
| 完整 SDK 验收 | runsc 0、Firecracker 0、JuiceFS 双节点 0；没有 checkpoint 停顿或恢复性能数据 |
| 磁盘 | 最近一次远端采样 XFS 约 834 GiB 可用、占用约 34%；未删除旧环境产物 |

显式模块分三批：

```text
br_netfilter ip_set ip_set_hash_ip xt_set xt_conntrack
ip_tables ip6_tables iptable_nat ip6table_nat iptable_filter ip6table_filter
xt_physdev nf_conntrack_netlink xt_connmark
```

未配置持久化 modules-load，未主动写全局 sysctl。`br_netfilter` 新注册的参数采用模块默认值；模块本身注册 hook，不是“对宿主完全无影响”。`nf_conntrack_max` 两次采样均为 262144，仅能说明这个参数没有变化。

镜像身份必须区分不同层次：

| 对象 | SHA-256 |
|---|---|
| 导出 OCI tar 文件 | `105c7c345407c853fe95f8d60f08540611276c405f5ac80a13bfa30644b76d87`，653413376 字节 |
| 导出 OCI manifest | `2fe4ad3de728f7fdeb2be1fef1e036dfa236fe7df000f12e2cf67699471bce72` |
| 镜像配置，实际 CRI imageId | `d1316b767b570f12a2eb5156fd0af80dfbcd783a9ba853a308fe872a4394dee0` |
| Kind 导入时生成的引用摘要 | `64bdfa645c396f43335802bb5b98bf357ebd63572ecced9daac679f97b8b47d0` |
| sandboxd ELF | `cc8f871d690b1c95017f92802bc95a0f079639ec618f39ce001ce9ba84338cfb` |
| Firecracker initrd | `360a0b3bc1faf51fefd2e389208622d1343e8e020aa271a306cf8fbf698cad1b` |

【实测】执行 Pod 的主进程先退出，随后 PostStart hook 报无法进入已经消失的 namespace 或容器已停止。因此不能把错误名解释为“DNS 替换命令自身失败”。实际 CRI 进程参数只有 `/usr/local/bin/akernel-entrypoint`，没有镜像默认的 `/bin/bash` 尾参；不支持“默认 CMD 被误传给 init”的猜测。CRI namespace 列表没有 cgroup namespace，cgroup 挂载为可写；是否导致 systemd 启动失败，仍待启动日志确认。

关键原始证据留在远端任务目录的 `cluster/module-change04/`、`kind09/`、`calico10/`、`netcheck12/result-fixed.json`、`helm13/`、`diag14/`。原始 Helm 渲染件可能含密码，不公开原件。

## 4. 结论

【实测】授权后的网络依赖已补齐，私有 Kubernetes 集群和跨节点访问控制已通过；官方镜像已导入节点，控制面可运行。

【实测】执行 Pod 仍无法启动，三条完整 SDK checkpoint/reload 均未通过。JuiceFS 的数据库和对象后端尚未部署，不存在本轮“JuiceFS 双节点恢复成功”的结论。

【外推】当前同机多节点容器适合功能与路径验证，不足以证明跨物理机带宽、掉电持久化或存储高可用，也不能用于宣布性能超过竞品。

## 5. 建议与改进项

1. 优先获取两个执行 Pod 的 systemd 早期退出日志；保留原失败配置，只修改任务私有 profile，不能关闭资源隔离或替换为绕过公共 API 的诊断捷径。
2. 执行节点健康后，先完成 runsc 公共 SDK 的创建、沙箱内 checkpoint、reload、文件与内存一致性，再完成 Firecracker 同口径验收。
3. 最后部署隔离的 JuiceFS 元数据/对象后端，固定两端路径与节点选择，完成源节点和目标节点不同的 SDK 恢复。禁用本实验无需的存储驱动，避免意外加载未授权的宿主存储模块。
4. 全链路通过后才采集多轮性能；checkpoint 请求耗时、guest 停顿、reload 返回和首次完整读取分开报告。

## 6. 可复现步骤

以下命令在远端执行。`TASK_ROOT` 是已有私有实验目录，不是共享配置目录；创建它需先检查容量并固定源码与镜像。脚本默认本轮命名，异地复现先使用新的任务标识，不能复用别人现场。

```bash
export TASK_ROOT=/path/to/your/private/pr119-task
python3 tools/pr119-pod-20261022/prepare_tools.py --help
python3 tools/pr119-pod-20261022/namespace_lab.py --help

# 宿主网络模块加载需要管理员事先确认，禁止脚本静默扩大范围。
modprobe br_netfilter
modprobe ip_set
modprobe ip_set_hash_ip
modprobe xt_set
modprobe xt_conntrack
modprobe ip_tables
modprobe ip6_tables
modprobe iptable_nat
modprobe ip6table_nat
modprobe iptable_filter
modprobe ip6table_filter
modprobe xt_physdev
modprobe nf_conntrack_netlink
modprobe xt_connmark

# 已按本轮私有配置创建 namespace、Kind 后，命令只进入本任务环境。
python3 "$TASK_ROOT/cluster/namespace-lab07.py" run --task "$TASK_ROOT" -- kubectl get nodes -o wide
python3 "$TASK_ROOT/cluster/namespace-lab07.py" run --task "$TASK_ROOT" -- kubectl get tigerastatus
python3 "$TASK_ROOT/cluster/namespace-lab07.py" run --task "$TASK_ROOT" -- kubectl -n akernel get pods -o wide
python3 "$TASK_ROOT/cluster/namespace-lab07.py" run --task "$TASK_ROOT" -- kubectl -n akernel logs daemonset/akernel-node --previous
```

本轮另需私有 aardvark-dns `1.16.0`：只解包 Ubuntu `aardvark-dns_1.16.0-3_amd64.deb` 到任务目录，包 SHA-256 `d830415401f01d123c6e145859554bf06dca983eba38f5bdfd1bcbaccc2fc31c`；在本任务 `containers.conf` 的 `[engine] helper_binaries_dir` 指向其 `usr/lib/podman`。不能用全局 apt 安装或改共享 Podman 配置代替。Kind 初次缺少该依赖，worker DNS 无法解析控制节点，已保留失败记录。

目前脚本与命令是阶段诊断材料，尚不是“一键复现三条验收”的完成品。旧预检附录仍描述构建/SDK 安装步骤；完整验收文档需待上述阻塞解除后补齐。

## 7. 现场清理披露

- 保留旧环境、旧 daemon、旧测试产物和共享服务，没有全局 prune、卸载他人模块或删除他人容器。
- 第一次 Kind 集群因缺少私有 DNS helper 失败；确认对应 Kind/kubeadm 进程结束后，导出日志，仅删除本任务三个容器。回收字节数未计量。
- 网络探针的三个 Pod、策略和 namespace 已删除；当前集群及 AKernel 失败 Pod 保留用于诊断。
- 本轮脚本曾因 Kind 版本字符串格式、Calico 分离 CRD schema、内联 shell 引号失败；修正后使用独立输出记录继续，未把失败记录覆盖成成功。一次 SSH 超时导致验收素材复制没有执行，不能认为素材已经准备完成。
- 未发现或处置他人环境异常；未进行宿主规则回滚，以免覆盖并发工作者的配置。后续清理先核对 PID、启动时间、namespace 和任务所有权。
