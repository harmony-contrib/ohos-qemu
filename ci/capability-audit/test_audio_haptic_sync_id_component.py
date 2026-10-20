#!/usr/bin/env python3
"""Private-file tests of the original generic exact component application."""
import hashlib,importlib.util,json,os,shutil,subprocess,tempfile,unittest
from unittest.mock import patch
import itertools
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
COMP=ROOT/'patches/common/foundation/multimedia/audio_framework/audio_haptic_sync_id'
FIX=Path(__file__).resolve().parent/'fixtures/audio_haptic_sync_id/before'
STATE=json.loads((COMP/'source_states.json').read_text())
REL=STATE['project']+'/'+STATE['files'][0]['relative']
RELS=[STATE['project']+'/'+r['relative']for r in STATE['files']]

def git_environment(scratch):
 env={k:v for k,v in os.environ.items()if not k.startswith('GIT_')}
 env.update(PYTHONDONTWRITEBYTECODE='1',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',
  GIT_CEILING_DIRECTORIES=str(Path(scratch).resolve()),TMPDIR=str(Path(scratch).resolve()))
 return env

class ComponentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='audio-sync-component495-');self.base=Path(self.tmp.name).resolve()
  self.tree=self.base/'source';shutil.copytree(FIX,self.tree);self.normalize_source_modes();self.env=git_environment(self.base)
 def tearDown(self):self.tmp.cleanup()
 def target(self):return self.tree/REL
 def bytes(self):return {r:(self.tree/r).read_bytes()for r in RELS}
 def normalize_source_modes(self):
  for p in self.tree.rglob('*'):
   if p.is_file():p.chmod(0o644)
 def restore(self):shutil.rmtree(self.tree);shutil.copytree(FIX,self.tree);self.normalize_source_modes()
 def apply(self):
  return subprocess.run(['bash',str(COMP/'apply.sh'),'--source-root',str(self.tree)],env=self.env,capture_output=True,text=True)
 def verify(self,*args):
  return subprocess.run([os.sys.executable,'-B',str(COMP/'verify_source.py'),'--source-root',str(self.tree),*args],env=self.env,capture_output=True,text=True)
 def test_generic_apply_and_idempotence(self):
  modes={r:(self.tree/r).stat().st_mode for r in RELS};one=self.apply();self.assertEqual(one.returncode,0,one.stderr)
  for row in STATE['files']:
   rel=STATE['project']+'/'+row['relative'];p=self.tree/rel
   self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),row['final_sha256']);self.assertEqual(modes[rel],p.stat().st_mode)
  state={r:((self.tree/r).stat().st_ino,(self.tree/r).stat().st_mtime_ns,(self.tree/r).read_bytes())for r in RELS}
  two=self.apply();self.assertEqual(two.returncode,0,two.stderr)
  self.assertEqual(state,{r:((self.tree/r).stat().st_ino,(self.tree/r).stat().st_mtime_ns,(self.tree/r).read_bytes())for r in RELS});self.assertEqual(self.verify('--require-patched').returncode,0)
 def test_readonly_and_require_patched(self):
  p=self.target();before=(p.stat().st_ino,p.stat().st_mtime_ns,p.read_bytes());self.assertEqual(self.verify('--check-prerequisites').returncode,0)
  self.assertNotEqual(self.verify('--require-patched').returncode,0);self.assertEqual(before,(p.stat().st_ino,p.stat().st_mtime_ns,p.read_bytes()))
 def test_unknown_preimage_refused_before_writes(self):
  for rel in RELS:
   with self.subTest(managed=rel):
    self.restore();p=self.tree/rel;p.write_bytes(p.read_bytes()+b'\n');raw=self.bytes();self.assertNotEqual(self.apply().returncode,0);self.assertEqual(raw,self.bytes())
 def test_guard_drift_refused_before_writes(self):
  for row in STATE['prerequisites']:
   with self.subTest(guard=row['relative']):
    self.restore();p=self.tree/STATE['project']/row['relative'];p.write_bytes(p.read_bytes()+b'\n');raw=self.bytes()
    self.assertNotEqual(self.apply().returncode,0);self.assertEqual(raw,self.bytes())
 def test_missing_guard_refused_before_writes(self):
  for row in STATE['prerequisites']:
   with self.subTest(guard=row['relative']):
    self.restore();(self.tree/STATE['project']/row['relative']).unlink();raw=self.bytes()
    self.assertNotEqual(self.apply().returncode,0);self.assertEqual(raw,self.bytes())
 def test_symlink_refused_before_writes(self):
  for rel in RELS:
   with self.subTest(managed=rel):
    self.restore();p=self.tree/rel;saved=p.with_suffix('.saved');p.rename(saved);p.symlink_to(saved);raw=self.bytes()
    self.assertNotEqual(self.apply().returncode,0);self.assertEqual(raw,self.bytes())
 def test_hardlink_refused_before_writes(self):
  for rel in RELS:
   with self.subTest(managed=rel):
    self.restore();p=self.tree/rel;os.link(p,p.with_suffix('.alias'));raw=self.bytes();self.assertNotEqual(self.apply().returncode,0);self.assertEqual(raw,self.bytes())
 def test_full_reverse_preserves_actual_before(self):
  self.assertEqual(self.apply().returncode,0)
  command=['git','-C',str(self.tree),'apply','--reverse','--check',str(COMP/STATE['patch'])]
  one=subprocess.run(command,env=self.env,capture_output=True,text=True);self.assertEqual(one.returncode,0,one.stderr)
  two=subprocess.run([x for x in command if x!='--check'],env=self.env,capture_output=True,text=True);self.assertEqual(two.returncode,0,two.stderr)
  self.assertEqual(self.bytes(),{r:(FIX/r).read_bytes()for r in RELS});self.assertEqual(self.verify('--check-prerequisites').returncode,0)
 def test_complete_actual_fixture_and_certified_sonic_hashes(self):
  expected={*RELS,*[STATE['project']+'/'+r['relative']for r in STATE['prerequisites']]}
  self.assertEqual({str(p.relative_to(FIX))for p in FIX.rglob('*')if p.is_file()},expected | {r['relative']for r in STATE['external_prerequisites']})
  for row in STATE['files']:
   self.assertEqual(hashlib.sha256((FIX/STATE['project']/row['relative']).read_bytes()).hexdigest(),row['original_sha256'])
  for row in STATE['prerequisites']:
   raw=(FIX/STATE['project']/row['relative']).read_bytes();self.assertEqual(len(raw),row['bytes']);self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
 def test_old495_renderer_after_backend_before_is_rejected(self):
  self.assertEqual(self.apply().returncode,0);(self.tree/RELS[1]).write_bytes((FIX/RELS[1]).read_bytes());raw=self.bytes()
  self.assertNotEqual(self.apply().returncode,0);self.assertEqual(raw,self.bytes());self.assertNotEqual(self.verify('--require-patched').returncode,0)
 def test_renderer_before_backend_after_is_rejected(self):
  self.assertEqual(self.apply().returncode,0);(self.tree/RELS[0]).write_bytes((FIX/RELS[0]).read_bytes());raw=self.bytes()
  self.assertNotEqual(self.apply().returncode,0);self.assertEqual(raw,self.bytes());self.assertNotEqual(self.verify('--require-patched').returncode,0)
 def test_all_eleven_file_mixed_states_refuse_before_writes(self):
  self.assertEqual(len(RELS),11)
  self.assertEqual(self.apply().returncode,0);final=self.bytes()
  original={r:(FIX/r).read_bytes()for r in RELS}
  # Actual generic preflight rejects every single changed/missing member and its complement.
  masks=[1<<i for i in range(len(RELS))]+[((1<<len(RELS))-1)^(1<<i)for i in range(len(RELS))]
  for mask in masks:
   with self.subTest(mask=mask):
    self.restore()
    for i,r in enumerate(RELS):(self.tree/r).write_bytes(final[r]if mask&(1<<i)else original[r])
    raw=self.bytes();self.assertNotEqual(self.apply().returncode,0);self.assertEqual(raw,self.bytes())
    self.assertNotEqual(self.verify('--require-patched').returncode,0)
 def test_exhaustive_mixed_vector_validator(self):
  self.assertEqual(self.apply().returncode,0);final=self.bytes();self.restore()
  original={r:(FIX/r).read_bytes()for r in RELS}
  spec=importlib.util.spec_from_file_location('queue528_vector',COMP/'verify_source.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  actual_read=Path.read_bytes;selected={}
  def read(p):return selected[p]if p in selected else actual_read(p)
  # Every 2^11-2 mixed full-file identity vector, using the unchanged real validator and in-memory read dependencies.
  for mask in range(1,(1<<len(RELS))-1):
   selected={(self.tree/r):final[r]if mask&(1<<i)else original[r]for i,r in enumerate(RELS)}
   with patch.object(Path,'read_bytes',read):
    with self.assertRaises(ValueError):m.validate(self.tree)
 def test_external_guards_refuse_before_writes(self):
  for row in STATE['external_prerequisites']:
   for mode in ('drift','missing','symlink','hardlink'):
    with self.subTest(guard=row['relative'],mode=mode):
     self.restore();p=self.tree/row['relative']
     if mode=='drift':p.write_bytes(p.read_bytes()+b'\n')
     elif mode=='missing':p.unlink()
     elif mode=='symlink':saved=p.with_suffix('.saved');p.rename(saved);p.symlink_to(saved)
     else:os.link(p,p.with_suffix('.alias'))
     raw=self.bytes();self.assertNotEqual(self.apply().returncode,0);self.assertEqual(raw,self.bytes())
 def test_missing_managed_refuses_before_writes(self):
  for rel in RELS:
   with self.subTest(missing=rel):
    self.restore();(self.tree/rel).unlink();raw={r:(self.tree/r).read_bytes()for r in RELS if r!=rel}
    self.assertNotEqual(self.apply().returncode,0)
    self.assertFalse((self.tree/rel).exists());self.assertEqual(raw,{r:(self.tree/r).read_bytes()for r in raw})
 def test_original_generic_stage_api_owns_only_eleven_managed_files(self):
  def load(name,path):
   spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
  helper=load('private_output512_generic',ROOT/'patches/lib/apply_exact_component.py')
  baseline=load('private_output512_baseline',COMP/'verify_source.py');before=self.bytes()
  stage=self.base/'stage';stage.mkdir()
  with patch.dict(os.environ,self.env,clear=True):patches=helper.prepare_stack(self.tree,COMP,baseline,stage)
  self.assertEqual(before,self.bytes());self.assertEqual(len(patches),1)
  self.assertEqual({str(p.relative_to(stage/'source'))for p in(stage/'source').rglob('*')if p.is_file()},set(RELS))
  self.assertTrue(baseline.validate(stage/'source',require_patched=True))
  for row in STATE['files']:
   self.assertEqual(hashlib.sha256((stage/'source'/STATE['project']/row['relative']).read_bytes()).hexdigest(),row['final_sha256'])

if __name__=='__main__':unittest.main(verbosity=2)
