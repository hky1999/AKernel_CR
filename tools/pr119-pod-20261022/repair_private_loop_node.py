#!/usr/bin/env python3
"""Expose a reported lost loop node only inside the owned Kind control node."""

import argparse
import json
from pathlib import Path
import re
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
    base = [sys.executable, str(task / "cluster/namespace-lab07.py"),
            "run", "--task", str(task), "--", "podman"]
    node = "akcr119-20261022-control-plane"
    inspect = subprocess.run(base + ["inspect", node], check=True, capture_output=True, text=True)
    data = json.loads(inspect.stdout)[0]
    if data["Id"] != "6ea1b30343a521d9f601ae5f6d0f432cf7939f09bf9fe441d05cb3af77b5efa5":
        raise RuntimeError("node identity mismatch")
    p = subprocess.run(base + ["exec", node, "losetup", "--find"],
                       check=True, capture_output=True, text=True)
    match = re.fullmatch(r"/dev/loop([0-9]+) \(lost\)\s*", p.stdout)
    record = {"sample_unix": time.time(), "private_node_only": True,
              "host_device_nodes_changed": False, "backing_storage_changed": False,
              "losetup_find": p.stdout.strip(), "created": False}
    if match:
        minor = int(match.group(1))
        device = "/dev/loop" + str(minor)
        subprocess.run(base + ["exec", node, "test", "!", "-e", device], check=True)
        subprocess.run(base + ["exec", node, "mknod", "-m", "600", device,
                               "b", "7", str(minor)], check=True)
        record.update(created=True, device=device, major_minor=[7, minor])
    output = task / "storage/live21" / ("private-loop-node-" + str(time.time_ns()) + ".json")
    output.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2), flush=True)


if __name__ == "__main__":
    main()
