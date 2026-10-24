#!/usr/bin/env python3
"""仅在远端分析已完成的同代码后端对照，输出白名单原始样本与配对统计。"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics


def distribution(values):
    assert values and all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in values)
    values = sorted(values)
    quartiles = statistics.quantiles(values, n=4, method='inclusive') if len(values) > 1 else [values[0]] * 3
    return dict(n=len(values), median=statistics.median(values), q1=quartiles[0], q3=quartiles[2], minimum=values[0], maximum=values[-1])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--terminal', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    raw = a.terminal.read_bytes()
    v = json.loads(raw)
    assert v['rc'] == 0 and v['status'] == 'same-code-backend-comparison-passed-final-native'
    assert v['final_profile'] == 'clone-native-juicefs' and v['protocol']['pairs'] == 10
    assert len(v['cases']) == 30
    assert v['protocol']['source_code_unchanged'] == 'sandboxd91dff2f/gvisor218d85378'
    assert v['protocol']['elf'] == '433574033952b1ad9106b125e085302b9c5268fea179609975de7d722c2f6c83'
    public = []
    per_case = {}
    hashes = set()
    observed_nodes = sorted({c['node'] for c in v['cases']})
    assert len(observed_nodes) == 2
    allowed = ['rc', 'runtime', 'variant', 'scope', 'samples_are_exploratory', 'sdk_versions', 'create_ms', 'create_clock_scope', 'create_rgw_delta', 'io_probe_sha256', 'observer_sha256', 'io_probe_command_ms', 'guest_io', 'root_write_fsync_ms', 'root_write_fsync_scope', 'memory_bytes', 'root_file_bytes', 'vm_memory_mb', 'private_storage_mb', 'requested_cpu_millis', 'prepare_rgw_delta', 'backing_media', 'rounds', 'lifetime_rgw_delta', 'resources_deleted']
    case_metrics = {}
    for c in v['cases']:
        d = c['data']
        pair, backend = c['pair'], c['backend']
        assert pair in range(1, 11) and backend in ['full-local-xfs', 'full-native-juicefs', 'clone-native-juicefs']
        assert (pair, backend) not in per_case
        assert d['rc'] == 0 and d['resources_deleted'] and len(d['rounds']) == 2 and d['runtime'] == 'runsc'
        assert d['io_probe_sha256'] == 'f11e2a32602ef80cadecb664086562f4367e92bd79a8df63c934088e8f13cc94'
        io = d['guest_io']
        assert io['readback_verified'] and io['bytes'] == 67108864 and len(io['random_sync_operations']) == 64
        assert len(d['backing_media']) == 4
        assert all(b['backend'] == backend and b['private_medium_verified'] and b['actual_private_rwfs_fds'] for b in d['backing_media'])
        assert all(r['round'] == i and r['state_verified'] for i, r in enumerate(d['rounds']))
        hashes.add(io['file_sha256_after'])
        per_case[(pair, backend)] = d
        public.append(dict(pair=pair, position=c['position'], backend=backend, execution_node=chr(65 + observed_nodes.index(c['node'])), data={k:d[k] for k in allowed}))
        case_metrics[(pair, backend)] = dict(
            sdk_create_ms=d['create_ms'],
            guest_sequential_write_ms=io['sequential_write_ns']/1e6,
            guest_sequential_file_sync_ms=io['sequential_file_sync_ns']/1e6,
            guest_sequential_directory_sync_ms=io['sequential_directory_sync_ns']/1e6,
            guest_sequential_total_ms=io['sequential_total_ns']/1e6,
            guest_random_4k_write_sync_instance_median_ms=statistics.median(o['total_ns']/1e6 for o in io['random_sync_operations']),
            guest_random_4k_write_sync_instance_max_ms=max(o['total_ns']/1e6 for o in io['random_sync_operations']),
            preparation_rgw_put_bytes=d['prepare_rgw_delta']['put_obj_bytes'],
            lifetime_rgw_put_bytes=d['lifetime_rgw_delta']['put_obj_bytes'])
    assert len(hashes) == 1
    groups, paired = {}, {}
    for backend in ['full-local-xfs', 'full-native-juicefs', 'clone-native-juicefs']:
        groups[backend] = dict(per_instance={key:distribution([case_metrics[(pair,backend)][key] for pair in range(1,11)]) for key in case_metrics[(1,backend)]}, rounds={})
        for i in [0,1]:
            rows = [per_case[(pair,backend)]['rounds'][i] for pair in range(1,11)]
            metrics = {k:[r[k] for r in rows] for k in ['checkpoint_http_ms','sdk_reload_ms','first_verified_root_ms','full_memory_verified_ms','full_root_and_memory_verified_ms']}
            metrics['guest_max_schedule_gap_ms']=[r['checkpoint_guest_observer']['max_mono_gap_ns']/1e6 for r in rows]
            for stage in ['checkpoint_rgw_delta','reload_through_full_verification_rgw_delta']:
                for counter in ['put_obj_bytes','get_obj_bytes','put_obj_ops','get_obj_ops']:
                    metrics[stage+'__'+counter] = [r[stage][counter] for r in rows]
            groups[backend]['rounds'][str(i)]={key:distribution(vals) for key,vals in metrics.items()}
    comparisons = [('native_full_over_local_full', 'full-local-xfs', 'full-native-juicefs'),
                   ('clone_over_native_full', 'full-native-juicefs', 'clone-native-juicefs'),
                   ('clone_over_local_full', 'full-local-xfs', 'clone-native-juicefs')]
    for i in [0,1]:
        paired[str(i)] = {}
        for label, baseline, candidate in comparisons:
            paired[str(i)][label] = {}
            for metric in ['checkpoint_http_ms', 'sdk_reload_ms', 'first_verified_root_ms', 'full_root_and_memory_verified_ms', 'guest_max_schedule_gap_ms']:
                values=[]
                for pair in range(1,11):
                    def value(backend):
                        r=per_case[(pair,backend)]['rounds'][i]
                        return r['checkpoint_guest_observer']['max_mono_gap_ns']/1e6 if metric=='guest_max_schedule_gap_ms' else r[metric]
                    old,new=value(baseline),value(candidate)
                    assert old>0 and new>=0
                    values.append(dict(group=pair,baseline=old,candidate=new,ratio_candidate_over_baseline=new/old,delta_candidate_minus_baseline=new-old))
                paired[str(i)][label][metric]=dict(ratio_candidate_over_baseline=distribution([q['ratio_candidate_over_baseline'] for q in values]),median_delta_candidate_minus_baseline=statistics.median(q['delta_candidate_minus_baseline'] for q in values),candidate_lower_count=sum(q['candidate']<q['baseline'] for q in values),pairs=values)
    result=dict(schema='akernel-gvisor-three-group-comparison/v1',rc=0,source_terminal_sha256=hashlib.sha256(raw).hexdigest(),product_source='91dff2f686d4f3f18540d33c0851b127212d8567',gvisor_source='218d85378357f9726fc3c0f7cf878cf19772d360',product_elf_sha256='433574033952b1ad9106b125e085302b9c5268fea179609975de7d722c2f6c83',protocol=v['protocol'],instance_count=30,state_rounds=60,file_sha256=next(iter(hashes)),final_profile=v['final_profile'],scope=['同一产品字节；A=本地XFS/full、B=JuiceFS/full、C=JuiceFS/clone，A/B分介质、B/C分保存格式', '应用内存后台恢复开关与2GiB沙箱配置相同；未改成内存增量保存', '两逻辑节点同一BareMetal，reload在原逻辑节点，不代表跨物理机/对象全冷性能', '每组内相同逻辑节点，六种顺序轮换十组；先后与节点因素未独立随机化', '每实例两轮相关状态，64次小块同步先按实例取中位数，n=10独立实例/配置/轮次', '自然基础设施缓存，客户端实际4GiB，缓存配置不变；不与历史2GiB客户端样本合并', 'gVisor客体fsync不等同宿主JuiceFS远端持久化，checkpoint最终同步另计', '未同条件复测E2B/AgentEnv/Cube；不含尚未实现的远端只读基线＋本地差异'],groups=groups,paired=paired,cases=public,clients_before=v['clients_before'],clients_after=v['clients_after'])
    with a.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(dict(rc=0,instances=30,state_rounds=60,first_checkpoint={k:groups[k]['rounds']['0']['checkpoint_http_ms']['median'] for k in groups},second_checkpoint={k:groups[k]['rounds']['1']['checkpoint_http_ms']['median'] for k in groups}),ensure_ascii=False))


if __name__=='__main__':
    main()
