"""Finite real-source whole-vector admission and original generic-helper tests."""
import base64,gzip,hashlib,importlib.util,json,os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
P='foundation/multimedia/player_framework';C='foundation/multimedia/av_codec';NAME='audio_haptic_source_provenance'
COMP=ROOT/'patches/common'/P/NAME;FIXTURE=HERE/'fixtures'/NAME
sys.path.insert(0,str(COMP))
from verify_batch import state,EXPECTED_FINAL,BEFORE_RELAY,EXPECTED_STATES,LIFECYCLE_SHA256
from verify_source import prerequisites
HISTORICAL=HERE/'fixtures/batch_media/audio_haptic_generation/source_states.json'
HISTORICAL_SHA='f467e27898ce8d877b5a1e521961e2d5938cd954e192e1b598bb6c6b6f6a0ab2'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot(root):return {str(p.relative_to(root)):p.read_bytes()for p in root.rglob('*')if p.is_file()and'.ohos-qemu-patches'not in p.parts}
def populate(root):shutil.copytree(FIXTURE/'before',root,dirs_exist_ok=True)
def env(root):
 result={k:v for k,v in os.environ.items()if not k.startswith('GIT_')};result['GIT_CEILING_DIRECTORIES']=str(root.parent);result['TMPDIR']=str(root.parent);return result
def run(root,argv,okay=True):
 result=subprocess.run([str(x)for x in argv],env=env(root),text=True,capture_output=True)
 if okay and result.returncode:raise AssertionError((argv,result.returncode,result.stdout,result.stderr))
 return result
