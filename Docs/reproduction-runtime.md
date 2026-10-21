# Runtime 构建与测试可复现命令附录

本附录从本轮已保存的进程 argv 与结果记录导出。文中的命令用于复现构建和测试，本次导出没有再次执行门禁、启动服务、运行 SDK 或 VM，也没有修改源码和挂载。历史失败尝试的日志仍保留在本轮结果摘要指向的位置。

`$SRC` 是包含 `sandboxd/` 和 `gvisor/` 两份源码导出的父目录；`$TASK` 是本次复放独占的新输出目录；`$TOOLS` 是只读工具链及可选依赖缓存种子的目录。三者都由复放者设置为绝对路径，`$TASK` 不与其他任务共享。本文没有原机器的目录、主机地址或凭据。

| 输入 | 本轮使用的精确版本或范围 |
|---|---|
| sandboxd 源码 | Git 基线 `d5886b42ceff89bf0bf9baf7f73f5c534f689dee` 加本轮交付中已验收的 phase69 源码修改；只取该基线不能复放本轮结果 |
| sandboxd Go | `go1.27.2 linux/amd64`，放在 `$TOOLS/go1.27.2/` |
| gVisor 源码 | Git 基线 `7fdef444b108f898d0d2959bc2d9d43b2ffb53ee`，本轮完整 Git tree 为 `1e16effbd98a59b5bc8954c0006f39dad20eb00d` |
| gVisor Go | Bazel 规则选择的 `go1.26.3 linux/amd64`；格式检查另用同版本 SDK，放在 `$TOOLS/go1.26.3/` |
| Bazel | `8.3.1` Linux x86-64 ELF，放在 `$TOOLS/bazel-8.3.1-linux-x86_64` |
| 并行度 | `JOBS=2`、`GOMAXPROCS=2`、Go `-p 2`；Bazel `--jobs=2`，CPU 上限参数为 2 |

工具链文件、完整源码和外部依赖不是本文附件。`seccomp apparmor` 构建还需要对应 C 编译器、头文件、库及 `pkg-config`。本文没有安装依赖或修改系统环境的命令。没有这些输入时，不能声称本文可离线一键复放。

## 完整的公开启动与记录辅助函数

下面的函数是本轮临时 Python supervisor 的独立 shell 替代，可直接纳入复现脚本。它先创建新的 mount namespace，并将挂载传播设置为 private，确认与父进程的 mount namespace 不同后，才把本任务的实际临时目录 bind 到该 namespace 的 `/tmp`。宿主机共享挂载不变，临时文件实际落在 `$TASK/<组件>/tmp`。需要具备创建 mount namespace 和 bind mount 的权限；本附录不会假定普通无权限用户能够运行。

本轮 sandboxd 最终全仓测试及构建、gVisor 门禁使用私有 `/tmp`。sandboxd 的格式、vet 和专项 race 最初使用独立的普通临时目录；下面为这些命令统一使用相同私有 `/tmp` 启动函数，argv、测试 selector 和工具链保持记录中的内容。

```sh
: "${SRC:?set the absolute source-export parent directory}"
: "${TASK:?set a new private output directory}"
: "${TOOLS:?set the read-only toolchain directory}"

capture() {
  record_name=$1
  shift
  mkdir -p "$TASK/records"
  if "$@" > "$TASK/records/$record_name.stdout" \
            2> "$TASK/records/$record_name.stderr"; then
    gate_rc=0
  else
    gate_rc=$?
  fi
  printf '%s\n' "$gate_rc" > "$TASK/records/$record_name.returncode"
  return "$gate_rc"
}

private_tmp() {
  component=$1
  shift
  case "$component" in sandboxd|gvisor) ;; *) return 2 ;; esac
  component_root=$TASK/$component
  mkdir -p "$component_root/home" "$component_root/tmp" \
    "$component_root/gopath" "$component_root/modcache" \
    "$component_root/gocache" "$component_root/artifacts" \
    "$component_root/records" "$component_root/tools"
  parent_mount_ns=$(readlink /proc/self/ns/mnt)
  env -i SRC="$SRC" TASK="$TASK" TOOLS="$TOOLS" \
    COMPONENT="$component" PARENT_MOUNT_NS="$parent_mount_ns" \
    REPLAY_OFFLINE="${REPLAY_OFFLINE:-0}" \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    unshare --mount --propagation private /bin/sh -eu -c '
      component_root=$TASK/$COMPONENT
      worker_mount_ns=$(readlink /proc/self/ns/mnt)
      test "$worker_mount_ns" != "$PARENT_MOUNT_NS"
      printf "parent=%s\nworker=%s\ndistinct_before_bind=true\n" \
        "$PARENT_MOUNT_NS" "$worker_mount_ns" \
        > "$component_root/records/private-mount-namespace.txt"
      mount --bind "$component_root/tmp" /tmp
      findmnt --target /tmp -o TARGET,SOURCE,FSTYPE,PROPAGATION \
        > "$component_root/records/private-tmp-mount.txt"
      export HOME="$component_root/home"
      export XDG_CACHE_HOME="$component_root/home/.cache"
      export TMPDIR=/tmp TMP=/tmp TEMP=/tmp
      export GOPATH="$component_root/gopath"
      export GOMODCACHE="$component_root/modcache"
      export GOCACHE="$component_root/gocache"
      export JOBS=2 GOMAXPROCS=2 LANG=C.UTF-8 LC_ALL=C.UTF-8
      if test "$COMPONENT" = sandboxd; then
        export PATH="$TOOLS/go1.27.2/bin:$PATH"
        export GOTOOLCHAIN=local GOTMPDIR=/tmp CGO_ENABLED=1
        export GOFLAGS="-p=2 -mod=readonly"
        if test "$REPLAY_OFFLINE" = 1; then
          export GOPROXY=off GOSUMDB=off GOENV=off
        fi
      else
        export GOFLAGS=-p=2
      fi
      cd "$SRC/$COMPONENT"
      exec "$@"
    ' runtime-gate "$@"
}
```

