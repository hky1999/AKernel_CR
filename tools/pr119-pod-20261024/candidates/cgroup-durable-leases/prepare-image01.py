#!/usr/bin/env python3
"""仅在已登记的 BareMetal 私有任务中构建/导入，不部署、不创建实例。"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

os.umask(0o077)
N = pathlib.Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
Q = N / 'round-365f797-20261023.clPWh2h0'
D = Q / 'tap-checksum-fix'
O = D / 'cgroup-durable-leases-image01'
O.mkdir(mode=0o700)
B = ['python3', str(N / 'cluster/namespace-lab07.py'), 'run', '--task', str(N), '--']
PB = ['/usr/bin/podman', '--root', str(N / 'image-build/graph'), '--runroot', str(N / 'image-build/runroot'), '--tmpdir', str(N / 'image-build/libpod-tmp'), '--cgroup-manager', 'cgroupfs']
NODES = {
    'akcr119-20261022-control-plane': '309834713ae51c81b89d88111a2a0adaf345f9ec135d8d3938d20f4727023bfa',
    'akcr119-20261022-worker': 'c94000a9e103f344bd40e2fd1cce2bb4ee113766beadc63ae5e5f8c7b6a5b550',
    'akcr119-20261022-worker2': '31814694e9fd4463d194bb5150fc2dec052131af18d726ca330e822345c0f017',
}
r = dict(rc=1, status='waiting-quality', deployed=False, steps=[], mapping=[])


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run(name, command, stdin=None, timeout=900):
    with (O / (name + '.stdout')).open('xb') as out, (O / (name + '.stderr')).open('xb') as err:
        p = subprocess.run(command, stdin=stdin, stdout=out, stderr=err, timeout=timeout)
    r['steps'].append(dict(name=name, rc=p.returncode))
    (O / 'current.json').write_text(json.dumps(r, indent=2))
    if p.returncode:
        raise RuntimeError(name + ' failed; preserve evidence')
    return (O / (name + '.stdout')).read_bytes()


def content(node, digest, label):
    raw = run(label, B + ['podman', 'exec', node, 'ctr', '-n', 'k8s.io', 'content', 'get', digest])
    if 'sha256:' + hashlib.sha256(raw).hexdigest() != digest:
        raise RuntimeError('content digest mismatch')
    return json.loads(raw)


try:
    deadline = time.monotonic() + 7200
    quality = D / 'cgroup-durable-leases-qa01/terminal.json'
    while not quality.exists():
        if time.monotonic() > deadline:
            raise TimeoutError('source gates did not finish; no image prepared')
        launch=json.loads((D/'cgroup-durable-leases-qa01/launch.json').read_text())
        p=pathlib.Path('/proc')/str(launch['pid'])/'stat'
        if not p.exists():raise RuntimeError('consumer gate driver gone without terminal')
        st=p.read_text().rsplit(')',1)[1].split()
        if st[19]!=launch['start_ticks'] or st[0]=='Z':raise RuntimeError('consumer gate process identity changed')
        time.sleep(5)
    qa = json.loads(quality.read_text())
    if qa.get('rc') != 0:
        raise RuntimeError('combined source quality gates failed')
    if os.statvfs(N).f_bavail * os.statvfs(N).f_frsize < 650 * (1 << 30):
        raise RuntimeError('disk reserve insufficient')
    sys.path.insert(0, str(Q / 'acceptance/scripts'))
    from read_control_state import read_control_state
    if any(key.startswith('environment:') for key in read_control_state(N)[1]):
        raise RuntimeError('active Environment; no image transition')
    source = D / 'cgroup-durable-leases-qa01/source'
    if any(sha(source / path) != value for path, value in qa['source_files'].items()):
        raise RuntimeError('tested source changed')
    binary = D / 'cgroup-durable-leases-qa01/out-candidate/sandboxd'
    if sha(binary) != qa['sandboxd_sha256']:
        raise RuntimeError('tested ELF changed')
    context = O / 'context'
    context.mkdir(mode=0o700)
    shutil.copyfile(binary, context / 'sandboxd')
    (context / 'sandboxd').chmod(0o755)
    runtime = json.loads((D/'gvisor-native-clone-bazel05/terminal.json').read_text())
    if runtime['rc'] != 0:
        raise RuntimeError('matched runtime/consumer gates not complete')
    archive_path=D/'gvisor-native-clone-bazel05/out/gvisor-native-clone-amd64.tar.bz2'
    if sha(archive_path) != runtime['bundle_sha256']:
        raise RuntimeError('qualified bundle changed')
    baseline=json.loads((D/'gvisor-native-consumer-image02/terminal.json').read_text())
    base=json.loads(run('base-image-identity', PB+['image','inspect',baseline['image']]))[0]
    if base['Id'].removeprefix('sha256:') != baseline['config_sha256']:
        raise RuntimeError('base candidate image moved')
    import tarfile,io
    # Inspect a stopped, task-owned base container; never run a process in it.
    cid=run('base-inspection-create',PB+['create','--pull=never','--network=none','--name','akcr119-cgroup-leases-base-inspect01','--label','akernel.qa=cgroup-durable-leases-image01','--label','akernel.task='+N.name,'--entrypoint','/usr/bin/true',baseline['image']]).decode().strip()
    obj=json.loads(run('base-inspection-identity',PB+['inspect',cid]))[0]
    if obj['Id']!=cid or obj['State']['Running'] or obj['Config']['Labels'].get('akernel.qa')!='cgroup-durable-leases-image01':
        raise RuntimeError('base inspector identity mismatch')
    old_helpers=run('base-helper-layout',PB+['cp',cid+':/usr/local/bin/gvisor-bin','-'])
    with tarfile.open(fileobj=io.BytesIO(old_helpers),mode='r:*')as tar:
        members={pathlib.PurePosixPath(m.name).name:m for m in tar.getmembers()if not m.isdir()}
        expected={pathlib.PurePosixPath(n).name for n in runtime['assets']if n.startswith('gvisor-bin/')}
        if set(members)!=expected or not all(m.isfile()for m in members.values()):
            raise RuntimeError('base helper layout has unaccounted entries; no overwrite permitted')
        r['base_helper_assets']={name:{'bytes':m.size,'sha256':hashlib.sha256(tar.extractfile(m).read()).hexdigest()}for name,m in members.items()}
        if any(v['sha256']!=runtime['assets']['gvisor-bin/'+name]['sha256']for name,v in r['base_helper_assets'].items()):raise RuntimeError('base helper bytes differ from unchanged runtime')
    obj=json.loads(run('base-inspection-final-identity',PB+['inspect',cid]))[0]
    if obj['Id']!=cid or obj['State']['Running'] or obj['Config']['Labels'].get('akernel.qa')!='cgroup-durable-leases-image01':
        raise RuntimeError('base inspector changed; retaining it')
    run('remove-stopped-owned-base-inspector',PB+['rm',cid])
    (context/'Dockerfile').write_text('FROM '+baseline['image']+'\nCOPY --chmod=0755 sandboxd /usr/local/bin/sandboxd\nLABEL org.akernel.test.scope=cgroup-lease-candidate-not-promoted org.akernel.test.runtime.bundle='+runtime['bundle_sha256']+' org.akernel.test.sandboxd.sha256='+qa['sandboxd_sha256']+'\n')
    r['runtime_bundle_sha256']=runtime['bundle_sha256'];r['runtime_assets']=runtime['assets']
    image = 'localhost/akernel-pr119:365f7971f895-cgroup-leases01'
    run('build', PB + ['build', '--pull=never', '--network=none', '--cpu-period', '100000', '--cpu-quota', '200000', '--memory', '2g', '--cgroup-parent', '/akernel-pr119-followup-20261022-qbGAw9tp', '-t', image, '-f', str(context / 'Dockerfile'), str(context)])
    info = json.loads(run('inspect', PB + ['image', 'inspect', image]))[0]
    config = info['Id'].removeprefix('sha256:')
    archive = O / 'cgroup-leases-candidate.oci.tar'
    run('export', PB + ['save', '--format', 'oci-archive', '-o', str(archive), image])
    for name, node in NODES.items():
        identity = json.loads(run(name + '-identity', B + ['podman', 'inspect', name]))[0]
        if identity['Id'] != node or not identity['State']['Running']:
            raise RuntimeError('owned Kind identity changed')
        with archive.open('rb') as stream:
            run(name + '-import', B + ['podman', 'exec', '-i', node, 'ctr', '-n', 'k8s.io', 'images', 'import', '--all-platforms', '--digests', '-'], stdin=stream)
        rows = json.loads(run(name + '-cri', B + ['podman', 'exec', node, 'crictl', 'images', '-o', 'json']))['images']
        rows = [item for item in rows if image in item.get('repoTags', [])]
        if len(rows) != 1:
            raise RuntimeError('CRI reference ambiguous')
        digests = {value.rsplit('@', 1)[-1] for value in rows[0].get('repoDigests', []) if '@' in value}
        if len(digests) != 1:
            raise RuntimeError('CRI digest ambiguous')
        cri = digests.pop()
        index = content(node, cri, name + '-index')
        descriptors = index.get('manifests', [])
        if len(descriptors) != 1 or descriptors[0].get('annotations', {}).get('org.opencontainers.image.ref.name') != image:
            raise RuntimeError('single image index does not identify exact tag')
        leaf = descriptors[0]['digest']
        manifest = content(node, leaf, name + '-leaf')
        if manifest.get('config', {}).get('digest') != 'sha256:' + config:
            raise RuntimeError('imported image config differs')
        actual = content(node, 'sha256:' + config, name + '-config')
        if actual.get('os') != 'linux' or actual.get('architecture') != 'amd64':
            raise RuntimeError('actual config platform differs')
        table = run(name + '-tags', B + ['podman', 'exec', node, 'ctr', '-n', 'k8s.io', 'images', 'ls']).decode()
        tag = [line.split() for line in table.splitlines() if line.split() and line.split()[0] == image]
        if len(tag) != 1 or tag[0][2] != leaf:
            raise RuntimeError('tag/CRI index/leaf disagree')
        r['mapping'].append(dict(node=name, cri_digest=cri, leaf_digest=leaf, config_sha256=config, platform='linux/amd64'))
    if len({row['cri_digest'] for row in r['mapping']}) != 1:
        raise RuntimeError('node CRI digests differ')
    r.update(rc=0, status='combined-image-imported-not-deployed', image=image, config_sha256=config, expected_cri_digest=r['mapping'][0]['cri_digest'], sandboxd_sha256=qa['sandboxd_sha256'], source_files=qa['source_files'], archive_sha256=sha(archive), archive_bytes=archive.stat().st_size)
except BaseException as error:
    r.update(status='failed', error_type=type(error).__name__, error=str(error))
finally:
    (O / 'terminal.json').write_text(json.dumps(r, indent=2))
sys.exit(r['rc'])
