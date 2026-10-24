#!/usr/bin/env python3
"""SDK + process-restart reference retention; not a GC race or performance test."""
import argparse,hashlib,json,os,pathlib,subprocess,sys,time
from akernel_sdk import Sandbox
from acceptance import completed,same_state
from read_control_state import read_control_state
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp")
Q=N/"round-365f797-20261023.clPWh2h0"
BASE=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"]
VM_PROBE=r'''
import pathlib,json,os,stat,tomllib,uuid
cfg=tomllib.loads(pathlib.Path('/home/akernel/sandboxd/config.toml').read_text())['plugin']['runtime']
root=pathlib.Path(cfg['runsc']['writable_storage_dir']);assert cfg['runsc']['checkpoint_mode']=='reflink'and cfg['runsc']['writable_storage_filesystem']=='fuse.juicefs'
device=root.stat().st_dev
rows=[]
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  args=(p/'cmdline').read_bytes().split(b'\0');arg0=os.path.basename(os.fsdecode(args[0]));actual=os.path.basename(os.readlink(p/'exe').removesuffix(' (deleted)'))
  if arg0 not in ['firecracker','runsc-sandbox']and actual not in ['firecracker','gvisor_sentry']:continue
  fields=(p/'stat').read_text().rsplit(')',1)[1].split()
  if fields[0]in ['Z','X']:continue
  deps=[]
  for f in(p/'fd').iterdir():
   try:
    value=os.readlink(f)
    if not value.startswith('/mnt/akernel-shared/'):continue
    info=f.stat();clean=pathlib.Path(value.removesuffix(' (deleted)'))
    if not stat.S_ISREG(info.st_mode):continue
    kind='other_shared_named'
    if clean.name.startswith('runsc-filestore-'):
     assert value.endswith(' (deleted)')and info.st_nlink==0 and info.st_dev==device,'unexpected private filestore identity'
     accepted=clean.parent==root
     if clean.parent.name=='filestores'and clean.parent.parent.parent==pathlib.Path('/mnt/akernel-shared/akernel/checkpoints/artifacts'):
      accepted=str(uuid.UUID(clean.parent.parent.name))==clean.parent.parent.name
     assert accepted,'private anonymous filestore outside the expected root/artifact directory'
     kind='private_anonymous_filestore'
    elif clean.name in ['pages.img','pages_meta.img','checkpoint.img','memory']and '/checkpoints/artifacts/'in value:
     kind='immutable_checkpoint_input'
    elif clean.name=='overlay.ext4'and '/fc-rwfs-native-'in value:kind='private_named_overlay'
    exists=clean.exists();same=False
    if exists:
     named=clean.stat();same=(named.st_dev,named.st_ino)==(info.st_dev,info.st_ino)
    deps.append({'kind':kind,'path':value,'named_path_exists':exists,'named_path_matches_fd':same,'device':info.st_dev,'inode':info.st_ino,'bytes':info.st_size,'links':info.st_nlink})
   except (FileNotFoundError,PermissionError):continue
  rows.append({'pid':int(p.name),'start_ticks':fields[19],'executable':arg0,'actual_executable':actual,'shared_file_dependencies':deps})
 except (FileNotFoundError,PermissionError):continue
print(json.dumps(rows))
'''
ROLE_PROBE="import pathlib,os,json,sys\nrole=sys.argv[1];rows=[]\nfor p in pathlib.Path(\"/proc\").iterdir():\n if not p.name.isdigit() or int(p.name)<=1:continue\n try:\n  args=(p/\"cmdline\").read_bytes().split(b\"\\0\");exe=os.readlink(p/\"exe\");fields=(p/\"stat\").read_text().rsplit(\")\",1)[1].split()\n  if os.path.basename(os.fsdecode(args[0]))==role and os.path.basename(exe)==role and exe.startswith(\"/opt/adx/\") and fields[0] not in [\"Z\",\"X\"]:\n   rows.append({\"pid\":int(p.name),\"start_ticks\":fields[19],\"role\":role,\"executable\":exe})\n except (OSError,ValueError):continue\nprint(json.dumps(rows))"
ROLE_SIGNAL="import pathlib,os,json,sys,signal\nidentity=json.loads(sys.argv[1]);p=pathlib.Path(\"/proc\")/str(identity[\"pid\"])\nfields=(p/\"stat\").read_text().rsplit(\")\",1)[1].split();exe=os.readlink(p/\"exe\")\nargs=(p/\"cmdline\").read_bytes().split(b\"\\0\")\nif identity[\"pid\"]<=1 or fields[19]!=identity[\"start_ticks\"] or exe!=identity[\"executable\"] or os.path.basename(os.fsdecode(args[0]))!=identity[\"role\"] or fields[0] in [\"Z\",\"X\"]:\n raise RuntimeError(\"role identity changed; refuse signal\")\nprint(json.dumps({\"verified_target\":identity,\"signal\":\"SIGKILL\",\"owned_container_only\":True}),flush=True)\nos.kill(identity[\"pid\"],signal.SIGKILL)"
ROLE_PROBE=ROLE_PROBE.replace('exe.startswith("/opt/adx/")','(exe.startswith("/opt/adx/") or (role=="sandboxd" and exe=="/usr/local/bin/sandboxd"))')
def run(argv,timeout=90):
 p=subprocess.run(BASE+argv,capture_output=True,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError({"command":argv,"rc":p.returncode,"stderr":p.stderr[-1500:]})
 return p.stdout
def read_state():return read_control_state(N)[1]
def artifact_key(a):return (a["storage"],a["location"])
def refs(record):
 result=record.get("result") or {};out=set()
 for a in result.get("execution_artifacts") or []:out.add(artifact_key(a))
 cp=result.get("checkpoint")
 if cp:out.add(artifact_key(cp["artifact"]))
 return out
def pod_for(node):
 pods=json.loads(run(["kubectl","-n","akernel","get","pods","-o","json"]))["items"]
 selected=[p for p in pods if p["metadata"]["name"].startswith("akernel-node-") and p["spec"].get("nodeName")==node]
 if len(selected)!=1:raise RuntimeError("node execution Pod is not unique")
 return selected[0]["metadata"]["name"]
def vm_state(pod):return json.loads(run(["kubectl","-n","akernel","exec",pod,"--","python3","-c",VM_PROBE]))
def vm_ids(rows):return {(x["pid"],x["start_ticks"],x["executable"]) for x in rows}
def main():
 p=argparse.ArgumentParser();p.add_argument("--runtime",choices=["runsc","firecracker"],required=True);p.add_argument("--restart",choices=["adxlet","coordinator","sandboxd"],required=True);p.add_argument("--output",type=pathlib.Path,required=True);args=p.parse_args()
 out=args.output.resolve();out.relative_to(N/"acceptance/runs");out.mkdir(mode=0o700)
 events=(out/"events.jsonl").open("x",buffering=1)
 def emit(name,**data):events.write(json.dumps({"event":name,"unix_ns":time.time_ns(),**data})+"\n")
 result={"rc":1,"runtime":args.runtime,"restart":args.restart,"diagnostic_not_performance":True,"gc_delete_race_tested":False,"fault_mode":"owned-role-sigkill"};sandbox=None;passed=False
 def crash_owned_role(resource,role):
  expected=json.loads(run(["kubectl","-n","akernel","exec",resource,"--","python3","-c",ROLE_PROBE,role]))
  if len(expected)!=1:raise AssertionError("expected one owned role process before crash")
  old=expected[0];(out/(role+"-before-crash.private.json")).write_text(json.dumps(old,indent=2))
  answer=subprocess.run(BASE+["kubectl","-n","akernel","exec",resource,"--","python3","-c",ROLE_SIGNAL,json.dumps(old)],text=True,capture_output=True,timeout=90)
  (out/(role+"-signal.stdout")).write_text(answer.stdout);(out/(role+"-signal.stderr")).write_text(answer.stderr)
  if not any('"verified_target"' in line for line in answer.stdout.splitlines()):raise RuntimeError("signal target was not verified")
  emit("owned_role_crash_injected",role=role,signal="SIGKILL",command_rc=answer.returncode)
  deadline=time.monotonic()+180
  while True:
   try:
    current=json.loads(run(["kubectl","-n","akernel","exec",resource,"--","python3","-c",ROLE_PROBE,role]))
    if len(current)==1 and (current[0]["pid"],current[0]["start_ticks"])!=(old["pid"],old["start_ticks"]):
     (out/(role+"-after-crash.private.json")).write_text(json.dumps(current[0],indent=2));emit("owned_role_process_restarted",role=role);break
   except Exception:
    if time.monotonic()>deadline:raise
   if time.monotonic()>deadline:raise TimeoutError(role+" supervisor did not restart the crashed role")
   time.sleep(1)
 try:
  if any(k.startswith("environment:") for k in read_state()):raise RuntimeError("another Environment exists before restart test")
  sandbox=Sandbox(runtime=args.runtime,cpu=1000,memory=2048,storage_mb=1024,idle_timeout=900,failover=True)
  identity=sandbox.id;facades=(sandbox.files,sandbox.commands,sandbox.pty);emit("created",sandbox_id=identity)
  def command(text):
   answer=sandbox.commands.run(text,timeout=180)
   if answer.exit_code:raise AssertionError({"command":text,"exit_code":answer.exit_code,"stderr":answer.stderr[-1000:]})
   return answer.stdout
  def probe(mode):return json.loads(command("/tmp/pr119-restart-probe "+mode))
  def memory_state():
   response=probe("state")
   if response["http_status"]!=200:raise AssertionError(response)
   return json.loads(response["body"])
  def capture(previous=None):
   reply=probe("checkpoint --socket /run/akernel/execd.sock --timeout 150");completed(reply)
   deadline=time.monotonic()+60
   while True:
    record=read_state()["environment:"+identity];point=record.get("result",{}).get("checkpoint")
    if point and point["artifact"]["storage"]=="akernel-checkpoints" and (previous is None or point["id"]!=previous["id"]):break
    if time.monotonic()>deadline:raise TimeoutError("new shared checkpoint was not committed")
    time.sleep(0.5)
   emit("checkpoint_committed",point_id_sha256=hashlib.sha256(point["id"].encode()).hexdigest())
   return point
  sandbox.files.write("/tmp/pr119-restart-probe",(N/"acceptance/bin/guest-probe").read_bytes());command("chmod 700 /tmp/pr119-restart-probe")
  sandbox.commands.run("/tmp/pr119-restart-probe hold --bytes 536870912 >/tmp/pr119-restart-hold.log 2>&1",background=True)
  deadline=time.monotonic()+120
  while True:
   try:before=memory_state();break
   except Exception:
    if time.monotonic()>deadline:raise
    time.sleep(0.5)
  root="/pr119-restart-root-state";initial="a"*(1<<20);sandbox.files.write(root,initial);command("sync")
  first=capture()
  sandbox.files.write(root,"changed-before-first-reload");probe("mutate")
  if not sandbox.reload():raise AssertionError("first SDK reload did not succeed")
  if sandbox.files.read(root)!=initial:raise AssertionError("first root rollback differs")
  same_state(before,memory_state())
  sandbox.files.write(root,"checkpoint-two");probe("mutate");second=capture(first)
  # Preserve state newer than the latest recovery point, so adoption cannot pass
  # by silently starting another VM from the checkpoint.
  live_marker="uncheckpointed-live-"+args.restart;sandbox.files.write(root,live_marker);probe("mutate");live=memory_state()
  original=read_state()["environment:"+identity];source=original["assignment"]["node_id"];old_runtime=original["result"]["runtime"]["id"];source_pod=pod_for(source);original_vms=vm_state(source_pod)
  if len(original_vms)!=1:raise AssertionError("expected one owned live runtime")
  original_refs=refs(original);first_key=artifact_key(first["artifact"]);old_reader=any(d["kind"]=="immutable_checkpoint_input" and first["artifact"]["location"] in d["path"] for v in original_vms for d in v["shared_file_dependencies"])
  if old_reader and first_key not in original_refs:raise AssertionError("live runtime reads first checkpoint but authority no longer references it")
  for v in original_vms:
   if any(d["kind"]!="private_anonymous_filestore" and not(d["named_path_exists"] and d["named_path_matches_fd"])for d in v["shared_file_dependencies"]):raise AssertionError("live runtime dependency path already removed")
  (out/"before-restart.private.json").write_text(json.dumps({"record":original,"vms":original_vms},indent=2))
  source_session=read_state()["node:"+source]["session"]["id"]
  emit("restart_prepared",source_node=source,old_checkpoint_reader_observed=old_reader,protected_artifact_count=len(original_refs))
  if args.restart in ["adxlet","sandboxd"]:
   crash_owned_role(source_pod,args.restart)
  else:
   dep=json.loads(run(["kubectl","-n","akernel","get","deployment","akernel-adx-coordinator","-o","json"]))
   if dep["metadata"].get("annotations",{}).get("meta.helm.sh/release-name")!="akernel":raise AssertionError("coordinator outside owned release")
   crash_owned_role("deployment/akernel-adx-coordinator","adx-coordinator")
  deadline=time.monotonic()+240;stable=0
  while True:
   state=read_state();current=state.get("environment:"+identity) or {};r=current.get("result") or {}
   nodes_ok=all(state.get("node:"+name,{}).get("session",{}).get("routable") and state.get("node:"+name,{}).get("node",{}).get("available") and not state.get("node:"+name,{}).get("scheduling_paused") for name in ["akcr119-20261022-worker","akcr119-20261022-worker2"])
   session_ok=args.restart!="adxlet" or state.get("node:"+source,{}).get("session",{}).get("id")!=source_session
   good=nodes_ok and session_ok and r.get("state")=="Running" and r.get("runtime",{}).get("id")==old_runtime and current.get("assignment",{}).get("node_id")==source and original_refs.issubset(refs(current))
   stable=stable+1 if good else 0
   if stable>=3:break
   if time.monotonic()>deadline:
    (out/"restart-timeout.private.json").write_text(json.dumps(state,indent=2));raise TimeoutError("restart did not preserve runtime identity and authoritative references")
   time.sleep(1)
  after_vms=vm_state(source_pod)
  if vm_ids(after_vms)!=vm_ids(original_vms):raise AssertionError("VM process changed across controller restart")
  private_ids=lambda rows:{(d["device"],d["inode"])for v in rows for d in v["shared_file_dependencies"]if d["kind"]=="private_anonymous_filestore"}
  if args.runtime=="runsc"and(not private_ids(original_vms)or private_ids(original_vms)!=private_ids(after_vms)):raise AssertionError("anonymous private filestore changed across role restart")
  if sandbox.files.read(root)!=live_marker:raise AssertionError("uncheckpointed root data was lost during adoption")
  same_state(live,memory_state())
  if sandbox.id!=identity or any(a is not b for a,b in zip(facades,(sandbox.files,sandbox.commands,sandbox.pty))):raise AssertionError("public SDK identity changed")
  for v in after_vms:
   if any(d["kind"]!="private_anonymous_filestore" and not(d["named_path_exists"] and d["named_path_matches_fd"])for d in v["shared_file_dependencies"]):raise AssertionError("live input path removed across restart")
  (out/"after-restart.private.json").write_text(json.dumps({"record":current,"vms":after_vms},indent=2))
  emit("live_state_and_references_survived_restart",old_checkpoint_reader_observed=old_reader,protected_artifact_count=len(original_refs),vm_process_unchanged=True)
  third=capture(second);sandbox.files.write(root,"changed-after-third");probe("mutate")
  if not sandbox.reload():raise AssertionError("post-restart SDK reload did not succeed")
  if sandbox.files.read(root)!=live_marker:raise AssertionError("post-restart checkpoint omitted root data")
  same_state(live,memory_state())
  emit("post_restart_checkpoint_reload_passed")
  passed=True;result.update(rc=0,private_anonymous_filestore_identity_preserved=(args.runtime=="runsc"),old_checkpoint_reader_observed=old_reader,protected_artifact_count=len(original_refs),vm_process_unchanged=True)
 except BaseException as e:
  result.update(error_type=type(e).__name__,error=str(e),sandbox_preserved=None if sandbox is None else sandbox.id);emit("acceptance_failed",**result)
 finally:
  if passed and sandbox is not None:
   try:sandbox.kill();emit("sandbox_deleted",sandbox_id=sandbox.id)
   except BaseException as e:result.update(rc=1,error_type=type(e).__name__,error=str(e))
  (out/"terminal.json").write_text(json.dumps(result,indent=2));events.close()
 return result["rc"]
if __name__=="__main__":sys.exit(main())