`capture` 保存 stdout、stderr 和真实退出码，返回同一退出码。Go JSON 测试流及 Bazel 的新鲜 `test.log`/`test.xml` 用于确认测试确实运行；仅有工具启动成功或零测试不算对应测试门禁通过。逐条运行下面的命令，并保留每条命令的结果。

## sandboxd 依赖缓存与门禁

本轮从已验收任务的只读 module/build cache 独立复制到新任务目录，没有写回原缓存。公开复放可使用自己提供的相同依赖缓存种子：

```sh
mkdir -p "$TASK/sandboxd/modcache" "$TASK/sandboxd/gocache"
cp -a --reflink=auto "$TOOLS/sandboxd-cache-seed/modcache/." \
  "$TASK/sandboxd/modcache/"
cp -a --reflink=auto "$TOOLS/sandboxd-cache-seed/gocache/." \
  "$TASK/sandboxd/gocache/"
```

`$TOOLS/sandboxd-cache-seed` 是复放者提供的输入，不是一个公开下载地址。没有缓存种子时，可在新任务中先联网取得 `go.mod`/`go.sum` 锁定的依赖，再运行离线门禁；缓存中的依赖本身仍须可获取。

```sh
capture sandboxd-module-download private_tmp sandboxd \
  "$TOOLS/go1.27.2/bin/go" mod download
```

本轮工具链检查期望输出 `go version go1.27.2 linux/amd64`：

```sh
capture sandboxd-go-version private_tmp sandboxd \
  "$TOOLS/go1.27.2/bin/go" version
```

### 格式、vet 与全仓测试

```sh
capture sandboxd-check-fmt private_tmp sandboxd \
  make \
  -j2 \
  check-fmt
```
```sh
capture sandboxd-vet private_tmp sandboxd \
  make \
  -j2 \
  vet
```
```sh
REPLAY_OFFLINE=1 capture sandboxd-full-test private_tmp sandboxd \
  make \
  -j2 \
  test \
  "GO=$TOOLS/go1.27.2/bin/go" \
  'TESTFLAGS=-p 2 -json -count=1'
```
本轮最终全仓测试实际启动 911 个顶层测试，906 个通过、5 个按默认配置跳过、0 个失败；包含子测试时为 1420 个启动、1415 个通过、5 个跳过。5 个跳过项为 cgroup-v2、distill-fs capacity、EROFS loop、TAP checksum offload 和 loop-backed filestore 的特权集成测试，本轮未启用对应集成测试开关。

### 专项 race 的完整 selector

以下三个 `-run` 参数逐字取自本轮实际 argv。`-count=1` 强制执行，`-parallel=1` 保持本轮测试并行口径。

