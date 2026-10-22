# 故障注入前的 DNS 放置门禁

两个CoreDNS副本曾全部落在执行节点B。停B同时使JuiceFS无法解析PostgreSQL，污染一次gVisor恢复：内存读取EIO、初始化超时。只读端点检查确认故障域后，本任务将DNS迁到控制节点，同方向重新验收通过。

在真实存储与两Node Pod就绪后、首次节点故障之前执行：

~~~sh
python3 "$T/cluster/pin_private_dns.py" --task "$T"
~~~

该helper校验任务控制容器身份，只修改这套私有集群的CoreDNS nodeSelector，保留原配置与失败记录；等待两个副本和DNS服务端点都在控制节点，再从两执行节点实际解析PG/RGW。不改宿主DNS或其他集群。

新环境须登记自己的容器ID，不能取消身份门禁。两DNS副本同在唯一控制节点是实验布置，不是生产HA。生产由基础设施提供跨真实故障域DNS，不应让应用工具越权修改共享集群。
