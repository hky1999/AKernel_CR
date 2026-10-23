#!/usr/bin/env python3
import hashlib,json,os,pathlib,signal,subprocess,sys,time
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp")
Q=N/"round-365f797-20261023.clPWh2h0";D=Q/"tap-checksum-fix";S=D/"storage"
O=S/"cross-node05";O.mkdir(mode=0o700)
BASE=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"]
result={"rc":1,"status":"preflight","coverage":{},"attempts":[],"cross_node_accepted":False}
nodes={"akcr119-20261022-worker","akcr119-20261022-worker2"}
def run(name,argv,timeout):
 with (O/(name+".stdout")).open("x") as so,(O/(name+".stderr")).open("x") as se:
  p=subprocess.Popen(argv,stdout=so,stderr=se,stdin=subprocess.DEVNULL,start_new_session=True)
  record={"pid":p.pid,"start_ticks":pathlib.Path("/proc",str(p.pid),"stat").read_text().rsplit(")",1)[1].split()[19],"argv_sha256":hashlib.sha256(json.dumps(argv).encode()).hexdigest()}
  (O/(name+".process.json")).write_text(json.dumps(record))
  try:rc=p.wait(timeout=timeout)
  except subprocess.TimeoutExpired:
   # This group contains only this recorded acceptance attempt and its children.
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=30)
   except subprocess.TimeoutExpired:raise RuntimeError(name+" failed to stop; retain task dependencies and inspect")
   raise RuntimeError(name+" timed out; inspect before another attempt")
 (O/(name+".terminal.json")).write_text(json.dumps({"rc":rc}))
 if rc:raise RuntimeError(name+" failed; retain failed sandbox and logs")
def ready(name):
 run(name,["python3",str(D/"wait-adx-ready01.py"),"--output",str(O/(name+"-evidence")),"--previous-session-hashes",str(S/"run05/previous-sessions.json"),"--timeout","300"],390)
try:
 gate=json.loads((S/"run06/terminal.json").read_text())
 if gate.get("rc")!=0 or not gate.get("shared_sdk_accepted"):raise RuntimeError("shared same-node SDK has not passed")
 sys.path.insert(0,str(Q/"acceptance/scripts"))
 from read_control_state import read_control_state
 if any(k.startswith("environment:") for k in read_control_state(N)[1]):raise RuntimeError("Environment records remain")
 for runtime in ["runsc","firecracker"]:
  covered=set()
  for attempt in range(1,9):
   name="shared-tapfix-direct01-"+runtime+"-cross-"+str(attempt)
   ready("ready-"+runtime+"-"+str(attempt))
   job=N/"acceptance/runs"/name
   shell='source "'+str(Q/'acceptance/auth-shared-tapfix-direct01/sdk.env')+'"; export PYTHONPATH="'+str(Q/'acceptance/scripts')+':'+str(Q/'source/AKernel/sdk/python')+'"; export PR119_TEST_DISK_RWFS=1; exec "'+str(Q/'sdk/client/bin/python')+'" "'+str(S/'sdk-failover03.py')+'" --task "'+str(N)+'" --runtime '+runtime+' --output "'+str(job)+'"'
   result["status"]="running-"+name
   (O/"current.json").write_text(json.dumps(result,indent=2))
   run(name,BASE+["bash","-euc",shell],1800)
   events=[json.loads(x) for x in (job/"events.jsonl").read_text().splitlines()]
   passed=[e for e in events if e.get("event")=="public_sdk_failover_passed"]
   if len(passed)!=1 or any(e.get("event") in ["acceptance_failed","source_health_check_failed"] for e in events):raise RuntimeError("failover evidence incomplete")
   p=passed[0];direction=(p["source_node"],p["target_node"])
   if set(direction)!=nodes or not p.get("source_offline") or p.get("explicit_reload_called") or p["memory_bytes"]!=536870912:raise RuntimeError("direction or complete state contract failed")
   required={"disk_rwfs_verified","target_survived_source_rejoin","source_healthy_again","sandbox_deleted"}
   if not required.issubset({e.get("event") for e in events}):raise RuntimeError("RWFS/rejoin/cleanup evidence missing")
   covered.add(direction)
   result["attempts"].append({"job":name,"runtime":runtime,"source":direction[0],"target":direction[1],"checkpoint_ms":p["checkpoint_until_http_completed_ms"],"first_file_ms":p["read_trigger_until_first_verified_file_ms"],"full_memory_ms":p["read_trigger_until_full_memory_verified_ms"]})
   result["coverage"][runtime]=[list(x) for x in sorted(covered)]
   (O/"current.json").write_text(json.dumps(result,indent=2))
   if len(covered)==2:break
  if len(covered)!=2:raise RuntimeError(runtime+" lacks bidirectional coverage after eight recorded attempts")
 ready("ready-final")
 result.update(rc=0,status="bidirectional-sdk-failover-passed",cross_node_accepted=True)
except BaseException as e:result.update(error_type=type(e).__name__,error=str(e))
finally:
 result["completed_unix"]=time.time()
 (O/"terminal.json").write_text(json.dumps(result,indent=2))
sys.exit(result["rc"])
