#!/usr/bin/env python3
"""仅在同一 fixture 的两个布局试跑成功后启动十组正式对照。"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time

os.umask(0o077)
N = Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
D = N / 'round-365f797-20261023.clPWh2h0/tap-checksum-fix'
B = ['python3', str(N / 'cluster/namespace-lab07.py'), 'run', '--task', str(N), '--']
PREFIX = D / 'fc-backend-compare-pairs01'
DRIVER = D / 'run-fc-backend-compare01.py'
FIXTURE = D / 'sdk-backend-compare01.py'
r = dict(rc=1, status='waiting-for-verified-live-smoke', formal_started=False)


def save():
    PREFIX.with_suffix('.chain-current.json').write_text(json.dumps(r, indent=2))


try:
    terminal = D / 'fc-backend-compare-smoke01/terminal.json'
    identity = json.loads((D / 'fc-backend-compare-smoke01.launch.json').read_text())
    deadline = time.monotonic() + 1800
    while not terminal.exists():
        stat = Path('/proc') / str(identity['pid']) / 'stat'
        if not stat.exists() or stat.read_text().rsplit(')', 1)[1].split()[19] != identity['start_ticks']:
            raise RuntimeError('smoke process disappeared without terminal; inspect, never restart blindly')
        r['verified_smoke_pid'] = identity['pid']
        save()
        if time.monotonic() > deadline:
            raise TimeoutError('live smoke exceeded observation budget; no formal workload started')
        time.sleep(3)
    result = json.loads(terminal.read_text())
    if result.get('rc') != 0 or len(result.get('cases', [])) != 2 or not result.get('smoke_only'):
        raise RuntimeError('both layouts did not pass; no formal workload started')
    if hashlib.sha256(FIXTURE.read_bytes()).hexdigest() != identity['fixture_sha256'] or hashlib.sha256(DRIVER.read_bytes()).hexdigest() != identity['script_sha256']:
        raise RuntimeError('executed script differs from smoke source')
    nodes = {
        'akcr119-20261022-control-plane': '309834713ae51c81b89d88111a2a0adaf345f9ec135d8d3938d20f4727023bfa',
        'akcr119-20261022-worker': 'c94000a9e103f344bd40e2fd1cce2bb4ee113766beadc63ae5e5f8c7b6a5b550',
        'akcr119-20261022-worker2': '31814694e9fd4463d194bb5150fc2dec052131af18d726ca330e822345c0f017',
    }
    for node, wanted in nodes.items():
        p = subprocess.run(B + ['podman', 'inspect', node], capture_output=True, text=True, timeout=60)
        if p.returncode:
            raise RuntimeError('owned Kind identity query failed')
        v = json.loads(p.stdout)[0]
        if v['Id'] != wanted or not v['State']['Running']:
            raise RuntimeError('owned Kind identity changed')
    if PREFIX.exists():
        raise RuntimeError('formal output already exists; reconcile original job')
    with PREFIX.with_suffix('.driver.log').open('x') as log:
        p = subprocess.Popen(['python3', str(DRIVER), '--output', str(PREFIX), '--pairs', '10', '--require-smoke', str(terminal)], stdout=log, stderr=subprocess.STDOUT)
        r.update(formal_started=True, status='formal-pairs-running', child_pid=p.pid, child_start_ticks=Path('/proc', str(p.pid), 'stat').read_text().rsplit(')', 1)[1].split()[19])
        save()
        code = p.wait()
    final = json.loads((PREFIX / 'terminal.json').read_text())
    if code or final.get('rc') != 0 or not final.get('performance_complete'):
        raise RuntimeError('formal pairs failed; retain resources and first failure')
    r.update(rc=0, status='ten-pairs-finished-final-native')
except BaseException as error:
    r.update(status='failed', error_type=type(error).__name__, error=str(error))
finally:
    PREFIX.with_suffix('.chain-terminal.json').write_text(json.dumps(r, indent=2))
sys.exit(r['rc'])
