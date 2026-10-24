#!/usr/bin/env python3
"""只导出这轮实际终态字段、脚本摘要和两个生成的只读盘点脚本。"""
from pathlib import Path
import hashlib
import json
import os
import tarfile

os.umask(0o077)
N = Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
D = N / 'round-365f797-20261023.clPWh2h0/tap-checksum-fix'
O = D / 'native-lifecycle-delivery01'
O.mkdir(mode=0o700)
E = O / 'evidence'
E.mkdir(mode=0o700)


def load(p):
    return json.loads(p.read_text())


def selected(value, names):
    return {k: value[k] for k in names if k in value}


def save(name, data):
    (E / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


faults = load(D / 'native-storage-faults01/terminal.json')
pending = load(D / 'native-pending-capture02/terminal.json')
resize = load(D / 'owned-juicefs-resize01/terminal.private.json')
rescue = load(N / 'acceptance/runs/shared-native-pending-capture03-rescue/terminal.json')
assert all(x['rc'] == 0 for x in [faults, pending, resize, rescue])
assert len(faults['cases']) == 4 and len(pending['cases']) == 2
save('storage-faults.json', {
    'rc': 0, 'client_limit_at_execution_bytes': 2 * (1 << 30),
    'product_commit': faults['source_commit'], 'sandboxd_sha256': faults['sandboxd_sha256'],
    'cri_digest': faults['cri_digest'], 'diagnostic_not_performance': True,
    'cases': [{'case': c['case'], 'result': selected(c['result'], [
        'rc', 'runtime', 'memory_bytes', 'request_rejected_inside_shadow_interval', 'no_published_snapshot',
        'no_local_fallback_entries', 'original_mount_restored', 'uncheckpointed_source_state_preserved',
        'new_distinct_snapshot_after_recovery', 'mount_fault_restored', 's3_unavailability_observed',
        'same_gateway_process_resumed', 'successful_ack_while_s3_paused', 'request_returned_success',
        'published_snapshot_after_recovery', 'storage_fault_reconciled_without_replay',
        'explicit_source_deletion_rescue', 'source_writer_exit_verified',
        'selected_snapshot_cross_node_recovery_verified', 'target_next_checkpoint_reload_verified',
        'failed_capture_directories_removed', 'storage_fault_restored', 'resources_deleted'])}
        for c in faults['cases']]})
save('pending-capture.json', {
    'rc': 0, 'client_limit_at_execution_bytes': 4 * (1 << 30),
    'diagnostic_not_performance': True, 'internal_await_line_execution_proven': False,
    'cases': [dict(execution_node=chr(65 + i), **selected(c, [
        'rc', 'runtime', 'memory_bytes', 'vm_memory_mb', 'reader_barrier_seconds',
        'sdk_snapshot_requested_with_real_pending_input', 'no_success_ack_before_reader_resume',
        'captured_snapshot_full_memory_and_root_readback_verified', 'original_runtime_preserved',
        'reference_and_named_files_preserved', 'busy_delete_after_restart', 'full_state_verified',
        'later_checkpoint_reload_verified', 'resources_deleted'])) for i, c in enumerate(pending['cases'])]})
proofs = []
for i, node in enumerate(['akcr119-20261022-worker', 'akcr119-20261022-worker2']):
    job = N / 'acceptance/runs' / ('shared-native-pending-capture02-' + node)
    overlap = load(job / 'overlap-proof.json')
    br = load(job / 'barrier/terminal.json')
    request = load(job / 'capture-result.private.json')
    assert br['rc'] == 0 and br['role_crash_injected'] is False
    assert br['control_barrier_unix_ns'] <= request['started_unix_ns'] <= overlap['observed_unix_ns'] < br['reader_resumed_unix_ns'] <= request['returned_unix_ns']
    proofs.append({'execution_node': chr(65 + i), 'actual_input_fds': overlap['actual_input_fds'],
                   'reader_stopped': overlap['reader_stopped'], 'sdk_call_pending': overlap['sdk_call_pending'],
                   'same_reader_resumed': br['same_reader_resumed'], 'role_crash_injected': False,
                   'request_spanned_real_input_barrier': True, 'return_after_original_reader_resume': True})
save('overlap-proof.json', {'rc': 0, 'cases': proofs})
client_rows = []
for i, (key, before) in enumerate(pending['clients_before'].items()):
    after = pending['clients_after'][key]
    assert before['processes'] == after['processes']
    delta = {k: after['events'][k] - before['events'][k] for k in before['events']}
    assert delta['oom'] == 0 and delta['oom_kill'] == 0
    client_rows.append({'execution_node': 'A' if key.startswith('c94000a9') else 'B', 'same_client_processes_and_start_ticks': True,
                        'client_process_count': len(after['processes']), 'memory_event_delta': delta})
save('client-resources.json', {
    **selected(resize, ['rc', 'same_containers_without_restart', 'new_client_memory_limit_bytes',
        'cache_configuration_changed', 'template_changed', 'task_40GiB_limit_unchanged',
        'sandbox_limits_unchanged', 'independent_pods_only']),
    'daemonset_template_still_bytes': 2 * (1 << 30),
    'scope': 'two existing worker-node client Pods only; control-node client unchanged',
    'pending_capture_clients': client_rows})
failures = []
for label, path in [
    ('initial-pending-probe-before-capture-request', N / 'acceptance/runs/shared-native-pending-capture01-akcr119-20261022-worker/terminal.json'),
    ('first-rescue-file-stream-interruption', N / 'acceptance/runs/shared-native-pending-capture01-rescue/terminal.json'),
    ('second-rescue-no-longer-present-failed-record-precheck', N / 'acceptance/runs/shared-native-pending-capture02-rescue/terminal.json')]:
    value = load(path)
    assert value['rc'] == 1
    failures.append({'case': label, **selected(value, ['rc', 'error_type'])})
save('rescue-and-original-failures.json', {'original_failures_retained': failures,
    'third_rescue': selected(rescue, ['rc', 'failed_record_already_absent', 'failed_environment_retired_via_sdk',
        'original_snapshot_root_1MiB_verified', 'original_snapshot_full_1GiB_memory_verified',
        'later_checkpoint_reload_verified', 'resources_retired_via_sdk']),
    'causality_limit': 'client 2GiB OOM/worker replacement and failure are correlated; no isolated client-death acceptance yet'})
save('final-state.json', {'after_pending_capture': pending['final_state'],
                        'after_storage_faults': faults['final_state'],
                        'retained_directory_hashes_are_names_not_content': True})
paths = {
    'run-native-storage-faults01.py': D / 'native-storage-faults01-input/run-native-storage-faults01.py',
    'sdk-pending-capture01.py': D / 'native-pending-capture01-input/sdk-pending-capture01.py',
    'hold-reader-control01.py': D / 'native-pending-capture01-input/hold-reader-control01.py',
    'run-pending-capture01.py': D / 'native-pending-capture01-input/run-pending-capture01.py',
    'rescue-pending01.py': D / 'native-pending-capture02-input/rescue-pending01.py',
    'rescue-pending02.py': D / 'native-pending-capture02b-input/rescue-pending02.py',
    'rescue-pending03.py': D / 'native-pending-rescue03-input/rescue-pending03.py',
    'resize-owned-juicefs-pods01.py': D / 'owned-juicefs-resize01-input/resize-owned-juicefs-pods01.py',
    'sdk-pending-capture02.py': D / 'native-pending-capture02c-input/sdk-pending-capture02.py',
    'hold-reader-control02.py': D / 'native-pending-capture02c-input/hold-reader-control02.py',
    'run-pending-capture02.py': D / 'native-pending-capture02c-input/run-pending-capture02.py'}
scripts = [{'path': 'tools/pr119-pod-20261024/candidates/native-storage-faults/' + name,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for name, path in paths.items()]
for name in ['sdk-mount-shadow01.py', 'shadow-owned-shared-mount01.py', 'sdk-s3-pause01.py', 'pause-owned-rgw01.py']:
    scripts.append({'path': 'tools/pr119-pod-20261024/executed/storage/' + name,
                    'sha256': hashlib.sha256((D / 'storage' / name).read_bytes()).hexdigest(), 'reused_without_edits': True})
generated = O / 'generated'
generated.mkdir(mode=0o700)
for source, name in [(D / 'native-storage-faults01/final-state01.py', 'storage-faults-final-state01.py'),
                     (D / 'native-pending-capture02/final-state01.py', 'pending-capture-final-state01.py')]:
    data = source.read_bytes()
    (generated / name).write_bytes(data)
    scripts.append({'path': 'tools/pr119-pod-20261024/candidates/native-storage-faults/executed/' + name,
                    'sha256': hashlib.sha256(data).hexdigest(), 'generated_and_executed': True})
save('script-source-index.json', {'scripts': scripts, 'collector_is_metadata_only_and_listed_separately': True})
save('summary.json', {'rc': 0, 'accepted_storage_fault_cases': 4, 'accepted_pending_capture_directions': 2,
    'source_commits_unchanged': True, 'performance_not_included': True,
    'remaining': ['client-death and resource-failure recovery isolation', 'same-code three-group performance',
                  'remote read-only baseline plus local delta implementation and acceptance', 'physical-node HA']})
index = [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
         for p in sorted(E.iterdir()) if p.is_file()]
save('artifact-index.json', {'files': index})
archive = D / 'native-lifecycle-delivery01.tar.gz'
with tarfile.open(archive, 'w:gz') as tar:
    for p in sorted(O.rglob('*')):
        if p.is_file():
            tar.add(p, arcname=str(p.relative_to(O)), recursive=False)
print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size,
                  'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                  'evidence_files': len(list(E.iterdir())), 'script_count': len(scripts)}))
