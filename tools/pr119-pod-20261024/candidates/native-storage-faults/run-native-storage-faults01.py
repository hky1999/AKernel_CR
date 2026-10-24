#!/usr/bin/env python3
"""复用已验收探针，只测试本任务两个原生 JuiceFS 私有层；失败即停。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

os.umask(0o077)
N = Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
Q = N / 'round-365f797-20261023.clPWh2h0'
D = Q / 'tap-checksum-fix'
O = D / 'native-storage-faults01'
B = ['python3', str(N / 'cluster/namespace-lab07.py'), 'run', '--task', str(N), '--']
EXPECTED_ELF = '433574033952b1ad9106b125e085302b9c5268fea179609975de7d722c2f6c83'
EXPECTED_CRI = 'sha256:0bde46ba9cbbee107af01d085919c012c9d38094910d2a4761716de7f1c9dcb4'
O.mkdir(mode=0o700)
sys.path.insert(0, str(Q / 'acceptance/scripts'))
from read_control_state import read_control_state

r = {'rc': 1, 'status': 'preflight', 'steps': [], 'cases': [],
     'source_commit': '91dff2f686d4f3f18540d33c0851b127212d8567',
     'sandboxd_sha256': EXPECTED_ELF, 'cri_digest': EXPECTED_CRI,
     'diagnostic_not_performance': True, 'product_changed': False}


def note(phase):
    r['status'] = phase
    temporary = O / 'current.tmp'
    temporary.write_text(json.dumps(r, indent=2))
    temporary.replace(O / 'current.json')


def run(name, args, timeout=300):
    with (O / (name + '.stdout')).open('x') as so, (O / (name + '.stderr')).open('x') as se:
        p = subprocess.run(args, stdout=so, stderr=se, timeout=timeout)
    r['steps'].append({'name': name, 'rc': p.returncode})
    note(name)
    if p.returncode:
        raise RuntimeError(name + ' failed; keep resources and inspect before any retry')
    return (O / (name + '.stdout')).read_text()


def empty_and_ready():
    rows = read_control_state(N)[1]
    if any(k.startswith('environment:') for k in rows):
        raise RuntimeError('another Environment exists; refuse next fault')
    nodes = [v for k, v in rows.items() if k.startswith('node:')]
    if len(nodes) != 2 or any(not v.get('session', {}).get('routable') or
                             not v.get('node', {}).get('available') or
                             v.get('scheduling_paused') for v in nodes):
        raise RuntimeError('two real routable/available nodes required')
    st = os.statvfs(N)
    if st.f_bavail * st.f_frsize < 650 * (1 << 30):
        raise RuntimeError('650 GiB host reserve insufficient')


try:
    for previous in ['cgroup-durable-leases-sdk01', 'cgroup-durable-leases-postsdk01',
                     'cgroup-durable-leases-final-state01']:
        if json.loads((D / previous / 'terminal.json').read_text()).get('rc') != 0:
            raise RuntimeError('prior full SDK gates incomplete')
    image = json.loads((D / 'cgroup-durable-leases-image01/terminal.json').read_text())
    if image['sandboxd_sha256'] != EXPECTED_ELF or image['expected_cri_digest'] != EXPECTED_CRI:
        raise RuntimeError('tested artifact tuple changed')
    empty_and_ready()
    # Copy sources without edits; their existing PID/container/mount guards remain mandatory.
    names = ['sdk-mount-shadow01.py', 'shadow-owned-shared-mount01.py',
             'sdk-s3-pause01.py', 'pause-owned-rgw01.py']
    r['reused_probe_sources'] = {}
    for name in names:
        content = (D / 'storage' / name).read_bytes()
        compile(content, name, 'exec')
        (O / name).write_bytes(content)
        r['reused_probe_sources'][name] = hashlib.sha256(content).hexdigest()
    run('fresh-routable-schedulable', [sys.executable,
        str(D / 'cgroup-durable-leases-sdk01/wait-ready01.py'), '--expected-digest', EXPECTED_CRI,
        '--output', str(O / 'ready'), '--previous-session-hashes',
        str(D / 'cgroup-durable-leases-sdk01/previous-sessions.json'), '--timeout', '240'], 300)
    for fault, script in [('mount-shadow', 'sdk-mount-shadow01.py'), ('s3-pause', 'sdk-s3-pause01.py')]:
        for runtime in ['runsc', 'firecracker']:
            empty_and_ready()
            name = fault + '-' + runtime
            note(name + '-running')
            job = N / 'acceptance/runs' / ('shared-native-storage-faults01-' + name)
            shell = ('set -eu; source ' + str(Q / 'acceptance/auth-shared-tapfix-direct01/sdk.env') +
                     '; export PYTHONPATH=' + str(Q / 'acceptance/scripts') + ':' +
                     str(Q / 'source/AKernel/sdk/python') + '; export PYTHONDONTWRITEBYTECODE=1; exec ' +
                     str(Q / 'sdk/client/bin/python') + ' ' + str(O / script) + ' --runtime ' + runtime +
                     ' --output ' + str(job))
            run(name, B + ['bash', '-c', shell], 1500)
            result = json.loads((job / 'terminal.json').read_text())
            if result.get('rc') != 0 or not result.get('resources_deleted'):
                raise RuntimeError(name + ' did not complete resource retirement')
            r['cases'].append({'case': name, 'result': result})
            empty_and_ready()
    content = (D / 'cgroup-leases-final-state01.py').read_text()
    old = "O=D/'cgroup-durable-leases-final-state01'"
    if content.count(old) != 1:
        raise RuntimeError('final-state output binding not unique')
    content = content.replace(old, "O=D/'native-storage-faults01/final-state'")
    compile(content, 'final-state01.py', 'exec')
    (O / 'final-state01.py').write_text(content)
    run('final-state', ['python3', str(O / 'final-state01.py')], 300)
    final = json.loads((O / 'final-state/terminal.json').read_text())
    if final.get('rc') != 0:
        raise RuntimeError('final-state audit failed')
    r.update(rc=0, status='both-native-private-layouts-mount-and-s3-faults-passed', final_state=final)
except BaseException as exc:
    r.update(status='failed', error_type=type(exc).__name__, error=str(exc))
finally:
    (O / 'terminal.json').write_text(json.dumps(r, indent=2))
    print(json.dumps({k: r.get(k) for k in ['rc', 'status', 'error_type', 'error']}))
sys.exit(r['rc'])
