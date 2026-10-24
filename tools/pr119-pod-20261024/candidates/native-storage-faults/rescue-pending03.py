#!/usr/bin/env python3
"""退休已 Failed 的诊断实例，在另一客户端核验保留快照及后续保存。"""
from pathlib import Path
import json
import os
import time
from adx_environment import ConnectionConfig, Environment
from acceptance import same_state, completed
from read_control_state import read_control_state

os.umask(0o077)
N = Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
D = N / 'round-365f797-20261023.clPWh2h0/tap-checksum-fix'
P = N / 'acceptance/runs/shared-native-pending-capture01-akcr119-20261022-worker'
O = N / 'acceptance/runs/shared-native-pending-capture03-rescue'
O.mkdir(mode=0o700)
reader = None
r = {'rc': 1, 'product_changed': False, 'first_rescue_remains_failed': True, 'phase': 'preflight'}


def records():
    return read_control_state(N)[1]


def resources():
    (O / 'resources.private.json').write_text(json.dumps({'reader': None if reader is None else reader.id}))


def command(text):
    reply = reader.commands.run(text, timeout=300)
    if reply.exit_code:
        raise RuntimeError('SDK command failed rc=' + str(reply.exit_code))
    return reply.stdout


def memory():
    reply = json.loads(command('/tmp/pr119-reader-probe state'))
    assert reply['http_status'] == 200
    return json.loads(reply['body'])


try:
    assert json.loads((D / 'owned-juicefs-resize01/terminal.private.json').read_text())['rc'] == 0
    saved = json.loads((P / 'resources.private.json').read_text())
    assert not saved['source'] and not saved['captured_snapshot'] and saved['reader'] and saved['snapshot']
    rows = records()
    active = {k for k in rows if k.startswith('environment:')}
    if active not in [set(), {'environment:' + saved['reader']}]:
        raise RuntimeError('another Environment exists; no rescue mutation')
    if active and rows['environment:' + saved['reader']]['result']['state'] != 'Failed':
        raise RuntimeError('original failed record changed state; inspect first')
    r['failed_record_already_absent'] = not active
    r['phase'] = 'checking-retained-snapshot'
    conn = ConnectionConfig(server_address=os.environ['AKERNEL_SERVER_ADDRESS'], token=os.environ['AKERNEL_TOKEN'],
                            use_tls=True, gateway_address=os.environ.get('AKERNEL_GATEWAY_ADDRESS'), verify_tls=True)
    assert Environment.get_snapshot(saved['snapshot'], connection=conn).snapshot_id == saved['snapshot']
    if active:
        Environment.delete(saved['reader'], connection=conn)
    deadline = time.monotonic() + 120
    while any(k.startswith('environment:') for k in records()):
        if time.monotonic() > deadline:
            raise TimeoutError('exact failed record did not retire')
        time.sleep(1)
    r['failed_environment_retired_via_sdk'] = bool(active)
    r['phase'] = 'restoring-retained-snapshot'
    reader = Environment.create(saved['snapshot'], name='pr119-pending-input-rescue02',
                                node_id='akcr119-20261022-worker2', idle_timeout=900, connection=conn)
    resources()
    r['phase'] = 'verifying-root-and-memory'
    assert reader.files.read('/pr119-reader-root') == 'r' * (1 << 20)
    baseline = json.loads((P / 'source-before-snapshot.json').read_text())
    same_state(baseline, memory())
    r.update(original_snapshot_root_1MiB_verified=True, original_snapshot_full_1GiB_memory_verified=True)
    r['phase'] = 'later-checkpoint-reload'
    reader.files.write('/pr119-reader-root', 'recovered-after-client-memory-failure')
    completed(json.loads(command('/tmp/pr119-reader-probe checkpoint --socket /run/akernel/execd.sock --timeout 240')))
    reader.files.write('/pr119-reader-root', 'must-roll-back')
    command('/tmp/pr119-reader-probe mutate')
    assert reader.reload()
    assert reader.files.read('/pr119-reader-root') == 'recovered-after-client-memory-failure'
    same_state(baseline, memory())
    r['later_checkpoint_reload_verified'] = True
    r['phase'] = 'retiring-verified-resources'
    Environment.delete(reader.id, connection=conn)
    reader = None
    resources()
    Environment.delete_snapshot(saved['snapshot'], connection=conn)
    deadline = time.monotonic() + 180
    while True:
        missing = False
        try:
            Environment.get_snapshot(saved['snapshot'], connection=conn)
        except Exception as exc:
            if str(getattr(exc, 'code', '')).upper() != 'NOT_FOUND':
                raise
            missing = True
        if missing and not any(k.startswith('environment:') for k in records()):
            break
        if time.monotonic() > deadline:
            raise TimeoutError('exact diagnostic resources did not retire')
        time.sleep(1)
    r.update(rc=0, resources_retired_via_sdk=True)
except BaseException as exc:
    import traceback
    (O / 'traceback.private.log').write_text(traceback.format_exc())
    r.update(error_type=type(exc).__name__, error=str(exc))
finally:
    resources()
    (O / 'terminal.json').write_text(json.dumps(r, indent=2))
    print(json.dumps(r))
raise SystemExit(r['rc'])
