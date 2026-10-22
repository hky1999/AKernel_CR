#!/usr/bin/env python3
"""Record a real remote SDK run without losing its terminal state on SSH detach."""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--auth", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--runtime", choices=("runsc", "firecracker"), required=True)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--memory-bytes", type=int, default=0)
    parser.add_argument("--parameters", action="store_true")
    parser.add_argument("--node-id")
    args = parser.parse_args()
    task = args.task.resolve(strict=True)
    job = args.job.resolve()
    if not job.is_relative_to(task):
        raise RuntimeError("job directory must belong to the task")
    auth = args.auth.resolve(strict=True)
    if not auth.is_relative_to(task):
        raise RuntimeError("auth directory must belong to the task")
    forward = json.loads((auth / "ready.json").read_text())["port_forward"]
    actual = (Path("/proc") / str(forward["pid"]) / "stat").read_text().rsplit(")", 1)[1].split()
    if actual[19] != forward["start_ticks"] or actual[0] == "Z":
        raise RuntimeError("port-forward identity is not live")
    job.mkdir(mode=0o700, parents=True, exist_ok=False)
    start = time.monotonic()
    stat = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    (job / "worker.json").write_text(json.dumps(
        {"pid": os.getpid(), "start_ticks": stat[19], "runtime": args.runtime,
         "rounds": args.rounds, "memory_bytes": args.memory_bytes}, indent=2) + "\n")
    argv = [str(task / "sdk/client/bin/python"), str(task / "acceptance/scripts/acceptance.py"),
            "--output", str(job / "result"), "--probe", str(task / "acceptance/bin/guest-probe"),
            "--runtime", args.runtime, "--rounds", str(args.rounds),
            "--memory-bytes", str(args.memory_bytes)]
    if args.parameters:
        argv.append("--parameters")
    if args.node_id:
        argv += ["--node-id", args.node_id]
    shell = "set -eu; source " + shlex.quote(str(auth / "sdk.env")) + "; exec " + shlex.join(argv)
    command = [sys.executable, str(task / "cluster/namespace-lab07.py"), "run", "--task", str(task),
               "--", "bash", "-c", shell]
    with (job / "stdout.log").open("x") as stdout, (job / "stderr.log").open("x") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        child_stat = (Path("/proc") / str(process.pid) / "stat").read_text().rsplit(")", 1)[1].split()
        (job / "child.json").write_text(json.dumps(
            {"pid": process.pid, "start_ticks": child_stat[19]}, indent=2) + "\n")
        rc = process.wait()
    terminal = {"rc": rc, "elapsed_seconds": time.monotonic() - start,
                "completed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (job / "terminal.json").write_text(json.dumps(terminal, indent=2) + "\n")
    print(json.dumps(terminal), flush=True)
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
