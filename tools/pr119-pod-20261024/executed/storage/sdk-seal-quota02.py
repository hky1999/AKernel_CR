#!/usr/bin/env python3
"""Task-private JuiceFS manifest inode-quota fault; never changes shared services."""
import argparse,errno,hashlib,json,os,pathlib,subprocess,sys,time,uuid
from akernel_sdk import Sandbox
from adx_environment import ConnectionConfig,Environment
from read_control_state import read_control_state
from acceptance import same_state
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp")
Q=N/"round-365f797-20261023.clPWh2h0"
BASE=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"]
def run(argv,timeout=90):
 p=subprocess.run(BASE+argv,text=True,capture_output=True,timeout=timeout)
 if p.returncode:raise RuntimeError({"rc":p.returncode,"argv":argv,"stderr_bytes":len(p.stderr)})
 return p.stdout
def state():return read_control_state(N)[1]
def main():
 a=argparse.ArgumentParser();a.add_argument("--runtime",choices=["runsc","firecracker"],required=True);a.add_argument("--output",type=pathlib.Path,required=True);a=a.parse_args()
 out=a.output.resolve();out.relative_to(N/"acceptance/runs");out.mkdir(mode=0o700)
 events=(out/"events.jsonl").open("x",buffering=1)
 def emit(event,**v):events.write(json.dumps({"event":event,"unix_ns":time.time_ns(),**v})+"\n")
 result={"rc":1,"runtime":a.runtime,"fault":"owned-volume manifests directory inode quota","diagnostic_not_performance":True,"full_lifecycle_fault_matrix_passed":False}
 source=None;quota_may_be_set=False;quota_restored=False;sentinel=None;source_pod=None;snapshots=[];fault_error=None
 conn=ConnectionConfig(server_address=os.environ["AKERNEL_SERVER_ADDRESS"],token=os.environ["AKERNEL_TOKEN"],use_tls=True,gateway_address=os.environ.get("AKERNEL_GATEWAY_ADDRESS"),verify_tls=True)
 def resources():
  (out/"resources.private.json").write_text(json.dumps({"source":None if source is None else source.id,"snapshots":snapshots,"quota_may_be_set":quota_may_be_set,"quota_restored":quota_restored,"sentinel":sentinel,"source_pod":source_pod},indent=2))
 def command(env,text,timeout=120):
  r=env.commands.run(text,timeout=timeout)
  if r.exit_code:raise AssertionError({"command":text,"exit_code":r.exit_code,"stderr":r.stderr[-1000:]})
  return r.stdout
 def memory(env):
  v=json.loads(command(env,"/tmp/pr119-seal-probe state"))
  if v["http_status"]!=200:raise AssertionError(v)
  return json.loads(v["body"])
 def kube_py(code):return json.loads(run(["kubectl","-n","akernel","exec",source_pod,"--","python3","-c",code]))
 def quota(action):
  script='test -n "$META_URL" && exec juicefs --no-agent --no-color quota '+action+' "$META_URL" --path /akernel/checkpoints/manifests'
  p=subprocess.run(BASE+["kubectl","-n","akernel-pr119-storage","exec","daemonset/akcr119-juicefs-client","-c","juicefs","--","/bin/sh","-c",script],text=True,capture_output=True,timeout=90)
  (out/("quota-"+action.split()[0]+"-"+str(time.time_ns())+".stdout")).write_text(p.stdout)
  # Do not persist a metadata URL or credentials in stderr.
  emit("quota_command",action=action,rc=p.returncode,stderr_bytes=len(p.stderr))
  if p.returncode:raise RuntimeError("task directory quota "+action+" failed, stderr retained only in client pod logs")
  return p.stdout
 def inventory():
  return kube_py('import pathlib,json; r=pathlib.Path("/mnt/akernel-shared/akernel/checkpoints"); print(json.dumps({"artifacts":{p.name:{"files":[x.name for x in p.iterdir()],"size":sum(x.stat().st_size for x in p.rglob("*") if x.is_file())} for p in (r/"artifacts").iterdir() if p.is_dir()},"manifests":[p.name for p in (r/"manifests").iterdir()]}))')
 try:
  if any(k.startswith("environment:") for k in state()):raise RuntimeError("another Environment exists")
  # No existing quota is silently replaced.
  p=subprocess.run(BASE+["kubectl","-n","akernel-pr119-storage","exec","daemonset/akcr119-juicefs-client","-c","juicefs","--","/bin/sh","-c",'test -n "$META_URL" && exec juicefs --no-agent --no-color quota list "$META_URL"'],text=True,capture_output=True,timeout=90)
  if p.returncode or p.stdout.strip():raise RuntimeError("quota list not empty; refuse to replace any existing quota")
  marker="pr119-sealfail-"+a.runtime+"-"+uuid.uuid4().hex[:10]
  source=Sandbox(runtime=a.runtime,cpu=1000,memory=2048,storage_mb=1024,idle_timeout=900,failover=True);resources()
  source.files.write("/tmp/pr119-seal-probe",(N/"acceptance/bin/guest-probe").read_bytes());command(source,"chmod 700 /tmp/pr119-seal-probe")
  source.commands.run("/tmp/pr119-seal-probe hold --bytes 536870912 >/tmp/pr119-seal-hold.log 2>&1",background=True)
  deadline=time.monotonic()+90
  while True:
   try:initial=memory(source);break
   except Exception:
    if time.monotonic()>deadline:raise
    time.sleep(.5)
  root="/pr119-seal-root";source.files.write(root,"before-fault")
  origin=Environment.from_id(source.id,connection=conn)
  first=origin.create_snapshot(name=marker+"-known-good",timeout_seconds=180);snapshots.append(first.snapshot_id);resources()
  record=state()["environment:"+source.id];node=record["assignment"]["node_id"]
  pods=json.loads(run(["kubectl","-n","akernel","get","pods","-o","json"]))["items"]
  matches=[p["metadata"]["name"] for p in pods if p["metadata"]["name"].startswith("akernel-node-") and p["spec"].get("nodeName")==node]
  if len(matches)!=1:raise RuntimeError("source Pod not unique")
  source_pod=matches[0]
  command(source,"/tmp/pr119-seal-probe mutate");live=memory(source);source.files.write(root,"uncheckpointed-state-must-stay")
  before=inventory();(out/"before-fault-inventory.private.json").write_text(json.dumps(before,indent=2))
  sentinel="/mnt/akernel-shared/akernel/checkpoints/manifests/."+marker+"-sentinel"
  kube_py("import os,json; f=os.open("+repr(sentinel)+",os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(f); print(json.dumps({'created':True}))")
  quota_may_be_set=True;resources();quota("set --inodes 1")
  # Wait for the same source client's metadata quota to actually deny creation.
  deadline=time.monotonic()+60
  while True:
   probe=sentinel+"-probe"
   code="import os,json\np="+repr(probe)+"\ntry:\n f=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(f);os.unlink(p);print(json.dumps({'created':True}))\nexcept OSError as e: print(json.dumps({'errno':e.errno}))"
   denial=kube_py(code)
   if denial.get("errno")==errno.EDQUOT:break
   if denial.get("errno"):raise AssertionError({"unexpected_probe_error":denial})
   if time.monotonic()>deadline:raise TimeoutError("directory quota never became effective in the source client")
   time.sleep(1)
  emit("manifest_create_denied",errno=errno.EDQUOT)
  (out/"state-before-fault.private.json").write_text(json.dumps(state(),indent=2))
  try:
   failed=origin.create_snapshot(name=marker+"-injected-failure",timeout_seconds=180)
  except Exception as e:
   fault_error={k:getattr(e,k,None) for k in ["code","retry","outcome","status_code","request_id","operation_id","environment_id"]}
   fault_error["type"]=type(e).__name__;fault_error["message"]=str(e)
   (out/"fault-error.private.json").write_text(json.dumps(fault_error,indent=2))
   emit("snapshot_request_failed",**{k:v for k,v in fault_error.items() if k not in ["message","request_id","operation_id","environment_id"]})
  else:
   snapshots.append(failed.snapshot_id);resources();raise AssertionError("snapshot reported success with manifest creation denied")
  after=inventory();(out/"after-fault-inventory.private.json").write_text(json.dumps(after,indent=2))
  (out/"state-after-fault.private.json").write_text(json.dumps(state(),indent=2))
  new=set(after["artifacts"])-set(before["artifacts"])
  unsealed=[k for k in new if k+".json" not in after["manifests"] and after["artifacts"][k]["size"]>0]
  result["unsealed_nonempty_capture_count"]=len(unsealed)
  result["unsealed_logical_bytes"]=[after["artifacts"][k]["size"] for k in unsealed]
  if not unsealed:raise AssertionError("no nonempty unsealed output observed; late seal failure not proven")
  # Restore only the quota installed by this attempt, before further lifecycle work.
  quota("delete");quota_may_be_set=False;quota_restored=True;resources()
  deadline=time.monotonic()+60
  while True:
   try:
    kube_py("import os,json;f=os.open("+repr(sentinel+"-restored")+",os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(f);os.unlink("+repr(sentinel+"-restored")+");print(json.dumps({'created':True}))");break
   except Exception:
    if time.monotonic()>deadline:raise
    time.sleep(1)
  # A new distinct operation is allowed only after reconciling the failed name.
  listing=Environment.list_snapshots(name=marker+"-injected-failure",connection=conn)
  (out/"failed-name-list.private.json").write_text(json.dumps(str(listing)))
  if not isinstance(listing,tuple) or len(listing)!=2:raise AssertionError("unexpected native Snapshot list shape")
  items,next_page=listing
  if next_page or items:raise AssertionError("failed name unexpectedly has a reusable published Snapshot or more pages")
  same_state(live,memory(source))
  if source.files.read(root)!="uncheckpointed-state-must-stay":raise AssertionError("source live state rolled back")
  recovered=origin.create_snapshot(name=marker+"-after-recovery",timeout_seconds=180);snapshots.append(recovered.snapshot_id);resources()
  emit("new_snapshot_after_quota_removal_succeeded")
  source.kill();source=None;resources()
  for sid in snapshots:
   Environment.delete_snapshot(sid,connection=conn)
  deadline=time.monotonic()+180
  while True:
   missing=0
   for sid in snapshots:
    try:Environment.get_snapshot(sid,connection=conn)
    except Exception as e:
     if str(getattr(e,"code","")).upper()=="NOT_FOUND":missing+=1
     else:raise
   if missing==len(snapshots):break
   if time.monotonic()>deadline:raise TimeoutError("known snapshots not deleted")
   time.sleep(1)
  kube_py("import os,json;os.unlink("+repr(sentinel)+");print(json.dumps({'removed':True}))");sentinel=None
  if any(k.startswith("environment:") for k in state()):raise AssertionError("Environment remains")
  result.update(rc=0,failed_snapshot_not_published=True,live_source_preserved=True,quota_restored=True,new_distinct_snapshot_after_recovery=True,known_snapshots_deleted=True,environment_count_after_cleanup=0)
 except BaseException as e:
  result.update(error_type=type(e).__name__,error=str(e));emit("acceptance_failed",error_type=type(e).__name__,error=str(e))
 finally:
  if quota_may_be_set:
   try:
    quota("delete");quota_may_be_set=False;quota_restored=True;emit("fault_quota_removed_in_rescue")
   except Exception as e:result["quota_restore_error"]=str(e)
  result["quota_restored"]=quota_restored
  resources();(out/"terminal.json").write_text(json.dumps(result,indent=2));events.close()
 return result["rc"]
if __name__=="__main__":sys.exit(main())
