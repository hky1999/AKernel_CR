#!/usr/bin/env python3
"""Validate and retire only the failed no-signal reader experiment's SDK resources."""
from pathlib import Path
import json,os,sys,time
from adx_environment import Environment,ConnectionConfig
from acceptance import same_state
from read_control_state import read_control_state
os.umask(0o077)
N=Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp');Q=N/'round-365f797-20261023.clPWh2h0';O=Q/'tap-checksum-fix/gvisor-native-held-reader02'
r={'rc':1,'fault_injected':False}
try:
 J=N/'acceptance/runs/shared-gvisor-native-held-reader01-sandboxd'
 old=json.loads((J/'terminal.json').read_text());barrier=json.loads((J/'barrier/terminal.json').read_text());saved=json.loads((J/'resources.private.json').read_text())
 assert old['rc']==1 and barrier['error']=='shared input FD already closed; no crash injected' and 'role_crash_unix_ns'not in barrier and 'reader_barrier_entered_unix_ns'not in barrier
 assert saved['source']is None and saved['reader']and saved['snapshot']
 identity=saved['reader'];assert [k for k in read_control_state(N)[1]if k.startswith('environment:')]==['environment:'+identity]
 fields=(Path('/proc')/str(barrier['reader']['pid'])/'stat').read_text().rsplit(')',1)[1].split();assert fields[19]==barrier['reader']['start_ticks']and fields[0]not in ['T','t','Z','X']
 conn=ConnectionConfig(server_address=os.environ['AKERNEL_SERVER_ADDRESS'],token=os.environ['AKERNEL_TOKEN'],use_tls=True,gateway_address=os.environ.get('AKERNEL_GATEWAY_ADDRESS'),verify_tls=True)
 reader=Environment.from_id(identity,connection=conn);v=reader.commands.run('/tmp/pr119-reader-probe state',timeout=180);assert v.exit_code==0
 response=json.loads(v.stdout);assert response['http_status']==200
 same_state(json.loads((J/'source-before-snapshot.json').read_text()),json.loads(response['body']))
 assert reader.files.read('/pr119-reader-root')=='r'*(1<<20)
 try:Environment.delete_snapshot(saved['snapshot'],connection=conn)
 except Exception as e:assert str(getattr(e,'code','')).upper()=='SNAPSHOT_IN_USE'and identity in(getattr(e,'sandbox_ids',None)or[])
 else:raise AssertionError('live reader snapshot was not protected')
 Environment.delete(identity,connection=conn);Environment.delete_snapshot(saved['snapshot'],connection=conn)
 deadline=time.monotonic()+180
 while True:
  missing=False
  try:Environment.get_snapshot(saved['snapshot'],connection=conn)
  except Exception as e:
   if str(getattr(e,'code','')).upper()=='NOT_FOUND':missing=True
   else:raise
  if missing and not any(k.startswith('environment:')for k in read_control_state(N)[1]):break
  if time.monotonic()>deadline:raise TimeoutError('SDK resources did not retire')
  time.sleep(1)
 r.update(rc=0,original_reader_not_stopped=True,memory_bytes=1073741824,full_state_verified=True,snapshot_busy_while_reader_alive=True,sdk_resources_deleted=True)
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
(O/'recovery-terminal.json').write_text(json.dumps(r,indent=2));print(json.dumps(r));sys.exit(r['rc'])
