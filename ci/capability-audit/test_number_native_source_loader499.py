"""Local source-loader/cache tests only; no Owner/resource/raw admission run."""
from pathlib import Path
import ast
import builtins
import copy
import hashlib
import importlib._bootstrap_external
import importlib.machinery
import importlib.util
import marshal
import os
import shutil
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
FIXTURES=ROOT/'ci/capability-audit/fixtures/number_native_source_loader499'
BEFORE=FIXTURES/'owner494_before.py'
OWNER=FIXTURES/'owner499_final.py'
ACTIVE_OWNER=ROOT/'ci/capability-audit/number_supported580/templates/normal/number/owner499.py'
SOURCE=ROOT
OWNER_PATCH=ROOT/'ci/capability-audit/number_native497/patches/kit411/candidate/number_owner411.py.patch'
TEMP_PREFIX='number-native-source-loader499-'
FIXTURE_PINS={
 'owner494_before.py':('fbc18add0cb642175ea31061283a313eeb1ad950174ef20b31c8bae707982b2d',48073),
 'owner499_final.py':('ca8b4551b8aca0a7091415e63a839f3a74a547b3c3f12d8533aaa189fa8dff0b',59272),
}
PREFIX='number_native496'
NAMES=[PREFIX,PREFIX+'.consumer496',PREFIX+'.evidence_join496']

def namespace():return {name:module for name,module in sys.modules.items() if type(name) is str and (name==PREFIX or name.startswith(PREFIX+'.'))}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def fixture_bytes(path):
 expected,size=FIXTURE_PINS[path.name]
 raw=path.read_bytes()
 if path.resolve()!=path or path.is_symlink() or len(raw)!=size or hashlib.sha256(raw).hexdigest()!=expected:
  raise ValueError('fixed repository Owner fixture changed: '+path.name)
 return raw

def fixture_nodes(path):
 return {node.name:node for node in ast.parse(fixture_bytes(path)).body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}

def dump(node):return ast.dump(node,include_attributes=False)

def active_canonical_pins():
 # Read only the reviewed active Owner's literal pin table, never execute it.
 nodes=[node.value for node in ast.parse(ACTIVE_OWNER.read_bytes(),filename=str(ACTIVE_OWNER)).body
  if isinstance(node,ast.Assign) and len(node.targets)==1 and
  isinstance(node.targets[0],ast.Name) and node.targets[0].id=='NATIVE496_CANONICAL_PINS']
 if len(nodes)!=1:raise ValueError('one active literal canonical pin table required')
 value=ast.literal_eval(nodes[0])
 if type(value) is not dict or len(value)!=9:raise ValueError('active nine-source pin table required')
 for relative,row in value.items():
  if (type(relative) is not str or type(row) is not dict or set(row)!={'sha256','bytes'} or
      type(row['sha256']) is not str or len(row['sha256'])!=64 or
      any(c not in '0123456789abcdef' for c in row['sha256']) or
      type(row['bytes']) is not int or row['bytes']<=0):
   raise ValueError('active literal source hash/size pin required')
 return value

def load_owner():
 name='_HOST_ONLY_number499_owner_'+os.urandom(8).hex()
 raw=fixture_bytes(OWNER);module=types.ModuleType(name);module.__file__=str(OWNER)
 sys.modules[name]=module
 try:exec(compile(raw,str(OWNER),'exec',dont_inherit=True),module.__dict__)
 except BaseException:
  if sys.modules.get(name) is module:del sys.modules[name]
  raise
 return module


