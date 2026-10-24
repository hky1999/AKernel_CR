#!/usr/bin/env python3
"""Isolate the reader SIGSTOP/SIGCONT from the daemon crash. No product mutation."""
from pathlib import Path
import json,os,sys,subprocess,time,uuid,importlib.util
from adx_environment import Environment,ConnectionConfig
from acceptance import same_state
from read_control_state import read_control_state
os.umask(0o077)
N=Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp');Q=N/'round-365f797-20261023.clPWh2h0';D=Q/'tap-checksum-fix';O=D/'gvisor-native-reader-barrier-control01';J=N/'acceptance/runs/shared-gvisor-native-reader-barrier-control01';J.mkdir(mode=0o700)
B=['python3',str(N/'cluster/namespace-lab07.py'),'run','--task',str(N),'--']
oldJ=N/'acceptance/runs/shared-gvisor-native-held-reader02-sandboxd'
r={'rc':1,'diagnostic_not_performance':True,'role_crash_injected':False};reader=None;helper=None;snapshot=None
conn=ConnectionConfig(server_address=os.environ['AKERNEL_SERVER_ADDRESS'],token=os.environ['AKERNEL_TOKEN'],use_tls=True,gateway_address=os.environ.get('AKERNEL_GATEWAY_ADDRESS'),verify_tls=True)
def resources():(J/'resources.private.json').write_text(json.dumps({'reader':None if reader is None else reader.id,'snapshot':snapshot}))
def run(args):
 p=subprocess.run(B+args,capture_output=True,text=True,timeout=60);p.check_returncode();return p.stdout
try:
 assert json.loads((D/'gvisor-native-held-reader02/terminal.json').read_text())['rc']==1
 old=json.loads((oldJ/'terminal.json').read_text());br=json.loads((oldJ/'barrier/terminal.json').read_text());saved=json.loads((oldJ/'resources.private.json').read_text());req=json.loads((oldJ/'barrier-request.private.json').read_text())
 assert old['rc']==1 and old['error']=='role did not reconcile the existing reader'and br['rc']==0 and br['same_reader_resumed']
 assert not (Path('/proc')/str(br['reader']['pid'])).exists(),'old reader still exists; no deletion'
 st=read_control_state(N)[1];identity=saved['reader'];record=st['environment:'+identity]
 assert [k for k in st if k.startswith('environment:')]==['environment:'+identity]and record['result']['state']=='Failed'and not record['result']['resources_held']
 snapshot=saved['snapshot'];resources();assert Environment.get_snapshot(snapshot,connection=conn).snapshot_id==snapshot
 Environment.delete(identity,connection=conn)
 deadline=time.monotonic()+90
 while any(k.startswith('environment:')for k in read_control_state(N)[1]):
  if time.monotonic()>deadline:raise TimeoutError('failed reader metadata did not retire')
  time.sleep(.5)
 r['previous_failed_reader_deleted_after_death_proof']=True
 target=record['assignment']['node_id'];pods=json.loads(run(['kubectl','-n','akernel','get','pods','-o','json']))['items'];pod=next(v for v in pods if v['metadata']['name'].startswith('akernel-node-')and v['spec']['nodeName']==target)
 assert [v['containerID'].removeprefix('containerd://')for v in pod['status']['containerStatuses']]==[req['reader_container_id']]
 reader=Environment.create(snapshot,name='pr119-reader-control-'+uuid.uuid4().hex[:10],node_id=target,connection=conn);resources();req['environment_id']=reader.id
 request=J/'request.private.json';request.write_text(json.dumps(req))
 with(J/'helper.stdout').open('xb')as so,(J/'helper.stderr').open('xb')as se:helper=subprocess.Popen(['/usr/bin/python3',str(O/'hold-reader-control01.py'),'--request',str(request),'--out',str(J/'barrier')],stdin=subprocess.DEVNULL,stdout=so,stderr=se,start_new_session=True)
 if helper.wait(timeout=25):raise RuntimeError('control could not stop/resume a real input reader')
 barrier=json.loads((J/'barrier/terminal.json').read_text());assert barrier['rc']==0 and barrier['role_crash_injected']is False and barrier['same_role_preserved']and barrier['shared_input_fd_count_at_control']>0
 spec=importlib.util.spec_from_file_location('helper',O/'hold-reader-control01.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 deadline=time.monotonic()+60
 while True:
  try:
   result=reader.commands.run('/tmp/pr119-reader-probe state',timeout=15)
   if result.exit_code:raise RuntimeError('guest probe failed')
   response=json.loads(result.stdout);assert response['http_status']==200
   same_state(json.loads((oldJ/'source-before-snapshot.json').read_text()),json.loads(response['body']));break
  except Exception:
   if time.monotonic()>deadline:raise
   time.sleep(.5)
 current=mod.process(barrier['reader']['pid']);assert current['start_ticks']==barrier['reader']['start_ticks']
 assert reader.files.read('/pr119-reader-root')=='r'*(1<<20)
 Environment.delete(reader.id,connection=conn);reader=None;resources()
 r.update(rc=0,memory_bytes=1073741824,vm_memory_mb=2048,open_input_control_exercised=True,original_reader_preserved=True,full_state_verified=True,control_reader_deleted=True,ready_snapshot_retained_for_diagnosis=True)
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
finally:
 if helper is not None and helper.poll()is None:
  try:helper.wait(timeout=15)
  except Exception as e:r['helper_wait_error']=str(e)
 resources();(J/'terminal.json').write_text(json.dumps(r,indent=2));(O/'terminal.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
sys.exit(r['rc'])
