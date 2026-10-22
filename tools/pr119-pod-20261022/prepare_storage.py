#!/usr/bin/env python3
"""Render the isolated storage profiles remotely; never apply or allocate devices."""

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time

import yaml


ROOK_SHA256 = "c070c7985deee72d7620e0377c07ce2afba28f566fbefe47bf934d00a5692cde"
NAMESPACE = "akernel-pr119-storage"
TOLERATION = {
    "key": "node-role.kubernetes.io/control-plane",
    "operator": "Exists",
    "effect": "NoSchedule",
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    task = args.task.resolve(strict=True)
    output = (args.output or task / "storage/preflight16").resolve()
    require(output.is_relative_to(task), "output must be inside the task directory")
    output.mkdir(parents=True, exist_ok=False)
    receipt = {
        "status": "failed",
        "mode": "offline-render-only",
        "namespace": NAMESPACE,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cluster_resources_created": False,
        "block_devices_allocated": False,
        "global_parameters_changed": False,
        "sdk_requests": 0,
    }
    try:
        archive = task / "storage/preflight15/rook-ceph-1.21.0.tgz"
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        require(actual == ROOK_SHA256, "Rook archive digest mismatch")
        receipt["rook_chart_sha256"] = actual
        receipt["rook_chart_version"] = "1.21.0"
        operator = {
            "currentNamespaceOnly": True,
            "nodeSelector": {"akernel.dev/role": "control"},
            "tolerations": [TOLERATION],
            "resources": {
                "requests": {"cpu": "100m", "memory": "128Mi"},
                "limits": {"cpu": "1", "memory": "512Mi"},
            },
            "enableDiscoveryDaemon": False,
            "allowLoopDevices": True,
            "csi": {"installCsiOperator": False, "createCsiOperatorResources": False},
        }
        storage = {
            "juicefs": {
                "volumeName": "akernel-pr119-checkpoints",
                "hostMountPath": "/srv/akernel-shared",
                "trashDays": 0,
                "cacheMiB": 0,
                "readaheadMiB": 4,
            },
            "ceph": {
                "storageClass": "akcr119-ceph-static",
                "dataDirHostPath": "/var/lib/akernel-pr119-storage/rook",
                "osdCount": 1,
                "osdSize": "40Gi",
                "monCount": 1,
                "monSize": "4Gi",
                "replicas": 1,
                "gatewayInstances": 1,
                "nodeSelector": {"akernel.dev/role": "control"},
            },
            "postgres": {
                "storageClass": "standard",
                "size": "4Gi",
                "existingSecret": "akcr119-postgres",
            },
        }
        for name, values in [("rook-values.yaml", operator), ("juicefs-values.yaml", storage)]:
            (output / name).write_text(yaml.safe_dump(values, sort_keys=False))
        helper = task / "cluster/namespace-lab07.py"
        command = [sys.executable, str(helper), "run", "--task", str(task), "--", "helm"]

        def render(name, chart, values):
            argv = command + [
                "template", name, str(chart), "--namespace", NAMESPACE,
                "--include-crds", "-f", str(output / values),
            ]
            result = subprocess.run(argv, text=True, capture_output=True, timeout=90)
            (output / (name + "-stderr.txt")).write_text(result.stderr)
            require(result.returncode == 0, "helm template failed for " + name)
            (output / (name + "-raw.yaml")).write_text(result.stdout)
            objects = [obj for obj in yaml.safe_load_all(result.stdout) if obj]
            require(not any(obj.get("kind") == "Secret" for obj in objects),
                    "unexpected Secret in offline render; keep output private")
            return objects

        rook = render("rook-ceph", archive, "rook-values.yaml")
        config = next(obj for obj in rook if obj.get("kind") == "ConfigMap"
                      and obj["metadata"]["name"] == "rook-ceph-operator-config")
        require(config["data"].get("ROOK_CREATE_CSI_OPERATOR_RESOURCES") == "false",
                "CSI resource generation not disabled in rendered operator config")
        require(config["data"].get("ROOK_ENABLE_DISCOVERY_DAEMON") == "false",
                "device discovery not disabled")
        workloads = [(obj["kind"], obj["metadata"]["name"]) for obj in rook
                     if obj.get("kind") in {"Deployment", "DaemonSet", "StatefulSet"}]
        require(workloads == [("Deployment", "rook-ceph-operator")],
                "unexpected storage driver/operator workloads")
        deployment = next(obj for obj in rook if obj.get("kind") == "Deployment")
        pod = deployment["spec"]["template"]["spec"]
        require(pod.get("nodeSelector", {}).get("akernel.dev/role") == "control",
                "operator placement not rendered")
        require(TOLERATION in pod.get("tolerations", []), "operator lacks control-plane toleration")

        objects = render("akcr119-juicefs", task / "source/AKernel/deploy/shared-storage/charts/juicefs",
                         "juicefs-values.yaml")
        placement = pathlib.Path(__file__).with_name("storage_placement.py")
        result = subprocess.run([sys.executable, str(placement)],
                                input=yaml.safe_dump_all(objects, sort_keys=False),
                                text=True, capture_output=True, timeout=30)
        (output / "placement-stderr.txt").write_text(result.stderr)
        require(result.returncode == 0, "storage placement post-renderer failed")
        (output / "juicefs-placed.yaml").write_text(result.stdout)
        placed = [obj for obj in yaml.safe_load_all(result.stdout) if obj]
        ceph = next(obj for obj in placed if obj.get("kind") == "CephCluster")
        require(ceph["spec"]["storage"].get("useAllDevices") is False,
                "Ceph must not discover all host devices")
        require(ceph["spec"]["storage"].get("useAllNodes") is False,
                "Ceph must not discover all host nodes")
        require(TOLERATION in ceph["spec"]["placement"]["all"].get("tolerations", []),
                "Ceph daemon placement lacks toleration")
        for device_set in ceph["spec"]["storage"]["storageClassDeviceSets"]:
            for claim in device_set["volumeClaimTemplates"]:
                require(claim["spec"]["volumeMode"] == "Block", "OSD must use raw Block PVC")
                require(claim["spec"]["storageClassName"] == "akcr119-ceph-static",
                        "OSD must use the explicit task storage class")
        pg = next(obj for obj in placed if obj.get("kind") == "StatefulSet")
        require(TOLERATION in pg["spec"]["template"]["spec"].get("tolerations", []),
                "PostgreSQL lacks toleration")
        receipt.update({
            "status": "offline-render-passed-not-deployed",
            "rook_object_count": len(rook),
            "juicefs_object_count": len(placed),
            "rook_workloads": workloads,
            "csi_operator_install_disabled": True,
            "csi_resource_generation_disabled": True,
            "device_discovery_disabled": True,
            "raw_block_pvc_required": True,
            "static_ceph_pvs_created": False,
            "single_replica_evaluation_only": True,
        })
    except Exception as error:
        receipt["error"] = str(error)
        raise
    finally:
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, indent=2), flush=True)


if __name__ == "__main__":
    main()
