#!/usr/bin/env python3
"""Real shared Snapshot lifecycle through existing SDKs, not a new AKernel API."""
import argparse,hashlib,json,os,pathlib,subprocess,sys,time,uuid
from concurrent.futures import ThreadPoolExecutor
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
 if p.returncode:raise RuntimeError({"command":argv,"rc":p.returncode,"stderr":p.stderr[-1500:]})
 return p.stdout
def state():return read_control_state(N)[1]
def pod_for(node):
 pods=json.loads(run(["kubectl","-n","akernel","get","pods","-o","json"]))["items"]
 items=[p for p in pods if p["metadata"]["name"].startswith("akernel-node-") and p["spec"].get("nodeName")==node]
 if len(items)!=1:raise RuntimeError("target Pod not unique")
 return items[0]["metadata"]["name"]
FD_PROBE=r'''
import pathlib,os,json
rows=[]
for p in pathlib.Path("/proc").iterdir():
 if not p.name.isdigit():continue
 try:
  args=(p/"cmdline").read_bytes().split(b"\0");exe=os.path.basename(os.fsdecode(args[0]))
  if exe not in ["runsc-sandbox","runsc-gofer","firecracker"]:continue
  files=[]
  for f in (p/"fd").iterdir():
   try:path=os.readlink(f)
   except OSError:continue
   if path.startswith("/mnt/akernel-shared/"):files.append({"path":path,"named_path_exists":pathlib.Path(path).exists()})
  rows.append({"executable":exe,"shared_fds":files})
 except (OSError,ValueError):continue
print(json.dumps(rows))
'''
def main():
 p=argparse.ArgumentParser();p.add_argument("--runtime",choices=["runsc","firecracker"],required=True);p.add_argument("--output",type=pathlib.Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.relative_to(N/"acceptance/runs");out.mkdir(mode=0o700);events=(out/"events.jsonl").open("x",buffering=1)
 def emit(name,**data):events.write(json.dumps({"event":name,"unix_ns":time.time_ns(),**data})+"\n")
 result={"rc":1,"runtime":a.runtime,"diagnostic_not_performance":True,"existing_native_snapshot_api":True,"internal_delete_barrier_tested":False}
 source=None;reader=None;second_reader=None;snapshot_id=None;known_closed=set()
 conn=ConnectionConfig(server_address=os.environ["AKERNEL_SERVER_ADDRESS"],token=os.environ["AKERNEL_TOKEN"],use_tls=True,gateway_address=os.environ.get("AKERNEL_GATEWAY_ADDRESS"),verify_tls=True)
 def resources():
  (out/"resources.private.json").write_text(json.dumps({"source":None if source is None else source.id,"reader":None if reader is None else reader.id,"second_reader":None if second_reader is None else second_reader.id,"snapshot_id":snapshot_id},indent=2))
 def command(env,text):
  r=env.commands.run(text,timeout=240)
  if r.exit_code:raise AssertionError({"command":text,"exit_code":r.exit_code,"stderr":r.stderr[-1000:]})
  return r.stdout
 def memory(env):
  r=json.loads(command(env,"/tmp/pr119-gc-probe state"))
  if r["http_status"]!=200:raise AssertionError(r)
  return json.loads(r["body"])
 try:
  if any(k.startswith("environment:") for k in state()):raise RuntimeError("another Environment exists")
  marker="pr119-gc-"+a.runtime+"-"+uuid.uuid4().hex[:10]
  source=Sandbox(runtime=a.runtime,cpu=1000,memory=2048,storage_mb=1024,idle_timeout=900,failover=True)
  resources();emit("public_sdk_source_created")
  source.files.write("/tmp/pr119-gc-probe",(N/"acceptance/bin/guest-probe").read_bytes());command(source,"chmod 700 /tmp/pr119-gc-probe")
  source.commands.run("/tmp/pr119-gc-probe hold --bytes 1073741824 >/tmp/pr119-gc-hold.log 2>&1",background=True)
  deadline=time.monotonic()+120
  while True:
   try:before=memory(source);break
   except Exception:
    if time.monotonic()>deadline:raise
    time.sleep(.5)
  root="/pr119-snapshot-gc-root";payload="g"*(1<<20);source.files.write(root,payload);command(source,"sync")
  origin_node=state()["environment:"+source.id]["assignment"]["node_id"]
  origin=Environment.from_id(source.id,connection=conn)
  snapshot=origin.create_snapshot(name=marker,timeout_seconds=180);snapshot_id=snapshot.snapshot_id;resources()
  emit("native_reusable_snapshot_created",snapshot_id_sha256=hashlib.sha256(snapshot_id.encode()).hexdigest())
  source.kill();source=None;resources()
  nodes={"akcr119-20261022-worker","akcr119-20261022-worker2"};target=next(iter(nodes-{origin_node}))
  reader=Environment.create(snapshot_id,name=marker+"-reader",node_id=target,connection=conn)
  resources();current=state()["environment:"+reader.id]
  if current["assignment"]["node_id"]!=target:raise AssertionError("reader did not use independently pinned target node")
  r=current["result"];art=(r.get("snapshot_source") or {}).get("artifact")
  if art is None:
   arts=[x for x in r.get("execution_artifacts") or [] if x["storage"]=="akernel-checkpoints"]
   if len(arts)!=1:raise AssertionError("shared artifact cannot be identified")
   art=arts[0]
  if art["storage"]!="akernel-checkpoints" or str(uuid.UUID(art["location"]))!=art["location"]:raise AssertionError("artifact outside owned shared storage")
  pod=pod_for(target);directory="/mnt/akernel-shared/akernel/checkpoints/artifacts/"+art["location"];manifest="/mnt/akernel-shared/akernel/checkpoints/manifests/"+art["location"]+".json"
  def physical():
   code="import pathlib,json; print(json.dumps({p:pathlib.Path(p).exists() for p in "+repr([directory,manifest])+"}))"
   return json.loads(run(["kubectl","-n","akernel","exec",pod,"--","python3","-c",code]))
  if not all(physical().values()):raise AssertionError("published shared artifact missing before delete attempt")
  observed=json.loads(run(["kubectl","-n","akernel","exec",pod,"--","python3","-c",FD_PROBE]))
  (out/"reader-fds.private.json").write_text(json.dumps(observed,indent=2))
  live_reader=any(art["location"] in f["path"] for x in observed for f in x["shared_fds"])
  emit("reader_registered",source_node=origin_node,target_node=target,shared_input_fd_observed=live_reader)
  def expect_busy(expected,phase):
   deadline=time.monotonic()+30
   while True:
    try:Environment.delete_snapshot(snapshot_id,connection=conn)
    except Exception as e:
     if str(getattr(e,"code","")).upper()!="SNAPSHOT_IN_USE":raise
     if getattr(e,"retry",None)!="never" or getattr(e,"outcome",None)!="not_started":raise AssertionError("busy delete lost retry/outcome contract")
     blockers=set(getattr(e,"sandbox_ids",None) or [])
     if not expected.issubset(blockers) or not (blockers-expected).issubset(known_closed):raise AssertionError("busy delete blocker identities differ from live readers")
     if blockers==expected:
      emit("delete_rejected_for_live_reader",phase=phase,blocker_count=len(blockers),code=e.code,retry=e.retry,outcome=e.outcome);break
     if time.monotonic()>deadline:raise TimeoutError("closed reader reference did not converge")
     time.sleep(.2)
    else:raise AssertionError("delete accepted while a Snapshot reader is alive")
   if not all(physical().values()):raise AssertionError("busy delete removed shared files")
  expect_busy({reader.id},"one-reader")
  if not all(physical().values()):raise AssertionError("busy delete removed real shared data")
  if Environment.get_snapshot(snapshot_id,connection=conn).snapshot_id!=snapshot_id:raise AssertionError("busy snapshot identity changed")
  if reader.files.read(root)!=payload:raise AssertionError("restored RWFS differs")
  same_state(before,memory(reader));reader.files.write("/pr119-gc-reader-write","reader-is-writable")
  if reader.files.read("/pr119-gc-reader-write")!="reader-is-writable":raise AssertionError("reader write failed")
  emit("reader_verified_after_rejected_delete",memory_bytes=before["memory_bytes"],root_bytes=len(payload))
  second_reader=Environment.create(snapshot_id,name=marker+"-reader2",node_id=origin_node,connection=conn);resources()
  second_record=state()["environment:"+second_reader.id]
  if second_record["assignment"]["node_id"]!=origin_node:raise AssertionError("second reader was not on the other independent client")
  expect_busy({reader.id,second_reader.id},"two-readers")
  emit("two_independent_readers_registered",reader_count=2)
  rid=reader.id;Environment.delete(rid,connection=conn);known_closed.add(rid);reader=None;resources()
  deadline=time.monotonic()+90
  while "environment:"+rid in state():
   if time.monotonic()>deadline:raise TimeoutError("reader record still present after delete")
   time.sleep(.5)
  expect_busy({second_reader.id},"one-reader-after-first-exit")
  if second_reader.files.read(root)!=payload:raise AssertionError("remaining reader root data changed")
  same_state(before,memory(second_reader))
  second_reader.files.write("/pr119-gc-second-write","remaining-reader-is-writable")
  if second_reader.files.read("/pr119-gc-second-write")!="remaining-reader-is-writable":raise AssertionError("remaining reader write failed")
  sid=second_reader.id;Environment.delete(sid,connection=conn);known_closed.add(sid);second_reader=None;resources()
  deadline=time.monotonic()+90
  while "environment:"+sid in state():
   if time.monotonic()>deadline:raise TimeoutError("last reader record remains")
   time.sleep(.5)
  def delete_unreferenced():
   try:Environment.delete_snapshot(snapshot_id,connection=conn);return {"code":"accepted"}
   except Exception as e:
    code=str(getattr(e,"code","")).upper()
    if code not in ["NOT_FOUND","CONFLICT"] or getattr(e,"retry",None)!="never" or getattr(e,"outcome",None)!="not_started":raise
    return {"code":code,"retry":e.retry,"outcome":e.outcome}
  with ThreadPoolExecutor(max_workers=2) as pool:delete_results=list(pool.map(lambda _:delete_unreferenced(),range(2)))
  if not any(x["code"]=="accepted" for x in delete_results):raise AssertionError("neither unreferenced delete request was accepted")
  emit("unreferenced_snapshot_delete_accepted",concurrent_delete_requests=2,outcomes=delete_results)
  deadline=time.monotonic()+180
  while True:
   gone=not any(physical().values())
   missing=False
   try:Environment.get_snapshot(snapshot_id,connection=conn)
   except Exception as e:
    if str(getattr(e,"code","")).upper()!="NOT_FOUND":raise
    missing=True
   if gone and missing:break
   if time.monotonic()>deadline:raise TimeoutError("snapshot did not finish physical shared filesystem deletion")
   time.sleep(1)
  try:
   late=Environment.create(snapshot_id,name=marker+"-late",node_id=target,connection=conn)
  except Exception as e:
   code=str(getattr(e,"code","")).upper()
   if code not in ["NOT_FOUND","CONFLICT"] or getattr(e,"status_code",None)!={"NOT_FOUND":404,"CONFLICT":409}[code] or getattr(e,"retry",None)!="never" or getattr(e,"outcome",None)!="not_started":raise
   emit("new_reader_rejected_after_delete",code=e.code,status_code=e.status_code,retry=e.retry,outcome=e.outcome)
  else:
   (out/"unexpected-late-reader.private.json").write_text(json.dumps({"id":late.id}));raise AssertionError("deleted snapshot acquired a new reader")
  if any(k.startswith("environment:") for k in state()):raise AssertionError("Environment remains after rejected late reader")
  result.update(rc=0,reader_first_delete_busy=True,physical_files_removed_after_reader_exit=True,delete_first_rejects_new_reader=True,shared_input_fd_observed=live_reader,memory_bytes=before["memory_bytes"],root_bytes=len(payload),snapshots_and_environments_cleaned=True,multiple_reader_protection_verified=True,concurrent_delete_requests=2)
 except BaseException as e:result.update(error_type=type(e).__name__,error=str(e));emit("acceptance_failed",error_type=type(e).__name__,error=str(e))
 finally:
  resources();(out/"terminal.json").write_text(json.dumps(result,indent=2));events.close()
 return result["rc"]
if __name__=="__main__":sys.exit(main())
