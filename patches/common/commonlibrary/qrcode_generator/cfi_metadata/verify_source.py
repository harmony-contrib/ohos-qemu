"""Exact actual qrcode CFI source states; no compile or runtime claim."""
from pathlib import Path
import argparse,hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'lib'))
from exact_source_states import validate_component
PROJECT='commonlibrary/qrcode_generator'
REVISION='993bd298a703301b21bb60fc1e352626558a66e7'
FILES=(('BUILD.gn', '860f6e139e30f954dc8c3dbc69ba497575ac172ccd39587e7d4248de9e806644', 'c5e3749364e02e0df0fb7a2f71e5770f151b9df4f3b75c40cb76160ecd592aa4'),)
PATCH='0001-keep-real-qrcode-archive-CFI-metadata.patch'
PATCH_SHA256='e67d77fbf7c6f298bdfc7ca4e8b49bae602abf5565aab2a7b04d96568b83d2dd'
COMPONENT=Path(__file__).resolve().parent
EXPECTED={'schema': 'native-qrcode-cfi-source/v1', 'project': 'commonlibrary/qrcode_generator', 'revision': '993bd298a703301b21bb60fc1e352626558a66e7', 'files': [{'relative': 'BUILD.gn', 'original_sha256': '860f6e139e30f954dc8c3dbc69ba497575ac172ccd39587e7d4248de9e806644', 'final_sha256': 'c5e3749364e02e0df0fb7a2f71e5770f151b9df4f3b75c40cb76160ecd592aa4'}], 'patch': '0001-keep-real-qrcode-archive-CFI-metadata.patch', 'patch_sha256': 'e67d77fbf7c6f298bdfc7ca4e8b49bae602abf5565aab2a7b04d96568b83d2dd', 'scope': 'real nonempty qrcode archive metadata for ACE linked input closure', 'actual_gn_compile_solink_runtime_pending': True, 'first_artifact_behavior_gate_passed': False}
def unique(pairs):
 r={}
 for k,v in pairs:
  if k in r:raise ValueError('duplicate qrcode source metadata')
  r[k]=v
 return r
def metadata():
 p=COMPONENT/'source_states.json'
 if p.is_symlink() or not p.is_file():raise ValueError('qrcode source manifest required')
 v=json.loads(p.read_text(),object_pairs_hook=unique)
 if v!=EXPECTED:raise ValueError('qrcode source metadata differs')
 a=list(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
 if len(a)!=1 or a[0].name!=PATCH or a[0].is_symlink() or hashlib.sha256(a[0].read_bytes()).hexdigest()!=PATCH_SHA256:raise ValueError('qrcode patch differs')
 return v
def validate(root,require_patched=False):
 metadata();return validate_component(root,PROJECT,REVISION,FILES,require_patched)
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--require-patched',action='store_true');a=p.parse_args(argv)
 v=validate(a.source_root,a.require_patched);print(json.dumps(dict(patched=v,compiled=False,runtime_passed=False)));return 0
if __name__=='__main__':raise SystemExit(main())
