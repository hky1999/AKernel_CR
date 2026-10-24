#!/usr/bin/env python3
"""只核验并退休 pending01 在请求前失败所留下的实例与快照。"""
from pathlib import Path
import json
import os
import time
from adx_environment import ConnectionConfig, Environment
from acceptance import same_state
from read_control_state import read_control_state

os.umask(0o077)
N = Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
P = N / 'acceptance/runs/shared-native-pending-capture01-akcr119-20261022-worker'
O = N / 'acceptance/runs/shared-native-pending-capture01-rescue'
O.mkdir(mode=0o700)
r = {'rc': 1, 'product_changed': False}
try:
    failure = json.loads((P / 'terminal.json').read_text())
    barrier = json.loads((P / 'barrier/terminal.json').read_text())
    saved = json.loads((P / 'resources.private.json').read_text())
    assert failure['error'] == 'reader barrier ended before capture request'
    assert barrier['error_type'] == 'InterruptedError' and not barrier.get('reader_barrier_entered_unix_ns')
    assert not saved['source'] and not saved['captured_snapshot'] and saved['reader'] and saved['snapshot']
    assert {k for k in read_control_state(N)[1] if k.startswith('environment:')} == {'environment:' + saved['reader']}
    pid = barrier['reader']['pid']
    stat = Path('/proc/' + str(pid) + '/stat').read_text().rsplit(')', 1)[1].split()
    assert stat[19] == barrier['reader']['start_ticks'] and stat[0] not in ['T', 't', 'Z', 'X']
    assert 'akernel-pr119-followup-20261022-qbGAw9tp' in Path('/proc/' + str(pid) + '/cgroup').read_text()
    conn = ConnectionConfig(server_address=os.environ['AKERNEL_SERVER_ADDRESS'], token=os.environ['AKERNEL_TOKEN'],
                            use_tls=True, gateway_address=os.environ.get('AKERNEL_GATEWAY_ADDRESS'), verify_tls=True)
    reader = Environment.from_id(saved['reader'], connection=conn)
    reply = reader.commands.run('/tmp/pr119-reader-probe state', timeout=240)
    assert reply.exit_code == 0
    state = json.loads(reply.stdout)
    assert state['http_status'] == 200
    same_state(json.loads((P / 'source-before-snapshot.json').read_text()), json.loads(state['body']))
    assert reader.files.read('/pr119-reader-root') == 'r' * (1 << 20)
    Environment.delete(reader.id, connection=conn)
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
        if missing and not any(k.startswith('environment:') for k in read_control_state(N)[1]):
            break
        if time.monotonic() > deadline:
            raise TimeoutError('exact failed-probe resources did not retire')
        time.sleep(1)
    r.update(rc=0, full_1GiB_memory_verified=True, root_1MiB_verified=True,
             no_fault_signal_or_capture_request_had_been_sent=True, resources_retired_via_sdk=True)
except BaseException as exc:
    r.update(error_type=type(exc).__name__, error=str(exc))
(O / 'terminal.json').write_text(json.dumps(r, indent=2))
print(json.dumps(r))
raise SystemExit(r['rc'])
