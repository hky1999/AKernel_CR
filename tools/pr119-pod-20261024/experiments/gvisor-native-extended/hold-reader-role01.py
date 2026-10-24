#!/usr/bin/env python3
"""Pin an open input reader across one owned ADX role crash; resume within 3 seconds."""
import argparse,json,os,pathlib,signal,stat,time,uuid,sys,hashlib
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp")
CGROOT="akernel-pr119-followup-20261022-qbGAw9tp"
def process(pid):
 p=pathlib.Path("/proc")/str(pid);s=(p/"stat").read_text().rsplit(")",1)[1].split()
 return {"pid":int(pid),"start_ticks":s[19],"state":s[0],"cgroup":(p/"cgroup").read_text(),"exe":os.readlink(p/"exe"),"args":[os.fsdecode(x) for x in (p/"cmdline").read_bytes().split(b"\0") if x]}
def candidates(kind,cid,executable=None,sandbox_id=None):
 rows=[]
 for p in pathlib.Path("/proc").iterdir():
  if not p.name.isdigit():continue
  try:
   cg=(p/"cgroup").read_text()
   if CGROOT not in cg or kind not in cg or (cid and cid not in cg):continue
   v=process(int(p.name))
   if executable and os.path.basename(v["exe"])!=executable:continue
   if sandbox_id and (not v["args"] or os.path.basename(v["args"][0])!="runsc-sandbox" or not any(sandbox_id in x for x in v["args"])):continue
   rows.append(v)
  except (OSError,ValueError):continue
 return rows
def exact(old,kind,cid=None):
 v=process(old["pid"])
 if v["pid"]<=1 or v["start_ticks"]!=old["start_ticks"] or v["exe"]!=old["exe"] or CGROOT not in v["cgroup"] or kind not in v["cgroup"] or (cid and cid not in v["cgroup"]):raise RuntimeError("owned process identity changed; refuse signal")
 return v
def input_fds(pid,artifact):
 rows=[]
 expected=pathlib.Path('/mnt/akernel-shared/akernel/checkpoints/artifacts')/artifact/'pages.img'
 for f in(pathlib.Path('/proc')/str(pid)/'fd').iterdir():
  try:
   target=os.readlink(f);info=f.stat()
   # Private anonymous clones may be named under this artifact but have
   # independent data references. Only the real, named async pages input counts.
   if target!=str(expected)or not stat.S_ISREG(info.st_mode):continue
   named=(pathlib.Path('/proc')/str(pid)/'root'/str(expected).lstrip('/')).stat()
   if(info.st_dev,info.st_ino)!=(named.st_dev,named.st_ino):raise RuntimeError('input FD differs from protected named input')
   rows.append({'fd':int(f.name),'path':target,'device':info.st_dev,'inode':info.st_ino,'bytes':info.st_size})
  except(FileNotFoundError,PermissionError):continue
 return rows
def main():
 def interrupted(*args):raise SystemExit("bounded reader helper interrupted; resume owned reader")
 signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
 p=argparse.ArgumentParser();p.add_argument("--request",type=pathlib.Path,required=True);p.add_argument("--out",type=pathlib.Path,required=True);a=p.parse_args()
 out=a.out.resolve();out.relative_to(N/"acceptance/runs");out.mkdir(mode=0o700)
 req=json.loads(a.request.read_text());artifact=req["artifact_id"]
 if str(uuid.UUID(artifact))!=artifact or req["role"] not in ["adxlet","coordinator","sandboxd"]:raise ValueError("invalid bounded test request")
 meta=pathlib.Path(req["metadata_root"]).resolve();meta.relative_to(N/"node-data09")
 matches=[]
 for d in meta.iterdir():
  try:
   ann=json.loads((d/"config.json").read_text()).get("annotations",{})
   if ann.get("adx.environment_id")==req["environment_id"]:matches.append({"sandbox_id":d.name,"runtime_id":ann.get("adx.runtime_id"),"ownership_generation":ann.get("adx.generation")})
  except (OSError,ValueError):pass
 if len(matches)!=1 or not matches[0]["sandbox_id"].startswith("sbox-"):raise RuntimeError("reader metadata binding is not unique")
 sentries=candidates(req["reader_kind_id"],None,sandbox_id=matches[0]["sandbox_id"])
 role_name={"adxlet":"adxlet","coordinator":"adx-coordinator","sandboxd":"sandboxd"}[req["role"]]
 roles=candidates(req["role_kind_id"],req["role_container_id"],executable=role_name)
 if len(sentries)!=1 or len(roles)!=1:raise RuntimeError("owned reader/role process binding is not unique")
 sentry=sentries[0];role=roles[0]
 if role["pid"]==1 or not(role["exe"].startswith("/opt/adx/")or(role_name=="sandboxd"and role["exe"]=="/usr/local/bin/sandboxd")):raise RuntimeError("role is not an accepted task executable")
 if hashlib.sha256((pathlib.Path('/proc')/str(sentry['pid'])/'exe').read_bytes()).hexdigest()!=req['expected_reader_sha256']:raise RuntimeError('reader ELF differs')
 if hashlib.sha256((pathlib.Path('/proc')/str(role['pid'])/'exe').read_bytes()).hexdigest()!=req['expected_role_sha256']:raise RuntimeError('role ELF differs')
 result={"rc":1,"role":req["role"],"reader":{"pid":sentry["pid"],"start_ticks":sentry["start_ticks"],"exe":sentry["exe"],"runtime_id":matches[0]["runtime_id"],"ownership_generation":matches[0]["ownership_generation"]},"role_before":{"pid":role["pid"],"start_ticks":role["start_ticks"],"exe":role["exe"]},"barrier_seconds":3}
 stopped=False
 try:
  exact(sentry,req["reader_kind_id"])
  if not input_fds(sentry["pid"],artifact):raise RuntimeError("shared input FD already closed; no crash injected")
  os.kill(sentry["pid"],signal.SIGSTOP);stopped=True
  deadline=time.monotonic()+2
  while exact(sentry,req["reader_kind_id"])["state"] not in ["T","t"]:
   if time.monotonic()>deadline:raise TimeoutError("reader did not enter bounded stop")
   time.sleep(.01)
  fds=input_fds(sentry["pid"],artifact)
  if not fds:raise RuntimeError("input closed before the reader barrier; no role crash injected")
  result["reader_barrier_entered_unix_ns"]=time.time_ns();result["shared_input_fd_count_at_role_crash"]=len(fds)
  exact(role,req["role_kind_id"],req["role_container_id"]);os.kill(role["pid"],signal.SIGKILL);result["role_crash_unix_ns"]=time.time_ns()
  (out/"role-crashed.json").write_text(json.dumps(result,indent=2))
  time.sleep(3)
 except BaseException as e:result.update(error_type=type(e).__name__,error=str(e))
 finally:
  if stopped:
   try:
    exact(sentry,req["reader_kind_id"]);os.kill(sentry["pid"],signal.SIGCONT)
    result["reader_resumed_unix_ns"]=time.time_ns();result["same_reader_resumed"]=True
   except Exception as e:result["reader_resume_error"]=str(e)
  if "role_crash_unix_ns" in result and result.get("same_reader_resumed") and "error" not in result:result["rc"]=0
  (out/"terminal.json").write_text(json.dumps(result,indent=2))
 return result["rc"]
if __name__=="__main__":sys.exit(main())
