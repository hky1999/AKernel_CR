import os,pathlib,json,stat,hashlib,random,fcntl,time,mmap,re,ctypes,shutil,sys
os.umask(0o077)
root=pathlib.Path(sys.argv[1]);nonce=sys.argv[2];role=sys.argv[3];SIZE=64<<20;SEED=0x11920261024
if root.parent!=pathlib.Path("/mnt/akernel-shared") or not root.name.startswith("pr119-native-clone-") or root.name!=("pr119-native-clone-"+nonce):raise RuntimeError("wrong owned path")
def fdinfo(fd):
 mid=int(next(x.split()[1]for x in pathlib.Path("/proc/self/fdinfo",str(fd)).read_text().splitlines()if x.startswith("mnt_id:")))
 line=next(x for x in pathlib.Path("/proc/self/mountinfo").read_text().splitlines()if int(x.split()[0])==mid)
 v=os.fstat(fd);return {"mount_id":mid,"fstype":line.split(" - ")[1].split()[0],"dev":v.st_dev,"inode":v.st_ino,"size":v.st_size,"nlink":v.st_nlink}
def check_root():
 if root.is_symlink() or root.resolve()!=root:raise RuntimeError("owned root changed")
 fd=os.open(root,os.O_PATH|os.O_DIRECTORY)
 try:v=fdinfo(fd)
 finally:os.close(fd)
 if v["fstype"]!="fuse.juicefs":raise RuntimeError("not a real JuiceFS mount")
 return v
def original():return random.Random(SEED).randbytes(SIZE)
def expected(edits=()):
 data=bytearray(original())
 for off,value in edits:data[off:off+len(value)]=value
 return hashlib.sha256(data).hexdigest()
def digest(name):
 h=hashlib.sha256()
 with (root/name).open("rb")as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def assert_digest(name,want):
 if digest(name)!=want:raise AssertionError("data differs: "+name)
