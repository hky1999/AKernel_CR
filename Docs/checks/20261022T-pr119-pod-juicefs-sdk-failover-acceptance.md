# PR #119 独立 Pod + JuiceFS 核心 SDK 验收检查

日期：2026-10-22。日志时间为 UTC，耗时为毫秒。**核心链路通过，不代表全量故障矩阵、生产高可用或性能领先。**

## 1. 问题

用户要求：临时将 fs.inotify.max_user_instances 调至 1024，不持久化、不重启共享服务；恢复独立集群，先确认 etcd 和 API Server 健康，再继续 runsc、Firecracker、JuiceFS 双节点完整 SDK 验收；编译测试全部远端执行，整理中文复现文档并提交推送。

本轮使用 Pod 方案，不增加基础设施虚拟机，不升级旧环境，不操作其他使用者的 daemon、沙箱和数据。

## 2. 方法

| 项目 | 固定条件 |
|---|---|
| AKernel PR #119 | 6ea004125eb4365ba06ba3c7b21c4fd80e4cdaac |
| sandboxd / ADX | d5acc3b5b673074e20fd8b7733d4035dbaeae1b0 / 59fa7912f875832c8ab053148ae8fd17b7c25a23 |
| 公共 / 原生 SDK | akernel-sdk 0.2.0rc3 / adx-environment 0.1.0rc2 |
| gVisor / Firecracker | 发布包 release-20260817.0-akernel.4 / v1.16.1-akernel.3 |
| gVisor 内嵌构建名 | release-20260817.0-akernel.3-2-g7fdef444b108，与发布包标签分别记账 |
| JuiceFS / PostgreSQL / Rook | 1.4.1+2026-07-30.0b90c7db / 17 / chart 1.21.0 |
| Kubernetes / Kind / containerd | 1.35.8 / 0.33.0 / 2.3.4 |
| 宿主与隔离 | 一台 BareMetal、104 vCPU / 约187 GiB、XFS；私有 namespace、Podman 存储、kubeconfig、cgroup、证书与凭据 |
| 逻辑节点 | 一个控制节点、两个执行节点，均为 Kind 容器；任务限制12 CPU /40 GiB，节点各4 CPU /10 GiB |

本轮未更换运行时二进制或修改产品源码。父仓三个历史 submodule 指针不自动等于这套测试组合；以本表、`VERSION.md` 和构建附录的固定版本为准。

源码链路：ADX 的 `platform/adxlet/src/controller/workload_checkpoint.rs::workload_checkpoint` 在 capture、artifact 发布和权威状态持久化之后才完成确认；`execution_artifacts` 保留仍在使用的输入。`gateway/apiserver/src/operations.rs::Operations::execute` 与 `controller/lifecycle.rs::reload` 区分主动回滚和恢复状态处理。本轮没有另建 checkpoint catalog 或新增公开目录 API。

实测均通过公共 `Sandbox` 对象创建，`failover=True`、不硬绑 `node_id`。沙箱内向 `/run/akernel/execd.sock` 的 `/checkpoint` 请求，必须返回 HTTP 200 和 completed。之后改写内存和文件，再检查恢复，不以“目录存在”代替验收。

Go 探针真实触达512 MiB，每次重新计算全内存 SHA-256，并核对随机身份标记、PID、已打开文件。原文件检查在 `/tmp`；实测两种运行时的该目录都是 tmpfs，不能冒充磁盘 RWFS。RWFS 指沙箱自己的可写文件层，不是共享卷；本轮另补根 overlay 内 `/pr119-disk-rwfs-state` 的1 MiB数据。

故障用例仅停止本任务执行节点容器，保持控制面/存储在线，通过同一个 SDK 对象的正常文件读取触发接管，不重复提交回滚请求。校验时源节点仍停止；源重新加入后，再校验数据、完整内存和目标运行时身份，最后删除沙箱。

## 3. 数据

### 3.1 基础与真实存储

| 检查 | 实测结果 |
|---|---|
| inotify | 128临时升至1024，未持久化；独立集群仍保留，最终值1024 |
| etcd / API Server | 恢复后先检查通过；结束再次 endpoint health=true、readyz全通过 |
| 节点与应用 | 3个节点Ready、5个AKernel Pod Ready |
| JuiceFS | 3个真实 fuse.juicefs 挂载；4 KiB文件经fsync后，另外两端摘要一致 |
| PostgreSQL | fsync、synchronous_commit、full_page_writes 均为on |
| 对象存储 | 本任务Ceph RGW S3，不是复用旧MinIO或SeaweedFS |
| Ceph | 实际资源rook-ceph，Ready / HEALTH_WARN；单OSD、单副本、认证兼容告警，不能叫生产健康验收 |
| 宿主磁盘 | 最终可用847172513792字节，约789 GiB；没有清理他人数据 |

