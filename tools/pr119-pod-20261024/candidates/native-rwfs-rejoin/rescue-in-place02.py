#!/usr/bin/env python3
"""在本任务 Pod 内安装固定 ELF，保留 Pod 身份；不停止目标运行时。"""
import base64
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

os.umask(0o077)
N = pathlib.Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
Q = N / 'round-365f797-20261023.clPWh2h0'
D = Q / 'tap-checksum-fix'
O = D / 'native-rwfs-rejoin-rescue02'
O.mkdir(mode=0o700)
B = ['python3', str(N / 'cluster/namespace-lab07.py'), 'run', '--task', str(N), '--']
sys.path.insert(0, str(Q / 'acceptance/scripts'))
from read_control_state import read_control_state

r = dict(rc=1, status='preflight', steps=[], bootstrap_changed=False, source_stopped=False)
OLD = '124020747ef5155677bea1efb0ca35af4271641a8afd158e5b30a6268168baa4'
NEW = 'debbf268d1b1a8d4a07b9ac02be7084c3fa53c7cf794f0b1887ec65f7ace313b'


def run(name, argv, timeout=120):
    with (O / (name + '.stdout')).open('x') as out, (O / (name + '.stderr')).open('x') as err:
        p = subprocess.run(B + argv, stdout=out, stderr=err, timeout=timeout)
    r['steps'].append(dict(name=name, rc=p.returncode))
    (O / 'current.json').write_text(json.dumps(r, indent=2))
    if p.returncode:
        raise RuntimeError(name + ' failed; preserve original data and private receipts')
    return (O / (name + '.stdout')).read_text()


def py(pod, code, label):
    return json.loads(run(label, ['kubectl', '-n', 'akernel', 'exec', pod, '--', 'python3', '-c', code]))


