# PR #119：BareMetal Pod 复现预检

日期：2026-10-22。**本轮完成镜像与 SDK 准备，尚未部署 Kubernetes；不是 checkpoint/reload 跑通报告。**

## 1. 问题

用户要求：不用额外测试虚拟机，在 BareMetal 新建独立 Pod 环境；先确认 Kubernetes 与宿主依赖，修改共享环境前告知；依次跑通 runsc、Firecracker 和 JuiceFS 双节点 checkpoint/reload；编译测试只在远端进行，不影响旧环境，关注磁盘，最后提交中文复现文档到 GitHub。

这里的“不用虚拟机”指不再用额外虚拟机承载测试集群；Firecracker 自身用于被测沙箱的 microVM 不因此被替换。

## 2. 方法

【源码】通过 GitHub PR API 固定本轮真正的 head，不跟随浮动分支。读取该版本的官方部署说明、Helm chart（Kubernetes 应用部署模板）、镜像构建入口和 sandboxd 网络初始化实现。

【实测】全部准备在 BareMetal 独立任务目录执行。使用任务私有 Podman 存储构建官方两阶段镜像；安装固定 SDK、检查依赖，运行无网络、只读的镜像载荷检查容器。没有启动镜像中的 ADX 服务入口。

【只读检查】检查当前内核、设备、文件系统、常见集群进程和 kubeconfig 路径；检查网络模块状态，并仅用 `modprobe --show-depends` 解析依赖，不实际加载模块。只读发现范围不能证明所有隐藏命名空间都不存在集群。

## 3. 数据与证据

### 3.1 固定版本

| 项目 | 本轮实际版本与边界 |
|---|---|
| AKernel PR #119 | `6ea004125eb4365ba06ba3c7b21c4fd80e4cdaac`，来源 `WenYuLuo/akernel:feat/juicefs-adx-build179` |
| sandboxd | `d5acc3b5b673074e20fd8b7733d4035dbaeae1b0`，官方 main-based 子模块；不是旧实验的 `3da34daf...` |
| ADX | `59fa7912f875832c8ab053148ae8fd17b7c25a23`；使用该版本配套发布包，本轮未重新编译 Rust 控制面 |
| 公共 SDK / 原生 SDK 依赖 | `akernel-sdk==0.2.0rc3` / `adx-environment==0.1.0rc2` |
| gVisor | 完整发布归档 `release-20260817.0-akernel.4`；内嵌 runsc 版本 `release-20260817.0-akernel.3-2-g7fdef444b108`，二者不是同一类版本标识 |
| Firecracker | 发布归档 `v1.16.1-akernel.3`，VMM 内嵌版本 `v1.16.1` |
| distill-fs / JuiceFS 垃圾箱 | PR 镜像使用 `v0.1.3`；JuiceFS 默认 `trashDays=0`，不得套用旧实验参数 |

固定源码归档 SHA-256：`af6d623d89689154a0b5fbe99a107eb56fc29a888dd33cbeddd3ef5421f56ad6`。

官方入口 `deploy/scripts/build-image.sh` 先执行 `builder/runtime.Dockerfile`，再执行 `builder/node.Dockerfile`。宿主没有 Docker CLI，本轮仅以任务专属的 Docker CLI shim 把官方两次 build 转给 Podman；实际引擎不是 Docker BuildKit，不能把两者写成相同验收。

### 3.2 已完成与尚未完成

| 项目 | 本轮结果 |
|---|---|
| 官方两阶段镜像构建 | 两次 build 返回码均为 0，合计约 371.7 秒；这是打包耗时，不是 checkpoint 耗时 |
| 镜像载荷检查 / OCI 导出 | 返回码均为 0；检查完整 gVisor helper、Firecracker/kernel/initrd、EROFS、ADX/Execd 等载荷 |
| OCI 镜像归档 | 653,413,376 字节，约 623 MiB；SHA-256 `105c7c345407c853fe95f8d60f08540611276c405f5ac80a13bfa30644b76d87` |
| 导出后的 OCI manifest | `sha256:2fe4ad3de728f7fdeb2be1fef1e036dfa236fe7df000f12e2cf67699471bce72`；不能与构建存储中的原 manifest 混记 |
| SDK 安装与依赖一致性检查 | 九个安装/校验阶段返回码为 0，`pip check` 通过；未创建 Sandbox |
| Kubernetes / 本任务 Pod | 尚未创建集群，Pod 为 0；未下载部署工具、未执行 Helm 渲染 |
| 公共 SDK checkpoint/reload | 请求数 0；runsc、Firecracker 均未执行 |
| JuiceFS 双节点恢复 | 未执行；没有新的性能数据、冷读取量或跨物理机结论 |

