"""Exact source-only ACE CFI coverage states; target graph/ELF/runtime are separate gates."""
from pathlib import Path
import argparse,hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5]/'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
FILES = (('BUILD.gn', '036775b7c03a2d2e002f002c8c44643e8b90b849aa7c8c26b2919432be4ac5c8', '9f7b3cd7604a5f9cf2a1ff8ff47ba3fc21f448be8de7be7140fdc1d3799a0166'), ('adapter/ohos/entrance/ui_content_impl.cpp', 'a02391fc2b1786f0a4ad47dcb895861689433520f0363c1c7aa8e939a2bf6bc5', 'af0a00d4fb58e12fb613821953220c1b93852959e480a3603c66e4768c7d0b80'), ('adapter/ohos/build/BUILD.gn', 'ef693f53bc8c1ce4b8792d9b38c1e5759d280c90598b499e58ecfd411eb30bd2', '9c289ac3cdcc0953a3c4a42e7fe414f39a70b4a2d424e92f40c0b4f0f0023203'), ('build/ace_lib.gni', '033309623b3f8dfe704db4ceda403b4e230738712e68343825a3422c35a47db1', 'd40731fa56ae8af0f8a7f65b3bbb4703b3560e00beab29acd5791e68a0b94edf'), ('build/BUILD.gn', '7c3b56fc8c144a184c1328a5400f58f5e1c908c927128a6b10956aaa73f64b14', 'dabef0b93491f02cf5fdd214e6bea84a75908b1656f1394d3019b288d5dd1104'), ('frameworks/core/components_ng/pattern/smart_layout/engine/BUILD.gn', 'e8fd104ecdebbf974e942f3a619d06fd11f1898ab48464772ae1275f751f4657', '7893c5214f6ddbe921cb1cd9c8b411b04ab7ca1b44cb89106fdf81e02d11a089'))
PATCH = '0001-instrument-ACE-common-carrier-and-align-factory-types.patch'
PATCH_SHA256 = '9923d92c776665cd521fab671508a2ed1656ecef39675c479b008127582d0a01'
COMPONENT = Path(__file__).resolve().parent
# Old component is preserved byte-for-byte and must have completed first.
PREREQUISITES = (
 ('frameworks/core/components_ng/components.gni','b845a254530491f05d8a8081a5f329fd6cd24a551c77f6f9c9cfeba0c43e1f8f'),
)
def unique(pairs):
 r={}
 for k,v in pairs:
  if k in r:raise ValueError('duplicate CFI coverage metadata')
  r[k]=v
 return r
