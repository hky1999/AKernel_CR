#!/usr/bin/env python3
import argparse,json,os,pathlib,subprocess,sys,time,uuid
from akernel_sdk import Sandbox
from adx_environment import ConnectionConfig,Environment
from acceptance import completed
from read_control_state import read_control_state
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";D=Q/"tap-checksum-fix"
IMAGE="docker.io/library/python@sha256:e8a38829209aea82774882e5157e1f7c3e8c8393ff53a697b3580896e57f345c"
def main():
 p=argparse.ArgumentParser();p.add_argument("--output",type=pathlib.Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.relative_to(N/"acceptance/runs");out.mkdir(mode=0o700)
 ev=(out/"events.jsonl").open("x",buffering=1);source=None;reader=None;snapshot=None;snapshot_name=None;reader_name=None
 r={"rc":1,"scope":"real FC guest direct-write/sync/readback under SDK snapshots; not deterministic io_uring stall injection and not a latency benchmark","same_node":[],"cross_node_branch":False,"runtime":"firecracker","image":IMAGE}
 conn=ConnectionConfig(server_address=os.environ["AKERNEL_SERVER_ADDRESS"],token=os.environ["AKERNEL_TOKEN"],use_tls=True,gateway_address=os.environ.get("AKERNEL_GATEWAY_ADDRESS"),verify_tls=True)
 def resources():(out/"resources.private.json").write_text(json.dumps({"source":None if source is None else source.id,"reader":None if reader is None else reader.id,"snapshot":snapshot,"snapshot_name":snapshot_name,"reader_name":reader_name}))
 def emit(event,**data):ev.write(json.dumps({"event":event,"at_unix_ns":time.time_ns(),**data})+"\n")
 def command(env,text,timeout=180):
  value=env.commands.run(text,timeout=timeout)
  if value.exit_code:raise RuntimeError({"guest_command_exit":value.exit_code,"stderr_bytes":len(value.stderr)})
  return value.stdout
 def state(env):
  value=json.loads(command(env,"python3 /tmp/pr119-direct-io.py state"))
  if value["error"]is not None:raise AssertionError(value["error"])
  if value["direct_flag"]is not True or value["block_bytes"]!=4096 or value["file_bytes"]!=1048576:raise AssertionError("direct I/O probe identity differs")
  return value
 def progress(env,identity=None,minimum=None):
  deadline=time.monotonic()+90
  while True:
   value=state(env)
   if identity and(value["pid"]!=identity["pid"]or value["cookie"]!=identity["cookie"]):raise AssertionError("writer process was replaced")
   if value["completed"]>=(64 if minimum is None else minimum):return value
   if time.monotonic()>deadline:raise TimeoutError("writer did not advance after restore")
   time.sleep(.2)
 def capture(env):
  value=json.loads(command(env,"/tmp/pr119-checkpoint-probe checkpoint --socket /run/akernel/execd.sock --timeout 180",240));completed(value);return value
 try:
  if any(k.startswith("environment:")for k in read_control_state(N)[1]):raise RuntimeError("Environment exists")
  source=Sandbox(image=IMAGE,runtime="firecracker",cpu=1000,memory=1024,storage_mb=1024,idle_timeout=900,failover=True);resources()
  source.files.write("/tmp/pr119-direct-io.py",(D/"guest-direct-io-probe02.py").read_bytes())
  source.files.write("/tmp/pr119-checkpoint-probe",(N/"acceptance/bin/guest-probe").read_bytes())
  command(source,"chmod 700 /tmp/pr119-checkpoint-probe")
  source.commands.run("python3 /tmp/pr119-direct-io.py hold >/tmp/pr119-direct-io.log 2>&1",background=True)
  deadline=time.monotonic()+90
  while True:
   try:initial=progress(source);break
   except AssertionError:raise
   except Exception:
    if time.monotonic()>deadline:raise
    time.sleep(.5)
  emit("guest_direct_io_ready",state=initial)
  for index in range(3):
   before=state(source);reply=capture(source)
   if not source.reload():raise AssertionError("public SDK reload returned false")
   restored=state(source);after=progress(source,identity=initial,minimum=restored["completed"]+64)
   r["same_node"].append({"round":index,"checkpoint_completed":True,"writer_before":before,"writer_after":after})
   emit("same_node_concurrent_write_reload_passed",round=index,after=after)
  actual=read_control_state(N)[1]["environment:"+source.id]["assignment"]["node_id"]
  other=next(iter({"akcr119-20261022-worker","akcr119-20261022-worker2"}-{actual}))
  native=Environment.from_id(source.id,connection=conn)
  snapshot_name="pr119-direct-io-"+uuid.uuid4().hex[:10];resources()
  snap=native.create_snapshot(name=snapshot_name,timeout_seconds=240);snapshot=snap.snapshot_id;resources()
  reader_name="pr119-direct-io-child-"+uuid.uuid4().hex[:10];resources()
  reader=Environment.create(snapshot,name=reader_name,node_id=other,connection=conn);resources()
  if read_control_state(N)[1]["environment:"+reader.id]["assignment"]["node_id"]!=other:raise AssertionError("branch did not use other node")
  branch=state(reader);progress(reader,identity=initial,minimum=branch["completed"]+64)
  changed=json.loads(command(reader,"python3 /tmp/pr119-direct-io.py branch/child"))
  if changed["salt"]!="child":raise AssertionError("branch writer salt did not change")
  child=progress(reader,identity=initial,minimum=changed["completed"]+128)
  parent_before=state(source);parent_after=progress(source,identity=initial,minimum=parent_before["completed"]+128)
  if parent_after["salt"]!="parent":raise AssertionError("private branches share writer state")
  capture(reader)
  if not reader.reload():raise AssertionError("native branch reload returned false")
  child_state=state(reader);child_after=progress(reader,identity=initial,minimum=child_state["completed"]+128)
  if child_after["salt"]!="child":raise AssertionError("branch state did not restore")
  final_parent=state(source);progress(source,identity=initial,minimum=final_parent["completed"]+64)
  r.update(cross_node_branch=True,cross_node={"source":actual,"target":other,"child":child_after,"parent":parent_after})
  emit("cross_node_independent_writers_and_next_checkpoint_passed",source=actual,target=other)
  Environment.delete(reader.id,connection=conn);reader=None;source.kill();source=None;resources()
  Environment.delete_snapshot(snapshot,connection=conn)
  deadline=time.monotonic()+180
  while True:
   missing=False
   try:Environment.get_snapshot(snapshot,connection=conn)
   except Exception as e:
    if str(getattr(e,"code","")).upper()=="NOT_FOUND":missing=True
    else:raise
   if missing and not any(k.startswith("environment:")for k in read_control_state(N)[1]):break
   if time.monotonic()>deadline:raise TimeoutError("owned resources did not retire")
   time.sleep(1)
  r.update(rc=0,status="real-guest-concurrent-direct-io-and-sdk-reload-passed",checkpoint_operations=5,reload_operations=4,resources_deleted=True)
 except BaseException as e:r.update(error_type=type(e).__name__,error=str(e));emit("acceptance_failed",error_type=type(e).__name__,error=str(e))
 finally:resources();(out/"terminal.json").write_text(json.dumps(r,indent=2));ev.close()
 return r["rc"]
if __name__=="__main__":sys.exit(main())