```sh
capture sandboxd-race-server private_tmp sandboxd \
  "$TOOLS/go1.27.2/bin/go" \
  test \
  -p \
  2 \
  -race \
  -json \
  ./internal/server \
  -run \
  '^(TestAddResourceMemory|TestCheckpointDirectoryValidation|TestCheckpointFailureCleansResidualsWithoutDeletingSource|TestCheckpointForwardsRequest|TestCheckpointGuestMemoryResources|TestCheckpointInputDirectoryValidation|TestCheckpointRejectsConcurrentOperation|TestCheckpointSyncOutputBarrierFailsPublicationOnUnsyncableEntry|TestCheckpointSyncOutputBarrierPassesCleanOutput|TestCheckpointTimeoutCleansCreatedDirectory|TestCheckpointValidatesRequestAndRuntime|TestCheckpointWithoutSyncKeepsHistoricalLocalContract|TestDeleteLegacyDoesNotStripPendingIntentDNAT|TestDescribeCheckpointArtifactsBindsExactManifestView|TestDescribeCheckpointArtifactsDoesNotValidatePayloadBytes|TestDescribeCheckpointArtifactsHonorsCanceledContext|TestDescribeCheckpointArtifactsRejectsInvalidDirectories|TestDescribeCheckpointArtifactsRejectsUnsealedAndUncoveredArtifacts|TestDescribeCheckpointArtifactsUsesAdmissionRootWithoutWriting|TestDescribeCheckpointArtifactsWireContract|TestFSRestoreKeepsPendingIntentStateAsOwned|TestFirecrackerCheckpointHeadroom|TestFirecrackerCheckpointMemorySlotHonorsCancellation|TestFullServiceShutdownPreservesRetainedStartChain|TestGetStartOperationUnknownAndInvalidIDs|TestLoadStartIntentsKeepsPreparedIntentDespiteMatchingMetadata|TestLoadStartIntentsKeepsRetainedIntentDespiteMetadata|TestLoadStartIntentsRejectsCorruptRecords|TestLoadStartIntentsRejectsUnexpectedEntries|TestLoadStartIntentsRemovesStaleTempFiles|TestLoadStartIntentsRetainsPendingWithoutMetadata|TestLoadStartIntentsRetiresCommittedIntentOnFullIdentity|TestManagerLoadSkipsRecycleForPendingIntentRoots|TestResetStateIfPodChangedRefusesWithPendingIntents|TestRestartAfterRetainedStartKeepsProtectionChain|TestRestartAfterSuccessfulStartCutPoints|TestRetirementBeforeAdmissionSurvivesRestartAndRejectsLateStart|TestRetirementCompletedReplayCannotDeleteLaterIncarnation|TestRetirementConcurrentReplayHasOneDurableIdentity|TestRetirementFencePersistenceFailureReturnsNoProofAndStillDenies|TestRetirementStrictExitFailureKeepsFenceWithoutReceipt|TestRetirementSuccessfulStartUsesStrictProofAndReplaySparesNewGeneration|TestRetirementUnknownOutcomeNeverBecomesAbsenceProof|TestRetirementWaitsForActualExecutorAndTimeoutKeepsProtection|TestShouldRaiseFirecrackerCheckpointMemoryLimit|TestShutdownPreservesRetainedStartFilesystemOwnership|TestStartCommitWriteFailureMustNotReportSuccess|TestStartFailureDoesNotWipePreExistingSameIDState|TestStartIntentStoreBeginRetainClearRoundTrip|TestStartIntentWriteFailureRetainsWhenRemovalUnknown|TestStartIntentWriteFailureRollsBackWhenRemovalConfirmed|TestStartOperationAdmissionWriteFailureSpendsID|TestStartOperationAdmitPublishesOnlyWithRegisteredExecutor|TestStartOperationCallerCancelEndsOnlyTheWait|TestStartOperationConcurrentSameRequestExecutesOnce|TestStartOperationDifferentRequestConflicts|TestStartOperationForwardsExpectedRootToRuntime|TestStartOperationLateCancelRegistrationConverges|TestStartOperationLegacyServerUnimplemented|TestStartOperationPodResetKeepsTombstones|TestStartOperationReplayAfterDeleteKeepsHistoricalSuccess|TestStartOperationRestartReload|TestStartOperationRestoreArtifactIdentity|TestStartOperationRestoreRefusesUnsupportedRuntime|TestStartOperationRestoreRootRequiresCompleteCoverage|TestStartOperationRootDigestBindsRealArtifactLayouts|TestStartOperationRootDigestBindsUncoveredSidecars|TestStartOperationServiceShutdownDuringAdmissionGapConverges|TestStartOperationShutdownWaitsForRealExit|TestStartOperationSuccessPublishesOnlyAfterPersist|TestStartOperationSuccessWriteFailureResolvedByRestart|TestStartOperationTakeoverPersistFailureFailsClosed|TestStartPersistsIntentAndFSBeforeRuntimeInvocation|TestStartPostSuccessFailureRetainsWithoutStrictSupport|TestStartPostSuccessFailureUsesStrictExitProof|TestStartRuntimeCleanupPendingRetainsEverything|TestStartRuntimeFailureRetainsWithoutProofContract|TestStartRuntimeFailureRollsBackWithProvenCleanupContract|TestStartSandboxRuntimeDispatchesRestore|TestStartSandboxRuntimeRejectsUnsupportedRestore|TestStartSandboxRuntimeUsesStartWithoutCheckpoint)$' \
  -count=1 \
  -parallel=1
```
```sh
capture sandboxd-race-firecracker private_tmp sandboxd \
  "$TOOLS/go1.27.2/bin/go" \
  test \
  -p \
  2 \
  -race \
  -json \
  ./pkg/runtime/firecracker \
  -run \
  '^(TestA1FCDeleteConfirmsExitBeforeCleanup|TestA1FCDeleteRejectsInvalidRecordedPID|TestA1FCDeleteRetainsUnconfirmedVirtioFSReader|TestA1FCDeleteRetainsUnrecognizedLiveProcess|TestA1FCDeleteRetriesAfterIdentityRestored|TestA1FCExitChild|TestCheckpointV2CarriesVirtioFSState|TestFinalizeCheckpointV2CoversLargeComponentDigests|TestFinalizeCheckpointV2ManifestIsSealedOnce|TestFinalizeCheckpointV2RejectsVirtioFSMismatch|TestOpenCheckpointSniffsLayouts|TestOpenCheckpointV2AndVerifyDigests|TestOpenCheckpointV2RejectsBadManifests|TestOpenCheckpointV2RejectsMissingComponent|TestPhase64InstantiateVerifyFailureStopsBeforeClone|TestPhase64ManifestExclusiveErrorUnchanged|TestPhase64SealTimingFields|TestPhase64VerifyCacheAndMismatchUnchanged|TestPhase69CancellationBeforeStartAndWhileQueued|TestPhase69CapacityRolloverUsesLegacyOrder|TestPhase69ConcurrentWarmCacheAndMtimeInvalidation|TestPhase69EachComponentDamageRejected|TestPhase69OrdinaryErrorDoesNotCancelAndStillJoins|TestPhase69OriginalDigesterFDAndWorkerLifetime|TestPhase69SealCanceledAndManifestExclusiveError|TestPhase69SealMatchesOriginalDigester|TestPhase69SealReadErrorsNeverPublishManifest|TestPhase69SharedBudgetAcrossConcurrentSealAndVerify|TestPhase69VerifyReadErrorAndMismatchPrefix|TestPrepareCheckpointV2ClonesBaseMemory|TestPrepareCheckpointV2FullDiscoversMemorySize|TestPrepareCheckpointV2PreallocatesZeroMemory|TestPrepareCheckpointV2RejectsSealedDirectory|TestPrepareCheckpointV2RejectsV1ArchiveDirectory|TestVerifyCheckpointDigestsMemoized)$' \
  -count=1 \
  -parallel=1
```
```sh
capture sandboxd-race-runsc private_tmp sandboxd \
  "$TOOLS/go1.27.2/bin/go" \
  test \
  -p \
  2 \
  -race \
  -json \
  ./pkg/runtime/runsc \
  -run \
  '^(TestA1RunscBindsParsedManifestBytes|TestA1RunscClientVerifiesBeforeStateOrNetwork|TestA1RunscHandlerSealsSuccessfulCheckpointOnly|TestA1RunscManifestCoverageRefusals|TestA1RunscPinnedRestoreRefusesLegacy|TestA1RunscRejectsOversizeManifest|TestA1RunscRejectsSameSizePayloadReplacement|TestA1RunscRejectsSymlinkAndFIFO|TestA1RunscSealRefusesPartialAndUnknownOutput|TestA1RunscSealedCheckpointRoundTrip|TestA1RunscUsesOpenedDescriptorNotReopenedPath|TestA1RunscVerificationCancellation)$' \
  -count=1 \
  -parallel=1
```
三组本轮实际分别通过 81、35、12 个顶层测试，均无失败或跳过；包含子测试时分别通过 134、83、29 项。

