import pathlib,json,subprocess,os,sys,time
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";D=Q/"tap-checksum-fix";S=D/"storage";O=S/"snapshot-gc02";O.mkdir(mode=0o700)
B=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"];result={"rc":1,"cases":[],"internal_delete_barrier_tested":False,"full_lifecycle_fault_matrix_passed":False}
def run(name,argv,timeout):
 with (O/(name+".stdout")).open("x") as so,(O/(name+".stderr")).open("x") as se:p=subprocess.run(argv,stdout=so,stderr=se,timeout=timeout)
 (O/(name+".terminal.json")).write_text(json.dumps({"rc":p.returncode}))
 if p.returncode:raise RuntimeError(name+" failed; preserve owned resources and snapshot references")
try:
 if json.loads((S/"restart-matrix02/terminal.json").read_text()).get("rc")!=0:raise RuntimeError("restart gate not complete")
 for runtime in ["runsc","firecracker"]:
  run("ready-"+runtime,["python3",str(D/"wait-adx-ready01.py"),"--output",str(O/("ready-"+runtime)),"--previous-session-hashes",str(S/"run05/previous-sessions.json"),"--timeout","300"],390)
  name="shared-snapshot-gc02-"+runtime;job=N/"acceptance/runs"/name
  shell='set -eu; source "'+str(Q/"acceptance/auth-shared-tapfix-direct01/sdk.env")+'"; export PYTHONPATH="'+str(Q/"acceptance/scripts")+':'+str(Q/"source/AKernel/sdk/python")+'"; exec "'+str(Q/"sdk/client/bin/python")+'" "'+str(S/"sdk-snapshot-gc02.py")+'" --runtime '+runtime+' --output "'+str(job)+'"'
  result["status"]="running-"+name;(O/"current.json").write_text(json.dumps(result,indent=2))
  run(name,B+["bash","-c",shell],1800);v=json.loads((job/"terminal.json").read_text())
  if v.get("rc")!=0:raise RuntimeError("snapshot lifecycle evidence incomplete")
  result["cases"].append(v)
 result.update(rc=0,status="real-juicefs-snapshot-reader-delete-orderings-passed")
except BaseException as e:result.update(error_type=type(e).__name__,error=str(e))
finally:(O/"terminal.json").write_text(json.dumps(result,indent=2))
sys.exit(result["rc"])
