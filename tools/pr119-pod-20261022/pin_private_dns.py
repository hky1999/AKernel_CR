#!/usr/bin/env python3
"""Keep this private cluster's DNS outside the execution-node fault domain."""
import argparse
import json
from pathlib import Path
import subprocess
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task", type=Path, required=True)
    a = p.parse_args()
    task = a.task.resolve()
    if task.parent != Path("/mnt/m0-xfs") or not task.name.startswith("akernel-pr119-repro-"):
        raise AssertionError("not an owned task directory")
    out = task / "cluster/dns47"
    out.mkdir(mode=0o700, exist_ok=False)
    helper = ["python3", str(task / "cluster/namespace-lab07.py"), "run", "--task", str(task), "--"]

    def command(*args, timeout=60):
        r = subprocess.run(helper + list(args), capture_output=True, text=True, timeout=timeout)
        if r.returncode:
            raise RuntimeError({"command": args, "rc": r.returncode, "stderr": r.stderr[-2000:]})
        return r.stdout

    def kube(*args, timeout=60):
        return command("kubectl", *args, timeout=timeout)

    control = "akcr119-20261022-control-plane"
    expected = "6ea1b30343a521d9f601ae5f6d0f432cf7939f09bf9fe441d05cb3af77b5efa5"
    actual = json.loads(command("podman", "inspect", control))[0]
    if actual["Id"] != expected or actual["Name"].lstrip("/") != control:
        raise AssertionError("private control container identity mismatch")
    nodes = json.loads(kube("get", "nodes", "-o", "json"))["items"]
    if {n["metadata"]["name"] for n in nodes} != {
        control, "akcr119-20261022-worker", "akcr119-20261022-worker2"
    }:
        raise AssertionError("unexpected cluster topology")
    (out / "apiserver-readyz.txt").write_text(kube("get", "--raw", "/readyz?verbose"))
    before = json.loads(kube("-n", "kube-system", "get", "deployment", "coredns", "-o", "json"))
    (out / "deployment-before.json").write_text(json.dumps(before, indent=2) + "\n")
    old_pods = json.loads(kube("-n", "kube-system", "get", "pods", "-l", "k8s-app=kube-dns", "-o", "json"))
    (out / "pods-before.json").write_text(json.dumps(old_pods, indent=2) + "\n")
    patch = {"metadata": {"resourceVersion": before["metadata"]["resourceVersion"]},
             "spec": {"template": {"spec": {"nodeSelector": {"akernel.dev/role": "control"}}}}}
    kube("-n", "kube-system", "patch", "deployment", "coredns", "--type=merge", "-p", json.dumps(patch))
    rollout = kube("-n", "kube-system", "rollout", "status", "deployment/coredns", "--timeout=180s", timeout=200)
    (out / "rollout.txt").write_text(rollout)
    deadline = time.monotonic() + 90
    while True:
        pods = json.loads(kube("-n", "kube-system", "get", "pods", "-l", "k8s-app=kube-dns", "-o", "json"))["items"]
        live = [x for x in pods if not x["metadata"].get("deletionTimestamp")]
        endpoints = json.loads(kube("-n", "kube-system", "get", "endpointslices", "-l", "kubernetes.io/service-name=kube-dns", "-o", "json"))
        ready = [e for s in endpoints["items"] for e in s.get("endpoints", []) if e.get("conditions", {}).get("ready")]
        if len(live) == 2 and all(p["spec"].get("nodeName") == control and
                                 any(c["type"] == "Ready" and c["status"] == "True" for c in p["status"].get("conditions", [])) for p in live):
            if len(ready) == 2 and all(e.get("nodeName") == control for e in ready):
                break
        if time.monotonic() >= deadline:
            raise TimeoutError("DNS endpoints did not converge to the private control node")
        time.sleep(2)
    (out / "dns-endpoints-after.json").write_text(json.dumps(endpoints, indent=2) + "\n")
    node_pods = json.loads(kube("-n", "akernel", "get", "pods", "-o", "json"))["items"]
    probes = []
    program = "import socket,json; names=['akcr119-juicefs-postgres.akernel-pr119-storage.svc.cluster.local','rook-ceph-rgw-checkpoints.akernel-pr119-storage.svc.cluster.local'];print(json.dumps({n:sorted(set(x[4][0] for x in socket.getaddrinfo(n,5432,type=socket.SOCK_STREAM))) for n in names}))"
    for pod in node_pods:
        if pod["metadata"]["name"].startswith("akernel-node-"):
            answer = kube("-n", "akernel", "exec", pod["metadata"]["name"], "--", "python3", "-c", program)
            probes.append({"node": pod["spec"]["nodeName"], "answers": json.loads(answer)})
    if len(probes) != 2:
        raise AssertionError("did not check both execution nodes")
    receipt = {"status": "private-dns-moved-and-resolved", "host_dns_changed": False,
               "old_nodes": [p["spec"].get("nodeName") for p in old_pods["items"]],
               "new_nodes": [p["spec"]["nodeName"] for p in live], "node_dns_probes": probes,
               "completed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