try:
    qa = json.loads((D / 'native-rwfs-rejoin-qa02/terminal.json').read_text())
    binary = D / 'native-rwfs-rejoin-qa02/out/sandboxd'
    if qa.get('rc') != 0 or qa['sandboxd_sha256'] != NEW or hashlib.sha256(binary.read_bytes()).hexdigest() != NEW:
        raise RuntimeError('candidate byte identity differs')
    if os.statvfs(N).f_bavail * os.statvfs(N).f_frsize < 650 * (1 << 30):
        raise RuntimeError('disk reserve insufficient')
    job = N / 'acceptance/runs/shared-native-rejoin-force01'
    owner = json.loads((job / 'source-owner.private.json').read_text())
    records = read_control_state(N)[1]
    if any(v.get('assignment', {}).get('node_id') == owner['node'] for k, v in records.items() if k.startswith('environment:')):
        raise RuntimeError('source has a current Environment; no service stop')
    pods = json.loads(run('pods-before', ['kubectl', '-n', 'akernel', 'get', 'pods', '-o', 'json']))['items']
    nodes = [p for p in pods if p['metadata']['name'].startswith('akernel-node-') and not p['metadata'].get('deletionTimestamp')]
    if len(nodes) != 2:
        raise RuntimeError('Node Pods not unique')
    source = next(p for p in nodes if p['spec']['nodeName'] == owner['node'])
    if source['metadata']['uid'] != owner['pod_uid']:
        raise RuntimeError('source Pod identity changed')
    snapshot = {p['spec']['nodeName']: dict(name=p['metadata']['name'], uid=p['metadata']['uid']) for p in nodes}
    (O / 'pod-identities.json').write_text(json.dumps(snapshot, indent=2))
    candidate_path = '/home/akernel/.cr-native-rejoin-binaries/' + NEW + '/sandboxd'
    for p in nodes:
        pod = p['metadata']['name']
        current = run('old-elf-' + pod, ['kubectl', '-n', 'akernel', 'exec', pod, '--', 'sha256sum', '/usr/local/bin/sandboxd']).split()[0]
        if current != OLD:
            raise RuntimeError('unexpected current ELF')
        code = 'import pathlib,json; p=pathlib.Path(' + repr(candidate_path) + ');p.parent.mkdir(parents=True,mode=0o700,exist_ok=True);assert not p.exists();print(json.dumps({"candidate_directory_created":True}))'
        py(pod, code, 'prepare-path-' + pod)
        run('copy-' + pod, ['kubectl', '-n', 'akernel', 'cp', str(binary), pod + ':' + candidate_path], 180)
        code = 'import pathlib,hashlib,json,os;p=pathlib.Path(' + repr(candidate_path) + ');assert p.is_file()and not p.is_symlink();assert hashlib.sha256(p.read_bytes()).hexdigest()==' + repr(NEW) + ';os.chmod(p,0o755);f=p.open("rb");os.fsync(f.fileno());f.close();print(json.dumps({"candidate_sha256":' + repr(NEW) + '}))'
        py(pod, code, 'verify-candidate-' + pod)

    volume = next(v for v in source['spec']['volumes'] if v['name'] == 'akernel-node-bootstrap')
    cm_name = volume['configMap']['name']
    cm = json.loads(run('bootstrap-before-private', ['kubectl', '-n', 'akernel', 'get', 'configmap', cm_name, '-o', 'json']))
    if cm['metadata'].get('annotations', {}).get('meta.helm.sh/release-name') != 'akernel':
        raise RuntimeError('bootstrap ConfigMap outside owned release')
    keys = [key for key, value in cm['data'].items() if 'sandboxd' in value and ('prepare' in key or key.endswith('.sh'))]
    if len(keys) != 1:
        raise RuntimeError('bootstrap script identity ambiguous')
    key = keys[0]
    original = cm['data'][key]
    if 'AKCR_NATIVE_REJOIN_RUNTIME_OVERRIDE_V2' in original:
        raise RuntimeError('bootstrap override already present; inspect prior receipt')
    install_code = '\n'.join([
        'import pathlib,hashlib,os,shutil',
        'source=pathlib.Path(' + repr(candidate_path) + ')',
        'assert source.is_file() and not source.is_symlink()',
        'assert hashlib.sha256(source.read_bytes()).hexdigest()==' + repr(NEW),
        'destination=pathlib.Path("/usr/local/bin/sandboxd")',
        'temporary=destination.with_name(".sandboxd-native-rejoin-"+str(os.getpid()))',
        'with source.open("rb")as src,temporary.open("xb")as out:',
        ' shutil.copyfileobj(src,out);out.flush();os.fchmod(out.fileno(),0o755);os.fsync(out.fileno())',
        'os.replace(temporary,destination)',
        'parent=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY)',
        'os.fsync(parent);os.close(parent)',
    ])
    injection = '\n# AKCR_NATIVE_REJOIN_RUNTIME_OVERRIDE_V2\nif ! python3 - <<\'AKCR_NATIVE_REJOIN_ELF\'\n' + install_code + '\nAKCR_NATIVE_REJOIN_ELF\nthen\n  exit 1\nfi\n'
    if original.startswith('#!'):
        first, tail = original.split('\n', 1)
        updated = first + '\n' + injection + tail
    else:
        updated = injection + original
    shell = O / 'prepare-node-override.private.sh'
    shell.write_text(updated)
    # A syntax check on BareMetal precedes any ConfigMap or service mutation.
    with (O / 'shell-syntax.stdout').open('x') as out, (O / 'shell-syntax.stderr').open('x') as err:
        p = subprocess.run(['bash', '-n', str(shell)], stdout=out, stderr=err, timeout=20)
    if p.returncode:
        raise RuntimeError('private bootstrap syntax failed')
    cm['data'][key] = updated
    document = O / 'bootstrap-updated.private.json'
    document.write_text(json.dumps(cm))
    run('bootstrap-replace', ['kubectl', '-n', 'akernel', 'replace', '-f', str(document)])
    r.update(bootstrap_changed=True, bootstrap_configmap=cm_name, bootstrap_uid=cm['metadata']['uid'], bootstrap_key=key, original_script_sha256=hashlib.sha256(original.encode()).hexdigest(), override_script_sha256=hashlib.sha256(updated.encode()).hexdigest(), candidate_sha256=NEW, image_base_unchanged=True)

    source_pod = source['metadata']['name']
    guard_code = 'import pathlib,os,json;rows=[]\nfor p in pathlib.Path("/proc").iterdir():\n if not p.name.isdigit():continue\n try:exe=os.path.basename(os.readlink(p/"exe"))\n except OSError:continue\n if exe in ["firecracker","runsc-sandbox","runsc-gofer"]:rows.append(exe)\nassert not rows,rows\nprint(json.dumps({"source_runtime_processes":0}))'
    py(source_pod, guard_code, 'source-runtime-guard')
    run('source-stop-sandboxd', ['kubectl', '-n', 'akernel', 'exec', source_pod, '--', 'systemctl', 'stop', 'sandboxd'])
    r['source_stopped'] = True
    py(source_pod, install_code + '\nprint("{}")', 'source-install-elf')
    run('source-start-sandboxd', ['kubectl', '-n', 'akernel', 'exec', source_pod, '--', 'systemctl', 'start', 'sandboxd'])
    r['status'] = 'waiting-source-routable'
    (O / 'current.json').write_text(json.dumps(r, indent=2))
    deadline = time.monotonic() + 240
    stable = 0
    while True:
        row = read_control_state(N)[1].get('node:' + owner['node'], {})
        good = row.get('session', {}).get('routable') and row.get('node', {}).get('available') and row.get('scheduling_paused') is False
        stable = stable + 1 if good else 0
        if stable >= 3:
            break
        if time.monotonic() > deadline:
            raise TimeoutError('source did not recover; keep private bootstrap and evidence')
        time.sleep(2)
    after = json.loads(run('pods-after', ['kubectl', '-n', 'akernel', 'get', 'pods', '-o', 'json']))['items']
    current = {p['spec']['nodeName']: dict(name=p['metadata']['name'], uid=p['metadata']['uid']) for p in after if p['metadata']['name'].startswith('akernel-node-') and not p['metadata'].get('deletionTimestamp')}
    if current != snapshot:
        raise RuntimeError('Pod identities changed during in-place rescue')
    actual = run('source-new-elf', ['kubectl', '-n', 'akernel', 'exec', source_pod, '--', 'sha256sum', '/usr/local/bin/sandboxd']).split()[0]
    if actual != NEW:
        raise RuntimeError('source did not consume tested bytes')
    r.update(rc=0, status='source-rescued-with-same-pod-and-tested-runtime-override', source_node=owner['node'], source_pod=source_pod, target_elf_unchanged=True, target_service_not_stopped=True, all_pod_uids_unchanged=True, manual_pool_reset=False)
except BaseException as error:
    r.update(status='failed', error_type=type(error).__name__, error=str(error))
finally:
    (O / 'terminal.json').write_text(json.dumps(r, indent=2))
sys.exit(r['rc'])
