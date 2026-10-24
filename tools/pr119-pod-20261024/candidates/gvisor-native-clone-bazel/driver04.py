#!/usr/bin/env python3
"""独立组件旧红/新绿与完整bundle；从不部署，原始日志只保存在任务目录。"""
from pathlib import Path
import hashlib,json,os,re,subprocess,sys,tarfile,time,shutil
os.umask(0o077)
N=Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp');Q=N/'round-365f797-20261023.clPWh2h0';D=Q/'tap-checksum-fix';O=D/'gvisor-native-clone-bazel04'
B=['python3',str(N/'cluster/namespace-lab07.py'),'run','--task',str(N),'--']
CACHE=D/'gvisor-native-clone-bazel01/cache'
PB=['/usr/bin/podman','--root',str(N/'image-build/graph'),'--runroot',str(N/'image-build/runroot'),'--tmpdir',str(N/'image-build/libpod-tmp'),'--cgroup-manager','cgroupfs']
BASE='87e8441b6db18219fbb941378cfcb2883750b07c'
BAZEL_SHA='17247e8a84245f59d3bc633d0cfe0a840992a7760a11af1a30012d03da31604c'
TAG='refs/tags/release-20260817.0-akernel.5'
SOURCE='pkg/sentry/pgalloc/save_restore.go'
TARGET='//pkg/sentry/pgalloc:pgalloc_test'
r=dict(rc=1,status='preflight',base=BASE,scope='component regression/related gates/complete amd64 bundle; not SDK or deployment',steps=[],deployed_product_unchanged=True)

def note(status,**values):
 r.update(status=status,**values);(O/'current.json').write_text(json.dumps(r,indent=2))

def run(name,args,timeout=300):
 with (O/(name+'.stdout')).open('xb')as so,(O/(name+'.stderr')).open('xb')as se:p=subprocess.run(args,stdout=so,stderr=se,timeout=timeout)
 r['steps'].append(dict(name=name,rc=p.returncode))
 if p.returncode:raise RuntimeError(name+' failed; preserve original logs')
 return (O/(name+'.stdout')).read_text()

def free_guard():
 if shutil.disk_usage(N).free<650*(1<<30):raise RuntimeError('host reserve below 650 GiB; stop only owned build')

def network_pid():
 v=json.loads((N/'cluster/lab07/ready.json').read_text());pid=v['pid'];st=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
 if st[19]!=str(v['start_ticks'])or os.readlink('/proc/'+str(pid)+'/ns/net')!=v['net']:raise RuntimeError('private namespace keeper changed')
 return pid

def stop_own(cidfile,process,name):
 deadline=time.monotonic()+30
 while not cidfile.exists()and process.poll()is None and time.monotonic()<deadline:time.sleep(1)
 if cidfile.exists():cid=cidfile.read_text().strip()
 else:
  if process.poll()is None:
   process.terminate();process.wait(timeout=30)
  p=subprocess.run(PB+['ps','--all','--no-trunc','--filter','label=akernel.qa=gvisor-native-clone-bazel04','--filter','label=akernel.step='+name,'--format','{{.ID}}'],capture_output=True,text=True,timeout=30)
  if p.returncode:raise RuntimeError('cannot reconcile owned build container; preserve client record')
  ids=p.stdout.split()
  if not ids:return
  if len(ids)!=1:raise RuntimeError('ambiguous owned build identity; no container signal sent')
  cid=ids[0]
 p=subprocess.run(PB+['inspect',cid],capture_output=True,text=True,timeout=30)
 if p.returncode:return
 v=json.loads(p.stdout)[0]
 if v['Id']!=cid or any(v['Config'].get('Labels',{}).get(k)!=value for k,value in {'akernel.qa':'gvisor-native-clone-bazel04','akernel.step':name,'akernel.task':N.name}.items()):raise RuntimeError('build container identity not owned; no signal sent')
 subprocess.run(PB+['stop','--time','10',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30,check=True)


def container(name,args,expected_red=False,deadline=3600,memory='8g',cpus='4'):
 free_guard();pid=network_pid();cid=O/'cids'/(name+'.cid')
 command=PB+['run','--rm','--pull=never','--cidfile',str(cid),'--name','akcr119-gvisor-native-bazel04-'+name,'--label','akernel.qa=gvisor-native-clone-bazel04','--label','akernel.task='+N.name,'--label','akernel.step='+name,'--network','ns:/proc/'+str(pid)+'/ns/net','--dns=none','--cgroupns','private','--cpus',cpus,'--memory',memory,'--pids-limit','4096','--cgroup-parent','/akernel-pr119-followup-20261022-qbGAw9tp','--volume',str(N/'cluster/lab07/resolv.conf')+':/etc/resolv.conf:ro','--volume',str(O/'source')+':/src:rw','--volume',str(O/'inputs')+':/inputs:ro','--volume',str(CACHE)+':/cache:rw','--volume',str(O/'out')+':/out:rw','--volume',str(O/'tools')+':/tools:ro','--volume',str(O/'entry.sh')+':/entry.sh:ro',IMAGE,*args]
 note(name)
 with (O/(name+'.stdout')).open('xb')as so,(O/(name+'.stderr')).open('xb')as se:
  p=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=so,stderr=se)
  started=time.monotonic();last=0
  (O/(name+'.client.json')).write_text(json.dumps({'pid':p.pid,'start_ticks':(Path('/proc')/str(p.pid)/'stat').read_text().rsplit(')',1)[1].split()[19],'cid_file':str(cid)}))
  try:
   while p.poll()is None:
    free_guard()
    if time.monotonic()-started>deadline:raise TimeoutError('owned build exceeded step deadline')
    if time.monotonic()-last>30:
     note(name,elapsed_seconds=round(time.monotonic()-started),host_available_bytes=shutil.disk_usage(N).free);last=time.monotonic()
    time.sleep(3)
  except BaseException:
   stop_own(cid,p,name)
   p.wait(timeout=60)
   raise
 code=p.returncode;r['steps'].append(dict(name=name,rc=code));note(name+'-finished')
 if expected_red:
  text=(O/(name+'.stdout')).read_text(errors='replace')+(O/(name+'.stderr')).read_text(errors='replace')
  markers=[r'snapshot finished before background input was released: .*err=<nil>',r'SnapshotToFd ignored failed async restore: got <nil>, want EIO']
  if code==0 or not all(re.search(m,text)for m in markers):raise RuntimeError('old run did not reproduce both intended semantic failures; do not apply fix')
  r['old_order_semantic_failures_validated']=2
 elif code:raise RuntimeError(name+' failed; no deployment or silent skip')

