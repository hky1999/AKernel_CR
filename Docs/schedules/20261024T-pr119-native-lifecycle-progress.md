# 原生 JuiceFS 私有层存储故障与再次保存验收进度

## 开发内容

在sandboxd91dff2f/gVisor218d85378完整SDK及归属崩溃修复之后，补两个原生私有可写层的存储故障和“内存恢复尚未读完就再次保存”的动态门。只用BareMetal独立Kind/Pod/存储；产品字节、ADX/SDK和正式默认值不变，不修改共享服务。

## 修改内容

新增`tools/pr119-pod-20261024/candidates/native-storage-faults/`，复用原四个存储探针和读者身份/三秒控制屏障；新增顺序执行器、SDK加载重叠检查、只读EINTR有界重试、三份明确区分失败与最终通过的救援、Kubernetes客户端资源原地增配和白名单导出器。两个生成的最终盘点脚本也保留实际字节。

函数级改动：执行器`empty_and_ready()`限制独占空实例和真实节点状态；`hold-reader-control02.py::input_fds()`对EINTR最多一秒重试；`sdk-pending-capture02.py::capture()`在独立线程发起SDK请求并核验屏障时序；`resize-owned-juicefs-pods01.py::run()/get()`执行带UID测试的resize与实际资源确认。失败原版和最终版按SHA分别留档。

没有新产品Go/Rust代码。源/实际ELF/CRI仍91dff2f、43357403…、0bde46ba…；完整六程序包仍63aa2353…。两端客户端限制从2到4GiB，通过resize子资源服务端dry-run和实际分配检查；Pod/容器/重启次数不变，缓存和任务40GiB/沙箱限制不变，DS模板仍2GiB。预算覆盖与未来模板配置分开记账。

更新七节检查、阶段总结、执行计划和VERSION。九份16298字节白名单及17份脚本来源均按SHA核对；不复制原日志/凭据/二进制。

## 测试结果

| 项 | 结果与口径 |
|---|---|
| gVisor/FC挂载遮蔽 | 各512MiB应用负载；故障期间拒绝、无本地误写、源未保存状态保留、恢复后再次保存和SDK清理均通过 |
| gVisor/FC S3暂停20秒 | 各1GiB应用负载；观测确实不可用、不错误提前确认、核清未知结果、跨节点恢复、后续保存/reload和清理均通过 |
| 待加载真实页输入期间再次保存 | 双向各1GiB应用/2GiB沙箱；请求确实与打开的pages输入和短停重叠，恢复后才确认；新快照完整内存/1MiB根文件读回及后续保存/reload、忙删除/清理通过 |
| JuiceFS客户端 | 双向测试前后工作进程/启动代次不变，OOM/oom_kill无增量；实际4GiB |
| 原失败保留 | 首次EINTR发生在注入/保存之前；首次救援文件流中断；第二次救援预检遇已消失旧记录；三者不计通过 |
| 最终救援 | 原快照另一端完整1GiB内存/1MiB根文件、后续保存/reload通过；读者/快照由SDK退休；旧Failed记录已自行消失，不虚报为本轮删除 |
| 最后盘点 | 两Node实际15制品一致、可路由/可调度；Environment/运行时/相关僵尸0，原旧失败盘保留 |
| 质量门 | 新脚本仅远端语法及真实SDK检查；产品未改，复用前一轮91dff2f全仓fmt/vet/test/相关race与官方76项证据，不冒称本轮重跑 |

首次异常与客户端2GiB分组OOM/工作进程更换相关，尚未做独立客户端死亡因果实验。增配后通过不能关闭这一生产故障边界。当前三组性能试跑在另一目录进行，不包含在本轮功能交付或性能样本中；远端基线＋本地差异尚未实现。

## 可复现步骤

以下为已执行任务的命令位置；目录有独占创建保护，不直接重复运行或把旧身份复制到新机器。新任务先按README另存适配并远端检查。

```bash
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
Q="$N/round-365f797-20261023.clPWh2h0"
D="$Q/tap-checksum-fix"
python3 "$D/native-storage-faults01-input/run-native-storage-faults01.py"
python3 "$D/owned-juicefs-resize01-input/resize-owned-juicefs-pods01.py"
# 救援通过后，按新输入目录执行两个方向；凭据由任务私有SDK环境提供。
python3 "$D/native-pending-capture02c-input/run-pending-capture02.py"
python3 "$D/collect-native-lifecycle01.py"
```

本地只编辑、传输、核对摘要和整理Git；没有本地编译测试。详细失败、资源预算覆盖和清理见同日native-storage-faults-pending-capture检查。
