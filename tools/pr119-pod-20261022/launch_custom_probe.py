#!/usr/bin/env python3
"""在已有私有 namespace 内运行 SDK 探针，保留真实进程身份及终态。"""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time


def identity(pid):
    return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task", type=Path, required=True)
    p.add_argument("--auth", type=Path, required=True)
    p.add_argument("--job", type=Path, required=True)
    p.add_argument("--script", type=Path, required=True)
    p.add_argument("--runtime", required=True)
    p.add_argument("--forward-pid", type=int, required=True)
    p.add_argument("--forward-start", required=True)
    p.add_argument("--worker", action="store_true")
    a = p.parse_args()
    task, job, auth, script = (v.resolve() for v in [a.task, a.job, a.auth, a.script])
    job.relative_to(task / "acceptance/runs")
    auth.relative_to(task / "acceptance")
    script.relative_to(task / "acceptance/scripts")
    if identity(a.forward_pid) != a.forward_start:
        raise RuntimeError("port-forward process identity changed")
    command_line = Path(f"/proc/{a.forward_pid}/cmdline").read_bytes()
    if b"port-forward" not in command_line or str(task).encode() not in command_line:
        raise RuntimeError("port-forward does not belong to task")
    if not a.worker:
        job.mkdir(mode=0o700, parents=True, exist_ok=False)
        with (job / "launcher.stdout").open("x") as stdout, (job / "launcher.stderr").open("x") as stderr:
            worker = subprocess.Popen([sys.executable, __file__, *sys.argv[1:], "--worker"],
                                      stdout=stdout, stderr=stderr, start_new_session=True)
        record = {"pid": worker.pid, "start_ticks": identity(worker.pid), "script": script.name,
                  "runtime": a.runtime}
        (job / "worker.json").write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record))
        return
    q = shlex.quote
    shell = ("set -ae; . " + q(str(auth / "sdk.env")) + "; set +a; exec " +
             " ".join(q(x) for x in [str(task / "sdk/client/bin/python"), str(script),
                                       "--task", str(task), "--runtime", a.runtime,
                                       "--output", str(job / "result")]))
    command = ["python3", str(task / "cluster/namespace-lab07.py"), "run", "--task", str(task),
               "--", "bash", "-c", shell]
    started = time.monotonic()
    with (job / "stdout.log").open("x") as stdout, (job / "stderr.log").open("x") as stderr:
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        (job / "child.json").write_text(json.dumps({"pid": child.pid, "start_ticks": identity(child.pid)}, indent=2) + "\n")
        rc = child.wait()
    record = {"rc": rc, "elapsed_seconds": time.monotonic() - started,
              "completed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    temporary = job / ("terminal." + str(os.getpid()) + ".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.replace(job / "terminal.json")


if __name__ == "__main__":
    main()
