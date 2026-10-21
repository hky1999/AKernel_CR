# ADX / SDK source-delivery gate command appendix

This appendix records the commands used for source-delivery checks. It does
not claim fresh-host installation, new SDK/VM end-to-end acceptance, production
deployment, or a new performance experiment. Run only in an independent remote
task, never against shared services or another developer's writable caches.

## 1. Paths and prerequisites

```bash
export SRC=/path/to/version-pinned-source-checkouts
# SRC/agent-dx, SRC/AKernel and SRC/AKernel_CR must exist.
export TASK=/path/to/new-independent-task
mkdir -p "$TASK/home" "$TASK/tmp" "$TASK/cargo-home" \
  "$TASK/cargo-target" "$TASK/python-deps" "$TASK/logs"
export HOME="$TASK/home" TMPDIR="$TASK/tmp"
export CARGO_HOME="$TASK/cargo-home"
export CARGO_TARGET_DIR="$TASK/cargo-target"
export CARGO_BUILD_JOBS=2 GOMAXPROCS=2 JOBS=2
export CARGO_NET_OFFLINE=true CARGO_TERM_COLOR=never
export PATH="$TASK/tools/rust-1.95.0/bin:$PATH"
export PYTHON="$TASK/python/bin/python"
export PROTOC="$TASK/tools/protoc"
export ADX_TEST_REDIS_SERVER="$TASK/tools/redis-server"
export ADX_TEST_TLS_DIR="$TASK/fixtures/control-rpc-tls"
```

Actual checked tools: Rust/Cargo 1.95.0, Python 3.14.4,
JuiceFS `1.4.1+2026-07-30.0b90c7d`.

The task must already have the locked Cargo dependencies in its own cache.
This round copied an existing cache and used `--offline --locked`; fresh-host
dependency bootstrapping was not validated. Do not make an old/shared cache
writable to avoid preparing a task-local copy.

The prepared Python interpreter must provide the runtime dependencies declared
by both SDKs' `pyproject.toml` files. This round reused the independent lab's
interpreter and added missing test/parser packages only into private targets.
A new clean Python environment was not independently accepted here.

### Required control-RPC TLS fixture

`ADX_TEST_TLS_DIR` must contain the control-RPC test identities expected by the
pinned tests. The recorded run reused a task-owned fixture, not production
credentials.

**No verified repository command for generating this fixture was recorded in
this round. Fixture generation remains a prerequisite to configure.** No
certificate filenames, identities, or generation command are invented here.
Obtain the generator and fixture contract for the pinned source version or
provide a new isolated fixture satisfying that contract. Never publish the
original private fixture or real service private keys.

## 2. ADX formatting and seven component unit suites

```bash
cd "$SRC/agent-dx"
cargo fmt --all -- --check
for package in \
  adx-agent-core adx-apiserver adx-core adx-protocol \
  adx-execd adxlet adx-coordinator
do
  cargo test --offline --locked -p "$package" --lib
done
```

Observed top-level totals: 234 passed, zero failed, one ignored in `adxlet`.
An additional nested `execd` subprocess summary was not counted twice.

## 3. Focused lint and five Coordinator integration suites

```bash
cd "$SRC/agent-dx"
cargo clippy --offline --locked \
  -p adx-agent-core -p adx-core -p adx-protocol -p adxlet \
  -p adx-coordinator -p adx-apiserver -p adx-execd \
  --all-targets --all-features -- -D warnings

# Requires the task-owned Redis executable and TLS fixture configured above.
for suite in \
  shared_volume_execution_rpc shared_volume_execution \
  shared_volumes shared_volumes_rpc snapshots
do
  cargo test --offline --locked -p adx-coordinator \
    --test "$suite" -- --include-ignored --nocapture
done
```

Observed integration counts: 8 + 13 + 13 + 8 + 3 = 45 passed, zero ignored.
After final equivalent test-initializer cleanup, the execution-RPC suite was
recompiled and passed all eight cases. The other RPC suite passed using its
already-compiled isolated test ELF after supplying its missing fixture setting.
Two test-only `LabelSelector` initializers were equivalently rewritten to fix
`field_reassign_with_default`; no lint suppression was added.

### Strict full-workspace lint remains blocked

```bash
cd "$SRC/agent-dx"
cargo clippy --offline --locked --workspace \
  --all-targets --all-features -- -D warnings
```

The strict command returned 101 after `protoc` was supplied because
`afs-transport/native/rdma.c` lacked `infiniband/verbs.h`. No shared system
packages were installed. The focused lint pass does not replace or imply a
successful full-workspace pass.

## 4. Development-documentation check

For a normal Git checkout:

```bash
cd "$SRC/agent-dx"
python3 build/docs/check.py
```

The export had no Git metadata; its first check stopped at `git ls-files`
before checking content. This export-only file-discovery setup then passed:

```bash
git init --bare "$TASK/docs-metadata.git"
git --git-dir="$TASK/docs-metadata.git" config core.bare false
cd "$SRC/agent-dx"
GIT_DIR="$TASK/docs-metadata.git" GIT_WORK_TREE="$SRC/agent-dx" \
  python3 build/docs/check.py
```

This creates no `source/.git`, commit, remote, or product source change.
Development documentation did not require architecture HTML regeneration.

