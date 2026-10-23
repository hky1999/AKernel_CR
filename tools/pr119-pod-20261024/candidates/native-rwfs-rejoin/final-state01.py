from pathlib import Path
import json,subprocess,sys,os,hashlib
N=Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp');Q=N/'round-365f797-20261023.clPWh2h0';D=Q/'tap-checksum-fix';O=D/'native-rwfs-rejoin-final-state01';O.mkdir(mode=0o700)
B=['python3',str(N/'cluster/namespace-lab07.py'),'run','--task',str(N),'--']
sys.path.insert(0,str(Q/'acceptance/scripts'));from read_control_state import read_control_state
def run(argv):
 p=subprocess.run(B+argv,capture_output=True,text=True,timeout=60)
 if p.returncode:raise RuntimeError('owned final read failed: '+str(p.returncode))
 return p.stdout
r={'rc':1,'read_only':True}
try:
 for name in ['native-rwfs-rejoin-sdk02','native-rwfs-rejoin-postsdk02','native-rwfs-rejoin-force02']:
  assert json.loads((D/name/'terminal.json').read_text())['rc']==0
 rows=read_control_state(N)[1];assert not any(k.startswith('environment:')for k in rows)
 r['environment_count']=0
 pods=json.loads(run(['kubectl','-n','akernel','get','pods','-o','json']))['items']
 pods=[p for p in pods if not p['metadata'].get('deletionTimestamp')]
 expected='sha256:53669406ddc4f00905dca9eaef2d619a5b0a85046e1d0a5f0511153ef38708e5'
 assert len(pods)==5
 assert all(s.get('ready')and s.get('imageID','').rsplit('@',1)[-1]==expected for p in pods for s in p['status'].get('containerStatuses',[]))
 r['business_pods_current_image']=5
 r['nodes']=[]
 code="""import pathlib,subprocess,hashlib,os,json
p=subprocess.run(['systemctl','show','sandboxd','-p','MainPID','--value'],capture_output=True,text=True,check=True);pid=int(p.stdout);assert pid>0
sha=hashlib.sha256(pathlib.Path('/proc/'+str(pid)+'/exe').read_bytes()).hexdigest();assert sha=='debbf268d1b1a8d4a07b9ac02be7084c3fa53c7cf794f0b1887ec65f7ace313b'
active=[]
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  args=(p/'cmdline').read_bytes().split(b'\\0');exe=os.path.basename(os.fsdecode(args[0]))
  if exe in ['firecracker','runsc-sandbox','runsc-gofer']:active.append(exe)
 except OSError:continue
assert not active,active
filesystems={}
for name,path in [('private_filestore','/home/akernel/filestore'),('shared','/mnt/akernel-shared'),('native_rwfs','/mnt/akernel-shared/akernel/fc-rwfs-native-qbGAw9tp01')]:
 p=subprocess.run(['findmnt','-n','-T',path,'-o','FSTYPE'],capture_output=True,text=True,check=True);filesystems[name]=p.stdout.strip()
assert filesystems=={'private_filestore':'xfs','shared':'fuse.juicefs','native_rwfs':'fuse.juicefs'}
root=pathlib.Path('/mnt/akernel-shared/akernel/fc-rwfs-native-qbGAw9tp01')
dirs=[p for p in root.iterdir()if p.is_dir()]
print(json.dumps({'running_elf_sha256':sha,'runtime_processes':0,'filesystems':filesystems,'retained_rwfs_directories':len(dirs),'retained_directory_hashes':sorted(hashlib.sha256(p.name.encode()).hexdigest()for p in dirs)}))
"""
 for p in pods:
  if not p['metadata']['name'].startswith('akernel-node-'):continue
  node=p['spec']['nodeName'];v=rows['node:'+node];assert v['session']['routable']and v['node']['available']and v['scheduling_paused']is False
  data=json.loads(run(['kubectl','-n','akernel','exec',p['metadata']['name'],'--','python3','-c',code]));data.update(node=node,routable=True,available=True);r['nodes'].append(data)
 rescue=json.loads((D/'native-rwfs-rejoin-rescue03/terminal.json').read_text());cm=json.loads(run(['kubectl','-n','akernel','get','configmap',rescue['bootstrap_configmap'],'-o','json']))
 assert cm['metadata']['uid']==rescue['bootstrap_uid']
 script=cm['data'][rescue['bootstrap_key']]
 assert hashlib.sha256(script.encode()).hexdigest()==rescue['original_script_sha256']
 r['temporary_bootstrap_override_present']=False
 st=os.statvfs(N);r['available_host_bytes']=st.f_bavail*st.f_frsize
 r.update(rc=0,status='no-active-environments-or-runtime-processes; retained-old-rwfs-explicit')
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
(O/'terminal.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
