#!/usr/bin/env python3
"""Apply five reviewed production source fixes before normal product compilation.

No image/package rewriting or runtime profile switch. Every source file must
be exactly the reviewed preimage or this exact final image, before any write.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
PAIRS = [('applications/standard/admin_provisioning/entry/src/main/ets/MainAbility/ByodAdminProvisionAbility.ts', '448901d9fd4b081a4949d2d06906b404a45504bd57730bc2ce3454d18e89514f', '9a16f377696e60d73cc9dc8d08a8f97d4a01238d2cac4cc01de3f158acc09fbd'), ('applications/standard/admin_provisioning/entry/src/main/ets/pages/byod/byodActivationPage.ets', 'c87ad0d795d4073e9ee553e24c183378f7ea7ca78134696f13e419ab363fc83e', 'd7ddfb7d63c59fec041799d494169cbb3ca7380ce842930d9c2d38e486fa5e44'), ('applications/standard/mms/entry/src/main/ets/pages/transmitmsg/transmitMsgPage.ets', '516e94fcada17b5c6e16c2c19d6121b0c0e709a675c540ad13699634303a596f', 'b53cf189c1e91f61c9b3de58bb48971ef97134003b056bbc73ed834d4f1beec9'), ('foundation/ability/ability_runtime/services/abilitymgr/etc/appfwk.para', 'fb05d3b87cfa9def879abec2b45f7e97d8d42b8069b2932cfde370a71d45a884', '50d25cbc171bd151b3016fd9b7a8911b24080b36a7acf031296b3fef02ed3a94'), ('foundation/ability/ability_runtime/services/abilitymgr/src/dialog_session/dialog_session_manager.cpp', '65d04f5cf9dfaf1f0aaa267ff8b0dfa06296a0ea600e25ceac2ac0438a60f11a', 'b3dec3bcc065de6c80814fd3c0cca599f80da43f25f00c5e56406732f57aef63')]
ASSETS=Path(__file__).resolve().parent/'additional579-product'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def apply(root,output):
    root=root.resolve();prepared=[]
    for relative,before,after in PAIRS:
        target=root/relative;asset=ASSETS/relative
        if any(p.is_symlink() for p in (target,*target.parents)) or not target.is_file() or sha(asset)!=after:
            raise ValueError('exact product source/asset required: '+relative)
        current=sha(target)
        if current not in (before,after):raise ValueError('foreign product preimage: '+relative)
        prepared.append((relative,target,asset,current,before,after))
    rows=[]
    for relative,target,asset,current,before,after in prepared:
        if current==before:
            temporary=target.with_name(target.name+'.additional579.tmp')
            with temporary.open('xb') as stream:stream.write(asset.read_bytes());stream.flush();os.fsync(stream.fileno())
            temporary.chmod(target.stat().st_mode&0o777);os.replace(temporary,target)
        if sha(target)!=after:raise ValueError('product source write mismatch: '+relative)
        rows.append(dict(path=relative,before=before,after=after,was_already_applied=current==after))
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w') as stream:json.dump(dict(schema='additional579-normal-product-source-apply/v1',files=rows,source_only=True,runtime_param_mutation=False),stream,indent=2);stream.write('\n')
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source-root',type=Path,required=True);parser.add_argument('--receipt',type=Path,required=True);a=parser.parse_args();apply(a.source_root,a.receipt)
