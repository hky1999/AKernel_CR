#!/usr/bin/env python3
"""只读提取白名单字段；不导出原始配置、身份记录或服务日志。"""
import argparse
import json
from pathlib import Path
import re


def select(value, keys):
    return {k: value[k] for k in keys if k in value}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--round-dir', type=Path, required=True)
    args = parser.parse_args()
    root = args.round_dir.resolve() / 'tap-checksum-fix'
    sdk = root / 'native-rwfs-rejoin-sdk02'
    reports = {}
    main_keys = ['rc', 'status', 'full_sdk_accepted', 'deployed', 'candidate', 'expected_cri_digest', 'sandboxd_sha256', 'memory_placement', 'temporary_bootstrap_removed', 'error_type']
    terminal = sdk / 'terminal.json'
    if not terminal.exists():
        raise RuntimeError('SDK has no terminal receipt; refuse a final report')
    value = json.loads(terminal.read_text())
    reports['native-rwfs-rejoin-sdk02'] = select(value, main_keys)
    suites = []
    for path in sorted((sdk / 'official-sdk').glob('*.stderr')):
        data = path.read_text(errors='replace')
        match = re.search(r'^Ran (\d+) tests? in ([\d.]+)s$', data, re.M)
        ok = re.search(r'^OK(?: \(skipped=(\d+)\))?$', data, re.M)
        if not match or not ok:
            raise RuntimeError('official suite lacks a successful terminal summary: ' + path.name)
        suites.append(dict(suite=path.stem, passed=int(match[1]), seconds=float(match[2]), skipped=int(ok[1] or 0)))
    reports['native-rwfs-rejoin-sdk02']['official_sdk'] = suites
    case_keys = ['rc', 'variant', 'runtime', 'scope', 'samples_are_exploratory', 'sdk_versions', 'create_ms', 'create_rgw_delta', 'observer_sha256', 'root_write_fsync_ms', 'memory_bytes', 'root_file_bytes', 'vm_memory_mb', 'private_storage_mb', 'requested_cpu_millis', 'assigned_node', 'prepare_rgw_delta', 'lifetime_rgw_delta', 'resources_deleted']
    round_keys = ['round', 'checkpoint_http_ms', 'checkpoint_outer_command_ms', 'sdk_reload_ms', 'first_verified_root_ms', 'full_memory_verified_ms', 'full_root_and_memory_verified_ms', 'idle_guest_observer', 'checkpoint_guest_observer', 'checkpoint_rgw_delta', 'reload_through_full_verification_rgw_delta', 'checkpoint_host_phases', 'restore_host_phases', 'state_verified']
    cases = []
    for case in value.get('cases', []):
        clean = select(case, case_keys)
        clean['rounds'] = [select(row, round_keys) for row in case['rounds']]
        cases.append(clean)
    reports['native-rwfs-rejoin-sdk02']['cases'] = cases
    reports['native-rwfs-rejoin-sdk02']['scope'] = '同物理机逻辑双节点；每运行时一实例三轮，不是交替后端性能结论；普通写入计时包含 SDK 写入与 guest sync'
    cross = sdk / 'cross-node01/terminal.json'
    if cross.exists():
        reports['native-rwfs-rejoin-cross02'] = select(json.loads(cross.read_text()), ['rc', 'status', 'coverage', 'attempts', 'cross_node_accepted', 'error_type'])
    for name in ['native-rwfs-rejoin-directio02', 'native-rwfs-rejoin-postsdk02']:
        path = root / name / 'terminal.json'
        if not path.exists():
            continue
        value = json.loads(path.read_text())
        report = select(value, ['rc', 'status', 'sdk_job_started', 'error_type'])
        if isinstance(value.get('data'), dict):
            report['data'] = select(value['data'], ['rc', 'status', 'scope', 'runtime', 'cross_node_branch', 'checkpoint_operations', 'reload_operations', 'resources_deleted'])
        if isinstance(value.get('restart'), dict):
            report['restart'] = {runtime: select(result, ['rc', 'status', 'runtime', 'restart', 'diagnostic_not_performance', 'gc_delete_race_tested', 'fault_mode', 'old_checkpoint_reader_observed', 'protected_artifact_count']) for runtime, result in value['restart'].items()}
        reports[name] = report
    print(json.dumps(reports, ensure_ascii=False))


if __name__ == '__main__':
    main()
