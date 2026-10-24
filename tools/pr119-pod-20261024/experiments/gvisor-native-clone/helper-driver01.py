#!/usr/bin/env python3
"""等正式测量成功终态后，仅独立验证候选克隆函数；不部署运行时。"""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
os.umask(0o077)
N=Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
Q=N/'round-365f797-20261023.clPWh2h0';D=Q/'tap-checksum-fix';O=D/'gvisor-native-clone-helper01'
B=['python3',str(N/'cluster/namespace-lab07.py'),'run','--task',str(N),'--']
PB=['/usr/bin/podman','--root',str(N/'image-build/graph'),'--runroot',str(N/'image-build/runroot'),'--tmpdir',str(N/'image-build/libpod-tmp'),'--cgroup-manager','cgroupfs']
root='/mnt/akernel-shared/akernel/gvisor-native-clone-helper-qbGAw9tp01'
nonce='gvisor-native-clone-helper-qbGAw9tp01'
r=dict(rc=1,status='waiting-for-terminal-no-build',product_baseline='87e8441b6db18219fbb941378cfcb2883750b07c',deployed_product_unchanged=True,steps=[])

def note(status):
 r['status']=status;(O/'current.json').write_text(json.dumps(r,indent=2))

def command(name,argv,timeout=180,**kw):
 with (O/(name+'.stdout')).open('xb')as so,(O/(name+'.stderr')).open('xb')as se:
  p=subprocess.run(argv,stdout=so,stderr=se,timeout=timeout,**kw)
 r['steps'].append(dict(name=name,rc=p.returncode))
 if p.returncode:raise RuntimeError(name+' failed; preserve private files and logs')
 return (O/(name+'.stdout')).read_text()

def no_env():
 sys.path.insert(0,str(Q/'acceptance/scripts'))
 from read_control_state import read_control_state
 if any(k.startswith('environment:')for k in read_control_state(N)[1]):raise RuntimeError('Environment exists; do not compile while another acceptance may be active')

