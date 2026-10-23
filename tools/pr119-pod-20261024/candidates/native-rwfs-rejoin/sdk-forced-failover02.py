#!/usr/bin/env python3
"""Public AKernel SDK failover; distinct from explicit same-node reload."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from acceptance import completed, same_state
from akernel_sdk import Sandbox
from read_control_state import read_control_state


NODE_IDS = {
    "akcr119-20261022-worker": "c94000a9e103f344bd40e2fd1cce2bb4ee113766beadc63ae5e5f8c7b6a5b550",
    "akcr119-20261022-worker2": "31814694e9fd4463d194bb5150fc2dec052131af18d726ca330e822345c0f017",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--runtime", choices=["runsc", "firecracker"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    task, output = args.task.resolve(), args.output.resolve()
    output.relative_to(task / "acceptance/runs")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    events = (output / "events.jsonl").open("x", buffering=1)

    def emit(name, **fields):
        events.write(json.dumps({"event": name, "unix_ns": time.time_ns(), **fields}) + "\n")

    def run(*command, timeout=60):
        answer = subprocess.run(
            ["python3", str(task / "cluster/namespace-lab07.py"), "run", "--task", str(task), "--", *command],
            text=True, capture_output=True, timeout=timeout,
        )
        if answer.returncode:
            raise RuntimeError({"command": command, "rc": answer.returncode, "stderr": answer.stderr[-2000:]})
        return answer.stdout

    def container(node):
        item = json.loads(run("podman", "inspect", node))[0]
        if item["Id"] != NODE_IDS[node] or item["Name"].lstrip("/") != node:
            raise AssertionError("task container identity changed")
        return item

    def records():
        return read_control_state(task)[1]

    def record_rgw(phase):
        try:
            value = json.loads(run("kubectl", "-n", "akernel-pr119-storage", "exec", "deployment/rook-ceph-rgw-checkpoints-a", "-c", "rgw", "--", "python3", "-c", 'import pathlib,subprocess,json,time\ns=list(pathlib.Path("/run/ceph").glob("ceph-client.rgw.checkpoints.a.*.asok"))\nassert len(s)==1\np=subprocess.run(["ceph","--admin-daemon",str(s[0]),"perf","dump"],capture_output=True,text=True,timeout=15)\np.check_returncode()\nv=json.loads(p.stdout)\nprint(json.dumps({"rgw_instance":s[0].name,"at_unix_ns":time.time_ns(),"rgw":{k:v["rgw"][k] for k in ["req","failed_req"]},"rgw_op":{k:x for k,x in v["rgw_op"].items() if isinstance(x,(int,float))}}))', timeout=60))
            (output / (phase + ".rgw.private.json")).write_text(json.dumps(value, indent=2))
            emit("rgw_counters_recorded", phase=phase)
        except Exception as error:
            emit("rgw_counters_unavailable", phase=phase, error_type=type(error).__name__, error=str(error))

    sandbox, source = None, None
    stopped, passed = False, False
    disk_rwfs = os.environ.get("PR119_TEST_DISK_RWFS") == "1"
    disk_path = "/pr119-disk-rwfs-state"
    disk_before = "a" * (1 << 20)
    try:
        sandbox = Sandbox(runtime=args.runtime, image=os.environ.get("AKERNEL_TEST_IMAGE") or None, cpu=1000, memory=2048, storage_mb=1024,
                          idle_timeout=900, failover=True)
        identity, facades = sandbox.id, (sandbox.files, sandbox.commands, sandbox.pty)
        emit("created", sandbox_id=identity, runtime=args.runtime, hard_node_pin=False,
             disk_rwfs_bytes=len(disk_before) if disk_rwfs else 0)

        def command(text):
            value = sandbox.commands.run(text, timeout=180)
            if value.exit_code:
                raise AssertionError({"command": text, "exit_code": value.exit_code, "stderr": value.stderr})
            return value.stdout

        def probe(mode):
            return json.loads(command("/tmp/pr119-failover-probe " + mode))

        sandbox.files.write("/tmp/pr119-failover-probe", (task / "acceptance/bin/guest-probe").read_bytes())
        command("chmod 700 /tmp/pr119-failover-probe")
        sandbox.commands.run("/tmp/pr119-failover-probe hold --bytes 536870912 >/tmp/pr119-failover-hold.log 2>&1", background=True)
        deadline = time.monotonic() + 120
        while True:
            try:
                response = probe("state")
                if response["http_status"] != 200:
                    raise AssertionError(response)
                before = json.loads(response["body"])
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.5)
        emit("memory_ready", **before)
        if disk_rwfs:
            sandbox.files.write(disk_path, disk_before)
            if sandbox.files.read(disk_path) != disk_before:
                raise AssertionError("root filesystem payload did not persist before checkpoint")
            mounts = command("cat /proc/mounts")
            emit("root_filesystem_payload_ready", path=disk_path, bytes=len(disk_before),
                 root_and_tmp_mounts=[line for line in mounts.splitlines()
                                      if len(line.split()) > 1 and line.split()[1] in ["/", "/tmp"]])
        sandbox.files.write("/tmp/pr119-failover-file", "checkpoint-before")
        record_rgw("capture-begin")
        checkpoint = probe("checkpoint --socket /run/akernel/execd.sock --timeout 150")
        emit("checkpoint_reply", **checkpoint)
        completed(checkpoint)
        record_rgw("capture-end")
        state = records()
        entry = state["environment:" + identity]
        source = entry["assignment"]["node_id"]
        point = entry["result"]["checkpoint"]
        if source not in NODE_IDS or point["artifact"]["storage"] != "akernel-checkpoints":
            raise AssertionError("checkpoint is not committed to the configured shared storage")
        source_pods = json.loads(run("kubectl", "-n", "akernel", "get", "pods", "-o", "json"))["items"]
        source_pods = [p for p in source_pods if p["metadata"]["name"].startswith("akernel-node-") and p["spec"].get("nodeName")==source and not p["metadata"].get("deletionTimestamp")]
        if len(source_pods)!=1:raise AssertionError("source Pod identity ambiguous before abrupt stop")
        source_pod_uid=source_pods[0]["metadata"]["uid"]
        owner_code="import pathlib,json;rows=[]\nfor p in pathlib.Path('/home/akernel/sandboxd/root/containers').glob('*/config.json'):\n try:a=json.loads(p.read_text()).get('annotations',{})\n except(OSError,ValueError):continue\n if a.get('adx.environment_id')=="+repr(identity)+" and a.get('adx.runtime_id')=="+repr(entry["result"]["runtime"]["id"])+":rows.append(p.parent.name)\nassert len(rows)==1\nprint(json.dumps(rows[0]))"
        source_sandboxd_id=json.loads(run("kubectl","-n","akernel","exec",source_pods[0]["metadata"]["name"],"--","python3","-c",owner_code))
        (output/"source-owner.private.json").write_text(json.dumps({"sandboxd_id":source_sandboxd_id,"pod_uid":source_pod_uid,"node":source}))
        emit("source_owner_recorded",sandboxd_id_sha256=hashlib.sha256(source_sandboxd_id.encode()).hexdigest(),fault_mode="podman-stop-time-zero")
        old_session = state["node:" + source]["session"]["id"]
        for key, value in state.items():
            if key.startswith("environment:") and key != "environment:" + identity:
                if value.get("assignment", {}).get("node_id") == source and value.get("result", {}).get("state") not in ["Failed", "Deleted"]:
                    raise AssertionError("source has another live task environment")
        emit("shared_checkpoint_committed", source_node=source, point=point)
        sandbox.files.write("/tmp/pr119-failover-file", "after-checkpoint-must-disappear")
        if disk_rwfs:
            sandbox.files.write(disk_path, "b" * len(disk_before))
            if sandbox.files.read(disk_path) != "b" * len(disk_before):
                raise AssertionError("root filesystem mutation did not occur")
        changed = probe("mutate")
        if changed["http_status"] != 200 or json.loads(changed["body"])["sha256"] == before["sha256"]:
            raise AssertionError("memory mutation did not occur")
        if not sandbox.is_running():
            raise AssertionError("checkpoint stopped source")
        container(source)
        fault_ns, fault_wall = time.monotonic_ns(), time.time()
        stopped = True
        run("podman", "stop", "--time=0", NODE_IDS[source])
        if container(source)["State"]["Running"]:
            raise AssertionError("source did not stop")
        emit("source_stopped", node=source)
        deadline = time.monotonic() + 240
        while True:
            node = records().get("node:" + source)
            if node is None or not node.get("session", {}).get("routable", False):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Coordinator did not withdraw source")
            time.sleep(1)
        record_rgw("restore-begin")
        read_ns = time.monotonic_ns()
        errors = []
        deadline = time.monotonic() + 180
        while True:
            try:
                if sandbox.files.read("/tmp/pr119-failover-file") != "checkpoint-before":
                    raise AssertionError("private filesystem rollback differs")
                break
            except AssertionError:
                raise
            except Exception as error:
                errors.append(type(error).__name__)
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.5)
        file_ms = (time.monotonic_ns() - read_ns) / 1e6
        if disk_rwfs:
            restored_disk = sandbox.files.read(disk_path)
            if restored_disk != disk_before:
                raise AssertionError("root filesystem payload did not roll back")
            sandbox.files.write("/pr119-disk-rwfs-target-write", "writable-on-target")
            if sandbox.files.read("/pr119-disk-rwfs-target-write") != "writable-on-target":
                raise AssertionError("target root filesystem write failed")
            emit("disk_rwfs_verified", path=disk_path, bytes=len(restored_disk),
                 sha256=hashlib.sha256(restored_disk.encode()).hexdigest(),
                 read_trigger_until_disk_verified_ms=(time.monotonic_ns() - read_ns) / 1e6)
        reply = probe("state")
        if reply["http_status"] != 200:
            raise AssertionError(reply)
        same_state(before, json.loads(reply["body"]))
        full_ms = (time.monotonic_ns() - read_ns) / 1e6
        current = records()["environment:" + identity]
        target = current["assignment"]["node_id"]
        if target not in NODE_IDS or target == source or current["result"]["state"] != "Running":
            raise AssertionError("environment did not move to another healthy task node")
        if sandbox.id != identity or any(x is not y for x, y in zip(facades, (sandbox.files, sandbox.commands, sandbox.pty))):
            raise AssertionError("public SDK identity or facades changed")
        if container(source)["State"]["Running"]:
            raise AssertionError("source restarted before full validation")
        sandbox.files.write("/tmp/pr119-failover-target-write", "writable-on-target")
        if sandbox.files.read("/tmp/pr119-failover-target-write") != "writable-on-target":
            raise AssertionError("target write failed")
        emit("public_sdk_failover_passed", source_node=source, target_node=target,
             checkpoint_until_http_completed_ms=checkpoint["elapsed_ms"],
             read_trigger_until_first_verified_file_ms=file_ms,
             read_trigger_until_full_memory_verified_ms=full_ms,
             fault_until_full_memory_verified_ms=(time.monotonic_ns() - fault_ns)/1e6,
             memory_bytes=before["memory_bytes"], sha256=before["sha256"],
             explicit_reload_called=False, source_offline=True,
             retryable_read_error_types=errors, recovery_operation=current["result"].get("last_operation"))
        record_rgw("restore-end-after-full-state-verification")
        pods = json.loads(run("kubectl", "-n", "akernel", "get", "pods", "-o", "json"))["items"]
        targets = [p for p in pods if p["metadata"]["name"].startswith("akernel-node-") and p["spec"].get("nodeName") == target]
        if len(targets) != 1:
            raise AssertionError("target storage observation Pod is not unique")
        processes = json.loads(run("kubectl", "-n", "akernel", "exec", targets[0]["metadata"]["name"], "--", "python3", "-c", 'import json,os,pathlib,subprocess\nprefixes=("/home/akernel/","/mnt/akernel-shared/","/memfd:")\nresult=[]\nfor item in pathlib.Path("/proc").iterdir():\n if not item.name.isdigit():continue\n try:\n  args=(item/"cmdline").read_bytes().split(b"\\0")\n  executable=os.path.basename(os.fsdecode(args[0]))\n  if executable not in ["firecracker","runsc","runsc-sandbox","runsc-gofer"]:continue\n  fds=[];parents=set()\n  for fd in (item/"fd").iterdir():\n   try:value=os.readlink(fd)\n   except OSError:continue\n   if value.startswith(prefixes):\n    fds.append({"fd":int(fd.name),"path":value})\n    if not value.startswith("/memfd:"):parents.add(str(pathlib.Path(value.removesuffix(" (deleted)")).parent))\n  maps=[line for line in (item/"maps").read_text().splitlines() if any(p in line for p in prefixes)]\n  mounts=[]\n  for parent in sorted(parents):\n   p=subprocess.run(["findmnt","-n","-T",parent,"-o","FSTYPE,SOURCE,TARGET"],text=True,capture_output=True,timeout=5)\n   mounts.append({"directory":parent,"rc":p.returncode,"findmnt":p.stdout.strip()})\n  result.append({"pid":int(item.name),"executable":executable,"fds":fds,"maps":maps,"mounts":mounts})\n except (FileNotFoundError,ProcessLookupError,PermissionError):continue\nprint(json.dumps(result))', timeout=90))
        if not processes:
            raise AssertionError("target runtime disappeared before storage observation")
        (output / "target-storage.private.json").write_text(json.dumps({"read_only": True, "target_node": target, "processes": processes}, indent=2))
        emit("target_storage_observed", process_count=len(processes), read_only=True)
        passed = True
    except BaseException as error:
        emit("acceptance_failed", error_type=type(error).__name__, error=str(error),
             sandbox_preserved=None if sandbox is None else sandbox.id)
        raise
    finally:
        original_error = sys.exc_info()[0] is not None
        healthy = not stopped
        if stopped:
            try:
                container(source)
                run("podman", "start", NODE_IDS[source], timeout=90)
                emit("source_restarted", node=source)
                deadline = time.monotonic() + 240
                while True:
                    node = records().get("node:" + source, {})
                    if node.get("session", {}).get("routable") and node["session"]["id"] != old_session and node.get("node", {}).get("available") and node.get("scheduling_paused") is False and {"firecracker", "runsc"}.issubset(node.get("node", {}).get("runtime_classes", [])) and node.get("node", {}).get("capacity", {}).get("cpu_millis", 0) >= 1000 and node.get("node", {}).get("capacity", {}).get("memory_bytes", 0) >= 2*(1<<30):
                        pods = json.loads(run("kubectl", "-n", "akernel", "get", "pods", "-o", "json"))["items"]
                        own = [p for p in pods if p["metadata"]["name"].startswith("akernel-node-") and p["spec"].get("nodeName") == source]
                        if len(own) == 1:
                            statuses = own[0]["status"].get("containerStatuses", [])
                            if statuses and all(s.get("ready") and s.get("state", {}).get("running") for s in statuses):
                                started = datetime.datetime.fromisoformat(statuses[0]["state"]["running"]["startedAt"].replace("Z", "+00:00")).timestamp()
                                if started >= fault_wall:
                                    run("kubectl", "-n", "akernel", "exec", own[0]["metadata"]["name"], "--", "sh", "-ec", "systemctl is-active sandboxd adx; test $(findmnt -n -T /mnt/akernel-shared -o FSTYPE) = fuse.juicefs; test $(findmnt -n -T /home/akernel/filestore -o FSTYPE) = xfs")
                                    healthy = True
                                    break
                    if time.monotonic() >= deadline:
                        raise TimeoutError("restarted source did not pass fresh service and mount checks")
                    time.sleep(2)
                pods=json.loads(run("kubectl","-n","akernel","get","pods","-o","json"))["items"]
                own=[p for p in pods if p["metadata"]["name"].startswith("akernel-node-")and p["spec"].get("nodeName")==source and not p["metadata"].get("deletionTimestamp")]
                if len(own)!=1 or own[0]["metadata"]["uid"]!=source_pod_uid:raise AssertionError("Pod was replaced; cannot prove same-Pod resource recovery")
                code="import pathlib,json;sid="+repr(source_sandboxd_id)+";p=pathlib.Path('/home/akernel/logs/sandboxd/sandboxd.log')\nwith p.open('rb')as f:\n f.seek(max(0,p.stat().st_size-8*1024*1024));text=f.read().decode(errors='replace')\nassert 'retired stopped sandbox '+sid+' network lease before pool recovery'in text\np=pathlib.Path('/home/akernel/sandboxd/root/containers')/sid/'config.json'\nif p.exists():\n a=json.loads(p.read_text()).get('annotations',{});assert not a.get('sandbox.akernel.dev/resource-interface')and not a.get('sandbox.akernel.dev/retired-interface')\nprint(json.dumps({'retired_by_product':True,'same_pod_uid':True,'old_bundle_removed':not p.exists(),'manual_pool_reset':False}))"
                digest = run("kubectl", "-n", "akernel", "exec", own[0]["metadata"]["name"], "--", "sha256sum", "/usr/local/bin/sandboxd").split()[0]
                if digest != "debbf268d1b1a8d4a07b9ac02be7084c3fa53c7cf794f0b1887ec65f7ace313b":
                    raise AssertionError("source restart did not consume fixed candidate")
                proof=json.loads(run("kubectl","-n","akernel","exec",own[0]["metadata"]["name"],"--","python3","-c",code))
                (output/"retirement-proof.json").write_text(json.dumps(proof,indent=2))
                emit("dead_owner_retirement_proved",**proof)
                emit("source_healthy_again", node=source)
            except BaseException as error:
                emit("source_health_check_failed", error_type=type(error).__name__, error=str(error))
                if not original_error:
                    raise
        if passed and healthy and sandbox is not None:
            if disk_rwfs:
                if sandbox.files.read(disk_path) != disk_before:
                    raise AssertionError("target disk payload changed after source rejoined")
                same_state(before, json.loads(probe("state")["body"]))
                final = records()["environment:" + sandbox.id]
                if final["result"]["runtime"]["id"] != current["result"]["runtime"]["id"]:
                    raise AssertionError("target runtime changed when original source rejoined")
                emit("target_survived_source_rejoin", target_node=target,
                     runtime_id=final["result"]["runtime"]["id"])
            sandbox.kill()
            emit("sandbox_deleted", sandbox_id=sandbox.id)
        events.close()


if __name__ == "__main__":
    main()
