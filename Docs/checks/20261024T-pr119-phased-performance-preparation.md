# PR #119 分相性能对照准备与版本边界
日期：2026-10-24。本文保留准备时的状态；后续十组交替已完成，最终结果以 [正式性能检查](20261024T-pr119-ten-pair-phased-performance.md) 为准，未观察到稳定提速。

## 1. 问题
先完成当前架构的同条件对照，区分控制面/Execd 版本变化、网络正确性修复、存储布局和缓存影响，再决定 JuiceFS 原生克隆或本地差异后端。不能用几次不同环境的耗时宣布提速。

## 2. 方法
全部构建、语法检查和 SDK 试跑在 BareMetal 本任务独立环境执行。只读验证旧 OCI 与历史验收摘要一致后，导入本任务私有 Podman graph，构建旧控制面对照镜像；原旧环境、SDK 文件和镜像归档均不修改。

新旧两组共同使用已经验收的 d5acc3b 加 TAP 状态修复 sandboxd，及同一组 runsc、FC、kernel/initrd。旧组保留 6ea0041 / ADX 59fa791 的控制面、Execd 与根镜像；新组为 365f797 / ADX 6fb53d7。两套 SDK 也分别来自各自固定版本。因此比较包括 SDK、控制面、Execd 和配套根镜像，不是未修改的旧 PR，也不能把差值归因于一个开关。

另编译任务专用 2 ms 周期 guest 观测器，通过 Unix socket 读取/重置调度间隙。重置与采样时间在同一锁下记录。此间隙包含 guest 调度和虚拟时钟行为，只作为停顿观测，不称为精确宿主 pause。现有 FC 日志的 pause 字段只是 pause API 阶段，不是整个停顿窗口。

## 3. 数据
[候选回执](evidence/pr119-juicefs-tapfix-20261023/performance-candidates.json) 记录构建步骤、摘要与范围：
- 远端准备 performance-prepare04 rc=0，尚未部署旧组。
- 旧组候选 config fbfba99f0334584086a3603125903bef1eaba9bd27396a1fe5e4361cfaa2daf8。
- 旧组 OCI SHA-256 15c4c3a0c3fe37566c679323138251d18e8530e352aee5a257bf861358a3792c。
- OCI 叶 manifest 为 a46c88b9dae948bffc410779a871ce629337ceb03c3ea7fb91664346eeff2e06；Kind 实际 CRI 回报导入索引 9840a277eeb71a1685c3c06b0838b2992434fdc791906751a0d47b9a0c6658f5。后续已逐层验证索引→叶 manifest→config 关系，见小型身份回执；两者不能机械作为相同摘要比较，也不能用 Podman inspect 的另一媒体格式摘要替代。
- 观测器 ELF SHA-256 634c4dad69f853adb10ec8cd51542b4aee47b1d2c4268402cea2692244d4d273，仅为测试工具，不替换运行时。
- SDK 旧组公共 0.2.0rc3 / 原生 0.1.0rc2；新组公共 0.2.0rc3 / 原生 0.1.0rc3，安装包与源版本分别固定。

保留三次准备失败：01 使用当前 podman build 不支持的 --cpus；02 字符串替换未匹配；03 检测到前次预留空目录并拒绝复用。都未部署旧组或启动 SDK。04 使用经远端 help 核对的 cpu-period/quota、受控复用空的本任务目录并保留原件，通过所有准备步骤。第一次观测器编译未单独留返回码，后续监督式构建已留 rc=0，不能伪造首次退出码。

## 4. 结论
【实测】旧镜像只读摘要、共同修复候选与新观测器准备通过。
【边界】候选可构建不等于 SDK 通过；performance-smoke01 正在试跑，不计正式样本。未完成至少十组新旧交替、冷读取归因或尾延迟统计，尚不能给出提速百分比。

## 5. 建议与改进项
先验证测量夹具的状态校验和字段，再以一致的资源、缓存、持久化配置轮换候选；部署后重新检查会话、路由、容量与实际载荷。区分首次捕获和恢复后再次捕获。RGW 数字为本任务端点计数增量，未证明唯一对象范围或 RAM/RWFS 精确归因，不当作网络线速字节或完整 lazy 证据。

## 6. 可复现步骤
```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
S="$N/round-365f797-20261023.clPWh2h0/tap-checksum-fix/storage"
cat "$S/performance-prepare04-launch-receipt.json"
cat "$S/performance-prepare04/terminal.json"
cat "$S/performance-smoke01-launch-receipt.json"
cat "$S/performance-smoke01/terminal.json"  # 仅存在且 rc=0 才能记试跑通过
```
准备为 performance-prepare04.py，观测源码为 performance-observation02/observer.go，SDK 夹具为 sdk-performance01.py，监督驱动为 run-performance-smoke01.py。复测另建输出与资源，不能覆写失败目录；产物不入父仓。

## 7. 现场清理披露
准备容器均为本任务私有 graph、2 CPU / 2 GiB / 1024 PID，使用独立 cgroup，结束后自动删除；新镜像、测试工具与缓存暂保留。旧环境、共享服务、宿主参数、当前运行制品、模板及父仓 gitlink 没有变更。性能试跑仍可能有本任务沙箱，未提前清理依赖。
