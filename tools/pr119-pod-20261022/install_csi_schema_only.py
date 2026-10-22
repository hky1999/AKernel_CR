#!/usr/bin/env python3
"""Install pinned CSI API schemas only, never CSI controllers or driver workloads."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile

import yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, required=True)
    args = parser.parse_args()
    task = args.task.resolve(strict=True)
    output = task / "storage/csi-schema27"
    output.mkdir(mode=0o700, exist_ok=False)
    archive = task / "storage/preflight15/rook-ceph-1.21.0.tgz"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != "c070c7985deee72d7620e0377c07ce2afba28f566fbefe47bf934d00a5692cde":
        raise RuntimeError("chart digest mismatch")
    with tarfile.open(archive) as package:
        package.extractall(output, filter="data")
    base = [sys.executable, str(task / "cluster/namespace-lab07.py"),
            "run", "--task", str(task), "--"]
    result = subprocess.run(base + ["helm", "template", "csi-api-schema",
                                    str(output / "rook-ceph/charts/ceph-csi-operator"),
                                    "--namespace", "akernel-pr119-storage", "--include-crds"],
                            text=True, capture_output=True, timeout=90)
    (output / "render.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError("CSI schema render failed")
    objects = [o for o in yaml.safe_load_all(result.stdout) if o]
    definitions = [o for o in objects if o.get("kind") == "CustomResourceDefinition"]
    if not definitions or not any(o["spec"]["names"]["kind"] == "ClientProfile" for o in definitions):
        raise RuntimeError("expected ClientProfile schema missing")
    if any(not o["spec"]["group"].endswith("ceph.io") for o in definitions):
        raise RuntimeError("unexpected schema group")
    manifest = yaml.safe_dump_all(definitions, sort_keys=False)
    (output / "schemas-only.yaml").write_text(manifest)
    result = subprocess.run(base + ["kubectl", "create", "-f", "-"],
                            input=manifest, text=True, capture_output=True, timeout=90)
    (output / "create.json").write_text(json.dumps(
        {"rc": result.returncode, "stdout": result.stdout, "stderr": result.stderr}, indent=2) + "\n")
    receipt = {"rc": result.returncode, "schema_names": [o["metadata"]["name"] for o in definitions],
               "only_kind_applied": "CustomResourceDefinition", "driver_workloads_created": 0,
               "global_kernel_changes": False}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2), flush=True)
    if result.returncode:
        raise RuntimeError("schema creation failed; retain original evidence")


if __name__ == "__main__":
    main()