Ceph 使用本任务40 GiB预分配镜像和loop测试设备，没有格式化物理磁盘；不是原生裸盘性能环境。普通 filestore 目录本身没有再套loop镜像。

初次安装失败保留：Kind缺少kubelet块设备锁定所需节点、Rook缺少CSI API定义、Ceph volume缺少udev描述、格式化Job超时。修正限定在本任务：私有设备节点、仅六个CSI CRD、只读复制宿主udev描述、核对失败Job UID后重试；没有启用新CSI驱动、重启宿主udev或放宽持久化。

### 3.2 DNS 污染与受控复测

首轮gVisor B→A目标内存读取EIO、恢复超时；同一时间JuiceFS报无法通过DNS解析PostgreSQL，出现connection refused / timeout。

检查发现两个CoreDNS副本及两个就绪端点全部在故障节点B；停止B同时切断了存储的DNS。此轮**不能作为gVisor数据损坏或JuiceFS不可靠的证明**。

仅将独立集群的DNS迁到控制节点，等待副本和端点就绪，并从两执行节点实际解析PG/RGW服务名。运行时、SDK、二进制均未变；随后相同B→A、512 MiB负载通过，另补A→B根RWFS用例通过。原失败未覆盖。两DNS副本同在唯一控制节点，仅保护本实验的执行节点故障，不构成生产HA。

### 3.3 同节点主动回滚

沙箱配置2 GiB内存限制，额外测试内存512 MiB；每行单样本，不标P50。文件路径为/tmp，真实根RWFS另验。

| 运行时 / checkpoint后端 | 请求至completed | reload返回 | 文件校验完成 | 全512 MiB内存校验完成 |
|---|---:|---:|---:|---:|
| gVisor / 本地XFS | 729 ms | 1014.590 ms | 1057.441 ms | 2752.881 ms |
| gVisor / JuiceFS | 1117 ms | 3061.137 ms | 3105.028 ms | 4826.547 ms |
| Firecracker / 本地XFS | 2668 ms | 2681.094 ms | 2725.392 ms | 4619.319 ms |
| Firecracker / JuiceFS | 5973 ms | 6712.452 ms | 6758.836 ms | 9966.751 ms |

checkpoint包含保存、发布和控制面确认，**不是guest停顿**；后三列从reload调用前计时。没有新增该负载的五轮统计，不能裸称稳定回归倍数或优化收益。

另一个没有额外512 MiB负载的本地五轮用例：gVisor checkpoint P50=64 ms、reload P50=243.450 ms；Firecracker为2590 ms、2655.709 ms。各八项非法参数拒绝通过。六个本地SDK任务共14次checkpoint/reload，四个初始共享存储任务也全部通过。

### 3.4 公共 SDK 故障接管与根 RWFS

下表同时含1 MiB根文件和512 MiB内存，每行独立单样本。“读取触发”计时在权威目录判定源不可路由之后开始；“全部故障”从停止源容器之前开始。

| 任务 / 方向 | checkpoint | 根RWFS校验 | 完整内存校验 | 全部故障至完整内存校验 |
|---|---:|---:|---:|---:|
| runsc49-rwfs / A→B | 1055 ms | 2030.716 ms | 3656.914 ms | 36706.873 ms |
| fc50-rwfs / B→A | 6030 ms | 4861.988 ms | 7646.183 ms | 37730.985 ms |
| runsc51-fd / A→B | 1026 ms | 3265.111 ms | 4880.728 ms | 36407.047 ms |

三轮均通过源重新加入后的二次校验，目标运行时身份未变，SDK删除成功。另有runsc48 B→A、fc45 A→B内存用例通过；完整事件见[脱敏JSON](../../evidence/pr119-pod-20261022/juicefs-sdk-failover.json)。

1 MiB根文件摘要为 `9bc1b2a288b26af7257a36277ae3816a7d4f16e89c1e7e77d0a5c48bad62b360`；内存摘要为 `8d9866eba7fdc8987fbacbda5290425f09b15cbfa6b7c9d2ce3e3d3ead45f8f6`。进程身份不是靠摘要猜测，还核对随机标记、PID和已打开文件内容。

约37秒包含故障处理、路由、SDK重试和数据恢复，不是VMM核心恢复耗时，不能与竞品热恢复或纯记账停顿比较。

### 3.5 恢复后文件描述符与映射

文件描述符是进程已经打开的文件句柄。采样在完整校验之后，不是全生命周期I/O跟踪。

