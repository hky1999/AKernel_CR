import pathlib,json,subprocess,os,sys,time,hashlib
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";D=Q/"tap-checksum-fix";S=D/"storage";O=D/"fc-io-cut-sdk02";O.mkdir(mode=0o700);(O/"cache").mkdir(mode=0o700);os.environ["XDG_CACHE_HOME"]=str(O/"cache")
B=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"]
sys.path.insert(0,str(Q/"acceptance/scripts"));from read_control_state import read_control_state
r={"rc":1,"roll_attempted":False,"deployed":False,"status":"preflight","cases":[],"steps":[]}
def status(phase):
 r["status"]=phase;(O/"current.json").write_text(json.dumps(r,indent=2))
def run(name,args,timeout=900):
 with (O/(name+".stdout")).open("x")as so,(O/(name+".stderr")).open("x")as se:p=subprocess.run(args,stdout=so,stderr=se,timeout=timeout)
 r["steps"].append({"name":name,"rc":p.returncode});(O/"current.json").write_text(json.dumps(r,indent=2))
 if p.returncode:raise RuntimeError(name+" failed; retain current profile and unknown operation before retry")
 return (O/(name+".stdout")).read_text()
def lab(name,args,timeout=900):return run(name,B+args,timeout)
def records():return read_control_state(N)[1]
def no_env():
 if any(k.startswith("environment:")for k in records()):raise RuntimeError("Environment remains; refuse rollout or next case")
def replace_once(text,before,after):
 if text.count(before)!=1:raise RuntimeError("script generation match is not unique")
 return text.replace(before,after)