以上“Pod 为 0”不包括镜像构建容器与载荷检查容器。构建成功不等于 ADX 启动成功，也不等于完整公共 SDK 验收通过。父仓历史交付的组件指针保留，没有改成这组尚未动态验收的 PR 版本。

### 3.3 宿主与共享内核阻塞

本次只读采样：内核 `7.0.0-31-generic`；`/dev/kvm`、`/dev/fuse`、`/dev/net/tun` 存在。未找到可直接采用的现有 Kubernetes/CRI 集群或常见 kubeconfig；观察到既有 `conmon` 与桥接设备，均未操作。不能仅凭 PATH 中没有 kubectl 就断言整台机器没有任何集群。

当前固定源码的证据链：

- `src/sandboxd/pkg/networkmanager/networkacl/iptables.go:newIPTablesBackend`，第 112 行起：先调用 `ensureBridgeNetfilter`，再创建 IPv4/IPv6 客户端并执行前置探针。
- 同文件 `ensureBridgeNetfilter`，第 278 行起：要求对应网络命名空间的 `bridge-nf-call-iptables` 和 `bridge-nf-call-ip6tables` 为 1。
- `validatePrerequisites` 的缓存证据包含第 214–260 行 IPv6 规则探针，以及第 265–273 行带 timeout 的 `hash:ip` 探针。没有保留该函数首行，故不补造其起始行号。
- `br_netfilter`、`ip_set`、`ip_set_hash_ip`、`xt_set`、`xt_conntrack` 当前均未加载，也不是内建；15 条只读依赖解析实际返回码均为 0。依赖涉及 bridge/STP/LLC、nfnetlink、x_tables、nf_conntrack 和 IPv4/IPv6 defrag，不能承诺只加载一个模块就完成全部前置条件。
- `bridge`、`veth`、`nf_tables`、`nft_compat`、`nf_conntrack`、`nf_nat`、`xt_MASQUERADE`、`overlay` 已加载，但这不证明完整新集群可以启动。

**Pod 和网络命名空间共享宿主内核。加载 `br_netfilter` 会注册 bridge hooks，可能改变已有桥接流量的处理；不能把它称为“只修改私有 Pod”。** 当前没有执行模块加载、共享 sysctl/NAT 修改，也没有关闭网络策略来绕过检查。CNI（Pod 网络插件）尚未最终选定，VXLAN/IPIP 仅为条件候选，不计入已确认的必需加载项。

冻结依赖证据：`cluster/prepare02/module-dependencies.json`，7,422 字节，SHA-256 `4929e7da1f49c83d2057ede5a41309a10f7ffe66e1efe21e9c6050307f2062dc`。

### 3.4 磁盘

| 口径 | 实际结果 |
|---|---|
| XFS 卷 | `/mnt/m0-xfs`，约 1.3 TiB；一次采样使用率 34% |
| 新任务有界目录统计 | 约 7.17 GiB，其中镜像构建目录约 7.11 GiB；不是实测峰值 |
| 磁盘审计时 XFS 可用空间 | 约 844.7 GiB；数值随采样时刻变化 |
| 删除日志、缓存、编译产物 | 0 字节；没有空间压力，不为清理而清理 |
| 收回的空资源 | 仅本任务一个未使用的空 cgroup；未启动额外测试 VM |

没有执行全局 prune，也未删除旧实验的 Go cache、已校验发布包、证据或活动构建目录。后续以任务占用 250 GiB 提醒；占用达 350 GiB 或 XFS 可用低于 250 GiB 时暂停新增分配，先核对归属，不自动删文件。这是保守操作阈值，不是本次实测峰值。

## 4. 结论

【实测】固定 PR 镜像与 SDK 准备完成；没有新 Pod、SDK Sandbox 或 checkpoint/reload 结果。磁盘当前无需清理。

【源码】完整网络访问控制链需要宿主当前尚未具备的模块；共享内核变更必须先向用户说明影响并确认操作边界。不能通过私有 namespace 或“Pod 而非 VM”消除模块加载的宿主影响。

【外推】可以继续采用 Pod 方案，但当前只完成部署前置检查。尚不能声称 PR #119 在本 BareMetal 上已复现，也不能引用旧版本的 Firecracker 优化数字来表示本轮性能。

## 5. 建议与改进项

