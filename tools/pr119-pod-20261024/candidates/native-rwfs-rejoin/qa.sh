set -euo pipefail
umask 022
export GOMAXPROCS=2 GOFLAGS="-p=2 -buildvcs=false" GOCACHE=/gocache GOMODCACHE=/gomodcache GOPROXY=off
test "$(cat /proc/self/cgroup)" = "0::/"
cd /src
go version
gofmt -w config/config.go internal/server/server.go internal/server/network_retirement.go internal/server/network_retirement_test.go internal/server/network_retirement_acl_linux_test.go pkg/networkmanager/tap_recovery_test.go pkg/runtime/firecracker/handler.go pkg/runtime/firecracker/checkpoint_handler.go pkg/runtime/firecracker/writable_directory_linux.go pkg/runtime/firecracker/writable_directory_linux_test.go
make check-fmt > /out/fmt.stdout 2> /out/fmt.stderr
SANDBOXD_NETWORK_RETIREMENT_KERNEL_TEST=1 SANDBOXD_FC_WRITABLE_MOUNT_TEST=1 SANDBOXD_FC_CAPTURE_IO_TEST=1 go test -count=3 -v -run '^Test(NetworkRetirement|Firecracker(Writable|CheckpointIncludesWriteCompleted|CheckpointInvalidatesBase)|Recovery(RejectsMissingActiveTapWithoutRetirementProof|RejectsExternallyReplacedActiveTap|RepairsIdleOrphanMacAndBridgeDrift))' ./internal/server ./pkg/networkmanager ./pkg/runtime/firecracker > /out/regression.stdout 2> /out/regression.stderr
make vet > /out/vet.stdout 2> /out/vet.stderr
make test TESTFLAGS="-count=1" > /out/unit.stdout 2> /out/unit.stderr
SANDBOXD_FC_WRITABLE_MOUNT_TEST=1 SANDBOXD_FC_CAPTURE_IO_TEST=1 go test -race -count=1 ./internal/server ./pkg/networkmanager ./pkg/runtime/firecracker > /out/race.stdout 2> /out/race.stderr
make release-binary > /out/build.stdout 2> /out/build.stderr
cp output/sandboxd /out/sandboxd
