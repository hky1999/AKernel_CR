#!/usr/bin/env python3
"""同镜像 gVisor 三组对照，分开介质迁移与克隆模式，只操作登记的独占任务。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import tomllib
import yaml

os.umask(0o077)
N = Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
Q = N / 'round-365f797-20261023.clPWh2h0'
D = Q / 'tap-checksum-fix'
B = ['python3', str(N / 'cluster/namespace-lab07.py'), 'run', '--task', str(N), '--']
NODES = ['akcr119-20261022-worker', 'akcr119-20261022-worker2']
ROOT = '/mnt/akernel-shared/akernel/runsc-rwfs-native-qbGAw9tp01'
IMAGE = 'localhost/akernel-pr119:365f7971f895-cgroup-leases01'
CRI = 'sha256:0bde46ba9cbbee107af01d085919c012c9d38094910d2a4761716de7f1c9dcb4'
ELF = '433574033952b1ad9106b125e085302b9c5268fea179609975de7d722c2f6c83'
PROBE = 'f11e2a32602ef80cadecb664086562f4367e92bd79a8df63c934088e8f13cc94'
sys.path.insert(0, str(Q / 'acceptance/scripts'))
from read_control_state import read_control_state

CAPACITY = r'''from pathlib import Path
import re,subprocess,json,os,time
keyring=Path('/etc/ceph/keyring-store/keyring')
names=re.findall(r'^\s*\[([A-Za-z0-9_.-]+)\]\s*$',keyring.read_text(),re.M)
assert names==['client.rgw.checkpoints.a']
extra=[];matched=0
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:a=[os.fsdecode(x)for x in(p/'cmdline').read_bytes().split(b'\0')if x]
 except OSError:continue
 if not a or os.path.basename(a[0])not in['radosgw','ceph-radosgw']:continue
 matched+=1
 for i,arg in enumerate(a):
  if arg in ['--mon-host','-m','--conf','-c','--fsid']and i+1<len(a):extra.extend([arg,a[i+1]])
  elif any(arg.startswith(t+'=')for t in ['--mon-host','--conf','--fsid']):extra.append(arg)
assert matched==1 and extra
p=subprocess.run(['/usr/bin/ceph','--name',names[0],'--keyring',str(keyring),*extra,'df','--format=json'],capture_output=True,text=True,timeout=35)
assert p.returncode==0,'live Ceph query failed; do not use old CR status'
v=json.loads(p.stdout);s=v['stats'];assert s['total_bytes']==42949672960 and s['num_osds']==1
pool=[p for p in v['pools']if p['name']=='checkpoints.rgw.buckets.data'];assert len(pool)==1
print(json.dumps({'at_unix_ns':time.time_ns(),'total_bytes':s['total_bytes'],'available_bytes':s['total_avail_bytes'],'used_raw_bytes':s['total_used_raw_bytes'],'data_pool_max_avail_bytes':pool[0]['stats']['max_avail'],'data_pool_stored_bytes':pool[0]['stats']['stored']}))
'''


def clients():
    expected = ['c94000a9e103f344bd40e2fd1cce2bb4ee113766beadc63ae5e5f8c7b6a5b550',
                '31814694e9fd4463d194bb5150fc2dec052131af18d726ca330e822345c0f017']
    result = {}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            if Path(os.readlink(p / 'exe')).name != 'juicefs':
                continue
            cg = (p / 'cgroup').read_text().strip().split('::', 1)[1]
            if 'akernel-pr119-followup-20261022-qbGAw9tp' not in cg:
                continue
            matches = [x for x in expected if x in cg]
            if not matches:
                continue
            assert len(matches) == 1
            q = Path('/sys/fs/cgroup' + cg)
            assert (q / 'memory.max').read_text().strip() == str(4 * (1 << 30))
            v = result.setdefault(matches[0], {'processes': {}, 'events': {
                k: int(v) for k, v in [line.split() for line in (q / 'memory.events').read_text().splitlines()]}})
            v['processes'][p.name] = (p / 'stat').read_text().rsplit(')', 1)[1].split()[19]
        except (FileNotFoundError, PermissionError):
            continue
    assert set(result) == set(expected) and all(len(v['processes']) == 2 for v in result.values())
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pairs', type=int, choices=[1, 10], required=True)
    parser.add_argument('--require-smoke', type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.relative_to(D)
    out.mkdir(mode=0o700)
    (out / 'cache').mkdir(mode=0o700)
    r = dict(rc=1, status='preflight', cases=[], steps=[], final_profile=None, protocol=dict(pairs=args.pairs, runtimes=['runsc'], order='six permutations repeated; paired within node; A=full-local; B=full-native; C=clone-native', state_rounds_per_instance=2, instances_independent_within_backend=True, cache_scope='warm infrastructure; no global cache clearing', only_config_fields=['runsc.checkpoint_mode', 'runsc.writable_storage_dir', 'runsc.writable_storage_filesystem'], image=IMAGE, elf=ELF, application_memory_bytes=536870912, vm_memory_mb=2048, root_file_bytes=67108864, private_disk_mb=1024, random_sync_operations=64, payload_seed=20261024, source_code_unchanged='sandboxd91dff2f/gvisor218d85378'))

    def status(phase, **data):
        r['status'] = phase
        r['current'] = data
        (out / 'current.json').write_text(json.dumps(r, indent=2))

    def run(folder, name, argv, timeout=180):
        with (folder / (name + '.stdout')).open('x') as so, (folder / (name + '.stderr')).open('x') as se:
            p = subprocess.run(argv, stdout=so, stderr=se, timeout=timeout)
        r['steps'].append(dict(name=str(folder.relative_to(out)) + '/' + name, rc=p.returncode))
        if p.returncode:
            raise RuntimeError(name + ' failed; retain case, resources and current profile')
        return (folder / (name + '.stdout')).read_text()

    def lab(folder, name, argv, timeout=180):
        return run(folder, name, B + argv, timeout)

    def no_env():
        rows = read_control_state(N)[1]
        if any(k.startswith('environment:') for k in rows):
            raise RuntimeError('Environment remains; refuse profile change')
        return rows

    def capacity(folder):
        if os.statvfs(N).f_bavail * os.statvfs(N).f_frsize < 650 * (1 << 30):
            raise RuntimeError('host reserve below 650 GiB')
        data = json.loads(lab(folder, 'live-ceph-capacity', ['kubectl', '-n', 'akernel-pr119-storage', 'exec', 'deployment/rook-ceph-rgw-checkpoints-a', '-c', 'rgw', '--', 'python3', '-c', CAPACITY]))
        if min(data['available_bytes'], data['data_pool_max_avail_bytes']) < 10 * (1 << 30):
            raise RuntimeError('test object backend has less than 10 GiB; no new workload')

    def pods(folder, label):
        rows = json.loads(lab(folder, label, ['kubectl', '-n', 'akernel', 'get', 'pods', '-o', 'json']))['items']
        return [p for p in rows if not p['metadata'].get('deletionTimestamp')]

    def deploy(backend, label):
        state = no_env()
        folder = out / label
        folder.mkdir(mode=0o700)
        status('deploying-profile', backend=backend, label=label)
        capacity(folder)
        previous = {node: hashlib.sha256(str(state['node:' + node]['session']['id']).encode()).hexdigest() for node in NODES}
        (folder / 'previous-sessions.json').write_text(json.dumps(previous))
        before = pods(folder, 'pods-before-private')
        controls = {p['metadata']['name']: p['metadata']['uid'] for p in before if not p['metadata']['name'].startswith('akernel-node-')}
        secretargs = ['kubectl', '-n', 'akernel', 'get', 'secrets', 'akernel-adx-tls', 'akernel-secrets', '-o', 'jsonpath={range .items[*]}{.metadata.name}{" "}{.metadata.uid}{"\\n"}{end}']
        secrets = lab(folder, 'secret-uids-before', secretargs)
        ds = json.loads(lab(folder, 'node-template-before-private', ['kubectl', '-n', 'akernel', 'get', 'daemonset', 'akernel-node', '-o', 'json']))
        if ds['spec']['template']['spec']['containers'][0]['image'] != IMAGE:
            raise RuntimeError('image changed outside comparison')
        checksum = ds['spec']['template']['metadata']['annotations']['checksum/node-config']
        lab(folder, 'helm-profile', ['helm', 'upgrade', '--install', 'akernel', str(Q / 'source/AKernel/deploy/akernel/charts/core'), '--namespace', 'akernel', '-f', str(out / (backend + '.private.yaml')), '-f', str(Q / 'source/AKernel/deploy/shared-storage/juicefs-values.yaml'), '--set-string', 'image.tag=' + IMAGE.split(':', 1)[1], '--post-renderer', str(N / 'cluster/helm11/control-placement.py'), '--wait', '--timeout=8m'], 540)
        ds = json.loads(lab(folder, 'node-template-after-private', ['kubectl', '-n', 'akernel', 'get', 'daemonset', 'akernel-node', '-o', 'json']))
        if ds['spec']['template']['metadata']['annotations']['checksum/node-config'] == checksum:
            lab(folder, 'same-layout-owned-nodes-restart', ['kubectl', '-n', 'akernel', 'rollout', 'restart', 'daemonset/akernel-node'])
        lab(folder, 'node-rollout', ['kubectl', '-n', 'akernel', 'rollout', 'status', 'daemonset/akernel-node', '--timeout=240s'], 270)
        run(folder, 'real-readiness', ['python3', str(D / 'cgroup-durable-leases-sdk01/wait-ready01.py'), '--expected-digest', CRI, '--output', str(folder / 'ready'), '--previous-session-hashes', str(folder / 'previous-sessions.json'), '--timeout', '360'], 450)
        after = pods(folder, 'pods-after-private')
        if {p['metadata']['name']: p['metadata']['uid'] for p in after if not p['metadata']['name'].startswith('akernel-node-')} != controls:
            raise RuntimeError('control/API/Redis Pod changed; comparison stopped before SDK')
        if lab(folder, 'secret-uids-after', secretargs) != secrets:
            raise RuntimeError('Secret UID changed')
        if len(after) != 5 or any(s.get('imageID', '').rsplit('@', 1)[-1] != CRI for p in after for s in p['status'].get('containerStatuses', [])):
            raise RuntimeError('actual image identity differs')
        for p in after:
            if not p['metadata']['name'].startswith('akernel-node-'):
                continue
            prefix = ['kubectl', '-n', 'akernel', 'exec', p['metadata']['name'], '--']
            paths = list(pins)
            got = lab(folder, 'pins-' + p['spec']['nodeName'], prefix + ['sha256sum', *paths])
            if {x.split()[1]: x.split()[0] for x in got.splitlines() if len(x.split()) == 2} != pins:
                raise RuntimeError('actual runtime tuple changed')
            code = "import pathlib,tomllib,json;v=tomllib.loads(pathlib.Path('/home/akernel/sandboxd/config.toml').read_text())['plugin']['runtime']['runsc'];expected=" + repr('' if backend == 'full-local-xfs' else ROOT) + ";assert v.get('writable_storage_dir','')==expected;assert v.get('writable_storage_filesystem','')==('fuse.juicefs'if expected else'');assert v['checkpoint_mode']==" + repr('reflink' if backend == 'clone-native-juicefs' else 'full') + ";print(json.dumps({'backend':" + repr(backend) + ",'config_verified':True}))"
            lab(folder, 'config-' + p['spec']['nodeName'], prefix + ['python3', '-c', code])
        no_env()
        r['final_profile'] = backend
        return folder

    try:
        for name in ['cgroup-durable-leases-sdk01', 'native-storage-faults01', 'native-pending-capture02', 'fc-backend-io-build01']:
            if json.loads((D / name / 'terminal.json').read_text()).get('rc') != 0:
                raise RuntimeError('accepted functional/probe prerequisite missing')
        fixture = Path(__file__).parent / 'sdk-backend-compare02.py'
        r['fixture_sha256'] = hashlib.sha256(fixture.read_bytes()).hexdigest()
        if args.require_smoke:
            smoke = json.loads(args.require_smoke.read_text())
            if smoke.get('rc') != 0 or len(smoke.get('cases', [])) != 3 or smoke.get('fixture_sha256') != r['fixture_sha256']:
                raise RuntimeError('both backend smoke cases have not passed on this fixture')
        elif args.pairs != 1:
            raise RuntimeError('formal pairs require successful smoke')
        assets = json.loads((Q / 'image-build/payload-receipt.json').read_text())['assets']
        paths = ['/usr/local/bin/sandboxd', '/usr/local/bin/runsc', '/usr/local/bin/firecracker', '/opt/firecracker/initrd.img', '/opt/firecracker/vmlinux', '/opt/akernel/runtime/akernel-runtime-rootfs.img', '/opt/adx/current/runtime/adx-execd', '/opt/adx/current/bin/adxlet', '/opt/adx/current/bin/adx-coordinator', '/opt/adx/current/bin/adx-apiserver']
        pins = {p: assets[p]['sha256'] for p in paths}
        pins['/usr/local/bin/sandboxd'] = ELF
        image = json.loads((D / 'cgroup-durable-leases-image01/terminal.json').read_text())
        for name, asset in image['runtime_assets'].items():
            pins['/usr/local/bin/' + name] = asset['sha256']
        native = yaml.safe_load((D / 'cgroup-durable-leases-sdk01/writable-values.yaml').read_text())
        cfg = native['node']['config']['sandboxd']['config']
        original = tomllib.loads(cfg)
        fields = original['plugin']['runtime']['runsc']
        if fields.get('writable_storage_dir') != ROOT or fields.get('writable_storage_filesystem') != 'fuse.juicefs' or fields.get('checkpoint_mode') != 'reflink':
            raise RuntimeError('native gVisor profile differs')
        for backend in ['full-local-xfs', 'full-native-juicefs', 'clone-native-juicefs']:
            expected = json.loads(json.dumps(original))
            gv = expected['plugin']['runtime']['runsc']
            gv['checkpoint_mode'] = 'reflink' if backend == 'clone-native-juicefs' else 'full'
            if backend == 'full-local-xfs':
                del gv['writable_storage_dir']
                del gv['writable_storage_filesystem']
            section = None
            output = []
            edits = []
            for line in cfg.splitlines(keepends=True):
                if line.strip().startswith('['):
                    section = line.strip()
                if section == '[plugin.runtime.runsc]':
                    m = re.match(r'^\s*(checkpoint_mode|writable_storage_dir|writable_storage_filesystem)\s*=', line)
                    if m:
                        key = m.group(1)
                        edits.append(key)
                        if key not in gv:
                            continue
                        line = key + ' = ' + json.dumps(gv[key]) + '\n'
                output.append(line)
            rewritten = ''.join(output)
            if sorted(edits) != ['checkpoint_mode', 'writable_storage_dir', 'writable_storage_filesystem'] or tomllib.loads(rewritten) != expected:
                raise RuntimeError('profile rewrite escaped the three runsc fields')
            values = json.loads(json.dumps(native))
            values['node']['config']['sandboxd']['config'] = rewritten
            (out / (backend + '.private.yaml')).write_text(yaml.safe_dump(values, sort_keys=False))
        no_env()
        before_clients = clients()
        r['clients_before'] = before_clients
        for pair in range(1, args.pairs + 1):
            groups = ['full-local-xfs', 'full-native-juicefs', 'clone-native-juicefs']
            permutations = [(0, 1, 2), (2, 1, 0), (1, 2, 0), (0, 2, 1), (2, 0, 1), (1, 0, 2)]
            order = [groups[i] for i in permutations[(pair - 1) % len(permutations)]]
            node = NODES[(pair - 1) % 2]
            for position, backend in enumerate(order):
                label = 'pair-' + str(pair) + '-' + str(position) + '-' + backend
                folder = deploy(backend, label)
                status('sdk-measurement', pair=pair, backend=backend, node=node)
                job = N / 'acceptance/runs' / (out.name + '-' + str(pair) + '-' + backend)
                shell = 'set -eu; source ' + shlex.quote(str(Q / 'acceptance/auth-shared-tapfix-direct01/sdk.env')) + '; export PYTHONPATH=' + shlex.quote(str(Q / 'acceptance/scripts')) + '; export PYTHONDONTWRITEBYTECODE=1 XDG_CACHE_HOME=' + shlex.quote(str(out / 'cache')) + '; exec ' + shlex.join([str(Q / 'sdk/client/bin/python'), str(fixture), '--runtime', 'runsc', '--variant', backend, '--node-id', node, '--rounds', '2', '--io-probe', str(D / 'fc-backend-io-build01/out/guest-storage-io'), '--output', str(job)])
                run(folder, 'sdk', B + ['bash', '-c', shell], 1800)
                data = json.loads((job / 'terminal.json').read_text())
                if data.get('rc') != 0 or len(data.get('rounds', [])) != 2 or not data.get('resources_deleted') or data.get('io_probe_sha256') != PROBE:
                    raise RuntimeError('measurement terminal incomplete')
                if len(data.get('backing_media', [])) != 4:
                    raise RuntimeError('pre/post restore media proof incomplete')
                r['cases'].append(dict(pair=pair, position=position, backend=backend, node=node, job=str(job), data=data))
                current_clients = clients()
                for key, before in before_clients.items():
                    if current_clients[key]['processes'] != before['processes']:
                        raise RuntimeError('JuiceFS worker changed; comparison interrupted')
                    if any(current_clients[key]['events'][event] != before['events'][event] for event in ['oom', 'oom_kill']):
                        raise RuntimeError('new client OOM; comparison interrupted')
                r['clients_after'] = current_clients
                no_env()
                status('case-complete', pair=pair, backend=backend)
        deploy('clone-native-juicefs', 'restore-final-native')
        no_env()
        r.update(rc=0, status='same-code-backend-comparison-passed-final-native', performance_complete=args.pairs == 10, smoke_only=args.pairs == 1)
    except BaseException as error:
        r.update(status='failed', error_type=type(error).__name__, error=str(error))
    finally:
        (out / 'terminal.json').write_text(json.dumps(r, indent=2))
    return r['rc']


if __name__ == '__main__':
    sys.exit(main())
