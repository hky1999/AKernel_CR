TEST_SOURCE = "package firecracker\n\nimport (\n \"crypto/sha256\"\n \"encoding/hex\"\n \"encoding/json\"\n \"fmt\"\n \"io\"\n \"os\"\n \"path/filepath\"\n \"strings\"\n \"syscall\"\n \"testing\"\n \"time\"\n)\nfunc TestJuiceFSActualCloneHelper(t *testing.T) {\n root := os.Getenv(\"AKCR_CLONE_ROOT\")\n nonce := os.Getenv(\"AKCR_CLONE_NONCE\")\n if filepath.Dir(root)!=\"/mnt/akernel-shared\" || filepath.Base(root)!=\"pr119-native-clone-\"+nonce || nonce==\"\" {t.Fatal(\"wrong owned root\")}\n info,err:=os.Lstat(root);if err!=nil || !info.IsDir() || info.Mode()&os.ModeSymlink!=0 {t.Fatal(\"root changed\",err)}\n var owner struct{Nonce string; Inode uint64}\n data,err:=os.ReadFile(filepath.Join(root,\"owner.json\"));if err!=nil{t.Fatal(err)}\n if err=json.Unmarshal(data,&owner);err!=nil{t.Fatal(err)}\n st:=info.Sys().(*syscall.Stat_t)\n var fs syscall.Statfs_t\n if err=syscall.Statfs(root,&fs);err!=nil || fs.Type!=0x65735546 || owner.Nonce!=nonce || owner.Inode!=st.Ino {t.Fatal(\"ownership or FUSE mismatch\",err)}\n src,dst:=filepath.Join(root,\"base\"),filepath.Join(root,\"go-actual-clone\")\n role:=os.Getenv(\"AKCR_CLONE_ROLE\")\n switch role {\n case \"copy\":\n  start:=time.Now()\n  reflinked,err:=cloneFileNoSync(src,dst)\n  if err!=nil {t.Fatal(err)}\n  copiedMS:=float64(time.Since(start).Nanoseconds())/1e6\n  f,err:=os.OpenFile(dst,os.O_RDWR,0);if err!=nil{t.Fatal(err)}\n  if err=f.Sync();err!=nil{f.Close();t.Fatal(err)};if err=f.Close();err!=nil{t.Fatal(err)}\n  a,err:=os.Stat(src);if err!=nil{t.Fatal(err)};b,err:=os.Stat(dst);if err!=nil{t.Fatal(err)}\n  if a.Size()!=67108864 || b.Size()!=a.Size() || os.SameFile(a,b) || reflinked {t.Fatal(\"unexpected size, alias, or FICLONE success\")}\n  if _,err=cloneFileNoSync(src,dst);err==nil {t.Fatal(\"existing destination accepted\")}\n  msg,_:=json.Marshal(map[string]any{\"role\":role,\"reflinked\":reflinked,\"logical_bytes\":b.Size(),\"helper_ms\":copiedMS,\"helper_plus_fsync_ms\":float64(time.Since(start).Nanoseconds())/1e6,\"exclusive_destination_rejected\":true})\n  fmt.Println(\"AKCR_GO_CLONE_RESULT \"+string(msg))\n case \"verify\":\n  for _,name:=range []string{\"base\",\"go-actual-clone\"} {\n   f,err:=os.Open(filepath.Join(root,name));if err!=nil{t.Fatal(err)};h:=sha256.New()\n   _,err=io.Copy(h,f);f.Close();if err!=nil{t.Fatal(err)}\n   if !strings.EqualFold(hex.EncodeToString(h.Sum(nil)),\"6e0722a16ae40d8fe00a54d43f600ec337f45868d7a2c5277c65b9caaa06a2fb\"){t.Fatal(\"full content differs\",name)}\n  }\n  fmt.Println(\"AKCR_GO_CLONE_RESULT {\\\"role\\\":\\\"verify\\\",\\\"full_hashes_equal\\\":true}\")\n default:t.Fatal(\"explicit role required\")\n }\n}\n"
import pathlib,json,subprocess,os,sys,time,hashlib,base64
os.umask(0o077)
N=pathlib.Path("/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp");Q=N/"round-365f797-20261023.clPWh2h0";D=Q/"tap-checksum-fix";S=D/"storage";O=S/"go-clone-helper01";O.mkdir(mode=0o700)
B=["python3",str(N/"cluster/namespace-lab07.py"),"run","--task",str(N),"--"]
PB=["/usr/bin/podman","--root",str(N/"image-build/graph"),"--runroot",str(N/"image-build/runroot"),"--tmpdir",str(N/"image-build/libpod-tmp"),"--cgroup-manager","cgroupfs"]
r={"rc":1,"scope":"exact existing cloneFileNoSync compiled separately with stdlib-only probe; not full runtime integration","steps":[],"runtime_artifacts_changed":False}
def run(name,args,timeout=180,inp=None):
 with (O/(name+".stdout")).open("xb")as so,(O/(name+".stderr")).open("xb")as se:p=subprocess.run(args,input=inp,stdout=so,stderr=se,timeout=timeout)
 r["steps"].append({"name":name,"rc":p.returncode});(O/"current.json").write_text(json.dumps(r,indent=2))
 if p.returncode:raise RuntimeError(name+" failed; preserve diagnostics")
 return (O/(name+".stdout")).read_text()
