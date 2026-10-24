#!/usr/bin/env python3
"""只删除 smoke01 在第一次保存之前由路径观测误判留下的沙箱。"""
from pathlib import Path
import json
import os
import time
from adx_environment import ConnectionConfig, Environment
from read_control_state import read_control_state

os.umask(0o077)
N = Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
J = N / 'acceptance/runs/gvisor-backend-smoke01-1-full-local-xfs'
O = N / 'acceptance/runs/gvisor-backend-smoke01-rescue'
O.mkdir(mode=0o700)
r = {'rc': 1, 'product_changed': False, 'phase': 'preflight'}
try:
    v = json.loads((J / 'terminal.json').read_text())
    assert v['rc'] == 1 and not v['rounds'] and not v['backing_media']
    assert v['guest_io']['readback_verified'] and v['guest_io']['bytes'] == 64 * (1 << 20)
    eid = v['preserved_source_id']
    rows = read_control_state(N)[1]
    active = {k for k in rows if k.startswith('environment:')}
    assert active in [set(), {'environment:' + eid}], 'another Environment exists'
    r['source_already_absent'] = not active
    r['phase'] = 'retiring-exact-owned-source'
    if active:
        conn = ConnectionConfig(server_address=os.environ['AKERNEL_SERVER_ADDRESS'], token=os.environ['AKERNEL_TOKEN'],
                                use_tls=True, gateway_address=os.environ.get('AKERNEL_GATEWAY_ADDRESS'), verify_tls=True)
        source = Environment.from_id(eid, connection=conn)
        reply = source.commands.run('sha256sum /pr119-perf-large', timeout=180)
        assert reply.exit_code == 0 and reply.stdout.split()[0] == v['guest_io']['file_sha256_after']
        r['original_64MiB_root_file_verified'] = True
        Environment.delete(eid, connection=conn)
    deadline = time.monotonic() + 180
    while any(k.startswith('environment:') for k in read_control_state(N)[1]):
        if time.monotonic() > deadline:
            raise TimeoutError('exact smoke01 source not retired')
        time.sleep(1)
    r.update(rc=0, resources_retired=True, no_checkpoint_request_had_been_issued=True)
except BaseException as exc:
    import traceback
    (O / 'traceback.private.log').write_text(traceback.format_exc())
    r.update(error_type=type(exc).__name__, error=str(exc))
(O / 'terminal.json').write_text(json.dumps(r, indent=2))
print(json.dumps(r))
raise SystemExit(r['rc'])
