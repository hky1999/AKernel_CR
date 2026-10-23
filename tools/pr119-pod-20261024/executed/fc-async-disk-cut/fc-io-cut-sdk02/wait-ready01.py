
import argparse,hashlib,json,pathlib,subprocess,sys,time,urllib.parse
Q=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp/round-365f797-20261023.clPWh2h0");N=Q.parent
sys.path.insert(0,str(Q/"acceptance/scripts"))
from read_control_state import read_control_state
p=argparse.ArgumentParser()
p.add_argument("--output",type=pathlib.Path,required=True)
p.add_argument("--previous-session-hashes",type=pathlib.Path,required=True)
p.add_argument("--timeout",type=int,default=240)
p.add_argument("--expected-digest",choices=['sha256:ff06cd24c136d5252da0ece6aea74c9db21a38c69c613d0b22651ddf0a921884'],required=True)
args=p.parse_args();out=args.output.resolve();out.relative_to(Q/"tap-checksum-fix")
out.mkdir(mode=0o700)
old=json.loads(args.previous_session_hashes.read_text())
expected={"akcr119-20261022-worker","akcr119-20261022-worker2"}
if set(old)!=expected:raise RuntimeError("previous session identities are incomplete")
base=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"]
def kubectl(*cmd):
 r=subprocess.run(base+["kubectl","-n","akernel",*cmd],text=True,capture_output=True,timeout=45)
 if r.returncode:raise RuntimeError("owned Kubernetes query failed: "+r.stderr[-500:])
 return r.stdout
def address_host(value):
 if not isinstance(value,str):return None
 return urllib.parse.urlsplit(value if "://" in value else "//"+value).hostname
deadline=time.monotonic()+args.timeout;stable=0;previous_marker=None;last=None
with (out/"observations.jsonl").open("x",buffering=1) as log:
 while True:
  records=read_control_state(N)[1]
  busy=[k for k,v in records.items() if k.startswith("environment:") and (v.get("result",{}).get("state") not in ["Failed","Deleted"] or v.get("result",{}).get("resources_held") or v.get("result",{}).get("restart_pending"))]
  pods=json.loads(kubectl("get","pods","-o","json"))["items"]
  candidates=[p for p in pods if p["metadata"]["name"].startswith("akernel-node-") and not p["metadata"].get("deletionTimestamp")]
  states=[];marker=[]
  for node_id in sorted(expected):
   reasons=[];node_pods=[p for p in candidates if p["spec"].get("nodeName")==node_id]
   pod=node_pods[0] if len(node_pods)==1 else None
   if pod is None:reasons.append("node Pod identity is not unique")
   value=records.get("node:"+node_id,{})
   info=value.get("node",{});session=value.get("session",{})
   sid=session.get("id");session_hash=hashlib.sha256(str(sid).encode()).hexdigest()
   if not sid or session_hash==old[node_id]:reasons.append("new ADX session not registered")
   if session.get("routable") is not True:reasons.append("ADX session not routable")
   if value.get("scheduling_paused") is not False:reasons.append("scheduling paused or unknown")
   if info.get("available") is not True:reasons.append("ADX node unavailable")
   if info.get("id")!=node_id or info.get("labels",{}).get("NODE_ID")!=node_id:reasons.append("ADX node identity mismatch")
   if not {"runsc","firecracker"}.issubset(set(info.get("runtime_classes",[]))):reasons.append("runtime capabilities missing")
   capacity=info.get("capacity",{})
   for k,minimum in {"cpu_millis":1000,"memory_bytes":2147483648,"disk_bytes":1073741824}.items():
    if not isinstance(capacity.get(k),int) or capacity[k]<minimum:reasons.append("insufficient "+k)
   uid=None;pod_name=None
   if pod:
    uid=pod["metadata"]["uid"];pod_name=pod["metadata"]["name"];ip=pod["status"].get("podIP")
    statuses=pod["status"].get("containerStatuses",[])
    if pod["status"].get("phase")!="Running" or not statuses or not all(s.get("ready") for s in statuses):reasons.append("Pod not ready")
    if not ip or address_host(value.get("address"))!=ip or address_host(value.get("proxy_address"))!=ip:reasons.append("ADX route does not match current Pod")
    if any(s.get("imageID","").rsplit("@",1)[-1]!=args.expected_digest for s in statuses):reasons.append("candidate image identity mismatch")
   states.append({"node_id":node_id,"pod":pod_name,"pod_uid":uid,"session_hash":session_hash,"ready":not reasons,"reasons":reasons,"capacity":capacity})
   marker.append((node_id,uid,session_hash))
  ready=not busy and all(s["ready"] for s in states)
  stable=stable+1 if ready and marker==previous_marker else (1 if ready else 0)
  previous_marker=marker;last={"at_unix_ns":time.time_ns(),"ready":ready,"stable_samples":stable,"busy_environments":busy,"nodes":states}
  log.write(json.dumps(last)+"\n")
  if stable>=3:break
  if time.monotonic()>deadline:
   (out/"terminal.json").write_text(json.dumps({"rc":1,"status":"not-ready","last":last},indent=2));raise TimeoutError("real ADX readiness gate did not pass; no automatic restart")
  time.sleep(2)
for s in last["nodes"]:
 data=kubectl("exec",s["pod"],"--","sha256sum","/usr/local/bin/sandboxd")
 if data.split()[0]!="c85d58b2efe8c141394877cc73cdb33cd796d7760770a31c808fbd6c22fb5dce":raise RuntimeError("live daemon ELF differs")
(out/"terminal.json").write_text(json.dumps({"rc":0,"status":"fresh-routable-resource-ready","snapshot":last},indent=2))
print(json.dumps({"status":"fresh-routable-resource-ready","stable_samples":stable,"nodes":[s["node_id"] for s in last["nodes"]]}))