class Loader499Tests(unittest.TestCase):
 def setUp(self):
  self.previous=namespace()
  for name in self.previous:del sys.modules[name]
  self.temp=tempfile.TemporaryDirectory(prefix=TEMP_PREFIX);self.root=Path(self.temp.name).resolve()
  self.n=load_owner();self.n.R=self.root
  active=active_canonical_pins();self.assertEqual(set(active),set(self.n.NATIVE496_CANONICAL_PINS))
  self.n.NATIVE496_CANONICAL_PINS=active
  for relative,row in self.n.NATIVE496_CANONICAL_PINS.items():
   source=SOURCE/relative;self.assertEqual(sha(source),row['sha256'])
   target=self.root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
  # Only source-loader shape. Never source_modules(), run(), Owner or admission.
  self.n.SOURCE_COMMIT='1'*40;self.n.KIT=self.root;self.n.KIT_SHA='2'*64
 def tearDown(self):
  for name in list(namespace()):del sys.modules[name]
  sys.modules.update(self.previous);sys.modules.pop(self.n.__name__,None);self.temp.cleanup()
 def test_verified_bytes_real_dataclass_relative_import_and_repeat_owned_objects(self):
  adapter=self.n.native_module496();initial=namespace();self.assertEqual(set(initial),set(NAMES))
  core=sys.modules[PREFIX+'.consumer496'];package=sys.modules[PREFIX]
  self.assertIs(adapter.core,core);self.assertIs(package.consumer496,core);self.assertIs(package.evidence_join496,adapter)
  self.assertEqual(core.Event.__module__,PREFIX+'.consumer496')
  self.assertIs(core.Event.__init__.__globals__,core.__dict__)
  self.assertIs(self.n.native_module496(),adapter)
  self.assertEqual(namespace(),initial)
  for name,module in initial.items():
   self.assertIs(module.__spec__.loader,module.__loader__)
   self.assertIsNone(module.__cached__);self.assertFalse(module.__spec__.has_location)
   self.assertFalse(hasattr(module.__loader__,'get_code'))
  with self.assertRaisesRegex(ValueError,'original actual compile/recheck/ELF/profile admission'):
   data={key:'HOST_MODEL_NOT_ACTUAL' for key in ('hdc','target','source_commit','archive_sha256','before','after','generation_captures','bridge_calls','caller','number_image_report','loader_image_report','system_image','emitter_elfs','build_inputs','producer_sources')}
   data['schema']='number-native-consumer496/v1';adapter.review(data)
 def test_first_load_rejects_all_preexisting_expected_filename_cache_shapes(self):
  for name in (*NAMES,PREFIX+'.foreign'):
   fake=types.ModuleType(name);fake.__file__=str(self.root/'ci/capability-audit/number_native496/evidence_join496.py')
   fake.__path__=['/HOST_ONLY_FOREIGN_PACKAGE'];fake.collect_bridge496=lambda **k:dict(FAKE=True)
   with self.subTest(name=name),patch.dict(sys.modules,{name:fake}):
    before=namespace()
    with self.assertRaisesRegex(ValueError,'preexisting native namespace'):self.n.native_module496()
    self.assertEqual(namespace(),before);self.assertIs(sys.modules[name],fake)
 def test_nonliteral_namespace_keys_and_replaced_module_table_are_refused(self):
  class HostNamespace(str):pass
  name=HostNamespace(PREFIX+'.foreign');foreign=types.ModuleType(str(name))
  with patch.dict(sys.modules,{name:foreign}):
   with self.assertRaisesRegex(ValueError,'nonliteral native namespace'):self.n.native_module496()
   self.assertIs(sys.modules[name],foreign)
  actual=sys.modules;replacement=dict(actual)
  with patch.object(sys,'modules',replacement):
   with self.assertRaisesRegex(ValueError,'module table identity changed'):self.n.native_module496()
   self.assertEqual(replacement,actual)
 def test_valid_timestamp_pyc_for_all_three_modules_is_never_loaded(self):
  for name,filename in ((PREFIX,'__init__.py'),(PREFIX+'.consumer496','consumer496.py'),(PREFIX+'.evidence_join496','evidence_join496.py')):
   source=self.root/'ci/capability-audit/number_native496'/filename;info=source.stat()
   code=compile("raise AssertionError('HOST_499_STALE_PYC_EXECUTED')",str(source),'exec')
   binary=importlib._bootstrap_external._code_to_timestamp_pyc(code,int(info.st_mtime),info.st_size)
   cache=Path(importlib.util.cache_from_source(str(source)));cache.parent.mkdir(exist_ok=True);cache.write_bytes(binary)
  original=importlib.machinery.SourceFileLoader.get_code;calls=[]
  def forbid_native(loader,fullname):
   if fullname==PREFIX or fullname.startswith(PREFIX+'.'):
    calls.append(fullname);raise AssertionError('ordinary native loader forbidden')
   return original(loader,fullname)
  with patch.object(importlib.machinery.SourceFileLoader,'get_code',forbid_native):
   adapter=self.n.native_module496()
  self.assertEqual(calls,[]);self.assertTrue(callable(adapter.collect_bridge496))
 def test_reuse_rejects_metadata_loader_path_children_and_core_identity_tampering(self):
  adapter=self.n.native_module496();package=sys.modules[PREFIX];core=adapter.core
  fake=types.ModuleType(PREFIX+'.consumer496');fake.__file__=core.__file__
  replacements=[(core,'__file__','/HOST_ONLY_FOREIGN/core.py'),(core,'__package__','HOST_FOREIGN'),
    (core,'__loader__',object()),(core,'__cached__','/HOST_ONLY/old.pyc'),
    (core,'__spec__',copy.copy(core.__spec__)),(core.__spec__,'origin','/HOST_ONLY_FOREIGN/core.py'),
    (core.__spec__,'loader',object()),(core.__spec__,'loader_state',object()),
    (core.__spec__,'_initializing',True),(core,'__name__','HOST_FOREIGN'),
    (core,'__path__',('/HOST_ONLY_FOREIGN',)),(package,'__path__',('/HOST_ONLY_FOREIGN',)),
    (package.__spec__,'submodule_search_locations',('/HOST_ONLY_FOREIGN',)),
    (package,'consumer496',fake),(package,'evidence_join496',fake),(adapter,'core',fake)]
  for obj,key,value in replacements:
   with self.subTest(key=key,value=value),patch.object(obj,key,value,create=True):
    before=namespace()
    with self.assertRaises(ValueError):self.n.native_module496()
    self.assertEqual(namespace(),before)
   self.assertIs(self.n.native_module496(),adapter)
  # Changing both public package path references cannot replace the private
  # tuple identity even when its string contents still look canonical.
  replacement=tuple([str(Path(package.__file__).parent)])
  with patch.object(package,'__path__',replacement),patch.object(package.__spec__,'submodule_search_locations',replacement):
   with self.assertRaises(ValueError):self.n.native_module496()
 def test_reuse_refuses_added_or_replaced_namespace_and_never_deletes_foreign(self):
  adapter=self.n.native_module496();foreign=types.ModuleType(PREFIX+'.foreign')
  for name in (PREFIX+'.foreign',*NAMES):
   with self.subTest(name=name),patch.dict(sys.modules,{name:foreign}):
    before=namespace()
    with self.assertRaises(ValueError):self.n.native_module496()
    self.assertEqual(namespace(),before);self.assertIs(sys.modules[name],foreign)
  self.assertIs(self.n.native_module496(),adapter)
 def test_all_nine_disk_sources_are_rechecked_before_first_load_and_reuse(self):
  for relative in self.n.NATIVE496_CANONICAL_PINS:
   path=self.root/relative;original=path.read_bytes();path.write_bytes(original+b'\n')
   with self.subTest(relative=relative),self.assertRaisesRegex(ValueError,'canonical native source changed'):self.n.native_module496()
   self.assertFalse(namespace());path.write_bytes(original)
  adapter=self.n.native_module496()
  path=self.root/'ci/capability-audit/number_native496/support/guest_ui.py';path.write_bytes(path.read_bytes()+b'\n')
  before=namespace()
  with self.assertRaises(ValueError):self.n.native_module496()
  self.assertEqual(namespace(),before);self.assertIs(sys.modules[NAMES[-1]],adapter)
 def test_initialization_failure_removes_only_self_insertions_and_allows_safe_retry(self):
  original_exec=builtins.exec
  def fail_adapter(code,globals=None,locals=None):
   if getattr(code,'co_filename','').endswith('/number_native496/evidence_join496.py'):
    raise RuntimeError('HOST_ONLY_INJECTED_SOURCE_INIT_FAILURE')
   return original_exec(code,globals,locals)
  with patch.object(builtins,'exec',fail_adapter):
   with self.assertRaisesRegex(RuntimeError,'HOST_ONLY_INJECTED'):self.n.native_module496()
  self.assertFalse(namespace())
  self.assertTrue(callable(self.n.native_module496().collect_bridge496))
 def test_initialization_failure_preserves_foreign_replacement_and_new_namespace(self):
  original_exec=builtins.exec;foreign=types.ModuleType(NAMES[1]);added=types.ModuleType(PREFIX+'.foreign')
  def fail_adapter(code,globals=None,locals=None):
   if getattr(code,'co_filename','').endswith('/number_native496/evidence_join496.py'):
    sys.modules[NAMES[1]]=foreign;sys.modules[PREFIX+'.foreign']=added
    raise RuntimeError('HOST_ONLY_FOREIGN_REPLACEMENT_DURING_INIT')
   return original_exec(code,globals,locals)
  with patch.object(builtins,'exec',fail_adapter):
   with self.assertRaisesRegex(RuntimeError,'HOST_ONLY_FOREIGN'):self.n.native_module496()
  self.assertEqual(namespace(),{NAMES[1]:foreign,PREFIX+'.foreign':added})
  with self.assertRaisesRegex(ValueError,'preexisting native namespace'):self.n.native_module496()
  self.assertIs(sys.modules[NAMES[1]],foreign);self.assertIs(sys.modules[PREFIX+'.foreign'],added)
 def test_changed_module_class_is_refused_before_custom_attribute_access(self):
  adapter=self.n.native_module496();core=adapter.core
  class HostForeignModule(types.ModuleType):
   def __getattribute__(self,name):
    if name=='__dict__':raise AssertionError('foreign module getter executed')
    return super().__getattribute__(name)
  core.__class__=HostForeignModule
  with self.assertRaisesRegex(ValueError,'changed module type'):self.n.native_module496()
  core.__class__=types.ModuleType
  self.assertIs(self.n.native_module496(),adapter)
 def test_spec_and_cached_module_with_spoofing_getattr_cannot_hide_missing_metadata(self):
  adapter=self.n.native_module496();core=adapter.core;actual=core.__dict__.pop('__file__')
  core.__getattr__=lambda key:actual if key=='__file__' else None
  with self.assertRaises(ValueError):self.n.native_module496()
  core.__dict__['__file__']=actual;del core.__getattr__
  self.assertIs(self.n.native_module496(),adapter)


