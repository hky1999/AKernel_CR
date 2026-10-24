# OverlayBD v1.0.18：本地差异路线的复用范围与接入门

## 1. 问题

继续“JuiceFS 原生克隆”和“远端只读基线＋本地差异”两条路线对照。FC 优先复用成熟 OverlayBD；检查它的文件 lower、在线快照、同步和启动边界能否直接满足当前 ADX/SDB 的 checkpoint 契约。

## 2. 方法

只读 GitHub 官方仓库，经 tag 引用与 Git tree 双重解析，v1.0.18 对应完整 commit `cee2186ca75670f6c3d48a4b79c2b43a7134fba5`。按该 commit 读取源码，逐一核对返回的 blob SHA 与 tree；不是拿最新 main 当发布版本。

读取 README、src/api_server.cpp、src/image_file.cpp、src/image_service.cpp、src/main.cpp、src/overlaybd/lsmt/file.cpp。未在 BareMetal 编译、启动或创建 OverlayBD 设备；最初源码检查时正在运行 FC 后端交替测量，避免叠加负载或触及共享内核。

## 3. 数据

| 能力/边界 | 精确源码证据 | 判定范围 |
|---|---|---|
| 文件 lower | image_file.cpp:268–290，配置 file 非空时经本地文件适配器打开，否则才考虑远端 Registry | 可复用 POSIX 文件入口；合法 LSMT/Zfile 放 JuiceFS 有接入基础，不证明真实跨客户端按需读已通过 |
| 在线快照接口 | api_server.cpp:62–84 调用 create_snapshot，成功才返回 200；image_service.cpp:538–553 按开关启动服务 | 可以复用已有 API，不自行实现块映射算法；服务默认关闭 |
| 状态切换先于配置替换 | image_file.cpp:587 restack，590–604 改当前层与索引，612 才 rename 配置 | 后段 rename 失败仍可能已经切层。HTTP 500 不能解释为“没有发生操作”，不能盲目重试或删新文件 |
| 配置闭包校验 | image_file.cpp:577–579 对 lowers 的检查被注释；580 比较新 upper 与 conf 中路径 | 调用方须构造并验证完整层链、全新代次路径，不能将 API 成功替代依赖完整性检查 |
| fsync 返回值 | lsmt/file.cpp:989–1000 检查 group commit，但未检查 data/index 文件的 fsync 返回值，最后返回 0 | 确定的源码错误传播缺口；还没有做故障注入，不能写成已复现数据损坏，也不能直接作为生产同步契约已验收 |
| 封存与切层 | lsmt/file.cpp:1038–1073，close_seal 后切 backing/index 并更换可写文件；1077–1085 在互斥下调用 | 复用成熟封存/层管理；与 guest 内存、设备排空及远端确认的一致性仍由接入层负责 |
| TCMU 启动动作 | main.cpp:477–512 调用 block_netlink/reset_netlink 参数 setter，并固定注册 overlaybd subtype | 不能仅因私有 /etc 就认定已隔离宿主影响。启动前必须核对现役 TCMU 使用者及全局作用域，不能重置他人服务 |

