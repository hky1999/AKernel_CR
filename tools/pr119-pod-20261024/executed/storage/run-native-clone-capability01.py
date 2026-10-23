import pathlib,json,subprocess,sys,os,time,uuid,hashlib
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";D=Q/"tap-checksum-fix";S=D/"storage";O=S/"native-clone-capability01";O.mkdir(mode=0o700)
B=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"];sys.path.insert(0,str(Q/"acceptance/scripts"));from read_control_state import read_control_state
r={"rc":1,"scope":"JuiceFS file primitives only; no runtime integration or SDK route acceptance","cases":[],"runtime_artifacts_changed":False};nonce=uuid.uuid4().hex;root="/mnt/akernel-shared/pr119-native-clone-"+nonce;r.update(root=root,nonce=nonce)
def run(name,argv,timeout=180):
 with (O/(name+".stdout")).open("x")as so,(O/(name+".stderr")).open("x")as se:p=subprocess.run(B+argv,stdout=so,stderr=se,timeout=timeout)
 (O/(name+".terminal.json")).write_text(json.dumps({"rc":p.returncode}))
 if p.returncode:raise RuntimeError(name+" failed; retain owned directory and diagnostics")
 return (O/(name+".stdout")).read_text()
def rgw(name):
 code='import pathlib,subprocess,json,time;s=list(pathlib.Path("/run/ceph").glob("ceph-client.rgw.checkpoints.a.*.asok"));assert len(s)==1;p=subprocess.run(["ceph","--admin-daemon",str(s[0]),"perf","dump"],capture_output=True,text=True,timeout=15);p.check_returncode();v=json.loads(p.stdout);print(json.dumps({"instance":s[0].name,"at":time.time_ns(),"counters":{k:x for k,x in v["rgw_op"].items()if isinstance(x,(int,float))}}))'
 return json.loads(run(name,["kubectl","-n","akernel-pr119-storage","exec","deployment/rook-ceph-rgw-checkpoints-a","-c","rgw","--","python3","-c",code]))
try:
 final=json.loads((S/"performance-pairs02/terminal.json").read_text())
 if final.get("rc")!=0 or final.get("final_profile")!="new-common-tapfix":raise RuntimeError("paired baseline has not finished and restored new profile")
 if any(k.startswith("environment:")for k in read_control_state(N)[1]):raise RuntimeError("Environment exists")
 if os.statvfs(N).f_bavail*os.statvfs(N).f_frsize<650*(1<<30):raise RuntimeError("disk reserve below 650 GiB")
 pods=json.loads(run("pods",["kubectl","-n","akernel","get","pods","-o","json"]))["items"];mapping={}
 for letter,node in [("a","akcr119-20261022-worker"),("b","akcr119-20261022-worker2")]:
  found=[p for p in pods if p["metadata"]["name"].startswith("akernel-node-")and p["spec"].get("nodeName")==node and not p["metadata"].get("deletionTimestamp")]
  if len(found)!=1:raise RuntimeError("owned Node Pod ambiguous")
  p=found[0]
  if any(x.get("imageID","").rsplit("@",1)[-1]!="sha256:20257a27de0137383b1141709fb15dc87f81520f7fe0e41ba17b4e5ee31194a7"for x in p["status"].get("containerStatuses",[])):raise RuntimeError("Node image differs")
  mapping[letter]={"pod":p["metadata"]["name"],"uid":p["metadata"]["uid"]}
 r["nodes"]=mapping;helper=(S/"native-clone-helper01.py").read_text()
 def op(step,letter,role):
  text=run(step,["kubectl","-n","akernel","exec",mapping[letter]["pod"],"--","python3","-c",helper,root,nonce,role])
  lines=[x for x in text.splitlines()if x.startswith("AKCR_CFR_RESULT ")]
  if len(lines)!=1:raise RuntimeError("primitive receipt missing")
  data=json.loads(lines[0].split(" ",1)[1]);r["cases"].append(data);(O/"current.json").write_text(json.dumps(r,indent=2));return data
 op("initialize-base","a","init");op("warm-owner-only","b","preflight")
 before=rgw("before-cold-clone");copied=op("clone-b-without-data-read","b","cold-clone");after=rgw("after-cold-clone")
 if before["instance"]!=after["instance"]:raise RuntimeError("RGW epoch changed")
 delta={k:after["counters"][k]-x for k,x in before["counters"].items()}
 if any(delta[k]!=0 for k in ["get_obj_bytes","put_obj_bytes","get_obj_ops","put_obj_ops"]):raise AssertionError("native metadata clone transferred object data; inspect counters")
 r["cold_clone_rgw_delta"]=delta
 op("branch-b-next-snapshot","b","branch-b");op("independent-client-a-restore","a","branch-a");op("copy-unnamed-open-fd","b","anonymous");op("copy-unflushed-mapped-data","b","mmap");op("truncate-and-hole","b","truncate-hole")
 r.update(rc=0,status="native-file-clone-primitives-passed",files_retained_for_actual_go_clone_check=True,all_short_command_processes_returned=True,full_sdk_route_accepted=False)
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
finally:(O/"terminal.json").write_text(json.dumps(r,indent=2))
sys.exit(r["rc"])
