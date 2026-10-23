#!/usr/bin/env python3
"""远端任务专用：相同 Pod 的即时退出、租约恢复与公共 SDK 双向接管。"""
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import sys
import time

os.umask(0o077)
N = pathlib.Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
Q = N / 'round-365f797-20261023.clPWh2h0'
D = Q / 'tap-checksum-fix'
O = D / 'native-rwfs-rejoin-force02'
O.mkdir(mode=0o700)
(O / 'cache').mkdir(mode=0o700)
B = ['python3', str(N / 'cluster/namespace-lab07.py'), 'run', '--task', str(N), '--']
sys.path.insert(0, str(Q / 'acceptance/scripts'))
from read_control_state import read_control_state

NEW = 'debbf268d1b1a8d4a07b9ac02be7084c3fa53c7cf794f0b1887ec65f7ace313b'
OLD_CRI = 'sha256:990c725857b24ff3d9000ab4f7f67a24d4103d5a9e07eadfcc82535d2b9d94ab'
NODES = {'akcr119-20261022-worker', 'akcr119-20261022-worker2'}
r = dict(rc=1, status='preflight', steps=[], attempts=[], coverage=[], runtime_override=True)


def run(name, command, timeout=180):
    with (O / (name + '.stdout')).open('x') as out, (O / (name + '.stderr')).open('x') as err:
        p = subprocess.run(command, stdout=out, stderr=err, timeout=timeout)
    r['steps'].append(dict(name=name, rc=p.returncode))
    (O / 'current.json').write_text(json.dumps(r, indent=2))
    if p.returncode:
        raise RuntimeError(name + ' failed; preserve sandbox, dependencies and first failure')
    return (O / (name + '.stdout')).read_text()


def records():
    return read_control_state(N)[1]


def ready(label):
    deadline = time.monotonic() + 300
    stable = 0
    while True:
        state = records()
        if any(k.startswith('environment:') for k in state):
            raise RuntimeError('Environment remains before a new independent attempt')
        good = all(state.get('node:' + node, {}).get('session', {}).get('routable') and state.get('node:' + node, {}).get('node', {}).get('available') and state.get('node:' + node, {}).get('scheduling_paused') is False and {'firecracker', 'runsc'}.issubset(state.get('node:' + node, {}).get('node', {}).get('runtime_classes', [])) and state.get('node:' + node, {}).get('node', {}).get('capacity', {}).get('cpu_millis', 0) >= 1000 and state.get('node:' + node, {}).get('node', {}).get('capacity', {}).get('memory_bytes', 0) >= 2 * (1 << 30) for node in NODES)
        stable = stable + 1 if good else 0
        if stable >= 3:
            break
        if time.monotonic() > deadline:
            raise TimeoutError('authority has not reported both nodes schedulable')
        time.sleep(2)
    pods = json.loads(run(label + '-pods-private', B + ['kubectl', '-n', 'akernel', 'get', 'pods', '-o', 'json']))['items']
    rows = [p for p in pods if p['metadata']['name'].startswith('akernel-node-') and not p['metadata'].get('deletionTimestamp')]
    if len(rows) != 2 or {p['spec']['nodeName'] for p in rows} != NODES:
        raise RuntimeError('Node Pod identity ambiguous')
    receipt = []
    for pod in rows:
        statuses = pod['status'].get('containerStatuses', [])
        if not statuses or not all(s.get('ready') and s.get('state', {}).get('running') and s.get('imageID', '').removeprefix('containerd://').endswith(OLD_CRI) for s in statuses):
            raise RuntimeError('base image or readiness differs')
        prefix = B + ['kubectl', '-n', 'akernel', 'exec', pod['metadata']['name'], '--']
        code = "import hashlib,pathlib,subprocess,json;v=subprocess.run(['systemctl','show','sandboxd','-p','MainPID','--value'],capture_output=True,text=True,check=True);pid=int(v.stdout);assert pid>0;sha=hashlib.sha256(pathlib.Path('/proc/'+str(pid)+'/exe').read_bytes()).hexdigest();assert sha==" + repr(NEW) + ";print(json.dumps({'pid':pid,'running_elf_sha256':sha}))"
        actual = json.loads(run(label + '-actual-' + pod['spec']['nodeName'], prefix + ['python3', '-c', code]))
        actual.update(node=pod['spec']['nodeName'], pod_uid=pod['metadata']['uid'], base_cri=OLD_CRI)
        receipt.append(actual)
    (O / (label + '-receipt.json')).write_text(json.dumps(receipt, indent=2))


