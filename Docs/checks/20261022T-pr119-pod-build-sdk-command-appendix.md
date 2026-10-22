# PR #119 镜像与 SDK 准备：可复现命令附录

## 1. 口径与固定版本

本附录仅使用本轮已完成 runner 与 receipt 整理，没有再次构建、测试或启动服务。以下命令均应在远端独占任务目录执行，不是在开发者本地编译。

- AKernel PR #119 本轮 API 实际 head：6ea004125eb4365ba06ba3c7b21c4fd80e4cdaac。不是此前的 1096294 或 bee5b368。
- sandboxd 官方子模块：d5acc3b5b673074e20fd8b7733d4035dbaeae1b0。
- ADX 源码 gitlink / 发布包：59fa7912f875832c8ab053148ae8fd17b7c25a23，daily 前缀 20261021064540-59fa7912f875/linux/amd64。
- 公共 SDK：akernel-sdk 0.2.0rc3；原生依赖：adx-environment 0.1.0rc2。
- gVisor 完整发布包：release-20260817.0-akernel.4；其中 runsc 嵌入版本为 release-20260817.0-akernel.3-2-g7fdef444b108。
- Firecracker 发布包：v1.16.1-akernel.3，VMM 嵌入版本为 v1.16.1。
- AKernel 镜像使用 distill-fs v0.1.3；不要误用 sandboxd 自身测试 manifest 中的 v0.1.2。

固定源码、发布包和校验和不表示位级可重复构建：官方 Dockerfile 仍使用基础镜像标签和 APT 索引，EROFS、镜像与 wheel 也可能带构建时信息。本轮已记录实际基础镜像 digest、最终 OCI 和 wheel 摘要；新构建输出不应机械要求与本轮输出字节相同。

## 2. 固定源码和子模块

下面是面向全新目录的等价 Git 获取方式。本轮实际先读取 GitHub PR API、下载固定 SHA 的 codeload 安全归档，再补入相同提交的 Git 对象、HEAD 与 index，以便官方 helper 获取版本。两种方式均固定同一源码图，不使用本地脏源码。

```bash
set -euo pipefail
export TASK=/absolute/path/to/a/new-private-task
export SRC="$TASK/source/AKernel"
export BUILD="$TASK/image-build"
export SDK="$TASK/sdk"
mkdir -p "$TASK/source" "$BUILD" "$SDK"

git init "$SRC"
git -C "$SRC" remote add origin https://github.com/WenYuLuo/akernel.git
git -C "$SRC" -c credential.helper= fetch --depth=1 origin \
  6ea004125eb4365ba06ba3c7b21c4fd80e4cdaac
git -C "$SRC" checkout --detach FETCH_HEAD
git -C "$SRC" -c credential.helper= submodule update --init --depth=1 src/sandboxd

test "$(git -C "$SRC" rev-parse HEAD)" = \
  6ea004125eb4365ba06ba3c7b21c4fd80e4cdaac
test "$(git -C "$SRC/src/sandboxd" rev-parse HEAD)" = \
  d5acc3b5b673074e20fd8b7733d4035dbaeae1b0
git -C "$SRC" status --porcelain --untracked-files=normal
git -C "$SRC" ls-tree HEAD src/agent-dx
```

本轮固定源码归档 URL 为 https://codeload.github.com/WenYuLuo/akernel/tar.gz/6ea004125eb4365ba06ba3c7b21c4fd80e4cdaac，SHA256 为 af6d623d89689154a0b5fbe99a107eb56fc29a888dd33cbeddd3ef5421f56ad6。实际下载和安全提取证据在 source/pr119-api.json 与 receipts/source.json。

本轮只初始化实际编译输入 sandboxd；ADX 平台及 Execd 使用官方固定发布包，不在本轮重新编译 Rust 控制面。

## 3. 官方镜像构建命令与 Podman 边界

实际入口为 deploy/scripts/build-image.sh，先构建 builder/runtime.Dockerfile 的 runtime-execd 目标，再构建 builder/node.Dockerfile。一个 all-in-one 镜像供后续 control / node 两种角色使用。本轮明确包含 runsc 与 Firecracker，不包含 Kata 或 runc。

宿主没有 Docker CLI，本轮使用 Podman 5.7.0 / Buildah 1.42.1 执行官方两次 docker build。任务私有 CLI shim 只接受 build，不实现 docker run、compose、push 或 Docker API。DOCKER_BUILDKIT=1 仅满足官方 helper 的入口检查，实际构建引擎不是 Docker BuildKit，不能写成“原生 Docker BuildKit 验收通过”。

