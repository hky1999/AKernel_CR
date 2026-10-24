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
    assert v['final_profile'] == 'native-juicefs' and v['protocol']['pairs'] == 10
    assert len(v['cases']) == 20
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
        assert pair in range(1, 11) and backend in ['local-xfs', 'native-juicefs']
        assert (pair, backend) not in per_case
        assert d['rc'] == 0 and d['resources_deleted'] and len(d['rounds']) == 2
        assert d['io_probe_sha256'] == 'f11e2a32602ef80cadecb664086562f4367e92bd79a8df63c934088e8f13cc94'
        io = d['guest_io']
        assert io['readback_verified'] and io['bytes'] == 67108864 and len(io['random_sync_operations']) == 64
        assert len(d['backing_media']) == 4
        assert all(b['backend'] == backend and b['vmm_has_overlay_fd'] for b in d['backing_media'])
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
    for backend in ['local-xfs', 'native-juicefs']:
        groups[backend] = dict(per_instance={key:distribution([case_metrics[(pair,backend)][key] for pair in range(1,11)]) for key in case_metrics[(1,backend)]}, rounds={})
        for i in [0,1]:
            rows = [per_case[(pair,backend)]['rounds'][i] for pair in range(1,11)]
            metrics = {k:[r[k] for r in rows] for k in ['checkpoint_http_ms','sdk_reload_ms','first_verified_root_ms','full_memory_verified_ms','full_root_and_memory_verified_ms']}
            metrics['guest_max_schedule_gap_ms']=[r['checkpoint_guest_observer']['max_mono_gap_ns']/1e6 for r in rows]
            for stage in ['checkpoint_rgw_delta','reload_through_full_verification_rgw_delta']:
                for counter in ['put_obj_bytes','get_obj_bytes','put_obj_ops','get_obj_ops']:
                    metrics[stage+'__'+counter] = [r[stage][counter] for r in rows]
            for phase in ['snapshot','overlay','flush','total']:
                values=[]
                for r in rows:
                    records=[p for p in r['checkpoint_host_phases']['records'] if p['kind']=='checkpoint']
                    assert len(records)==1
                    values.append(records[0]['values_ms'][phase])
                metrics['host_checkpoint_'+phase+'_ms']=values
            groups[backend]['rounds'][str(i)]={key:distribution(vals) for key,vals in metrics.items()}
    for i in [0,1]:
        paired[str(i)] = {}
        for metric in ['checkpoint_http_ms','sdk_reload_ms','full_root_and_memory_verified_ms','guest_max_schedule_gap_ms']:
            values=[]
            for pair in range(1,11):
                def value(backend):
                    r=per_case[(pair,backend)]['rounds'][i]
                    return r['checkpoint_guest_observer']['max_mono_gap_ns']/1e6 if metric=='guest_max_schedule_gap_ms' else r[metric]
                local,native=value('local-xfs'),value('native-juicefs')
                values.append(dict(pair=pair,local=local,native=native,ratio_native_over_local=native/local,delta_native_minus_local=native-local))
            paired[str(i)][metric]=dict(ratio_native_over_local=distribution([q['ratio_native_over_local'] for q in values]),median_delta_native_minus_local=statistics.median(q['delta_native_minus_local'] for q in values),native_lower_count=sum(q['native']<q['local'] for q in values),pairs=values)
    result=dict(schema='akernel-fc-backend-paired-comparison/v1',rc=0,source_terminal_sha256=hashlib.sha256(raw).hexdigest(),product_source='fdb145cf51f340dc46ebea3713c342b4ec93b127',product_elf_sha256='debbf268d1b1a8d4a07b9ac02be7084c3fa53c7cf794f0b1887ec65f7ace313b',protocol=v['protocol'],instance_count=20,state_rounds=40,file_sha256=next(iter(hashes)),final_profile=v['final_profile'],scope=['同一产品字节；仅两个 FC 私有盘配置字段变化','两逻辑执行节点位于同一 BareMetal；每次 reload 在原逻辑节点，非跨物理主机性能','十对 AB/BA；两个节点按组交替，节点与先后顺序相关，不能分别估计这两个效应','每实例两轮相关状态；64 次 fsync 为实例内相关操作，按实例与配对统计','自然/温基础设施缓存，无宿主缓存清理；不表示全冷对象读取量','旧测量 fixture 与本轮试跑均不合并；未对 E2B/AgentEnv/Cube 做同条件复测'],groups=groups,paired=paired,cases=public)
    with a.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(dict(rc=0,instances=20,state_rounds=40,first_checkpoint={k:groups[k]['rounds']['0']['checkpoint_http_ms']['median'] for k in groups},second_checkpoint={k:groups[k]['rounds']['1']['checkpoint_http_ms']['median'] for k in groups}),ensure_ascii=False))


if __name__=='__main__':
    main()
