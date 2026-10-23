#!/usr/bin/env python3
"""Remote-only SDK timing fixture. All clocks and counters have explicit scope."""
import argparse,hashlib,importlib.metadata,json,os,pathlib,re,subprocess,sys,time
from akernel_sdk import Sandbox
from acceptance import completed,same_state
from read_control_state import read_control_state
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";S=Q/"tap-checksum-fix/storage"
B=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"]
def run(argv,timeout=90):
 p=subprocess.run(B+argv,capture_output=True,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError({"rc":p.returncode,"stderr_bytes":len(p.stderr),"operation":argv[:6]})
 return p.stdout
def state():return read_control_state(N)[1]
def rgw():
 code='import pathlib,subprocess,json,time;s=list(pathlib.Path("/run/ceph").glob("ceph-client.rgw.checkpoints.a.*.asok"));assert len(s)==1;p=subprocess.run(["ceph","--admin-daemon",str(s[0]),"perf","dump"],capture_output=True,text=True,timeout=15);p.check_returncode();v=json.loads(p.stdout);print(json.dumps({"rgw_instance":s[0].name,"at_unix_ns":time.time_ns(),"rgw_op":{k:x for k,x in v["rgw_op"].items() if isinstance(x,(int,float))}}))'
 return json.loads(run(["kubectl","-n","akernel-pr119-storage","exec","deployment/rook-ceph-rgw-checkpoints-a","-c","rgw","--","python3","-c",code]))
def delta(a,b):
 if a["rgw_instance"]!=b["rgw_instance"]:raise RuntimeError("RGW counter epoch changed")
 out={k:b["rgw_op"][k]-v for k,v in a["rgw_op"].items() if k in b["rgw_op"]}
 if any(x<0 for x in out.values()):raise RuntimeError("RGW counter reset")
 return out
def main():
 p=argparse.ArgumentParser();p.add_argument("--runtime",choices=["runsc","firecracker"],required=True);p.add_argument("--variant",choices=["old-common-tapfix","new-common-tapfix"],required=True);p.add_argument("--node-id",required=True);p.add_argument("--rounds",type=int,default=1);p.add_argument("--output",type=pathlib.Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.relative_to(N/"acceptance/runs");out.mkdir(mode=0o700)
 events=(out/"events.jsonl").open("x",buffering=1)
 def emit(event,**v):events.write(json.dumps({"event":event,"unix_ns":time.time_ns(),**v})+"\n")
 source=None;result={"rc":1,"variant":a.variant,"runtime":a.runtime,"rounds":[],"scope":"same-node SDK checkpoint/reload; warm infrastructure caches; not node-fault recovery","samples_are_exploratory":True}
 def command(text,timeout=240):
  r=source.commands.run(text,timeout=timeout)
  if r.exit_code:raise RuntimeError({"guest_command_exit":r.exit_code,"stderr_bytes":len(r.stderr)})
  return r.stdout
 def memory():return json.loads(json.loads(command("/tmp/pr119-memory-probe state"))["body"])
 def authority_identity():
  r=state()["environment:"+source.id];node=r["assignment"]["node_id"];logical=r["result"]["runtime"]["id"]
  pods=json.loads(run(["kubectl","-n","akernel","get","pods","-o","json"]))["items"]
  matches=[p for p in pods if p["metadata"]["name"].startswith("akernel-node-") and p["spec"].get("nodeName")==node]
  if len(matches)!=1:raise RuntimeError("Node Pod identity ambiguous")
  pod=matches[0]
  code="import pathlib,json;found=[]\nfor p in pathlib.Path('/home/akernel/sandboxd/root/containers').glob('*/config.json'):\n try:v=json.loads(p.read_text()).get('annotations',{})\n except (OSError,ValueError):continue\n if v.get('adx.environment_id')=="+repr(source.id)+" and v.get('adx.runtime_id')=="+repr(logical)+":found.append(p.parent.name)\nassert len(found)==1,found\nprint(json.dumps(found[0]))"
  sid=json.loads(run(["kubectl","-n","akernel","exec",pod["metadata"]["name"],"--","python3","-c",code]))
  return {"pod":pod["metadata"]["name"],"pod_uid":pod["metadata"]["uid"],"node":node,"logical_runtime":logical,"sandboxd_id":sid,"image":pod["spec"]["containers"][0]["image"]}
 def phases(identity):
  if a.runtime!="firecracker":return {"available":False,"reason":"fixed gVisor adapter has no equivalent host phase fields"}
  code="import pathlib,re,json;sid="+repr(identity["sandboxd_id"])+";result=[]\np=pathlib.Path('/home/akernel/logs/sandboxd/sandboxd.log')\nwith p.open('rb') as f:\n f.seek(max(0,p.stat().st_size-8*1024*1024));text=f.read().decode(errors='replace')\nfor line in text.splitlines():\n if sid not in line or 'phases: ' not in line or 'firecracker:' not in line:continue\n kind='checkpoint' if 'checkpointed sandbox '+sid in line else 'restore' if 'restored sandbox '+sid in line else None\n if kind is None:continue\n values={k:int(v) for k,v in re.findall(r'(layout|flush|pause|snapshot|overlay|resume|seal|total|open|prepare|instantiate|vmm_ready|load|agent)=(\\d+)ms',line)}\n typ=re.search(r'type=(\\w+)',line);result.append(dict(kind=kind,values_ms=values,snapshot_type=typ.group(1) if typ else None))\nprint(json.dumps(result))"
  records=json.loads(run(["kubectl","-n","akernel","exec",identity["pod"],"--","python3","-c",code]))
  return {"available":bool(records),"records":records,"pause_field_scope":"pause is API-call phase only; not the entire guest stop window"}
 try:
  expected_native="0.1.0rc2" if a.variant=="old-common-tapfix" else "0.1.0rc3"
  versions={k:importlib.metadata.version(k) for k in ["akernel-sdk","adx-environment"]}
  if versions!={"akernel-sdk":"0.2.0rc3","adx-environment":expected_native}:raise RuntimeError("SDK version mismatch")
  if os.environ.get("AKERNEL_VERIFY_TLS","").lower()not in ["true","1"] or not os.environ.get("SSL_CERT_FILE"):raise RuntimeError("TLS verification and private CA required")
  if any(k.startswith("environment:") for k in state()):raise RuntimeError("another Environment exists")
  result["sdk_versions"]=versions
  source=Sandbox(runtime=a.runtime,cpu=1000,memory=2048,storage_mb=1024,idle_timeout=900,failover=True,node_id=a.node_id)
  (out/"resources.private.json").write_text(json.dumps({"source_id":source.id}))
  source.files.write("/tmp/pr119-memory-probe",(N/"acceptance/bin/guest-probe").read_bytes())
  observer=S/"performance-observation02/guest-observer";source.files.write("/tmp/pr119-observer",observer.read_bytes())
  result["observer_sha256"]=hashlib.sha256(observer.read_bytes()).hexdigest()
  command("chmod 700 /tmp/pr119-memory-probe /tmp/pr119-observer")
  source.commands.run("/tmp/pr119-memory-probe hold --bytes 536870912 >/tmp/pr119-perf-hold.log 2>&1",background=True)
  source.commands.run("/tmp/pr119-observer serve >/tmp/pr119-perf-observer.log 2>&1",background=True)
  deadline=time.monotonic()+120
  while True:
   try:baseline=memory();json.loads(command("/tmp/pr119-observer stats"));break
   except Exception:
    if time.monotonic()>deadline:raise
    time.sleep(.25)
  command("dd if=/dev/urandom of=/pr119-perf-large bs=1048576 count=64 conv=fsync")
  large_sha=command("sha256sum /pr119-perf-large").split()[0]
  if not re.fullmatch("[0-9a-f]{64}",large_sha):raise RuntimeError("invalid root file hash")
  result.update(memory_bytes=536870912,root_file_bytes=67108864,vm_memory_mb=2048,private_storage_mb=1024,requested_cpu_millis=1000,assigned_node=a.node_id)
  for index in range(a.rounds):
   pre=authority_identity()
   if pre["node"]!=a.node_id:raise RuntimeError("wrong actual node")
   original="captured-root-"+str(index);source.files.write("/pr119-perf-small",original)
   command("/tmp/pr119-observer reset");time.sleep(.25)
   idle=json.loads(command("/tmp/pr119-observer stats"))
   before_cp=rgw();command("/tmp/pr119-observer reset")
   outer_begin=time.monotonic_ns()
   reply=json.loads(command("/tmp/pr119-memory-probe checkpoint --socket /run/akernel/execd.sock --timeout 150"))
   outer_ms=(time.monotonic_ns()-outer_begin)/1e6;completed(reply)
   gaps=json.loads(command("/tmp/pr119-observer stats"));after_cp=rgw()
   source.files.write("/pr119-perf-small","changed-after-capture")
   json.loads(command("/tmp/pr119-memory-probe mutate"))
   before_restore=rgw();start=time.monotonic_ns()
   if not source.reload():raise AssertionError("SDK reload returned false")
   reload_ms=(time.monotonic_ns()-start)/1e6
   if source.files.read("/pr119-perf-small")!=original:raise AssertionError("root version mismatch")
   first_ms=(time.monotonic_ns()-start)/1e6
   same_state(baseline,memory());memory_ms=(time.monotonic_ns()-start)/1e6
   if command("sha256sum /pr119-perf-large").split()[0]!=large_sha:raise AssertionError("large root file mismatch")
   full_ms=(time.monotonic_ns()-start)/1e6;after_restore=rgw();post=authority_identity()
   if post["node"]!=pre["node"] or post["logical_runtime"]==pre["logical_runtime"]:raise AssertionError("reload did not replace runtime on same node")
   r={"round":index,"checkpoint_http_ms":reply["elapsed_ms"],"checkpoint_outer_command_ms":outer_ms,"sdk_reload_ms":reload_ms,"first_verified_root_ms":first_ms,"full_memory_verified_ms":memory_ms,"full_root_and_memory_verified_ms":full_ms,"idle_guest_observer":idle,"checkpoint_guest_observer":gaps,"checkpoint_rgw_delta":delta(before_cp,after_cp),"reload_through_full_verification_rgw_delta":delta(before_restore,after_restore),"checkpoint_host_phases":phases(pre),"restore_host_phases":phases(post),"state_verified":True}
   result["rounds"].append(r);(out/"current.json").write_text(json.dumps(result,indent=2));emit("round_passed",**r)
  source.kill();source=None
  deadline=time.monotonic()+120
  while any(k.startswith("environment:") for k in state()):
   if time.monotonic()>deadline:raise TimeoutError("SDK-deleted source did not retire")
   time.sleep(1)
  result.update(rc=0,resources_deleted=True)
 except BaseException as e:
  result.update(error_type=type(e).__name__,error_code=getattr(e,"code",None),preserved_source_id=None if source is None else source.id)
  emit("acceptance_failed",error_type=type(e).__name__,error_code=getattr(e,"code",None))
 finally:(out/"terminal.json").write_text(json.dumps(result,indent=2));events.close()
 return result["rc"]
if __name__=="__main__":sys.exit(main())
