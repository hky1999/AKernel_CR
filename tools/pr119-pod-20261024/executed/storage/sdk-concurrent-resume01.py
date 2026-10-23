#!/usr/bin/env python3
"""Eight independent existing SDK handles resume one paused Environment."""
import argparse,hashlib,json,os,pathlib,subprocess,sys,threading,time
from concurrent.futures import ThreadPoolExecutor
from akernel_sdk import Sandbox
from adx_environment import ConnectionConfig,Environment
from acceptance import same_state
from read_control_state import read_control_state
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";B=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"]
def run(argv,timeout=90):
 p=subprocess.run(B+argv,text=True,capture_output=True,timeout=timeout)
 if p.returncode:raise RuntimeError({"command":argv,"rc":p.returncode,"stderr_bytes":len(p.stderr)})
 return p.stdout
def state():return read_control_state(N)[1]
def main():
 p=argparse.ArgumentParser();p.add_argument("--runtime",choices=["runsc","firecracker"],required=True);p.add_argument("--output",type=pathlib.Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.relative_to(N/"acceptance/runs");out.mkdir(mode=0o700);ev=(out/"events.jsonl").open("x",buffering=1)
 def emit(event,**d):ev.write(json.dumps({"event":event,"unix_ns":time.time_ns(),**d})+"\n")
 conn=ConnectionConfig(server_address=os.environ["AKERNEL_SERVER_ADDRESS"],token=os.environ["AKERNEL_TOKEN"],use_tls=True,gateway_address=os.environ.get("AKERNEL_GATEWAY_ADDRESS"),verify_tls=True)
 source=None;handles=[];origin=None;result={"rc":1,"runtime":a.runtime,"diagnostic_not_performance":True,"concurrent_resume_handles":8,"rounds":[],"full_lifecycle_fault_matrix_passed":False}
 def resources():(out/"resources.private.json").write_text(json.dumps({"source":None if source is None else source.id},indent=2))
 def command(cmd,timeout=240):
  r=source.commands.run(cmd,timeout=timeout)
  if r.exit_code:raise RuntimeError({"command":cmd,"rc":r.exit_code,"stderr":r.stderr[-1500:]})
  return r.stdout
 def memory():
  v=json.loads(command("/tmp/pr119-concurrent-probe state"))
  if v["http_status"]!=200:raise AssertionError(v)
  return json.loads(v["body"])
 def observe():
  pods=json.loads(run(["kubectl","-n","akernel","get","pods","-o","json"]))["items"];nodes=[x["metadata"]["name"] for x in pods if x["metadata"]["name"].startswith("akernel-node-")]
  if len(nodes)!=2:raise RuntimeError("owned two-node workload no longer matches")
  rows=[];traces=set()
  for pod in nodes:
   code='import pathlib,os,json,re,hashlib;eid='+repr(source.id)+';ids=[];vms=[]\nfor d in pathlib.Path("/home/akernel/sandboxd/root/containers").iterdir():\n try:\n  a=json.loads((d/"config.json").read_text()).get("annotations",{})\n  if a.get("adx.environment_id")==eid:ids.append(d.name)\n except (OSError,ValueError):pass\nfor p in pathlib.Path("/proc").iterdir():\n if not p.name.isdigit():continue\n try:\n  cmd=(p/"cmdline").read_bytes().split(b"\\0");exe=os.path.basename(os.fsdecode(cmd[0]))\n  if exe in ["runsc-sandbox","firecracker"] and any(any(i in os.fsdecode(x) for x in cmd) for i in ids):vms.append({"pid":int(p.name),"start_ticks":(p/"stat").read_text().split()[21]})\n except (OSError,ValueError):pass\ntraces=[]\np=pathlib.Path("/home/akernel/logs/sandboxd/sandboxd.log")\nfor line in p.read_text().splitlines():\n if "/runtime.v1.SandboxService/Start request" not in line or eid not in line:continue\n m=re.search(r"TRACEID=([0-9a-f]+)",line)\n if not m:raise RuntimeError("Start request lacks a trace identity")\n traces.append(hashlib.sha256(m.group(1).encode()).hexdigest())\nprint(json.dumps({"runtime_processes":vms,"start_trace_sha256":sorted(set(traces))}))'
   v=json.loads(run(["kubectl","-n","akernel","exec",pod,"--","python3","-c",code]));rows.extend({"pod":pod,**x} for x in v["runtime_processes"]);traces.update(v["start_trace_sha256"])
  return {"runtime_processes":rows,"start_trace_sha256":sorted(traces)}
 try:
  if any(k.startswith("environment:") for k in state()):raise RuntimeError("another Environment exists")
  source=Sandbox(runtime=a.runtime,cpu=1000,memory=2048,storage_mb=1024,idle_timeout=900,failover=True);resources()
  source.files.write("/tmp/pr119-concurrent-probe",(N/"acceptance/bin/guest-probe").read_bytes());command("chmod 700 /tmp/pr119-concurrent-probe")
  source.commands.run("/tmp/pr119-concurrent-probe hold --bytes 536870912 >/tmp/pr119-concurrent.log 2>&1",background=True)
  deadline=time.monotonic()+120
  while True:
   try:before=memory();break
   except Exception:
    if time.monotonic()>deadline:raise
    time.sleep(.5)
  origin=Environment.from_id(source.id,connection=conn)
  for i in range(3):
   root="/pr119-concurrent-root";marker="generation-"+str(i);source.files.write(root,marker);before=memory()
   handles=[Environment.from_id(source.id,connection=conn) for _ in range(8)]
   initial=observe()
   if len(initial["runtime_processes"])!=1:raise AssertionError("source runtime is not unique before pause")
   paused=origin.pause(timeout_seconds=180)
   if paused.state!="paused" or paused.environment_id!=source.id:raise AssertionError("native pause did not acknowledge the exact source")
   stopped=observe()
   if stopped["runtime_processes"]:raise AssertionError("old source runtime still alive after pause")
   current=state()["environment:"+source.id]
   if current["result"]["state"]!="Paused":raise AssertionError("authority is not Paused")
   gate=threading.Barrier(8)
   def resume(handle):
    gate.wait(timeout=30)
    try:
     r=handle.resume()
     return {"ok":True,"environment_id":r.environment_id,"state":r.state,"node_id":r.node_id}
    except Exception as e:
     x=e;visited=set()
     while x is not None and id(x) not in visited:
      visited.add(id(x))
      if getattr(x,"code",None):
       if str(x.code).upper()=="CONFLICT" and getattr(x,"retry",None)=="never" and getattr(x,"outcome",None)=="not_started":
        return {"ok":False,"code":"CONFLICT","retry":x.retry,"outcome":x.outcome}
       raise
      x=getattr(x,"__cause__",None)
     raise
   with ThreadPoolExecutor(max_workers=8) as pool:replies=list(pool.map(resume,handles))
   current=state()["environment:"+source.id];assigned=current["assignment"]["node_id"]
   if current["result"]["state"]!="Running":raise AssertionError("authority not Running after concurrent resume")
   successes=[x for x in replies if x["ok"]];conflicts=[x for x in replies if not x["ok"]]
   if not successes or any(x["environment_id"]!=source.id or x["state"]!="running" or x["node_id"]!=assigned for x in successes):raise AssertionError("resume winners disagree about the logical identity or placement")
   if len(successes)+len(conflicts)!=8:raise AssertionError("unclassified concurrent resume result")
   after=observe();delta=set(after["start_trace_sha256"])-set(initial["start_trace_sha256"])
   (out/("round-"+str(i)+"-observations.private.json")).write_text(json.dumps({"before":initial,"paused":stopped,"after":after,"replies":replies},indent=2))
   if len(after["runtime_processes"])!=1:raise AssertionError("multiple runtime processes remained after concurrent resume")
   if len(delta)!=1:raise AssertionError("eight simultaneous resumes did not reduce to one sandboxd Start request")
   if source.files.read(root)!=marker:raise AssertionError("public SDK root content changed during native concurrent resume")
   same_state(before,memory())
   row={"round":i,"resume_successes":len(successes),"not_started_conflicts":len(conflicts),"logical_requests":8,"underlying_start_requests":len(delta),"final_runtime_processes":len(after["runtime_processes"]),"full_state_verified":True}
   result["rounds"].append(row);emit("concurrent_resume_round_passed",**row)
   for h in handles:h.close()
   handles=[];command("/tmp/pr119-concurrent-probe mutate")
  source.kill();source=None;resources()
  deadline=time.monotonic()+120
  while any(k.startswith("environment:") for k in state()):
   if time.monotonic()>deadline:raise TimeoutError("Environment remained after cleanup")
   time.sleep(.5)
  result.update(rc=0,memory_bytes=536870912,native_control_public_sdk_io=True,resources_deleted=True)
 except BaseException as e:result.update(error_type=type(e).__name__,error=str(e));emit("acceptance_failed",error_type=type(e).__name__,error=str(e))
 finally:
  for h in handles:
   try:h.close()
   except Exception:pass
  if origin is not None:
   try:origin.close()
   except Exception:pass
  resources();(out/"terminal.json").write_text(json.dumps(result,indent=2));ev.close()
 return result["rc"]
if __name__=="__main__":sys.exit(main())