try:
    for dep in ['native-rwfs-rejoin-complete04', 'native-rwfs-rejoin-image02']:
        terminal = D / dep / 'terminal.json'
        deadline = time.monotonic() + 900
        while not terminal.exists():
            if time.monotonic() > deadline:
                raise TimeoutError(dep + ' not finished; no SDK started')
            time.sleep(2)
        if json.loads(terminal.read_text()).get('rc') != 0:
            raise RuntimeError(dep + ' failed; no SDK started')
    covered = set()
    for attempt in range(1, 9):
        name = 'shared-native-rejoin-force02-' + str(attempt)
        ready('ready-' + str(attempt))
        job = N / 'acceptance/runs' / name
        shell = 'set -eu; source ' + shlex.quote(str(Q / 'acceptance/auth-shared-tapfix-direct01/sdk.env')) + '; export PYTHONPATH=' + shlex.quote(str(Q / 'acceptance/scripts') + ':' + str(Q / 'source/AKernel/sdk/python')) + '; export PR119_TEST_DISK_RWFS=1 PYTHONDONTWRITEBYTECODE=1 XDG_CACHE_HOME=' + shlex.quote(str(O / 'cache')) + '; exec ' + shlex.join([str(Q / 'sdk/client/bin/python'), str(D / 'sdk-native-forced-failover02.py'), '--task', str(N), '--runtime', 'firecracker', '--output', str(job)])
        r['status'] = 'running-' + name
        (O / 'current.json').write_text(json.dumps(r, indent=2))
        run(name, B + ['bash', '-c', shell], 1800)
        events = [json.loads(line) for line in (job / 'events.jsonl').read_text().splitlines()]
        required = {'public_sdk_failover_passed', 'source_healthy_again', 'target_survived_source_rejoin', 'sandbox_deleted', 'dead_owner_retirement_proved', 'disk_rwfs_verified'}
        if not required.issubset({v['event'] for v in events}) or any(v['event'] in ['acceptance_failed', 'source_health_check_failed'] for v in events):
            raise RuntimeError('forced SDK recovery evidence incomplete')
        success = [v for v in events if v['event'] == 'public_sdk_failover_passed']
        if len(success) != 1:
            raise RuntimeError('failover event ambiguous')
        event = success[0]
        direction = (event['source_node'], event['target_node'])
        if set(direction) != NODES or event.get('explicit_reload_called') or not event.get('source_offline') or event.get('memory_bytes') != 536870912:
            raise RuntimeError('cross-node full state contract differs')
        proof = json.loads((job / 'retirement-proof.json').read_text())
        if not proof.get('retired_by_product') or not proof.get('same_pod_uid') or proof.get('manual_pool_reset'):
            raise RuntimeError('same-Pod retirement proof missing')
        covered.add(direction)
        r['attempts'].append(dict(name=name, source=direction[0], target=direction[1], checkpoint_ms=event['checkpoint_until_http_completed_ms'], first_file_ms=event['read_trigger_until_first_verified_file_ms'], full_memory_ms=event['read_trigger_until_full_memory_verified_ms'], proof=proof))
        r['coverage'] = [list(v) for v in sorted(covered)]
        (O / 'current.json').write_text(json.dumps(r, indent=2))
        if len(covered) == 2:
            break
    if len(covered) != 2:
        raise RuntimeError('two directions not obtained after eight independent attempts')
    ready('ready-final')
    r.update(rc=0, status='same-pod-abrupt-exit-retirement-and-bidirectional-sdk-passed', candidate_sha256=NEW, full_official_sdk_not_run_here=True)
except BaseException as error:
    r.update(status='failed', error_type=type(error).__name__, error=str(error))
finally:
    (O / 'terminal.json').write_text(json.dumps(r, indent=2))
sys.exit(r['rc'])
