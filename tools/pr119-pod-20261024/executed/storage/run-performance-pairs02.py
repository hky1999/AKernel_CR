#!/usr/bin/env python3
import pathlib,json,subprocess,os,sys,time,hashlib
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";D=Q/"tap-checksum-fix";S=D/"storage";O=S/"performance-pairs02";O.mkdir(mode=0o700)
B=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"];sys.path.insert(0,str(Q/"acceptance/scripts"))
from read_control_state import read_control_state
OLD=pathlib.Path("/mnt/m0-xfs/akernel-pr119-repro-20261022.XfboxUgq")
C={"old-common-tapfix":{"image":"localhost/akernel-pr119:6ea004125eb4-tapoffload-perf04","digest":"sha256:9840a277eeb71a1685c3c06b0838b2992434fdc791906751a0d47b9a0c6658f5","elfs":OLD/"image-build/payload-receipt.json","sdk":OLD/"sdk/client/bin/python"},"new-common-tapfix":{"image":"localhost/akernel-pr119:365f7971f895-tapoffload01","digest":"sha256:20257a27de0137383b1141709fb15dc87f81520f7fe0e41ba17b4e5ee31194a7","elfs":Q/"image-build/payload-receipt.json","sdk":Q/"sdk/client/bin/python"}}
r={"rc":1,"cases":[],"status":"preflight","protocol":{"pairs":10,"order":"odd old/new; even new/old","rounds_per_runtime_per_deployment":2,"rounds_are_clustered_by_instance":True,"runtime_memory_mb":2048,"application_memory_bytes":536870912,"root_file_bytes":67108864,"kind":"same-node shared-checkpoint exploratory version comparison","cold_object_storage_claim":False},"final_profile":None}
def status(phase,**v):
 r["current"]={"phase":phase,**v};(O/"current.json").write_text(json.dumps(r,indent=2))
def run(output,name,argv,timeout=900):
 with (output/(name+".stdout")).open("x") as so,(output/(name+".stderr")).open("x") as se:p=subprocess.run(argv,stdout=so,stderr=se,timeout=timeout)
 (output/(name+".terminal.json")).write_text(json.dumps({"rc":p.returncode}))
 if p.returncode:raise RuntimeError(name+" failed; preserve resources and current profile")
 return (output/(name+".stdout")).read_text()
def lab(output,name,argv,timeout=900):return run(output,name,B+argv,timeout)
def records():return read_control_state(N)[1]
def no_env():
 if any(k.startswith("environment:") for k in records()):raise RuntimeError("Environment remains; do not roll services")
def secrets(output,name):return lab(output,name,["kubectl","-n","akernel","get","secrets","akernel-adx-tls","akernel-secrets","-o",'jsonpath={range .items[*]}{.metadata.name}{" "}{.metadata.uid}{"\\n"}{end}'])
def deploy(variant,label):
 no_env()
 if os.statvfs(N).f_bavail*os.statvfs(N).f_frsize<650*(1<<30):raise RuntimeError("disk reserve below 650 GiB")
 cfg=C[variant];o=O/label;o.mkdir(mode=0o700);status("roll-profile",variant=variant,label=label)
 v=records();previous={}
 for node in ["akcr119-20261022-worker","akcr119-20261022-worker2"]:
  sid=v["node:"+node]["session"]["id"];previous[node]=hashlib.sha256(str(sid).encode()).hexdigest()
 pp=o/"previous-sessions.json";pp.write_text(json.dumps(previous))
 before=secrets(o,"secret-uids-before")
 ds=json.loads(lab(o,"node-template-before",["kubectl","-n","akernel","get","daemonset","akernel-node","-o","json"]))
 current=ds["spec"]["template"]["spec"]["containers"][0]["image"]
 if current==cfg["image"]:
  lab(o,"force-owned-roles-new-session",["kubectl","-n","akernel","rollout","restart","deployment/akernel-adx-coordinator","deployment/akernel-adx-ingress-api","daemonset/akernel-node"])
 else:
  lab(o,"helm-version-profile",["helm","upgrade","--install","akernel",str(Q/"source/AKernel/deploy/akernel/charts/core"),"--namespace","akernel","-f",str(D/"virtiofs-enabled01-values.yaml"),"-f",str(Q/"source/AKernel/deploy/shared-storage/juicefs-values.yaml"),"--set-string","image.tag="+cfg["image"].split(":",1)[1],"--post-renderer",str(N/"cluster/helm11/control-placement.py"),"--wait","--timeout=8m"],540)
 lab(o,"node-rollout",["kubectl","-n","akernel","rollout","status","daemonset/akernel-node","--timeout=240s"],270)
 for dep in ["akernel-adx-coordinator","akernel-adx-ingress-api"]:
  lab(o,"rollout-"+dep,["kubectl","-n","akernel","rollout","status","deployment/"+dep,"--timeout=240s"],270)
 status("real-readiness",variant=variant,label=label)
 run(o,"fresh-routable-schedulable",["python3",str(S/"wait-perf-ready02.py"),"--expected-digest",cfg["digest"],"--output",str(o/"ready"),"--previous-session-hashes",str(pp),"--timeout","360"],450)
 if secrets(o,"secret-uids-after")!=before:raise RuntimeError("identity Secret UID changed")
 pods=json.loads(lab(o,"live-pod-identities",["kubectl","-n","akernel","get","pods","-o","json"]))["items"]
 live=[p for p in pods if not p["metadata"].get("deletionTimestamp") and any(p["metadata"]["name"].startswith(x) for x in ["akernel-node-","akernel-adx-coordinator-","akernel-adx-ingress-api-"])]
 if len(live)!=4:raise RuntimeError("unexpected current core Pod count")
 if any(x.get("imageID","").rsplit("@",1)[-1]!=cfg["digest"] for p in live for x in p["status"].get("containerStatuses",[])):raise RuntimeError("core image identities differ")
 assets=json.loads(cfg["elfs"].read_text())["assets"];paths=["/usr/local/bin/sandboxd","/usr/local/bin/runsc","/usr/local/bin/firecracker","/opt/firecracker/initrd.img","/opt/firecracker/vmlinux","/opt/akernel/runtime/akernel-runtime-rootfs.img","/opt/adx/current/runtime/adx-execd","/opt/adx/current/bin/adxlet","/opt/adx/current/bin/adx-coordinator","/opt/adx/current/bin/adx-apiserver"]
 pins={p:assets[p]["sha256"] for p in paths};pins["/usr/local/bin/sandboxd"]="9c74060c3c4edceed6edb746e6b42bdd21116e3663427238fb1dd5067f3c964b"
 for pod in [p["metadata"]["name"]for p in live if p["metadata"]["name"].startswith("akernel-node-")]:
  text=lab(o,"payload-"+pod,["kubectl","-n","akernel","exec",pod,"--","sha256sum",*paths])
  got={x.split()[1]:x.split()[0] for x in text.splitlines() if len(x.split())==2}
  if got!=pins:raise RuntimeError("live node payload differs")
 r["final_profile"]=variant;status("profile-verified",variant=variant,label=label)
 return o
