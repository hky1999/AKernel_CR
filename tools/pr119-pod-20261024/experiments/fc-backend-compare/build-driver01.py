from pathlib import Path
import json,subprocess,hashlib
N=Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp');D=N/'round-365f797-20261023.clPWh2h0/tap-checksum-fix';O=D/'fc-backend-io-build01'
r={'rc':1,'status':'building-guest-benchmark-only'}
try:
 PB=['/usr/bin/podman','--root',str(N/'image-build/graph'),'--runroot',str(N/'image-build/runroot'),'--tmpdir',str(N/'image-build/libpod-tmp'),'--cgroup-manager','cgroupfs']
 cmd=PB+['run','--rm','--name','akcr119-fc-backend-io-build01','--cgroupns','private','--network','none','--cpus','2','--memory','2g','--pids-limit','512','--cgroup-parent','/akernel-pr119-followup-20261022-qbGAw9tp','--volume',str(O/'source')+':/src:rw','--volume',str(O/'out')+':/out:rw','--volume',str(O/'qa.sh')+':/qa.sh:ro','--volume',str(D/'modcache')+':/gomodcache:rw','--volume',str(D/'gocache')+':/gocache:rw','docker.io/library/golang:1.25.5-bookworm','bash','/qa.sh']
 with (O/'build.stdout').open('x')as so,(O/'build.stderr').open('x')as se:p=subprocess.run(cmd,stdout=so,stderr=se,timeout=600)
 if p.returncode:raise RuntimeError('isolated probe build failed')
 cases=[]
 for suffix in ['a','b']:
  data=json.loads((O/('out/smoke-'+suffix+'.json')).read_text())
  assert data['readback_verified']and data['bytes']==65536 and data['block_bytes']==4096 and len(data['random_sync_operations'])==4
  assert hashlib.sha256((O/('out/smoke-'+suffix)).read_bytes()).hexdigest()==data['file_sha256_after']
  assert data['sequential_total_ns']>=data['sequential_write_ns']+data['sequential_file_sync_ns']
  assert all(o['offset']%4096==0 and 0<=o['offset']<=65536-4096 and o['total_ns']>=o['write_ns']+o['sync_ns']for o in data['random_sync_operations'])
  cases.append(data)
 assert cases[0]['file_sha256_after']==cases[1]['file_sha256_after']
 assert [o['offset']for o in cases[0]['random_sync_operations']]==[o['offset']for o in cases[1]['random_sync_operations']]
 r.update(rc=0,status='guest-probe-built-and-independent-sha-clock-shape-verified-not-sdk',source_sha256=hashlib.sha256((O/'source/guest-storage-io.go').read_bytes()).hexdigest(),elf_sha256=hashlib.sha256((O/'out/guest-storage-io').read_bytes()).hexdigest(),smoke_bytes=65536,smoke_ops=4,matching_seed_sha=cases[0]['file_sha256_after'])
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
(O/'terminal.json').write_text(json.dumps(r,indent=2))