try:
 im=json.loads((D/"fc-io-cut-image01/terminal.json").read_text())
 proof=json.loads((D/"fc-io-cut-identity01/terminal.json").read_text())
 if proof.get("rc")!=0 or proof["config_sha256"]!=im["config_sha256"]:raise RuntimeError("CRI identity proof missing")
 prior=json.loads((D/"fc-io-cut-sdk01/terminal.json").read_text())
 if prior.get("rc")!=1 or prior["steps"][-1]!={"name":"fresh-routable-schedulable","rc":1} or (D/"fc-io-cut-sdk01/official-sdk").exists():raise RuntimeError("prior run was not limited to readiness; inspect before continuing")
 im["expected_cri_digest"]=proof["cri_digest"]
 if im.get("rc")!=0 or im["sandboxd_sha256"]!="c85d58b2efe8c141394877cc73cdb33cd796d7760770a31c808fbd6c22fb5dce":raise RuntimeError("candidate image gate incomplete")
 if os.statvfs(N).f_bavail*os.statvfs(N).f_frsize<650*(1<<30):raise RuntimeError("disk reserve insufficient")
 no_env();nodes=["akcr119-20261022-worker","akcr119-20261022-worker2"]
 before=records();previous=json.loads((D/"fc-io-cut-sdk01/previous-sessions.json").read_text())
 if set(previous)!=set(nodes) or any(hashlib.sha256(str(before["node:"+node]["session"]["id"]).encode()).hexdigest()==previous[node]for node in nodes):raise RuntimeError("original fresh sessions are not proven")
 pp=O/"previous-sessions.json";pp.write_text(json.dumps(previous))
 # Prepare a strictly pinned readiness gate before rolling any service.
 gate=(S/"wait-perf-ready02.py").read_text()
 lines=gate.splitlines();choices=[i for i,x in enumerate(lines)if x.startswith('p.add_argument("--expected-digest",choices=')]
 if len(choices)!=1:raise RuntimeError("readiness digest definition ambiguous")
 lines[choices[0]]='p.add_argument("--expected-digest",choices=['+repr(im["expected_cri_digest"])+'],required=True)'
 gate="\n".join(lines)+"\n"
 gate=replace_once(gate,"9c74060c3c4edceed6edb746e6b42bdd21116e3663427238fb1dd5067f3c964b",im["sandboxd_sha256"])
 (O/"wait-ready01.py").write_text(gate);compile(gate,str(O/"wait-ready01.py"),"exec")
 official=replace_once((S/"sdk-full02.sh").read_text(),'OUT="$D/storage/sdk-full02"','OUT="$D/fc-io-cut-sdk02/official-sdk"')
 official=replace_once(official,'export HOME="$OUT/home"\nmkdir -m 700 "$HOME"','export XDG_CACHE_HOME="$OUT/cache"\nmkdir -m 700 "$XDG_CACHE_HOME"')
 (O/"sdk-full01.sh").write_text(official)
 run("official-shell-syntax",["bash","-n",str(O/"sdk-full01.sh")])
 perf=(S/"sdk-performance01.py").read_text()
 perf=replace_once(perf,'choices=["old-common-tapfix","new-common-tapfix"]','choices=["old-common-tapfix","new-common-tapfix","new-io-cut-candidate"]')
 (O/"sdk-performance01.py").write_text(perf);compile(perf,str(O/"sdk-performance01.py"),"exec")
 cross=(S/"cross-node05.py").read_text()
 cross=replace_once(cross,'O=S/"cross-node05";O.mkdir(mode=0o700)','O=D/"fc-io-cut-sdk02/cross-node01";O.mkdir(mode=0o700)')
 cross=replace_once(cross,'str(D/"wait-adx-ready01.py")','str(O.parent/"wait-ready01.py"),"--expected-digest",'+repr(im["expected_cri_digest"]))
 cross=replace_once(cross,'str(S/"run05/previous-sessions.json")','str(O.parent/"previous-sessions.json")')
 cross=replace_once(cross,'(S/"run06/terminal.json")','(O.parent/"same-node-accepted.json")')
 cross=replace_once(cross,'name="shared-tapfix-direct01-"','name="shared-io-cut-sdk02-"')
 (O/"cross-node01.py").write_text(cross);compile(cross,str(O/"cross-node01.py"),"exec")
 secretargs=["kubectl","-n","akernel","get","secrets","akernel-adx-tls","akernel-secrets","-o",'jsonpath={range .items[*]}{.metadata.name}{" "}{.metadata.uid}{"\\n"}{end}']
 secrets=lab("secret-uids-before",secretargs)
 if secrets!=(D/"fc-io-cut-sdk01/secret-uids-before.stdout").read_text():raise RuntimeError("Secret changed since original rollout")
 ds=json.loads(lab("node-template-before",["kubectl","-n","akernel","get","daemonset","akernel-node","-o","json"]))
 original_image=ds["spec"]["template"]["spec"]["containers"][0]["image"]
 if original_image!=im["image"]:raise RuntimeError("already-deployed candidate changed; refuse continuation")
 r.update(roll_attempted=False,verified_existing_rollout=True,original_image=original_image,candidate=im["image"],expected_cri_digest=im["expected_cri_digest"],sandboxd_sha256=im["sandboxd_sha256"]);status("checking-already-deployed-candidate")
 run("fresh-routable-schedulable",[sys.executable,str(O/"wait-ready01.py"),"--expected-digest",im["expected_cri_digest"],"--output",str(O/"ready"),"--previous-session-hashes",str(pp),"--timeout","360"],450)
 if lab("secret-uids-after",secretargs)!=secrets:raise RuntimeError("Secret identity changed")
 pods=json.loads(lab("candidate-pod-identities",["kubectl","-n","akernel","get","pods","-o","json"]))["items"]
 live=[p for p in pods if not p["metadata"].get("deletionTimestamp")and any(p["metadata"]["name"].startswith(x)for x in ["akernel-node-","akernel-adx-coordinator-","akernel-adx-ingress-api-"])]
 if len(live)!=4 or any(c.get("imageID","").rsplit("@",1)[-1]!=im["expected_cri_digest"]for p in live for c in p["status"].get("containerStatuses",[])):raise RuntimeError("actual core image identities differ")
 assets=json.loads((Q/"image-build/payload-receipt.json").read_text())["assets"]
 paths=["/usr/local/bin/sandboxd","/usr/local/bin/runsc","/usr/local/bin/firecracker","/opt/firecracker/initrd.img","/opt/firecracker/vmlinux","/opt/akernel/runtime/akernel-runtime-rootfs.img","/opt/adx/current/runtime/adx-execd","/opt/adx/current/bin/adxlet","/opt/adx/current/bin/adx-coordinator","/opt/adx/current/bin/adx-apiserver"]
 pins={p:assets[p]["sha256"]for p in paths};pins["/usr/local/bin/sandboxd"]=im["sandboxd_sha256"]
 for pod in [p for p in live if p["metadata"]["name"].startswith("akernel-node-")]:
  text=lab("payload-"+pod["metadata"]["name"],["kubectl","-n","akernel","exec",pod["metadata"]["name"],"--","sha256sum",*paths])
  if {x.split()[1]:x.split()[0]for x in text.splitlines()if len(x.split())==2}!=pins:raise RuntimeError("actual payload mismatch")
 r["deployed"]=True;status("official-sdk")
 run("official-sdk",B+["bash",str(O/"sdk-full01.sh")],4500)
 if json.loads((O/"official-sdk/terminal.json").read_text()).get("rc")!=0:raise RuntimeError("official SDK did not finish")
 for rt,node in [("firecracker",nodes[1]),("runsc",nodes[0])]:
  no_env();status("state-and-phases-"+rt)
  job=N/"acceptance/runs"/("shared-io-cut-sdk02-"+rt+"-three")
  shell='set -eu; source "'+str(Q/"acceptance/auth-shared-tapfix-direct01/sdk.env")+'"; export PYTHONPATH="'+str(Q/"acceptance/scripts")+'"; export PYTHONDONTWRITEBYTECODE=1; export XDG_CACHE_HOME="'+str(O/"cache")+'"; exec "'+str(Q/"sdk/client/bin/python")+'" "'+str(O/"sdk-performance01.py")+'" --runtime '+rt+' --variant new-io-cut-candidate --node-id '+node+' --rounds 3 --output "'+str(job)+'"'
  run("state-three-"+rt,B+["bash","-c",shell],1800)
  data=json.loads((job/"terminal.json").read_text())
  if data.get("rc")!=0 or len(data.get("rounds",[]))!=3:raise RuntimeError("state rounds incomplete")
  r["cases"].append(data)
 no_env();(O/"same-node-accepted.json").write_text(json.dumps({"rc":0,"shared_sdk_accepted":True,"candidate":im["image"]}))
 status("bidirectional-sdk-failover")
 run("cross-node",["python3",str(O/"cross-node01.py")],7200)
 cross_result=json.loads((O/"cross-node01/terminal.json").read_text())
 if cross_result.get("rc")!=0 or not cross_result.get("cross_node_accepted"):raise RuntimeError("bidirectional failover incomplete")
 no_env();r.update(rc=0,status="candidate-full-sdk-state-and-bidirectional-failover-passed",cross_node=cross_result,full_sdk_accepted=True,concurrent_guest_direct_io_stress_accepted=False,remaining="real guest concurrent write stress and performance cost; new RWFS routes not accepted")
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
finally:(O/"terminal.json").write_text(json.dumps(r,indent=2))
sys.exit(r["rc"])