def metadata():
 p=COMPONENT/'source_states.json'
 if p.is_symlink() or not p.is_file():raise ValueError('exact CFI coverage manifest required')
 v=json.loads(p.read_text(),object_pairs_hook=unique)
 expected=dict(schema='native-ace-cfi-coverage-source/v1',project=PROJECT,revision=REVISION,files=[dict(relative=n,original_sha256=o,final_sha256=f) for n,o,f in FILES],patch=PATCH,patch_sha256=PATCH_SHA256,scope='actual prepared ACE whole-file paired states; existing UIExtension CFI component is a prerequisite',actual_gn_compile_solink_runtime_pending=True,first_artifact_behavior_gate_passed=False)
 if v!=expected:raise ValueError('exact CFI coverage metadata differs')
 patches=list(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
 if len(patches)!=1 or patches[0].name!=PATCH or patches[0].is_symlink() or hashlib.sha256(patches[0].read_bytes()).hexdigest()!=PATCH_SHA256:raise ValueError('exact CFI coverage patch differs')
 return v
def preflight(root):
 """Exactly pristine, previous identity component, or full coverage post-state."""
 metadata();root=Path(root).resolve()
 value={}
 for relative,old,new in FILES:
  p=root/PROJECT/relative
  for parent in (p,*p.parents):
   if parent==root:break
   if parent.is_symlink():raise ValueError('CFI preflight contains symlink')
  if not p.is_file():raise ValueError('missing CFI sibling: '+relative)
  value[relative]=hashlib.sha256(p.read_bytes()).hexdigest()
 relative,expected=PREREQUISITES[0];p=root/PROJECT/relative
 for parent in (p,*p.parents):
  if parent==root:break
  if parent.is_symlink():raise ValueError('CFI prerequisite contains symlink')
 if not p.is_file():raise ValueError('missing CFI prerequisite')
 value[relative]=hashlib.sha256(p.read_bytes()).hexdigest()
 before={n:o for n,o,f in FILES};identity=dict(before);final={n:f for n,o,f in FILES}
 identity[relative]=expected;final[relative]=expected
 before['build/BUILD.gn']='bd4b450a591a8110ec519ad90b29ea7cc44834a173b7e3de8c0403954f1faae9'
 before[relative]='40eeb7262448f89e65b18c776ae8ffda7330ed9589898585eabfddb1d63d7f76'
 qrcode=root/'commonlibrary/qrcode_generator/BUILD.gn'
 for parent in (qrcode,*qrcode.parents):
  if parent==root:break
  if parent.is_symlink():raise ValueError('qrcode sibling contains symlink')
 if not qrcode.is_file():raise ValueError('missing qrcode CFI sibling')
 key='@qrcode/BUILD.gn';value[key]=hashlib.sha256(qrcode.read_bytes()).hexdigest()
 before[key]='860f6e139e30f954dc8c3dbc69ba497575ac172ccd39587e7d4248de9e806644';identity[key]='860f6e139e30f954dc8c3dbc69ba497575ac172ccd39587e7d4248de9e806644';final[key]='c5e3749364e02e0df0fb7a2f71e5770f151b9df4f3b75c40cb76160ecd592aa4'
 qrcode_ready=dict(identity);qrcode_ready[key]='c5e3749364e02e0df0fb7a2f71e5770f151b9df4f3b75c40cb76160ecd592aa4'
 sec=root/'third_party/bounds_checking_function/BUILD.gn'
 for parent in (sec,*sec.parents):
  if parent==root:break
  if parent.is_symlink():raise ValueError('sec variant sibling contains symlink')
 if not sec.is_file():raise ValueError('missing sec variant sibling')
 key='@sec/BUILD.gn';value[key]=hashlib.sha256(sec.read_bytes()).hexdigest()
 before[key]='78dceed022da3bbea9175e5385d89f17f2950e18dc065dc2a1dfea30cd875477';identity[key]='78dceed022da3bbea9175e5385d89f17f2950e18dc065dc2a1dfea30cd875477';qrcode_ready[key]='78dceed022da3bbea9175e5385d89f17f2950e18dc065dc2a1dfea30cd875477';final[key]='7a1185bc4c0ec95af9b7e6b5000a71e51ec94d69203e4edc7a159312ce0a35b5'
 sec_ready=dict(qrcode_ready);sec_ready[key]='7a1185bc4c0ec95af9b7e6b5000a71e51ec94d69203e4edc7a159312ce0a35b5'
 for state,known in [('pristine',before),('identity',identity),('identity-qrcode',qrcode_ready),('identity-qrcode-sec',sec_ready),('coverage',final)]:
  if value==known:return state
 raise ValueError('mixed/unknown CFI sibling states; preserving all source')
def prerequisites(root):
 if preflight(root) not in ('identity-qrcode-sec','coverage'):raise ValueError('complete preceding identity and qrcode CFI components required')
def validate(root,require_patched=False):
 metadata()
 return validate_component(root,PROJECT,REVISION,FILES,require_patched)
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--require-patched',action='store_true');p.add_argument('--check-prerequisites',action='store_true');p.add_argument('--preflight',action='store_true');a=p.parse_args(argv)
 metadata()
 if a.preflight:
  print(preflight(a.source_root));return 0
 prerequisites(a.source_root)
 if a.check_prerequisites:return 0
 state=validate(a.source_root,a.require_patched)
 print(json.dumps(dict(scope='exact paired ACE source configuration ONLY',patched=state,compiled=False,CFI_linked_input_closure_verified=False,runtime_passed=False,first_artifact_behavior_gate_passed=False)))
 return 0
if __name__=='__main__':raise SystemExit(main())
