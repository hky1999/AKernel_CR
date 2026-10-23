#!/usr/bin/env bash
set -eu
umask 077
Q=/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp/round-365f797-20261023.clPWh2h0
D="$Q/tap-checksum-fix"
OUT="$D/storage/sdk-full02"
mkdir -m 700 "$OUT"
trap 'rc=$?; printf "{\"rc\":%s}\n" "$rc" > "$OUT/terminal.json"' EXIT
source "$Q/acceptance/auth-shared-tapfix-direct01/sdk.env"
export AKERNEL_RUN_INTEGRATION=1 PYTHONPATH="$Q/source/AKernel/sdk/python"
export HOME="$OUT/home"
mkdir -m 700 "$HOME"
AKERNEL_TEST_IMAGE=$("$Q/sdk/client/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["image_ref"])' "$D/oci-test-image.json")
export AKERNEL_TEST_IMAGE AKERNEL_TEST_HTTP_IMAGE="$AKERNEL_TEST_IMAGE"
cd "$Q/source/AKernel"
for runtime in firecracker runsc; do
 export AKERNEL_TEST_RUNTIME="$runtime"
 for suite in integration e2e/standalone; do
  name="$runtime-$(basename "$suite")"
  if timeout 900s "$Q/sdk/client/bin/python" -m unittest discover -s "sdk/python/tests/$suite" -t sdk/python -v > "$OUT/$name.stdout" 2> "$OUT/$name.stderr"; then rc=0; else rc=$?; fi
  printf '{"runtime":"%s","suite":"%s","rc":%s}\n' "$runtime" "$suite" "$rc" >> "$OUT/steps.jsonl"
  test "$rc" -eq 0
 done
done
