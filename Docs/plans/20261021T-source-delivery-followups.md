# Remaining source-delivery and product gates

## Priority 1: fresh isolated deployment and portable full-chain acceptance

1. Stage the exact pinned binaries and matching Firecracker guest initrd in a new task. Regenerate deployment profiles and compatibility pins; validate real node registration/resources and Unix socket path lengths.
2. Generate new JuiceFS credentials, separate node mounts of the same UUID, control-plane state and private TLS fixtures. Preserve writeback=false, synchronization barriers and isolation.
3. Port the host-bound historical full SDK orchestration into a parameterized runner. Retain true node assignment, RAM/open-FD checks, private clone isolation, independent-tenant RW/RO shared-volume checks and execution-bound cleanup proofs.
4. Replay process restart, unknown timeout outcomes, reader retirement and collection races. A native SDK smoke test or returned delete code is insufficient. Do not enable automatic collection while these gates remain open.
5. Repeat formal A/B performance using the newly staged ELF identities before attributing historical numbers to a new rebuild.

## Priority 2: performance attribution

Investigate gVisor CPU/read I/O by actual process role using task-scoped identities. Preserve the registered six-pair results unchanged. Measure checkpoint guest pause separately from recovery-to-ready. Then measure genuine two-compute-host transfer and cold-S3 bytes, not only warm cache wall time.

## Priority 3: production release

Close public failover/reload combined acceptance; establish storage HA, durability under failures, tenant authorization, operational recovery and P95/P99. Promote runtime bundles and package versions only after those gates. Optional AFS full-workspace lint requires a dedicated environment with RDMA development headers; current focused lint is not that gate.

No timeline or competitor superiority is asserted by this source publication.

