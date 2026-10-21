# Accepted scope and exclusions

The historical accepted experiment used two isolated logical nodes on one BareMetal host, separate JuiceFS clients, ADX control-plane/SDK integration, gVisor and Firecracker.

Accepted historical scopes include the basic shared-volume RW/RO public chain, private checkpoint/clone restoration for both runtimes, real RAM/open-FD restoration checks, persisted execution-bound reader/attachment reservations and retirement checks, plus the registered six-pair recovery comparison.

These are different from new delivery gates. Newly compiled source commits, clean-host deployment, runtime bundle promotion and a newly portable SDK/retirement launcher need their own evidence; historical binary hashes do not prove that an arbitrary rebuild or deployment works.

Excluded source candidates: Coordinator shutdown/stream-cancellation preparation not yet built or tested; unrelated AFS changes; other developers' local modifications. Their original workspaces are preserved.

Remaining product/performance work includes full public failover/reload combined acceptance, additional active-reader crash cases where not already accepted, physical cross-host measurements, cold-S3 per-operation read attribution, production HA, P95/P99 and dynamic runtime/function attribution for gVisor variance.

Do not claim that this route already exceeds E2B, AgentEnv or CubeSandbox. The paired numbers are for our own two sandboxd versions, not an equivalent workload comparison against those products.

