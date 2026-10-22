#!/usr/bin/env python3
"""Allocate only task-owned loop backing and static PVs in the private cluster."""

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time


SIZE = 40 * 1024 ** 3
NODE = "akcr119-20261022-control-plane"
NODE_ID = "6ea1b30343a521d9f601ae5f6d0f432cf7939f09bf9fe441d05cb3af77b5efa5"
DEVICE = "/dev/akcr119-ceph-osd21"
STORAGE_CLASS = "akcr119-ceph-static"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    args = parser.parse_args()
    task = args.task.resolve(strict=True)
    require(task.name == "akernel-pr119-repro-20261022.XfboxUgq", "wrong task identity")
    require(Path("/sys/module/loop").is_dir(), "loop module must already be loaded")
    require(shutil.disk_usage(task).free > 250 * 1024 ** 3, "less than 250 GiB free")
    output = task / "storage/live21"
    output.mkdir(mode=0o700, exist_ok=False)
    record = {"status": "failed", "task_owned_only": True, "backing_bytes": SIZE,
              "created_unix": time.time(), "commands": []}
    base = [sys.executable, str(task / "cluster/namespace-lab07.py"),
            "run", "--task", str(task), "--"]

    def run(argv, private=False):
        p = subprocess.run(argv, text=True, capture_output=True, timeout=90)
        record["commands"].append({"argv": argv, "rc": p.returncode,
                                   "stdout": "<private>" if private else p.stdout,
                                   "stderr": p.stderr})
        (output / "receipt.json").write_text(json.dumps(record, indent=2) + "\n")
        require(p.returncode == 0, "command failed: " + argv[0] + " " + p.stderr[-1000:])
        return p.stdout

    try:
        inspect = json.loads(run(base + ["podman", "inspect", NODE], private=True))[0]
        require(inspect["Id"] == NODE_ID, "node container identity mismatch")
        require(inspect["Config"]["Labels"].get("io.x-k8s.kind.cluster") == "akcr119-20261022",
                "cluster label mismatch")
        require(inspect["State"]["Running"], "node is not running")
        ready = run(base + ["kubectl", "get", "--raw=/readyz?verbose"])
        require("[+]etcd ok" in ready, "etcd gate not passed")
        backing = output / "ceph-osd40g.img"
        fd = os.open(backing, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        run(["fallocate", "--length", str(SIZE), str(backing)])
        loop = run(["losetup", "--find", "--show", "--direct-io=on", str(backing)]).strip()
        record["loop_device"] = loop
        record["backing_file"] = str(backing)
        (output / "receipt.json").write_text(json.dumps(record, indent=2) + "\n")
        mapping = json.loads(run(["losetup", "--json", "--output", "NAME,BACK-FILE", loop]))
        devices = mapping["loopdevices"]
        require(len(devices) == 1 and Path(devices[0]["back-file"]).resolve() == backing,
                "loop backing identity mismatch")
        device_stat = os.stat(loop)
        require(stat.S_ISBLK(device_stat.st_mode), "allocated path is not a block device")
        major, minor = os.major(device_stat.st_rdev), os.minor(device_stat.st_rdev)
        require(major == 7, "unexpected device major")
        record["device_major_minor"] = [major, minor]
        run(base + ["podman", "exec", NODE, "test", "!", "-e", DEVICE])
        run(base + ["podman", "exec", NODE, "mknod", "-m", "600", DEVICE,
                    "b", str(major), str(minor)])
        size = run(base + ["podman", "exec", NODE, "blockdev", "--getsize64", DEVICE]).strip()
        require(int(size) == SIZE, "node block capacity mismatch")
        monitor = task / "node-data09/control/volumes/akcr119-ceph-mon"
        require(monitor.parent.resolve().is_relative_to(task), "monitor path escaped task")
        monitor.mkdir(mode=0o755, exist_ok=False)
        affinity = {"required": {"nodeSelectorTerms": [{"matchExpressions": [
            {"key": "kubernetes.io/hostname", "operator": "In", "values": [NODE]}]}]}}
        objects = [{"apiVersion": "storage.k8s.io/v1", "kind": "StorageClass",
                    "metadata": {"name": STORAGE_CLASS}, "provisioner": "kubernetes.io/no-provisioner",
                    "volumeBindingMode": "WaitForFirstConsumer", "reclaimPolicy": "Retain"}]
        for name, mode, capacity, path in [
                ("akcr119-ceph-osd21", "Block", "40Gi", DEVICE),
                ("akcr119-ceph-mon21", "Filesystem", "4Gi", "/var/local-path-provisioner/akcr119-ceph-mon")]:
            objects.append({"apiVersion": "v1", "kind": "PersistentVolume",
                            "metadata": {"name": name, "labels": {"akernel.dev/task": "pr119-20261022"}},
                            "spec": {"capacity": {"storage": capacity}, "volumeMode": mode,
                                     "accessModes": ["ReadWriteOnce"], "persistentVolumeReclaimPolicy": "Retain",
                                     "storageClassName": STORAGE_CLASS, "local": {"path": path},
                                     "nodeAffinity": affinity}})
        manifest = {"apiVersion": "v1", "kind": "List", "items": objects}
        path = output / "static-pvs.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        run(base + ["kubectl", "create", "-f", str(path)])
        record["status"] = "task-owned-static-pvs-created"
        record["raw_block_device_bytes_verified"] = int(size)
        record["pv_names"] = [x["metadata"]["name"] for x in objects[1:]]
        record["filesystem_pv_hard_quota"] = False
        record["free_bytes_after"] = shutil.disk_usage(task).free
    finally:
        (output / "receipt.json").write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps({k: v for k, v in record.items() if k != "commands"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
