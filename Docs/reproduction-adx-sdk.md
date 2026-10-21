# ADX / SDK 源码交付门禁命令附录

本附录记录源码交付门禁实际使用的命令，不代表已完成全新主机安装、新的 SDK/VM 端到端验收、生产部署或新性能实验。只在远端独立任务中运行，不操作共享服务，也不写入其他开发者的缓存。

## 1. 路径与前置条件

```bash
export SRC=/path/to/version-pinned-source-checkouts
# SRC 下必须已有 agent-dx、AKernel 和 AKernel_CR 源码目录。
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

实际检查的工具版本：Rust/Cargo 1.95.0、Python 3.14.4、JuiceFS `1.4.1+2026-07-30.0b90c7d`。

任务私有缓存必须已有锁定的 Cargo 依赖。本轮独立复制已有缓存并使用 `--offline --locked`；没有验收全新主机的依赖初始化。不能为省去独立复制而将旧缓存或共享缓存改为可写。

Python 解释器必须具备两套 SDK 的 `pyproject.toml` 声明的运行依赖。本轮复用独立实验环境解释器，仅向任务私有目录补充缺失的测试/解析包，没有单独验收一个全新 Python 环境。

### 控制面 RPC 测试所需的 TLS 材料

`ADX_TEST_TLS_DIR` 必须包含固定版本控制面 RPC 测试要求的身份材料。历史记录使用任务自有测试材料，不使用生产凭据。

**本轮未记录经过验证的仓库内 TLS 材料生成命令，此前置条件仍需补齐。** 此处不虚构证书文件名、身份或生成命令。应取得固定源码版本的生成器/材料契约，或生成符合该契约的独立测试材料；不发布原私有材料或真实服务私钥。

## 2. ADX 格式检查与七组件单测

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

实际顶层测试合计234通过、零失败，`adxlet` 中1项忽略。嵌套的 `execd` 子进程测试汇总没有重复计数。

## 3. 七组件严格 lint 与五组 Coordinator 集成测试

```bash
cd "$SRC/agent-dx"
cargo clippy --offline --locked \
  -p adx-agent-core -p adx-core -p adx-protocol -p adxlet \
  -p adx-coordinator -p adx-apiserver -p adx-execd \
  --all-targets --all-features -- -D warnings

# 需要上面配置的本任务 Redis 可执行文件及 TLS 测试材料。
for suite in \
  shared_volume_execution_rpc shared_volume_execution \
  shared_volumes shared_volumes_rpc snapshots
do
  cargo test --offline --locked -p adx-coordinator \
    --test "$suite" -- --include-ignored --nocapture
done
```

实际集成测试8 + 13 + 13 + 8 + 3 = 45通过，零忽略。对测试初始化器做最终等价清理后，execution-RPC 重新编译并通过8项；另一组 RPC 在补上缺失材料配置后，使用先前独立编译的测试 ELF 通过。两处测试用 `LabelSelector` 初始化器仅作等价改写以消除 `field_reassign_with_default`，未增加 lint 豁免。

### 严格全工作区 lint 仍受环境依赖阻塞

```bash
cd "$SRC/agent-dx"
cargo clippy --offline --locked --workspace \
  --all-targets --all-features -- -D warnings
```

补齐 `protoc` 后，严格命令因 `afs-transport/native/rdma.c` 缺少 `infiniband/verbs.h` 返回101。没有向共享系统安装依赖包。七组件 lint 通过不等于全工作区通过。

## 4. 开发文档检查

正常 Git 工作区执行：

```bash
cd "$SRC/agent-dx"
python3 build/docs/check.py
```

源码导出没有 Git 元数据，初次检查在 `git ls-files` 阶段停止，尚未检查正文。仅为导出目录提供以下临时文件发现环境后，检查通过：

```bash
git init --bare "$TASK/docs-metadata.git"
git --git-dir="$TASK/docs-metadata.git" config core.bare false
cd "$SRC/agent-dx"
GIT_DIR="$TASK/docs-metadata.git" GIT_WORK_TREE="$SRC/agent-dx" \
  python3 build/docs/check.py
```

该方式不在 `source/.git` 创建元数据，不创建提交或远端，也不改产品源码。此次开发文档不需要重新生成架构 HTML。

## 5. 任务私有 Python 测试依赖

本轮补充的固定依赖为 `pytest==8.4.2`、`pytest-asyncio==1.2.0`、`dockerfile-parse==2.0.1`。若已准备的解释器包含 pip：

```bash
"$PYTHON" -m pip install --disable-pip-version-check --no-cache-dir \
  --index-url https://pypi.org/simple --target "$TASK/python-deps" \
  pytest==8.4.2 pytest-asyncio==1.2.0 dockerfile-parse==2.0.1
```

实际解释器没有 pip、ensurepip 和 uv。通过 HTTPS PyPI 元数据校验 SHA-256 后，从任务私有路径加载官方 pip 25.2 wheel，再安装到同样的任务私有目录。对应初始化方式如下，路径使用公开占位符：

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

未关闭 TLS 校验，也未修改原虚拟环境或全局安装。上述两种准备方式选择一种即可。

## 6. 原生与公共 SDK 测试

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

必须保留未改动的 `AKernel/deploy/standalone`、builder 输入及根 Makefile，因为单测收集会导入部署辅助模块。不能为弥补不完整导出而排除 `test_standalone_environment.py`。

最终实际结果：原生 SDK306项、公共 SDK 完整 unit 目录305项、公共共享卷独立文件6项通过，均零跳过、零失败。独立共享卷测试位于 `tests/`，不是 `tests/unit/`。

## 7. 纯辅助脚本测试与 CLI 帮助

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

实际结果：实验部署辅助脚本56项、验收辅助脚本19项通过，零跳过；五个帮助命令均返回0。这些命令不会启动实际 SDK 探针、沙箱、JuiceFS 挂载或集群服务。

## 8. 重算已有性能样本的点估计

```bash
cd "$SRC/AKernel_CR"
"$PYTHON" tools/performance/recompute.py evidence/performance-six-pairs.json
```

根据已有六组样本核对中位数及配对几何均值新/旧耗时比。Firecracker：4.187135070秒→2.349072761秒，耗时比0.560002133；gVisor：3.199337987秒→3.140797789秒，耗时比0.957930057，但登记结论仍为不确定。脚本不重算登记的 bootstrap 区间，不新增性能实验，不证明冷 S3 性能，也不比较竞品。

## 9. 证据与剩余范围

`adx-sdk-gates-summary.json` 保留真实返回码、实际执行/忽略数量、版本及各次尝试的相对证据路径。此前的环境配置缺失、pytest/pip/解析包缺失、未改动部署输入缺失、共享卷测试路径错误，以及导出目录 Git 文件发现失败，都保留记录而未被覆盖。

本轮源码交付门禁没有完成完整运行时集成套件、全新主机集群搭建、TLS 测试材料生成流程或正式生产发布；未修改/替换共享服务与正在运行的沙箱。

