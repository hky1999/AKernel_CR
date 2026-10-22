#!/usr/bin/python3
import sys, yaml
objects=list(yaml.safe_load_all(sys.stdin))
for obj in objects:
    if obj and obj.get("kind") in ("Deployment","StatefulSet") and obj.get("metadata",{}).get("name") in ("akernel-adx-coordinator","akernel-adx-ingress-api","akernel-adx-redis"):
        spec=obj["spec"]["template"]["spec"]
        spec.setdefault("nodeSelector",{})["akernel.dev/role"]="control"
        spec.setdefault("tolerations",[]).append({"key":"node-role.kubernetes.io/control-plane","operator":"Exists","effect":"NoSchedule"})
yaml.safe_dump_all(objects,sys.stdout,sort_keys=False)