try:
 old=D/'gvisor-native-clone-bazel01'
 prev=D/'gvisor-native-clone-bazel03'
 prior=json.loads((prev/'terminal.json').read_text());assert prior['rc']==1 and prior['old_order_semantic_failures_validated']==2
 assert prior['steps'][-1]=={'name':'related-tests','rc':1}
 assert 'aarch64-linux-gnu-gcc'in(prev/'related-tests.stderr').read_text() and 'No such file or directory'in(prev/'related-tests.stderr').read_text()
 identity=json.loads((prev/'launch.json').read_text());p=Path('/proc')/str(identity['pid'])/'stat'
 if p.exists()and p.read_text().rsplit(')',1)[1].split()[19]==identity['start_ticks']:raise RuntimeError('previous driver still live; no overlap')
 check=subprocess.run(PB+['ps','--all','--filter','label=akernel.qa=gvisor-native-clone-bazel03','--format','{{.ID}}'],capture_output=True,text=True,timeout=30)
 if check.returncode or check.stdout.strip():raise RuntimeError('previous build container remains')
 builder=D/'gvisor-clang-builder02';identity=json.loads((builder/'launch.json').read_text());deadline=time.monotonic()+1800
 note('waiting-for-owned-clang-builder')
 while not(builder/'terminal.json').exists():
  p=Path('/proc')/str(identity['pid'])/'stat'
  if not p.exists():raise RuntimeError('builder gone without terminal; no QA started')
  stat=p.read_text().rsplit(')',1)[1].split()
  if stat[19]!=identity['start_ticks']or stat[0]=='Z':raise RuntimeError('builder identity changed without terminal')
  if time.monotonic()>deadline:raise TimeoutError('builder observation deadline; no QA started')
  time.sleep(5)
 build=json.loads((builder/'terminal.json').read_text())
 if build['rc']!=0:raise RuntimeError('private builder failed; no QA started')
 IMAGE=build['image_id'];assert re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}',IMAGE)
 r['build_image_id']=IMAGE;r['build_packages']=build['packages']
 assert CACHE.is_dir()
 assert json.loads((D/'fc-backend-compare-pairs01/terminal.json').read_text())['rc']==0
 assert json.loads((D/'gvisor-native-clone-helper01/terminal.json').read_text())['rc']==0
 sys.path.insert(0,str(Q/'acceptance/scripts'));from read_control_state import read_control_state
 if any(k.startswith('environment:')for k in read_control_state(N)[1]):raise RuntimeError('another Environment exists; do not start build')
 free_guard();network_pid()
 note('fetching-exact-base-and-bazel')
 source=O/'source';source.mkdir(mode=0o700)
 run('git-init',B+['git','-C',str(source),'init'])
 run('git-origin',B+['git','-C',str(source),'remote','add','origin','https://github.com/akernel-dev/gvisor.git'])
 run('git-fetch',B+['git','-C',str(source),'-c','credential.helper=','fetch','--depth=1','origin',TAG+':'+TAG],600)
 run('git-checkout',B+['git','-C',str(source),'checkout','--detach',TAG+'^{}'])
 if run('git-base',B+['git','-C',str(source),'rev-parse','HEAD']).strip()!=BASE:raise RuntimeError('tag source moved; abort')
 if run('git-clean',B+['git','-C',str(source),'status','--porcelain']).strip():raise RuntimeError('base checkout not clean')
 manifest=json.loads((O/'input-manifest.json').read_text())
 for name,sha in manifest['sources'].items():
  p=O/'inputs/source'/name
  if hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise RuntimeError('candidate input hash changed')
  dest=source/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
 # Download only into the task; no installation or system package change.
 fetch="from pathlib import Path;import urllib.request,hashlib,json;u='https://github.com/bazelbuild/bazel/releases/download/8.3.1/bazel-8.3.1-linux-x86_64';d=urllib.request.urlopen(u,timeout=90).read();assert len(d)==64028260 and hashlib.sha256(d).hexdigest()==SHA;p=Path(DEST);p.write_bytes(d);p.chmod(0o700);print(json.dumps({'bytes':len(d),'sha256':hashlib.sha256(d).hexdigest()}))".replace('SHA',repr(BAZEL_SHA)).replace('DEST',repr(str(O/'tools/bazel')))
 prior_bazel=old/'tools/bazel'
 if hashlib.sha256(prior_bazel.read_bytes()).hexdigest()!=BAZEL_SHA:raise RuntimeError('old Bazel binary identity changed')
 shutil.copyfile(prior_bazel,O/'tools/bazel');(O/'tools/bazel').chmod(0o700)
 r['bazel_verified_reused']=True
 format_cmd='cd /src\ngofmt -w '+ ' '.join(n for n in manifest['sources']if n.endswith('.go'))+'\ngofmt -w /out/fixed-save_restore.go\n'
 # Fixed variant remains out of the source until both old failures are real.
 (O/'out/fixed-save_restore.go').write_bytes((O/'inputs/fixed-save_restore.go').read_bytes())
 container('format',['bash','-euc',format_cmd],deadline=180,memory='2g',cpus='2')
 # Reuse the exact previous regression sources and outcomes; do not repeat passed gates.
 prior_manifest=json.loads((prev/'input-manifest.json').read_text())
 for name,sha in manifest['sources'].items():
  if hashlib.sha256((prev/'source'/name).read_bytes()).hexdigest()!=sha:raise RuntimeError('previous fixed/formatted source differs; regression reuse invalid')
  if hashlib.sha256((source/name).read_bytes()).hexdigest()!=sha:raise RuntimeError('format unexpectedly changed the verified source')
 assert prior['old_order_semantic_failures_validated']==2
 assert {'name':'fixed-order','rc':0} in prior['steps']
 assert prior['fixed_order_source_sha256']==manifest['sources'][SOURCE]
 r['regression_reused_from']=str(prev/'terminal.json')
 r['old_order_semantic_failures_validated']=2
 r['old_order_source_sha256']=prior['old_order_source_sha256']
 r['fixed_order_source_sha256']=prior['fixed_order_source_sha256']
 r['fixed_order_three_rounds_reused']=True
 targets=['//pkg/sentry/checkpoint:clone_filestore_test',TARGET,'//runsc/container:filestore_snapshot_test','//runsc/boot/filter/config:config_test']
 container('related-tests',['bash','/entry.sh','related-tests',*targets])
 container('related-race',['bash','/entry.sh','related-race','--config=race',*targets])
 container('release',['bash','/entry.sh','release'],deadline=5400)
 run('final-source-status',B+['git','-C',str(source),'status','--porcelain'])
 run('final-source-diff',B+['git','-C',str(source),'diff','--stat'])
 archive=O/'out/gvisor-native-clone-amd64.tar.bz2'
 with tarfile.open(archive,'r:bz2')as t:
  files=[m for m in t.getmembers()if m.isfile()]
  expected={'runsc','containerd-shim-runsc-v1','gvisor-bin/gvisor_sentry','gvisor-bin/checkpointgofer','gvisor-bin/runsc-metric-server','gvisor-bin/gvisor-sentry-prewarmer'}
  normalized={m.name.removeprefix('./'):m for m in files}
  if set(normalized)!=expected:raise RuntimeError('complete bundle layout mismatch')
  assets={}
  for name,m in normalized.items():
   data=t.extractfile(m).read()
   if data[:6]!=b'\x7fELF\x02\x01'or int.from_bytes(data[18:20],'little')!=62:raise RuntimeError('bundle contains non-amd64 ELF')
   assets[name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
 r.update(rc=0,status='verified-regression-reused-related-tests-race-and-complete-amd64-bundle-passed-not-sdk',bundle_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),bundle_bytes=archive.stat().st_size,assets=assets,formatted_sources={n:hashlib.sha256((source/n).read_bytes()).hexdigest()for n in manifest['sources']},host_available_bytes=shutil.disk_usage(N).free)
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
(O/'terminal.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:r.get(k)for k in ('rc','status','error_type','error')}));sys.exit(r['rc'])