| 运行时 | 实测与边界 |
|---|---|
| Firecracker私有盘 | overlay.ext4的FD位于目标/home/akernel/filestore/.firecracker，findmnt为XFS；目标写入已验，重建传输量与lazy block未测 |
| Firecracker内存 | memory FD位于JuiceFS artifacts，映射rw-p，即私有写时复制；这段映射的写入不会直接修改父文件，不代表下一次checkpoint后也不切换 |
| gVisor内存 | 采到runsc-memory、systrap-memory等Linux匿名内存文件memfd；不能因此说恢复过程没读JuiceFS |
| gVisor私有可写层 | 根数据语义通过，filestore配置XFS，但采样未出现filestore FD；**恢复后实际介质路径仍待进一步跟踪，不能只靠配置推断** |

没有新增P2P、OverlayBD、NBD或节点LRU服务。JuiceFS block cache=0、writeback关闭，但Linux page cache及S3服务端缓存仍在，不能称严格冷缓存跨物理机测试。

## 4. 结论

【实测】本地保存/主动回滚、真实JuiceFS同节点回滚、两执行节点间公共SDK故障接管通过；根RWFS与/tmp分开验证，512 MiB完整内存、身份和打开文件一致。

【实测】源进程和节点重返时，目标身份及数据保持不变。它不等于所有目标adxlet重启、跨进程读者保护和垃圾回收（GC）竞争均已验收。

【源码/配置】实例归属与恢复引用由ADX/Redis维护，JuiceFS/PostgreSQL维护文件元数据，S3保存数据块，没有另建catalog。

【边界】早期源失联时显式reload=False的轮次受DNS故障影响，不能简单定性SDK bug；正常同节点reload单独通过，故障接管用正常访问单独通过。原生SDK事后诊断没有冒充公共SDK验收。

【未验收】单宿主、单副本及认证兼容告警不满足生产HA；没有guest停顿、S3实际字节及竞品同口径数据。

## 5. 建议与改进项

1. 补全交接矩阵：同沙箱四并发和恰好一次捕获、四沙箱隔离、合法默认/边界参数、受控超时、客户端断连、上传失败不降级本地、提交前后adxlet重启、活读者GC保护及删除后引用/工件回收。
2. 归因三次更早的创建就绪超时：B上运行过FC后gVisor曾启动但execd未就绪，后来重启及部分相同节点FC→gVisor成功；不能由单轮成功关闭缓存端点反复混用风险。
3. 补gVisor恢复后RWFS实际FD/I/O、FC再次checkpoint后的内存映射切换、ACK后立即杀源客户端的持久化验证。本轮停止容器允许最多10秒优雅退出，不是断电。
4. 分开测停顿、持久化发布、故障检测、路由/SDK重试、VMM恢复、S3字节和工作集读取，再决定publish/cache/RWFS lazy收益。
5. 测试预检保护DNS等依赖故障域；生产由基础设施提供跨物理故障域HA与安全配置，不让应用工具越权改其他集群的系统服务。
6. 参数化helper的任务身份和宿主容量扣除量，保留校验，不放宽检查换“一键成功”。当前是已实测参考配置，不是任意机器一键部署产品。

## 6. 可复现步骤

全部在远端独立环境执行。固定源码/镜像/SDK构建见[构建附录](20261022T-pr119-pod-build-sdk-command-appendix.md)，私有集群见[部署记录](20261022T-pr119-pod-cluster-network-and-node-startup.md)，本地基线见[本地SDK检查](20261022T-pr119-pod-resume-local-sdk-acceptance.md)。

`T`为自己的新任务目录。按附录准备namespace helper、SDK venv、Go探针及目录；新任务必须登记自己的容器ID/PID/启动时钟与容量参数，不能填本轮旧值或取消校验。

~~~sh
# 仅在宿主所有者批准时临时调整，不写sysctl.d。
sysctl -n fs.inotify.max_user_instances > "$T/cluster/inotify-original.txt"
sysctl -w fs.inotify.max_user_instances=1024
python3 "$T/cluster/namespace-lab07.py" run --task "$T" -- \
  kubectl get --raw '/readyz?verbose'
python3 "$T/cluster/namespace-lab07.py" run --task "$T" -- \
  kubectl -n kube-system exec etcd-akcr119-20261022-control-plane -- \
  etcdctl --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt \
  --key=/etc/kubernetes/pki/etcd/healthcheck-client.key endpoint health
~~~

先在本地checkpoint profile跑基线，再切共享。初次安装及前提见[存储准备记录](20261022T-pr119-pod-sdk-storage-preparation.md)。救援脚本只在对应故障成立时执行，不能盲目重跑或删卷。

~~~sh
python3 "$T/storage/prepare_storage.py" --task "$T" --output "$T/storage/preflight16"
python3 "$T/storage/prepare_block_pvs.py" --task "$T"
python3 "$T/storage/install_storage_recorded.py" --task "$T"

# 本轮遇到udev缺失、旧格式化Job已失败时的受控处理：
python3 "$T/storage/copy_private_udev_data.py" --task "$T"
python3 "$T/storage/retry_juicefs_recorded.py" --task "$T"

