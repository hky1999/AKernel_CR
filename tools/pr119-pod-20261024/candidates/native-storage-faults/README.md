# 原生 JuiceFS 私有层故障与加载重叠验收

这里保存 BareMetal 独立任务实际执行的脚本，包括明确失败的原版。产品源码没有进入父仓；产品元组继续使用 `delivery/pr119-cgroup-durable-leases-20261024.json`。它们有固定任务路径、Pod/进程身份和输入摘要，不能直接在其他机器运行，也不是通用一键部署器。

## 已执行脚本与结果

| 脚本 | 实际用途和结果 |
|---|---|
| `run-native-storage-faults01.py` | 固定已测镜像，复用现有四个存储探针；两个运行时各挂载遮蔽/S3暂停一次，四例及盘点通过 |
| `sdk-pending-capture01.py`、`run-pending-capture01.py`、`hold-reader-control01.py` | 首次加载重叠检查；`/proc`读取被EINTR中断，尚未短停或发起保存即退出；不算通过 |
| `rescue-pending01.py` | 首次救援，下载根文件连接中断，未完成；原件保留 |
| `rescue-pending02.py` | 第二次救援在旧Failed记录已不存在时预检失败，未创建新读者；原件保留 |
| `resize-owned-juicefs-pods01.py` | 两端独占JuiceFS客户端2→4GiB；Kubernetes resize子资源先dry-run，实际确认Pod/容器/重启次数不变，不重挂卷、不改缓存或任务总限制 |
| `rescue-pending03.py` | 根据只读证据允许旧失败记录已不存在；原快照在另一端完整1GiB内存/1MiB根文件、后续保存/reload通过，最后由SDK退休读者与原快照 |
| `hold-reader-control02.py` | 仅对EINTR有界重试，仍核验实际输入FD、命名文件和进程身份，三秒内恢复原读者 |
| `sdk-pending-capture02.py`、`run-pending-capture02.py` | 双向真实未结束内存输入期间发起SDK保存；请求返回时序、新快照完整读回、后续保存/reload、引用与清理通过；客户端未重启、OOM计数不增 |
| `executed/*final-state01.py` | 本轮生成并执行的两个只读收尾盘点，均通过 |
| `collect-native-lifecycle01.py`、`collect-native-lifecycle02.py` | 仅从既有证据导出字段白名单、脚本SHA与两个盘点脚本；第二版明确本轮没有角色重启，不新增实验 |

四个复用探针仍在 `../../executed/storage/`：`sdk-mount-shadow01.py`、`shadow-owned-shared-mount01.py`、`sdk-s3-pause01.py`、`pause-owned-rgw01.py`。新的证据索引逐份匹配它们的原始SHA，没有擅自更新固定身份后重用旧结果。

## 新环境的使用顺序

1. 先按父仓Pod/JuiceFS中文复现文档建独立环境，取得自己的证书、连接配置和存储卷；固定当前源码、完整运行时包和实际ELF摘要。编译、语法检查、SDK和性能测试都在远端执行。
2. 在安装JuiceFS客户端之前设置资源预算。本轮原客户端2GiB遇到内存压力；用于双向重叠测试的两个客户端实际4GiB、缓存参数未变。当前现场仅改了两个现有Pod，DS模板仍2GiB，第三客户端未改；未来替换Pod不会自动继承这两个覆盖值。新环境应在模板中声明预算，不复制本轮Pod UID或直接修改宿主cgroup。
3. 用新任务的路径、namespace、Pod/容器、PID/start_ticks、cgroup和ELF摘要另存脚本；先在远端语法检查，再验证节点新会话已注册、可路由、资源可调度。不能仅依据Pod Ready开始SDK调用。
4. 先正常SDK/状态/双向接管，再顺序进行挂载、S3和真实待加载输入测试；每例以terminal为准，失败即停。观察连接超时不等于任务结束，不重复发起未知操作。
5. 故障恢复进程独立运行且有界。检查其恢复终态后，通过SDK核清请求结果和退休资源；不能按目录名直接删除仍可能被读取的工件。

## 证据与边界

`Docs/checks/evidence/pr119-native-lifecycle-20261024/`九份白名单共16298字节；其中17份实际执行/复用脚本的SHA逐一与父仓源匹配。该统计不把导出器算作产品验收脚本。元数据压缩包SHA为`2cee47e44d72e5b764c4707968bbda88b5a117ec8dbc0442e8f30e298c595a82`，原日志、配置、凭据、OCI和运行数据不入库。

这轮没有新产品构建或性能结论。SDK请求与真实待加载输入重叠不单独证明内部某行等待函数执行；组件确定性回归、SDK动态证明分开记账。增配后通过不等于客户端进程死亡恢复、生产资源配置或物理高可用已验收；首次异常的完整因果仍是待办。三组性能和远端基线＋本地差异层仍按计划继续。

导出字段说明：实际SDK探针沿用旧字段名`busy_delete_after_restart`，该值在本轮仅表示活读者使快照删除被拒绝；本轮未重启控制角色。第二版白名单将其明确命名为`snapshot_delete_rejected_while_reader_alive`，并显式输出`control_role_restart_injected=false`。第一次导出原件仍保留，不修改实际测试源码或重跑测试。
