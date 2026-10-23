set -euo pipefail
umask 022
export GOMAXPROCS=2 GOFLAGS="-p=2 -buildvcs=false" GOCACHE=/gocache GOMODCACHE=/gomodcache GOPROXY=off
test "$(cat /proc/self/cgroup)" = "0::/"
go version
cd /src
gofmt -w pkg/runtime/firecracker/checkpoint_handler.go pkg/runtime/firecracker/checkpoint_io_cut_linux_test.go
gofmt -l . > /out/fmt.txt
test ! -s /out/fmt.txt
go test -c -o /out/capture.test ./pkg/runtime/firecracker > /out/build-test.stdout 2> /out/build-test.stderr
SANDBOXD_FC_CAPTURE_IO_TEST=1 /out/capture.test -test.v -test.count=3 -test.run "^TestFirecrackerCheckpoint(IncludesWriteCompletedDuringDeviceSave|InvalidatesBaseAfterDiskCaptureFailure)$" > /out/regression.stdout 2> /out/regression.stderr
go vet ./... > /out/vet.stdout 2> /out/vet.stderr
make test TESTFLAGS="-count=1" > /out/unit.stdout 2> /out/unit.stderr
SANDBOXD_FC_CAPTURE_IO_TEST=1 go test -race -count=1 ./pkg/runtime/firecracker > /out/race.stdout 2> /out/race.stderr
make release-binary > /out/build.stdout 2> /out/build.stderr
cp output/sandboxd /out/sandboxd
sha256sum /out/sandboxd > /out/sandboxd.sha256
