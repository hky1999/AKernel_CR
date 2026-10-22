#!/usr/bin/env python3
"""Verify a private lab policy with before/allowed/denied/removed controls."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

HTTP_PROBE = """
import json, sys, time, urllib.request
start = time.monotonic()
try:
    response = urllib.request.urlopen(sys.argv[1], timeout=3)
    print(json.dumps({"connected": True, "status": response.status,
                      "seconds": time.monotonic() - start}))
except Exception as error:
    print(json.dumps({"connected": False, "error": type(error).__name__,
                      "seconds": time.monotonic() - start}))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    args = parser.parse_args()
    task = Path(args.task)
    if not task.is_absolute() or task.resolve() != task:
        parser.error("use an absolute non-symlink task path")
    out = task / "cluster/netcheck12"
    result_path = out / "result-fixed.json"
    if result_path.exists():
        parser.error("existing result retained; do not overwrite or blindly retry")
    base = ["python3", str(task / "cluster/namespace-lab07.py"), "run",
            "--task", str(task), "--", "kubectl"]
    report = {"started_unix": time.time(), "requests": [],
              "network_policy_enforcement_proven": False,
              "namespace_cleanup_confirmed": False, "sdk_acceptance": False}

    def run(argv, timeout=30, input_text=None):
        value = subprocess.run(base + argv, input=input_text,
                               capture_output=True, text=True, timeout=timeout)
        if value.returncode:
            raise RuntimeError(json.dumps({"argv": argv, "rc": value.returncode,
                                           "stderr": value.stderr}))
        return value.stdout

    try:
        raw = json.loads(run(["-n", "pr119-netcheck", "get", "pods", "-o", "json"]))
        pods = {p["metadata"]["name"]: {"ip": p["status"].get("podIP"),
                "node": p["spec"]["nodeName"], "phase": p["status"]["phase"]}
                for p in raw["items"]}
        report["pods"] = pods
        if set(pods) != {"server", "allowed", "denied"}:
            raise RuntimeError("unexpected probe Pod set")
        if any(p["phase"] != "Running" for p in pods.values()):
            raise RuntimeError("probe Pods are not all running")
        report["cross_node"] = pods["server"]["node"] != pods["allowed"]["node"]
        if not report["cross_node"]:
            raise RuntimeError("server and clients must be on different nodes")
        url = "http://" + pods["server"]["ip"] + ":18081/"

        def probe(stage, name):
            raw = run(["-n", "pr119-netcheck", "exec", "-i", name, "--",
                       "/usr/bin/python3", "-", url], 20, HTTP_PROBE)
            value = json.loads(raw)
            value.update(stage=stage, client=name)
            report["requests"].append(value)
            return value

        for name in ("allowed", "denied"):
            if not probe("before_policy", name)["connected"]:
                raise RuntimeError("baseline HTTP failed for " + name)
        run(["create", "-f", str(out / "policy.json")])
        report["policy_created"] = True
        time.sleep(3)
        allowed = probe("policy_active", "allowed")
        denied = probe("policy_active", "denied")
        passed = allowed["connected"] and allowed.get("status") == 200 and not denied["connected"]
        run(["-n", "pr119-netcheck", "delete", "networkpolicy", "only-authorized-client"])
        report["policy_removed"] = True
        time.sleep(2)
        for name in ("allowed", "denied"):
            passed = probe("after_policy_removed", name)["connected"] and passed
        report["network_policy_enforcement_proven"] = passed
        if not passed:
            raise RuntimeError("policy positive/negative controls failed")
        run(["delete", "namespace", "pr119-netcheck", "--wait=true",
             "--timeout=60s"], 70)
        report["namespace_cleanup_confirmed"] = True
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        report["finished_unix"] = time.time()
        with result_path.open("x") as f:
            json.dump(report, f, indent=2)
        print(json.dumps(report, indent=2))
    if not report["network_policy_enforcement_proven"] or not report["namespace_cleanup_confirmed"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()

