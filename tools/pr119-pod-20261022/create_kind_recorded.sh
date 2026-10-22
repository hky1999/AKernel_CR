#!/usr/bin/env bash
# Run remotely under nohup/setsid. Retain actual terminal status across SSH loss.
set -u
umask 077
TASK="$1"
RUN="$2"
mkdir -m 700 "$RUN/create"
python3 - "$BASHPID" <<'PY' > "$RUN/create/worker.json"
import json, os, sys, time
from pathlib import Path
pid = int(sys.argv[1])
stat = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
print(json.dumps({"pid": pid, "start_ticks": stat[19], "started_unix": time.time()}))
PY
python3 "$TASK/cluster/namespace-lab07.py" run --task "$TASK" -- \
  kind create cluster --name akcr119-20261022 \
  --config "$RUN/config.yaml" \
  --image docker.io/kindest/node:v1.35.8@sha256:07b2536e30b803ed61d1677a79df6115f798ce64c80f9e22f6ed45afd09323c0 \
  --retain --wait 0s --kubeconfig "$TASK/cluster/lab07/kubeconfig" \
  > "$RUN/create/stdout.log" 2> "$RUN/create/stderr.log"
rc=$?
python3 - "$rc" <<'PY' > "$RUN/create/terminal.json"
import json, sys, time
print(json.dumps({"returncode": int(sys.argv[1]), "finished_unix": time.time(),
                  "scope": "Kind bootstrap only; CNI and SDK acceptance not implied"}))
PY
exit "$rc"

