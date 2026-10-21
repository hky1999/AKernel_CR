# CrossNode checkpoint/restore: accepted source delivery

This repository contains the sanitized source manifest, component Git submodules, deployment helpers, acceptance probes and paired performance data for the ADX / JuiceFS CrossNode experiment.

## Start here

```bash
git clone --recurse-submodules git@github.com:hky1999/AKernel_CR.git
cd AKernel_CR
cat VERSION.md
cat Docs/reproduction.md
```

Do not use `git submodule update --remote`: the Git links select the reviewed versions. Install both SDKs from these source checkouts, not only the currently published PyPI packages. See `Docs/reproduction.md`.

## Scope and limits

- ADX owns Environment lifecycle, checkpoint references, persisted reader reservations and shared-volume admission.
- JuiceFS provides one shared namespace through independent node mounts. Its metadata and S3 object data are separate from ADX's Redis state.
- Shared application volumes and private writable root filesystems are different contracts. Shared volume contents are not rolled back by a sandbox checkpoint.
- The Firecracker private writable disk in the accepted performance runs remains local XFS-backed ext4. Checkpoint artifacts are published into JuiceFS. This is not a production OverlayBD integration.
- The accepted performance environment has one physical host and two isolated logical nodes. It does not establish two-physical-host migration, storage high availability or production latency percentiles.
- Firecracker improved on the registered recovery metric; gVisor remains statistically uncertain. See `evidence/performance-six-pairs.json`.
- Unaccepted Coordinator shutdown changes, unrelated AFS edits, raw private configurations, tokens, process inventories and historical internal documents are excluded.

This is an experimental accepted-source delivery, not a claim that all production rollout and runtime-release promotion gates are complete. Exact newly executed gate results belong in `evidence/delivery-gates.json`; unavailable or failing gates must remain visible.

