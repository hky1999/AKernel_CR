import pathlib,json,subprocess,os,sys,time,signal,hashlib
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";D=Q/"tap-checksum-fix";O=D/"native-rwfs-rejoin-directio02";O.mkdir(mode=0o700)
B=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"]
r={"rc":1,"status":"waiting-candidate-sdk","sdk_job_started":False}
def status(name):r["status"]=name;(O/"current.json").write_text(json.dumps(r,indent=2))
try:
 deadline=time.monotonic()+7200
 while not(D/"native-rwfs-rejoin-sdk02/terminal.json").exists():
  if time.monotonic()>deadline:raise TimeoutError("candidate SDK dependency not complete; no stress sandbox created")
  status("waiting-candidate-sdk");time.sleep(2)
 sdk=json.loads((D/"native-rwfs-rejoin-sdk02/terminal.json").read_text())
 if sdk.get("rc")!=0 or not sdk.get("full_sdk_accepted"):raise RuntimeError("candidate SDK dependency failed; no stress sandbox created")
 if sdk.get("sandboxd_sha256")!="debbf268d1b1a8d4a07b9ac02be7084c3fa53c7cf794f0b1887ec65f7ace313b":raise RuntimeError("candidate daemon differs")
 sys.path.insert(0,str(Q/"acceptance/scripts"));from read_control_state import read_control_state
 if any(k.startswith("environment:")for k in read_control_state(N)[1]):raise RuntimeError("Environment remains before stress")
 if os.statvfs(N).f_bavail*os.statvfs(N).f_frsize<650*(1<<30):raise RuntimeError("disk reserve insufficient")
 (O/"cache").mkdir(mode=0o700);job=N/"acceptance/runs/shared-native-rejoin-directio02"
 shell='set -eu; source "'+str(Q/"acceptance/auth-shared-tapfix-direct01/sdk.env")+'"; export PYTHONPATH="'+str(Q/"acceptance/scripts")+'"; export PYTHONDONTWRITEBYTECODE=1; export XDG_CACHE_HOME="'+str(O/"cache")+'"; exec "'+str(Q/"sdk/client/bin/python")+'" "'+str(D/"sdk-direct-io02.py")+'" --output "'+str(job)+'"'
 with(O/"sdk.stdout").open("x")as so,(O/"sdk.stderr").open("x")as se:p=subprocess.Popen(B+["bash","-c",shell],stdout=so,stderr=se,stdin=subprocess.DEVNULL,start_new_session=True)
 receipt={"pid":p.pid,"start_ticks":pathlib.Path("/proc",str(p.pid),"stat").read_text().rsplit(")",1)[1].split()[19],"job":str(job),"guest_source_sha256":hashlib.sha256((D/"guest-direct-io-probe02.py").read_bytes()).hexdigest(),"sdk_source_sha256":hashlib.sha256((D/"sdk-direct-io02.py").read_bytes()).hexdigest()}
 (O/"sdk-process.json").write_text(json.dumps(receipt));r["sdk_job_started"]=True;status("real-guest-direct-io-and-sdk")
 try:rc=p.wait(timeout=3600)
 except subprocess.TimeoutExpired:
  current=pathlib.Path("/proc",str(p.pid),"stat").read_text().rsplit(")",1)[1].split()
  if current[19]!=receipt["start_ticks"]:raise RuntimeError("SDK process identity changed; refuse signal")
  os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(timeout=30)
  except subprocess.TimeoutExpired:raise RuntimeError("owned SDK process group did not stop; preserve dependencies")
  raise TimeoutError("SDK stress timed out; reconcile resources/private names before retry; dependencies retained")
 if rc:raise RuntimeError("real guest stress failed; preserve sandbox dependencies and diagnostics")
 data=json.loads((job/"terminal.json").read_text())
 if data.get("rc")!=0 or not data.get("resources_deleted"):raise RuntimeError("guest stress result incomplete")
 if any(k.startswith("environment:")for k in read_control_state(N)[1]):raise RuntimeError("stress Environment remains")
 r.update(rc=0,status="real-guest-direct-io-stress-passed",data=data)
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
finally:(O/"terminal.json").write_text(json.dumps(r,indent=2))
sys.exit(r["rc"])
