# gVisor 原生克隆候选准备

## 开发内容

在 FC 的原生 JuiceFS 私有盘功能验收之后，继续计划中的 gVisor 对应工作。保留已有应用内存保存/后台恢复，复用 filestore 冻结内捕获和非消费式采纳，避免把文件数据和应用内存一并迁移。

## 修改内容

独立工作树 codex-pr119-gvisor-native-clone-20261024 基于 `.5` 发布包的精确源码 87e8441b6db18219fbb941378cfcb2883750b07c，而非 10 月 rebase 的另一候选。新增 checkpoint.CloneFilestore，优先 FICLONE、不支持时走同文件系统 copy_file_range；处理短复制/中断/部分失败，不做用户态全量回退。SnapshotToFd 和 adopter 共用，原大小/资源 ID/指纹/同步协议保留。sentry seccomp 限定两个持有 FD 和 flags=0，并准备相关回归；源码未提交。

首次直接读取全部候选源码用于传输时超出工具输出上限，本地 JSON 解析即停止，没有远端写入或构建。改为小型压缩输入包，接收前核对长度/SHA、精确成员集合及大小，另存任务目录，原源码工作树保留。

新增远端 helper-driver01.py / helper-qa01.sh，固定 x/sys v0.43.0 及原 go.sum，两 CPU/两 GiB、任务私有网络/挂载/cgroup，在两个实际 JuiceFS 客户端验证同一克隆函数。驱动严格等待正式 FC 对照 20 实例成功终态、最终 native 布局及 Environment=0；不能在性能测量中并行构建。

## 测试结果

驱动登记时仅完成源码准备和远端脚本语法前检，后续结果在下段续记；当时未将候选标为通过。helper 驱动 PID 2855469、start_ticks 214850143，登记时等待正式性能依赖；不把已有 FC 或上游 CI 结果转记为该候选通过。当前实际运行 fdb145c / image02 / debbf268… 和原 `.4` bundle，未更换。

续记：正式 FC 二十实例/四十次保存恢复整轮成功后，helper 已自动执行并 rc=0：Go1.25.5/x/sys v0.43.0 容器三轮 race，两个实际 JuiceFS 客户端各三轮匿名脏 mmap、私有克隆和错误/短复制边界通过。ELF 5605d610…；源函数 7e31e5e2…、回归 69d4bba3…，远端格式化的七文件按输入原 SHA 校验后回填独立工作树，未本地构建测试。两客户端临时二进制和测试目录全部删除，产品制品不变。完整 Bazel、后台恢复捕获顺序、匹配 bundle 与 SDK 仍未完成；源码未提交/交付。

## 可复现步骤

在远端任务根目录内先检查 `gvisor-native-clone-helper01/launch.json`、`current.json`、`terminal.json` 和记录 PID/start_ticks。driver.py 是本任务受控入口，已有进程尚在或没有终态时不能重复启动。完整候选来源和待执行 Bazel 目标见同日 `Docs/checks/20261024T-pr119-gvisor-native-clone-candidate-boundary.md`。所有编译测试仍只远端、失败保留，不关闭资源隔离或修改共享服务。
