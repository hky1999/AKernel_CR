#!/usr/bin/env python3
"""Verify and delete the single SDK sandbox preserved by the pre-injection probe failure."""
from pathlib import Path
import ast,json,os,subprocess,sys,time
from adx_environment import Environment,ConnectionConfig
from read_control_state import read_control_state
os.umask(0o077)
N=Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp');Q=N/'round-365f797-20261023.clPWh2h0';D=Q/'tap-checksum-fix';O=D/'gvisor-native-role-restart02'
B=['python3',str(N/'cluster/namespace-lab07.py'),'run','--task',str(N),'--']
r={'rc':1,'fault_injected':False}
try:
 J=N/'acceptance/runs/shared-gvisor-native-role-restart01-sandboxd';old=json.loads((J/'terminal.json').read_text())
 assert old['rc']==1 and old['error']=='expected one owned live runtime' and not (J/'sandboxd-before-crash.private.json').exists()
 identity=old['sandbox_preserved'];state=read_control_state(N)[1]
 assert [k for k in state if k.startswith('environment:')]==['environment:'+identity]
 tree=ast.parse((O/'sdk-role-restart02.py').read_text());probe=next(n.value.value for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='VM_PROBE'for t in n.targets))
 p=subprocess.run(B+['kubectl','-n','akernel','get','pods','-o','json'],capture_output=True,text=True,timeout=60);p.check_returncode()
 node=state['environment:'+identity]['assignment']['node_id'];pod=next(x['metadata']['name']for x in json.loads(p.stdout)['items']if x['metadata']['name'].startswith('akernel-node-')and x['spec']['nodeName']==node)
 p=subprocess.run(B+['kubectl','-n','akernel','exec',pod,'--','python3','-c',probe],capture_output=True,text=True,timeout=60);p.check_returncode();rows=json.loads(p.stdout)
 assert len(rows)==1 and rows[0]['executable']=='runsc-sandbox' and any(d['kind']=='private_anonymous_filestore'for d in rows[0]['shared_file_dependencies'])
 (O/'recovered-runtime.private.json').write_text(json.dumps(rows,indent=2))
 conn=ConnectionConfig(server_address=os.environ['AKERNEL_SERVER_ADDRESS'],token=os.environ['AKERNEL_TOKEN'],use_tls=True,gateway_address=os.environ.get('AKERNEL_GATEWAY_ADDRESS'),verify_tls=True)
 env=Environment.from_id(identity,connection=conn)
 assert env.files.read('/pr119-restart-root-state')=='uncheckpointed-live-sandboxd'
 v=env.commands.run('/tmp/pr119-restart-probe state',timeout=180);assert v.exit_code==0
 response=json.loads(v.stdout);assert response['http_status']==200
 mem=json.loads(response['body']);assert mem['memory_bytes']==536870912
 (O/'recovered-memory.private.json').write_text(json.dumps(mem,indent=2))
 Environment.delete(identity,connection=conn)
 deadline=time.monotonic()+180
 while any(k.startswith('environment:')for k in read_control_state(N)[1]):
  if time.monotonic()>deadline:raise TimeoutError('SDK resource did not retire')
  time.sleep(1)
 r.update(rc=0,pre_injection_failure_verified=True,main_runtime_count=1,live_uncheckpointed_root_verified=True,memory_bytes=mem['memory_bytes'],sdk_resource_deleted=True)
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
(O/'recovery-terminal.json').write_text(json.dumps(r,indent=2));print(json.dumps(r));sys.exit(r['rc'])
