# gVisor 后台恢复顺序回归与完整构建门

## 1. 问题

延续计划中的 gVisor JuiceFS 原生克隆：先核实私有文件数据后台装入与再次快照的顺序，随后验证完整组件和匹配 bundle，不能以独立克隆函数通过替代完整 SDK。

## 2. 方法

基线为 `.5` 源码 87e8441b6db18219fbb941378cfcb2883750b07c，加独立候选的文件范围克隆适配。新 `snapshot_async_load_test.go` 使用真实 split-file 保存 codec、AsyncPagesFileLoad、stateio.IOReader 和可控 ReaderAt 屏障，不用伪造 MemoryFile 状态。测试观察实际加载器的等待者，再释放输入并核对副本；另注入 EIO 检查错误不得被成功快照掩盖。

严格先保留旧 SnapshotToFd 顺序；旧红必须同时包含“背景输入仍阻塞时返回成功”和“加载失败后快照仍返回成功”两条特定语义断言。编译失败、依赖失败或不支持克隆均不能当作旧红。只有证据命中后，才将独立 AwaitLoadAll variant 复制进远端源码、三轮复测和相关组件/race/完整 bundle 构建。

全部在 BareMetal 本任务新目录 `gvisor-native-clone-bazel01`，沿用私有网络/挂载/cgroup，构建容器4CPU/8GiB，保留宿主650GiB；超限只按CID/任务标签停止本构建。Bazel8.3.1 官方资产 SHA-256 为17247e8a84245f59d3bc633d0cfe0a840992a7760a11af1a30012d03da31604c。没有安装系统软件或修改共享服务。

## 3. 数据

当前仅登记新任务：驱动PID3115311/start_ticks215119448，输入包SHA b03d7243aaa263e516a678d179127850fc2ba9444530b7609a69472e5e063e2f。正在取得精确源码/工具和构建依赖，尚无旧红、新绿或完整构建终态；以实际current/terminal、进程及Bazel日志为准，不预填通过。现役仍fdb145c/image02/debbf268…/原runsc `.4`，Environment为空，本轮不部署。

首轮 bazel01 已停止，驱动与其容器均不存在，旧生产函数 SHA 仍为 d4d850b0…，未应用修复。Bazel 编译成功、实际屏障回归出现“背景输入未释放即返回成功”的断言；第二用例在探针检查处停止，因为加载器把 unix.EIO 归一化为 linuxerr.EIO，不能以 errors.Is 对比二者。本轮未把该失败当作完整两项旧红。保留全部原记录，仅改探针按既有 linuxerr 契约检查，另存 bazel02，串行复用已验证缓存/工具，不覆盖旧输出。

bazel02 续记：两条严格旧红均命中成功返回断言；AwaitLoadAll 最小修复三轮通过，源码由d4d850b0…变为d43b4672…。随后相关四目标编译停在 tools/xdp/cmd/bpf:pass_ebpf，原因是本任务Go基础镜像没有clang；未将它归因于产品逻辑，也未继续race或bundle。驱动/构建容器确认退出。正在另建本任务专有clang/libbpf构建镜像，不修改宿主包或共享服务；后续新输出重新跑所需gate。

私有工具镜像续记：clang-builder01 rc=0，eBPF编译探针通过，setup容器删除；镜像固定f153bb72…472cc78。仅任务容器内装包，宿主和共享服务未变。bazel03另存以同一源码/工具/缓存和不可变镜像ID重新执行完整gate；当前尚待终态，不把镜像就绪当运行时通过。

bazel03 续记：相同两条旧红/三轮新绿再次通过；四目标进一步构建在公共 systrap 信号处理生成处因缺 aarch64-linux-gnu-gcc 停止。上游默认镜像包含 crossbuild-essential-arm64，最终 amd64 包同样需要这一构建依赖。本轮保留原证据，只在新的私有 clang-builder02 加该依赖；首个 helper 目录写错在 mkdir 失败，未启动或修改旧目录，随后修正。builder02 rc=0、探针和清理通过，镜像ID147178fbc1464e4f4d2b65ff91ac1e52683430cd11e188d1d37659b24cb53148。

bazel04 续记：两项旧红/三轮新绿按九文件精确SHA复用，不再盲目重复已完成步骤；四个相关目标 rc=0，用时194.219秒。正在继续相同目标race和完整六ELF bundle，尚无整轮终态。Bazel标准库分析有GOVERSION提示，但动作整体完成成功；保留原提示，不修改go.mod或屏蔽分析。

bazel04终态：四个普通目标rc=0；race三目标通过、pgalloc失败（Bazel rc=3，子测试Exit255，整轮rc=1），完整bundle未执行。原测试日志止于TestDefaultSaveStillDecommitsOnDestroy，内核记录pgalloc_test被8GiB内存cgroup杀死；Podman事件将CID24ccde395bf563de21c5b9612a16522bfa36555fa808086d75d61452b59de259明确归属本轮related-race。不是数据竞争报警，不计race全绿。消费qa01依赖失败退出，没有构建或部署。