### release-equivalent build 与只读产物信息

```sh
REPLAY_OFFLINE=1 capture sandboxd-release-build private_tmp sandboxd \
  "$TOOLS/go1.27.2/bin/go" \
  build \
  -p \
  2 \
  -o \
  "$TASK/sandboxd/artifacts/sandboxd" \
  -tags \
  'seccomp apparmor' \
  ./cmd/sandboxd
```
```sh
REPLAY_OFFLINE=1 capture sandboxd-artifact-info private_tmp sandboxd \
  "$TOOLS/go1.27.2/bin/go" \
  version \
  -m \
  "$TASK/sandboxd/artifacts/sandboxd"
```
```sh
sha256sum "$TASK/sandboxd/artifacts/sandboxd"
wc -c < "$TASK/sandboxd/artifacts/sandboxd"
```

本轮产物为 84237580 bytes，SHA-256 为 `6b2f5aca7e5ea42acdd10e798d7ffa999e791fcb807b543fa420a02d584d1f04`。编译路径、工具链或依赖输入变化可能改变二进制字节；此处摘要用于识别本轮产物，不保证另一输出目录下重建字节一致。没有执行该产物。

## gVisor 独立 Bazel 缓存初始化

本轮复制了只读 Bazel repository cache、disk cache，以及旧 output base 中的隐藏 `MODULE.bazel.lock` 到全新的 output base。最后一个文件保存 Bazel module extension 的已解析结果；它与源码根目录的 `MODULE.bazel.lock` 不同。本轮没有修改源码 lockfile。只复制 repository/disk cache 时，首次四条门禁均因 Go SDK 版本列表的 module-extension download 被禁用而返回 `48`，测试数为零；这些记录保留，不能计为测试通过。

