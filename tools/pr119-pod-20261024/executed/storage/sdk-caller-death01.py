#!/usr/bin/env python3
"""Native SDK capture timeout; reconcile once, never blindly replay."""
import argparse,json,os,pathlib,subprocess,sys,time,uuid
from akernel_sdk import Sandbox
from adx_environment import ConnectionConfig,Environment
from acceptance import same_state,completed
from read_control_state import read_control_state
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0"
BASE=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"]
def run(argv,timeout=90):
 p=subprocess.run(BASE+argv,text=True,capture_output=True,timeout=timeout)
 if p.returncode:raise RuntimeError({"rc":p.returncode,"argv":argv,"stderr":p.stderr[-1000:]})
 return p.stdout
def authority():return read_control_state(N)[1]
def main():
 p=argparse.ArgumentParser();p.add_argument("--runtime",choices=["runsc","firecracker"],required=True);p.add_argument("--output",type=pathlib.Path,required=True);p.add_argument("--resume-from",type=pathlib.Path);a=p.parse_args()
 out=a.output.resolve();out.relative_to(N/"acceptance/runs");out.mkdir(mode=0o700);ev=(out/"events.jsonl").open("x",buffering=1)
 def emit(event,**d):ev.write(json.dumps({"event":event,"unix_ns":time.time_ns(),**d})+"\n")
 conn=ConnectionConfig(server_address=os.environ["AKERNEL_SERVER_ADDRESS"],token=os.environ["AKERNEL_TOKEN"],use_tls=True,gateway_address=os.environ.get("AKERNEL_GATEWAY_ADDRESS"),verify_tls=True)
 source=None;reader=None;known=None;source_pod=None;caller=None;published=None;result={"rc":1,"runtime":a.runtime,"diagnostic_not_performance":True,"fault":"verified task SDK caller SIGKILL after unsealed capture directory observed","full_lifecycle_fault_matrix_passed":False}
 def resources():(out/"resources.private.json").write_text(json.dumps({"source":None if source is None else source.id,"reader":None if reader is None else reader.id,"known_snapshot":known,"source_pod":source_pod,"caller_pid":None if caller is None else caller.pid,"published_after_caller_death":published},indent=2))
 def command(env,text,timeout=240):
  r=env.commands.run(text,timeout=timeout)
  if r.exit_code:raise RuntimeError({"cmd":text,"rc":r.exit_code,"stderr":r.stderr[-1500:]})
  return r.stdout
 def memory(env):
  r=json.loads(command(env,"/tmp/pr119-timeout-probe state"))
  if r["http_status"]!=200:raise AssertionError(r)
  return json.loads(r["body"])
 def pod_py(code):return json.loads(run(["kubectl","-n","akernel","exec",source_pod,"--","python3","-c",code]))
 def artifact_ids():return pod_py('import pathlib,json;print(json.dumps([p.name for p in pathlib.Path("/mnt/akernel-shared/akernel/checkpoints/artifacts").iterdir() if p.is_dir()]))')
 try:
  root="/pr119-timeout-root";marker="pr119-caller-death-"+a.runtime+"-"+uuid.uuid4().hex[:10]
  if a.resume_from:
   old=a.resume_from.resolve();old.relative_to(N/"acceptance/runs")
   saved=json.loads((old/"resources.private.json").read_text())
   if saved.get("reader") is not None or not saved.get("source") or not saved.get("known_snapshot"):raise RuntimeError("invalid pre-fault continuation receipt")
   active=[k for k in authority() if k.startswith("environment:")]
   if active!=["environment:"+saved["source"]]:raise RuntimeError("continuation does not exclusively own the active Environment")
   source=Environment.from_id(saved["source"],connection=conn);origin=source;known=saved["known_snapshot"];resources()
   if Environment.get_snapshot(known,connection=conn).snapshot_id!=known:raise AssertionError("known snapshot identity changed")
   before=memory(source)
   if source.files.read(root)!="known-recovery-point":raise AssertionError("pre-fault source changed")
   emit("continued_existing_pre_fault_source")
  else:
   if any(k.startswith("environment:") for k in authority()):raise RuntimeError("another Environment exists")
   source=Sandbox(runtime=a.runtime,cpu=1000,memory=2048,storage_mb=1024,idle_timeout=900,failover=False);resources()
   source.files.write("/tmp/pr119-timeout-probe",(N/"acceptance/bin/guest-probe").read_bytes());command(source,"chmod 700 /tmp/pr119-timeout-probe")
   source.commands.run("/tmp/pr119-timeout-probe hold --bytes 1073741824 >/tmp/pr119-timeout-hold.log 2>&1",background=True)
   deadline=time.monotonic()+120
   while True:
    try:before=memory(source);break
    except Exception:
     if time.monotonic()>deadline:raise
     time.sleep(.5)
   root="/pr119-timeout-root";source.files.write(root,"known-recovery-point")
   marker="pr119-timeout-"+a.runtime+"-"+uuid.uuid4().hex[:10]
   origin=Environment.from_id(source.id,connection=conn);snap=origin.create_snapshot(name=marker+"-good",timeout_seconds=180);known=snap.snapshot_id;resources()
  record=authority()["environment:"+source.id];source_node=record["assignment"]["node_id"];runtime_id=record["result"]["runtime"]["id"]
  pods=json.loads(run(["kubectl","-n","akernel","get","pods","-o","json"]))["items"];matches=[p["metadata"]["name"] for p in pods if p["metadata"]["name"].startswith("akernel-node-") and p["spec"].get("nodeName")==source_node]
  if len(matches)!=1:raise RuntimeError("source Pod is not unique")
  source_pod=matches[0];resources()
  annotation_code='import pathlib,json;rid='+repr(runtime_id)+';eid='+repr(source.id)+';rows=[]\nfor d in pathlib.Path("/home/akernel/sandboxd/root/containers").iterdir():\n try:\n  a=json.loads((d/"config.json").read_text()).get("annotations",{})\n  if a.get("adx.runtime_id")==rid and a.get("adx.environment_id")==eid:rows.append(d.name)\n except (OSError,ValueError):pass\nprint(json.dumps(rows))'
  actual_ids=pod_py(annotation_code)
  if len(actual_ids)!=1 or not actual_ids[0].startswith("sbox-"):raise AssertionError("runtime annotation binding not unique")
  actual_id=actual_ids[0]
  code='import pathlib,os,json;rid='+repr(actual_id)+';rows=[]\nfor p in pathlib.Path("/proc").iterdir():\n if not p.name.isdigit():continue\n try:\n  cmd=(p/"cmdline").read_bytes().split(b"\\0");exe=os.path.basename(os.fsdecode(cmd[0]))\n  if exe in ["firecracker","runsc-sandbox"] and any(rid in os.fsdecode(x) for x in cmd):rows.append({"pid":int(p.name),"start_ticks":(p/"stat").read_text().split()[21],"executable":exe})\n except (OSError,ValueError):pass\nprint(json.dumps(rows))'
  processes=pod_py(code)
  if not processes:raise AssertionError("original runtime process could not be identified")
  (out/"original-processes.private.json").write_text(json.dumps(processes,indent=2))
  initial_ids=set(artifact_ids());command(source,"/tmp/pr119-timeout-probe mutate");source.files.write(root,"after-known-snapshot")
  (out/"state-before-timeout.private.json").write_text(json.dumps(authority(),indent=2))
  mutated=memory(source)
  child_out=out/"caller"
  with (out/"caller.stdout").open("x") as so,(out/"caller.stderr").open("x") as se:
   caller=subprocess.Popen([sys.executable,str(Q/"tap-checksum-fix/storage/sdk-capture-client01.py"),"--environment",source.id,"--name",marker+"-short","--out",str(child_out)],stdin=subprocess.DEVNULL,stdout=so,stderr=se)
  resources()
  child_start=pathlib.Path("/proc/"+str(caller.pid)+"/stat").read_text().split()[21]
  deadline=time.monotonic()+90
  while True:
   if caller.poll() is not None:raise AssertionError("SDK caller ended before active capture could be observed; no caller-death coverage")
   current=set(artifact_ids());active=current-initial_ids
   if active:
    manifest_states=pod_py('import pathlib,json;r=pathlib.Path("/mnt/akernel-shared/akernel/checkpoints/manifests");print(json.dumps({x:(r/(x+".json")).exists() for x in '+repr(sorted(active))+'}))')
    if not any(manifest_states.values()):break
   if time.monotonic()>deadline:raise TimeoutError("accepted capture directory never observed")
   time.sleep(.1)
  if pathlib.Path("/proc/"+str(caller.pid)+"/stat").read_text().split()[21]!=child_start or caller.pid<=1:raise AssertionError("caller identity changed")
  if (child_out/"terminal.json").exists():raise AssertionError("caller already recorded a completed response; no active-call death coverage")
  caller.kill()
  if caller.wait(timeout=30)!=-9:raise AssertionError("caller was not terminated by the intended SIGKILL")
  emit("verified_sdk_caller_killed",capture_directory_observed=True,manifest_absent_at_observation=True)
  # Server work can finish despite the lost caller. Resolve by unique name, never replay.
  time.sleep(15)
  short_items,page=Environment.list_snapshots(name=marker+"-short",connection=conn)
  if page or len(short_items)>1:raise AssertionError("unique caller-death snapshot name not unique")
  if short_items:published=short_items[0].snapshot_id
  (out/"state-after-caller-death.private.json").write_text(json.dumps(authority(),indent=2));failed_ids=set(artifact_ids())-initial_ids
  emit("caller_death_outcome_reconciled",ready_snapshot_count=len(short_items),new_capture_directories=len(failed_ids))
  # Explicit deletion is the bounded cancellation/rescue; no local filesystem cleanup.
  sid=source.id
  try:Environment.delete(sid,connection=conn)
  except Exception as e:
   if "environment:"+sid in authority():raise
  source=None;resources()
  deadline=time.monotonic()+120
  while True:
   gone=not pod_py(code)
   no_record="environment:"+sid not in authority()
   if gone and no_record:break
   if time.monotonic()>deadline:raise TimeoutError("original runtime/writer not retired after explicit source deletion")
   time.sleep(1)
  emit("source_runtime_retired_before_recovery_and_collection",original_process_count=len(processes))
  final_items,page=Environment.list_snapshots(name=marker+"-short",connection=conn)
  if page or len(final_items)>1:raise AssertionError("caller-death outcome did not reconcile")
  published=final_items[0].snapshot_id if final_items else None;resources()
  selected=published or known;expected=mutated if published else before;expected_root="after-known-snapshot" if published else "known-recovery-point"
  other=next(iter({"akcr119-20261022-worker","akcr119-20261022-worker2"}-{source_node}))
  reader=Environment.create(selected,name=marker+"-recovered",node_id=other,connection=conn);resources()
  same_state(expected,memory(reader))
  if reader.files.read(root)!=expected_root:raise AssertionError("known snapshot was damaged by the timed capture")
  reader.files.write(root,"target-write-after-timeout");reply=json.loads(command(reader,"/tmp/pr119-timeout-probe checkpoint --socket /run/akernel/execd.sock --timeout 180"));completed(reply)
  reader.files.write(root,"must-roll-back")
  if not reader.reload():raise AssertionError("target reload after timeout rescue failed")
  if reader.files.read(root)!="target-write-after-timeout":raise AssertionError("target later checkpoint missed new writes")
  rid=reader.id;Environment.delete(rid,connection=conn);reader=None;resources()
  for snap_id in [known]+([published] if published else []):Environment.delete_snapshot(snap_id,connection=conn)
  deadline=time.monotonic()+180
  while True:
   missing=True
   for snap_id in [known]+([published] if published else []):
    try:Environment.get_snapshot(snap_id,connection=conn);missing=False
    except Exception as e:
     if str(getattr(e,"code","")).upper()!="NOT_FOUND":raise
   remaining=set(artifact_ids())&failed_ids
   if missing and not remaining and not any(k.startswith("environment:") for k in authority()):break
   if time.monotonic()>deadline:raise TimeoutError("capture artifacts/readers/catalog did not retire")
   time.sleep(1)
  result.update(rc=0,memory_bytes=1073741824,caller_killed_after_capture_observed=True,published_snapshot_after_caller_death=bool(published),outcome_reconciled_without_replay=True,explicit_source_deletion_rescue=True,source_writer_exit_verified=True,selected_snapshot_cross_node_recovery_verified=True,target_next_checkpoint_reload_verified=True,failed_capture_directories_removed=True,resources_deleted=True)
 except BaseException as e:result.update(error_type=type(e).__name__,error=str(e));emit("acceptance_failed",error_type=type(e).__name__,error=str(e))
 finally:
  if caller is not None and caller.poll() is None:
   try:
    if pathlib.Path("/proc/"+str(caller.pid)+"/stat").read_text().split()[21]!=child_start:raise RuntimeError("caller birth identity changed; refuse signal")
    caller.kill();caller.wait(timeout=30);result["caller_rescued_in_finally"]=True
   except Exception as e:result["caller_rescue_error"]=str(e)
  resources();(out/"terminal.json").write_text(json.dumps(result,indent=2));ev.close()
 return result["rc"]
if __name__=="__main__":sys.exit(main())
