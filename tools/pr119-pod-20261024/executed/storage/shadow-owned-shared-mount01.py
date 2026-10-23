#!/usr/bin/env python3
"""Shadow one task Pod's slave JuiceFS mount, then pop exactly our bind mount."""
import argparse,json,os,pathlib,signal,subprocess,time,sys
TARGET=pathlib.Path("/mnt/akernel-shared")
BASE=pathlib.Path("/home/akernel/.pr119-owned-fault")
def mount_id(path):
 fd=os.open(path,os.O_PATH|os.O_DIRECTORY)
 try:
  for line in pathlib.Path("/proc/self/fdinfo/"+str(fd)).read_text().splitlines():
   if line.startswith("mnt_id:"):return int(line.split()[1])
  raise RuntimeError("mount identity missing")
 finally:os.close(fd)
def mount_rows():
 rows=[]
 for line in pathlib.Path("/proc/self/mountinfo").read_text().splitlines():
  a=line.split();i=a.index("-");rows.append({"id":int(a[0]),"point":a[4],"optional":a[6:i],"type":a[i+1]})
 return rows
def main():
 p=argparse.ArgumentParser();p.add_argument("--work",type=pathlib.Path,required=True);p.add_argument("--namespace",required=True);p.add_argument("--expected-mount",type=int,required=True);a=p.parse_args()
 work=a.work.resolve();work.relative_to(BASE)
 if work==BASE or not work.is_dir():raise RuntimeError("work directory not exclusively prepared")
 out=work/"watchdog";out.mkdir(mode=0o700);shadow=work/"shadow";shadow.mkdir(mode=0o700)
 rows=mount_rows();namespace=os.readlink("/proc/self/ns/mnt")
 if namespace!=a.namespace or mount_id(TARGET)!=a.expected_mount:raise RuntimeError("task Pod namespace/mount identity changed")
 ancestors=[x for x in rows if x["point"]=="/" or str(TARGET)==x["point"] or str(TARGET).startswith(x["point"].rstrip("/")+"/")]
 if any(any(v.startswith("shared:") for v in x["optional"]) for x in ancestors):raise RuntimeError("target has shared propagation; refuse mount fault")
 old=next(x for x in rows if x["id"]==a.expected_mount)
 if old["type"]!="fuse.juicefs":raise RuntimeError("original task mount is not JuiceFS")
 fs=next(x for x in rows if x["id"]==mount_id(work))
 if fs["type"]!="xfs":raise RuntimeError("shadow is not on task local XFS")
 for rel in ["akernel/checkpoints/artifacts","akernel/checkpoints/manifests"]:(shadow/rel).mkdir(parents=True,mode=0o700)
 (shadow/".owner").write_text(work.name)
 proof=shadow/"akernel/checkpoints/manifests/.write-proof";proof.write_bytes(b"task writable local fallback");f=os.open(proof,os.O_RDONLY);os.fsync(f);os.close(f);proof.unlink()
 before=sorted(str(p.relative_to(shadow)) for p in shadow.rglob("*"))
 result={"rc":1,"namespace":namespace,"original_mount_id":a.expected_mount,"original_fstype":old["type"],"shadow_fstype":fs["type"],"bounded_seconds":20,"fallback_prefix_exists_and_writable":True,"before_entries":before}
 mounted=False;own_id=None
 def interrupted(*args):raise SystemExit("watchdog interrupted; restore task mount")
 for sig in [signal.SIGHUP,signal.SIGTERM,signal.SIGINT]:signal.signal(sig,interrupted)
 try:
  subprocess.run(["mount","--bind",str(shadow),str(TARGET)],check=True,capture_output=True,text=True)
  mounted=True;own_id=mount_id(TARGET)
  if own_id==a.expected_mount or (os.stat(TARGET).st_dev,os.stat(TARGET).st_ino)!=(os.stat(shadow).st_dev,os.stat(shadow).st_ino):raise RuntimeError("shadow bind identity mismatch")
  result.update(shadow_mount_id=own_id,shadowed_unix_ns=time.time_ns())
  (out/"shadowed.json").write_text(json.dumps(result,indent=2));time.sleep(20)
 except BaseException as e:result.update(error_type=type(e).__name__,error=str(e))
 finally:
  if mounted:
   try:
    if os.readlink("/proc/self/ns/mnt")!=namespace or mount_id(TARGET)!=own_id or (os.stat(TARGET).st_dev,os.stat(TARGET).st_ino)!=(os.stat(shadow).st_dev,os.stat(shadow).st_ino):raise RuntimeError("top mount is no longer this task's bind; refuse unmount")
    deadline=time.monotonic()+5
    while True:
     answer=subprocess.run(["umount",str(TARGET)],text=True,capture_output=True)
     if answer.returncode==0:break
     if time.monotonic()>deadline:raise RuntimeError("owned bind remains busy; no lazy/forced unmount attempted")
     time.sleep(.2)
    if mount_id(TARGET)!=a.expected_mount:raise RuntimeError("original mount identity did not return")
    result.update(restored_original_mount=True,restored_unix_ns=time.time_ns())
   except Exception as e:result["restore_error"]=str(e)
  result["after_entries"]=sorted(str(p.relative_to(shadow)) for p in shadow.rglob("*"))
  result["no_local_fallback_entries_created"]=result["after_entries"]==before
  if result.get("restored_original_mount") and "error" not in result and "restore_error" not in result:result["rc"]=0
  (out/"terminal.json").write_text(json.dumps(result,indent=2))
 return result["rc"]
if __name__=="__main__":sys.exit(main())
