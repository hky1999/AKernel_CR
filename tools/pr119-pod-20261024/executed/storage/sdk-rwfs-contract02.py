#!/usr/bin/env python3
import argparse,hashlib,json,os,pathlib,shlex,subprocess,sys,time,uuid
from akernel_sdk import Sandbox
from adx_environment import ConnectionConfig,Environment
from read_control_state import read_control_state
from acceptance import completed
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";S=Q/"tap-checksum-fix/storage"
IMAGE="docker.io/library/python@sha256:e8a38829209aea82774882e5157e1f7c3e8c8393ff53a697b3580896e57f345c"
def state():return read_control_state(N)[1]
def main():
 p=argparse.ArgumentParser();p.add_argument("--runtime",choices=["runsc","firecracker"],required=True);p.add_argument("--output",type=pathlib.Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.relative_to(N/"acceptance/runs");out.mkdir(mode=0o700);ev=(out/"events.jsonl").open("x",buffering=1)
 def emit(event,**data):ev.write(json.dumps({"event":event,"unix_ns":time.time_ns(),**data})+"\n")
 result={"rc":1,"runtime":a.runtime,"diagnostic_not_performance":True,"image":IMAGE,"same_node_rounds":[],"cross_node_branch":False,"full_lifecycle_fault_matrix_passed":False}
 source=None;reader=None;snapshot=None
 conn=ConnectionConfig(server_address=os.environ["AKERNEL_SERVER_ADDRESS"],token=os.environ["AKERNEL_TOKEN"],use_tls=True,gateway_address=os.environ.get("AKERNEL_GATEWAY_ADDRESS"),verify_tls=True)
 def resources():(out/"resources.private.json").write_text(json.dumps({"source":None if source is None else source.id,"reader":None if reader is None else reader.id,"snapshot":snapshot},indent=2))
 def command(env,cmd,timeout=180):
  r=env.commands.run(cmd,timeout=timeout)
  if r.exit_code:raise RuntimeError({"command":cmd,"exit_code":r.exit_code,"stderr":r.stderr[-1500:]})
  return r.stdout
 def probe(env,mode):return json.loads(command(env,"python3 /tmp/pr119-rwfs-probe.py "+mode))
 def compare(expected,actual,phase):
  if expected!=actual:
   (out/(phase+"-expected.json")).write_text(json.dumps(expected,indent=2));(out/(phase+"-actual.json")).write_text(json.dumps(actual,indent=2))
   raise AssertionError("RWFS/process/open-fd/mmap state mismatch: "+phase)
 def cp(env):
  reply=json.loads(command(env,"/tmp/pr119-checkpoint-probe checkpoint --socket /run/akernel/execd.sock --timeout 180",240));completed(reply);return reply
 try:
  if any(k.startswith("environment:") for k in state()):raise RuntimeError("another Environment exists")
  source=Sandbox(image=IMAGE,runtime=a.runtime,cpu=1000,memory=2048,storage_mb=1024,idle_timeout=900,failover=True);resources()
  source.files.write("/tmp/pr119-rwfs-probe.py",(S/"guest-rwfs-contract02.py").read_bytes())
  source.files.write("/tmp/pr119-checkpoint-probe",(N/"acceptance/bin/guest-probe").read_bytes());command(source,"chmod 700 /tmp/pr119-checkpoint-probe")
  source.commands.run("python3 /tmp/pr119-rwfs-probe.py hold >/tmp/pr119-rwfs-hold.log 2>&1",background=True)
  deadline=time.monotonic()+150
  while True:
   try:initial=probe(source,"state");break
   except Exception:
    if time.monotonic()>deadline:raise
    time.sleep(.5)
  if initial["files"]["large"]["bytes"]!=64*(1<<20) or initial["files"]["sparse"]["bytes"]!=128*(1<<20):raise AssertionError("incorrect RWFS fixture dimensions")
  emit("rwfs_ready",large_bytes=64*(1<<20),sparse_logical_bytes=128*(1<<20),unlinked_open_bytes=1<<20,mmap_bytes=4<<20)
  for i in range(3):
   before=probe(source,"state");reply=cp(source);changed=probe(source,"mutate")
   if before==changed:raise AssertionError("mutation did not change fixture")
   if not source.reload():raise AssertionError("public SDK reload returned false")
   compare(before,probe(source,"state"),"same-node-"+str(i))
   result["same_node_rounds"].append({"round":i,"checkpoint_completed":True,"state_restored":True})
   emit("same_node_round_passed",round=i)
   probe(source,"mutate")
  parent=probe(source,"state");source_node=state()["environment:"+source.id]["assignment"]["node_id"]
  native=Environment.from_id(source.id,connection=conn)
  snap=native.create_snapshot(name="pr119-rwfs-"+a.runtime+"-"+uuid.uuid4().hex[:10],timeout_seconds=240);snapshot=snap.snapshot_id;resources()
  other=next(iter({"akcr119-20261022-worker","akcr119-20261022-worker2"}-{source_node}))
  reader=Environment.create(snapshot,name="pr119-rwfs-branch-"+uuid.uuid4().hex[:10],node_id=other,connection=conn);resources()
  if state()["environment:"+reader.id]["assignment"]["node_id"]!=other:raise AssertionError("reader did not use the other node")
  compare(parent,probe(reader,"state"),"cross-node-restored")
  branch=probe(reader,"mutate");compare(parent,probe(source,"state"),"parent-after-branch-write")
  cp(reader);probe(reader,"mutate")
  if not reader.reload():raise AssertionError("native reader reload returned false")
  compare(branch,probe(reader,"state"),"branch-next-generation");compare(parent,probe(source,"state"),"parent-after-branch-checkpoint")
  result["cross_node_branch"]=True;emit("cross_node_branch_isolation_and_next_generation_passed")
  rid=reader.id;Environment.delete(rid,connection=conn);reader=None;source.kill();source=None;resources()
  Environment.delete_snapshot(snapshot,connection=conn)
  deadline=time.monotonic()+180
  while True:
   missing=False
   try:Environment.get_snapshot(snapshot,connection=conn)
   except Exception as e:
    if str(getattr(e,"code","")).upper()=="NOT_FOUND":missing=True
    else:raise
   if missing and not any(k.startswith("environment:") for k in state()):break
   if time.monotonic()>deadline:raise TimeoutError("resources did not retire")
   time.sleep(1)
  result.update(rc=0,checkpoint_operations=5,reload_operations=4,append_truncate_sparse_hardlink_symlink_verified=True,mmap_and_open_unlinked_and_renamed_fd_verified=True,resources_deleted=True)
 except BaseException as e:result.update(error_type=type(e).__name__,error=str(e));emit("acceptance_failed",error_type=type(e).__name__,error=str(e))
 finally:resources();(out/"terminal.json").write_text(json.dumps(result,indent=2));ev.close()
 return result["rc"]
if __name__=="__main__":sys.exit(main())