1. 先确认是否允许受控加载已核对的网络模块及依赖，记录宿主既有桥接状态和可接受影响范围；若不能接受共享内核风险，保持当前停止点，不偷偷绕过网络访问控制。
2. 宿主前置条件对齐后，再创建任务私有 Podman 状态、网络和 Kind 集群。Kind 用容器模拟 Kubernetes 节点，不另建测试虚拟机。准备一个控制节点和两个执行节点；这是同物理机双逻辑节点，不是两台物理机。
3. 两个执行节点分别拥有独立节点身份、本地 XFS 路径、socket、cgroup 和资源额度，核验 Kubernetes 可分配资源，不能把整机容量重复记两次。普通本地 XFS filestore 显式覆盖官方默认 `filestore_dir_size="200G"` loop-ext4；此差异须进入后续报告。
4. 使用真正执行 NetworkPolicy 的 CNI。Kind 默认 kindnet 不足以证明访问策略生效，不能以 YAML 存在代替运行验证。官方内部 TLS `mode: network`、Coordinator HTTP 的安全模式如实记录，对外 SDK HTTPS 证书校验保持开启；不能误报为内部双向 TLS。
5. 先分别完成 runsc 和 Firecracker 的 SDK 创建、沙箱内 checkpoint、SDK reload 与文件/内存正确性。再部署官方单 OSD 40 GiB、单 MON、replicas=1 的非高可用评估存储，完成 JuiceFS 双客户端读写与 SDK 双节点恢复。所需块设备仅使用任务自有文件，不格式化已有共享盘。
6. 双节点验收须保留源节点、目标节点的实际身份；checkpoint 完成后仅让本任务源执行节点退出，验证目标接管，不能以原节点 reload 冒充跨节点。读者锁生命周期、服务故障、共享卷等专项矩阵仍需独立验收。
7. 后续报告分别统计 checkpoint 请求到完成、业务停顿、SDK reload 到首次文件/内存正确、JuiceFS/S3 读取字节数。当前全部无新数据，不填估算数字。

### 预期拓扑，尚未部署

```text
BareMetal（共享宿主内核）
  |
  +-- 本任务私有网络 / Podman 状态 / Kind 集群
       |
       +-- Kubernetes 控制节点：控制面与评估存储（待排布）
       +-- 执行节点 A：独立 ADX 节点 / sandboxd / 本地 XFS filestore
       +-- 执行节点 B：独立 ADX 节点 / sandboxd / 本地 XFS filestore
                 |                            |
                 +----- JuiceFS checkpoint --+
                             |
                     PostgreSQL + Ceph RGW
                     单副本评估布局，非生产 HA
```

JuiceFS 共享 checkpoint 目录不自动意味着两个节点的私有 RWFS 都直接写共享盘。实际配置、挂载传播、块设备归属和恢复写入落点，需要部署后逐项验证；本轮没有将其验收为通过。

## 6. 可复现步骤

以下为只读预检与已完成构建阶段的复现入口，**不是已验收的一键部署脚本**。所有编译与测试在远端执行，不在本地运行。

```bash
ssh BareMetal 'uname -r; df -hT /mnt/m0-xfs /; df -Pi /mnt/m0-xfs /'
ssh BareMetal 'for m in br_netfilter ip_set ip_set_hash_ip xt_set xt_conntrack; do
  if test -d "/sys/module/$m"; then printf "%s loaded-or-builtin\n" "$m";
  else printf "%s not-active\n" "$m"; fi
  modprobe --show-depends "$m"
done'
```

上面的 `--show-depends` 只解析依赖，不能删除该选项后当成同一种只读操作。模块、sysctl 和 iptables 规则的实际写入须等环境变更确认。

固定源码、官方构建参数、SDK 安装和载荷检查命令见同目录的 `20261022T-pr119-pod-build-sdk-command-appendix.md`。其中使用到的任务专属 shim、检查器与监督器尚未通用化，不应把该附录称为外部机器可直接运行的一键脚本。

脱敏汇总：`evidence/pr119-pod-20261022/preflight.json`。完整原始日志、归档、私有配置仍在远端任务目录保存，不进入 Git；不提交镜像、凭据或运行数据。

## 7. 现场清理披露

新任务目录：`/mnt/m0-xfs/akernel-pr119-repro-20261022.XfboxUgq`。创建了源码、私有镜像存储、SDK 环境、构建容器和无网络只读检查容器；没有启动 Kubernetes、ADX 服务、SDK 沙箱或额外测试 VM。

仅删除本任务一个空 cgroup：核对设备号、inode、UID、无进程、`populated=0` 与无子组后执行 `rmdir`。空 cgroup 收尾脚本首轮语法失败原件保留，修正后成功。没有删除日志、缓存、构建归档；未杀旧进程、重启旧 daemon、修改旧配置或已有桥接设备。后续部署尚未开始，不存在“部署后已全部清理”的验收结论。
