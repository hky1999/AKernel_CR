#!/bin/bash
set -euo pipefail
umask 022
export GOMAXPROCS=2 GOFLAGS='-p=2 -buildvcs=false' GOCACHE=/gocache GOMODCACHE=/gomodcache GOPROXY=off
[[ $(cat /proc/self/cgroup) == '0::/' ]]
cd /src
go version
# Only the candidate input files are formatted. No local format/build/test.
gofmt -w config/config.go config/config_test.go pkg/runtime/runsc/client.go pkg/runtime/runsc/client_test.go pkg/runtime/runsc/handler.go pkg/runtime/runsc/filestore_checkpoint.go pkg/runtime/runsc/filestore_checkpoint_test.go pkg/runtime/runsc/writable_directory_linux.go pkg/runtime/runsc/writable_directory_linux_test.go
make check-fmt > /out/fmt.stdout 2> /out/fmt.stderr
go test -count=3 -v -run '^Test.*(Filestore|Writable|CheckpointMode|Restore)' ./config ./pkg/runtime/runsc > /out/regression.stdout 2> /out/regression.stderr
make vet > /out/vet.stdout 2> /out/vet.stderr
make test TESTFLAGS='-count=1' > /out/unit.stdout 2> /out/unit.stderr
go test -race -count=1 ./pkg/runtime/runsc ./config ./internal/server ./pkg/networkmanager ./pkg/runtime/firecracker > /out/race.stdout 2> /out/race.stderr
make release-binary > /out/build.stdout 2> /out/build.stderr
cp output/sandboxd /out/sandboxd