有完整、匹配的只读缓存种子时，可以独立复制：

```sh
mkdir -p "$TASK/gvisor/repository-cache" "$TASK/gvisor/disk-cache" \
  "$TASK/gvisor/output-base" "$TASK/gvisor/output-user-root" \
  "$TASK/gvisor/links" "$TASK/gvisor/tools"
cp -a --reflink=auto "$TOOLS/bazel-cache-seed/repository-cache/." \
  "$TASK/gvisor/repository-cache/"
cp -a --reflink=auto "$TOOLS/bazel-cache-seed/disk-cache/." \
  "$TASK/gvisor/disk-cache/"
cp -a --reflink=auto "$TOOLS/bazel-cache-seed/MODULE.bazel.lock" \
  "$TASK/gvisor/output-base/MODULE.bazel.lock"
```

上述缓存种子包含本轮历史生成状态，不作为公开可下载输入提供；没有种子时不能照此宣称可直接离线复放。独立替代是使用自己的新 `$TASK`，先允许一次依赖联网解析并构建，生成属于该任务的缓存及隐藏 output lock，再执行下方保留 `--repository_disable_download` 的正式门禁。该初始化也受当前网络和外部依赖可获取性影响。

### workspace-status 完整替代脚本

本轮 optimized build 调用的临时 workspace-status 脚本只有下面这条固定输出。这里公开其完整等价内容，避免依赖原任务的临时脚本：

```sh
mkdir -p "$TASK/gvisor/tools"
cat > "$TASK/gvisor/tools/workspace-status" <<'SH'
#!/bin/sh
printf '%s\n' 'STABLE_VERSION release-20260817.0-akernel.3-2-g7fdef444b108-a1-strong-delete-work02'
SH
chmod 755 "$TASK/gvisor/tools/workspace-status"
```

该字符串沿用本轮已验收候选的历史版本标签，不表示最终对外发布提交。若复放时改为自己的版本标签，属于明确改变构建输入，产物摘要也可能改变。

### 无历史缓存种子的独立初始化命令

下面与本轮 optimized build 使用相同构建参数，去掉禁止下载参数，并额外构建三个测试目标以准备依赖。它是公开复放的初始化替代步骤，没有在本次文档导出时执行，也不作为本轮实际门禁记录。

```sh
capture gvisor-independent-cache-initialization private_tmp gvisor \
  "$TOOLS/bazel-8.3.1-linux-x86_64" \
  --batch \
  "--output_user_root=$TASK/gvisor/output-user-root" \
  "--output_base=$TASK/gvisor/output-base" \
  --host_jvm_args=-Xmx1024m \
  --host_jvm_args=-XX:ActiveProcessorCount=2 \
  "--host_jvm_args=-Duser.home=$TASK/gvisor/home" \
  build \
  --jobs=2 \
  --loading_phase_threads=2 \
  --local_resources=cpu=2 \
  --local_resources=memory=3072 \
  "--repository_cache=$TASK/gvisor/repository-cache" \
  "--disk_cache=$TASK/gvisor/disk-cache" \
  --repo_env=GOMAXPROCS=2 \
  --action_env=GOMAXPROCS=2 \
  --lockfile_mode=error \
  --linkopt=-fuse-ld=bfd \
  --host_linkopt=-fuse-ld=bfd \
  --config=x86_64 \
  -c \
  opt \
  --stamp \
  "--workspace_status_command=$TASK/gvisor/tools/workspace-status" \
  //runsc:runsc \
  "--symlink_prefix=$TASK/gvisor/links/" \
  "--repo_env=HOME=$TASK/gvisor/home" \
  --repo_env=TMPDIR=/tmp \
  "--action_env=HOME=$TASK/gvisor/home" \
  --action_env=TMPDIR=/tmp \
  //runsc/container:retirement_test \
  //runsc/container:serialization_test \
  //pkg/sentry/kernel:kernel_test
```
### 工具链与改动文件格式检查

