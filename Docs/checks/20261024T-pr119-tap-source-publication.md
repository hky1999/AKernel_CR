# PR #119 TAP 修复源码整理与推送检查

日期：2026-10-24。已将通过验收的两文件修复提交到独立组件分支并普通 push；没有发布新运行制品。

## 1. 问题

远端 SDK 验收曾依赖未提交的 TAP 修复，需要让外部同事能获取实际使用的源码；不能混入并行 Kata/upstream rebase 改动或未验收候选。

## 2. 方法

从已验收基线 d5acc3b 新建独立工作树与 codex/pr119-tap-reset-20261024 分支。只取远端实际 QA 源树的 network.go 与 network_tap_reuse_linux_test.go，按文件 SHA-256 核对。Git hooks 目录没有活动脚本；本地只编辑、核对和提交，没有本地编译测试。格式、vet、全仓单测、runsc race、旧红新绿回归及 SDK 均取前轮同字节远端结果，不伪造重跑。

## 3. 数据

提交 [10312f2](https://github.com/hky1999/sandboxd/commit/10312f28c9b3286545eb2e97070cdd08fe994cee)，父 d5acc3b，普通 push 到 hky1999/sandboxd 的同名新分支；两文件 153 行新增：

- OpenTAP 在 TUNSETIFF 后清零遗留 TUNSETOFFLOAD，错误沿原 FD 清理路径返回。
- 显式 opt-in 的 Linux 回归在调用方独立网络命名空间中创建自己的 TAP，三轮交替设置 vnet consumer 的 checksum offload 与打开 raw queue，校对状态并清理；未启用时明确 skip，远端特权门已显式执行。

文件与 ELF 摘要、质量门范围见 [源码交付回执](evidence/pr119-juicefs-tapfix-20261023/tap-source-publication.json)。完整 SDK 为本地/真实 JuiceFS 各 76 个既有用例、均无跳过；公共 SDK 自动接管是两运行时各 A→B、B→A。它们不等于本轮所有存储故障或性能门全部关闭。

## 4. 结论

【Git 与文件实查】外部同事可以获取这份确切的修复源码，已不依赖远端未提交文件。其他工作树和原 PR 分支未修改。

【边界】测试制品仍是此前固定的 sandboxd ELF 9c74060c…；本轮没有重新构建、打 release 或将提交后重建产物宣称为相同字节。父仓 gitlink 和复现分支交付仍待整理。

## 5. 建议与改进项

父仓交付中固定源码提交和实际制品两套身份，补齐远端脚本与脱敏数据。未来重建须使用新制品摘要及配套模板再验收，不仅更新版本字符串。并行 runtime/Kata 候选仍单独保留。

## 6. 可复现步骤

```bash
git clone --branch codex/pr119-tap-reset-20261024 git@github.com:hky1999/sandboxd.git
git -C sandboxd rev-parse HEAD
git -C sandboxd show --stat 10312f28c9b3286545eb2e97070cdd08fe994cee
sha256sum sandboxd/pkg/runtime/runsc/network.go sandboxd/pkg/runtime/runsc/network_tap_reuse_linux_test.go
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
D="$N/round-365f797-20261023.clPWh2h0/tap-checksum-fix"
cat "$D/qa03-runner/terminal.json"
cat "$D/out03/status.json"
```

远端质量命令及原始失败/修正见 20261023T-pr119-tap-offload-local-sdk-acceptance.md；复测只在独立容器中显式启用 TAP fixture，不在共享宿主网络或本地运行。

## 7. 现场清理披露

源码整理工作树为 /home/keyang/AKernelWorkspace/codex-pr119-tap-delivery-20261024，提交后干净，保留供维护。没有操作其他工作树、旧服务、沙箱、宿主参数、镜像或模板。性能轮换实验独立记录，不算作源码提交时的环境变更。
