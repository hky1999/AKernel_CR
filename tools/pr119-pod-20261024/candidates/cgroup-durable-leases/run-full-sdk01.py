import pathlib,json,subprocess,os,sys,time,hashlib,yaml,tomllib,copy
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";D=Q/"tap-checksum-fix";S=D/"storage";O=D/"cgroup-durable-leases-sdk01";O.mkdir(mode=0o700);(O/"cache").mkdir(mode=0o700);os.environ["XDG_CACHE_HOME"]=str(O/"cache")
B=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"]
sys.path.insert(0,str(Q/"acceptance/scripts"));from read_control_state import read_control_state
r={"rc":1,"roll_attempted":False,"deployed":False,"status":"preflight","cases":[],"steps":[]}
def status(phase):
 r["status"]=phase;(O/"current.json").write_text(json.dumps(r,indent=2))
def run(name,args,timeout=900):
 with (O/(name+".stdout")).open("x")as so,(O/(name+".stderr")).open("x")as se:p=subprocess.run(args,stdout=so,stderr=se,timeout=timeout)
 r["steps"].append({"name":name,"rc":p.returncode});(O/"current.json").write_text(json.dumps(r,indent=2))
 if p.returncode:raise RuntimeError(name+" failed; retain current profile and unknown operation before retry")
 return (O/(name+".stdout")).read_text()
def lab(name,args,timeout=900):return run(name,B+args,timeout)
def records():return read_control_state(N)[1]
def no_env():
 if any(k.startswith("environment:")for k in records()):raise RuntimeError("Environment remains; refuse rollout or next case")
def replace_once(text,before,after):
 if text.count(before)!=1:raise RuntimeError("script generation match is not unique")
 return text.replace(before,after)
