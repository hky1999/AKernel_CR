from pathlib import Path
import subprocess,json,hashlib,os
O=Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp/round-365f797-20261023.clPWh2h0/tap-checksum-fix/cgroup-durable-leases-qa01');S=O/'source'
target=subprocess.check_output(['git','-C',str(S),'show','HEAD:CLAUDE.md'],text=True).strip()
assert target=='AGENTS.md'
p=S/'CLAUDE.md';assert p.is_file()and not p.is_symlink()and p.read_bytes()==(S/target).read_bytes()
content=p.read_bytes();record={'scope':'noncompiled instruction alias only','original_status':'T CLAUDE.md','git_target':target,'content_equals_target':True,'content_sha256':hashlib.sha256(content).hexdigest(),'cause':'shutil.copytree followed source symlink','product_source_changed':False,'binary_rebuilt':False}
with(O/'claude-copy-before-alias-restore.private.md').open('xb')as f:f.write(content)
p.unlink();p.symlink_to(target)
raw=subprocess.check_output(['git','-C',str(S),'status','--porcelain','--untracked-files=all'],text=True)
q=json.loads((O/'terminal.json').read_text());assert {l[3:]for l in raw.splitlines()}==set(q['source_files'])
for n,h in q['source_files'].items():assert hashlib.sha256((S/n).read_bytes()).hexdigest()==h
record['canonical_status_verified']=True
(O/'source-alias-restore01.json').write_text(json.dumps(record,indent=2));(O/'canonical-source-status01.stdout').write_text(raw);print(json.dumps(record))
