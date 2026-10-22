#!/usr/bin/env python3
"""Retry the explicitly failed task format Job without replacing any storage data."""

import argparse
import json
import os
from pathlib import Path
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
    output = task / "storage/retry35"
    output.mkdir(mode=0o700, exist_ok=False)
    stat = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    (output / "worker.json").write_text(json.dumps(
        {"pid": os.getpid(), "start_ticks": stat[19]}, indent=2) + "\n")
    base = [sys.executable, str(task / "cluster/namespace-lab07.py"),
            "run", "--task", str(task), "--"]
    namespace = "akernel-pr119-storage"
    job_name = "akcr119-juicefs-format-75a22b4f"
    steps = []
    started = time.monotonic()
    rc = 1

    def run(name, argv, data=None, timeout=90):
        p = subprocess.run(base + argv, input=data, text=True, capture_output=True, timeout=timeout)
        (output / (name + ".json")).write_text(json.dumps(
            {"rc": p.returncode, "stdout": p.stdout, "stderr": p.stderr}, indent=2) + "\n")
        steps.append({"step": name, "rc": p.returncode})
        print(json.dumps(steps[-1]), flush=True)
        if p.returncode:
            raise RuntimeError(name + " failed; preserve current task resources")
        return p.stdout

    try:
        run("redis-client-path", ["kubectl", "-n", "akernel", "exec", "akernel-adx-redis-0", "--",
                                  "bash", "-ec", "test -x /opt/adx/current/bin/redis-cli; "
                                  "if ! command -v redis-cli >/dev/null; then "
                                  "test ! -e /usr/local/bin/redis-cli; test ! -L /usr/local/bin/redis-cli; "
                                  "ln -s /opt/adx/current/bin/redis-cli /usr/local/bin/redis-cli; fi; "
                                  "redis-cli --version"])
        bucket = json.loads(run("bucket-before", ["kubectl", "-n", namespace, "get", "obc",
                                                   "akcr119-juicefs-bucket", "-o", "json"]))
        if bucket.get("status", {}).get("phase") != "Bound":
            raise RuntimeError("bucket not bound; do not recreate format Job")
        job = json.loads(run("failed-format-before", ["kubectl", "-n", namespace, "get", "job",
                                                       job_name, "-o", "json"]))
        status = job.get("status", {})
        if status.get("active", 0) or not any(c["type"] == "Failed" and c["status"] == "True"
                                               for c in status.get("conditions", [])):
            raise RuntimeError("format Job is not terminal failed; no deletion")
        body = {"apiVersion": "v1", "kind": "DeleteOptions",
                "preconditions": {"uid": job["metadata"]["uid"]}, "propagationPolicy": "Foreground"}
        run("delete-failed-format", ["kubectl", "delete", "--raw",
                                      "/apis/batch/v1/namespaces/" + namespace + "/jobs/" + job_name,
                                      "-f", "-"], data=json.dumps(body))
        run("format-deleted", ["kubectl", "-n", namespace, "wait", "--for=delete",
                                "job/" + job_name, "--timeout=60s"], timeout=80)
        run("juicefs-upgrade", ["helm", "upgrade", "--install", "akcr119-juicefs",
                                 str(task / "source/AKernel/deploy/shared-storage/charts/juicefs"),
                                 "--namespace", namespace,
                                 "-f", str(task / "storage/preflight16/juicefs-values.yaml"),
                                 "--post-renderer", str(task / "storage/storage_placement.py"),
                                 "--wait", "--wait-for-jobs", "--timeout=8m"], timeout=540)
        rc = 0
    finally:
        record = {"rc": rc, "steps": steps, "elapsed_seconds": time.monotonic() - started,
                  "completed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        (output / "terminal.json").write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