def rgw(name):
 code='import pathlib,subprocess,json;s=list(pathlib.Path("/run/ceph").glob("ceph-client.rgw.checkpoints.a.*.asok"));assert len(s)==1;p=subprocess.run(["ceph","--admin-daemon",str(s[0]),"perf","dump"],capture_output=True,text=True,timeout=15);p.check_returncode();v=json.loads(p.stdout);print(json.dumps({"instance":s[0].name,"counters":{k:x for k,x in v["rgw_op"].items()if isinstance(x,(int,float))}}))'
 return json.loads(run(name,B+["kubectl","-n","akernel-pr119-storage","exec","deployment/rook-ceph-rgw-checkpoints-a","-c","rgw","--","python3","-c",code]))
try:
 prev=json.loads((S/"native-clone-capability01/terminal.json").read_text())
 if prev.get("rc")!=0:raise RuntimeError("primitives not passed")
 root=prev["root"];nonce=prev["nonce"];node=prev["nodes"]["b"]
 sys.path.insert(0,str(Q/"acceptance/scripts"));from read_control_state import read_control_state
 if any(k.startswith("environment:")for k in read_control_state(N)[1]):raise RuntimeError("Environment not empty")
 if os.statvfs(N).f_bavail*os.statvfs(N).f_frsize<650*(1<<30):raise RuntimeError("disk reserve insufficient")
 p=json.loads(run("owned-node",B+["kubectl","-n","akernel","get","pod",node["pod"],"-o","json"]))
 if p["metadata"]["uid"]!=node["uid"]:raise RuntimeError("Node replaced")
 source=Q/"source/AKernel/src/sandboxd/pkg/runtime/firecracker/reflink.go";data=source.read_bytes()
 if hashlib.sha256(data).hexdigest()!="81d641cc729863f33e03f0f89866981cb8c0dbd837ef22239c112631c8654227":raise RuntimeError("helper source differs")
 (O/"reflink.go").write_bytes(data);(O/"clone_probe_test.go").write_bytes(TEST_SOURCE.encode())
 r["source_sha256"]=hashlib.sha256(data).hexdigest();r["probe_sha256"]=hashlib.sha256((O/"clone_probe_test.go").read_bytes()).hexdigest()
 run("remote-build",PB+["run","--rm","--name","akcr119-go-clone-helper01","--network","none","--cpus","2","--memory","2g","--pids-limit","1024","--cgroup-parent","/akernel-pr119-followup-20261022-qbGAw9tp","--cap-drop","ALL","--security-opt","no-new-privileges","--volume",str(O)+":/work:rw","--volume",str(S/"performance-observation01/gocache")+":/gocache:rw","--env","CGO_ENABLED=0","--env","GOMAXPROCS=2","--env","GOCACHE=/gocache","--env","GOFLAGS=-p=2","--env","GOPROXY=off","docker.io/library/golang:1.25.5-bookworm","bash","-ec","gofmt -w /work/clone_probe_test.go; go version; go test -c -o /work/clone-helper.test /work/reflink.go /work/clone_probe_test.go"],300)
 binary=(O/"clone-helper.test").read_bytes();r["binary_sha256"]=hashlib.sha256(binary).hexdigest()
 tasktmp="/tmp/pr119-go-clone-"+nonce
 create='import os,pathlib,sys;p=pathlib.Path(sys.argv[1]);p.mkdir(mode=0o700);f=os.open(p/"clone-helper.test",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o700);d=sys.stdin.buffer.read();assert len(d)=='+str(len(binary))+';assert os.write(f,d)==len(d);os.close(f)'
 run("install-owned-probe",B+["kubectl","-n","akernel","exec","-i",node["pod"],"--","python3","-c",create,tasktmp],inp=binary)
 def probe(role):
  out=run("actual-helper-"+role,B+["kubectl","-n","akernel","exec",node["pod"],"--","env","AKCR_CLONE_ROOT="+root,"AKCR_CLONE_NONCE="+nonce,"AKCR_CLONE_ROLE="+role,tasktmp+"/clone-helper.test","-test.v","-test.run","^TestJuiceFSActualCloneHelper$"])
  receipt=[x.split(" ",1)[1]for x in out.splitlines()if x.startswith("AKCR_GO_CLONE_RESULT ")]
  if len(receipt)!=1:raise RuntimeError("Go receipt missing")
  return json.loads(receipt[0])
 before=rgw("before-copy");r["copy"]=probe("copy");after=rgw("after-copy")
 if before["instance"]!=after["instance"]:raise RuntimeError("RGW epoch changed")
 delta={k:after["counters"][k]-x for k,x in before["counters"].items()};r["copy_rgw_delta"]=delta
 if any(delta[k]!=0 for k in ["put_obj_ops","put_obj_bytes","get_obj_ops","get_obj_bytes"]):raise AssertionError("object data transfer observed")
 r["verify"]=probe("verify")
 cleanup='import pathlib,hashlib,sys;p=pathlib.Path(sys.argv[1]);f=p/"clone-helper.test";assert not p.is_symlink();assert hashlib.sha256(f.read_bytes()).hexdigest()==sys.argv[2];f.unlink();p.rmdir()'
 run("remove-owned-probe",B+["kubectl","-n","akernel","exec",node["pod"],"--","python3","-c",cleanup,tasktmp,r["binary_sha256"]])
 r.update(rc=0,status="existing-go-helper-native-copy-and-full-content-passed",full_sdk_route_accepted=False,probe_binary_removed_from_node=True,primitive_files_still_retained=True)
except BaseException as e:r.update(error_type=type(e).__name__,error=str(e))
finally:(O/"terminal.json").write_text(json.dumps(r,indent=2))
sys.exit(r["rc"])