实际私有 Podman 前缀：

```bash
/usr/bin/podman \
  --root "$BUILD/graph" \
  --runroot "$BUILD/runroot" \
  --tmpdir "$BUILD/libpod-tmp" \
  --storage-driver overlay \
  --cgroup-manager cgroupfs \
  --events-backend file
```

shim 对每次官方 docker build 增加以下参数，其余官方参数原样转交：

```text
build
--jobs 2
--cpu-period 100000
--cpu-quota 200000
--cpuset-cpus <当前允许 CPU 集合的前四个，本轮为 0,1,2,3>
--layers
--pull=missing
--http-proxy=false
--tls-verify=true
```

两个并行阶段各限制 2 CPU，并共用四个 CPU 的允许集合。外层 GOMAXPROCS=2 / JOBS=2 并非 Dockerfile build-arg，不应据此宣称容器内所有编译器都读取了这两个环境变量；实际资源限制来自上述 Podman 参数。

私有配置与必要环境：

```bash
mkdir -p "$BUILD/bin" "$BUILD/home" "$BUILD/tmp" "$BUILD/xdg" \
  "$BUILD/graph" "$BUILD/runroot" "$BUILD/libpod-tmp" "$BUILD/artifacts"
printf 'unqualified-search-registries = ["docker.io"]\nshort-name-mode = "disabled"\n' \
  > "$BUILD/registries.conf"
printf '{"auths":{}}\n' > "$BUILD/auth.json"
chmod 600 "$BUILD/auth.json"

export HOME="$BUILD/home"
export TMPDIR="$BUILD/tmp"
export XDG_RUNTIME_DIR="$BUILD/xdg"
export REGISTRY_AUTH_FILE="$BUILD/auth.json"
export CONTAINERS_REGISTRIES_CONF="$BUILD/registries.conf"
export PATH="$BUILD/bin:/usr/local/bin:/usr/bin:/bin"
export DOCKER_BUILDKIT=1
export AKERNEL_TARGETARCH=amd64
export AKERNEL_ENABLE_KATA=false
export AKERNEL_ENABLE_RUNC=false
export AKERNEL_ENABLE_FIRECRACKER=true
export AKERNEL_BUILD_MIRROR=official
export AKERNEL_BUILD_NETWORK=host
export AKERNEL_BUILD_PROXY=false
export PIP_INDEX_URL=https://pypi.org/simple
export GOMAXPROCS=2
export JOBS=2
unset HTTP_PROXY HTTPS_PROXY NO_PROXY ALL_PROXY
unset http_proxy https_proxy no_proxy all_proxy
unset ADX_RELEASE_URL ADX_RELEASE_SHA256 ADX_EXECD_URL ADX_EXECD_SHA256
unset OTELCOL_CONTRIB_URL OTELCOL_CONTRIB_SHA256
unset AKERNEL_APT_UBUNTU_MIRROR AKERNEL_APT_UBUNTU_PORTS_MIRROR
unset AKERNEL_APT_DEBIAN_MIRROR AKERNEL_APT_DEBIAN_SECURITY_MIRROR GOPROXY

cd "$SRC"
bash deploy/scripts/build-image.sh \
  --repository localhost/akernel-pr119 \
  --tag 6ea004125eb4-runsc-firecracker \
  --runtime-image localhost/akernel-runtime-pr119:6ea004125eb4
```

上述命令要求先安装任务专属的 docker shim 到 $BUILD/bin/docker。本轮实际 shim 文件为 image-build/bin/docker；其中只写入本任务 graph/runroot/tmp，拒绝非 build 动作。其绝对任务路径须参数化后再作为通用脚本发布。不能简单 alias docker=podman 后漏掉私有存储、CPU、代理与 TLS 边界。