def copyfd(src,dst_name):
 dst=os.open(root/dst_name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  a=fdinfo(src);b=fdinfo(dst)
  if a["fstype"]!="fuse.juicefs" or a["mount_id"]!=b["mount_id"] or a["dev"]!=b["dev"] or a["inode"]==b["inode"]:raise RuntimeError("copy crosses mount or aliases source")
  start=time.monotonic_ns();offset=0;calls=0
  while offset<a["size"]:
   count=os.copy_file_range(src,dst,a["size"]-offset,offset_src=offset,offset_dst=offset);calls+=1
   if count<=0:raise RuntimeError("short copy_file_range")
   offset+=count
  os.fsync(dst)
  if os.fstat(dst).st_size!=a["size"]:raise AssertionError("destination size differs")
  return {"copied_logical_bytes":offset,"copy_calls":calls,"copy_and_fsync_ms":(time.monotonic_ns()-start)/1e6,"source":a,"destination":fdinfo(dst)}
 finally:os.close(dst)
def clone(src_name,dst_name):
 fd=os.open(root/src_name,os.O_RDONLY|os.O_NOFOLLOW)
 try:return copyfd(fd,dst_name)
 finally:os.close(fd)
def patch(name,off,value):
 fd=os.open(root/name,os.O_RDWR|os.O_NOFOLLOW)
 try:
  if os.pwrite(fd,value,off)!=len(value):raise RuntimeError("short write")
  os.fsync(fd)
 finally:os.close(fd)
if role=="init":
 root.mkdir(mode=0o700);identity=check_root()
 with (root/"owner.json").open("x")as f:json.dump({"nonce":nonce,"inode":identity["inode"]},f);f.flush();os.fsync(f.fileno())
 data=original()
 with (root/"base").open("xb")as f:f.write(data);f.flush();os.fsync(f.fileno())
 result={"role":role,"root":identity,"base_sha256":hashlib.sha256(data).hexdigest(),"bytes":SIZE}
else:
 own=json.loads((root/"owner.json").read_text());identity=check_root()
 if own["nonce"]!=nonce or own["inode"]!=identity["inode"]:raise RuntimeError("owned directory identity differs")
 if role=="preflight":result={"role":role,"root":identity,"base_size":(root/"base").stat().st_size}
 elif role=="cold-clone":
  src=os.open(root/"base",os.O_RDONLY|os.O_NOFOLLOW);dst=os.open(root/"ficlone-probe",os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
  try:
   try:fcntl.ioctl(dst,0x40049409,src);fic={"supported":True}
   except OSError as e:fic={"supported":False,"errno":e.errno}
  finally:os.close(dst);os.close(src);(root/"ficlone-probe").unlink()
  result={"role":role,"ficlone":fic,"copy_file_range":clone("base","child-b")}
 elif role=="branch-b":
  assert_digest("child-b",expected());off=(1<<20)-4096;p1=b"B"*8192
  patch("child-b",off,p1);snap=clone("child-b","snapshot-b1")
  off2=(3<<20)-2048;p2=b"D"*8192;patch("child-b",off2,p2)
  assert_digest("snapshot-b1",expected([(off,p1)]));assert_digest("child-b",expected([(off,p1),(off2,p2)]))
  result={"role":role,"next_snapshot":snap,"first_snapshot_immutable":True}
 elif role=="branch-a":
  ownclone=clone("base","child-a");off=(2<<20)-4096;pa=b"A"*8192;patch("child-a",off,pa)
  restored=clone("snapshot-b1","restored-next-a")
  assert_digest("restored-next-a",expected([((1<<20)-4096,b"B"*8192)]));assert_digest("child-a",expected([(off,pa)]));assert_digest("base",expected())
  result={"role":role,"own_clone":ownclone,"second_generation_restore":restored,"cross_client_branch_isolation":True,"parent_unchanged":True}
 elif role=="anonymous":
  clone("snapshot-b1","anonymous-source");fd=os.open(root/"anonymous-source",os.O_RDWR)
  try:
   (root/"anonymous-source").unlink()
   if os.fstat(fd).st_nlink!=0:raise RuntimeError("source is still named")
   copied=copyfd(fd,"anonymous-snapshot")
  finally:os.close(fd)
  assert_digest("anonymous-snapshot",expected([((1<<20)-4096,b"B"*8192)]))
  result={"role":role,"unnamed_open_fd_copy":copied,"state_verified":True}
 elif role=="mmap":
  clone("base","mmap-source");fd=os.open(root/"mmap-source",os.O_RDWR);off=(4<<20)-4096
  try:
   mm=mmap.mmap(fd,0,access=mmap.ACCESS_WRITE)
   try:
    mm[off:off+8192]=b"M"*8192
    active=False;dirty=0
    for line in pathlib.Path("/proc/self/smaps").read_text().splitlines():
     if re.match(r"^[0-9a-f]+-[0-9a-f]+ ",line):active=str(root/"mmap-source")in line
     elif active and (line.startswith("Private_Dirty:")or line.startswith("Shared_Dirty:")):dirty+=int(line.split()[1])
    if dirty<8:raise AssertionError("no proof of unflushed mapped pages")
    copied=copyfd(fd,"mmap-snapshot")
    mm[off:off+8192]=b"N"*8192;mm.flush();os.fsync(fd)
   finally:mm.close()
  finally:os.close(fd)
  assert_digest("mmap-snapshot",expected([(off,b"M"*8192)]));assert_digest("mmap-source",expected([(off,b"N"*8192)]))
  result={"role":role,"unflushed_map_dirty_kib":dirty,"copy":copied,"saved_state_and_later_writes_isolated":True}
 elif role=="truncate-hole":
  clone("base","truncated");fd=os.open(root/"truncated",os.O_RDWR)
  try:os.ftruncate(fd,SIZE//2);os.ftruncate(fd,SIZE);os.fsync(fd)
  finally:os.close(fd)
  want=hashlib.sha256(original()[:SIZE//2]+bytes(SIZE//2)).hexdigest();clone("truncated","truncated-snapshot");assert_digest("truncated-snapshot",want)
  clone("base","punched");fd=os.open(root/"punched",os.O_RDWR);lib=ctypes.CDLL(None,use_errno=True);fn=lib.fallocate;fn.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_longlong,ctypes.c_longlong];fn.restype=ctypes.c_int
  try:
   rc=fn(fd,3,8<<20,1<<20)
   if rc:hole={"supported":False,"errno":ctypes.get_errno()}
   else:os.fsync(fd);hole={"supported":True}
  finally:os.close(fd)
  if hole["supported"]:assert_digest("punched",expected([(8<<20,bytes(1<<20))]))
  assert_digest("base",expected());result={"role":role,"truncate_expand_zeroes_preserved":True,"punch_hole":hole,"parent_unchanged":True}
 elif role=="cleanup":
  shutil.rmtree(root);result={"role":role,"owned_directory_removed":not root.exists()}
 else:raise RuntimeError("unknown role")
print("AKCR_CFR_RESULT "+json.dumps(result))
