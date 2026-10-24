#!/usr/bin/env python3
import argparse,importlib.util,json,os,pathlib,subprocess,sys,time,uuid
from akernel_sdk import Sandbox
from adx_environment import Environment,ConnectionConfig
from acceptance import same_state,completed
from read_control_state import read_control_state
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";S=Q/"tap-checksum-fix/gvisor-native-reader-barrier-control02";B=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"]
KINDS={"akcr119-20261022-worker":("c94000a9e103f344bd40e2fd1cce2bb4ee113766beadc63ae5e5f8c7b6a5b550","a"),"akcr119-20261022-worker2":("31814694e9fd4463d194bb5150fc2dec052131af18d726ca330e822345c0f017","b")}
CP="309834713ae51c81b89d88111a2a0adaf345f9ec135d8d3938d20f4727023bfa"
def run(argv,timeout=90):
 p=subprocess.run(B+argv,text=True,capture_output=True,timeout=timeout)
 if p.returncode:raise RuntimeError({"argv":argv,"rc":p.returncode,"stderr_bytes":len(p.stderr)})
 return p.stdout
def state():return read_control_state(N)[1]
def main():
 p=argparse.ArgumentParser();p.add_argument("--role",choices=["adxlet","coordinator","sandboxd"],required=True);p.add_argument("--output",type=pathlib.Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.relative_to(N/"acceptance/runs");out.mkdir(mode=0o700);ev=(out/"events.jsonl").open("x",buffering=1)
 def emit(event,**d):ev.write(json.dumps({"event":event,"unix_ns":time.time_ns(),**d})+"\n")
 conn=ConnectionConfig(server_address=os.environ["AKERNEL_SERVER_ADDRESS"],token=os.environ["AKERNEL_TOKEN"],use_tls=True,gateway_address=os.environ.get("AKERNEL_GATEWAY_ADDRESS"),verify_tls=True)
 source=None;reader=None;snapshot=None;barrier=None;result={"rc":1,"runtime":"runsc","role":a.role,"diagnostic_not_performance":True,"full_lifecycle_fault_matrix_passed":False,"reader_barrier_seconds":3,"role_crash_injected":False}
 def resources():(out/"resources.private.json").write_text(json.dumps({"source":None if source is None else source.id,"reader":None if reader is None else reader.id,"snapshot":snapshot},indent=2))
 def command(env,cmd,timeout=240):
  r=env.commands.run(cmd,timeout=timeout)
  if r.exit_code:raise RuntimeError({"command":cmd,"rc":r.exit_code,"stderr":r.stderr[-1000:]})
  return r.stdout
 def memory(env):
  v=json.loads(command(env,"/tmp/pr119-reader-probe state"))
  if v["http_status"]!=200:raise AssertionError(v)
  return json.loads(v["body"])
 def py(pod,code):return json.loads(run(["kubectl","-n","akernel","exec",pod,"--","python3","-c",code]))
 try:
  st=state();resident=1073741824
  if any(k.startswith("environment:") for k in st):raise RuntimeError("another Environment exists")
  memory_mb=2048
  source=Sandbox(runtime="runsc",cpu=1000,memory=memory_mb,storage_mb=1024,idle_timeout=900,failover=True)
  source.files.write("/tmp/pr119-reader-probe",(N/"acceptance/bin/guest-probe").read_bytes());command(source,"chmod 700 /tmp/pr119-reader-probe")
  resources()
  source.commands.run("/tmp/pr119-reader-probe hold --bytes "+str(resident)+" >/tmp/pr119-reader-hold.log 2>&1",background=True)
  deadline=time.monotonic()+120
  while True:
   try:before=memory(source);break
   except Exception:
    if time.monotonic()>deadline:raise
    time.sleep(.5)
  (out/"source-before-snapshot.json").write_text(json.dumps(before,indent=2))
  root="/pr119-reader-root";payload="r"*(1<<20);source.files.write(root,payload)
  origin_node=state()["environment:"+source.id]["assignment"]["node_id"]
  pods=json.loads(run(["kubectl","-n","akernel","get","pods","-o","json"]))["items"]
  nodepods={p["spec"]["nodeName"]:p for p in pods if p["metadata"]["name"].startswith("akernel-node-")}
  cpods=[p for p in pods if p["metadata"]["name"].startswith("akernel-adx-coordinator-")]
  if len(nodepods)!=2 or len(cpods)!=1:raise RuntimeError("owned workload identity mismatch")
  source_pod=nodepods[origin_node]["metadata"]["name"]
  ids=lambda:py(source_pod,'import pathlib,json;print(json.dumps([p.name for p in pathlib.Path("/mnt/akernel-shared/akernel/checkpoints/artifacts").iterdir() if p.is_dir()]))')
  initial=set(ids());origin=Environment.from_id(source.id,connection=conn)
  snap=origin.create_snapshot(name="pr119-live-reader-"+a.role+"-"+uuid.uuid4().hex[:10],timeout_seconds=240);snapshot=snap.snapshot_id;resources()
  new=set(ids())-initial
  if len(new)!=1:raise RuntimeError("new immutable artifact directory is not unique")
  artifact=next(iter(new))
  if str(uuid.UUID(artifact))!=artifact:raise RuntimeError("artifact is not a canonical UUID")
  Environment.delete(source.id,connection=conn);source=None;resources()
  target=next(iter(set(KINDS)-{origin_node}));target_pod=nodepods[target]["metadata"]["name"];role_pod=nodepods[target] if a.role in ["adxlet","sandboxd"] else cpods[0]
  cids=[x["containerID"].removeprefix("containerd://") for x in role_pod["status"]["containerStatuses"]]
  if len(cids)!=1 or len(cids[0])!=64:raise RuntimeError("owned role container identity missing")
  reader=Environment.create(snapshot,name="pr119-held-reader-"+a.role+"-"+uuid.uuid4().hex[:10],node_id=target,connection=conn);resources()
  # No status query/full memory read before the host helper pins the still-open input.
  req={"role":a.role,"environment_id":reader.id,"artifact_id":artifact,"reader_kind_id":KINDS[target][0],"role_kind_id":KINDS[target][0] if a.role in ["adxlet","sandboxd"] else CP,"role_container_id":cids[0],"metadata_root":str(N/"node-data09"/KINDS[target][1]/"akernel/variants/tapfix/sandboxd/root/containers")}
  im=json.loads((Q/"tap-checksum-fix/gvisor-native-consumer-image02/terminal.json").read_text());assert im["rc"]==0
  reader_cids=[x['containerID'].removeprefix('containerd://')for x in nodepods[target]['status']['containerStatuses']]
  if len(reader_cids)!=1 or len(reader_cids[0])!=64:raise RuntimeError('reader mount anchor container identity missing')
  req['reader_container_id']=reader_cids[0];req['expected_sandboxd_sha256']=im['sandboxd_sha256']
  req["expected_reader_sha256"]=im["runtime_assets"]["gvisor-bin/gvisor_sentry"]["sha256"]
  if a.role=="sandboxd":req["expected_role_sha256"]=im["sandboxd_sha256"]
  else:
   receipt=json.loads((Q/"image-build/payload-receipt.json").read_text())
   req["expected_role_sha256"]=receipt["assets"]["/opt/adx/current/bin/"+{"adxlet":"adxlet","coordinator":"adx-coordinator"}[a.role]]["sha256"]
  request=out/"barrier-request.private.json";request.write_text(json.dumps(req,indent=2))
  with (out/"barrier.stdout").open("x") as so,(out/"barrier.stderr").open("x") as se:
   barrier=subprocess.Popen(["/usr/bin/python3",str(S/"hold-reader-control01.py"),"--request",str(request),"--out",str(out/"barrier")],stdin=subprocess.DEVNULL,stdout=so,stderr=se,start_new_session=True)
  resources()
  if barrier.wait(timeout=25)!=0:raise RuntimeError("reader-only control did not prove open input; inspect and preserve")
  br=json.loads((out/"barrier/terminal.json").read_text())
  if br.get("rc")!=0 or br.get("role_crash_injected")is not False or not br.get("same_role_preserved")or not br.get("shared_input_fd_count_at_control") or not br.get("same_reader_resumed"):raise AssertionError("reader-only control evidence incomplete")
  emit("reader_only_barrier_no_role_crash",role=a.role,barrier_seconds=3,shared_input_fds=br["shared_input_fd_count_at_control"])
  modspec=importlib.util.spec_from_file_location("held_reader_helper",S/"hold-reader-control01.py");mod=importlib.util.module_from_spec(modspec);modspec.loader.exec_module(mod)
  deadline=time.monotonic()+180;stable=0
  while True:
   roles=mod.candidates(req["role_kind_id"],req["role_container_id"],executable={"adxlet":"adxlet","coordinator":"adx-coordinator","sandboxd":"sandboxd"}[a.role])
   control=state();r=control.get("environment:"+reader.id)
   nodes=[v for k,v in control.items() if k.startswith("node:") and v.get("node",{}).get("id")==target]
   good=len(roles)==1 and roles[0]["start_ticks"]==br["role_before"]["start_ticks"] and r and r["result"]["state"]=="Running" and r["result"]["runtime"]["id"]==br["reader"]["runtime_id"] and str(r["assignment"]["generation"])==str(br["reader"]["ownership_generation"]) and len(nodes)==1 and nodes[0].get("session",{}).get("routable") is True and nodes[0]["node"].get("available") is True and not nodes[0].get("scheduling_paused",False)
   if good:
    try:
     check=Environment.from_id(reader.id,connection=conn);check.close()
     if Environment.get_snapshot(snapshot,connection=conn).snapshot_id!=snapshot:raise AssertionError("snapshot identity changed")
    except Exception:good=False
   stable=stable+1 if good else 0
   if stable>=3:break
   if time.monotonic()>deadline:raise TimeoutError("reader-only control did not retain original runtime")
   time.sleep(.5)
  current=mod.process(br["reader"]["pid"])
  if current["start_ticks"]!=br["reader"]["start_ticks"]:raise AssertionError("original reader runtime was replaced")
  rr=r["result"];arts=[x.get("location") for x in rr.get("execution_artifacts") or []]
  ss=(rr.get("snapshot_source") or {}).get("artifact") or {}
  if artifact not in arts and ss.get("location")!=artifact:raise AssertionError("role restart lost the live input reference")
  try:Environment.delete_snapshot(snapshot,connection=conn)
  except Exception as e:
   if str(getattr(e,"code","")).upper()!="SNAPSHOT_IN_USE" or getattr(e,"retry",None)!="never" or getattr(e,"outcome",None)!="not_started" or reader.id not in (getattr(e,"sandbox_ids",None) or []):raise
  else:raise AssertionError("Snapshot deletion accepted while the surviving reader is alive")
  physical=py(target_pod,'import pathlib,json;r=pathlib.Path("/mnt/akernel-shared/akernel/checkpoints");a='+repr(artifact)+';print(json.dumps({"directory":(r/"artifacts"/a).exists(),"manifest":(r/"manifests"/(a+".json")).exists()}))')
  if not all(physical.values()):raise AssertionError("protected input physically disappeared")
  same_state(before,memory(reader))
  if reader.files.read(root)!=payload:raise AssertionError("root RWFS changed")
  reader.files.write(root,"after-role-restart")
  completed(json.loads(command(reader,"/tmp/pr119-reader-probe checkpoint --socket /run/akernel/execd.sock --timeout 240",300)))
  reader.files.write(root,"must-roll-back")
  if not reader.reload() or reader.files.read(root)!="after-role-restart":raise AssertionError("later checkpoint/reload failed")
  same_state(before,memory(reader))
  Environment.delete(reader.id,connection=conn);reader=None;resources();Environment.delete_snapshot(snapshot,connection=conn)
  deadline=time.monotonic()+180
  while True:
   missing=False
   try:Environment.get_snapshot(snapshot,connection=conn)
   except Exception as e:
    if str(getattr(e,"code","")).upper()=="NOT_FOUND":missing=True
    else:raise
   if missing and not any(k.startswith("environment:") for k in state()):break
   if time.monotonic()>deadline:raise TimeoutError("reader/snapshot did not retire")
   time.sleep(1)
  result.update(rc=0,memory_bytes=resident,vm_memory_mb=memory_mb,open_input_control_exercised=True,original_runtime_preserved=True,reference_and_named_files_preserved=True,busy_delete_after_restart=True,full_state_verified=True,later_checkpoint_reload_verified=True,resources_deleted=True)
 except BaseException as e:result.update(error_type=type(e).__name__,error=str(e));emit("acceptance_failed",error_type=type(e).__name__,error=str(e))
 finally:
  if barrier is not None and barrier.poll() is None:
   try:barrier.wait(timeout=15)
   except Exception as e:result["barrier_wait_error"]=str(e)
  resources();(out/"terminal.json").write_text(json.dumps(result,indent=2));ev.close()
 return result["rc"]
if __name__=="__main__":sys.exit(main())
