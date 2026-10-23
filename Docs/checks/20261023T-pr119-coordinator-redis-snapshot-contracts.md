# PR #119 Coordinator 快照与回收 Redis 契约检查

日期：2026-10-23。固定 ADX `6fb53d7` 的六个既有测试远端通过，未修改或部署产品源码。

## 1. 问题

补齐共享快照引用、并发获取/删除、失败回收的组件证据，区分模型/Redis 契约与真实 SDK 故障验收，避免用测试名称中的 restart 冒充实际 Coordinator 进程重启。

## 2. 方法

按固定 ADX 仓 AGENTS 的长构建测试委派要求，复用本任务远端只读源码和独占 2 CPU / 6 GiB / 2048 PID 容器。实际 Rust/Cargo 1.95.0、Redis 7.0.15、protoc 3.21.12；锁文件不变，实际测试网络 `none`。Redis 仅在容器专属 Unix socket 监听，port=0，AOF 开启、appendfsync=always，不接触集群 Redis。

六个测试直接使用 RedisStore/RedisSession；新建会话模拟 Coordinator 所有权变化。其中 busy 测试确实重启了私有 Redis，并加载相同 AOF；这与另行完成的四组真实 Rust 角色 SIGKILL 验收分开。

## 3. 数据

| 目标 | 结果 | 范围 |
|---|---|---|
| `adx-coordinator --test snapshots -- --ignored --test-threads=2` | 4 passed，0 failed，0 ignored | 忙快照/Redis 重启、身份与租户隔离、物理回收前保留 deleting、获取/删除原子竞争与禁止重新发布 |
| `--test storage failed_collection_age_survives_retry_and_coordinator_restart -- --ignored --exact --test-threads=1` | 1 passed，50 filtered out | 失败回收年龄跨重试/会话保留 |
| `--test storage invalidated_failed_collection_is_atomic_and_fences_replacement -- --ignored --exact --test-threads=1` | 1 passed，50 filtered out | 失效回收的原子更新和替换围栏 |

获取/删除用例内部循环 24 次，仍只计一个测试；filtered 不计通过。与之前 checkpoint-storage 10 项、snapshot_busy 2 项合计 18 个不同测试。

源码 1320 文件摘要前后一致、无新增；峰值内存 4821450752 字节，OOM/PID 触顶为 0。八次 Redis 启动含预检一次、六个用例与一次同数据目录重启。[小型回执](evidence/pr119-juicefs-tapfix-20261023/coordinator-redis-contracts.json) 保留命令、完整用例名、隔离、日志摘要和清理信息。含编译 wall time 不作为产品性能。

## 4. 结论

【远端组件实测】六个既有 Redis 契约通过，补强引用裁决和回收状态的基线证据。

【边界】不是实际 Coordinator 主进程崩溃、真实 JuiceFS 内部 DELETE 交错、完整 SDK 或性能对照，不能单独关闭完整生命周期门。

## 5. 建议与改进项

与真实 SDK 角色崩溃、共享文件物理删除证据一同审查。后续精确补超时、失败发布和内部屏障，不以重复扩大单测数量替代缺失的端到端场景。

## 6. 可复现步骤

```bash
ssh BareMetal
N=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp
T="$N/round-365f797-20261023.clPWh2h0/tap-checksum-fix/storage/contract-tests01/coordinator-attempt01"
cat "$T/terminal-receipt.json"
cat "$T/logs/coordinator-snapshots.stdout"
cat "$T/logs/failed-collection-age.stdout"
cat "$T/logs/invalidated-failed-collection.stdout"
```

完整 Cargo 命令如表；复测只在独占容器内，依赖沿用 locked/offline，源码只读挂载，不在本地或共享宿主运行 Cargo。

## 7. 现场清理披露

六个测试的临时 AOF 目录由原生 TempDir 正常删除，日志留档；预检 AOF 保留于任务证据目录。自有容器、派生镜像和 cgroup 已删除，缓存保留供后续用。两个测试结束后的空闲 PID1 容器在 Podman stop 等待 10 秒后被 SIGKILL，警告原样留档；测试已先返回 0，没有误杀其他进程。集群、共享服务、运行镜像、父仓 gitlink 均未改。
