#!/usr/bin/env python3
"""Read-only FD/maps observation after an independently verified SDK failover."""
import argparse
import json
from pathlib import Path
import subprocess
import time


PROBE = r'''
import json,os,pathlib,subprocess
prefixes=("/home/akernel/filestore/","/home/akernel/adx/","/home/akernel/sandboxd/root/containers/","/mnt/akernel-shared/","/memfd:")
result=[]
for item in pathlib.Path('/proc').iterdir():
    if not item.name.isdigit():continue
    try:
        args=(item/'cmdline').read_bytes().split(b'\0')
        executable=os.path.basename(os.fsdecode(args[0]))
        if executable not in ['firecracker','runsc-sandbox','runsc-gofer']:continue
        fds=[];parents=set()
        for fd in (item/'fd').iterdir():
            try:value=os.readlink(fd)
            except OSError:continue
            if value.startswith(prefixes):
                fds.append({'fd':int(fd.name),'path':value})
                if not value.startswith('/memfd:'):parents.add(str(pathlib.Path(value.removesuffix(' (deleted)')).parent))
        maps=[line for line in (item/'maps').read_text().splitlines() if any(p in line for p in prefixes)]
        mounts=[]
        for parent in sorted(parents):
            r=subprocess.run(['findmnt','-n','-T',parent,'-o','FSTYPE,SOURCE,TARGET'],capture_output=True,text=True,timeout=5)
            mounts.append({'directory':parent,'rc':r.returncode,'findmnt':r.stdout.strip()})
        result.append({'pid':int(item.name),'executable':executable,'fds':fds,'maps':maps,'mounts':mounts})
    except (FileNotFoundError,ProcessLookupError,PermissionError):continue
print(json.dumps(result))
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task", type=Path, required=True)
    p.add_argument("--job", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    task, job, output = (v.resolve() for v in [args.task, args.job, args.output])
    job.relative_to(task / "acceptance/runs")
    output.relative_to(task / "acceptance")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    base = ["python3", str(task / "cluster/namespace-lab07.py"), "run", "--task", str(task), "--", "kubectl"]
    deadline = time.monotonic() + 360
    receipt = {"status": "not-captured", "read_only": True}
    rc = 1
    try:
        while True:
            event_file = job / "result/events.jsonl"
            events = []
            if event_file.exists():
                for line in event_file.read_text().splitlines():
                    try:events.append(json.loads(line))
                    except json.JSONDecodeError:pass
            passed = next((e for e in events if e["event"] == "public_sdk_failover_passed"), None)
            if passed is not None:
                result = subprocess.run(base + ["-n", "akernel", "get", "pods", "-o", "json"], capture_output=True, text=True, timeout=30)
                result.check_returncode()
                pods = [p for p in json.loads(result.stdout)["items"] if p["metadata"]["name"].startswith("akernel-node-") and p["spec"].get("nodeName") == passed["target_node"]]
                if len(pods) != 1:
                    raise AssertionError("target node Pod is not unique")
                observed = subprocess.run(base + ["-n", "akernel", "exec", pods[0]["metadata"]["name"], "--", "python3", "-c", PROBE], capture_output=True, text=True, timeout=40)
                observed.check_returncode()
                processes = json.loads(observed.stdout)
                if not processes:
                    raise AssertionError("runtime exited before observation")
                receipt = {"status": "captured", "read_only": True,
                           "target_node": passed["target_node"], "processes": processes,
                           "observed_unix_ns": time.time_ns()}
                rc = 0
                break
            if (job / "terminal.json").exists():
                raise RuntimeError("SDK job ended without a passing failover event")
            if time.monotonic() >= deadline:
                raise TimeoutError("SDK failover event was not observed before deadline")
            time.sleep(1)
    except BaseException as error:
        receipt.update(error_type=type(error).__name__, error=str(error))
        raise
    finally:
        receipt["rc"] = rc
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
