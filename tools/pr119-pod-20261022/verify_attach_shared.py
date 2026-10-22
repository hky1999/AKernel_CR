#!/usr/bin/env python3
"""Verify actual shared mounts and durability settings before attaching private ADX."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--attach", action="store_true")
    args = parser.parse_args()
    task = args.task.resolve(strict=True)
    if task.name != "akernel-pr119-repro-20261022.XfboxUgq":
        raise RuntimeError("wrong task identity")
    output = task / "storage/verify36"
    output.mkdir(mode=0o700, exist_ok=False)
    base = [sys.executable, str(task / "cluster/namespace-lab07.py"),
            "run", "--task", str(task), "--"]
    ns = "akernel-pr119-storage"
    receipt = {"status": "failed", "attached_to_adx": False, "shared_sdk_accepted": False}

    def run(name, command, timeout=90):
        result = subprocess.run(base + command, capture_output=True, text=True, timeout=timeout)
        (output / (name + ".private.json")).write_text(json.dumps(
            {"rc": result.returncode, "stdout": result.stdout, "stderr": result.stderr}, indent=2) + "\n")
        print(json.dumps({"step": name, "rc": result.returncode}), flush=True)
        if result.returncode:
            raise RuntimeError(name + " failed; retain private diagnostics")
        return result.stdout

    try:
        pods = json.loads(run("clients", ["kubectl", "-n", ns, "get", "pods",
                                           "-l", "app=akcr119-juicefs-client", "-o", "json"]))["items"]
        if len(pods) != 3 or not all(any(c["type"] == "Ready" and c["status"] == "True"
                                         for c in p["status"].get("conditions", [])) for p in pods):
            raise RuntimeError("three independent JuiceFS clients are not Ready")
        mounts = []
        for node in ("akcr119-20261022-control-plane", "akcr119-20261022-worker", "akcr119-20261022-worker2"):
            data = json.loads(run("mount-" + node, ["podman", "exec", node, "findmnt", "--json",
                                                       "--target", "/srv/akernel-shared",
                                                       "--output", "TARGET,SOURCE,FSTYPE"]))
            if not any(f["target"] == "/srv/akernel-shared" and f["fstype"] == "fuse.juicefs"
                       and f["source"] == "JuiceFS:akernel-pr119-checkpoints"
                       for f in data.get("filesystems", [])):
                raise RuntimeError("plain directory or wrong mount on " + node)
            mounts.append(node)
        settings = run("postgres-durability", ["kubectl", "-n", ns, "exec",
                                                 "akcr119-juicefs-postgres-0", "--", "psql",
                                                 "-U", "juicefs", "-d", "juicefs", "-Atc",
                                                 "SHOW fsync; SHOW synchronous_commit; SHOW full_page_writes;"])
        if settings.split() != ["on", "on", "on"]:
            raise RuntimeError("PostgreSQL persistence settings not enabled")
        pod_names = [p["metadata"]["name"] for p in pods]
        version = run("juicefs-version", ["kubectl", "-n", ns, "exec", pod_names[0],
                                           "-c", "juicefs", "--", "juicefs", "version"]).strip()
        if "1.4.1" not in version:
            raise RuntimeError("unexpected JuiceFS version")
        raw = run("juicefs-status", ["kubectl", "-n", ns, "exec", pod_names[0], "-c", "juicefs",
                                     "--", "sh", "-ec", 'juicefs --quiet --no-color status "$META_URL"'])
        status = json.loads(raw)
        setting = status["Setting"]
        if setting["Name"] != "akernel-pr119-checkpoints" or setting["BlockSize"] != 1024 or setting["TrashDays"] != 0:
            raise RuntimeError("unexpected JuiceFS volume configuration")
        path = "/shared/pr119-verify36/check.bin"
        hashes = []
        for index, name in enumerate(pod_names):
            command = ["kubectl", "-n", ns, "exec", name, "-c", "juicefs", "--"]
            if index == 0:
                text = run("shared-write-fsync", command + ["sh", "-ec",
                           "mkdir /shared/pr119-verify36; dd if=/dev/urandom of=" + path
                           + " bs=4096 count=1 conv=fsync 2>/dev/null; sha256sum " + path])
            else:
                text = run("shared-read-" + str(index), command + ["sha256sum", path])
            hashes.append(text.split()[0])
        if len(set(hashes)) != 1 or len(hashes[0]) != 64:
            raise RuntimeError("cross-client data mismatch")
        run("smoke-cleanup", ["kubectl", "-n", ns, "exec", pod_names[0], "-c", "juicefs", "--",
                               "sh", "-ec", "rm " + path + "; rmdir /shared/pr119-verify36"])
        receipt.update(status="real-storage-preflight-passed", mounted_nodes=mounts,
                       postgres_fsync=True, postgres_synchronous_commit=True, postgres_full_page_writes=True,
                       juicefs_version=version, block_size_kib=1024, trash_days=0,
                       cross_client_sha256=hashes[0], client_count=3)
        if args.attach:
            sys.path.insert(0, str(task / "acceptance/scripts"))
            from read_control_state import read_control_state

            _, records = read_control_state(task)
            if any(name.startswith("environment:") for name in records):
                raise RuntimeError("active Environment exists; do not roll node/control Pods")
            run("core-shared-upgrade", ["helm", "upgrade", "--install", "akernel",
                                        str(task / "source/AKernel/deploy/akernel/charts/core"),
                                        "--namespace", "akernel",
                                        "-f", str(task / "cluster/helm13/local-values.yaml"),
                                        "-f", str(task / "source/AKernel/deploy/shared-storage/juicefs-values.yaml"),
                                        "--post-renderer", str(task / "cluster/helm11/control-placement.py"),
                                        "--wait", "--timeout=8m"], timeout=540)
            run("shared-node-rollout", ["kubectl", "-n", "akernel", "rollout", "status",
                                        "daemonset/akernel-node", "--timeout=180s"], timeout=210)
            run("shared-core-pods", ["kubectl", "-n", "akernel", "get", "pods", "-o", "wide"])
            receipt.update(status="real-storage-verified-adx-shared-profile-attached",
                           attached_to_adx=True, private_runtime_storage="node-local XFS")
    finally:
        receipt["recorded_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, indent=2), flush=True)


if __name__ == "__main__":
    main()
