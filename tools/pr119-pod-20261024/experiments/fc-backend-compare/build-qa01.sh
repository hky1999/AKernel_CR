set -euo pipefail
export GOMAXPROCS=2 GOFLAGS='-p=2 -buildvcs=false' GOCACHE=/gocache GOMODCACHE=/gomodcache GOPROXY=off
test "$(cat /proc/self/cgroup)" = '0::/'
cd /src
go version
gofmt -w guest-storage-io.go
CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/guest-storage-io guest-storage-io.go
/out/guest-storage-io --path /out/smoke-a --bytes 65536 --ops 4 --seed 20261024 > /out/smoke-a.json
/out/guest-storage-io --path /out/smoke-b --bytes 65536 --ops 4 --seed 20261024 > /out/smoke-b.json
