#!/bin/bash
set -euo pipefail
umask 022
export GOTOOLCHAIN=local GOMODCACHE=/modcache GOCACHE=/gocache GOPATH=/gopath
cd /source
# 仅格式化已登记的候选，未关闭静态检查或资源隔离。
gofmt -w pkg/sentry/checkpoint/clone_filestore.go pkg/sentry/checkpoint/clone_filestore_test.go pkg/sentry/pgalloc/save_restore.go runsc/container/filestore_snapshot.go runsc/boot/filter/config/config_main.go runsc/boot/filter/config/config_test.go
cp pkg/sentry/checkpoint/clone_filestore.go pkg/sentry/checkpoint/clone_filestore_test.go /helper/
cd /helper
go version
go test -mod=readonly -race -count=3 -v ./...
go test -mod=readonly -c -o /out/clone-filestore.test ./...
