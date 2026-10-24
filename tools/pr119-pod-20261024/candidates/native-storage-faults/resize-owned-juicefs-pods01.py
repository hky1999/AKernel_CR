#!/usr/bin/env python3
"""仅通过 resize 子资源增加两端任务客户端内存，不滚动挂载。"""
from pathlib import Path
import json
import os
import subprocess
import time

os.umask(0o077)
N = Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
D = N / 'round-365f797-20261023.clPWh2h0/tap-checksum-fix'
O = D / 'owned-juicefs-resize01'
O.mkdir(mode=0o700)
B = ['python3', str(N / 'cluster/namespace-lab07.py'), 'run', '--task', str(N), '--']
PINS = [('akcr119-juicefs-client-hzn8q', '3e167e78-da76-4bd0-855d-35932aa3e0db'),
        ('akcr119-juicefs-client-l9ftq', '82df1110-abc1-431d-ab96-eeb13acb3c2e')]
DS_UID = 'd3a5f42c-5951-40ee-870e-278bd04cccc8'
IMAGE = 'docker.io/juicedata/mount:ce-v1.4.1@sha256:ab99388a397fe52575fdeb84a9e017c3c594a6b07d63966cd4805bbf6f172673'
r = {'rc': 1, 'before': [], 'after': [], 'steps': [], 'product_changed': False,
     'cache_configuration_changed': False, 'template_changed': False,
     'task_40GiB_limit_unchanged': True, 'sandbox_limits_unchanged': True}


def run(name, args):
    p = subprocess.run(B + args, capture_output=True, text=True, timeout=60)
    (O / (name + '.stdout')).write_text(p.stdout)
    (O / (name + '.stderr')).write_text(p.stderr)
    r['steps'].append({'name': name, 'rc': p.returncode})
    if p.returncode:
        raise RuntimeError(name + ' failed; no fallback to unbounded cgroups or forced rollout')
    return p.stdout


def get(name):
    return json.loads(run('get-' + name + '-' + str(time.monotonic_ns()),
                         ['kubectl', '-n', 'akernel-pr119-storage', 'get', 'pod', name, '-o', 'json']))


try:
    outer = Path('/sys/fs/cgroup/akernel-pr119-followup-20261022-qbGAw9tp')
    assert (outer / 'memory.max').read_text().strip() == str(40 * (1 << 30))
    assert int((outer / 'memory.current').read_text()) < 36 * (1 << 30)
    prepared = []
    for name, uid in PINS:
        pod = get(name)
        assert pod['metadata']['uid'] == uid
        owners = pod['metadata']['ownerReferences']
        assert len(owners) == 1 and owners[0]['uid'] == DS_UID
        assert len(pod['spec']['containers']) == 1
        c = pod['spec']['containers'][0]
        assert c['name'] == 'juicefs' and c['image'] == IMAGE
        assert c['resources'] == {'limits': {'memory': '2Gi'}, 'requests': {'cpu': '100m', 'memory': '256Mi'}}
        assert c.get('resizePolicy') in [None, []]
        status = pod['status']['containerStatuses'][0]
        assert status['ready']
        r['before'].append({'name': name, 'uid': uid, 'container_id': status['containerID'],
                            'restart_count': status['restartCount'], 'resources': c['resources']})
        patch = [{'op': 'test', 'path': '/metadata/uid', 'value': uid},
                 {'op': 'test', 'path': '/spec/containers/0/name', 'value': 'juicefs'},
                 {'op': 'test', 'path': '/spec/containers/0/resources/limits/memory', 'value': '2Gi'},
                 {'op': 'replace', 'path': '/spec/containers/0/resources/limits/memory', 'value': '4Gi'}]
        args = ['kubectl', '-n', 'akernel-pr119-storage', 'patch', 'pod', name,
                '--subresource=resize', '--type=json', '-p', json.dumps(patch)]
        run('dry-run-' + name, args + ['--dry-run=server'])
        prepared.append((name, uid, args))
    (O / 'before.private.json').write_text(json.dumps(r, indent=2))
    for name, uid, args in prepared:
        run('resize-' + name, args)
    deadline = time.monotonic() + 120
    while True:
        observations = []
        ready = True
        for (name, uid), before in zip(PINS, r['before']):
            pod = get(name)
            s = pod['status']['containerStatuses'][0]
            assert pod['metadata']['uid'] == uid and s['containerID'] == before['container_id']
            assert s['restartCount'] == before['restart_count']
            assert pod['spec']['containers'][0]['resources']['limits']['memory'] == '4Gi'
            done = s.get('resources', {}).get('limits', {}).get('memory') == '4Gi'
            ready = ready and done and s['ready']
            observations.append({'name': name, 'same_pod_and_container': True,
                                 'restart_count_unchanged': True, 'actual_resources': s.get('resources'),
                                 'allocated_resources': s.get('allocatedResources'), 'ready': s['ready']})
        r['after'] = observations
        if ready:
            break
        if time.monotonic() > deadline:
            raise TimeoutError('in-place allocation not confirmed; preserve receipts')
        time.sleep(1)
    r.update(rc=0, same_containers_without_restart=True, at_unix_ns=time.time_ns(),
             new_client_memory_limit_bytes=4 * (1 << 30), independent_pods_only=True)
except BaseException as exc:
    r.update(error_type=type(exc).__name__, error=str(exc))
(O / 'terminal.private.json').write_text(json.dumps(r, indent=2))
print(json.dumps({k: r.get(k) for k in ['rc', 'error_type', 'error', 'same_containers_without_restart',
                                       'template_changed', 'new_client_memory_limit_bytes']}))
raise SystemExit(r['rc'])