长构建由 image-build/build-official-images.py 持久监督，实际执行官方脚本的 argv 与上面相同。断开 SSH 后不要再次启动构建：应读取原任务 PID、image-build/build-calls/*-terminal.json 与 receipts/images.json 判断状态。本轮 runtime 约 35.17 秒、node 约 336.42 秒，两个 build 返回码均为 0。这是本次镜像打包耗时，不是 checkpoint/reload 性能。

AKERNEL_BUILD_NETWORK=host 只用于镜像构建中的下载；不等于创建了运行时网络或修改了宿主模块/防火墙。本轮没有修改宿主 package manager、容器全局 graph 或共享服务。

## 4. 镜像载荷检查与 OCI 导出

本轮执行一个 --network none、--read-only、覆盖 entrypoint 为 Python 的临时检查容器；没有运行镜像的 systemd / ADX 服务入口。

```bash
# 将 podman-task 实现为上节相同的私有 Podman 前缀。
podman-task run --rm --network none --read-only \
  --entrypoint /usr/bin/python3 \
  --volume "$BUILD/payload-check.py:/tmp/payload-check.py:ro" \
  localhost/akernel-pr119:6ea004125eb4-runsc-firecracker \
  /tmp/payload-check.py

podman-task image inspect \
  localhost/akernel-pr119:6ea004125eb4-runsc-firecracker \
  localhost/akernel-runtime-pr119:6ea004125eb4

podman-task save --format oci-archive \
  --output "$BUILD/artifacts/akernel-pr119-6ea004125eb4-runsc-firecracker.oci.tar" \
  localhost/akernel-pr119:6ea004125eb4-runsc-firecracker
```

payload-check.py 的已知检查范围为：完整 runsc / containerd shim / 四个 gvisor-bin helpers、sandboxd、Firecracker、virtiofsd、distill-fs、ADX 服务与 Execd 的 ELF64/amd64 和可执行属性；EROFS magic；initrd 内 /init 存在且无动态加载器；Kata/runc 未混入；文件摘要。还执行 runsc --version 与 firecracker --version，这些只是版本命令，不会启动沙箱或 VM。

runtime EROFS 由官方 runtime.Dockerfile 从固定 Execd 构建，不是直接使用 ADX 发布包自带的另一份 runtime rootfs。

本轮结果：

- all-in-one 未压缩镜像：1,541,952,224 字节。
- runtime 镜像：102,403,392 字节。
- OCI archive：653,413,376 字节，SHA256 105c7c345407c853fe95f8d60f08540611276c405f5ac80a13bfa30644b76d87。
- OCI archive 内 manifest：sha256:2fe4ad3de728f7fdeb2be1fef1e036dfa236fe7df000f12e2cf67699471bce72。
- 构建存储中的原 manifest：sha256:c492365a04c1b26e2271e2753c3683c8aaca0092cb0bb6ffcae7c55f74228905。OCI 导出发生格式转换，不能与导出 manifest 混写。
- 构建目录只读 du 快照约 7.11 GiB，整个任务约 7.17 GiB；未采样真实构建峰值。低水位守卫启动时构建已完成，0 次检查 / 0 次信号，不能作为本轮导出受到其保护的证据。

这些 tag 只存在本任务私有存储和 OCI 中；没有推送公共 latest 或任何公共镜像标签。

## 5. 公共 SDK 与匹配原生 wheel 的安装

本轮原生 wheel 从上轮已完整校验的相同 ADX release 只读复制，并再次核对 SHA；未复用旧运行数据或模板。下面给出外部无该缓存时等价获取路径。完整发布包：

```bash
export ADX_BASE=https://agent-dx.obs.cn-southwest-2.myhuaweicloud.com/adx/daily/20261021064540-59fa7912f875/linux/amd64
mkdir -p "$SDK/bootstrap" "$SDK/wheelhouse" "$SDK/build-input" "$SDK/cache" "$SDK/logs"
curl -fSL "$ADX_BASE/adx-release.tar.gz" -o "$SDK/adx-release.tar.gz"
printf '%s  %s\n' \
  d2dcb7d6c18077a798e8c86b1caadd974b245fe9a32d901839c018448b64bb9f \
  "$SDK/adx-release.tar.gz" | sha256sum -c -
```

解包前校验归档摘要，使用拒绝绝对路径、..、特殊设备和逃逸链接的安全提取。本轮使用 Python tarfile 的 data filter，未直接对未校验下载运行 tar。原生 wheel 的精确位置为发布包内 sdk/adx_environment-0.1.0rc2-py3-none-any.whl，其 SHA256 为 c2e7a54dc13af1529d9699ad964d6ca178cd730a12db344789f9e2f7ca18a575。

全新私有 venv 与原样安装 argv：

```bash
/usr/bin/python3 -m venv --without-pip "$SDK/client"
export PY="$SDK/client/bin/python"
export PIP_CONFIG_FILE=/dev/null
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_CACHE_DIR="$SDK/cache"
export PIP_INDEX_URL=https://pypi.org/simple
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
unset PIP_EXTRA_INDEX_URL PIP_FIND_LINKS PYTHONPATH
```

由于系统 Python 的 venv 不带 pip，本轮从 https://pypi.org/pypi/pip/25.2/json 定位官方 pip-25.2-py3-none-any.whl，核验 PyPI 元数据的 SHA256 后保存到 $SDK/bootstrap。其实际 SHA256 为 6d67a2b4e7f14d8b31b8b52648866fa717f45a1eb70e83002f4331d07e953717。未全局安装 pip。

```bash
PYTHONPATH="$SDK/bootstrap/pip-25.2-py3-none-any.whl" \
  "$PY" -m pip install --no-index --no-deps \
  "$SDK/bootstrap/pip-25.2-py3-none-any.whl"

"$PY" -m pip install setuptools==80.9.0 wheel==0.45.1

# 以下 wheel 必须先从已校验的固定 ADX bundle 放到 wheelhouse。
"$PY" -m pip install \
  "$SDK/wheelhouse/adx_environment-0.1.0rc2-py3-none-any.whl"

# 复制固定 PR SDK 源码到任务私有构建输入，不在固定源树写 egg-info/build。
cp -a "$SRC/sdk/python" "$SDK/build-input/akernel-sdk"
"$PY" -m pip wheel --no-build-isolation --no-deps \
  --wheel-dir "$SDK/wheelhouse" "$SDK/build-input/akernel-sdk"
"$PY" -m pip install \
  "$SDK/wheelhouse/akernel_sdk-0.2.0rc3-py3-none-any.whl"

"$PY" -m pip check
"$PY" -m pip list --format=json
"$PY" -m pip freeze --all
```

本轮九个安装/校验阶段均 rc=0。公共 wheel 的本次产物 SHA256 为 abbff3a759ff8ab6d60d724cc8e7b5e0e36ebcaa1bc2a934a21e0e4dfe87df97，仅用于识别本次产物，不承诺重新打包产生相同 SHA。

requirements-resolved.txt 可能含本任务 file:// 绝对路径；发布为可移植清单前应根据 sdk/receipt.json 的包名/版本规范化，不应直接复制私有任务路径。

## 6. 哪些完成了，哪些没有完成

- 已完成：固定 PR / 子模块获取、下载校验、官方 Dockerfile 两阶段构建、镜像载荷文件检查与版本命令、OCI 导出、固定源 SDK wheel 构建、匹配原生 wheel 安装、pip 依赖一致性检查。
- 未在本任务完成：公共 SDK Sandbox 创建、checkpoint/reload、跨节点恢复、512 MiB 内存完整核验、读者保护 / GC 故障验收、真实 RWFS 或 JuiceFS 读写验收、Pod/Kubernetes 部署。
- 不能把编译成功、pip check 或载荷静态检查写成 SDK 端到端通过。
- 本轮启动过构建容器和无网络只读载荷检查容器；没有启动 ADX 服务、SDK 沙箱、Pod 或 VM。

## 7. 适合整理进父仓的现有脚本

以下均位于新远端任务根，不在父 Git 仓，尚未作为公共通用工具提交：

- image-build/payload-check.py：相对独立、无凭据的镜像内载荷检查，最适合整理成复现工具；覆盖完整 gVisor 邻接 helper、FC initrd 静态 agent、EROFS 与匹配 ADX 载荷。
- image-build/bin/docker：只接受 build 的 Podman CLI shim。发布前须把硬编码任务路径参数化，保留私有 graph、CPU 限制、TLS 与不透传代理策略。
- image-build/build-official-images.py：持久构建监督、实际 rc/时间日志、载荷检查、镜像元数据和 OCI 导出。发布前须参数化任务根、保留固定版本与阶段边界；本轮低水位守卫未在构建过程中生效，不可包装成已验证能力。
- sdk/prepare-client.py：私有 pip bootstrap、固定 native wheel、从固定 PR SDK 源码构建公共 wheel、pip check 与 package receipt。发布前须把旧只读 bundle 的私有路径替换为显式已校验 bundle 输入。
- image-build/source-preparation.py：本轮安全归档之后补 Git 元数据与初始化真实 sandboxd 的审计实现。它依赖已解包源码，不是独立下载器；通用文档优先采用第 2 节的全新 Git checkout 命令。

完整实际记录入口：receipts/source.json、receipts/images.json、sdk/receipt.json、image-build/build-calls/、image-build/logs/、image-build/payload-receipt.json。日志和配置原件保持在独立远端根，未向父仓复制凭据或运行数据。