try:
 if json.loads((S/"performance-smoke01/terminal.json").read_text()).get("rc")!=0:raise RuntimeError("measurement smoke gate incomplete")
 if json.loads((S/"performance-prepare04/terminal.json").read_text()).get("rc")!=0:raise RuntimeError("candidate preparation incomplete")
 if json.loads((S/"performance-image-identity02/terminal.json").read_text()).get("rc")!=0:raise RuntimeError("image import mapping not proven")
 no_env()
 for name,want in {"akcr119-20261022-control-plane":"309834713ae51c81b89d88111a2a0adaf345f9ec135d8d3938d20f4727023bfa","akcr119-20261022-worker":"c94000a9e103f344bd40e2fd1cce2bb4ee113766beadc63ae5e5f8c7b6a5b550","akcr119-20261022-worker2":"31814694e9fd4463d194bb5150fc2dec052131af18d726ca330e822345c0f017"}.items():
  info=json.loads(lab(O,"kind-identity-"+name,["podman","inspect",name]))[0]
  if info["Id"]!=want or not info["State"]["Running"]:raise RuntimeError("owned Kind identity changed")
 for pair in range(1,11):
  variants=["old-common-tapfix","new-common-tapfix"] if pair%2 else ["new-common-tapfix","old-common-tapfix"]
  node="akcr119-20261022-worker" if pair%2 else "akcr119-20261022-worker2"
  for position,variant in enumerate(variants):
   label="pair-"+str(pair)+"-"+str(position)+"-"+variant;o=deploy(variant,label)
   for rt in ["runsc","firecracker"]:
    status("sdk-measurement",variant=variant,pair=pair,runtime=rt,label=label)
    job=N/"acceptance/runs"/("shared-performance-pairs02-"+str(pair)+"-"+variant+"-"+rt)
    shell='set -eu; source "'+str(Q/"acceptance/auth-shared-tapfix-direct01/sdk.env")+'"; export PYTHONPATH="'+str(Q/"acceptance/scripts")+'"; export PYTHONDONTWRITEBYTECODE=1; export HOME="'+str(o)+'"; exec "'+str(C[variant]["sdk"])+'" "'+str(S/"sdk-performance01.py")+'" --runtime '+rt+' --variant '+variant+' --node-id '+node+' --rounds 2 --output "'+str(job)+'"'
    run(o,"sdk-"+rt,B+["bash","-c",shell],1800)
    result=json.loads((job/"terminal.json").read_text())
    if result.get("rc")!=0 or len(result.get("rounds",[]))!=2:raise RuntimeError("SDK measurement incomplete")
    r["cases"].append({"pair":pair,"position":position,"job":str(job),"data":result});status("case-complete",variant=variant,pair=pair,runtime=rt)
 deploy("new-common-tapfix","restore-final-new-profile")
 no_env();r.update(rc=0,status="ten-paired-version-blocks-passed-final-new-profile",paired_performance_complete=True)
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e),paired_performance_complete=False)
finally:r["completed_unix_ns"]=time.time_ns();(O/"terminal.json").write_text(json.dumps(r,indent=2))
sys.exit(r["rc"])
