# PR #119 本轮验收脚本

本目录保存 2026-10-23～24 在 BareMetal 独立任务环境实际执行的源码与小型来源清单，不含凭据、二进制或运行数据。所有编译测试只能在远端独立环境执行。

`executed/` 保留历史代码和摘要。部分脚本固定了旧任务目录、Pod/容器身份、文件摘要和输出目录；这是防误操作的身份检查，**不能在新环境原样运行，也不能删除检查后碰运气重试**。它们不是任意主机的一键安装器。新任务应另存配置、记录自己的身份和摘要、先做只读预检，再运行；保留历史脚本作为已测来源。

完整流程的公共底座仍是 `tools/pr119-pod-20261022/`。先按中文复现文档在远端准备固定源码、完整运行时包、独立 Kind/Pod、TLS、任务凭据、XFS 与真实 JuiceFS，再使用本轮就绪门、SDK 夹具与观测器。Python 依赖 `acceptance`、`read_control_state` 等沿用该底座，不需要另造控制面或 catalog。

| 入口 | 用途与前提 |
|---|---|
| `executed/wait-adx-ready01.py`、`storage/wait-perf-ready02.py` | 新会话、路由、资源、真实镜像和 ELF 校验；Pod Ready 只是其中一项 |
| `executed/qa03.sh` | 源码旧红/新绿、fmt/vet/全仓单测/runsc race/生产构建；容器挂载和依赖缓存须预先准备 |
| `executed/storage/sdk-full02.sh` | 固定公共 SDK 的两运行时 integration/standalone，不跳过 OCI 用例 |
| `executed/storage/cross-node05.py`、`sdk-failover03.py` | 源真实退出、公共 SDK 接管、完整状态与源重新加入 |
| `executed/storage/run-*.py`、`sdk-*.py` | 崩溃、忙删除、配额、超时、S3 停顿、并发恢复及挂载替换；只允许操作已证明属于本任务的资源 |
| `executed/storage/run-performance-pairs02.py`、`sdk-performance01.py` | 十组 AB/BA 对照、每实例两轮、完整状态和 RGW 字节；旧 OCI 只读，最终恢复新组 |
| `executed/storage/performance-observation02/observer.go` | 远端构建的 2 ms guest 调度间隙观测器；不是精确宿主 pause |
| `executed/storage/native-clone-helper01.py` | 可直接指定独占路径/nonce/角色的 JuiceFS 原语探针；跨客户端冷目标克隆和后续隔离校验 |
| `executed/storage/go-clone-helper01/clone_probe_test.go` | 与精确版本的 reflink.go 在独立目录远端编译，调用 FC 现有函数；不复制产品源码到父仓 |

`executed-source-index.json` 给出从远端取得时的源码 SHA-256。故障脚本均含身份边界；不要把历史 PID 或设备号改成当前看见的第一个进程。原始服务日志可能含临时执行凭据，本交付仅保留白名单统计 JSON，不上传原日志。

新文件和命令复现的结果不自动等于历史已测字节。重建后应记录新的制品摘要，并重做相应的 SDK 验收。两条后端路线尚未达到产品级通过，勿将这些原语作为生产开关。
