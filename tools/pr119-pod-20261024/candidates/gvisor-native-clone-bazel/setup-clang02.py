#!/usr/bin/env python3
from pathlib import Path
import json,subprocess,os,time,hashlib,shutil,sys
os.umask(0o077)
N=Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp');D=N/'round-365f797-20261023.clPWh2h0/tap-checksum-fix';O=D/'gvisor-clang-builder02'
PB=['/usr/bin/podman','--root',str(N/'image-build/graph'),'--runroot',str(N/'image-build/runroot'),'--tmpdir',str(N/'image-build/libpod-tmp'),'--cgroup-manager','cgroupfs']
TAG='localhost/akernel-pr119-gvisor-builder:clang02-20261024';LABEL='gvisor-clang-builder02'
r={'rc':1,'status':'preflight','host_software_modified':False,'steps':[]}
def run(name,args,timeout=180):
 with (O/(name+'.stdout')).open('xb')as so,(O/(name+'.stderr')).open('xb')as se:p=subprocess.run(args,stdout=so,stderr=se,timeout=timeout)
 r['steps'].append({'name':name,'rc':p.returncode})
 if p.returncode:raise RuntimeError(name+' failed; keep owned container and evidence')
 return (O/(name+'.stdout')).read_text()
def status(value):
 r['status']=value;(O/'current.json').write_text(json.dumps(r,indent=2))
def inspect(cid):
 v=json.loads(run('identity-'+str(len(r['steps'])),PB+['inspect',cid]))[0]
 assert v['Id']==cid and v['Config'].get('Labels',{}).get('akernel.qa')==LABEL
 return v
try:
 prior=json.loads((D/'gvisor-native-clone-bazel03/terminal.json').read_text());assert prior['old_order_semantic_failures_validated']==2 and prior['steps'][-1]=={'name':'related-tests','rc':1}
 assert not run('no-old-builds',PB+['ps','--all','--filter','label=akernel.qa=gvisor-native-clone-bazel03','--format','{{.ID}}']).strip()
 ready=json.loads((N/'cluster/lab07/ready.json').read_text());pid=ready['pid'];st=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split();assert st[19]==str(ready['start_ticks'])and os.readlink('/proc/'+str(pid)+'/ns/net')==ready['net']
 assert shutil.disk_usage(N).free>=650*(1<<30)
 builder=json.loads((D/'gvisor-clang-builder01/terminal.json').read_text());assert builder['rc']==0
 base=json.loads(run('base-image',PB+['image','inspect',builder['image_id']]))[0];assert base['Id']==builder['image_id'];r['base_image_id']=base['Id']
 cidfile=O/'container.cid';cmd=PB+['run','--pull=never','--cidfile',str(cidfile),'--name','akcr119-gvisor-clang-builder02','--label','akernel.qa='+LABEL,'--label','akernel.task='+N.name,'--network','ns:/proc/'+str(pid)+'/ns/net','--dns=none','--cgroupns','private','--cpus','2','--memory','3g','--pids-limit','1024','--cgroup-parent','/akernel-pr119-followup-20261022-qbGAw9tp','--volume',str(N/'cluster/lab07/resolv.conf')+':/etc/resolv.conf:ro','--volume',str(O/'setup.sh')+':/setup.sh:ro',base['Id'],'bash','/setup.sh']
 status('installing-only-into-owned-container')
 with (O/'install.stdout').open('xb')as so,(O/'install.stderr').open('xb')as se:
  p=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=so,stderr=se);started=time.monotonic()
  (O/'client.json').write_text(json.dumps({'pid':p.pid,'start_ticks':(Path('/proc')/str(p.pid)/'stat').read_text().rsplit(')',1)[1].split()[19]}))
  while p.poll()is None:
   if time.monotonic()-started>900 or shutil.disk_usage(N).free<650*(1<<30):
    if cidfile.exists():
     cid=cidfile.read_text().strip();inspect(cid);subprocess.run(PB+['stop','--time','10',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30,check=True)
    else:p.terminate()
    p.wait(timeout=60);raise RuntimeError('builder deadline/reserve guard; no image committed')
   time.sleep(3)
 r['steps'].append({'name':'install','rc':p.returncode})
 if p.returncode:raise RuntimeError('private package installation failed')
 cid=cidfile.read_text().strip();v=inspect(cid);assert not v['State']['Running']and v['State']['ExitCode']==0
 status('committing-private-build-image')
 run('commit',PB+['commit','--format','oci',cid,TAG],300)
 image=json.loads(run('new-image',PB+['image','inspect',TAG]))[0];r['image_id']=image['Id'];r['image_tag']=TAG
 meta=run('packages',PB+['run','--rm','--pull=never','--network','none','--cgroupns','private','--cpus','1','--memory','1g','--pids-limit','128','--cgroup-parent','/akernel-pr119-followup-20261022-qbGAw9tp',image['Id'],'cat','/usr/local/share/akernel-build/packages.txt'])
 r['packages']=meta.splitlines()
 inspect(cid);run('remove-owned-setup-container',PB+['rm',cid])
 r.update(rc=0,status='private-clang-bpf-builder-ready-no-host-install',available_host_bytes=shutil.disk_usage(N).free,setup_sha256=hashlib.sha256((O/'setup.sh').read_bytes()).hexdigest())
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
(O/'terminal.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:r.get(k)for k in ('rc','status','image_id','error_type','error')}));sys.exit(r['rc'])
