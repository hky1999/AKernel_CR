#!/usr/bin/env python3
import hashlib,http.server,json,mmap,os,pathlib,sys,threading,urllib.request,uuid
ROOT=pathlib.Path("/pr119-rwfs-contract")
PORT=19094
def digest_file(f):
 p=f.tell();f.seek(0);h=hashlib.sha256()
 while True:
  b=f.read(1<<20)
  if not b:break
  h.update(b)
 f.seek(p);return h.hexdigest()
def main():
 if sys.argv[1]!="hold":
  print(urllib.request.urlopen("http://127.0.0.1:"+str(PORT)+"/"+sys.argv[1],timeout=90).read().decode());return
 ROOT.mkdir(mode=0o700)
 token=uuid.uuid4().hex
 block=b"".join(hashlib.sha256(str(i).encode()).digest() for i in range(2048))
 with (ROOT/"large").open("wb") as f:
  for _ in range(1024):f.write(block)
  f.flush();os.fsync(f.fileno())
 with (ROOT/"sparse").open("wb") as f:
  f.truncate(128<<20);f.seek(0);f.write(b"prefix");f.seek((128<<20)-6);f.write(b"suffix");f.flush();os.fsync(f.fileno())
 (ROOT/"truncated").write_bytes(block*16)
 (ROOT/"append").write_bytes(b"initial")
 (ROOT/"mapped").write_bytes(block*64)
 mf=(ROOT/"mapped").open("r+b",buffering=0);mm=mmap.mmap(mf.fileno(),0)
 tag0=b"unflushed-before-checkpoint";mm[4090:4090+len(tag0)]=tag0
 # Length guard: slice lengths are derived from bytes, not guessed.
 uf=(ROOT/"unlinked").open("w+b",buffering=0);uf.write(block*16);os.unlink(ROOT/"unlinked")
 (ROOT/"renamed").write_bytes(b"opened-before-rename");rf=(ROOT/"renamed").open("r+b",buffering=0);os.rename(ROOT/"renamed",ROOT/"renamed-live")
 os.link(ROOT/"large",ROOT/"large-hardlink");os.symlink("large",ROOT/"large-symlink")
 generation=0;lock=threading.Lock()
 def state():
  rows={}
  for p in sorted(ROOT.iterdir()):
   if p.is_symlink():rows[p.name]={"symlink":os.readlink(p)};continue
   with p.open("rb") as f:sha=digest_file(f)
   st=p.stat();rows[p.name]={"bytes":st.st_size,"sha256":sha,"mode":st.st_mode&0o7777,"nlink":st.st_nlink}
  return {"pid":os.getpid(),"token":token,"generation":generation,"files":rows,"unlinked_fd_sha256":digest_file(uf),"renamed_fd_sha256":digest_file(rf),"mmap_sha256":hashlib.sha256(mm).hexdigest()}
 def mutate():
  nonlocal generation
  generation+=1;tag=("generation-%d"%generation).encode()
  with (ROOT/"large").open("r+b",buffering=0) as f:
   f.seek(65530);f.write(tag*1000);f.flush();os.fsync(f.fileno())
  with (ROOT/"truncated").open("r+b",buffering=0) as f:
   f.truncate((1<<20)+37);f.truncate((2<<20)+11);f.seek((2<<20)-24);f.write(tag);f.flush();os.fsync(f.fileno())
  with (ROOT/"append").open("ab",buffering=0) as f:f.write(tag*1024);os.fsync(f.fileno())
  with (ROOT/"sparse").open("r+b",buffering=0) as f:
   f.seek((64<<20)-5);f.write(tag*20);os.fsync(f.fileno())
  uf.seek(13);uf.write(tag*100);os.fsync(uf.fileno())
  (ROOT/"unlinked").write_bytes(b"new-path-distinct-from-open-fd:"+tag)
  rf.seek(0);rf.write(tag);os.fsync(rf.fileno())
  mappedtag=b"dirty-mmap-"+tag;mm[4090:4090+len(mappedtag)]=mappedtag
  return state()
 class Handler(http.server.BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_GET(self):
   try:
    with lock:body=json.dumps(mutate() if self.path=="/mutate" else state()).encode()
    self.send_response(200);self.end_headers();self.wfile.write(body)
   except Exception as e:
    self.send_response(500);self.end_headers();self.wfile.write(str(e).encode())
 http.server.ThreadingHTTPServer(("127.0.0.1",PORT),Handler).serve_forever()
if __name__=="__main__":main()
