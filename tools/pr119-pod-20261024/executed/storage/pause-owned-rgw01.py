#!/usr/bin/env python3
"""Bounded SIGSTOP/SIGCONT for one pinned task RGW process, never a shared service."""
import argparse,json,os,pathlib,signal,time,sys
p=argparse.ArgumentParser();p.add_argument("--out",type=pathlib.Path,required=True);p.add_argument("--seconds",type=int,default=20);a=p.parse_args()
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp")
out=a.out.resolve();out.relative_to(N/"acceptance/runs");out.mkdir(mode=0o700)
PID=1024035;START="209686351";CID="8d9fe34dc23d050d54ebdf939bbf4947ff92275db387adc9af2a5a61f63aa352";ROOT="akernel-pr119-followup-20261022-qbGAw9tp";CP="309834713ae51c81b89d88111a2a0adaf345f9ec135d8d3938d20f4727023bfa"
def identity():
 p=pathlib.Path("/proc")/str(PID);cg=(p/"cgroup").read_text();stat=(p/"stat").read_text().split()
 if PID<=1 or stat[21]!=START or CID not in cg or ROOT not in cg or CP not in cg or os.path.basename(os.readlink(p/"exe"))!="radosgw":raise RuntimeError("pinned RGW identity does not match; refuse signal")
 return stat[2]
def interrupted(*args):raise SystemExit("task watchdog interrupted; resume pinned process")
for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(sig,interrupted)
paused=False;r={"rc":1,"pid":PID,"start_ticks":START,"seconds":a.seconds}
try:
 if not 1<=a.seconds<=20:raise ValueError("pause bound must be at most twenty seconds")
 if identity() in ["T","t"]:raise RuntimeError("RGW already stopped; refuse to take over an unknown fault")
 os.kill(PID,signal.SIGSTOP);paused=True
 deadline=time.monotonic()+3
 while identity() not in ["T","t"]:
  if time.monotonic()>deadline:raise TimeoutError("pinned process did not stop")
  time.sleep(.01)
 r["paused_unix_ns"]=time.time_ns();(out/"paused.json").write_text(json.dumps(r))
 time.sleep(a.seconds)
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
finally:
 if paused:
  try:
   identity();os.kill(PID,signal.SIGCONT);r["resumed_unix_ns"]=time.time_ns()
   deadline=time.monotonic()+3
   while identity() in ["T","t"]:
    if time.monotonic()>deadline:raise TimeoutError("pinned RGW remained stopped after CONT")
    time.sleep(.01)
   r["same_process_resumed"]=True
   if "error" not in r:r["rc"]=0
  except Exception as e:r["resume_error"]=str(e)
 (out/"terminal.json").write_text(json.dumps(r,indent=2))
sys.exit(r["rc"])
