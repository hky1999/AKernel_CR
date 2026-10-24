from pathlib import Path
import sys,json,subprocess,os,hashlib
os.umask(0o077)
N=Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp');Q=N/'round-365f797-20261023.clPWh2h0';D=Q/'tap-checksum-fix';O=D/'fc-backend-final-state01';O.mkdir(mode=0o700)
B=['python3',str(N/'cluster/namespace-lab07.py'),'run','--task',str(N),'--']
sys.path.insert(0,str(Q/'acceptance/scripts'));from read_control_state import read_control_state
r={'rc':1,'read_only':True,'nodes':[]}
def lab(args):
 p=subprocess.run(B+args,capture_output=True,text=True,timeout=90)
 if p.returncode:raise RuntimeError('private observation failed rc='+str(p.returncode))
 return p.stdout
try:
 assert json.loads((D/'fc-backend-compare-pairs01/terminal.json').read_text())['rc']==0
 assert json.loads((D/'gvisor-native-clone-helper01/terminal.json').read_text())['rc']==0
 rows=read_control_state(N)[1]
 assert not any(k.startswith('environment:')for k in rows)
 r['environment_count']=0
 pods=[p for p in json.loads(lab(['kubectl','-n','akernel','get','pods','-o','json']))['items']if not p['metadata'].get('deletionTimestamp')]
 assert len(pods)==5
 assert all(s.get('ready')and s.get('imageID','').rsplit('@',1)[-1]=='sha256:53669406ddc4f00905dca9eaef2d619a5b0a85046e1d0a5f0511153ef38708e5'for p in pods for s in p['status'].get('containerStatuses',[]))
 r['business_pods_current_image']=5
 assert lab(['kubectl','get','--raw','/readyz']).strip()=='ok'
 r['kubernetes_api_ready']=True
 for p in sorted(pods,key=lambda p:p['spec']['nodeName']):
  if not p['metadata']['name'].startswith('akernel-node-'):continue
  v=rows['node:'+p['spec']['nodeName']]
  assert v['session']['routable']and v['node']['available']and v['scheduling_paused']is False
  value=json.loads(lab(['kubectl','-n','akernel','exec',p['metadata']['name'],'--','python3','-c',"from pathlib import Path\nimport json,os,hashlib,subprocess,tomllib\npid=int(subprocess.check_output(['systemctl','show','sandboxd','-p','MainPID','--value'],text=True))\nassert pid>0\nsha=hashlib.sha256((Path('/proc')/str(pid)/'exe').read_bytes()).hexdigest()\nassert sha=='debbf268d1b1a8d4a07b9ac02be7084c3fa53c7cf794f0b1887ec65f7ace313b'\nactive=[];zombies=[]\nexpected={'firecracker','gvisor_sentry','runsc','runsc-sandbox','runsc-gofer','checkpointgofer','runsc-fd-parking'}\nfor p in Path('/proc').iterdir():\n if not p.name.isdigit():continue\n try:\n  state=(p/'stat').read_text().rsplit(')',1)[1].split()[0]\n  exe=Path(os.readlink(p/'exe').removesuffix(' (deleted)')).name\n  args=(p/'cmdline').read_bytes().split(b'\\0')\n  arg0=Path(os.fsdecode(args[0])).name if args[0]else''\n  if exe in expected or arg0 in expected:\n   (zombies if state=='Z'else active).append(exe)\n except OSError:continue\nassert not active,active\ncfg=tomllib.loads(Path('/home/akernel/sandboxd/config.toml').read_text())\nfc=cfg['plugin']['runtime']['firecracker']\nassert fc['writable_storage_dir']=='/mnt/akernel-shared/akernel/fc-rwfs-native-qbGAw9tp01' and fc['writable_storage_filesystem']=='fuse.juicefs'\nfilesystems={}\nfor k,path in [('private_filestore','/home/akernel/filestore'),('shared','/mnt/akernel-shared')]:\n filesystems[k]=subprocess.check_output(['findmnt','-n','-T',path,'-o','FSTYPE'],text=True).strip()\nassert filesystems=={'private_filestore':'xfs','shared':'fuse.juicefs'}\nroot=Path(fc['writable_storage_dir'])\ndirs=[p for p in root.iterdir()if p.is_dir()]\nassert not Path('/mnt/akernel-shared/akernel/gvisor-native-clone-helper-qbGAw9tp01').exists()\nassert not Path('/tmp/gvisor-native-clone-helper-qbGAw9tp01.test').exists()\nprint(json.dumps({'running_elf_sha256':sha,'runtime_process_count':len(active),'runtime_zombie_count':len(zombies),'filesystems':filesystems,'final_fc_backend':'native-juicefs','retained_rwfs_directories':len(dirs),'retained_directory_hashes':sorted(hashlib.sha256(p.name.encode()).hexdigest()for p in dirs),'helper_resources_removed':True}))\n"]))
  value.update(execution_node=chr(65+len(r['nodes'])),routable=True,available=True)
  r['nodes'].append(value)
 assert len(r['nodes'])==2
 st=os.statvfs(N);r['available_host_bytes']=st.f_bavail*st.f_frsize
 assert r['available_host_bytes']>=650*(1<<30)
 r.update(rc=0,status='final-native-and-two-ready-nodes-no-environments-or-runtime-processes-old-orphan-retained')
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
(O/'terminal.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