Bazel 后续构建由源码规则选择 Go SDK；应保持本轮 `go1.26.3`，不能仅凭 PATH 中的 Go 版本推定 Bazel 所用 SDK。本轮格式检查使用同版本 SDK，检查 7 个改动 Go 文件；其余 2 个改动文件是 BUILD，由后续 Bazel 分析。

```sh
capture gvisor-go-version private_tmp gvisor \
  "$TOOLS/go1.26.3/bin/go" \
  version
```
```sh
capture gvisor-bazel-version private_tmp gvisor \
  "$TOOLS/bazel-8.3.1-linux-x86_64" \
  --batch \
  "--output_user_root=$TASK/gvisor/output-user-root" \
  "--output_base=$TASK/gvisor/output-base" \
  --host_jvm_args=-Xmx1024m \
  --host_jvm_args=-XX:ActiveProcessorCount=2 \
  "--host_jvm_args=-Duser.home=$TASK/gvisor/home" \
  version
```
```sh
capture gvisor-format private_tmp gvisor /bin/sh -eu -c '
  files=$("$TOOLS/go1.26.3/bin/gofmt" -l \
    pkg/sentry/kernel/kernel_restore.go \
    pkg/sentry/kernel/kernel_restore_wait_test.go \
    runsc/cmd/delete.go \
    runsc/container/container.go \
    runsc/container/retirement.go \
    runsc/container/retirement_test.go \
    runsc/container/state_file.go)
  test -z "$files" || { printf "%s\n" "$files" >&2; exit 1; }
'
```

### retirement、serialization 和 waiter 的普通及 race 门禁

所有参数来自本轮实际 argv。每条命令均禁用测试结果缓存，保留详细测试输出；新鲜 `test.log` 和 `test.xml` 在独立 output base 的 `execroot/*/bazel-out/*/testlogs/` 下。

