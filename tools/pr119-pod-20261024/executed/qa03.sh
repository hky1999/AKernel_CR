#!/bin/bash
set -euo pipefail
umask 077
trap 'rc=$?; printf "{\"rc\":%s}\n" "$rc" > /out/qa-terminal.json' EXIT
export GOMODCACHE=/gomodcache GOCACHE=/gocache GOMAXPROCS=2
export GOFLAGS='-p=2 -buildvcs=false' GOPROXY=off
test "$(cat /proc/self/cgroup)" = '0::/'
printf 'QA_NETWORK_NAMESPACE '; readlink /proc/self/ns/net
printf 'QA_CGROUP_NAMESPACE '; readlink /proc/self/ns/cgroup
go version
cd /baseline
go test -c -o /out/tap-baseline.test ./pkg/runtime/runsc > /out/baseline-build.stdout 2> /out/baseline-build.stderr
set +e
SANDBOXD_RUNSC_TAP_REUSE_TEST=1 /out/tap-baseline.test -test.v -test.run '^TestOpenTAPClearsPersistentChecksumOffload$' > /out/baseline-regression.stdout 2> /out/baseline-regression.stderr
baseline_rc=$?
set -e
printf '{"baseline_rc":%s}\n' "$baseline_rc" > /out/baseline-regression.json
test "$baseline_rc" -ne 0
grep -F 'persistent TAP TX checksum offload = true, want false' /out/baseline-regression.stdout
cd /src/sandboxd
gofmt -l . > /out/fmt.txt
test ! -s /out/fmt.txt
go test -c -o /out/tap-fixed.test ./pkg/runtime/runsc > /out/fixed-build.stdout 2> /out/fixed-build.stderr
SANDBOXD_RUNSC_TAP_REUSE_TEST=1 /out/tap-fixed.test -test.v -test.run '^TestOpenTAPClearsPersistentChecksumOffload$' > /out/fixed-regression.stdout 2> /out/fixed-regression.stderr
go vet ./... > /out/vet.stdout 2> /out/vet.stderr
(umask 022; make test TESTFLAGS='-count=1') > /out/unit.stdout 2> /out/unit.stderr
(umask 022; SANDBOXD_RUNSC_TAP_REUSE_TEST=1 go test -race -count=1 ./pkg/runtime/runsc) > /out/race.stdout 2> /out/race.stderr
make release-binary > /out/build.stdout 2> /out/build.stderr
cp output/sandboxd /out/sandboxd
sha256sum /out/sandboxd > /out/sandboxd.sha256
printf '{"status":"source-gates-passed-not-sdk-accepted"}\n' > /out/status.json