try:
 inputs=pathlib.Path(__file__).parent;manifest=json.loads((inputs/'input-manifest.json').read_text())
 for name in ['sdk-held-reader03.py','hold-reader-role02.py','check-preserved-snapshot01.py']:
  data=(inputs/name).read_bytes()
  if hashlib.sha256(data).hexdigest()!=manifest['sources'][name]:raise RuntimeError('SDK probe input changed')
  compile(data,str(O/name),'exec');(O/name).write_bytes(data)
 im=json.loads((D/"cgroup-durable-leases-image01/terminal.json").read_text())
 if im.get("rc")!=0 or im["sandboxd_sha256"]!="433574033952b1ad9106b125e085302b9c5268fea179609975de7d722c2f6c83":raise RuntimeError("candidate image gate incomplete")
 if os.statvfs(N).f_bavail*os.statvfs(N).f_frsize<650*(1<<30):raise RuntimeError("disk reserve insufficient")
 no_env();nodes=["akcr119-20261022-worker","akcr119-20261022-worker2"]
 before=records();previous={node:hashlib.sha256(str(before["node:"+node]["session"]["id"]).encode()).hexdigest()for node in nodes}
 pp=O/"previous-sessions.json";pp.write_text(json.dumps(previous))
 # Prepare a strictly pinned readiness gate before rolling any service.
 gate=(S/"wait-perf-ready02.py").read_text()
 lines=gate.splitlines();choices=[i for i,x in enumerate(lines)if x.startswith('p.add_argument("--expected-digest",choices=')]
 if len(choices)!=1:raise RuntimeError("readiness digest definition ambiguous")
 lines[choices[0]]='p.add_argument("--expected-digest",choices=['+repr(im["expected_cri_digest"])+'],required=True)'
 gate="\n".join(lines)+"\n"
 gate=replace_once(gate,"9c74060c3c4edceed6edb746e6b42bdd21116e3663427238fb1dd5067f3c964b",im["sandboxd_sha256"])
 (O/"wait-ready01.py").write_text(gate);compile(gate,str(O/"wait-ready01.py"),"exec")
 official=replace_once((S/"sdk-full02.sh").read_text(),'OUT="$D/storage/sdk-full02"','OUT="$D/cgroup-durable-leases-sdk01/official-sdk"')
 official=replace_once(official,'export HOME="$OUT/home"\nmkdir -m 700 "$HOME"','export XDG_CACHE_HOME="$OUT/cache"\nmkdir -m 700 "$XDG_CACHE_HOME"')
 (O/"sdk-full01.sh").write_text(official)
 run("official-shell-syntax",["bash","-n",str(O/"sdk-full01.sh")])
 perf=(D/"sdk-writable-performance01.py").read_text().replace("new-writable-candidate","new-gvisor-native-candidate")
 (O/"sdk-performance01.py").write_text(perf);compile(perf,str(O/"sdk-performance01.py"),"exec")
 cross=(S/"cross-node05.py").read_text()
 cross=replace_once(cross,'O=S/"cross-node05";O.mkdir(mode=0o700)','O=D/"cgroup-durable-leases-sdk01/cross-node01";O.mkdir(mode=0o700)')
 cross=replace_once(cross,'str(D/"wait-adx-ready01.py")','str(O.parent/"wait-ready01.py"),"--expected-digest",'+repr(im["expected_cri_digest"]))
 cross=replace_once(cross,'str(S/"run05/previous-sessions.json")','str(O.parent/"previous-sessions.json")')
 cross=replace_once(cross,'(S/"run06/terminal.json")','(O.parent/"same-node-accepted.json")')
 cross=replace_once(cross,'name="shared-tapfix-direct01-"','name="shared-cgroup-leases-sdk01-"')
 (O/"cross-node01.py").write_text(cross);compile(cross,str(O/"cross-node01.py"),"exec")
 secretargs=["kubectl","-n","akernel","get","secrets","akernel-adx-tls","akernel-secrets","-o",'jsonpath={range .items[*]}{.metadata.name}{" "}{.metadata.uid}{"\\n"}{end}']
 secrets=lab("secret-uids-before",secretargs)
 ds=json.loads(lab("node-template-before",["kubectl","-n","akernel","get","daemonset","akernel-node","-o","json"]))
 original_image=ds["spec"]["template"]["spec"]["containers"][0]["image"]
 if original_image!="localhost/akernel-pr119:365f7971f895-gvisor-native02":raise RuntimeError("original profile differs; inspect before changing")
 profile=D/'gvisor-native-consumer-sdk01/writable-values.yaml'
 values=yaml.safe_load(profile.read_text())
 cfg=values['node']['config']['sandboxd']['config']
 original_cfg=tomllib.loads(cfg)
 if original_cfg['plugin']['runtime']['filestore_dir']!='/home/akernel/filestore':raise RuntimeError('common filestore changed')
 if original_cfg['plugin']['runtime']['firecracker'].get('writable_storage_dir')!='/mnt/akernel-shared/akernel/fc-rwfs-native-qbGAw9tp01':raise RuntimeError('FC profile changed')
 ROOT='/mnt/akernel-shared/akernel/runsc-rwfs-native-qbGAw9tp01'
 settings={'checkpoint_mode':'reflink','writable_storage_dir':ROOT,'writable_storage_filesystem':'fuse.juicefs'}
 current=original_cfg['plugin']['runtime']['runsc']
 if any(current.get(k)!=v for k,v in settings.items()):raise RuntimeError('existing native runsc profile differs')
 (O/'writable-values.yaml').write_bytes(profile.read_bytes())
 allpods=json.loads(lab('pre-roll-owned-pods',['kubectl','-n','akernel','get','pods','-o','json']))['items']
 if len([p for p in allpods if not p['metadata'].get('deletionTimestamp')])!=5:raise RuntimeError('base workload count differs')
 if any(c.get('imageID','').rsplit('@',1)[-1]!='sha256:0806341c5c1939a52497c4dfb28d6b111819322405b33e0f1bb344145fc38660'for p in allpods for c in p['status'].get('containerStatuses',[])):raise RuntimeError('base image differs')
 for pod in [p for p in allpods if p['metadata']['name'].startswith('akernel-node-')]:
  code="from pathlib import Path;import os,json\nroot=Path("+repr(ROOT)+");assert root.resolve()==root and root.is_dir();m=json.loads((root/'.task-owner').read_text());assert m['task']=="+repr(N.name)+" and m['runtime_bundle_sha256']=="+repr(im['runtime_bundle_sha256'])+";assert {p.name for p in root.iterdir()}=={'.task-owner'}\nfor p in Path('/proc').iterdir():\n if not p.name.isdigit():continue\n try:name=(p/'comm').read_text().strip();state=(p/'stat').read_text().rsplit(')',1)[1].split()[0]\n except OSError:continue\n assert name not in {'firecracker','gvisor_sentry','checkpointgofer'}or state=='Z','live runtime remains'\nprint(json.dumps({'root_owner_verified':True,'no_running_runtime':True}))"
  compile(code,'owned-preflight','exec');lab('native-root-'+pod['spec']['nodeName'],['kubectl','-n','akernel','exec',pod['metadata']['name'],'--','python3','-c',code])
 r.update(runtime_bundle_sha256=im['runtime_bundle_sha256'],native_private_layout_unchanged=True)
 # Check our prior bootstrap was restored; do not modify it in this experiment.
 rescue=json.loads((D/'native-rwfs-rejoin-rescue03/terminal.json').read_text())
 cm=json.loads(lab('bootstrap-current-private',['kubectl','-n','akernel','get','configmap',rescue['bootstrap_configmap'],'-o','json']))
 if cm['metadata']['uid']!=rescue['bootstrap_uid']or hashlib.sha256(cm['data'][rescue['bootstrap_key']].encode()).hexdigest()!=rescue['original_script_sha256']:raise RuntimeError('bootstrap differs; no rollout')
 def retained(name):
  shell='set -eu; source '+str(Q/'acceptance/auth-shared-tapfix-direct01/sdk.env')+'; export PYTHONDONTWRITEBYTECODE=1; exec '+str(Q/'sdk/client/bin/python')+' '+str(O/'check-preserved-snapshot01.py')
  data=json.loads(run(name,B+['bash','-c',shell],180));assert data['retained_snapshot_retrievable'];return data
 preserved=retained('diagnostic-snapshot-before')
 r.update(roll_attempted=True,original_image=original_image,candidate=im["image"],expected_cri_digest=im["expected_cri_digest"],sandboxd_sha256=im["sandboxd_sha256"]);status("rolling-owned-candidate")
 lab("helm-candidate",["helm","upgrade","--install","akernel",str(Q/"source/AKernel/deploy/akernel/charts/core"),"--namespace","akernel","-f",str(O/"writable-values.yaml"),"-f",str(Q/"source/AKernel/deploy/shared-storage/juicefs-values.yaml"),"--set-string","image.tag="+im["image"].split(":",1)[1],"--post-renderer",str(N/"cluster/helm11/control-placement.py"),"--wait","--timeout=8m"],540)
 for role in ["daemonset/akernel-node","deployment/akernel-adx-coordinator","deployment/akernel-adx-ingress-api"]:
  lab("rollout-"+role.split("/")[1],["kubectl","-n","akernel","rollout","status",role,"--timeout=240s"],270)
 run("fresh-routable-schedulable",[sys.executable,str(O/"wait-ready01.py"),"--expected-digest",im["expected_cri_digest"],"--output",str(O/"ready"),"--previous-session-hashes",str(pp),"--timeout","360"],450)
 if lab("secret-uids-after",secretargs)!=secrets:raise RuntimeError("Secret identity changed")
 if retained('diagnostic-snapshot-after')!=preserved:raise RuntimeError('retained diagnostic snapshot identity changed')
 pods=json.loads(lab("candidate-pod-identities",["kubectl","-n","akernel","get","pods","-o","json"]))["items"]
 live=[p for p in pods if not p["metadata"].get("deletionTimestamp")and any(p["metadata"]["name"].startswith(x)for x in ["akernel-node-","akernel-adx-coordinator-","akernel-adx-ingress-api-"])]
 if len(live)!=4 or any(c.get("imageID","").rsplit("@",1)[-1]!=im["expected_cri_digest"]for p in live for c in p["status"].get("containerStatuses",[])):raise RuntimeError("actual core image identities differ")
 assets=json.loads((Q/"image-build/payload-receipt.json").read_text())["assets"]
 paths=["/usr/local/bin/sandboxd","/usr/local/bin/runsc","/usr/local/bin/firecracker","/opt/firecracker/initrd.img","/opt/firecracker/vmlinux","/opt/akernel/runtime/akernel-runtime-rootfs.img","/opt/adx/current/runtime/adx-execd","/opt/adx/current/bin/adxlet","/opt/adx/current/bin/adx-coordinator","/opt/adx/current/bin/adx-apiserver"]
 pins={p:assets[p]["sha256"]for p in paths};pins["/usr/local/bin/sandboxd"]=im["sandboxd_sha256"]
 for name,asset in im['runtime_assets'].items():
  path='/usr/local/bin/'+name
  if path not in paths:paths.append(path)
  pins[path]=asset['sha256']
 for pod in [p for p in live if p["metadata"]["name"].startswith("akernel-node-")]:
  text=lab("payload-"+pod["metadata"]["name"],["kubectl","-n","akernel","exec",pod["metadata"]["name"],"--","sha256sum",*paths])
  if {x.split()[1]:x.split()[0]for x in text.splitlines()if len(x.split())==2}!=pins:raise RuntimeError("actual payload mismatch")
 r["deployed"]=True;status("strict-reader-restarts")
 # First reproduce the original failed target, then the other direction and roles.
 strict=[]
 for role,target in [('sandboxd',nodes[0]),('sandboxd',nodes[1]),('adxlet',nodes[0]),('coordinator',nodes[1])]:
  no_env();name='strict-'+role+'-'+target;status(name)
  job=N/'acceptance/runs'/('shared-cgroup-leases-sdk01-'+name)
  shell='set -eu; source '+str(Q/'acceptance/auth-shared-tapfix-direct01/sdk.env')+'; export PYTHONPATH='+str(Q/'acceptance/scripts')+':'+str(Q/'source/AKernel/sdk/python')+'; export PYTHONDONTWRITEBYTECODE=1; exec '+str(Q/'sdk/client/bin/python')+' '+str(O/'sdk-held-reader03.py')+' --role '+role+' --target-node '+target+' --output '+str(job)
  run(name,B+['bash','-c',shell],1800)
  result=json.loads((job/'terminal.json').read_text())
  if result['rc']!=0 or not result['open_input_at_role_crash_proven']or not result['original_runtime_preserved']:raise RuntimeError('strict reader did not survive; stop before official SDK')
  strict.append(result);no_env()
 r['strict_reader_restarts']=strict
 status("official-sdk")
 run("official-sdk",B+["bash",str(O/"sdk-full01.sh")],4500)
 if json.loads((O/"official-sdk/terminal.json").read_text()).get("rc")!=0:raise RuntimeError("official SDK did not finish")
 for rt,node in [("firecracker",nodes[1]),("runsc",nodes[0])]:
  no_env();status("state-and-phases-"+rt)
  job=N/"acceptance/runs"/("shared-cgroup-leases-sdk01-"+rt+"-three")
  shell='set -eu; source "'+str(Q/"acceptance/auth-shared-tapfix-direct01/sdk.env")+'"; export PYTHONPATH="'+str(Q/"acceptance/scripts")+'"; export PYTHONDONTWRITEBYTECODE=1; export XDG_CACHE_HOME="'+str(O/"cache")+'"; exec "'+str(Q/"sdk/client/bin/python")+'" "'+str(O/"sdk-performance01.py")+'" --runtime '+rt+' --variant new-gvisor-native-candidate --node-id '+node+' --rounds 3 --output "'+str(job)+'"'
  run("state-three-"+rt,B+["bash","-c",shell],1800)
  data=json.loads((job/"terminal.json").read_text())
  if data.get("rc")!=0 or len(data.get("rounds",[]))!=3:raise RuntimeError("state rounds incomplete")
  r["cases"].append(data)
 no_env();(O/"same-node-accepted.json").write_text(json.dumps({"rc":0,"shared_sdk_accepted":True,"candidate":im["image"]}))
 status("bidirectional-sdk-failover")
 run("cross-node",["python3",str(O/"cross-node01.py")],7200)
 cross_result=json.loads((O/"cross-node01/terminal.json").read_text())
 if cross_result.get("rc")!=0 or not cross_result.get("cross_node_accepted"):raise RuntimeError("bidirectional failover incomplete")
 no_env();r.update(rc=0,status="cgroup-lease-strict-reader-sdk-state-and-bidirectional-failover-passed",cross_node=cross_result,full_sdk_accepted=True,concurrent_guest_direct_io_stress_accepted=False,remaining="native layout mount/sync faults and paired comparison; remote baseline/local delta unaccepted")
except BaseException as e:r.update(status="failed",error_type=type(e).__name__,error=str(e))
finally:(O/"terminal.json").write_text(json.dumps(r,indent=2))
sys.exit(r["rc"])
