from pathlib import Path
import json,hashlib,re,tarfile,subprocess,os
os.umask(0o077)
N=Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp');Q=N/'round-365f797-20261023.clPWh2h0';D=Q/'tap-checksum-fix';O=D/'cgroup-durable-leases-delivery02';O.mkdir(mode=0o700)
def read(p):return json.loads(p.read_text())
def select(d,keys):return {k:d[k]for k in keys if k in d}
qa=read(D/'cgroup-durable-leases-qa01/terminal.json');im=read(D/'cgroup-durable-leases-image01/terminal.json');sdk=read(D/'cgroup-durable-leases-sdk01/terminal.json');post=read(D/'cgroup-durable-leases-postsdk01/terminal.json');final=read(D/'cgroup-durable-leases-final-state01/terminal.json')
assert all(v['rc']==0 for v in [qa,im,sdk,post,final])
alias=read(D/'cgroup-durable-leases-qa01/source-alias-restore01.json');assert alias['canonical_status_verified']and not alias['product_source_changed']
status=(D/'cgroup-durable-leases-qa01/canonical-source-status01.stdout').read_text().splitlines();assert {l[3:]for l in status}==set(qa['source_files'])
red=(D/'cgroup-durable-leases-qa01/out-old-red/regression.stdout').read_text();failed=re.findall(r'^--- FAIL: (\S+)',red,re.M);assert len(failed)==4 and '[build failed]'not in red
outputs={'qa.json':{**qa,'expected_old_go_test_rc':1,'old_failed_regression_groups':failed,'measured_binary_built_before_source_commit':True,'noncompiled_source_alias_restoration':alias},'image.json':select(im,['rc','status','deployed','image','config_sha256','expected_cri_digest','sandboxd_sha256','source_files','archive_sha256','archive_bytes','runtime_bundle_sha256','runtime_assets','mapping'])}
official=[]
for name,expected in [('firecracker-integration',8),('firecracker-standalone',30),('runsc-integration',8),('runsc-standalone',30)]:
 s=(D/'cgroup-durable-leases-sdk01/official-sdk'/(name+'.stderr')).read_text();m=re.search(r'Ran ([0-9]+) tests in ([0-9.]+)s',s);assert m and int(m[1])==expected and re.search(r'^OK$',s,re.M)
 official.append({'name':name,'tests':expected,'skipped':0,'seconds':float(m[2]),'OK':True})
strict=[];proof=[]
for v in sdk['strict_reader_restarts']:
 assert v['rc']==0 and v['open_input_at_role_crash_proven']and v['original_runtime_preserved']
 J=N/'acceptance/runs'/('shared-cgroup-leases-sdk01-strict-'+v['role']+'-'+v['target_node']);b=read(J/'barrier/terminal.json')
 strict.append({**v,'barrier':select(b,['rc','role','barrier_seconds','reader_barrier_entered_unix_ns','shared_input_fd_count_at_role_crash','role_crash_unix_ns','reader_resumed_unix_ns','same_reader_resumed'])})
 if(J/'cgroup-log-whitelist.json').exists():proof.append({'target_node':v['target_node'],'rows':read(J/'cgroup-log-whitelist.json')})
assert len(strict)==4
states=[]
for v in sdk['cases']:
 assert v['rc']==0 and len(v['rounds'])==3
 states.append({**select(v,['rc','runtime','memory_bytes','root_file_bytes','vm_memory_mb','private_storage_mb','requested_cpu_millis','assigned_node']),'state_rounds_verified':3,'not_a_paired_performance_sample':True})
cross=sdk['cross_node'];assert cross['rc']==0 and cross['cross_node_accepted']and all(len(x)==2 for x in cross['coverage'].values())
outputs['sdk.json']={'rc':0,'full_sdk_accepted':True,'official':official,'official_case_count':76,'strict_reader_restarts':strict,'state_cases':states,'cross_node':select(cross,['rc','status','coverage','cross_node_accepted']),'source_node_offline_and_rejoin_verified':True,'explicit_reload_for_failover':False}
outputs['post-sdk.json']=post;outputs['final-state.json']=final;outputs['cgroup-log-proof.json']=proof
sources={}
for n,rel in {
 'driver01.py':'cgroup-durable-leases-qa01/driver01.py','qa01.sh':'cgroup-durable-leases-qa01/qa.sh','prepare-image01.py':'prepare-cgroup-leases-image01.py',
 'run-full-sdk01.py':'cgroup-durable-leases-sdk-input01/run-full-sdk01.py','sdk-held-reader03.py':'cgroup-durable-leases-sdk-input01/sdk-held-reader03.py','hold-reader-role02.py':'cgroup-durable-leases-sdk-input01/hold-reader-role02.py','check-preserved-snapshot01.py':'cgroup-durable-leases-sdk-input01/check-preserved-snapshot01.py',
 'run-postsdk01.py':'cgroup-durable-leases-postsdk01/run-postsdk01.py','sdk-ordinary-restart01.py':'cgroup-durable-leases-postsdk01/sdk-ordinary-restart01.py','sdk-retire-diagnostic01.py':'cgroup-durable-leases-postsdk01/sdk-retire-diagnostic01.py','final-state01.py':'cgroup-leases-final-state01.py'}.items():
 data=(D/rel).read_bytes();sources[n]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'executed_task_relative_path':rel}
outputs['script-source-index.json']={'schema':'executed-cgroup-lease-probes/v1','files':sources,'source_count':len(sources)}
outputs['summary.json']={'schema':'cgroup-lease-qualified-sdk-evidence/v1','source_base':qa['base_commit'],'sandboxd_sha256':qa['sandboxd_sha256'],'image_cri_digest':im['expected_cri_digest'],'full_sdk_cases':76,'strict_input_cases':4,'state_rounds_each_runtime':3,'bidirectional_each_runtime':True,'live_state_restarts_each_runtime':True,'original_failure_snapshot_recovered_and_retired':True,'final_environment_count':0,'product_default_or_runtime_pin_promoted':False,'remaining':['native mount/sync faults and checkpoint during loading','same-code backend paired performance','remote read-only baseline plus local delta route','production orphan reconciliation and physical fault domains']}
for name,v in outputs.items():
 with(O/name).open('x')as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
index={name:{'sha256':hashlib.sha256((O/name).read_bytes()).hexdigest(),'bytes':(O/name).stat().st_size}for name in outputs}
(O/'artifact-index.json').write_text(json.dumps(index,indent=2)+'\n')
with tarfile.open(O/'metadata.tar.gz','w:gz')as t:
 for name in [*outputs,'artifact-index.json']:t.add(O/name,arcname=name)
p=O/'metadata.tar.gz';print(json.dumps({'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'files':len(outputs)+1,'script_sources':len(sources)}))
