# gVisor 私有存储三配置十组对照进度

## 开发内容

在完整SDK和原生布局故障门通过后，验证将私有运行文件搬到JuiceFS及保存时使用原生克隆各自的代价；避免把不同代码、客户端资源与内存模式混成性能优化结论。

## 修改内容

只新增独立测试/统计/元数据脚本，没有产品源码、API或正式默认值变化。`tools/pr119-pod-20261024/experiments/gvisor-backend-compare/`的driver每例只切换runsc三个字段，重启本任务Node Pod，等待新会话、路由与容量稳定，核验15制品及控制Pod/Secret身份；fixture通过公共SDK完成两轮状态回滚并核验真实私有FD介质。顺序六种轮换，每组相同逻辑节点，两逻辑节点按组交替。

首次smoke01在checkpoint前因内部`/filestore`挂载别名误判，原件保留，源64MiB文件核验后SDK退休。02版只补已证实别名，保留具体Sentry/沙箱/匿名文件/设备检查；成功试跑后相同SHA进入正式30实例。`summarize-trios01.py`按配置/轮次/实例统计和组内配对；`collect-trios01.py`只拆分白名单JSON及实际脚本，最终盘点原件也交付。

更新中文计划、七节检查、阶段总结、版本台账及独立性能清单。源码仍sandboxd91dff2f/gVisor218d85378，实际ELF43357403…/CRI0bde46ba…、六程序包63aa2353…，不重建，不改历史gitlink/正式pin/default。后续QEMU文件导出只做源码/工具存在性检查，未实现新后端。

## 测试结果

正式`gvisor-backend-trios01`、最终原生配置恢复/真实就绪、`gvisor-backend-final01`、远端统计/导出均rc=0。30实例/60次完整512MiB内存与64MiB根文件回滚通过；每配置每轮n=10。C原生克隆首次/再次checkpoint请求P50为1332.5/1195.5ms，A本地full为1400/1218ms；C的reload稍快，但普通写入更慢、首次应用执行间隔未改善，默认值保持。B第二轮恢复区间额外231.44MiB PUT尚待归因。

客户端实际4GiB且进程/启动代次不变，OOM/oom_kill无增量，memory.max事件仍增加1537/1432；DS模板仍2GiB。最终Environment/运行时/相关僵尸为0、五业务Pod镜像一致、两端15制品一致可调度，旧FC失败盘保留，宿主余量超过650GiB。

37份脱敏证据、8份实际脚本SHA逐份核对；归档84626字节，SHA-256 `8111169dc5be1ccd34f342ceedd44d60c8b75c9cbae35c0c41d76f73bff5d41f`。源码质量门沿用同一字节已通过的全仓门，本轮未改产品代码，不重复构建；脚本语法、SDK与统计全在远端。没有共享服务/旧环境/宿主参数或全局缓存变更。

### 可复现步骤

以下是本任务实际命令，路径/Pod身份固定，新环境须按README另存适配。不要重放到已有输出目录：

```bash
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
D="$N/round-365f797-20261023.clPWh2h0/tap-checksum-fix"
I="$D/gvisor-backend-compare02-input"
python3 "$I/run-backend-compare02.py" --output "$D/gvisor-backend-smoke02" --pairs 1
python3 "$I/run-backend-compare02.py" --output "$D/gvisor-backend-trios01" --pairs 10 \
  --require-smoke "$D/gvisor-backend-smoke02/terminal.json"
python3 "$D/gvisor-backend-final01-input/final-state01.py"
python3 "$D/gvisor-backend-summarize01-input/summarize-trios01.py" \
  --terminal "$D/gvisor-backend-trios01/terminal.json" \
  --output "$D/gvisor-backend-trios01/public-summary01.json"
python3 "$D/gvisor-backend-export02-input/collect-trios01.py"
```

全部分位数、配对值、S3字节/操作数、逐例状态和清理证据见[检查](../checks/20261024T-pr119-gvisor-three-group-performance.md)。两条路线的总目标仍未完成，下一阶段是真正的远端只读基线＋本地差异，不把本地full组当作该后端。