```sh
capture gvisor-retirement-serialization private_tmp gvisor \
  "$TOOLS/bazel-8.3.1-linux-x86_64" \
  --batch \
  "--output_user_root=$TASK/gvisor/output-user-root" \
  "--output_base=$TASK/gvisor/output-base" \
  --host_jvm_args=-Xmx1024m \
  --host_jvm_args=-XX:ActiveProcessorCount=2 \
  "--host_jvm_args=-Duser.home=$TASK/gvisor/home" \
  test \
  --jobs=2 \
  --loading_phase_threads=2 \
  --local_resources=cpu=2 \
  --local_resources=memory=3072 \
  "--repository_cache=$TASK/gvisor/repository-cache" \
  "--disk_cache=$TASK/gvisor/disk-cache" \
  --repo_env=GOMAXPROCS=2 \
  --action_env=GOMAXPROCS=2 \
  --lockfile_mode=error \
  --repository_disable_download \
  --linkopt=-fuse-ld=bfd \
  --host_linkopt=-fuse-ld=bfd \
  --test_env=GOMAXPROCS=2 \
  --nostamp \
  --workspace_status_command=/bin/true \
  --test_output=all \
  --test_timeout=600 \
  --nocache_test_results \
  --test_arg=-test.v \
  --test_arg=-test.parallel=2 \
  //runsc/container:retirement_test \
  //runsc/container:serialization_test \
  "--symlink_prefix=$TASK/gvisor/links/" \
  "--repo_env=HOME=$TASK/gvisor/home" \
  --repo_env=TMPDIR=/tmp \
  "--action_env=HOME=$TASK/gvisor/home" \
  --action_env=TMPDIR=/tmp \
  --test_tmpdir=/tmp \
  --test_env=TMPDIR=/tmp
```
```sh
capture gvisor-retirement-serialization-race private_tmp gvisor \
  "$TOOLS/bazel-8.3.1-linux-x86_64" \
  --batch \
  "--output_user_root=$TASK/gvisor/output-user-root" \
  "--output_base=$TASK/gvisor/output-base" \
  --host_jvm_args=-Xmx1024m \
  --host_jvm_args=-XX:ActiveProcessorCount=2 \
  "--host_jvm_args=-Duser.home=$TASK/gvisor/home" \
  test \
  --jobs=2 \
  --loading_phase_threads=2 \
  --local_resources=cpu=2 \
  --local_resources=memory=3072 \
  "--repository_cache=$TASK/gvisor/repository-cache" \
  "--disk_cache=$TASK/gvisor/disk-cache" \
  --repo_env=GOMAXPROCS=2 \
  --action_env=GOMAXPROCS=2 \
  --lockfile_mode=error \
  --repository_disable_download \
  --linkopt=-fuse-ld=bfd \
  --host_linkopt=-fuse-ld=bfd \
  --test_env=GOMAXPROCS=2 \
  --nostamp \
  --workspace_status_command=/bin/true \
  --test_output=all \
  --test_timeout=600 \
  --nocache_test_results \
  --test_arg=-test.v \
  --test_arg=-test.parallel=2 \
  --config=race \
  //runsc/container:retirement_test \
  //runsc/container:serialization_test \
  "--symlink_prefix=$TASK/gvisor/links/" \
  "--repo_env=HOME=$TASK/gvisor/home" \
  --repo_env=TMPDIR=/tmp \
  "--action_env=HOME=$TASK/gvisor/home" \
  --action_env=TMPDIR=/tmp \
  --test_tmpdir=/tmp \
  --test_env=TMPDIR=/tmp
```
```sh
capture gvisor-waiter private_tmp gvisor \
  "$TOOLS/bazel-8.3.1-linux-x86_64" \
  --batch \
  "--output_user_root=$TASK/gvisor/output-user-root" \
  "--output_base=$TASK/gvisor/output-base" \
  --host_jvm_args=-Xmx1024m \
  --host_jvm_args=-XX:ActiveProcessorCount=2 \
  "--host_jvm_args=-Duser.home=$TASK/gvisor/home" \
  test \
  --jobs=2 \
  --loading_phase_threads=2 \
  --local_resources=cpu=2 \
  --local_resources=memory=3072 \
  "--repository_cache=$TASK/gvisor/repository-cache" \
  "--disk_cache=$TASK/gvisor/disk-cache" \
  --repo_env=GOMAXPROCS=2 \
  --action_env=GOMAXPROCS=2 \
  --lockfile_mode=error \
  --repository_disable_download \
  --linkopt=-fuse-ld=bfd \
  --host_linkopt=-fuse-ld=bfd \
  --test_env=GOMAXPROCS=2 \
  --nostamp \
  --workspace_status_command=/bin/true \
  --test_output=all \
  --test_timeout=600 \
  --nocache_test_results \
  --test_arg=-test.v \
  --test_arg=-test.parallel=2 \
  '--test_filter=^(TestCheckpointRegistrationLockOrder|TestCheckpointRegistrationAfterNotification|TestCheckpointWaiterThresholdUnregisterAndError)$' \
  //pkg/sentry/kernel:kernel_test \
  "--symlink_prefix=$TASK/gvisor/links/" \
  "--repo_env=HOME=$TASK/gvisor/home" \
  --repo_env=TMPDIR=/tmp \
  "--action_env=HOME=$TASK/gvisor/home" \
  --action_env=TMPDIR=/tmp \
  --test_tmpdir=/tmp \
  --test_env=TMPDIR=/tmp
```
```sh
capture gvisor-waiter-race private_tmp gvisor \
  "$TOOLS/bazel-8.3.1-linux-x86_64" \
  --batch \
  "--output_user_root=$TASK/gvisor/output-user-root" \
  "--output_base=$TASK/gvisor/output-base" \
  --host_jvm_args=-Xmx1024m \
  --host_jvm_args=-XX:ActiveProcessorCount=2 \
  "--host_jvm_args=-Duser.home=$TASK/gvisor/home" \
  test \
  --jobs=2 \
  --loading_phase_threads=2 \
  --local_resources=cpu=2 \
  --local_resources=memory=3072 \
  "--repository_cache=$TASK/gvisor/repository-cache" \
  "--disk_cache=$TASK/gvisor/disk-cache" \
  --repo_env=GOMAXPROCS=2 \
  --action_env=GOMAXPROCS=2 \
  --lockfile_mode=error \
  --repository_disable_download \
  --linkopt=-fuse-ld=bfd \
  --host_linkopt=-fuse-ld=bfd \
  --test_env=GOMAXPROCS=2 \
  --nostamp \
  --workspace_status_command=/bin/true \
  --test_output=all \
  --test_timeout=600 \
  --nocache_test_results \
  --test_arg=-test.v \
  --test_arg=-test.parallel=2 \
  '--test_filter=^(TestCheckpointRegistrationLockOrder|TestCheckpointRegistrationAfterNotification|TestCheckpointWaiterThresholdUnregisterAndError)$' \
  //pkg/sentry/kernel:kernel_test \
  "--symlink_prefix=$TASK/gvisor/links/" \
  "--repo_env=HOME=$TASK/gvisor/home" \
  --repo_env=TMPDIR=/tmp \
  "--action_env=HOME=$TASK/gvisor/home" \
  --action_env=TMPDIR=/tmp \
  --test_tmpdir=/tmp \
  --test_env=TMPDIR=/tmp \
  --config=race
```
retirement/serialization 的普通和 race 每轮均实际通过 14 个顶层测试及 5 个子测试，无跳过；`TestRetirementWaitsForBothNamespacesAndDescendants` 在两轮均实际执行并通过。waiter 的普通和 race 每轮均实际通过 3 个顶层测试及 2 个子测试，无跳过。

