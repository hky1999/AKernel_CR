#!/usr/bin/env python3
"""Place the isolated PR119 storage components without changing source charts."""

import sys

import yaml


TOLERATION = {
    "key": "node-role.kubernetes.io/control-plane",
    "operator": "Exists",
    "effect": "NoSchedule",
}


def tolerate(spec):
    tolerations = spec.setdefault("tolerations", [])
    if TOLERATION not in tolerations:
        tolerations.append(dict(TOLERATION))


def place(objects):
    for obj in objects:
        if not obj:
            continue
        kind = obj.get("kind")
        name = obj.get("metadata", {}).get("name", "")
        spec = obj.get("spec", {})
        if kind == "CephCluster" and name == "rook-ceph":
            tolerate(spec.setdefault("placement", {}).setdefault("all", {}))
            for device_set in spec.get("storage", {}).get("storageClassDeviceSets", []):
                tolerate(device_set.setdefault("placement", {}))
                tolerate(device_set.setdefault("preparePlacement", {}))
        elif kind == "CephObjectStore" and name == "checkpoints":
            tolerate(spec.setdefault("gateway", {}).setdefault("placement", {}))
        elif kind == "StatefulSet" and name.endswith("-postgres"):
            tolerate(spec["template"]["spec"])
        elif kind == "Job" and "-format-" in name:
            pod = spec["template"]["spec"]
            tolerate(pod)
            pod.setdefault("nodeSelector", {})["akernel.dev/role"] = "control"
        yield obj


if __name__ == "__main__":
    yaml.safe_dump_all(place(yaml.safe_load_all(sys.stdin)), sys.stdout, sort_keys=False)
