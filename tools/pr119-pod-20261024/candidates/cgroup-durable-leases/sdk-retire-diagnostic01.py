#!/usr/bin/env python3
"""Recover the retained owned diagnostic Snapshot, verify every byte, then retire via SDK."""
from pathlib import Path
import json,os,sys,time,uuid,subprocess
from adx_environment import Environment,ConnectionConfig
from acceptance import same_state
from read_control_state import read_control_state
os.umask(0o077)
N=Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp');Q=N/'round-365f797-20261023.clPWh2h0';O=Q/'tap-checksum-fix/cgroup-durable-leases-postsdk01';J=N/'acceptance/runs/shared-cgroup-leases-diagnostic-retire01';J.mkdir(mode=0o700)
B=['python3',str(N/'cluster/namespace-lab07.py'),'run','--task',str(N),'--']
old=N/'acceptance/runs/shared-gvisor-native-held-reader02-sandboxd';saved=json.loads((old/'resources.private.json').read_text());snapshot=saved['snapshot'];reader=None
r={'rc':1,'runtime':'runsc','diagnostic_not_performance':True}
conn=ConnectionConfig(server_address=os.environ['AKERNEL_SERVER_ADDRESS'],token=os.environ['AKERNEL_TOKEN'],use_tls=True,gateway_address=os.environ.get('AKERNEL_GATEWAY_ADDRESS'),verify_tls=True)
def resources():(J/'resources.private.json').write_text(json.dumps({'reader':None if reader is None else reader.id,'snapshot':snapshot}))
try:
 assert not any(k.startswith('environment:')for k in read_control_state(N)[1])
 assert Environment.get_snapshot(snapshot,connection=conn).snapshot_id==snapshot
 reader=Environment.create(snapshot,name='pr119-diagnostic-retire-'+uuid.uuid4().hex[:10],node_id='akcr119-20261022-worker',connection=conn);resources()
 v=reader.commands.run('/tmp/pr119-reader-probe state',timeout=240);assert v.exit_code==0
 response=json.loads(v.stdout);assert response['http_status']==200
 same_state(json.loads((old/'source-before-snapshot.json').read_text()),json.loads(response['body']))
 assert reader.files.read('/pr119-reader-root')=='r'*(1<<20)
 reader.files.write('/pr119-reader-root','verified-with-fixed-cgroup-lifetime')
 assert reader.files.read('/pr119-reader-root')=='verified-with-fixed-cgroup-lifetime'
 identity=reader.id;Environment.delete(identity,connection=conn);reader=None;resources()
 deadline=time.monotonic()+180
 while any(k.startswith('environment:')for k in read_control_state(N)[1]):
  if time.monotonic()>deadline:raise TimeoutError('diagnostic reader did not retire')
  time.sleep(.5)
 Environment.delete_snapshot(snapshot,connection=conn)
 while True:
  try:Environment.get_snapshot(snapshot,connection=conn)
  except Exception as e:
   if str(getattr(e,'code','')).upper()=='NOT_FOUND':break
   raise
  if time.monotonic()>deadline:raise TimeoutError('diagnostic Snapshot did not retire')
  time.sleep(.5)
 r.update(rc=0,memory_bytes=1073741824,root_file_bytes=1048576,original_failure_snapshot_recovered_with_fixed_daemon=True,full_state_verified=True,target_private_write_verified=True,reader_deleted=True,diagnostic_snapshot_deleted_via_sdk=True)
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
resources();(J/'terminal.json').write_text(json.dumps(r,indent=2));print(json.dumps(r));sys.exit(r['rc'])
