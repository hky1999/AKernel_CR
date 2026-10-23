import pathlib,json,subprocess,os,sys
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";D=Q/"tap-checksum-fix";S=D/"storage";O=S/"mount-shadow01";O.mkdir(mode=0o700)
B=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"];result={"rc":1,"cases":[],"full_lifecycle_fault_matrix_passed":False}
def run(name,argv,timeout):
 with (O/(name+".stdout")).open("x") as so,(O/(name+".stderr")).open("x") as se:p=subprocess.run(argv,stdout=so,stderr=se,timeout=timeout)
 (O/(name+".terminal.json")).write_text(json.dumps({"rc":p.returncode}))
 if p.returncode:raise RuntimeError(name+" failed; preserve owned resources and dependencies")
try:
 if json.loads((S/"held-reader-restart03/terminal.json").read_text()).get("rc")!=0:raise RuntimeError("held reader restart gate incomplete")
 for runtime in ["runsc","firecracker"]:
  if os.statvfs(N).f_bavail*os.statvfs(N).f_frsize<650*(1<<30):raise RuntimeError("disk reserve below 650 GiB")
  run("ready-"+runtime,["python3",str(D/"wait-adx-ready01.py"),"--output",str(O/("ready-"+runtime)),"--previous-session-hashes",str(S/"run05/previous-sessions.json"),"--timeout","300"],390)
  name="shared-mount-shadow01-"+runtime;job=N/"acceptance/runs"/name
  shell='set -eu; source "'+str(Q/"acceptance/auth-shared-tapfix-direct01/sdk.env")+'"; export PYTHONPATH="'+str(Q/"acceptance/scripts")+':'+str(Q/"source/AKernel/sdk/python")+'"; exec "'+str(Q/"sdk/client/bin/python")+'" "'+str(S/"sdk-mount-shadow01.py")+'" --runtime '+runtime+' --output "'+str(job)+'"'
  result["status"]="running-"+name;(O/"current.json").write_text(json.dumps(result,indent=2))
  run(name,B+["bash","-c",shell],1800);v=json.loads((job/"terminal.json").read_text())
  if v.get("rc")!=0:raise RuntimeError("timeout evidence incomplete")
  result["cases"].append(v)
 result.update(rc=0,status="mount-replacement-fail-closed-with-live-source-passed")
except BaseException as e:result.update(error_type=type(e).__name__,error=str(e))
finally:(O/"terminal.json").write_text(json.dumps(result,indent=2))
sys.exit(result["rc"])
