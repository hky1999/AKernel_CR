#!/usr/bin/env python3
"""只构建测试任务消费层；等待匹配完整运行时门，不部署。"""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,time
os.umask(0o077)
N=Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
D=N/'round-365f797-20261023.clPWh2h0/tap-checksum-fix'
O=D/'gvisor-native-consumer-qa01'
B=['python3',str(N/'cluster/namespace-lab07.py'),'run','--task',str(N),'--']
PB=['/usr/bin/podman','--root',str(N/'image-build/graph'),'--runroot',str(N/'image-build/runroot'),'--tmpdir',str(N/'image-build/libpod-tmp'),'--cgroup-manager','cgroupfs']
BASE='fdb145cf51f340dc46ebea3713c342b4ec93b127'
LABEL='gvisor-native-consumer-qa01'
r={'rc':1,'status':'preflight','steps':[],'deployed':False,'base_commit':BASE}
def note(status,**kw):
 r.update(status=status,**kw);p=O/'current.tmp';p.write_text(json.dumps(r,indent=2));p.replace(O/'current.json')
def run(name,args,timeout=300):
 with(O/(name+'.stdout')).open('xb')as so,(O/(name+'.stderr')).open('xb')as se:p=subprocess.run(args,stdout=so,stderr=se,timeout=timeout)
 r['steps'].append({'name':name,'rc':p.returncode})
 if p.returncode:raise RuntimeError(name+' failed; preserve original evidence')
 return(O/(name+'.stdout')).read_text()
def guard():
 if shutil.disk_usage(N).free<650*(1<<30):raise RuntimeError('host free reserve below 650 GiB')
def owned_stop(cidfile):
 if not cidfile.exists():raise RuntimeError('build CID unavailable; retain client identity, no unverified stop')
 cid=cidfile.read_text().strip();v=json.loads(run('stop-identity',PB+['inspect',cid]))[0]
 if v['Id']!=cid or v['Config']['Labels'].get('akernel.qa')!=LABEL or v['Config']['Labels'].get('akernel.task')!=N.name:raise RuntimeError('build identity mismatch; no signal sent')
 run('stop-owned-build',PB+['stop','--time','10',cid])
try:
 dependency=D/'gvisor-native-clone-bazel04';identity=json.loads((dependency/'launch.json').read_text())
 note('waiting-for-complete-gvisor-component-gates')
 deadline=time.monotonic()+7200
 while not(dependency/'terminal.json').exists():
  guard();p=Path('/proc')/str(identity['pid'])/'stat'
  if not p.exists():raise RuntimeError('runtime driver gone without terminal')
  stat=p.read_text().rsplit(')',1)[1].split()
  if stat[19]!=identity['start_ticks']or stat[0]=='Z':raise RuntimeError('runtime driver changed identity')
  if time.monotonic()>deadline:raise TimeoutError('runtime gate dependency not complete')
  time.sleep(5)
 runtime=json.loads((dependency/'terminal.json').read_text())
 if runtime['rc']!=0:raise RuntimeError('runtime component gates failed; do not build/deploy consumer')
 r['runtime_bundle_sha256']=runtime['bundle_sha256']
 if run('no-runtime-build-container',PB+['ps','--all','--filter','label=akernel.qa=gvisor-native-clone-bazel04','--format','{{.ID}}']).strip():raise RuntimeError('runtime build container still present')
 sys.path.insert(0,str(N/'round-365f797-20261023.clPWh2h0/acceptance/scripts'));from read_control_state import read_control_state
 if any(k.startswith('environment:')for k in read_control_state(N)[1]):raise RuntimeError('active Environment; no build')
 guard();note('fetching-exact-consumer-base')
 source=O/'source'
 run('git-clone',B+['git','-c','credential.helper=','clone','--depth=1','--branch','codex/pr119-native-rwfs-rejoin-20261024','https://github.com/hky1999/sandboxd.git',str(source)],600)
 if run('git-base',B+['git','-C',str(source),'rev-parse','HEAD']).strip()!=BASE:raise RuntimeError('consumer base moved')
 manifest=json.loads((O/'input-manifest.json').read_text())
 for name,sha in manifest['sources'].items():
  data=(O/'inputs'/name).read_bytes()
  if hashlib.sha256(data).hexdigest()!=sha:raise RuntimeError('consumer input digest mismatch')
  target=source/name;target.relative_to(source)
  if target.is_symlink():raise RuntimeError('consumer target is a symlink')
  target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
 note('source-gates-running')
 cid=O/'container.cid'
 cmd=PB+['run','--rm','--pull=never','--cidfile',str(cid),'--name','akcr119-gvisor-native-consumer-qa01','--label','akernel.qa='+LABEL,'--label','akernel.task='+N.name,'--privileged','--cgroupns','private','--network','none','--cpus','2','--memory','6g','--pids-limit','1024','--cgroup-parent','/akernel-pr119-followup-20261022-qbGAw9tp','--volume',str(source)+':/src:rw','--volume',str(O/'out')+':/out:rw','--volume',str(O/'qa.sh')+':/qa.sh:ro','--volume',str(D/'modcache')+':/gomodcache:rw','--volume',str(D/'gocache')+':/gocache:rw','docker.io/library/golang:1.25.5-bookworm','bash','/qa.sh']
 with(O/'qa.stdout').open('xb')as so,(O/'qa.stderr').open('xb')as se:
  p=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=so,stderr=se);start=time.monotonic()
  (O/'client.json').write_text(json.dumps({'pid':p.pid,'start_ticks':(Path('/proc')/str(p.pid)/'stat').read_text().rsplit(')',1)[1].split()[19]}))
  try:
   while p.poll()is None:
    guard()
    if time.monotonic()-start>3600:raise TimeoutError('consumer quality deadline')
    note('source-gates-running',elapsed_seconds=round(time.monotonic()-start),host_available_bytes=shutil.disk_usage(N).free);time.sleep(3)
  except BaseException:
   owned_stop(cid);p.wait(timeout=60);raise
 r['steps'].append({'name':'quality','rc':p.returncode})
 if p.returncode:raise RuntimeError('consumer gates failed; no deployment')
 run('final-source-status',B+['git','-C',str(source),'status','--porcelain'])
 r.update(rc=0,status='consumer-source-gates-passed-not-sdk',sandboxd_sha256=hashlib.sha256((O/'out/sandboxd').read_bytes()).hexdigest(),source_files={n:hashlib.sha256((source/n).read_bytes()).hexdigest()for n in manifest['sources']},host_available_bytes=shutil.disk_usage(N).free)
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
(O/'terminal.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:r.get(k)for k in('rc','status','error_type','error')}));sys.exit(r['rc'])
