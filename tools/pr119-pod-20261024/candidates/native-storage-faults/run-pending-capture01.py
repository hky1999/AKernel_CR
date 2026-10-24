#!/usr/bin/env python3
"""存储故障整轮成功后，双向验收真实待加载输入期间请求再次保存。"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time

os.umask(0o077)
N = Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
Q = N / 'round-365f797-20261023.clPWh2h0'
D = Q / 'tap-checksum-fix'
I = Path(__file__).parent
O = D / 'native-pending-capture01'
O.mkdir(mode=0o700)
B = ['python3', str(N / 'cluster/namespace-lab07.py'), 'run', '--task', str(N), '--']
sys.path.insert(0, str(Q / 'acceptance/scripts'))
from read_control_state import read_control_state

r = {'rc': 1, 'status': 'preflight', 'cases': [], 'diagnostic_not_performance': True,
     'source_commit': '91dff2f686d4f3f18540d33c0851b127212d8567',
     'product_changed': False, 'internal_await_line_execution_proven': False}


def note(phase):
    r['status'] = phase
    (O / 'current.json').write_text(json.dumps(r, indent=2))


try:
    # This driver is launched only after the preceding storage job is terminal.
    if json.loads((D / 'native-storage-faults01/terminal.json').read_text()).get('rc') != 0:
        raise RuntimeError('native storage fault gates not passed; refuse capture probe')
    for name in ['sdk-pending-capture01.py', 'hold-reader-control01.py']:
        content = (I / name).read_bytes()
        compile(content, name, 'exec')
        (O / name).write_bytes(content)
        r.setdefault('source_sha256', {})[name] = hashlib.sha256(content).hexdigest()
    for node in ['akcr119-20261022-worker', 'akcr119-20261022-worker2']:
        if any(k.startswith('environment:') for k in read_control_state(N)[1]):
            raise RuntimeError('another Environment exists; no new experiment')
        st = os.statvfs(N)
        if st.f_bavail * st.f_frsize < 650 * (1 << 30):
            raise RuntimeError('650 GiB reserve insufficient')
        name = 'pending-input-' + node
        note(name + '-running')
        job = N / 'acceptance/runs' / ('shared-native-pending-capture01-' + node)
        shell = ('set -eu; source ' + str(Q / 'acceptance/auth-shared-tapfix-direct01/sdk.env') +
                 '; export PYTHONPATH=' + str(Q / 'acceptance/scripts') + ':' +
                 str(Q / 'source/AKernel/sdk/python') + '; export PYTHONDONTWRITEBYTECODE=1; exec ' +
                 str(Q / 'sdk/client/bin/python') + ' ' + str(O / 'sdk-pending-capture01.py') +
                 ' --role sandboxd --target-node ' + node + ' --output ' + str(job))
        with (O / (name + '.stdout')).open('x') as so, (O / (name + '.stderr')).open('x') as se:
            p = subprocess.run(B + ['bash', '-c', shell], stdout=so, stderr=se, timeout=1500)
        if p.returncode:
            raise RuntimeError(name + ' failed; preserve exact resources before rescue')
        v = json.loads((job / 'terminal.json').read_text())
        if v.get('rc') != 0 or not v.get('captured_snapshot_full_memory_and_root_readback_verified'):
            raise RuntimeError('pending capture full readback missing')
        r['cases'].append(v)
    content = (D / 'cgroup-leases-final-state01.py').read_text()
    old = "O=D/'cgroup-durable-leases-final-state01'"
    if content.count(old) != 1:
        raise RuntimeError('final-state binding ambiguous')
    content = content.replace(old, "O=D/'native-pending-capture01/final-state'")
    compile(content, 'final-state01.py', 'exec')
    script = O / 'final-state01.py'
    script.write_text(content)
    with (O / 'final-state.stdout').open('x') as so, (O / 'final-state.stderr').open('x') as se:
        p = subprocess.run(['python3', str(script)], stdout=so, stderr=se, timeout=300)
    final = json.loads((O / 'final-state/terminal.json').read_text())
    if p.returncode or final.get('rc') != 0:
        raise RuntimeError('final state failed')
    r.update(rc=0, status='bidirectional-sdk-capture-request-during-real-pending-input-passed', final_state=final)
except BaseException as exc:
    r.update(status='failed', error_type=type(exc).__name__, error=str(exc))
finally:
    (O / 'terminal.json').write_text(json.dumps(r, indent=2))
    print(json.dumps({k: r.get(k) for k in ['rc', 'status', 'error_type', 'error']}))
sys.exit(r['rc'])