主要源码链接：[在线快照实现](https://github.com/containerd/overlaybd/blob/cee2186ca75670f6c3d48a4b79c2b43a7134fba5/src/image_file.cpp#L561)、[LSMT 同步](https://github.com/containerd/overlaybd/blob/cee2186ca75670f6c3d48a4b79c2b43a7134fba5/src/overlaybd/lsmt/file.cpp#L989)、[TCMU 初始化](https://github.com/containerd/overlaybd/blob/cee2186ca75670f6c3d48a4b79c2b43a7134fba5/src/main.cpp#L477)。发布 tag 的 docs/live-snapshot.md 不存在；README 内联说明和已核对源码才是本次证据，不拿另一 commit 的独立文档冒充 tag 内容。

补充【实测，只读宿主盘点】：target_core_user 已加载，block_netlink 显示 unblocked；reset_netlink 为写入型/读权限不足，本次未读取到值。未发现可见的 overlaybd-tcmu/tcmu-runner 进程、TCMU UIO 名称或 configfs user_* backstore。此刻没有现役使用者的可见证据，不证明将来可任意修改全局参数；真正启动前还须重新检查并约束独占，当前没有启动或写入。

补充【源码】：同一版本 lsmt/file.cpp:800–814 的 group commit 只把索引写入文件，并不包含 fsync；因此不能用它消解上述同步返回值缺口。append_index:820–828 另有忽略 append/group commit 错误的路径，需要与 I/O 故障回归一并审查，尚未做动态损坏复现。官方 latest release 仍为 v1.0.18，不能假定存在已发布的新版本修复。

## 4. 结论

【源码】OverlayBD 已有文件 lower、局部写层、封存与在线切层，可复用，不需要重新开发块级 COW。它不是把任意 raw ext4 文件直接作为 LSMT 层；初始模板转换和格式身份仍需验证/计费。

【源码】现版本存在具体的同步错误传播和快照非整体原子边界。接入不能只做 curl 成功后上传文件；必须先补同步错误回归、操作结果对账、文件/层依赖闭包、重启恢复和失败保留。还没有动态故障数据，不据此宣称整个项目不可生产。

【外推，待实测】不可变 LSMT 层以文件方式放 JuiceFS、本地写层留 XFS 有望避免独立 Registry。实际读取量、缓存叠加、格式转换与层链增长成本须在 SDK 链路验证，不能替代现有两条路线的最终对照。

## 5. 建议与改进项

1. 正式性能测量结束后，先只读盘点宿主 TCMU 模块、全局参数、现役进程与 configfs；禁止为了实验重置他人连接或共享服务。不能证明隔离时，先评估已有成熟替代，不直接启动。
2. 对 data/index fsync 返回失败补确定性旧红/新绿。若采用版本未修复，候选带最小、可审查补丁和固定源码/制品，不能忽略错误来获取性能。
3. 接入操作使用独立 nonce/代次和日志；API 超时/后段失败先对账。现有调用可已切层，未确认前不释放新旧数据或默认继续旧路径；与 SDB 的暂停/恢复、失败基线失效统一处理。
4. 每份发布工件包含自洽的全部层成员，或显式登记父依赖到 ADX 原有引用模型。可以评估 JuiceFS 文件克隆形成自包含层集合；不能隐藏绝对父路径、另建权威 catalog，或把本地未上传的写层当作远端已持久化。
5. 通过两个分支、至少两代、后台/按需读时写入、同步故障、重启/进程死亡和回收门后，才与原生克隆按相同协议比较。当前 FC 本地/原生基线十组还不是本条路线的实现。

作为可选成熟替代，QEMU 官方提供 storage daemon 的单文件 FUSE raw 导出，可把已有 raw 基线叠加 qcow2 差异后呈现为普通盘文件，源见 [官方说明](https://www.qemu.org/2021/08/22/fuse-blkexport/) 与 [storage daemon 文档](https://www.qemu.org/docs/master/tools/qemu-storage-daemon.html)。这只是能力入口，不是本任务验证：需要固定实际版本、证明导出后持有 FD 的在线切层、flush/错误传播、后端死亡恢复、VMM Async 兼容和层依赖；FUSE 又增加一跳，也不能直接用于 gVisor 的 MemoryFile。未选择替换 OverlayBD，未下载、安装或启动 QEMU。若 OverlayBD 为修复同步/隔离需要较多自研，可按既定计划 5.2 的成熟替代条款做成本比较，不先开发自研块映射服务。

## 6. 可复现步骤

只读源码核验，可在调研目录或远端执行，不构建、不安装到共享系统：

```sh
git ls-remote https://github.com/containerd/overlaybd.git refs/tags/v1.0.18
# 已有独立源码副本中读取固定 commit，不切换他人的工作树：
git show cee2186ca75670f6c3d48a4b79c2b43a7134fba5:src/image_file.cpp
git show cee2186ca75670f6c3d48a4b79c2b43a7134fba5:src/overlaybd/lsmt/file.cpp
git show cee2186ca75670f6c3d48a4b79c2b43a7134fba5:src/main.cpp
```

同样可以使用上述固定 commit 的 GitHub 文件链接。动态错误注入、构建和 SDK 验收只在远端独立环境，尚未执行，不能将本篇源码调查计为动态通过。

## 7. 现场清理披露

本检查只读外部官方源码并写本地文档/小型来源索引；没有在 BareMetal 下载、构建或启动 OverlayBD，没有新块设备、模块、全局参数或共享配置变更。源码检查期间远端仅既定 FC 对照；正式测量结束后才执行 gVisor 独立克隆函数门，未启动任何 OverlayBD/QEMU 实验或修改其宿主参数。
