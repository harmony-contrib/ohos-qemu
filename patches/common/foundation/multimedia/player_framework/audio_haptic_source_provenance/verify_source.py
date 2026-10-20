#!/usr/bin/env python3
"""Exact Stage A source/input observations only; no onset proof."""
import argparse,hashlib,json,stat,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[5]/'lib'))
from exact_source_states import validate_component
COMPONENT=Path(__file__).resolve().parent
EXPECTED_METADATA = {'schema': 'audio-haptic-source-provenance-source/v1', 'project': 'foundation/multimedia/player_framework', 'revision': '3d3b1231db27561e8978652d7ae867c12f488d9a', 'files': [{'relative': 'frameworks/native/audio_haptic/audio_haptic_sound_normal_impl.cpp', 'original_sha256': '284068ca75062ce4716dbaa6169bcce5fb5620d7f809c706cab56e5e23d0858f', 'final_sha256': 'b11e413265c3f103aed375670d50b98476bb8fac743d51d3fbb8d3d3004431b2'}, {'relative': 'frameworks/native/audio_haptic/audio_haptic_sound_normal_impl.h', 'original_sha256': '017a60022cdfb40cd323f73854234f2e1b64215421e653449e9adf54f7b0ccb0', 'final_sha256': '3f5d247640eb72c7f88f6e91d1c7e6bbb4a05971ab65327b97568274f3450207'}, {'relative': 'services/engine/histreamer/player/hiplayer_impl.cpp', 'original_sha256': '3bb7f9e9220411f0c20323274d0b45ca9a5a95f800bff1a91d2a13bb6c3700db', 'final_sha256': '50f4d5d7b7b0552358a222edb695dbcbd2e2288a785c51861b9d67289c3af58f'}, {'relative': 'services/engine/histreamer/player/hiplayer_impl.h', 'original_sha256': 'cf37a65cdf9b0420d792c5454c1480bc2e6b6bcd25a3d7aeef5720b5409925bc', 'final_sha256': '876012cdf6cb6811cd3ae92000a380a76844a16e7535fa8bfb3e69e1fbbb2f10'}, {'relative': 'frameworks/native/audio_haptic/qemu_audio_provenance505.h', 'original_sha256': None, 'final_sha256': 'e6a9cfbf52d5cbe868d1b0ee1e663f282f9f68b1442b06087bf1976fa783ef73'}, {'relative': 'services/engine/histreamer/player/qemu_audio_provenance505.h', 'original_sha256': None, 'final_sha256': 'e6a9cfbf52d5cbe868d1b0ee1e663f282f9f68b1442b06087bf1976fa783ef73'}], 'prerequisites': [{'relative': 'foundation/multimedia/audio_framework/interfaces/inner_api/native/audiorenderer/include/audio_renderer.h', 'sha256': '0e655c03ceb2ad7725982496253bc70ce713392c7492c350659e35f586bdb29f', 'bytes': 48254}, {'relative': 'foundation/multimedia/player_framework/services/services/player/server/player_server.cpp', 'sha256': '85bcefcb7f0c1e5722ccd355c31c59a98a642f790bd7d29ef13c54164d7a842f', 'bytes': 121554}, {'relative': 'foundation/multimedia/player_framework/frameworks/native/audio_haptic/audio_haptic_player_impl.cpp', 'sha256': 'b654c792352a010f5526f707b94e7a8de7c52027c5011ed2847caa12dae890e1', 'bytes': 41062}, {'relative': 'foundation/multimedia/player_framework/frameworks/native/audio_haptic/audio_haptic_player_impl.h', 'sha256': '69b9ab3c4a3a49bfdb2f754efcadc86e79591a5ac30fc169f82c9af4acad91c3', 'bytes': 7056}, {'relative': 'foundation/multimedia/player_framework/frameworks/native/audio_haptic/audio_haptic_playback_session.h', 'sha256': 'd3b63a658f58b2091154b5006b6657fb3866c064cc2291ae3f619e3f5995a30c', 'bytes': 1925}, {'relative': 'foundation/multimedia/player_framework/frameworks/native/audio_haptic/audio_haptic_publication_callback.h', 'sha256': '1716816d6db703f582367bfbd478090938f50743e44d48074d7da57586cc5d6c', 'bytes': 1575}], 'patch': '0001-source-provenance.patch', 'patch_sha256': 'efe08ae6d2ed9b5f0a0893bd5358c0d98785eecd3a12393a75a9703862234bdf', 'accepted': False, 'onset_proven': False, 'first_artifact_behavior_gate_passed': False}
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
