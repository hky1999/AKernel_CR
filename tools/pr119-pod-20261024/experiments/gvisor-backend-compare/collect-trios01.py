#!/usr/bin/env python3
"""远端整轮通过后，拆分白名单样本并导出实际脚本，不导出凭据或原始日志。"""
from pathlib import Path
import hashlib
import json
import os
import tarfile

os.umask(0o077)
N = Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
D = N / 'round-365f797-20261023.clPWh2h0/tap-checksum-fix'
O = D / 'gvisor-trios-delivery01'
E = O / 'evidence'


def load(path):
    return json.loads(path.read_text())


def selected(value, names):
    return {k: value[k] for k in names if k in value}


def save(name, value):
    path = E / name
    data = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    assert len(data) < 200000, 'split evidence before publication'
    path.write_bytes(data)


terminal = load(D / 'gvisor-backend-trios01/terminal.json')
summary = load(D / 'gvisor-backend-trios01/public-summary01.json')
audit = load(D / 'gvisor-backend-final01/terminal.json')
smoke = load(D / 'gvisor-backend-smoke02/terminal.json')
assert all(v['rc'] == 0 for v in [terminal, summary, audit, smoke])
assert len(terminal['cases']) == len(summary['cases']) == 30
assert summary['state_rounds'] == 60 and summary['final_profile'] == 'clone-native-juicefs'
assert summary['source_terminal_sha256'] == hashlib.sha256((D / 'gvisor-backend-trios01/terminal.json').read_bytes()).hexdigest()
O.mkdir(mode=0o700)
E.mkdir(mode=0o700)
G = O / 'generated'
G.mkdir(mode=0o700)

cases = summary.pop('cases')
clients_before = summary.pop('clients_before')
clients_after = summary.pop('clients_after')
save('statistics.json', summary)
for c in cases:
    save('case-%02d-%s.json' % (c['pair'], c['backend']), c)
clients = []
for key, before in clients_before.items():
    after = clients_after[key]
    assert before['processes'] == after['processes']
    delta = {k: after['events'][k] - before['events'][k] for k in before['events']}
    assert delta['oom'] == delta['oom_kill'] == 0
    clients.append(dict(execution_node='A' if key.startswith('c94000a9') else 'B',
                        actual_memory_limit_bytes=4 * (1 << 30),
                        same_processes_and_start_ticks=True,
                        process_count=len(after['processes']), memory_event_delta=delta))
save('client-stability.json', dict(rc=0, clients=clients, daemonset_template_bytes=2 * (1 << 30),
                                  cache_configuration_unchanged=True, no_global_cache_clear=True))
save('final-state.json', dict(**audit, retained_directory_hashes_are_names_not_content=True))

first = load(D / 'gvisor-backend-smoke01/terminal.json')
rescue = load(N / 'acceptance/runs/gvisor-backend-smoke01-rescue/terminal.json')
assert first['rc'] == 1 and not first['cases'] and rescue['rc'] == 0
save('trial-history.json', dict(first_trial=selected(first, ['rc', 'error_type']),
     first_trial_failed_before_checkpoint=True, observer_mount_alias_fixed_without_relaxing_device_identity=True,
     original_failed_source_verified_and_retired=selected(rescue, ['rc', 'original_64MiB_root_file_verified', 'resources_retired', 'no_checkpoint_request_had_been_issued', 'source_already_absent']),
     accepted_trial=dict(rc=0, instances=len(smoke['cases']), state_rounds=6,
                         final_profile=smoke['final_profile']), formal_samples_exclude_trials=True))

paths = {}
for version in ['01', '02']:
    for stem in ['run-backend-compare', 'sdk-backend-compare']:
        name = stem + version + '.py'
        paths[name] = D / ('gvisor-backend-compare' + version + '-input') / name
paths['rescue-smoke01.py'] = D / 'gvisor-backend-compare02-input/rescue-smoke01.py'
paths['summarize-trios01.py'] = D / 'gvisor-backend-summarize01-input/summarize-trios01.py'
paths['collect-trios01.py'] = Path(__file__).resolve()
paths['executed/final-state01.py'] = D / 'gvisor-backend-final01-input/final-state01.py'
scripts = []
for name, path in paths.items():
    data = path.read_bytes()
    target = G / name
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.write_bytes(data)
    scripts.append(dict(path='tools/pr119-pod-20261024/experiments/gvisor-backend-compare/' + name,
                        sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)))
save('script-source-index.json', dict(scripts=scripts, products_not_rebuilt=True,
                                    formal_driver_sha256=next(v['sha256'] for v in scripts if v['path'].endswith('/run-backend-compare02.py'))))
save('summary.json', dict(rc=0, instances=30, checkpoint_reload_rounds=60,
     same_product_bytes=True, final_native_profile_restored=True, final_audit_rc=0,
     scope='same physical machine, same logical node reload; not remote baseline plus local delta',
     no_competitor_or_physical_failure_domain_claim=True))
index = [dict(name=p.name, bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
         for p in sorted(E.iterdir())]
save('artifact-index.json', dict(files=index))
archive = D / 'gvisor-trios-delivery01.tar.gz'
assert not archive.exists()
with tarfile.open(archive, 'w:gz') as tar:
    for p in sorted(O.rglob('*')):
        if p.is_file():
            tar.add(p, arcname=str(p.relative_to(O)), recursive=False)
print(json.dumps(dict(archive=str(archive), bytes=archive.stat().st_size,
                     sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                     evidence_files=len(list(E.iterdir())), scripts=len(scripts))))
