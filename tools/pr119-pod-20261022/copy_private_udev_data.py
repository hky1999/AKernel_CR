#!/usr/bin/env python3
"""Copy real host block udev metadata to the owned Kind node; never change host udev."""

import argparse
import io
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
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
    p = subprocess.run(base + ["inspect", node], check=True, capture_output=True, text=True)
    info = json.loads(p.stdout)[0]
    if info["Id"] != "6ea1b30343a521d9f601ae5f6d0f432cf7939f09bf9fe441d05cb3af77b5efa5":
        raise RuntimeError("node identity mismatch")
    output = task / "storage" / ("udev-snapshot-" + str(time.time_ns()))
    output.mkdir(mode=0o700)
    data = output / "data"
    data.mkdir()
    count = 0
    source = Path("/run/udev/data")
    for path in source.glob("b[0-9]*:[0-9]*"):
        if not stat.S_ISREG(path.lstat().st_mode):
            continue
        shutil.copy2(path, data / path.name, follow_symlinks=False)
        count += 1
    if not (data / "b7:0").is_file() or not (data / "b7:147").is_file():
        raise RuntimeError("real required host block metadata missing; do not fabricate it")
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as package:
        package.add(data, arcname="data")
    subprocess.run(base + ["exec", node, "mkdir", "-p", "/run/udev/data"], check=True)
    p = subprocess.run(base + ["exec", "-i", node, "tar", "-xf", "-", "-C", "/run/udev"],
                       input=stream.getvalue(), capture_output=True, timeout=60)
    record = {"rc": p.returncode, "real_block_records_copied": count,
              "host_udev_modified": False, "shared_service_restarted": False,
              "target": "owned Kind control node /run/udev/data", "raw_metadata_public": False}
    (output / "receipt.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2), flush=True)
    if p.returncode:
        raise RuntimeError("private metadata copy failed: " + p.stderr.decode()[-1000:])


if __name__ == "__main__":
    main()
