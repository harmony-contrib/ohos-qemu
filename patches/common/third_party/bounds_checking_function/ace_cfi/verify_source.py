"""Exact actual ACE-only sec-static CFI source states; no compile or runtime claim."""
from pathlib import Path
import argparse,hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'lib'))
from exact_source_states import validate_component
PROJECT='third_party/bounds_checking_function'
REVISION='61baa7a3eb9347efca58397d1d0504faa96d79f0'
FILES=(('BUILD.gn', '78dceed022da3bbea9175e5385d89f17f2950e18dc065dc2a1dfea30cd875477', '7a1185bc4c0ec95af9b7e6b5000a71e51ec94d69203e4edc7a159312ce0a35b5'),)
PATCH='0001-add-fixed-ACE-only-secstatic-CFI-variant.patch'
PATCH_SHA256='3313501f50cd0bab2bb2b6b53bb16c5c9dfa6e714cfd674f028e2ebb611b73f1'
COMPONENT=Path(__file__).resolve().parent
EXPECTED={'schema': 'native-ace-sec-static-cfi-source/v1', 'project': 'third_party/bounds_checking_function', 'revision': '61baa7a3eb9347efca58397d1d0504faa96d79f0', 'files': [{'relative': 'BUILD.gn', 'original_sha256': '78dceed022da3bbea9175e5385d89f17f2950e18dc065dc2a1dfea30cd875477', 'final_sha256': '7a1185bc4c0ec95af9b7e6b5000a71e51ec94d69203e4edc7a159312ce0a35b5'}], 'patch': '0001-add-fixed-ACE-only-secstatic-CFI-variant.patch', 'patch_sha256': '3313501f50cd0bab2bb2b6b53bb16c5c9dfa6e714cfd674f028e2ebb611b73f1', 'scope': 'fixed ACE-only secstatic variant; global original target and shared/Lite code preserved', 'actual_gn_compile_solink_runtime_pending': True, 'first_artifact_behavior_gate_passed': False}
def unique(pairs):
 r={}
 for k,v in pairs:
  if k in r:raise ValueError('duplicate ACE sec variant source metadata')
  r[k]=v
 return r
def metadata():
 p=COMPONENT/'source_states.json'
 if p.is_symlink() or not p.is_file():raise ValueError('ACE sec variant source manifest required')
 v=json.loads(p.read_text(),object_pairs_hook=unique)
 if v!=EXPECTED:raise ValueError('ACE sec variant source metadata differs')
 a=list(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
 if len(a)!=1 or a[0].name!=PATCH or a[0].is_symlink() or hashlib.sha256(a[0].read_bytes()).hexdigest()!=PATCH_SHA256:raise ValueError('ACE sec variant patch differs')
 return v
def validate(root,require_patched=False):
 metadata();return validate_component(root,PROJECT,REVISION,FILES,require_patched)
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--require-patched',action='store_true');a=p.parse_args(argv)
 v=validate(a.source_root,a.require_patched);print(json.dumps(dict(patched=v,compiled=False,runtime_passed=False)));return 0
if __name__=='__main__':raise SystemExit(main())
