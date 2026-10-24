from pathlib import Path
import os,json,hashlib
from adx_environment import Environment,ConnectionConfig
N=Path('/mnt/m0-xfs/akernel-pr119-followup-20261022.qbGAw9tp')
s=json.loads((N/'acceptance/runs/shared-gvisor-native-held-reader02-sandboxd/resources.private.json').read_text())['snapshot']
c=ConnectionConfig(server_address=os.environ['AKERNEL_SERVER_ADDRESS'],token=os.environ['AKERNEL_TOKEN'],use_tls=True,gateway_address=os.environ.get('AKERNEL_GATEWAY_ADDRESS'),verify_tls=True)
v=Environment.get_snapshot(s,connection=c);assert v.snapshot_id==s
print(json.dumps({'retained_snapshot_retrievable':True,'snapshot_id_sha256':hashlib.sha256(s.encode()).hexdigest()}))
