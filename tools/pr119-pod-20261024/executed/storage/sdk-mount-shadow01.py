#!/usr/bin/env python3
import argparse,json,os,pathlib,subprocess,sys,time,uuid
from akernel_sdk import Sandbox
from adx_environment import ConnectionConfig,Environment
from acceptance import same_state
from read_control_state import read_control_state
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";S=Q/"tap-checksum-fix/storage";B=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"]
LETTERS={"akcr119-20261022-worker":"a","akcr119-20261022-worker2":"b"}
def run(argv,timeout=90):
 p=subprocess.run(B+argv,text=True,capture_output=True,timeout=timeout)
 if p.returncode:raise RuntimeError({"command":argv[:8],"rc":p.returncode,"stderr_bytes":len(p.stderr)})
 return p.stdout
def state():return read_control_state(N)[1]
def main():
 p=argparse.ArgumentParser();p.add_argument("--runtime",choices=["runsc","firecracker"],required=True);p.add_argument("--output",type=pathlib.Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.relative_to(N/"acceptance/runs");out.mkdir(mode=0o700);ev=(out/"events.jsonl").open("x",buffering=1)
 def emit(event,**d):ev.write(json.dumps({"event":event,"unix_ns":time.time_ns(),**d})+"\n")
 conn=ConnectionConfig(server_address=os.environ["AKERNEL_SERVER_ADDRESS"],token=os.environ["AKERNEL_TOKEN"],use_tls=True,gateway_address=os.environ.get("AKERNEL_GATEWAY_ADDRESS"),verify_tls=True)
 source=None;snapshots=[];hostwork=None;nodework=None;pod=None
 result={"rc":1,"runtime":a.runtime,"diagnostic_not_performance":True,"full_lifecycle_fault_matrix_passed":False,"fault":"task Pod only: complete writable local directory shadows JuiceFS mount"}
 def resources():(out/"resources.private.json").write_text(json.dumps({"source":None if source is None else source.id,"snapshots":snapshots,"pod":pod,"hostwork":None if hostwork is None else str(hostwork),"nodework":nodework},indent=2))
 def command(cmd):
  r=source.commands.run(cmd,timeout=240)
  if r.exit_code:raise RuntimeError({"command":cmd,"rc":r.exit_code,"stderr":r.stderr[-1000:]})
  return r.stdout
 def memory():
  v=json.loads(command("/tmp/pr119-mount-probe state"))
  if v["http_status"]!=200:raise AssertionError(v)
  return json.loads(v["body"])
 def py(code):return json.loads(run(["kubectl","-n","akernel","exec",pod,"--","python3","-c",code]))
 try:
  if any(k.startswith("environment:") for k in state()):raise RuntimeError("another Environment exists")
  source=Sandbox(runtime=a.runtime,cpu=1000,memory=2048,storage_mb=1024,idle_timeout=900,failover=True);resources()
  source.files.write("/tmp/pr119-mount-probe",(N/"acceptance/bin/guest-probe").read_bytes());command("chmod 700 /tmp/pr119-mount-probe")
  source.commands.run("/tmp/pr119-mount-probe hold --bytes 536870912 >/tmp/pr119-mount-hold.log 2>&1",background=True)
  deadline=time.monotonic()+120
  while True:
   try:before=memory();break
   except Exception:
    if time.monotonic()>deadline:raise
    time.sleep(.5)
  root="/pr119-mount-root";source.files.write(root,"known-before-fault")
  marker="mount-"+a.runtime+"-"+uuid.uuid4().hex[:12]
  origin=Environment.from_id(source.id,connection=conn);known=origin.create_snapshot(name=marker+"-known",timeout_seconds=180);snapshots.append(known.snapshot_id);resources()
  command("/tmp/pr119-mount-probe mutate");live=memory();source.files.write(root,"live-uncheckpointed-state")
  record=state()["environment:"+source.id];node=record["assignment"]["node_id"];logical_runtime=record["result"]["runtime"]["id"]
  pods=json.loads(run(["kubectl","-n","akernel","get","pods","-o","json"]))["items"];items=[x for x in pods if x["metadata"]["name"].startswith("akernel-node-") and x["spec"].get("nodeName")==node]
  if len(items)!=1 or items[0]["spec"].get("hostPID",False):raise RuntimeError("owned Node Pod identity changed")
  pod=items[0]["metadata"]["name"]
  nodework="/home/akernel/.pr119-owned-fault/"+marker;hostwork=N/"node-data09"/LETTERS[node]/"akernel/variants/tapfix/.pr119-owned-fault"/marker;resources()
  pre=py('import os,pathlib,json;d="/mnt/akernel-shared";fd=os.open(d,os.O_PATH|os.O_DIRECTORY);line=next(s for s in pathlib.Path("/proc/self/fdinfo/"+str(fd)).read_text().splitlines() if s.startswith("mnt_id:"));os.close(fd);print(json.dumps({"namespace":os.readlink("/proc/self/ns/mnt"),"mount_id":int(line.split()[1])}))')
  starter='import pathlib,os,subprocess,json;w=pathlib.Path('+repr(nodework)+');w.parent.mkdir(mode=0o700,exist_ok=True);w.mkdir(mode=0o700);script=w/"watchdog.py";script.write_text('+repr((S/"shadow-owned-shared-mount01.py").read_text())+');so=(w/"watchdog.stdout").open("x");se=(w/"watchdog.stderr").open("x");p=subprocess.Popen(["python3",str(script),"--work",str(w),"--namespace",'+repr(pre["namespace"])+',"--expected-mount",'+repr(str(pre["mount_id"]))+'],stdin=subprocess.DEVNULL,stdout=so,stderr=se,start_new_session=True);r={"pid":p.pid,"start_ticks":pathlib.Path("/proc/"+str(p.pid)+"/stat").read_text().split()[21]};(w/"launch.json").write_text(json.dumps(r));print(json.dumps(r))'
  started=py(starter);(out/"watchdog-launch.json").write_text(json.dumps(started,indent=2))
  deadline=time.monotonic()+15
  while not (hostwork/"watchdog/shadowed.json").exists():
   if (hostwork/"watchdog/terminal.json").exists():raise RuntimeError("mount watchdog refused preflight; no checkpoint attempted")
   if time.monotonic()>deadline:raise TimeoutError("task bind shadow not observed")
   time.sleep(.1)
  sh=json.loads((hostwork/"watchdog/shadowed.json").read_text());emit("owned_pod_mount_shadowed",original_mount_id=pre["mount_id"],writable_fallback_prefix=True)
  try:bad=origin.create_snapshot(name=marker+"-denied",timeout_seconds=30)
  except Exception as e:
   emit("snapshot_rejected_while_mount_shadowed",code=getattr(e,"code",None),status_code=getattr(e,"status_code",None),retry=getattr(e,"retry",None),outcome=getattr(e,"outcome",None))
  else:snapshots.append(bad.snapshot_id);resources();raise AssertionError("snapshot reported success while configured shared mount was shadowed")
  returned=time.time_ns()
  deadline=time.monotonic()+35
  while not (hostwork/"watchdog/terminal.json").exists():
   if time.monotonic()>deadline:raise TimeoutError("owned bind was not safely popped; preserve source and dependencies")
   time.sleep(.2)
  wd=json.loads((hostwork/"watchdog/terminal.json").read_text());(out/"watchdog-result.json").write_text(json.dumps(wd,indent=2))
  if wd.get("rc")!=0 or not wd.get("restored_original_mount") or not wd.get("no_local_fallback_entries_created"):raise AssertionError("mount restoration or no-local-write proof failed")
  if not sh["shadowed_unix_ns"]<=returned<wd["restored_unix_ns"]:raise AssertionError("request returned outside the controlled shadow interval; no temporal proof")
  entries,page=Environment.list_snapshots(name=marker+"-denied",connection=conn)
  if entries or page:raise AssertionError("rejected request published a reusable snapshot")
  deadline=time.monotonic()+120;stable=0
  while True:
   control=state();r=control.get("environment:"+source.id);nodes=[v for k,v in control.items() if k.startswith("node:") and v.get("node",{}).get("id")==node]
   good=r and r["result"]["state"]=="Running" and r["result"]["runtime"]["id"]==logical_runtime and len(nodes)==1 and nodes[0]["node"].get("available") is True and nodes[0].get("session",{}).get("routable") is True
   stable=stable+1 if good else 0
   if stable>=3:break
   if time.monotonic()>deadline:raise TimeoutError("original source did not remain available after mount restoration")
   time.sleep(.5)
  same_state(live,memory())
  if source.files.read(root)!="live-uncheckpointed-state":raise AssertionError("source uncheckpointed root state changed")
  recovered=origin.create_snapshot(name=marker+"-recovered",timeout_seconds=180);snapshots.append(recovered.snapshot_id);resources()
  source.kill();source=None;resources()
  for sid in snapshots:Environment.delete_snapshot(sid,connection=conn)
  deadline=time.monotonic()+180
  while True:
   gone=0
   for sid in snapshots:
    try:Environment.get_snapshot(sid,connection=conn)
    except Exception as e:
     if str(getattr(e,"code","")).upper()=="NOT_FOUND":gone+=1
     else:raise
   if gone==len(snapshots) and not any(k.startswith("environment:") for k in state()):break
   if time.monotonic()>deadline:raise TimeoutError("mount fault resources did not retire")
   time.sleep(1)
  result.update(rc=0,memory_bytes=536870912,request_rejected_inside_shadow_interval=True,no_published_snapshot=True,no_local_fallback_entries=True,original_mount_restored=True,uncheckpointed_source_state_preserved=True,new_distinct_snapshot_after_recovery=True,resources_deleted=True)
 except BaseException as e:result.update(error_type=type(e).__name__,error=str(e));emit("acceptance_failed",error_type=type(e).__name__,error=str(e))
 finally:
  if hostwork is not None:
   deadline=time.monotonic()+30
   while not (hostwork/"watchdog/terminal.json").exists() and time.monotonic()<deadline:time.sleep(.2)
   if (hostwork/"watchdog/terminal.json").exists():
    result["mount_fault_restored"]=json.loads((hostwork/"watchdog/terminal.json").read_text()).get("restored_original_mount",False)
  resources();(out/"terminal.json").write_text(json.dumps(result,indent=2));ev.close()
 return result["rc"]
if __name__=="__main__":sys.exit(main())