class Overlay499Tests(unittest.TestCase):
 def test_original_owner_bridge_finally_posthook_and_unknown_future_gates_stay(self):
  original=fixture_nodes(BEFORE);updated=fixture_nodes(OWNER)
  for name in original.keys()-{'source_modules','run'}:self.assertEqual(dump(original[name]),dump(updated[name]),name)
  # Compare directly to494, excluding only the two reviewed source gates,
  # the new exact capture pin, and the unique independent post-collect hook.
  sources=copy.deepcopy(updated['source_modules'])
  gates={'integration497_ready','native_module496'}
  removed=[node for node in sources.body if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and
           isinstance(node.value.func,ast.Name) and node.value.func.id in gates]
  self.assertEqual(len(removed),2)
  sources.body=[node for node in sources.body if node not in removed]
  class RestoreBeforePin(ast.NodeTransformer):
   def visit_Constant(self,node):
    if node.value=='e0cc7372d13c71d3d08269d42ea1c71738d9672761ba4cf17a66d47e8c236bb6':
     return ast.copy_location(ast.Constant(value='0d3e7f9a238095e66fb9cd17806e62fa9ef518339940a376a515afa19f1571c5'),node)
    return node
  self.assertEqual(dump(original['source_modules']),dump(RestoreBeforePin().visit(sources)))
  class RemoveIndependentHook(ast.NodeTransformer):
   count=0
   def visit_Assign(self,node):
    target=node.targets[0]
    if ((isinstance(target,ast.Name) and target.id=='native_index496') or
        (isinstance(target,ast.Subscript) and isinstance(target.value,ast.Name) and target.value.id=='report' and
         isinstance(target.slice,ast.Constant) and target.slice.value=='native_chain496_reviews')):
     self.count+=1;return None
    return self.generic_visit(node)
  remove=RemoveIndependentHook();runtime=remove.visit(copy.deepcopy(updated['run']))
  self.assertEqual(remove.count,2);self.assertEqual(dump(original['run']),dump(runtime))
  n=load_owner();self.assertIsNone(n.SOURCE_COMMIT);self.assertIsNone(n.KIT);self.assertIsNone(n.KIT_SHA)
  with self.assertRaisesRegex(ValueError,'future.*HEAD pending'):n.source_modules()
  sys.modules.pop(n.__name__,None)
 def test_fixed_before_overlay_roundtrip_without_git_index_or_target_tools(self):
  import subprocess,json
  receipts=[]
  with tempfile.TemporaryDirectory(prefix=TEMP_PREFIX) as temp:
   root=Path(temp).resolve();before_path=root/'kit411/candidate/number_owner411.py'
   before_path.parent.mkdir(parents=True);before_path.write_bytes(fixture_bytes(BEFORE))
   patchfile=OWNER_PATCH;env=dict(os.environ,GIT_CEILING_DIRECTORIES=str(root.parent))
   for flags in (['--check'],[],['--reverse','--check'],['--reverse']):
    argv=['/usr/bin/git','-C',str(root),'apply',*flags,str(patchfile)]
    run=subprocess.run(argv,capture_output=True,env=env);self.assertEqual(run.returncode,0,run.stderr)
    receipts.append(dict(argv=argv,exit_code=run.returncode,stdout=run.stdout.decode(),stderr=run.stderr.decode()))
    expected=OWNER if flags==[] else BEFORE
    if flags in ([],['--reverse']):self.assertEqual((root/'kit411/candidate/number_owner411.py').read_bytes(),expected.read_bytes())
  output=os.environ.get('NUMBER499_EVIDENCE_OUTPUT')
  if output:
   path=Path(output);path.mkdir(parents=True,exist_ok=False)
   (path/'source-roundtrip.json').write_text(json.dumps(dict(scope='host source roundtrip only',commands=receipts),indent=2)+'\n')


if __name__=='__main__':unittest.main(verbosity=2)
