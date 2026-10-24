# gVisor 三种私有存储配置对照

正式采样、最终原生配置恢复/真实就绪、独立盘点及远端统计均rc=0。30实例、60次完整状态保存/reload通过。产品为同一sandboxd91dff2f/gVisor218d85378、同一43357403…/0bde46ba…字节，应用内存后台恢复开关不变。所有构建/语法/SDK/统计仅在BareMetal独立任务执行；本地只编辑、传输、核对摘要和整理文档。

结果见[七节检查](../../../../Docs/checks/20261024T-pr119-gvisor-three-group-performance.md)。C首次/再次checkpoint请求P50为1332.5/1195.5ms，A为1400/1218ms；C的SDK reload略快，但普通运行写入更慢、首次停顿未改善，不切换正式默认值。这里比较的是同节点自然缓存恢复，不是跨物理机或对象全冷数据。

## 三种配置

| 组 | 正常运行时私有文件数据 | checkpoint格式 | 比较用途 |
|---|---|---|---|
| A，`full-local-xfs` | 本地XFS匿名文件 | 完整保存，文件数据随保存输出到JuiceFS | 基线 |
| B，`full-native-juicefs` | JuiceFS匿名文件 | 与A相同的完整保存 | A/B分开衡量介质变化 |
| C，`clone-native-juicefs` | JuiceFS匿名文件 | 独立私有文件清单及卷内克隆 | B/C分开衡量克隆格式；A/C衡量整套候选 |

这三组不包含尚未实现的“远端只读基线＋本地差异”后端。gVisor私有文件是保存可写文件数据的后端句柄，不等于把guest每个目录/inode直接搬到JuiceFS；目录等状态仍随gVisor内核检查点保存。共享卷是另一条链路。

同一实例两次保存：第一次正常启动后保存，第二次在reload并完整校验之后再次保存。每次都修改再回滚512MiB应用内存、64MiB确定性根文件和小标记，验证实际源/恢复存储介质。沙箱配置1vCPU、2GiB内存、1GiB私有容量。

先各一例试跑，再十组；每组同一逻辑节点上运行三个独立实例，共30实例、60次完整保存/reload。六种先后顺序轮换，节点按组交替；未独立随机化节点与顺序，不宣称一般统计显著性。缓存自然使用，不清宿主全局缓存。两端JuiceFS客户端实际4GiB、缓存参数不变，始末PID/start_ticks和OOM计数设门。每次部署重新验证节点新会话、路由、资源、15文件摘要、控制Pod/Secret身份和空间余量。

## 实际脚本

- `run-backend-compare01.py`、`sdk-backend-compare01.py`：首次试跑保留。真实文件在本地XFS，但FD显示gVisor内部`/filestore`别名，首版要求宿主路径字符串相等而误判；未发起保存。
- `rescue-smoke01.py`：只核验该实例64MiB文件并通过SDK退休，原失败保留。
- `run-backend-compare02.py`、`sdk-backend-compare02.py`：补内部别名识别，仍核验具体Sentry/沙箱、匿名文件和设备号；三配置试跑及每例两次状态回滚已通过。正式采样复用同一SHA，不重新构建产品。
- `summarize-trios01.py`：整轮成功后已在远端执行，分轮次、配置和同组配对统计，保留全部30样本。
- `executed/final-state01.py`：实际执行的只读盘点原件，零Environment/运行时/相关僵尸、15制品/节点就绪及原生配置恢复检查通过；保留旧FC失败盘。
- `collect-trios01.py`：实际远端白名单导出器，37份脱敏JSON、8份实际脚本；不导出原始服务日志、配置和认证环境。第一个未执行的导出器准备目录因遗漏救援字段另存修正，实际执行的是`gvisor-backend-export02-input`。

第一次失败是观测错误，不是产品保存/恢复失败，也不计入正式数据。脚本路径/Pod/身份固定于独占任务，需要在新环境另存适配并远端预检，不能照搬到另一台机器。

## 数字口径

保存请求耗时、SDK reload、首次根文件可用、完整内存/文件读取分开记录；恢复的S3读取量区间直到完整校验结束，不等于仅到业务首次可用的读取量。应用的最大执行间隔是暂停影响的观测值，也含调度影响；gVisor没有本fixture里的FC分相日志，不借用FC字段。

64次小块写/同步先按实例求中位数，再以每配置10个独立实例统计，不能算作640个独立样本。gVisor tmpfs上层文件的Sync不是宿主JuiceFS持久化屏障，因此不与FC ext4的fsync绝对值直接横比；checkpoint远端同步另行完成。源证据为gVisor218d85378的`pkg/sentry/fsimpl/tmpfs/tmpfs.go::fileDescription.Sync`和`filesystem.go::filesystem.Sync`。

全部reload在原逻辑节点；两个节点处于同一BareMetal，不代表跨物理机或对象全冷性能。未做E2B/AgentEnv/Cube同条件复测，也不将历史FC/fdb145c数据混入91dff2f的本轮样本。
