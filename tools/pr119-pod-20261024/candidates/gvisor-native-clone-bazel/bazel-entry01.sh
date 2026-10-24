#!/bin/bash
set -euo pipefail
umask 022
export GOMAXPROCS=4 GOTOOLCHAIN=local XDG_CACHE_HOME=/cache/xdg
cd /src
step=$1
shift
startup=(--batch --install_base=/cache/bazel-install --output_user_root=/cache/bazel-user --host_jvm_args=-Xmx2048m --nosystem_rc --nohome_rc)
common=(--jobs=4 --local_ram_resources=6144 --repository_cache=/cache/repository --disk_cache=/cache/action --color=no --curses=no --show_progress_rate_limit=10)
if [[ "$step" == release ]]; then
  /tools/bazel "${startup[@]}" build "${common[@]}" --build_event_json_file=/out/release.bep.json //debian:gvisor-release-tar
  cp bazel-bin/debian/gvisor.tar.bz2 /out/gvisor-native-clone-amd64.tar.bz2
else
  exec /tools/bazel "${startup[@]}" test "${common[@]}" --test_timeout=300 --nocache_test_results --test_output=all --test_arg=-test.v --build_event_json_file="/out/${step}.bep.json" "$@"
fi
