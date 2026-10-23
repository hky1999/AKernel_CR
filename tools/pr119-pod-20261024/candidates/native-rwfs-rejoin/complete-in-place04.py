#!/usr/bin/env python3
"""仅在已救援的任务内更新空闲目标服务，保留两个 Pod 的身份。"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

os.umask(0o077)
N = pathlib.Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
Q = N / 'round-365f797-20261023.clPWh2h0'
D = Q / 'tap-checksum-fix'
O = D / 'native-rwfs-rejoin-complete04'
O.mkdir(mode=0o700)
B = ['python3', str(N / 'cluster/namespace-lab07.py'), 'run', '--task', str(N), '--']
sys.path.insert(0, str(Q / 'acceptance/scripts'))
from read_control_state import read_control_state

OLD = '124020747ef5155677bea1efb0ca35af4271641a8afd158e5b30a6268168baa4'
NEW = 'debbf268d1b1a8d4a07b9ac02be7084c3fa53c7cf794f0b1887ec65f7ace313b'
r = dict(rc=1, status='preflight', steps=[], target_service_stopped=False)


def run(name, argv, timeout=120):
    with (O / (name + '.stdout')).open('x') as out, (O / (name + '.stderr')).open('x') as err:
        p = subprocess.run(B + argv, stdout=out, stderr=err, timeout=timeout)
    r['steps'].append(dict(name=name, rc=p.returncode))
    (O / 'current.json').write_text(json.dumps(r, indent=2))
    if p.returncode:
        raise RuntimeError(name + ' failed; retain task dependencies')
    return (O / (name + '.stdout')).read_text()


def no_env():
    if any(k.startswith('environment:') for k in read_control_state(N)[1]):
        raise RuntimeError('current Environment exists; refuse target service update')


try:
    prior = json.loads((D / 'native-rwfs-rejoin-rescue03/terminal.json').read_text())
    if prior.get('rc') != 0 or prior['candidate_sha256'] != NEW:
        raise RuntimeError('source rescue not accepted')
    no_env()
    original = json.loads((D / 'native-rwfs-rejoin-rescue03/pod-identities.json').read_text())
    pods = json.loads(run('pods-before', ['kubectl', '-n', 'akernel', 'get', 'pods', '-o', 'json']))['items']
    actual = {p['spec']['nodeName']: dict(name=p['metadata']['name'], uid=p['metadata']['uid']) for p in pods if p['metadata']['name'].startswith('akernel-node-') and not p['metadata'].get('deletionTimestamp')}
    if original != actual:
        raise RuntimeError('Pod identities changed')
    for node, identity in actual.items():
        sha = run('elf-before-' + node, ['kubectl', '-n', 'akernel', 'exec', identity['name'], '--', 'sha256sum', '/usr/local/bin/sandboxd']).split()[0]
        if sha != (NEW if node == prior['source_node'] else OLD):
            raise RuntimeError('unexpected source/target runtime')
    target_node = next(n for n in actual if n != prior['source_node'])
    target_pod = actual[target_node]['name']
    candidate = '/home/akernel/.cr-native-rejoin-binaries/' + NEW + '/sandboxd'
    guard = '''import os,pathlib,json,hashlib
p=pathlib.Path(CANDIDATE)
assert p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==DIGEST
rows=[]
for d in pathlib.Path('/proc').iterdir():
 if not d.name.isdigit():continue
 try:exe=os.path.basename(os.readlink(d/'exe'))
 except OSError:continue
 if exe in ['firecracker','runsc-sandbox','runsc-gofer']:rows.append(exe)
assert not rows,rows
print(json.dumps({'runtime_processes':0,'candidate_sha256':DIGEST}))
'''.replace('CANDIDATE', repr(candidate)).replace('DIGEST', repr(NEW))
    run('target-runtime-guard', ['kubectl', '-n', 'akernel', 'exec', target_pod, '--', 'python3', '-c', guard])
    no_env()
    run('target-stop', ['kubectl', '-n', 'akernel', 'exec', target_pod, '--', 'systemctl', 'stop', 'sandboxd'])
    r['target_service_stopped'] = True
    install = '''import pathlib,hashlib,os,shutil
s=pathlib.Path(CANDIDATE);assert s.is_file()and not s.is_symlink()
assert hashlib.sha256(s.read_bytes()).hexdigest()==DIGEST
d=pathlib.Path('/usr/local/bin/sandboxd');t=d.with_name('.sandboxd-native-rejoin-'+str(os.getpid()))
with s.open('rb')as a,t.open('xb')as b:
 shutil.copyfileobj(a,b);b.flush();os.fchmod(b.fileno(),0o755);os.fsync(b.fileno())
os.replace(t,d);f=os.open(d.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(f);os.close(f)
'''.replace('CANDIDATE', repr(candidate)).replace('DIGEST', repr(NEW))
    run('target-install', ['kubectl', '-n', 'akernel', 'exec', target_pod, '--', 'python3', '-c', install])
    run('target-start', ['kubectl', '-n', 'akernel', 'exec', target_pod, '--', 'systemctl', 'start', 'sandboxd'])
    r['target_service_restarted'] = True
    r['status'] = 'waiting-both-nodes-actually-schedulable'
    (O / 'current.json').write_text(json.dumps(r, indent=2))
    stable = 0
    deadline = time.monotonic() + 300
    while True:
        records = read_control_state(N)[1]
        rows = {node: records.get('node:' + node, {}) for node in actual}
        good = all(v.get('session', {}).get('routable') and v.get('node', {}).get('available') and v.get('scheduling_paused') is False and {'firecracker', 'runsc'}.issubset(v.get('node', {}).get('runtime_classes', [])) and v.get('node', {}).get('capacity', {}).get('cpu_millis', 0) >= 1000 and v.get('node', {}).get('capacity', {}).get('memory_bytes', 0) >= 2 * (1 << 30) for v in rows.values())
        stable = stable + 1 if good else 0
        if stable >= 3:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError('both nodes not routable, available and schedulable')
        time.sleep(2)
    for node, identity in actual.items():
        sha = run('elf-after-' + node, ['kubectl', '-n', 'akernel', 'exec', identity['name'], '--', 'sha256sum', '/usr/local/bin/sandboxd']).split()[0]
        if sha != NEW:
            raise RuntimeError('candidate bytes differ after update')
    no_env()
    after = json.loads(run('pods-after', ['kubectl', '-n', 'akernel', 'get', 'pods', '-o', 'json']))['items']
    identity = {p['spec']['nodeName']: dict(name=p['metadata']['name'], uid=p['metadata']['uid']) for p in after if p['metadata']['name'].startswith('akernel-node-') and not p['metadata'].get('deletionTimestamp')}
    if identity != original:
        raise RuntimeError('Pod identity changed during update')
    r.update(rc=0, status='both-runtime-overrides-ready-for-forced-sdk', candidate_sha256=NEW, all_pod_uids_unchanged=True, manual_pool_reset=False, expected_image_unchanged=True, source_service_not_stopped=True)
except BaseException as error:
    r.update(status='failed', error_type=type(error).__name__, error=str(error))
finally:
    (O / 'terminal.json').write_text(json.dumps(r, indent=2))
sys.exit(r['rc'])
