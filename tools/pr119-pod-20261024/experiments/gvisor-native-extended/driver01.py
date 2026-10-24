#!/usr/bin/env python3
"""Task-owned extended probes, no product code change or shared-service mutation."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time,signal
os.umask(0o077)
N=Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp');Q=N/'round-365f797-20261023.clPWh2h0';D=Q/'tap-checksum-fix';O=D/'gvisor-native-extended01'
B=['python3',str(N/'cluster/namespace-lab07.py'),'run','--task',str(N),'--']
sys.path.insert(0,str(Q/'acceptance/scripts'));from read_control_state import read_control_state
r={'rc':1,'status':'preflight','steps':[],'new_product_build':False}
def note(s,**kw):
 r.update(status=s,**kw);p=O/'current.tmp';p.write_text(json.dumps(r,indent=2));p.replace(O/'current.json')
def lab(args):
 p=subprocess.run(B+args,capture_output=True,text=True,timeout=90)
 if p.returncode:raise RuntimeError('owned preflight query failed rc='+str(p.returncode))
 return p.stdout
def guard():
 if os.statvfs(N).f_bavail*os.statvfs(N).f_frsize<650*(1<<30):raise RuntimeError('host reserve below 650 GiB')
 state=read_control_state(N)[1]
 if any(k.startswith('environment:')for k in state):raise RuntimeError('Environment remains; preserve resources')
 im=json.loads((D/'gvisor-native-consumer-image02/terminal.json').read_text());assert im['rc']==0
 pods=[p for p in json.loads(lab(['kubectl','-n','akernel','get','pods','-o','json']))['items']if not p['metadata'].get('deletionTimestamp')]
 assert len(pods)==5 and all(c.get('ready')and c['imageID'].rsplit('@',1)[-1]==im['expected_cri_digest']for p in pods for c in p['status']['containerStatuses'])
 for p in pods:
  if not p['metadata']['name'].startswith('akernel-node-'):continue
  v=state['node:'+p['spec']['nodeName']];assert v['session']['routable']and v['node']['available']and not v['scheduling_paused']
  raw=lab(['kubectl','-n','akernel','exec',p['metadata']['name'],'--','sha256sum','/usr/local/bin/sandboxd','/usr/local/bin/runsc','/usr/local/bin/gvisor-bin/gvisor_sentry'])
  expected={p:a['sha256']for p,a in [('/usr/local/bin/runsc',im['runtime_assets']['runsc']),('/usr/local/bin/gvisor-bin/gvisor_sentry',im['runtime_assets']['gvisor-bin/gvisor_sentry'])]};expected['/usr/local/bin/sandboxd']=im['sandboxd_sha256']
  assert {x.split()[1]:x.split()[0]for x in raw.splitlines()}==expected
 return im
try:
 assert json.loads((D/'gvisor-native-consumer-sdk01/terminal.json').read_text())['rc']==0
 im=guard()
 manifest=json.loads((O/'input-manifest.json').read_text())
 for name,sha in manifest['sources'].items():
  assert hashlib.sha256((O/name).read_bytes()).hexdigest()==sha
 note('two-restored-branches')
 job=N/'acceptance/runs/shared-gvisor-native-two-branches01'
 shell='set -eu; source '+str(Q/'acceptance/auth-shared-tapfix-direct01/sdk.env')+'; export PYTHONPATH='+str(Q/'acceptance/scripts')+':'+str(Q/'source/AKernel/sdk/python')+'; export PYTHONDONTWRITEBYTECODE=1; export XDG_CACHE_HOME='+str(O/'cache')+'; exec '+str(Q/'sdk/client/bin/python')+' '+str(O/'sdk-two-branches01.py')+' --runtime runsc --output '+str(job)
 with(O/'two-branches.stdout').open('xb')as so,(O/'two-branches.stderr').open('xb')as se:
  p=subprocess.Popen(B+['bash','-c',shell],stdin=subprocess.DEVNULL,stdout=so,stderr=se,start_new_session=True)
  identity={'pid':p.pid,'start_ticks':(Path('/proc')/str(p.pid)/'stat').read_text().rsplit(')',1)[1].split()[19]};(O/'client.json').write_text(json.dumps(identity))
  try:rc=p.wait(timeout=2400)
  except subprocess.TimeoutExpired:
   current=(Path('/proc')/str(p.pid)/'stat').read_text().rsplit(')',1)[1].split()
   if current[19]!=identity['start_ticks']:raise RuntimeError('SDK process identity changed; no signal')
   os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=30);raise RuntimeError('SDK timeout; resources retained, no next probe')
 r['steps'].append({'name':'two-branches','rc':rc})
 if rc:raise RuntimeError('dual-branch SDK probe failed; retain evidence and all dependencies')
 result=json.loads((job/'terminal.json').read_text());assert result['rc']==0 and result['two_restored_branches']and result['resources_deleted']
 guard();r.update(rc=0,status='native-dual-branch-multigeneration-passed',two_branches=result)
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
(O/'terminal.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:r.get(k)for k in['rc','status','error_type','error']}));sys.exit(r['rc'])
