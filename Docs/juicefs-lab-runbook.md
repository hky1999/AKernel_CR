# Independent JuiceFS functional lab

Use a dedicated remote test host. Do not run this against the original shared machine's occupied ports or existing services. The helpers refuse conflicts instead of stopping another task.

The accepted client reports `juicefs version 1.4.1+2026-07-30.0b90c7d`. The original functional backend used PostgreSQL 17 (observed 17.11) and Ceph 20.2.4 RGW. Deployment image tags in historical helpers are not a production HA design or immutable image digests.

Copy only helper source into a new private task profile; never copy the original `secrets/`, generated YAML, Redis data or `.config` contents into Git. Install the pinned JuiceFS client into the task's private `bin/` and prepend that directory to PATH. Stage ADX, sandboxd and runtime artifacts built/verified from the delivery manifest, including a matching static guest-agent initrd.

The existing source helpers expose these commands:

```text
lab.py --root ROOT {init,start,format,mount,unmount,stop,status,check-data,exec}
node_network.py --root ROOT {up,down}
native_profile.py --root ROOT --generation GEN --volume-uuid UUID --runtime {runsc,firecracker}
runtime_nodes.py --root ROOT --generation GEN --node {source,target} {setup,status,exec,stop,...}
short_profile.py --root ROOT --generation GEN [--node NODE] {prepare,activate,filestore,...}
```

Use `--help` for node-specific mount/exec options. Native generation names use `native` followed by two digits. A task root must have the `cn-a0-adx-juicefs-` prefix, be canonical, and not be group/world writable.

The deployment order is storage initialization/start/format, task-owned network creation, two independent client mounts, volume UUID equality check, native profile generation, runtime namespace/cgroup setup, short stable filestore binding, config validation, node/resource readiness, then SDK probes. Do not launch the SDK before both nodes register and become ready.

Read only the format UUID when configuring ADX; do not print the complete JuiceFS `.config`, which may contain object-store credentials. The two mounts must have the same format UUID, while each node keeps independent mount and cache state. Writeback is disabled for the accepted durability contract. PostgreSQL fsync and synchronous commit stay enabled.

The partial examples in `configs/` are not a complete deployment. Keep `checkpoint_dir` unset when `checkpoint_storage` is present. Keep checkpoint automatic GC disabled until the relevant reader-retirement gates are accepted in the new environment. Do not remove cgroup isolation, use unsafe filesystem aliases, or disable TLS verification to bypass an admission error.

The original profile generator defaults are historical scaffolding: explicitly stage the newly built component versions, set the accepted Firecracker local `storage_dir`, and keep the same short gVisor filestore path inside both task mount namespaces. Never change `storage_dir` beneath an existing Firecracker runtime; its source rejects an identity/root mismatch rather than hiding live state.

The source delivery includes helpers and configuration contracts, not the private original environment. A full fresh-host replay, including reader-proof collection and the complete public SDK matrix, is not established merely by re-running pure unit tests. Record that separately before treating a newly generated deployment as accepted.
