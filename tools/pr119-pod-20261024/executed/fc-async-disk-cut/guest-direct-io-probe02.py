#!/usr/bin/env python3
import ctypes,errno,hashlib,http.server,json,os,pathlib,statistics,sys,threading,time,urllib.request,uuid
ROOT=pathlib.Path("/pr119-async-io-contract");PORT=19095;BLOCK=4096;SLOTS=256
if sys.argv[1]!="hold":
 print(urllib.request.urlopen("http://127.0.0.1:"+str(PORT)+"/"+sys.argv[1],timeout=30).read().decode());sys.exit(0)
ROOT.mkdir(mode=0o700)
if not hasattr(os,"O_DIRECT"):raise RuntimeError("guest O_DIRECT unavailable")
fd=os.open(ROOT/"ring",os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_DIRECT|os.O_CLOEXEC,0o600)
os.ftruncate(fd,BLOCK*SLOTS);os.fsync(fd)
import fcntl
if not fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_DIRECT:raise RuntimeError("direct flag not retained")
lib=ctypes.CDLL(None,use_errno=True)
lib.posix_memalign.argtypes=[ctypes.POINTER(ctypes.c_void_p),ctypes.c_size_t,ctypes.c_size_t];lib.posix_memalign.restype=ctypes.c_int
for fn in ["pwrite","pread"]:
 call=getattr(lib,fn);call.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_longlong];call.restype=ctypes.c_ssize_t
wbuf=ctypes.c_void_p();rbuf=ctypes.c_void_p()
for ptr in [wbuf,rbuf]:
 rc=lib.posix_memalign(ctypes.byref(ptr),BLOCK,BLOCK)
 if rc:raise OSError(rc,"posix_memalign")
lock=threading.Lock();cookie=uuid.uuid4().hex;salt="parent";done=0;attempted=0;error=None;latencies=[];phase="starting"
def work():
 global done,attempted,error,phase
 try:
  while True:
   with lock:seq=done+1;current_salt=salt;attempted=seq;phase="pwrite"
   payload=hashlib.sha256((cookie+current_salt+str(seq)).encode()).digest()*(BLOCK//32)
   ctypes.memmove(wbuf,payload,BLOCK);offset=(seq%SLOTS)*BLOCK;start=time.monotonic_ns()
   if lib.pwrite(fd,wbuf,BLOCK,offset)!=BLOCK:raise OSError(ctypes.get_errno(),"direct pwrite")
   with lock:phase="fdatasync"
   os.fdatasync(fd)
   with lock:phase="pread"
   if lib.pread(fd,rbuf,BLOCK,offset)!=BLOCK:raise OSError(ctypes.get_errno(),"direct pread")
   actual=ctypes.string_at(rbuf,BLOCK)
   if actual!=payload:raise AssertionError("direct readback differs from completed write: sequence="+str(seq))
   elapsed=time.monotonic_ns()-start
   with lock:
    done=seq;phase="between-operations";latencies.append(elapsed/1e6)
    if len(latencies)>2048:latencies.pop(0)
 except BaseException as e:
  with lock:error={"type":type(e).__name__,"message":str(e)};phase="error"
threading.Thread(target=work,daemon=True).start()
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  global salt
  with lock:
   if self.path.startswith("/branch/"):
    new=self.path.split("/")[-1]
    if new not in ["parent","child"]:self.send_error(400);return
    salt=new
   body={"pid":os.getpid(),"cookie":cookie,"salt":salt,"completed":done,"attempted":attempted,"phase":phase,"error":error,"direct_flag":bool(fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_DIRECT),"block_bytes":BLOCK,"file_bytes":BLOCK*SLOTS,"recent_latency_samples":len(latencies),"recent_p50_ms":statistics.median(latencies)if latencies else None,"recent_max_ms":max(latencies)if latencies else None}
  self.send_response(200);self.end_headers();self.wfile.write(json.dumps(body).encode())
http.server.ThreadingHTTPServer(("127.0.0.1",PORT),Handler).serve_forever()