# 必须真实挂载/跨客户端/持久化检查通过，且没有活动测试沙箱。
python3 "$T/storage/verify_attach_shared.py" --task "$T" --attach
python3 "$T/cluster/pin_private_dns.py" --task "$T"
~~~

CSI schema与私有loop节点分别由 `install_csi_schema_only.py`、`repair_private_loop_node.py` 处理。安装器失败不代表后台任务已结束，先检查真实PID/Job终态。只读观察器使用任务Redis Pod，其CLI不在PATH时，本轮仅在该Pod补链接：

~~~sh
python3 "$T/cluster/namespace-lab07.py" run --task "$T" -- \
  kubectl -n akernel exec akernel-adx-redis-0 -- sh -ec \
  'if [ ! -e /usr/local/bin/redis-cli ] && [ ! -L /usr/local/bin/redis-cli ]; then
     test -x /opt/adx/current/bin/redis-cli
     ln -s /opt/adx/current/bin/redis-cli /usr/local/bin/redis-cli
   fi'
python3 "$T/acceptance/scripts/read_control_state.py" --task "$T"
~~~

共享profile升级可能替换入口Pod。旧端口转发只能核对任务PID、启动时钟、进程组和命令归属后停止，不准killall。重新建立私有入口，控制端TLS校验保持开启：

~~~sh
python3 "$T/acceptance/scripts/prepare_sdk.py" --task "$T" \
  --output "$T/acceptance/auth-new"
python3 "$T/acceptance/scripts/run_sdk_recorded.py" --task "$T" \
  --auth "$T/acceptance/auth-new" --job "$T/acceptance/runs/shared-runsc-five" \
  --runtime runsc --rounds 5 --parameters
python3 "$T/acceptance/scripts/run_sdk_recorded.py" --task "$T" \
  --auth "$T/acceptance/auth-new" --job "$T/acceptance/runs/shared-fc-memory" \
  --runtime firecracker --rounds 1 --memory-bytes 536870912
~~~

完整接管探针会停止并启动校验过的本任务节点，需要独占此环境。`FORWARD_PID`、`FORWARD_START` 填本次prepare_sdk输出，不要填旧值：

~~~sh
test -n "$FORWARD_PID" || exit 1
test -n "$FORWARD_START" || exit 1
PR119_TEST_DISK_RWFS=1 python3 "$T/acceptance/scripts/launch_custom_probe.py" \
  --task "$T" --auth "$T/acceptance/auth-new" \
  --job "$T/acceptance/runs/runsc-disk-failover" \
  --script "$T/acceptance/scripts/sdk_failover.py" --runtime runsc \
  --forward-pid "$FORWARD_PID" --forward-start "$FORWARD_START"
# 前一轮须terminal.json rc=0，并有source_healthy_again和sandbox_deleted，
# 再用新job目录和--runtime firecracker执行另一种运行时。
~~~

`observe_runtime_storage.py --task T --job JOB --output OUT` 在通过事件后只读采样FD/maps，不能代替SDK任务终态。持续任务看worker.json的PID/启动时钟与terminal.json，不能把SSH超时当成结束。

`tools/pr119-pod-20261022/profiles` 提供脱敏Kind/Calico/Helm参考配置。它们需要新任务容量及身份重新生成，不包含kubeconfig、私钥、SDK环境或JuiceFS凭据。

## 7. 现场清理披露

源节点故障只针对本任务Kind容器，结束恢复节点、ADX服务与FUSE/XFS挂载。未停止其他使用者的服务。本任务自己的ADX Pod因profile切换重建，自己的DNS滚动迁移，不能说完全没重启任何组件。

最终权威目录无Environment记录，节点及任务Pod健康；没有统计全部S3对象或关闭GC收敛门禁。原失败目录/诊断保留，但运行态和工件可能被正常生命周期自动清理，不冒充仍可attach的完整现场。

旧实验探针对OnDelete DaemonSet误用rollout status，记录保留；新探针按新会话、实际启动时间、服务和挂载验源恢复。仅针对旧案例的 `crossnode_sdk.py`、`diagnose_recovered_sdk.py` 留原工作树/远端，未混入交付入口。

最后只读采集误查Ceph名akcr119-ceph；NotFound只是查询名错误。随后按实际资源读取rook-ceph，Ready/HEALTH_WARN；原输出未覆盖。

独立集群、存储和任务设备保留。40 GiB OSD镜像仍在用，不能直接删除或losetup -D；先退出本任务读者/OSD/卷使用者，再按backing文件和设备身份回收。磁盘可用约789 GiB，没有删除他人资源。

inotify原值128已记录，未持久化；集群仍运行暂保留1024。退役且确认无人依赖新阈值后恢复，不覆盖别人后续的全局调整。本轮只交付测试工具、配置、证据和文档，不产生新产品源码提交，不改三个gitlink；编译测试全部远端。