源码确认旧hostFilePatternOk只断言前1MiB，却os.ReadFile整份1GiB稀疏文件并在轮询中重复。仅把读取改为io.ReadFull所断言范围，逐字节及短读失败语义保持；不加内存或跳过race。新增bazel05，九文件产品候选不变，加一个旧测试辅助修复。重新执行pgalloc普通及三轮race，其他三个同源码通过目标复用，再继续完整包。新消费qa02仅排队等待实际运行时成功。现场实际内核只读核对为7.0.0-31-generic，历史6.8记录不作为当前事实。

bazel05续记：有界读取修正后pgalloc普通目标和三轮race全部rc=0（race27.300秒），原异步捕获等待/EIO回归也包含在三轮目标中；另外三个同源码目标普通/race沿用bazel04成功回执。完整六ELF包正在构建，消费qa02仍等待。bazel04原stdout/stderr/BEP/terminal均保留，失败pgalloc的12585字节输出从原stdout另存，Podman归属和内核同CID OOM行保存于failure-evidence；共享Bazel缓存test.log/xml已更新，不冒称保有原缓存文件。

bazel05最终rc=0：完整包67566256字节，SHA-256 63aa235350012e44020c8a9b404c677d2ce8894f167249ca7e5516ba3970cafa；六个独立程序均为amd64 ELF。最终源码status只有清单内十文件，没有MODULE.bazel.lock等额外变化。随后sandboxd消费qa02全套源码门通过，ELF f81eec47…；镜像打包首轮RUN因任务cgroup父目录约束失败，没有导入或部署。新image02改为只检查停止的任务专有基底容器、验证原四helper清单，再完整COPY六程序，不改变宿主cgroup/内核或降低隔离，后续实际结果待记录。

## 4. 结论

【组件实测】两条原顺序问题已通过真实加载器动态复现，最小等待/错误传播修复转绿。bazel05已完成有界旧测试辅助读取后的pgalloc普通/三轮race，另三目标普通/race复用同源码成功回执；完整六ELF amd64包构建及布局/架构/SHA校验通过。SDK尚未验收，工具镜像前提与旧OOM失败原件仍保留。

【边界】此前 CloneFilestore 函数的三轮 race 和两个 JuiceFS 客户端门仍有效；新增组件实测已覆盖 SnapshotToFd 后台读取顺序、采纳及系统调用过滤的相关目标，原race整组因旧测试的整文件读入触发内存限额失败；修正测试辅助后pgalloc三轮转绿且完整bundle通过，SDK仍未完成。整个开发目标保持进行中。

## 5. 建议与改进项

旧红与最小等待修复已通过，继续尚未完成的 race 和完整 amd64 bundle（runsc、shim 与四 helper），保留原失败。格式化源码已按摘要回填本地，sandboxd #78 复用、专有目录与挂载校验留在另一个未验收工作树；消费层质量门串行等待完整运行时门成功，再考虑部署和 SDK。不得因观察超时重复启动同一个输出目录，不能通过跳过隔离、下载校验或数据验证获得通过。

## 6. 可复现步骤

仅在远端独立任务执行，旧输出不可重放覆盖：

```sh
cat "$ROUND/tap-checksum-fix/gvisor-native-clone-bazel01/launch.json"
cat "$ROUND/tap-checksum-fix/gvisor-native-clone-bazel01/current.json"
cat "$ROUND/tap-checksum-fix/gvisor-native-clone-bazel01/terminal.json"
# 组件顺序，具体资源/输入身份以driver01.py为准：
# old-order -> fixed-order(三轮) -> related-tests -> related-race -> release
```

实际执行脚本在 `tools/pr119-pod-20261024/candidates/gvisor-native-clone-bazel/`，仍为未验收准备，不发布成产品实现。固定variant只加复制前AwaitLoadAll及错误传播，不在旧红之前改旧顺序。

## 7. 现场清理披露

新增独立源码/缓存/工具目录和受控构建进程，没有启动新VM或修改现役Pod/配置。未在本地编译测试；输入只含候选源码/脚本，不含凭据或运行数据。上一轮FC对照和helper均已成功结束，不混跑；失败则保留原记录并按真实进程/容器身份恢复，不触及旧环境或共享服务。

## 续记：匹配消费层完整 SDK 已通过

同一bundle63aa2353…与sandboxd f81eec47…随后通过官方76项、各三轮完整状态回滚和两个运行时的双向跨节点。源码整理为gVisor218d85378/sandboxd21fb466并普通push个人fork，实际字节未变；最终实例与运行时0。组件问题已修复且核心SDK通过，完整新布局故障/分支、配对性能和正式推广仍单列，见[阶段总结](../stages/20261024T-pr119-gvisor-native-sdk-stage-summary.md)。
