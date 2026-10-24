#!/bin/bash
set -euo pipefail
umask 022
export GOMAXPROCS=2 GOFLAGS='-p=2 -buildvcs=false' GOCACHE=/gocache GOMODCACHE=/gomodcache GOPROXY=off
[[ $(cat /proc/self/cgroup) == '0::/' ]]
cd /src
go version
if [[ ${PROBE_PHASE:?} == old-red ]]; then
 set +e
 go test -count=1 -v -run '^Test(Allocate(PersistsLeaseBeforeReturn|WaitsForDurableLeaseCommit|StoreFailureDoesNotAdmitOrLoseCapacity)|OlderStoreCannotOverwriteCommittedAllocation)$' ./pkg/cgroupmanager > /out/regression.stdout 2> /out/regression.stderr
 red_rc=$?
 set -e
 [[ $red_rc == 1 ]]
 ! grep -qF '[build failed]' /out/regression.stdout
 ! grep -qF 'undefined:' /out/regression.stderr
 for test_name in TestAllocatePersistsLeaseBeforeReturn TestAllocateWaitsForDurableLeaseCommit TestAllocateStoreFailureDoesNotAdmitOrLoseCapacity TestOlderStoreCannotOverwriteCommittedAllocation; do
  grep -qF -- "--- FAIL: $test_name" /out/regression.stdout
 done
 exit 0
fi
[[ $PROBE_PHASE == candidate ]]
gofmt -w pkg/cgroupmanager/{cgroup,ops,ops_v1,ops_v2,ops_test,leases_persistence_test,leases_recovery_test}.go
make check-fmt > /out/fmt.stdout 2> /out/fmt.stderr
go test -count=3 -v ./pkg/cgroupmanager > /out/regression.stdout 2> /out/regression.stderr
make vet > /out/vet.stdout 2> /out/vet.stderr
make test TESTFLAGS='-count=1' > /out/unit.stdout 2> /out/unit.stderr
go test -race -count=1 ./pkg/cgroupmanager ./pkg/sandbox ./pkg/resourcemanager ./pkg/runtime/runsc ./pkg/runtime/firecracker ./internal/server > /out/race.stdout 2> /out/race.stderr
make release-binary > /out/build.stdout 2> /out/build.stderr
cp output/sandboxd /out/sandboxd
