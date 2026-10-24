# gVisor 原生克隆核心 SDK：实际执行脚本

本目录与相邻 `gvisor-native-clone-bazel/` 保存本轮远端实际脚本，精确来源见 `source-index.json`。产品Go源码只在组件仓中；父仓不复制产品代码或二进制。

- gVisor driver01–03保留工具依赖/探针失败；driver04普通四目标通过，race三过一项因旧测试整文件读取触发任务cgroup OOM；driver05只改旧测试辅助的读取范围，pgalloc普通/三轮race通过并完成六程序包。其他同源码已过目标按回执复用。
- setup-clang01/02仅创建私有构建镜像，不在宿主装包；ARM64交叉编译器是上游已有的公共生成依赖。
- 消费层driver01因运行时依赖失败退出，未编译/部署；driver02通过fmt/vet/全仓单测/相关race/build。
- prepare-image01新增RUN被cgroup父目录约束拒绝；prepare-image02检查停止的私有基底容器，确认原四helper完整后COPY完整六程序，三Kind节点导入一致，不改宿主cgroup。
- run-full-sdk01完成实际独立部署、真实就绪/15制品门、官方76项、各三轮状态及双向接管；final-state01只读盘点成功，实例/运行时/僵尸均0，原一份失败FC盘保留。

脚本包含固定旧任务目录、对象身份和失败依赖链，供审计使用。新独立环境直接按[远端构建与配置说明](../../../../deploy/experiments/README-pr119-gvisor-native-rwfs.md)获取组件，生成自己的配置/Secret/输出；不直接在旧任务上重放这些脚本，不关闭隔离、不复用未知运行资源。没有本地编译测试、原始服务日志、凭据或二进制进入本次交付。

核心SDK通过不等于新布局全故障/分支、同代码性能或生产推广通过，剩余见[阶段总结](../../../../Docs/stages/20261024T-pr119-gvisor-native-sdk-stage-summary.md)。
