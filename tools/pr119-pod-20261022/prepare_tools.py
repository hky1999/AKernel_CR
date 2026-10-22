#!/usr/bin/env python3
"""Prepare fixed client tools in an existing private remote task; start no cluster."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time
import traceback

TOOLS = [
    ("kind", "v0.33.0",
     "https://github.com/kubernetes-sigs/kind/releases/download/v0.33.0/kind-linux-amd64",
     "https://github.com/kubernetes-sigs/kind/releases/download/v0.33.0/kind-linux-amd64.sha256sum",
     ["--version"], "aee6151561422756b764a4ae28e7f44cda5af5a9eead3cc9985112b1de8d8e0d"),
    ("helm", "v3.22.1",
     "https://get.helm.sh/helm-v3.22.1-linux-amd64.tar.gz",
     "https://get.helm.sh/helm-v3.22.1-linux-amd64.tar.gz.sha256sum",
     ["version", "--short"], None),
    ("kubectl", "v1.35.8",
     "https://dl.k8s.io/release/v1.35.8/bin/linux/amd64/kubectl",
     "https://dl.k8s.io/release/v1.35.8/bin/linux/amd64/kubectl.sha256",
     ["version", "--client", "-o", "json"], None),
]


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda: f.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task", required=True)
    a = p.parse_args()
    task = Path(a.task)
    if not task.is_absolute() or task.resolve() != task or not task.is_dir():
        p.error("--task must be an existing absolute non-symlink directory")
    if shutil.disk_usage(task).free < 250 * 1024 ** 3:
        p.error("free disk below the 250 GiB allocation threshold")
    out = task / "k8s-inputs" / "prepared06"
    out.mkdir(mode=0o700)
    (out / "bin").mkdir(mode=0o700)
    (out / "home").mkdir(mode=0o700)
    os.nice(10)
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, set(sorted(os.sched_getaffinity(0))[:2]))
    env = os.environ.copy()
    for k in list(env):
        if k.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
            del env[k]
    env.update(HOME=str(out / "home"), GOMAXPROCS="2",
               KUBECONFIG=str(out / "no-cluster.kubeconfig"))
    report = {"started_unix": time.time(), "status": "running", "tools": [],
              "cluster_started": False, "host_install": False,
              "module_loads": 0, "shared_sysctl_writes": 0}

    def run(cmd, log_name, timeout):
        started = time.monotonic()
        r = subprocess.run(cmd, env=env, capture_output=True, text=True,
                           timeout=timeout)
        record = {"argv": cmd, "rc": r.returncode,
                  "elapsed_seconds": time.monotonic() - started,
                  "stdout": r.stdout, "stderr": r.stderr}
        (out / (log_name + ".json")).write_text(json.dumps(record, indent=2))
        if r.returncode:
            raise RuntimeError(log_name + " failed: rc=" + str(r.returncode))
        return record

    def fetch(url, dest, log_name):
        run(["curl", "--disable", "--proto", "=https", "--proto-redir", "=https",
             "--fail", "--show-error", "--location", "--retry", "2",
             "--retry-delay", "2", "--connect-timeout", "15", "--max-time", "180",
             "--output", str(dest), url], log_name, 190)

    try:
        for name, version, url, sha_url, version_args, fixed_sha in TOOLS:
            archive = out / (name + (".tar.gz" if name == "helm" else ".download"))
            checksum = out / (name + ".upstream.sha256")
            fetch(sha_url, checksum, name + "-checksum")
            expected = checksum.read_text().split()[0].lower()
            if not re.fullmatch("[0-9a-f]{64}", expected):
                raise RuntimeError(name + " invalid upstream checksum")
            if fixed_sha and expected != fixed_sha:
                raise RuntimeError(name + " checksum changed from pinned selection")
            fetch(url, archive, name + "-download")
            actual = digest(archive)
            if actual != expected:
                raise RuntimeError(name + " downloaded SHA-256 mismatch")
            binary = out / "bin" / name
            if name == "helm":
                with tarfile.open(archive, "r:gz") as tar:
                    member = tar.getmember("linux-amd64/helm")
                    if not member.isfile() or member.size > 200 * 1024 ** 2:
                        raise RuntimeError("unexpected Helm archive member")
                    with tar.extractfile(member) as src, binary.open("xb") as dst:
                        shutil.copyfileobj(src, dst)
            else:
                shutil.copyfile(archive, binary)
            binary.chmod(0o700)
            result = run([str(binary)] + version_args, name + "-version", 30)
            if version.lstrip("v") not in result["stdout"] + result["stderr"]:
                raise RuntimeError(name + " version output mismatch")
            report["tools"].append({
                "name": name, "version": version, "url": url,
                "upstream_checksum_url": sha_url,
                "download_sha256": actual, "binary_sha256": digest(binary),
                "download_bytes": archive.stat().st_size,
                "binary_bytes": binary.stat().st_size,
                "version_command": result})
        report["status"] = "tools_ready_no_cluster"
    except Exception:
        report["status"] = "failed_preserved"
        report["error"] = traceback.format_exc()
        raise
    finally:
        report["finished_unix"] = time.time()
        (out / "receipt.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()

