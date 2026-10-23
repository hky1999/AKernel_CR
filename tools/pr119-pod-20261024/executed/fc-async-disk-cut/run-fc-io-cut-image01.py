import pathlib,json,subprocess,os,sys,time,shutil,hashlib,tarfile
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";D=Q/"tap-checksum-fix";O=D/"fc-io-cut-image01";O.mkdir(mode=0o700)
B=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"]
PB=["/usr/bin/podman","--root",str(N/"image-build/graph"),"--runroot",str(N/"image-build/runroot"),"--tmpdir",str(N/"image-build/libpod-tmp"),"--cgroup-manager","cgroupfs"]
r={"rc":1,"deployed":False,"steps":[]}
def sha(p):
 h=hashlib.sha256()
 with p.open("rb")as f:
  for x in iter(lambda:f.read(8<<20),b""):h.update(x)
 return h.hexdigest()
def run(name,args,timeout=600,stdin=None):
 with (O/(name+".stdout")).open("xb")as so,(O/(name+".stderr")).open("xb")as se:p=subprocess.run(args,stdin=stdin,stdout=so,stderr=se,timeout=timeout)
 r["steps"].append({"name":name,"rc":p.returncode});(O/"current.json").write_text(json.dumps(r,indent=2))
 if p.returncode:raise RuntimeError(name+" failed; retain candidate and diagnostics")
 return (O/(name+".stdout")).read_bytes()
try:
 qa=json.loads((D/"fc-io-cut-fix02/terminal.json").read_text())
 if qa.get("rc")!=0:raise RuntimeError("source gates not passed")
 sys.path.insert(0,str(Q/"acceptance/scripts"));from read_control_state import read_control_state
 if any(k.startswith("environment:")for k in read_control_state(N)[1]):raise RuntimeError("active Environment before image preparation")
 if os.statvfs(N).f_bavail*os.statvfs(N).f_frsize<650*(1<<30):raise RuntimeError("disk reserve insufficient")
 source=D/"fc-io-cut-fix02/source"
 if any(sha(source/rel)!=digest for rel,digest in qa["source_files"].items()):raise RuntimeError("tested source changed")
 binary=D/"fc-io-cut-fix02/out/sandboxd"
 if sha(binary)!=qa["sandboxd_sha256"]:raise RuntimeError("candidate ELF changed")
 ctx=O/"context";ctx.mkdir(mode=0o700);shutil.copyfile(binary,ctx/"sandboxd");(ctx/"sandboxd").chmod(0o755)
 (ctx/"Dockerfile").write_text("FROM localhost/akernel-pr119:365f7971f895-tapoffload01\nCOPY --chmod=0755 sandboxd /usr/local/bin/sandboxd\nLABEL org.akernel.test.sandboxd.base=10312f28c9b3286545eb2e97070cdd08fe994cee org.akernel.test.sandboxd.patch=fc-async-disk-cut org.akernel.test.sandboxd.sha256="+qa["sandboxd_sha256"]+"\n")
 image="localhost/akernel-pr119:365f7971f895-io-cut01"
 run("build-candidate",PB+["build","--pull=never","--network=none","--cpu-period","100000","--cpu-quota","200000","--memory","2g","--cgroup-parent","/akernel-pr119-followup-20261022-qbGAw9tp","-t",image,"-f",str(ctx/"Dockerfile"),str(ctx)])
 meta=json.loads(run("inspect-candidate",PB+["image","inspect",image]))[0];config=meta["Id"].removeprefix("sha256:")
 archive=O/"io-cut-candidate.oci.tar";run("export-candidate",PB+["save","--format","oci-archive","-o",str(archive),image])
 nodes={"akcr119-20261022-control-plane":"309834713ae51c81b89d88111a2a0adaf345f9ec135d8d3938d20f4727023bfa","akcr119-20261022-worker":"c94000a9e103f344bd40e2fd1cce2bb4ee113766beadc63ae5e5f8c7b6a5b550","akcr119-20261022-worker2":"31814694e9fd4463d194bb5150fc2dec052131af18d726ca330e822345c0f017"}
 maps=[]
 for name,ident in nodes.items():
  info=json.loads(run("identity-"+name,B+["podman","inspect",name]))[0]
  if info["Id"]!=ident or not info["State"]["Running"]:raise RuntimeError("owned Kind identity changed")
  with archive.open("rb")as inp:run("import-"+name,B+["podman","exec","-i",ident,"ctr","-n","k8s.io","images","import","--all-platforms","--digests","-"],stdin=inp)
  table=run("image-table-"+name,B+["podman","exec",ident,"ctr","-n","k8s.io","images","ls"]).decode()
  lines=[line.split()for line in table.splitlines()if line.split()and line.split()[0]==image]
  if len(lines)!=1:raise RuntimeError("candidate image reference missing or ambiguous")
  target=lines[0][2]
  def content(digest,label):
   raw=run("content-"+name+"-"+label,B+["podman","exec",ident,"ctr","-n","k8s.io","content","get",digest])
   if "sha256:"+hashlib.sha256(raw).hexdigest()!=digest:raise RuntimeError("content hash does not match digest")
   return json.loads(raw)
  first=content(target,"target");chain=[target]
  if "manifests"in first:
   choices=[m for m in first["manifests"]if m.get("platform",{}).get("architecture")=="amd64"and m.get("platform",{}).get("os")=="linux"]
   if len(choices)!=1:raise RuntimeError("candidate platform manifest ambiguous")
   leaf=choices[0]["digest"];state=content(leaf,"linux-amd64");chain.append(leaf)
  else:state=first
  if state.get("config",{}).get("digest")!="sha256:"+config:raise RuntimeError("imported image config differs from candidate")
  maps.append({"node":name,"target_digest":target,"verified_chain":chain,"config_sha256":config})
 if len({x["target_digest"]for x in maps})!=1:raise RuntimeError("Kind imported target identities differ")
 r.update(rc=0,status="candidate-built-imported-not-deployed",image=image,config_sha256=config,expected_cri_digest=maps[0]["target_digest"],mapping=maps,archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,sandboxd_sha256=qa["sandboxd_sha256"],source_files=qa["source_files"])
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
finally:(O/"terminal.json").write_text(json.dumps(r,indent=2))
sys.exit(r["rc"])
