"""Fixed internal bundle-only upgrade for known whole legacy486 source state."""
from pathlib import Path
import argparse,hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[6]/'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
FILES = (('bundle.json', 'a6795d1664a261e761326b3310d8e089e2a88085f5f6e133701674a7d9dbfe2c', '9e2e83c6709571e8b9a410b6d42c7bbbb5d21f4b2171364f22b102496de87898'),)
PATCH = '0001-declare-existing-ACE-secvariant-third-party-dependency.patch'
PATCH_SHA256 = 'f32d152439ff41b20f9dc0d0227dc43015b0f76f15240fa196bd8391e4dfb58d'
COMPONENT=Path(__file__).resolve().parent
EXPECTED = {'schema': 'native-ace-bundle-dependency-upgrade/v1', 'project': 'foundation/arkui/ace_engine', 'revision': 'e55e178228b9f6388b15d3024e8caf125fa293d7', 'files': [{'relative': 'bundle.json', 'original_sha256': 'a6795d1664a261e761326b3310d8e089e2a88085f5f6e133701674a7d9dbfe2c', 'final_sha256': '9e2e83c6709571e8b9a410b6d42c7bbbb5d21f4b2171364f22b102496de87898'}], 'patch': '0001-declare-existing-ACE-secvariant-third-party-dependency.patch', 'patch_sha256': 'f32d152439ff41b20f9dc0d0227dc43015b0f76f15240fa196bd8391e4dfb58d', 'scope': 'internal exact one-file upgrade after complete known legacy486 CFI siblings; no checks/CFI/part identity changed', 'actual_gn_compile_solink_runtime_pending': True, 'first_artifact_behavior_gate_passed': False}

def unique(pairs):
 r={}
 for k,v in pairs:
  if k in r:raise ValueError('duplicate ACE bundle upgrade metadata')
  r[k]=v
 return r

def metadata():
 p=COMPONENT/'source_states.json'
 if p.is_symlink() or not p.is_file():raise ValueError('exact bundle upgrade metadata required')
 v=json.loads(p.read_text(),object_pairs_hook=unique)
 if v!=EXPECTED:raise ValueError('bundle upgrade metadata differs')
 patches=list(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
 if len(patches)!=1 or patches[0].name!=PATCH or patches[0].is_symlink() or hashlib.sha256(patches[0].read_bytes()).hexdigest()!=PATCH_SHA256:raise ValueError('exact bundle upgrade patch differs')
 return v

def validate(root,require_patched=False):
 metadata();return validate_component(root,PROJECT,REVISION,FILES,require_patched)