## 5. Task-private Python test dependencies

Tested additions: `pytest==8.4.2`, `pytest-asyncio==1.2.0`, and
`dockerfile-parse==2.0.1`. If the prepared interpreter already has pip:

```bash
"$PYTHON" -m pip install --disable-pip-version-check --no-cache-dir \
  --index-url https://pypi.org/simple --target "$TASK/python-deps" \
  pytest==8.4.2 pytest-asyncio==1.2.0 dockerfile-parse==2.0.1
```

The actual interpreter lacked pip, ensurepip, and uv. It loaded the official
pip 25.2 wheel from a task-local path after SHA256 verification against HTTPS
PyPI metadata, then ran the same private-target installation. That bootstrap,
with public placeholders:

```bash
export PIP_WHEEL="$("$PYTHON" - <<'PY'
import hashlib, json, os, pathlib, urllib.request
task = pathlib.Path(os.environ['TASK'])
with urllib.request.urlopen('https://pypi.org/pypi/pip/25.2/json', timeout=30) as response:
    metadata = json.load(response)
wheel, = [item for item in metadata['urls'] if item['filename'].endswith('-py3-none-any.whl')]
with urllib.request.urlopen(wheel['url'], timeout=30) as response:
    data = response.read()
assert hashlib.sha256(data).hexdigest() == wheel['digests']['sha256']
path = task / wheel['filename']
path.write_bytes(data)
print(path)
PY
)"
PYTHONPATH="$PIP_WHEEL" PIP_CONFIG_FILE=/dev/null \
  "$PYTHON" -m pip install --disable-pip-version-check --no-cache-dir \
  --index-url https://pypi.org/simple --target "$TASK/python-deps" \
  pytest==8.4.2 pytest-asyncio==1.2.0 dockerfile-parse==2.0.1
```

No TLS verification was disabled. No old virtual environment or global package
installation was changed. Choose one preparation route, not both.

## 6. Native and public SDK tests

```bash
export PYTHONPATH="$TASK/python-deps:$SRC/agent-dx/platform/sdk/environment/python:$SRC/AKernel/sdk/python"
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

"$PYTHON" -m pytest -q -rs -p no:cacheprovider -p pytest_asyncio.plugin \
  --junitxml="$TASK/logs/native-sdk.junit.xml" \
  "$SRC/agent-dx/platform/sdk/environment/python/tests"

"$PYTHON" -m pytest -q -rs -p no:cacheprovider -p pytest_asyncio.plugin \
  --junitxml="$TASK/logs/public-sdk.junit.xml" \
  "$SRC/AKernel/sdk/python/tests/unit"

"$PYTHON" -m pytest -q -rs -p no:cacheprovider -p pytest_asyncio.plugin \
  --junitxml="$TASK/logs/public-shared-volumes.junit.xml" \
  "$SRC/AKernel/sdk/python/tests/test_shared_volumes.py"
```

The unchanged `AKernel/deploy/standalone`, builder inputs, and root Makefile
must be present: unit collection imports deployment helpers. Do not exclude
`test_standalone_environment.py` to compensate for a partial source export.

Observed final counts: native 306, complete public-unit directory 305, and
standalone public shared-volume file 6 passed; all had zero skipped or failed.
The separate shared-volume test is under `tests/`, not `tests/unit/`.

## 7. Pure helper checks and CLI help

```bash
"$PYTHON" -m unittest discover \
  -s "$SRC/AKernel/deploy/experimental/juicefs-adx" -p 'test_*.py'

for helper in lab.py native_profile.py runtime_nodes.py node_network.py short_profile.py
do
  "$PYTHON" "$SRC/AKernel/deploy/experimental/juicefs-adx/$helper" --help
done

cd "$SRC/AKernel_CR"
"$PYTHON" -m unittest discover -s tools/acceptance -p 'test_*.py'
```

Observed: lab helpers 56 passed, acceptance helpers 19 passed, zero skipped;
all five help commands returned zero. These commands do not launch the actual
SDK probe, a sandbox, a JuiceFS mount, or cluster services.

## 8. Recompute existing performance point estimates

```bash
cd "$SRC/AKernel_CR"
"$PYTHON" tools/performance/recompute.py evidence/performance-six-pairs.json
```

This checks medians and paired geometric new/old ratios from the existing six
pairs. Firecracker: 4.187135070 s to 2.349072761 s, ratio 0.560002133.
gVisor: 3.199337987 s to 3.140797789 s, ratio 0.957930057; its registered result
remains uncertain. The script does not recompute registered bootstrap
intervals, execute a new benchmark, establish cold-S3 performance, or compare
competitors.

## 9. Evidence and remaining scope

`adx-sdk-gates-summary.json` records actual return codes, nonzero counts,
ignored counts, versions, and relative per-attempt evidence paths. Earlier
missing environment settings, pytest/pip/parser packages, unchanged deployment
inputs, wrong shared-volume selector, and export-only Git discovery failures
were retained rather than overwritten.

The full runtime integration suite, clean-host cluster setup, TLS-fixture
generation procedure, and production promotion were not completed by this
source-delivery gate round. Shared services and live sandboxes were not
modified or replaced.

