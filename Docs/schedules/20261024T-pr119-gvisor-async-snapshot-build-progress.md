# gVisor 后台恢复到快照的确定性交错回归

## 开发内容

在原生克隆函数已通过真实JuiceFS客户端后，补齐实际MemoryFile捕获边界。任务暂停不代表旧后台页加载已停止，需要用实际加载器验证再次checkpoint不会捕获缺页占位数据。

## 修改内容

独立gVisor候选新增snapshot_async_load_test.go和pgalloc_test依赖，复用真实split-filecodec/异步加载器，ReaderAt停在输入屏障；观察真实等待者而非靠sleep宣布等待。另注入EIO，要求快照失败。AwaitLoadAll修复仅生成单独variant，旧顺序先跑。

新增bazel-entry01.sh/driver01.py，新远端gvisor-native-clone-bazel01校验精确87e8441源码与Bazel8.3.1官方digest，4CPU/8GiB/私有网络/cgroup、650GiB余量门。只有两条旧语义成功返回断言真实命中，才做固定顺序三轮和组件/race/完整bundle；没有本地编译测试或部署。

## 测试结果

当前只有脚本语法前检与启动回执，驱动PID3115311/start_ticks215119448，尚无旧红/新绿/构建终态。源候选仍未提交，现役fdb145c/image02与SDK结果不变；不得把单函数门、准备状态或初始rc=1误报为整体通过或失败。

续记：bazel01 编译通过，首项确实在背景输入屏障未释放时返回成功；第二用例因探针比较错误类型（unix.EIO vs加载器归一化linuxerr.EIO）停止。驱动/容器确认退出，源函数d4d850b0…未变；没有应用Await修复。修正探针类型和Bazel依赖后另存bazel02，使用串行缓存，不重写旧记录；完整双旧红/新绿仍待终态。

bazel02 续记：两条旧语义成功返回断言均命中，最小Await修复三轮通过；后续相关组件因构建镜像无clang停在eBPF生成，未执行race/bundle。该轮驱动/容器已确认退出。正在只给本任务新构建镜像增加官方gVisor基础依赖clang/libbpf等，未在宿主安装或改共享服务。完整gate和SDK仍待完成。

## 可复现步骤

先查新任务launch/current/terminal并核对PID/start_ticks。实际阶段命令与严格旧红条件见driver01.py和同日gvisor-bazel-async-snapshot-regression检查。此目录有固定任务身份，只在另存的独立环境适配，不能对共享环境照抄、覆盖失败或盲目重启。

## 本轮续记：工具前提与消费层复用

bazel03的两项旧红/三轮新绿再次通过，公共信号处理生成进一步需要官方已有ARM64交叉编译器；只在本任务clang-builder02镜像补齐，rc=0，setup容器按身份回收。此前启动辅助脚本误指已有builder01目录，在mkdir失败，未改变旧目录；修正后PID3396856/start_ticks215343908完成。bazel04 PID3402436/start_ticks215348802复用相同九文件的回归回执，相关四目标194.219秒通过，race/bundle待终态。

sandboxd独立候选复用PR#78的checkpoint_mode/manifest/非消费式采纳，同时补runsc专有目录和实际FD/挂载核验，不改变全局filestore或FC内存模式。目录替换和匿名/采纳FD等回归已写，尚未编译测试；gvisor-native-consumer-qa01必须等待上述完整运行时bundle通过后才执行远端fmt/vet/test/race/build，不自动部署。正式发布分支仍a314a81，实际运行仍fdb145c/image02/旧runsc .4，不将未验收代码计入交付。

## 本轮续记：race 内存失败定位及有界读取修正

bazel04四个普通相关目标通过；race三个通过，pgalloc在旧测试辅助函数整文件读入期间被8GiB cgroup杀死。Podman事件CID与内核OOM完全匹配，源九文件未变，bundle和消费qa01均由依赖门停止。现役和共享服务未受影响。

仅修改save_restore_external_test.go的hostFilePatternOk：旧逻辑反复把1GiB稀疏文件os.ReadFile，再比较前1MiB；改io.ReadFull读取原断言范围，保留每字节检查及短读失败。不通过增额或跳过race取得绿。新bazel05 PID3701581/start_ticks215493353继续同私有镜像/精确工具，复用其他三目标，通过pgalloc普通/三轮race后才构建完整包。消费qa02另存依赖，所有旧失败文件保留；实际BareMetal内核为只读核对的7.0.0-31-generic，不更改任何宿主参数。

## 本轮续记：完整包、消费层与实际部署

bazel05整轮rc=0，匹配完整包67566256字节/SHA63aa2353…；消费qa02完整fmt/vet/全仓单测/相关race/build绿，ELF f81eec47…。两源码工作树均按远端格式化摘要核对，未在本地编译测试，未提交推送。image01的RUN因任务cgroup父目录约束失败，原件保留；image02只检查停止的基底容器、验证四helper清单再COPY完整六程序，三Kind节点导入CRI0806341c…/leaf4d18c0fa…/configf8036516…一致，检查容器已删。未改变宿主cgroup或降低隔离。

SDK01 PID3799802/start_ticks215591412在空Environment/无旧VM、两端私有目录同卷及原bootstrap/Secret门后部署新候选；新会话/路由/资源连续三次稳定与15文件摘要门通过。当前实验已运行新.5候选，不再记为原.4。FC integration8项通过，其余官方SDK、状态和跨节点仍在执行，不预填通过；无新性能对照结论，生产pin/default未改。

## 本轮收尾：核心 SDK 全绿、候选源码已推

官方76项（每运行时8集成+30独立端到端）、各三轮512MiB内存/64MiB根文件回滚、每运行时两个方向512MiB内存/1MiB文件自动接管全部通过，SDK01终态rc=0。最终只读盘点rc=0：Environment0、两端运行时与僵尸0、五Pod候选镜像、15文件SHA一致，公共XFS与各原生JFS目录明确，原FC失败盘一份保留、gVisor仅marker；可用719370366976字节。

gVisor218d85378357f9726fc3c0f7cf878cf19772d360与sandboxd21fb4668431cef88d05b7a789a2bd9a5e19e827c均普通push个人fork且ls-remote匹配，两树干净。实际字节均为提交前构建、源逐一匹配，没有重建冒充。9份脱敏白名单证据30315字节进入父仓；新增核心阶段总结，执行计划先补原生布局剩余故障/分支与同代码配对，再进入本地差异。正式pin/default不改，不把功能试跑当稳定提速或生产完成。父仓复现分支准备整理推送。