### optimized runsc build 与产物信息

```sh
capture gvisor-runsc-build private_tmp gvisor \
  "$TOOLS/bazel-8.3.1-linux-x86_64" \
  --batch \
  "--output_user_root=$TASK/gvisor/output-user-root" \
  "--output_base=$TASK/gvisor/output-base" \
  --host_jvm_args=-Xmx1024m \
  --host_jvm_args=-XX:ActiveProcessorCount=2 \
  "--host_jvm_args=-Duser.home=$TASK/gvisor/home" \
  build \
  --jobs=2 \
  --loading_phase_threads=2 \
  --local_resources=cpu=2 \
  --local_resources=memory=3072 \
  "--repository_cache=$TASK/gvisor/repository-cache" \
  "--disk_cache=$TASK/gvisor/disk-cache" \
  --repo_env=GOMAXPROCS=2 \
  --action_env=GOMAXPROCS=2 \
  --lockfile_mode=error \
  --repository_disable_download \
  --linkopt=-fuse-ld=bfd \
  --host_linkopt=-fuse-ld=bfd \
  --config=x86_64 \
  -c \
  opt \
  --stamp \
  "--workspace_status_command=$TASK/gvisor/tools/workspace-status" \
  //runsc:runsc \
  "--symlink_prefix=$TASK/gvisor/links/" \
  "--repo_env=HOME=$TASK/gvisor/home" \
  --repo_env=TMPDIR=/tmp \
  "--action_env=HOME=$TASK/gvisor/home" \
  --action_env=TMPDIR=/tmp
```
Bazel 构建成功后的产物位于独立 output base 的 `execroot/*/bazel-out/*/bin/runsc/runsc_/runsc`。下面的完整复制片段要求该新 output base 中只有一个匹配产物，避免选择其他配置留下的文件：

```sh
set -- "$TASK"/gvisor/output-base/execroot/*/bazel-out/*/bin/runsc/runsc_/runsc
test "$#" -eq 1
test -f "$1"
mkdir -p "$TASK/gvisor/artifacts"
cp "$1" "$TASK/gvisor/artifacts/runsc"
chmod 755 "$TASK/gvisor/artifacts/runsc"
capture gvisor-runsc-build-info private_tmp gvisor \
  "$TOOLS/go1.26.3/bin/go" version -m "$TASK/gvisor/artifacts/runsc"
sha256sum "$TASK/gvisor/artifacts/runsc"
wc -c < "$TASK/gvisor/artifacts/runsc"
```

本轮 runsc 为 105585738 bytes，SHA-256 为 `a4c84b051a402ba07c169c71ac9784bfd2f54662d3c3271a5230d82fae9c8982`。该产物没有运行，也没有部署或修改 runtime release pin。

## 必须随结果保留的失败与中断尝试

- 初次工具链指令误将 gVisor 的 Go1.26.3 用于 sandboxd，格式检查返回 2，正在执行的 vet 被中断。更正为已验收 Go1.27.2 后重新记录正式门禁；这份初次尝试单独保留，没有计入最终通过项。
- sandboxd 第一次全仓测试使用较长的独立绝对 TMP 路径，4 个 Unix socket 测试因路径超过 AF_UNIX 限制而失败，真实 make 退出码为 2，顶层测试为 902 通过、4 失败、5 跳过。
- `/proc/<自有supervisor>/fd/<fd>` 短 TMP 尝试不适配要求普通绝对路径的测试，并导致一个 checkpoint 并发测试等待未结束。该尝试未完整执行，顶层测试为 737 通过、16 失败、5 跳过，另有 1 个已启动未完成。执行者在记录精确 PID、启动时间、ELF、cwd 和 namespace 后，仅向该自有测试进程发送 TERM，原 supervisor 保留真实 make 退出码 2。最终改为私有 mount namespace 内的普通 `/tmp` 后，全仓测试通过，源码未改。
- gVisor 首次新 output base 没有 module-extension 缓存，四条门禁均退出 48，零测试；独立复制隐藏 output lock 后重新执行正式门禁。没有开启下载来掩盖这份失败记录。

本附录提供源码与输入已准备好之后的逐项复现方式。私有挂载随相应 namespace 的进程退出而撤销；依赖缓存、日志及编译产物保留在复放者自己的 `$TASK`，无需清理其他任务或共享服务。