try:
 deadline=time.monotonic()+7200
 terminal=D/'fc-backend-compare-pairs01/terminal.json'
 while not terminal.exists():
  if time.monotonic()>deadline:raise TimeoutError('dependency observation deadline; no build')
  p=Path('/proc/2568103/stat')
  if not p.exists():raise RuntimeError('formal process gone without terminal; no build')
  st=p.read_text().rsplit(')',1)[1].split()
  if st[19]!='214593417'or st[0]=='Z':raise RuntimeError('formal process identity changed; no build')
  time.sleep(10)
 formal=json.loads(terminal.read_text())
 if formal['rc']!=0 or len(formal['cases'])!=20 or formal['final_profile']!='native-juicefs':raise RuntimeError('formal measurement not fully passed; no build')
 r['formal_source_terminal_sha256']=hashlib.sha256(terminal.read_bytes()).hexdigest()
 no_env()
 ready=json.loads((N/'cluster/lab07/ready.json').read_text());pid=ready['pid']
 stat=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
 if stat[19]!=str(ready['start_ticks'])or os.readlink('/proc/'+str(pid)+'/ns/net')!=ready['net']:raise RuntimeError('private network keeper identity changed')
 if os.statvfs(N).f_bavail*os.statvfs(N).f_frsize<650*(1<<30):raise RuntimeError('host reserve below 650 GiB')
 note('remote-helper-building')
 cmd=PB+['run','--rm','--pull=never','--name','akcr119-gvisor-native-clone-helper01','--network','ns:/proc/'+str(pid)+'/ns/net','--dns=none','--cgroupns','private','--cpus','2','--memory','2g','--pids-limit','512','--cgroup-parent','/akernel-pr119-followup-20261022-qbGAw9tp','--volume',str(N/'cluster/lab07/resolv.conf')+':/etc/resolv.conf:ro','--volume',str(O/'source')+':/source:rw','--volume',str(O/'helper')+':/helper:rw','--volume',str(O/'out')+':/out:rw','--volume',str(O/'modcache')+':/modcache:rw','--volume',str(D/'gocache')+':/gocache:rw','--volume',str(O/'qa.sh')+':/qa.sh:ro','docker.io/library/golang:1.25.5-bookworm','bash','/qa.sh']
 command('isolated-helper-qa',cmd,900)
 binary=(O/'out/clone-filestore.test').read_bytes();digest=hashlib.sha256(binary).hexdigest()
 r['helper_elf_sha256']=digest
 r['formatted_sources']={str(p.relative_to(O/'source')):hashlib.sha256(p.read_bytes()).hexdigest()for p in(O/'source').rglob('*')if p.is_file()}
 pods=json.loads(command('pods-private',B+['kubectl','-n','akernel','get','pods','-l','app.kubernetes.io/component=node','-o','json']))['items']
 # Some historical chart labels differ; only the fixed two Node names are accepted.
 if len(pods)!=2:
  pods=json.loads(command('all-pods-private',B+['kubectl','-n','akernel','get','pods','-o','json']))['items'];pods=[p for p in pods if p['metadata']['name'].startswith('akernel-node-')and not p['metadata'].get('deletionTimestamp')]
 if len(pods)!=2:raise RuntimeError('expected exactly two owned Node Pods')
 node_results=[]
 for i,p in enumerate(sorted(pods,key=lambda p:p['spec']['nodeName'])):
  note('real-juicefs-helper-node-'+str(i))
  prefix=B+['kubectl','-n','akernel','exec',p['metadata']['name'],'--']
  prep="from pathlib import Path;import os,json;root=Path(ROOT);shared=Path('/mnt/akernel-shared');local=Path('/home/akernel/filestore');root.mkdir(mode=0o700,exist_ok=True);assert root.is_dir()and not root.is_symlink()and root.stat().st_dev==shared.stat().st_dev!=local.stat().st_dev;marker=root/'.owner';\nif not marker.exists():\n with marker.open('x')as f:f.write(NONCE)\nassert marker.read_text()==NONCE;print(json.dumps({'juicefs_root':True,'owner_verified':True}))".replace('ROOT',repr(root)).replace('NONCE',repr(nonce))
  command('prepare-'+str(i),prefix+['python3','-c',prep])
  dest='/tmp/'+nonce+'.test'
  install="import sys,os,hashlib;p=DEST;data=sys.stdin.buffer.read();assert hashlib.sha256(data).hexdigest()==SHA;f=open(p,'xb');f.write(data);f.close();os.chmod(p,0o700)".replace('DEST',repr(dest)).replace('SHA',repr(digest))
  command('install-'+str(i),B+['kubectl','-n','akernel','exec','-i',p['metadata']['name'],'--','python3','-c',install],120,input=binary)
  command('juicefs-helper-'+str(i),prefix+['env','TMPDIR='+root,dest,'-test.v','-test.count=3'],300)
  cleanup="from pathlib import Path;import hashlib;p=Path(DEST);assert hashlib.sha256(p.read_bytes()).hexdigest()==SHA;p.unlink()".replace('DEST',repr(dest)).replace('SHA',repr(digest))
  command('remove-helper-'+str(i),prefix+['python3','-c',cleanup])
  node_results.append(dict(execution_node=chr(65+i),helper_tests_rc=0,iterations=3))
 # Both clients have finished using the shared task directory.
 prefix=B+['kubectl','-n','akernel','exec',pods[0]['metadata']['name'],'--']
 clean="from pathlib import Path;r=Path(ROOT);m=r/'.owner';assert m.read_text()==NONCE;assert sorted(p.name for p in r.iterdir())==['.owner'];m.unlink();r.rmdir();print('task helper directory removed')".replace('ROOT',repr(root)).replace('NONCE',repr(nonce))
 command('remove-shared-test-root',prefix+['python3','-c',clean])
 no_env()
 r.update(rc=0,status='standalone-helper-and-two-real-juicefs-clients-passed-not-runsc-sdk',nodes=node_results,scope='actual candidate CloneFilestore; Go 1.25.5 and exact x/sys v0.43.0; not full Bazel or sentry/seccomp/SDK qualification',test_resources_removed=True)
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
(O/'terminal.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:r.get(k)for k in('rc','status','error_type')}));sys.exit(r['rc'])
