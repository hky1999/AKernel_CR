#!/usr/bin/env python3
"""Install only the private PR119 Rook/JuiceFS stack and record every real exit."""

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    args = parser.parse_args()
    task = args.task.resolve(strict=True)
    if task.name != "akernel-pr119-repro-20261022.XfboxUgq":
        raise RuntimeError("wrong task identity")
    for name in ("fc-five21", "fc-memory21"):
        job = task / "acceptance/runs" / name
        terminal = json.loads((job / "terminal.json").read_text())
        events = [json.loads(line) for line in (job / "result/events.jsonl").read_text().splitlines()]
        if terminal["rc"] != 0 or not any(e["event"] == "sandbox_deleted" for e in events):
            raise RuntimeError("local SDK run has not completed and cleaned up: " + name)
    output = task / "storage/install22"
    output.mkdir(mode=0o700, exist_ok=False)
    own_stat = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    (output / "worker.json").write_text(json.dumps(
        {"pid": os.getpid(), "start_ticks": own_stat[19]}, indent=2) + "\n")
    base = [sys.executable, str(task / "cluster/namespace-lab07.py"),
            "run", "--task", str(task), "--"]
    namespace = "akernel-pr119-storage"
    steps = []
    started = time.monotonic()
    rc = 1

    def run(name, argv, data=None, timeout=120):
        with (output / (name + ".stdout")).open("x") as stdout, \
                (output / (name + ".stderr")).open("x") as stderr:
            result = subprocess.run(base + argv, input=data, text=True,
                                    stdout=stdout, stderr=stderr, timeout=timeout)
        steps.append({"step": name, "rc": result.returncode})
        (output / "steps.json").write_text(json.dumps(steps, indent=2) + "\n")
        print(json.dumps(steps[-1]), flush=True)
        if result.returncode:
            raise RuntimeError(name + " failed; retain task state and private logs")

    try:
        run("api-ready", ["kubectl", "get", "--raw=/readyz?verbose"])
        run("rook-install", ["helm", "upgrade", "--install", "rook-ceph",
                             str(task / "storage/preflight15/rook-ceph-1.21.0.tgz"),
                             "--namespace", namespace, "--create-namespace",
                             "-f", str(task / "storage/preflight16/rook-values.yaml"),
                             "--wait", "--timeout=8m"], timeout=540)
        secret = {"apiVersion": "v1", "kind": "Secret",
                  "metadata": {"name": "akcr119-postgres", "namespace": namespace,
                               "labels": {"akernel.dev/task": "pr119-20261022"}},
                  "type": "Opaque", "data": {
                      "password": base64.b64encode(secrets.token_hex(32).encode()).decode()}}
        fd = os.open(output / "postgres-secret.private.json",
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(json.dumps(secret) + "\n")
        run("postgres-secret", ["kubectl", "create", "-f", "-"], data=json.dumps(secret))
        renderer = task / "storage/storage_placement.py"
        renderer.chmod(0o700)
        run("juicefs-install", ["helm", "upgrade", "--install", "akcr119-juicefs",
                                str(task / "source/AKernel/deploy/shared-storage/charts/juicefs"),
                                "--namespace", namespace,
                                "-f", str(task / "storage/preflight16/juicefs-values.yaml"),
                                "--post-renderer", str(renderer),
                                "--wait", "--wait-for-jobs", "--timeout=12m"], timeout=780)
        run("storage-pods", ["kubectl", "-n", namespace, "get", "pods", "-o", "wide"])
        run("storage-ceph", ["kubectl", "-n", namespace, "get", "cephcluster", "rook-ceph", "-o", "json"])
        rc = 0
    finally:
        terminal = {"rc": rc, "steps": steps, "elapsed_seconds": time.monotonic() - started,
                    "completed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        (output / "terminal.json").write_text(json.dumps(terminal, indent=2) + "\n")
        print(json.dumps(terminal), flush=True)


if __name__ == "__main__":
    main()
