# CrossNode source delivery versions

Date: 2026-10-21. This ledger is the source of truth for this sanitized GitHub delivery. Source commits, historic measured binaries and newly rebuilt binaries are different identities.

## Obtainable source

| Component | GitHub repository and commit | Delivery branch | Exact commit |
|---|---|---|---|
| agent-dx | [hky1999/agent-dx](https://github.com/hky1999/agent-dx/commit/d66150a0d37c1413f22499e81d95a88e297ead7a) | `crossnode/accepted-20261021` | `d66150a0d37c1413f22499e81d95a88e297ead7a` |
| AKernel | [hky1999/AKernel](https://github.com/hky1999/AKernel/commit/2163fc77390c1ddc2aa66ac6a9d6f0d7a9bd1459) | `crossnode/accepted-20261021` | `2163fc77390c1ddc2aa66ac6a9d6f0d7a9bd1459` |
| sandboxd | [hky1999/sandboxd](https://github.com/hky1999/sandboxd/commit/3da34daf860de80a0adea64a457646cd208d4aa4) | `crossnode/accepted-20261021` | `3da34daf860de80a0adea64a457646cd208d4aa4` |
| gvisor-akernel-dev | [hky1999/gvisor](https://github.com/hky1999/gvisor/commit/93425aec2c93d07a38e021916dda8967743c46b0) | `crossnode/accepted-20261021` | `93425aec2c93d07a38e021916dda8967743c46b0` |
| firecracker | [hky1999/firecracker](https://github.com/hky1999/firecracker/commit/b9a362d1070ee17991e7388d3b53a9ccce25ecca) | `crossnode/runtime-baseline-20261021` | `b9a362d1070ee17991e7388d3b53a9ccce25ecca` |

The parent Git links, not the branch tips, fix the reproducible combination. AKernel also fixes its nested ADX/sandboxd Git links to these commits. No upstream default branch was changed.

## Runtime and SDK provenance

- Serial digest comparison source: sandboxd `fc5eda63350f5bd106104176011370a14611d951` on `crossnode/serial-baseline-20261021`.
- Parallel digest source: sandboxd `3da34daf860de80a0adea64a457646cd208d4aa4`; complete SHA-256 verification with at most two concurrent component checks.
- Historic measured sandboxd ELF A: `9e555c43f0e2d8b33ead0ad8abd5cf5695cfb0c2145296e003f825f42a8f17ea`.
- Historic measured sandboxd ELF B: `4806b036d23470c966265bce97986d36256cb223e0ab3792b35ac0173d1399af`.
- New remote sandboxd ELF: `6b2f5aca7e5ea42acdd10e798d7ffa999e791fcb807b543fa420a02d584d1f04`. Built but not run, deployed or rebenchmarked.
- New remote runsc ELF: `a4c84b051a402ba07c169c71ac9784bfd2f54662d3c3271a5230d82fae9c8982`; matches historical accepted runsc bytes. Built, not deployed this round.
- Firecracker existing release: `v1.16.1-akernel.3`, source `b9a362d1070ee17991e7388d3b53a9ccce25ecca`. No new VMM source change/build this round.
- SDK source package versions remain public `0.1.6rc9` and native `0.1.0rc1`; install from pinned source, not arbitrary PyPI releases. No SDK package release performed.
- Formal sandboxd runtime bundle pins are not promoted by these experimental source commits. Matching guest agent/initrd and template compatibility digests must be regenerated for a new deployment.

## Toolchain and storage

- sandboxd: Go 1.27.2; gVisor: Go 1.26.3 and Bazel 8.3.1; ADX: Rust/Cargo 1.95.0; SDK gates: Python 3.14.4.
- JuiceFS: `1.4.1+2026-07-30.0b90c7d`, writeback disabled. PostgreSQL metadata plus Ceph RGW S3 data, not the SeaweedFS arrangement in an earlier architecture illustration.
- Container image digests and JuiceFS binary digest: `delivery/manifest.json`. The two observed RepoDigests are recorded without guessing architecture/index roles.

## Acceptance and remaining work

All builds/tests were remote and task-isolated. ADX scoped tests, both SDKs, helper tests, sandboxd full default suite and selected race tests, and gVisor targeted tests/build passed. Five sandboxd privileged tests were skipped by default and one ADX test ignored. Strict whole-workspace all-features clippy is blocked by optional AFS RDMA headers (`infiniband/verbs.h`), not green.

Historic six-pair performance: Firecracker SDK-create-to-first-ready median 4.187 s to 2.349 s, paired geometric new/old ratio 0.5600. gVisor median 3.199 s to 3.141 s but confidence interval crosses both benefit and regression, so improvement is unproven. One physical host/two logical nodes; not guest pause or cold-S3 latency.

Clean-host replay of the complete public SDK and reader-retirement fault matrix remains open. Published probes and helpers do not themselves close that gate. See `Docs/plans/20261021T-source-delivery-followups.md`.

## Changelog

### 2026-10-21

Published accepted ADX, SDK, sandboxd and gVisor source on separate GitHub delivery branches; registered the matching existing Firecracker release source; added sanitized configurations, deployment helpers, diagnostic acceptance scripts, gate summaries and six-pair raw durations. Excluded unaccepted source candidates and preserved original dirty workspaces. This clean GitHub parent history intentionally omits the internal parent history and private evidence. No production deployment or shared service change.

