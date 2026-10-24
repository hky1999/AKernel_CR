# Firecracker 同代码私有盘后端对照

这是一组在 BareMetal 独立任务实际执行的验收脚本，不是产品实现，也不是可在任意共享机器直接执行的部署器。脚本包含固定任务根目录、Kind 身份、Pod/镜像及制品摘要；复现时另存新任务副本并重建等价隔离，不能移除身份校验。编译测试只在远端执行。

## 测什么

固定 sandboxd fdb145c、同一 image02/ELF debbf268…、VMM/内核/initrd/runsc/ADX/SDK、Full 模式与缓存条件，只删除/恢复两个可写盘后端配置字段。本地 XFS 盘在 checkpoint 时复制到 JuiceFS，与运行态盘直接放 JuiceFS、卷内克隆进行比较。后一组的普通运行写入也进入远端。

`guest-storage-io.go` 仅是验收工作负载：固定种子生成 64 MiB，分开记录 guest 内 write/file fsync/directory fsync，另做 64 次 4 KiB 随机覆盖和逐次同步，独立 SHA 校验最终文件。生成数据、SDK 往返和完整读回不计入存储写时钟。它不提供业务存储服务。

`build-driver01.py` / `build-qa01.sh` 在私有 Go 1.25.5 容器中编译，2 CPU/2 GiB，网络 none，使用本任务 cgroup/Podman graph。

`sdk-backend-compare01.py` 通过公共 SDK 创建实例，连续两轮保存恢复，校验 512 MiB 应用状态、64 MiB 根文件以及实际 VMM 盘 FD/文件系统；区分第一次 checkpoint 与恢复后再次 checkpoint，保存 guest 调度间隙、SDK 延迟、宿主分相和 S3 GET/PUT。

`run-backend-compare01.py` 先核对实时容量、空 Environment、所有制品摘要、真实新会话/路由/可调度。每 case 更新/重启仅本任务 Node Pod，控制/API/Redis 与 Secret UID 必须不变。每对在同一执行节点，奇数组本地→JuiceFS、偶数组反向，节点按组交替；每后端十个独立实例，每实例两轮。基础设施和 Linux 缓存保持自然状态，不清共享缓存。

`summarize-pairs01.py` 是已准备的远端离线统计器，须正式二十实例全部成功后执行；已在远端正式终态成功后执行，白名单二十实例数据与配对统计见同日正式检查；不能用试跑数据替代正式样本。

`run-pairs-after-smoke01.py` 只在试跑已有终态成功、fixture 摘要一致、Kind 身份正确时启动正式任务；没有终态的任务不能因观察超时重启。

## 复现顺序

先按父仓 delivery 清单与可选实验配置建立自己的独立双 Node 环境。以下变量必须指向该任务：

```sh
cat "$TASK_ROUND/tap-checksum-fix/fc-backend-io-build01/terminal.json"
cat "$TASK_ROUND/tap-checksum-fix/fc-backend-compare-smoke01/terminal.json"
cat "$TASK_ROUND/tap-checksum-fix/fc-backend-compare-pairs01/current.json"
# 原任务还在运行时只读观察；新任务在前检齐备后才独立启动：
python3 "$TASK_ROUND/tap-checksum-fix/run-fc-backend-compare01.py" \
  --output "$TASK_ROUND/tap-checksum-fix/fc-backend-compare-pairs01" --pairs 10 \
  --require-smoke "$TASK_ROUND/tap-checksum-fix/fc-backend-compare-smoke01/terminal.json"
```

先核对原 PID 与 start_ticks 和 terminal；命令不支持原地覆盖输出，失败保留资源，不能盲目清库。每个 case 的原始 YAML/凭据、OCI 日志与运行环境 ID 只在远端私有目录；父仓仅保存白名单数据。

## 结果边界

两个布局试跑已经通过；十组正式测量整体 rc=0，20 实例/40 次完整状态通过，最终恢复 native，见同日正式性能检查。试跑与旧 fixture 不合并。64 次随机同步是同一实例内的相关操作，统计以实例/配对为单位，不当作 640 个独立沙箱。当前仅比较已有本地盘和原生克隆，没有实现“远端只读基线＋本地差异”，也不代表 gVisor 或冷缓存性能。
