# FC 后端十组对照完成与 gVisor 原语验收

## 开发内容

在 fdb145c 功能门通过后，用同一镜像/内存模式比较本地运行盘和 JuiceFS 运行盘，同时测普通写入成本、真实停顿、SDK 恢复和对象流量。继续准备 gVisor 的原生克隆，避免只看快照收益。

## 修改内容

产品源码与制品不变。正式同代码脚本只切两个 FC 可写盘字段，每次检查真实会话/路由/资源和载荷。远端 summarize-pairs01.py 生成白名单、四分位数和配对比；新增 final-state01.py 检查实际运行进程、介质和容量。原始时钟定义已更正，旧数值不改。

gVisor 独立候选基于 `.5` 精确源码 87e8441b6；源码只在独立工作树。远端正式对照成功后才启动 helper 三轮 race 与两客户端实际匿名文件/脏 mmap/克隆隔离验证，输入/格式化后 SHA 和 ELF 单列。未部署、不混进交付源码。源码检查另发现后台装入到外部副本捕获的顺序窗口，待确定性回归，不冒充已修复。

## 测试结果

正式 rc=0：20 独立实例/40 次保存与同节点 reload，完整内存/根文件/介质通过；最终恢复 native 配置。首次 checkpoint P50 8404.5→5507.5 ms，再次 11307→7574 ms；配对 10/10 更快。4 KiB 随机逐次同步的每实例中位数再取组中位数 0.300→9.588 ms；普通顺序 64 MiB 创建/写/同步 181.3→209.7 ms。每次 PUT 约 3→2 GiB，停顿仍约 5.0/7.3 秒，不是 SOTA 或全冷/跨物理机性能。完整分相/四分位数/原始数据见同日性能检查。

gVisor helper rc=0：Go1.25.5、x/sys v0.43.0、2 CPU/2 GiB/私有网络，容器三轮 race、两真实 JuiceFS 客户端各三轮通过。不是完整 Bazel、sentry seccomp、匹配 bundle 或 SDK 通过。全部编译测试仅 BareMetal，未修改共享服务。

最终只读 rc=0：Environment=0、两节点运行时/僵尸进程=0、五业务 Pod 就绪、API/真实路由/可调度通过。保留历史单份失败盘，helper 资源删除，宿主可用约 683.2 GiB。新数据/脚本和计划更新待推送；产品仍 fdb145c/image02。

## 可复现步骤

先核对原任务 `fc-backend-compare-pairs01/terminal.json` 与 summary-terminal，不能重复启动旧输出。统计命令和真实 fixture 入口见 `Docs/checks/20261024T-pr119-fc-backend-ten-pair-performance.md` 第 6 节；helper 结果见 evidence 的 gvisor-native-clone-helper01.json。源码、实际 ELF 和元组分别记账，候选全量 gate 未通过前不改默认值或发布新 bundle。
