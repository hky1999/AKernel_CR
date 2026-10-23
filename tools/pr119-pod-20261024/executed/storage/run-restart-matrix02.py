#!/usr/bin/env python3
import pathlib,json,subprocess,os,time,sys
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";D=Q/"tap-checksum-fix";S=D/"storage";O=S/"restart-matrix02";O.mkdir(mode=0o700)
BASE=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"]
result={"rc":1,"status":"preflight","cases":[],"full_lifecycle_fault_matrix_passed":False,"diagnostic_not_performance":True}
def run(name,argv,timeout):
 with (O/(name+".stdout")).open("x") as so,(O/(name+".stderr")).open("x") as se:
  p=subprocess.Popen(argv,stdout=so,stderr=se,stdin=subprocess.DEVNULL,start_new_session=True)
  record={"pid":p.pid,"start_ticks":pathlib.Path("/proc",str(p.pid),"stat").read_text().rsplit(")",1)[1].split()[19]}
  (O/(name+".process.json")).write_text(json.dumps(record))
  try:rc=p.wait(timeout=timeout)
  except subprocess.TimeoutExpired:raise RuntimeError(name+" timed out; inspect owned process before any signal or rerun")
 (O/(name+".terminal.json")).write_text(json.dumps({"rc":rc}))
 if rc:raise RuntimeError(name+" failed; retain owned sandbox and diagnostics")
try:
 if json.loads((S/"cross-node05/terminal.json").read_text()).get("rc")!=0:raise RuntimeError("main SDK failover gate has not passed")
 if json.loads((S/"media-diagnostic01/terminal.json").read_text()).get("rc")!=0:raise RuntimeError("media diagnostic not complete")
 for runtime in ["firecracker","runsc"]:
  for action in ["adxlet","coordinator"]:
   name="shared-tapfix-restart02-"+runtime+"-"+action
   run("ready-"+runtime+"-"+action,["python3",str(D/"wait-adx-ready01.py"),"--output",str(O/("ready-"+runtime+"-"+action)),"--previous-session-hashes",str(S/"run05/previous-sessions.json"),"--timeout","300"],390)
   job=N/"acceptance/runs"/name
   shell='set -eu; source "'+str(Q/"acceptance/auth-shared-tapfix-direct01/sdk.env")+'"; export PYTHONPATH="'+str(Q/"acceptance/scripts")+':'+str(Q/"source/AKernel/sdk/python")+'"; exec "'+str(Q/"sdk/client/bin/python")+'" "'+str(S/"sdk-reader-restart02.py")+'" --runtime '+runtime+' --restart '+action+' --output "'+str(job)+'"'
   result["status"]="running-"+name;(O/"current.json").write_text(json.dumps(result,indent=2))
   run(name,BASE+["bash","-c",shell],2400)
   terminal=json.loads((job/"terminal.json").read_text());events=[json.loads(x) for x in (job/"events.jsonl").read_text().splitlines()];names={x["event"] for x in events}
   if terminal.get("rc")!=0 or not {"live_state_and_references_survived_restart","post_restart_checkpoint_reload_passed","sandbox_deleted"}.issubset(names):raise RuntimeError(name+" lacks complete state and cleanup proof")
   result["cases"].append(terminal);(O/"current.json").write_text(json.dumps(result,indent=2))
 result.update(rc=0,status="controller-restart-state-and-reference-matrix-passed",restart_reference_matrix_passed=True,fc_old_reader_coverage_complete=all(x.get("old_checkpoint_reader_observed") for x in result["cases"] if x["runtime"]=="firecracker"))
except BaseException as e:result.update(error_type=type(e).__name__,error=str(e))
finally:
 result["completed_unix"]=time.time();(O/"terminal.json").write_text(json.dumps(result,indent=2))
sys.exit(result["rc"])
