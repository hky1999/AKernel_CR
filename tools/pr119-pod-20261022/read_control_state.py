#!/usr/bin/env python3
"""Read the existing private ADX control state; never write Redis or create a catalog."""

import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def read_control_state(task):
    task = Path(task).resolve(strict=True)
    base = [sys.executable, str(task / "cluster/namespace-lab07.py"),
            "run", "--task", str(task), "--", "kubectl", "-n", "akernel"]
    result = subprocess.run(base + ["get", "secret", "akernel-adx-redis-auth", "-o", "json"],
                            text=True, capture_output=True, check=True, timeout=40)
    password = base64.b64decode(json.loads(result.stdout)["data"]["password"]).decode()

    def read(*args):
        shell = 'IFS= read -r REDISCLI_AUTH; export REDISCLI_AUTH; exec redis-cli --json "$@"'
        result = subprocess.run(base + ["exec", "-i", "akernel-adx-redis-0", "--",
                                        "sh", "-c", shell, "redis-read-only", *args],
                                input=password + "\n", text=True, capture_output=True,
                                check=True, timeout=40)
        return json.loads(result.stdout)

    keys = read("KEYS", "*control:v1")
    if not isinstance(keys, list) or len(keys) != 1:
        raise RuntimeError("expected exactly one control realm in the private Redis")
    values = read("HGETALL", keys[0])
    if isinstance(values, list):
        values = dict(zip(values[::2], values[1::2]))
    if not isinstance(values, dict):
        raise RuntimeError("unexpected control state representation")
    return keys[0], {key: json.loads(value) for key, value in values.items()}


def safe_summary(record):
    result = record.get("result") or {}
    assignment = record.get("assignment") or {}
    return {"node_id": assignment.get("node_id"),
            "state": result.get("state") if isinstance(result, dict) else None,
            "record_field_names": sorted(record),
            "checkpoint_field_names": [key for key in record
                                       if "checkpoint" in key or "recovery" in key]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--environment")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    task = args.task.resolve(strict=True)
    key, records = read_control_state(task)
    path = (args.output or task / "acceptance/control-state" / (str(time.time_ns()) + ".private.json")).resolve()
    if not path.is_relative_to(task):
        raise RuntimeError("private output must belong to the task")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.environment:
        records = {"environment:" + args.environment: records["environment:" + args.environment]}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"control_hash": key, "records": records}, stream, indent=2)
        stream.write("\n")
    environments = {name: safe_summary(record) for name, record in records.items()
                    if name.startswith("environment:")}
    print(json.dumps({"read_only": True, "record_count": len(records),
                      "environment_summaries": environments, "raw_state_private": True}, indent=2), flush=True)


if __name__ == "__main__":
    main()
