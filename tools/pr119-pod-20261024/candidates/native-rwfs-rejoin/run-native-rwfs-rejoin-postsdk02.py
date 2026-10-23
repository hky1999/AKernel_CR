import pathlib,json,subprocess,os,sys,time,hashlib
os.umask(0o077)
N=pathlib.Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp');Q=N/'round-365f797-20261023.clPWh2h0';D=Q/'tap-checksum-fix';O=D/'native-rwfs-rejoin-postsdk02';O.mkdir(mode=0o700);(O/'cache').mkdir(mode=0o700)
B=['python3',str(N/'cluster/namespace-lab07.py'),'run','--task',str(N),'--']
r=dict(rc=1,status='waiting-full-sdk',steps=[])
try:
 deadline=time.monotonic()+7200
 while not (D/'native-rwfs-rejoin-sdk02/terminal.json').exists():
  (O/'current.json').write_text(json.dumps(r,indent=2))
  if time.monotonic()>deadline:raise TimeoutError('SDK dependency did not complete; no new action')
  time.sleep(3)
 accepted=json.loads((D/'native-rwfs-rejoin-sdk02/terminal.json').read_text())
 if accepted.get('rc')!=0 or not accepted.get('full_sdk_accepted'):raise RuntimeError('SDK dependency failed; retain evidence, no new action')
 sys.path.insert(0,str(Q/'acceptance/scripts'));from read_control_state import read_control_state
 def no_env():
  if any(k.startswith('environment:')for k in read_control_state(N)[1]):raise RuntimeError('another Environment exists')
 def run(name,args,timeout):
  r['status']=name;(O/'current.json').write_text(json.dumps(r,indent=2))
  with (O/(name+'.stdout')).open('x')as so,(O/(name+'.stderr')).open('x')as se:p=subprocess.run(args,stdout=so,stderr=se,timeout=timeout)
  r['steps'].append(dict(name=name,rc=p.returncode))
  if p.returncode:raise RuntimeError(name+' failed; inspect retained resources before further mutation')
 no_env()
 run('ongoing-guest-io',['python3',str(D/'run-native-rwfs-rejoin-directio02.py')],3900)
 no_env()
 outcomes={}
 for runtime in ['firecracker','runsc']:
  job=N/('acceptance/runs/shared-native-rejoin-sandboxd-restart02-'+runtime)
  shell='set -eu; source "'+str(Q/'acceptance/auth-shared-tapfix-direct01/sdk.env')+'"; export PYTHONPATH="'+str(Q/'acceptance/scripts')+'"; export PYTHONDONTWRITEBYTECODE=1; export XDG_CACHE_HOME="'+str(O/'cache')+'"; exec "'+str(Q/'sdk/client/bin/python')+'" "'+str(D/'sdk-writable-restart01.py')+'" --runtime '+runtime+' --restart sandboxd --output "'+str(job)+'"'
  run('sandboxd-restart-'+runtime,B+['bash','-c',shell],1800)
  outcome=json.loads((job/'terminal.json').read_text())
  if outcome.get('rc')!=0:raise RuntimeError('restart terminal not accepted')
  outcomes[runtime]=outcome
 no_env();r.update(rc=0,status='continuous-io-and-sandboxd-restart-passed',restart=outcomes,direct_io=json.loads((D/'native-rwfs-rejoin-directio02/terminal.json').read_text()))
except BaseException as e:r.update(status='failed',error_type=type(e).__name__,error=str(e))
finally:(O/'terminal.json').write_text(json.dumps(r,indent=2))
sys.exit(r['rc'])