class ExactSourceProvenance(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='audio-provenance505-');self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()/'source';self.root.mkdir();populate(self.root)
 def apply(self,project):
  return run(self.root,['bash',ROOT/'patches/common'/project/NAME/'apply.sh','--source-root',self.root])
 def test_original_helper_apply_repeat_reverse_whole_vectors(self):
  before=snapshot(self.root);self.assertEqual(state(self.root),'legacy:incarnation')
  for project in [P,C]:self.apply(project)
  self.assertEqual(state(self.root,True),'final505');final=snapshot(self.root)
  for project in [P,C]:self.apply(project)
  self.assertEqual(snapshot(self.root),final)
  for project in [C,P]:
   patch=ROOT/'patches/common'/project/NAME/'0001-source-provenance.patch'
   run(self.root,['git','-C',self.root,'apply','--reverse','--check',patch]);run(self.root,['git','-C',self.root,'apply','--reverse',patch])
  self.assertEqual(snapshot(self.root),before);self.assertEqual(state(self.root),'legacy:incarnation')
 def test_all_real_historical_complete_lifecycle_vectors_admitted(self):
  self.assertEqual(digest(HISTORICAL),HISTORICAL_SHA);old=json.loads(HISTORICAL.read_text())
  for name,vector in old['states'].items():
   with self.subTest(state=name):
    for rel,value in vector.items():
     path=self.root/P/rel;data=gzip.decompress(base64.b64decode(value['gzip_base64'],validate=True))if value['gzip_base64']is not None else None
     self.assertEqual(hashlib.sha256(data).hexdigest()if data is not None else None,EXPECTED_STATES[name][rel])
     if data is None:path.unlink(missing_ok=True)
     else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    before=snapshot(self.root);self.assertEqual(state(self.root),'legacy:'+name);self.assertEqual(snapshot(self.root),before)
    with self.assertRaises(ValueError):state(self.root,True)
 def test_each_managed_foreign_edit_rejected_before_any_write(self):
  for name in EXPECTED_FINAL:
   with self.subTest(file=name),tempfile.TemporaryDirectory(prefix='qap505-foreign-')as directory:
    root=Path(directory).resolve();populate(root);target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(target.read_bytes()+b'\n// foreign\n'if target.exists()else b'// foreign new header\n');before=snapshot(root)
    with self.assertRaises(ValueError):state(root)
    result=run(root,[sys.executable,COMP/'verify_batch.py','--source-root',root],False)
    self.assertNotEqual(result.returncode,0);self.assertEqual(snapshot(root),before);self.assertFalse((root/'.ohos-qemu-patches').exists())
 def test_each_component_partial_state_rejected_without_mutation(self):
  for project in [P,C]:
   with self.subTest(project=project),tempfile.TemporaryDirectory(prefix='qap505-partial-')as directory:
    root=Path(directory).resolve();populate(root)
    component=ROOT/'patches/common'/project/NAME;manifest=json.loads((component/'source_states.json').read_text())
    # Produce authentic complete after image with the original helper, then mix one actual final file.
    complete=root.parent/(root.name+'-complete');shutil.copytree(root,complete)
    try:
     run(complete,['bash',component/'apply.sh','--source-root',complete])
     rel=manifest['files'][0]['relative'];shutil.copy2(complete/project/rel,root/project/rel);before=snapshot(root)
     with self.assertRaises(ValueError):state(root)
     result=run(root,['bash',component/'apply.sh','--source-root',root],False)
     self.assertNotEqual(result.returncode,0);self.assertEqual(snapshot(root),before);self.assertFalse((root/'.ohos-qemu-patches').exists())
    finally:shutil.rmtree(complete)
 def test_final_other_four_lifecycle_guards_cannot_be_bypassed(self):
  for project in [P,C]:self.apply(project)
  normal=['audio_haptic_sound_normal_impl.cpp','audio_haptic_sound_normal_impl.h']
  other=[n for n in EXPECTED_FINAL if n.startswith(P+'/frameworks/native/audio_haptic/')and Path(n).name not in normal and not n.endswith('qemu_audio_provenance505.h')]
  self.assertEqual(len(other),4)
  for name in other:
   target=self.root/name;old=target.read_bytes();target.write_bytes(old+b'// drift\n');before=snapshot(self.root)
   with self.assertRaises(ValueError):state(self.root)
   with self.assertRaises(ValueError):prerequisites(self.root)
   self.assertEqual(snapshot(self.root),before);target.write_bytes(old)
 def test_all_stable_guards_missing_and_foreign_rejected(self):
  meta=json.loads((COMP/'source_states.json').read_text())
  for f in meta['prerequisites']:
   path=self.root/f['relative'];old=path.read_bytes()
   for mode in ['missing','foreign']:
    with self.subTest(file=f['relative'],mode=mode):
     if mode=='missing':path.unlink()
     else:path.write_bytes(old+b'// wrong\n')
     before=snapshot(self.root)
     with self.assertRaises((ValueError,FileNotFoundError)):prerequisites(self.root)
     self.assertEqual(snapshot(self.root),before);path.write_bytes(old)
 def test_symlinks_hardlinks_and_unknown_root_rejected(self):
  rel=next(iter(EXPECTED_FINAL));target=self.root/rel;saved=self.root/'saved';target.rename(saved);target.symlink_to(saved)
  with self.assertRaises(ValueError):state(self.root)
  target.unlink();os.link(saved,target)
  with self.assertRaises(ValueError):state(self.root)
  target.unlink();target.write_bytes(saved.read_bytes());alias=self.root.parent/'alias';alias.symlink_to(self.root)
  with self.assertRaises(ValueError):state(alias)
 def test_metadata_and_patch_tampering_fail_closed(self):
  # Test copied component only, never mutate shared/canonical metadata.
  with tempfile.TemporaryDirectory(prefix='qap505-component-')as directory:
   root=Path(directory).resolve();component=root/'patches/common'/P/NAME;component.parent.mkdir(parents=True);shutil.copytree(COMP,component)
   lib=root/'patches/lib';shutil.copytree(ROOT/'patches/lib',lib)
   manifest=component/'source_states.json';value=json.loads(manifest.read_text());value['accepted']=True;manifest.write_text(json.dumps(value))
   before=snapshot(self.root);r=run(self.root,[sys.executable,component/'verify_source.py','--source-root',self.root],False);self.assertNotEqual(r.returncode,0);self.assertEqual(snapshot(self.root),before)
   shutil.copy2(COMP/'source_states.json',manifest);patch=component/'0001-source-provenance.patch';patch.write_bytes(patch.read_bytes()+b'\n')
   r=run(self.root,[sys.executable,component/'verify_source.py','--source-root',self.root],False);self.assertNotEqual(r.returncode,0);self.assertEqual(snapshot(self.root),before)
 def test_fixture_raw_inputs_and_original_support_bound(self):
  meta=json.loads((FIXTURE/'SOURCE505.json').read_text())
  for f in meta['source_files']:self.assertEqual(digest(FIXTURE/'before'/f['relative']),f['sha256'])
  self.assertEqual(digest(COMP.parent/'audio_haptic_lifecycle/source_states.json'),LIFECYCLE_SHA256)
 def test_ordinary_relay_and_plugin_bodies_are_byte_preserved(self):
  sys.path.insert(0,str(FIXTURE));from extract505 import method
  with tempfile.TemporaryDirectory(prefix='qap513-relay-source-')as directory:
   root=Path(directory).resolve();populate(root)
   for project in [P,C]:run(root,['bash',ROOT/'patches/common'/project/NAME/'apply.sh','--source-root',root])
   for rel,owner in [(C+'/services/media_engine/filters/audio_sink_filter.cpp','AudioSinkFilter'),(C+'/services/media_engine/modules/sink/audio_sink.cpp','AudioSink')]:
    before=method((FIXTURE/'before'/rel).read_text(),owner,'SetParameter');after=method((root/rel).read_text(),owner,'SetParameter')
    original=before[before.index('\n    globalMeta_ = meta;'):];final=after[after.index('\n    globalMeta_ = meta;'):];self.assertEqual(final,original)
   rel=C+'/services/media_engine/plugins/sink/audio_server_sink_plugin.cpp';self.assertEqual(method((FIXTURE/'before'/rel).read_text(),'AudioServerSinkPlugin','SetParameter'),method((root/rel).read_text(),'AudioServerSinkPlugin','SetParameter'))
if __name__=='__main__':unittest.main()
