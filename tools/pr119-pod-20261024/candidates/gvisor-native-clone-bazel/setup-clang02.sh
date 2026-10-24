#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends crossbuild-essential-arm64
mkdir -p /usr/local/share/akernel-build
clang --version > /usr/local/share/akernel-build/clang-version.txt
dpkg-query -W -f='${Package}=${Version}\n' clang clang-14 libbpf-dev libc6-dev-i386 libnuma-dev python3 pkg-config gcc libc6-dev binutils crossbuild-essential-arm64 gcc-aarch64-linux-gnu g++-aarch64-linux-gnu binutils-aarch64-linux-gnu > /usr/local/share/akernel-build/packages.txt
printf 'int prog(void *ctx) { return 2; }\n' > /tmp/akernel-clang-probe.c
clang -O2 -target bpf -c /tmp/akernel-clang-probe.c -o /tmp/akernel-clang-probe.o
aarch64-linux-gnu-gcc -c /tmp/akernel-clang-probe.c -o /tmp/akernel-arm-probe.o
rm /tmp/akernel-clang-probe.c /tmp/akernel-clang-probe.o /tmp/akernel-arm-probe.o
apt-get clean
rm -rf /var/lib/apt/lists/*
