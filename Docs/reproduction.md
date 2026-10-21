# Reproducing the accepted source delivery

## 1. Safety and prerequisites

Use a dedicated Linux x86_64 test host or your own isolated test environment. Builds and tests must not run on the local development workstation. Do not stop or modify somebody else's sandboxd, Redis, JuiceFS, containers, mounts or network rules.

The runtime experiment needs KVM, FUSE, cgroup v2, mount/network namespaces and a reflink-capable XFS filesystem. Filestore and templates must meet the selected runtime's filesystem constraints. Use short, stable mount paths: Linux Unix-domain socket names have a 108-byte upper bound. The same guest-visible filestore path must be available in both node mount namespaces.

Use fresh task state and credentials. Do not copy the original experiment's private configuration or an old checkpoint made with different kernel/initrd/VMM compatibility pins.

## 2. Source and component gates

Exact commands and test environment requirements are recorded in `Docs/reproduction-adx-sdk.md` and `Docs/reproduction-runtime.md`. These appendices distinguish direct repository tests from generated harnesses and private fixture prerequisites.

Clone recursively and keep the commits in `delivery/manifest.json`. On the remote test host:

```bash
cd sandboxd
GOMAXPROCS=2 make check-fmt
GOMAXPROCS=2 make vet
GOMAXPROCS=2 make test
cd ../agent-dx
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features -- -D warnings
```

Some optional ADX all-features dependencies require system libraries. A missing library or a failing unrelated baseline is a failed/unavailable gate, not permission to modify shared services or a reason to silently report green.

Build ADX using its native Makefile/package workflow. The historic component builds used the pinned Rust toolchain and `cargo build --locked --release -p adx-coordinator --bin adx-coordinator` (and the corresponding API Server/adxlet targets). Build sandboxd and its matching static Firecracker guest agent using the sandboxd Makefile. The guest initrd must match sandboxd; changing its bytes invalidates old templates. Do not use a dynamic guest agent.

Build gVisor from the pinned source using its Bazel version and adjacent helper packaging rules; do not combine an arbitrary runsc executable and helpers from another release. The published runtime bundle pins in `sandboxd/third_party/runtime-versions.env` remain distinct from these experimental source commits.

## 3. Install the matching SDK sources

Use a new virtual environment on the remote host:

```bash
python3 -m venv out/client
out/client/bin/pip install -e ./agent-dx/platform/sdk/environment/python
out/client/bin/pip install -e ./AKernel/sdk/python
```

The accepted experiment used source extensions. Installing only the published `akernel-sdk` / `adx-environment` packages can omit those extensions.

## 4. JuiceFS deployment helpers

The reusable, secret-generating lab helpers and their tests are in:

`AKernel/deploy/experimental/juicefs-adx/`

They include `lab.py`, `node_network.py`, `runtime_nodes.py`, `private_pki.py`, `native_profile.py`, `short_profile.py`, runtime downloads and initrd construction. Read their `--help` before creating a new task. Their state directories are private; generated environment files, passwords, certificates and actual deployment YAML are not repository contents.

The lab has fixed reserved addresses and ports and refuses conflicts. Do not alter an existing environment to make it fit. Run it on an unused dedicated host or an independently isolated outer namespace. PostgreSQL uses fsync and synchronous commit. JuiceFS must use the same volume UUID in both node clients and must not enable writeback for this acceptance.

`configs/adx-shared-storage.example.json` is a partial storage example, not a complete launch configuration. Merge it through the ADX deployment tools and validate the generated `.yaml` with `adxctl` before launch. Do not keep the legacy `checkpoint_dir` alongside `checkpoint_storage`. Do not disable cgroups or certificate verification to get a demo running.

The original A0 generators are retained as tested source material, not a promise that their old default runtime binaries already include the new commits. Stage the newly built source versions, regenerate the package/profile and guest compatibility pins, and run the gates before accepting that profile.

## 5. Diagnostic checkpoint/restore probe

`tools/acceptance/shared_fs_probe.py` and `probe_cleanup.py` are reused from the accepted A0 diagnostic chain. They exercise real native ADX SDK pause/resume/snapshot/clone, verify actual source/target node placement and private filesystem branch isolation, and record owned cleanup.

```bash
out/client/bin/python tools/acceptance/shared_fs_probe.py \
  --endpoint https://YOUR-TEST-ENDPOINT \
  --token-file /YOUR-PRIVATE-DIR/token \
  --ca /YOUR-PRIVATE-DIR/ca.pem \
  --runtime runsc \
  --source-node YOUR-SOURCE-NODE --target-node YOUR-TARGET-NODE \
  --shared-root /YOUR-SHARED-MOUNT/checkpoints \
  --output /YOUR-TASK-DIR/results/runsc-01
```

Repeat in a fresh output directory with `--runtime firecracker`. Use runtime-compatible rootfs/bootstrap profiles. This native diagnostic probe is not by itself the complete public AKernel SDK acceptance and does not establish restart/fault safety.

## 6. Public SDK and reader-protection acceptance

The accepted full chain creates through the public `Sandbox` facade; internal checkpoint coordination and clone use the existing native Environment interface. It does not add a public checkpoint catalog API.

Required evidence includes: actual node assignment, restored volatile memory and an open file descriptor, immutable parent/private clone isolation, RW writer / independent-tenant RO reader behavior, explicit EROFS refusal, durable reader reservation before runtime start, and positive retirement proof before collection. A process exit code or successful SDK delete alone is insufficient.

Historical accepted scope and omissions are recorded in `Docs/acceptance-scope.md`. The raw host-bound orchestration scripts and private journals are deliberately not advertised as a portable one-command launcher. A clean-host replay of the complete SDK + retirement matrix is a separate delivery gate and must not be inferred from component tests.

## 7. Recompute published performance points

```bash
python3 tools/performance/recompute.py evidence/performance-six-pairs.json
```

This verifies all paired point estimates from the published samples. Registered confidence intervals are included as accepted results; this minimal helper does not claim to recompute their bootstrap stream. No live infrastructure or credentials are needed. New runtime samples require the original metric definition and the same registered alternating-version design.

## 8. Cleanup

Use normal APIs for resources created by your task and verify execution-bound retirement. Keep dependencies when an operation has an unknown outcome. Never use global process-name kills, global GC, forced unmounts of shared mounts, or delete-by-age as a substitute for ownership proof.

