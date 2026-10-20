#!/usr/bin/env python3
"""Exact Stage A source/input observations only; no onset proof."""
import argparse,hashlib,json,stat,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[5]/'lib'))
from exact_source_states import validate_component
COMPONENT=Path(__file__).resolve().parent
EXPECTED_METADATA = {'schema': 'audio-haptic-source-provenance-source/v1', 'project': 'foundation/multimedia/av_codec', 'revision': 'e5c525670d1f6622d441c9e5bf975ea0579ea177', 'files': [{'relative': 'services/media_engine/plugins/sink/audio_server_sink_plugin.cpp', 'original_sha256': '24bc39c901437a47b178e022a055322e0bf055dcbf5074c044ba155e6213b276', 'final_sha256': '3e4d125773c8dfacf36360231d7b414dd78bf56aa8d0e8c6fe9f52a250d3bbcc'}, {'relative': 'services/media_engine/plugins/sink/audio_server_sink_plugin.h', 'original_sha256': 'c256981b4dc8012e5eac1327ee5d572f834e43ec476c62101ee3657bcf0f4abc', 'final_sha256': 'cfabb2c11d1e9e6021aff8cd0ebc9f14c0586f380289c2d0d82bb6438221b647'}, {'relative': 'services/media_engine/plugins/sink/qemu_audio_provenance505.h', 'original_sha256': None, 'final_sha256': 'e6a9cfbf52d5cbe868d1b0ee1e663f282f9f68b1442b06087bf1976fa783ef73'}, {'relative': 'services/media_engine/filters/audio_sink_filter.cpp', 'original_sha256': '0e5d427cc26152d092b486e45921f302a45f2e5e9cac1ac218dcd905918390ea', 'final_sha256': '0fd322964b9235d964ba77a80918e3680d7dc07e40e05ed54807e5b83ca7e0e2'}, {'relative': 'services/media_engine/modules/sink/audio_sink.cpp', 'original_sha256': '3bb47db1ee09e9eee25aa03b79c4e94890a125b7ecc002199da4ef10404f3f4e', 'final_sha256': 'd211fafe5ef895f8642b02ba87d66bcf57daa2548feea8624726288bae681ef0'}], 'prerequisites': [{'relative': 'foundation/multimedia/audio_framework/interfaces/inner_api/native/audiorenderer/include/audio_renderer.h', 'sha256': '0e655c03ceb2ad7725982496253bc70ce713392c7492c350659e35f586bdb29f', 'bytes': 48254}, {'relative': 'foundation/multimedia/player_framework/services/services/player/server/player_server.cpp', 'sha256': '85bcefcb7f0c1e5722ccd355c31c59a98a642f790bd7d29ef13c54164d7a842f', 'bytes': 121554}, {'relative': 'foundation/multimedia/player_framework/frameworks/native/audio_haptic/audio_haptic_player_impl.cpp', 'sha256': 'b654c792352a010f5526f707b94e7a8de7c52027c5011ed2847caa12dae890e1', 'bytes': 41062}, {'relative': 'foundation/multimedia/player_framework/frameworks/native/audio_haptic/audio_haptic_player_impl.h', 'sha256': '69b9ab3c4a3a49bfdb2f754efcadc86e79591a5ac30fc169f82c9af4acad91c3', 'bytes': 7056}, {'relative': 'foundation/multimedia/player_framework/frameworks/native/audio_haptic/audio_haptic_playback_session.h', 'sha256': 'd3b63a658f58b2091154b5006b6657fb3866c064cc2291ae3f619e3f5995a30c', 'bytes': 1925}, {'relative': 'foundation/multimedia/player_framework/frameworks/native/audio_haptic/audio_haptic_publication_callback.h', 'sha256': '1716816d6db703f582367bfbd478090938f50743e44d48074d7da57586cc5d6c', 'bytes': 1575}], 'patch': '0001-source-provenance.patch', 'patch_sha256': '15ea6bd0f940e138d3bdab40e64d545a84840fa59928e3a2a81d6bbe23488b7d', 'accepted': False, 'onset_proven': False, 'first_artifact_behavior_gate_passed': False}
PROJECT=EXPECTED_METADATA['project'];REVISION=EXPECTED_METADATA['revision']
FILES=tuple((f['relative'],f['original_sha256'],f['final_sha256'])for f in EXPECTED_METADATA['files'])
def unique(pairs):
 d={}
 for k,v in pairs:
  if k in d:raise ValueError('duplicate metadata key')
  d[k]=v
 return d
def metadata():
 p=COMPONENT/'source_states.json'
 if p.is_symlink()or not p.is_file():raise ValueError('regular exact metadata required')
 v=json.loads(p.read_text(),object_pairs_hook=unique)
 if v!=EXPECTED_METADATA:raise ValueError('source provenance metadata differs')
 patches=list(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))
 if len(patches)!=1 or patches[0].name!=v['patch']or patches[0].is_symlink()or hashlib.sha256(patches[0].read_bytes()).hexdigest()!=v['patch_sha256']:raise ValueError('source provenance patch differs')
 return v
def root_path(root):
 root=Path(root).absolute()
 for p in (root,*root.parents):
  if p.is_symlink():raise ValueError('source root/ancestor symlink refused')
 if not root.is_dir():raise ValueError('source root directory required')
 return root
def regular(root,relative,optional=False):
 root=root_path(root);p=root/relative
 for cursor in (p,*p.parents):
  if cursor==root:break
  if cursor.is_symlink():raise ValueError('source symlink refused: '+relative)
 if optional and not p.exists():return None
 st=p.stat()
 if not stat.S_ISREG(st.st_mode)or st.st_nlink!=1:raise ValueError('single regular source required: '+relative)
 return p.read_bytes()
def prerequisites(root):
 metadata()
 for f in EXPECTED_METADATA['prerequisites']:
  raw=regular(root,f['relative'])
  if len(raw)!=f['bytes']or hashlib.sha256(raw).hexdigest()!=f['sha256']:raise ValueError('stable API/relay/lifecycle prerequisite differs: '+f['relative'])
 for rel,old,new in FILES:regular(root,PROJECT+'/'+rel,old is None)
 return validate(root)
def validate(root,require_patched=False):
 # Original generic helper stages only managed files; outer guards stay outside.
 metadata()
 return validate_component(root,PROJECT,REVISION,FILES,require_patched)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',required=True,type=Path);p.add_argument('--check-prerequisites',action='store_true');p.add_argument('--require-patched',action='store_true');a=p.parse_args()
 prerequisites(a.source_root)
 if a.check_prerequisites:return 0
 patched=validate(a.source_root,a.require_patched)
 print(json.dumps(dict(scope='exact Stage A source-only configuration',patched=patched,compiled=False,accepted=False,onset_proven=False,first_artifact_behavior_gate_passed=False)))
 return 0
if __name__=='__main__':raise SystemExit(main())
