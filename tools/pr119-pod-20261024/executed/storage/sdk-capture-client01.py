#!/usr/bin/env python3
import argparse,json,os,pathlib,sys
from adx_environment import Environment,ConnectionConfig
p=argparse.ArgumentParser();p.add_argument("--environment",required=True);p.add_argument("--name",required=True);p.add_argument("--out",type=pathlib.Path,required=True);a=p.parse_args()
a.out.mkdir(mode=0o700)
conn=ConnectionConfig(server_address=os.environ["AKERNEL_SERVER_ADDRESS"],token=os.environ["AKERNEL_TOKEN"],use_tls=True,gateway_address=os.environ.get("AKERNEL_GATEWAY_ADDRESS"),verify_tls=True)
env=Environment.from_id(a.environment,connection=conn)
(a.out/"started.json").write_text(json.dumps({"pid":os.getpid(),"start_ticks":pathlib.Path("/proc/self/stat").read_text().split()[21]}))
try:
 snap=env.create_snapshot(name=a.name,timeout_seconds=180)
 (a.out/"terminal.json").write_text(json.dumps({"rc":0,"snapshot_id":snap.snapshot_id}))
except Exception as e:
 (a.out/"terminal.json").write_text(json.dumps({"rc":1,"type":type(e).__name__,"code":getattr(e,"code",None),"retry":getattr(e,"retry",None),"outcome":getattr(e,"outcome",None)}));raise
