# PR #119 独立 Pod + JuiceFS 核心 SDK 验收进度

日期：2026-10-22。本篇是实际工作进度，不是下一阶段计划。

## 开发内容

恢复被inotify上限阻塞的独立集群，固定版本打通公共SDK→ADX→sandboxd→运行时→共享存储。分开验证主动回滚、节点故障接管、根RWFS，不用/tmp或基础探针冒充全部验收；不改旧环境，不在本地编译测试。

## 修改内容

| 文件 / 函数 | 本轮工作 |
|---|---|
| VERSION.md | 固定版本、临时参数、部署、DNS修正、验收结果与残余边界 |
| copy_private_udev_data.py::main | 只读宿主udev描述，送入任务私有节点 |
| retry_juicefs_recorded.py::main | 对已失败Job核对UID重试，不重建PG/OSD数据 |
| verify_attach_shared.py::main | 真实挂载、内容和持久化门禁后切共享profile |
| read_control_state.py::read_control_state | 只读现有ADX/Redis权威目录，不建平行catalog、不输出密码 |
| pin_private_dns.py::main | 仅移动本任务DNS，验证真实端点及两端名称解析 |
| launch_custom_probe.py::main | PID/启动时钟、子进程、日志、真实终态与私有转发归属 |
| sdk_failover.py::main | 同一公共SDK对象、无硬绑节点，内存/根RWFS、源重新加入、目标身份和删除 |
| observe_runtime_storage.py::main | 通过事件后的只读FD/maps，不把配置当I/O实测 |
| profiles、checks、stages、evidence | 脱敏配置、中文复现入口和小型JSON，不提交凭据、镜像或RAM |

旧固定案例实验脚本留原现场，未作为交付入口。没有产品源码修改、运行时新commit或三个gitlink变化；父仓提交以Git记录为准。

## 测试结果

- 临时128→1024恢复集群，先验etcd/API；结束再验通过，三节点Ready。
- 两种运行时本地六个任务共14次checkpoint/reload，含各五轮、八项非法参数和完整512 MiB内存。
- 真JuiceFS三客户端、PG持久化、跨客户端内容通过；两运行时的基本回滚与512 MiB回滚均通过。
- 首轮gVisor故障被DNS和源节点共址污染；只移动任务DNS后，同方向B→A重测通过，未把旧EIO计作已确认数据损坏。
- gVisor两轮A→B、FC一轮B→A的1 MiB根RWFS+512 MiB内存通过；源重新加入后目标身份/内容不变，测试沙箱删除成功。另有gVisor B→A及FC A→B内存用例通过。
- FC恢复后的overlay.ext4 FD在目标XFS，memory在JuiceFS且为私有写时复制映射；gVisor恢复后filestore FD未采到，介质路径仍需确认。
- 三次早期创建就绪超时未归因；全量并发/故障/GC矩阵、生产HA和SOTA对比未完成。产品源码未改，全仓fmt/vet/test未在本轮重跑，不冒充新增产品提交的全仓门禁。

同节点512 MiB单样本：gVisor本地/共享checkpoint为729/1117 ms，reload为1014.590/3061.137 ms；FC为2668/5973 ms、2681.094/6712.452 ms。不是停顿，不是稳定五轮收益。

根RWFS故障接管，从正常读取触发到完整内存：gVisor3656.914、4880.728 ms；FC7646.183 ms。停止源之前起算约36.7、36.4、37.7秒，包含故障处理和路由，不等于VMM核心恢复。

## 可复现步骤

逐命令步骤、固定版本、数据和清理见[检查文档](../checks/20261022T-pr119-pod-juicefs-sdk-failover-acceptance.md)，汇总入口见[阶段总结](../stages/20261022T-pr119-pod-baremetal-reproduction-stage-summary.md)。

入口为prepare_sdk.py、run_sdk_recorded.py、launch_custom_probe.py、sdk_failover.py。根RWFS须PR119_TEST_DISK_RWFS=1。故障前先保护DNS/存储/控制面，前轮终态并恢复源健康后才开下一轮，不能重叠停两节点。

原始失败留远端，集群与存储保留，可用约789 GiB；未清他人数据。退役后再按原值恢复临时inotify。
