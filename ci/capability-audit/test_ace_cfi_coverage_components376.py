#!/usr/bin/env python3
"""Actual private exact-component entry replay. No target compiler/resource use."""
from pathlib import Path
import hashlib,importlib.util,json,os,re,shutil,subprocess,sys,tempfile,unittest
R=Path(__file__).resolve().parents[2]
H=R
C=R/'patches/common/foundation/arkui/ace_engine/cfi_coverage'
O=C.parent/'ui_extension_identity_cfi'
Q=R/'patches/common/commonlibrary/qrcode_generator/cfi_metadata'
S=R/'patches/common/third_party/bounds_checking_function/ace_cfi'
P='foundation/arkui/ace_engine'
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
n=load('coverage486',C/'verify_source.py');old=load('identity486',O/'verify_source.py');q=load('qrcode486',Q/'verify_source.py');sec=load('sec486',S/'verify_source.py')
class Source486(unittest.TestCase):
 def setUp(self):
  scratch=Path(tempfile.gettempdir())
  self.t=tempfile.TemporaryDirectory(prefix='source-',dir=scratch);self.addCleanup(self.t.cleanup);self.root=Path(self.t.name)
  self.write('pristine')
 def write(self,state):
  for name,_,_ in n.FILES:
   f=self.root/P/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes((C/'fixtures'/('final' if state=='coverage' else 'original')/P/name).read_bytes())
  for name,_,_ in old.FILES:
   if name=='build/BUILD.gn' and state=='coverage':continue
   f=self.root/P/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes((O/'fixtures'/('original' if state=='pristine' else 'final')/P/name).read_bytes())
  f=self.root/q.PROJECT/'BUILD.gn';f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes((Q/'fixtures'/('final' if state in ('coverage','identity-qrcode','identity-qrcode-sec') else 'original')/q.PROJECT/'BUILD.gn').read_bytes())
  f=self.root/sec.PROJECT/'BUILD.gn';f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes((S/'fixtures'/('final' if state in ('coverage','identity-qrcode-sec') else 'original')/sec.PROJECT/'BUILD.gn').read_bytes())
 def snapshot(self):
  return {str(f.relative_to(self.root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in self.root.rglob('*') if f.is_file() and '.ohos-qemu-patches' not in f.parts}
 def entry(self,component,ok=True):
  # The parent explicitly authorizes only the original helper's scratch git apply.
  # Stop discovery before the shared checkout; the scratch has no index or HEAD.
  env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',GIT_CEILING_DIRECTORIES=str(H),TMPDIR=tempfile.gettempdir())
  for k in ('GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_OBJECT_DIRECTORY','GIT_COMMON_DIR'):env.pop(k,None)
  r=subprocess.run(['/bin/bash',str(component/'apply.sh'),'--source-root',str(self.root)],capture_output=True,text=True,env=env)
  self.assertEqual(r.returncode==0,ok,r.stdout+r.stderr);return r
 def full(self):
  self.entry(O);self.entry(Q);self.entry(S);self.entry(C)
 def test_01_actual_whole_preimages_and_payloads(self):
  for m,c in ((n,C),(old,O),(q,Q),(sec,S)):
   m.metadata()
   for name,b,a in m.FILES:
    self.assertEqual(hashlib.sha256((c/'fixtures/original'/m.PROJECT/name).read_bytes()).hexdigest(),b)
    self.assertEqual(hashlib.sha256((c/'fixtures/final'/m.PROJECT/name).read_bytes()).hexdigest(),a)
 def test_02_real_old_qrcode_new_then_all_repeat(self):
  self.assertEqual(n.preflight(self.root),'pristine');self.full();a=self.snapshot()
  self.assertEqual(n.preflight(self.root),'coverage');self.assertTrue(n.validate(self.root,True));self.assertTrue(old.validate(self.root,True));self.assertTrue(q.validate(self.root,True))
  self.full();self.assertEqual(a,self.snapshot())
 def test_03_old_two_file_API_scope_preserved(self):
  self.assertFalse(old.validate(self.root));self.write('identity');self.assertTrue(old.validate(self.root,True))
 def test_04_original_not_coverage_ready(self):
  with self.assertRaises(ValueError):n.validate(self.root,True)
  self.entry(C,False)
 def test_05_qrcode_required_before_coverage(self):
  self.write('identity');a=self.snapshot();self.entry(C,False);self.assertEqual(a,self.snapshot())
  self.entry(Q);self.assertEqual(n.preflight(self.root),'identity-qrcode');self.entry(C,False);self.entry(S);self.entry(C)
 def test_06_unknown_each_sibling_rejects_old_before_mutation(self):
  names=[(n.PROJECT,name) for name,_,_ in n.FILES]+[(P,'frameworks/core/components_ng/components.gni'),(q.PROJECT,'BUILD.gn'),(sec.PROJECT,'BUILD.gn')]
  for project,name in names:
   self.write('pristine');f=self.root/project/name;f.write_bytes(f.read_bytes()+b'\n# UNREVIEWED\n');a=self.snapshot()
   with self.subTest(name=str(f.relative_to(self.root))):self.entry(O,False);self.assertEqual(a,self.snapshot())
 def test_07_missing_each_sibling_rejects_old_before_mutation(self):
  names=[(n.PROJECT,name) for name,_,_ in n.FILES]+[(P,'frameworks/core/components_ng/components.gni'),(q.PROJECT,'BUILD.gn'),(sec.PROJECT,'BUILD.gn')]
  for project,name in names:
   self.write('pristine');f=self.root/project/name;f.unlink();a=self.snapshot()
   with self.subTest(name=str(f.relative_to(self.root))):self.entry(O,False);self.assertEqual(a,self.snapshot())
 def test_08_each_before_final_mix_rejects(self):
  for name,_,_ in n.FILES:
   self.write('identity');f=self.root/P/name;f.write_bytes((C/'fixtures/final'/P/name).read_bytes());a=self.snapshot()
   with self.subTest(name=name):self.entry(O,False);self.entry(C,False);self.assertEqual(a,self.snapshot())
 def test_09_fake_new_build_after_without_new_siblings_rejects(self):
  self.write('identity');f=self.root/P/'build/BUILD.gn';f.write_bytes((C/'fixtures/final'/P/'build/BUILD.gn').read_bytes())
  with self.assertRaises(ValueError):old.validate(self.root,True)
  self.entry(O,False)
 def test_10_missing_qrcode_metadata_cannot_upgrade(self):
  self.write('coverage');f=self.root/q.PROJECT/'BUILD.gn';f.write_bytes((Q/'fixtures/original'/q.PROJECT/'BUILD.gn').read_bytes());a=self.snapshot();self.entry(O,False);self.entry(C,False);self.assertEqual(a,self.snapshot())
 def test_11_unknown_after_rejects_without_mutation(self):
  self.full();f=self.root/P/'BUILD.gn';f.write_bytes(f.read_bytes()+b'\n# unknown\n');a=self.snapshot();self.entry(O,False);self.entry(C,False);self.assertEqual(a,self.snapshot())
 def test_12_leaf_symlink_rejects(self):
  f=self.root/P/'BUILD.gn';b=f.read_bytes();f.unlink();dest=self.root/'foreign.gn';dest.write_bytes(b);f.symlink_to(dest);self.entry(O,False)
 def test_13_parent_symlink_rejects(self):
  f=self.root/P/'adapter/ohos/entrance';dest=self.root/'foreign';f.rename(dest);f.symlink_to(dest,target_is_directory=True);self.entry(O,False)
 def test_14_official_config_reuse_and_host_gates(self):
  a=(C/'fixtures/original'/P/'BUILD.gn').read_text();z=(C/'fixtures/final'/P/'BUILD.gn').read_text()
  block='''# Source sets do not inherit sanitizer policy from the final libace_compatible.
# Keep CFI metadata and platform link flags on the complete ACE common carrier.
if (is_ohos && current_os == "ohos") {
  ohos_sanitizer_config("ace_cfi_config") {
    sanitize = {
      cfi = true
      cfi_cross_dso = true
      debug = ace_sanitize_debug
    }
  }
}

'''
  add='  if (is_ohos && current_os == "ohos") {\n    configs = [ ":ace_cfi_config" ]\n  }\n'
  self.assertEqual(z.count(block),1);self.assertEqual(z.count(add),1);self.assertEqual(z.replace(block,'',1).replace(add,'',1),a)
  for forbidden in ('-fsanitize','use_cfi =','is_asan =','no_sanitize','ignorelist'):self.assertNotIn(forbidden,z[len(a):] if False else block+add)
 def test_15_factory_return_types_match_real_consumer(self):
  consumer=(C/'fixtures/consumer/ui_content.cpp').read_text();before=(C/'fixtures/original'/P/'adapter/ohos/entrance/ui_content_impl.cpp').read_text();after=(C/'fixtures/final'/P/'adapter/ohos/entrance/ui_content_impl.cpp').read_text()
  for typedef,fun,args in [('CreateFunc','CreateUIContent','void*, void*, int32_t'),('CreateCardFunc','CreateFormContent','void*, void*, bool'),('CreateFunction','CreateSubWindowUIContent','void*'),('GetUIContentFunc','GetUIContent','int32_t')]:
   self.assertRegex(consumer,r'using '+typedef+r' = UIContent\* \(\*\)\('+re.escape(args)+r'\);')
   b='extern "C" ACE_FORCE_EXPORT void* OHOS_ACE_'+fun+'(';a=b.replace('void* OHOS_ACE_','UIContent* OHOS_ACE_');self.assertEqual(before.count(b),1);self.assertEqual(after.count(a),1);after=after.replace(a,b)
  self.assertEqual(after,before)
 def test_16_all_3_missing_link_carriers_add_only_official_config(self):
  for name,anchor in [('adapter/ohos/build/BUILD.gn','  ohos_shared_library(module_name) {\n'),('build/BUILD.gn','ohos_shared_library("libace_compatible_components") {\n')]:
   a=(C/'fixtures/original'/P/name).read_text();z=(C/'fixtures/final'/P/name).read_text();indent='    ' if name.startswith('adapter') else '  ';addition=indent+'if (is_ohos && current_os == "ohos") {\n'+indent+'  configs = [ "$ace_root:ace_cfi_config" ]\n'+indent+'}\n';self.assertEqual(z,a.replace(anchor,anchor+addition))
  name='build/ace_lib.gni';a=(C/'fixtures/original'/P/name).read_text();z=(C/'fixtures/final'/P/name).read_text();addition='    if (is_ohos && current_os == "ohos") {\n      configs += [ "$ace_root:ace_cfi_config" ]\n    }\n';self.assertEqual(z.replace(addition,'',1),a)
 def test_17_qrcode_only_standard_ohos_existing_flags_preserved(self):
  a=(Q/'fixtures/original'/q.PROJECT/'BUILD.gn').read_text();z=(Q/'fixtures/final'/q.PROJECT/'BUILD.gn').read_text();addition='''    # Its real code members are linked into the CFI-protected ACE DSOs.
    if (is_ohos && current_os == "ohos") {
      sanitize = {
        cfi = true
        cfi_cross_dso = true
      }
    }
''';self.assertEqual(z.count(addition),1);self.assertEqual(z.replace(addition,'',1),a);self.assertLess(z.index('} else {\n  ohos_static_library'),z.index(addition))
 def test_18_old_patch_stack_pin_is_preserved(self):
  self.assertEqual(old.PATCH_SHA256,'e033023a190cdb38a257c55f16dbcb29da80a5e00018f332829a0d64be305ebb')
  self.assertEqual(len(old.FILES),2);old.metadata()
 def test_19_original_common_helpers_byte_identical(self):
  expected={'apply_exact_component.py': 'be60d0be4e741af2768f1936779f94aac5d778cd2d627db898353b3b3d47cc65', 'exact_source_states.py': 'd876f46528b81323414866a97987ac72d82a5b7e748cddda8d8fef01e239e1a2'}
  for name,sha in expected.items():self.assertEqual(hashlib.sha256((R/'patches/lib'/name).read_bytes()).hexdigest(),sha)
 def test_20_bash_source_syntax(self):
  for c in (O,C,Q,S):self.assertEqual(subprocess.run(['/bin/bash','-n',str(c/'apply.sh')],capture_output=True).returncode,0)
 def test_21_source_only_CLI_keeps_all_runtime_gates_false(self):
  self.full();r=subprocess.run([sys.executable,'-B',str(C/'verify_source.py'),'--source-root',str(self.root),'--require-patched'],capture_output=True,text=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'));self.assertEqual(r.returncode,0,r.stderr);d=json.loads(r.stdout);self.assertTrue(d['patched']);self.assertFalse(d['compiled']);self.assertFalse(d['CFI_linked_input_closure_verified']);self.assertFalse(d['runtime_passed']);self.assertFalse(d['first_artifact_behavior_gate_passed'])
 def test_22_global_secstatic_shared_Lite_bytes_unchanged(self):
  a=(S/'fixtures/original'/sec.PROJECT/'BUILD.gn').read_text();z=(S/'fixtures/final'/sec.PROJECT/'BUILD.gn').read_text();start=z.index('  # Only the ACE smartlayout consumer');stop=z.index('  ohos_shared_library("libsec_shared") {',start);self.assertEqual(z[:start]+z[stop:],a)
  original=a[a.index('  ohos_static_library("libsec_static") {'):a.index('  ohos_shared_library("libsec_shared") {')];variant=z[start:stop];self.assertIn('sources = libsec_sources',variant);self.assertIn('public_configs = [ ":libsec_public_config" ]',variant)
  for flag in ('-D_INC_STRING_S','-D_INC_WCHAR_S','-D_SECIMP=//','-D_STDIO_S_DEFINED','-D_INC_STDIO_S','-D_INC_STDLIB_S','-D_INC_MEMORY_S'):self.assertEqual(original.count(flag),variant.count(flag))
 def test_23_smartlayout_only_fixed_OHOS_variant(self):
  name='frameworks/core/components_ng/pattern/smart_layout/engine/BUILD.gn';a=(C/'fixtures/original'/P/name).read_text();z=(C/'fixtures/final'/P/name).read_text();extra='  if (is_ohos && current_os == "ohos") {\n    external_deps -= [ "bounds_checking_function:libsec_static" ]\n    deps = [ "//third_party/bounds_checking_function:libsec_static_ace_cfi" ]\n  }\n';self.assertEqual(z.replace(extra,'',1),a);self.assertEqual(z.count(extra),1)
 def test_24_original_secstatic_cannot_count_as_variant_ready(self):
  self.write('coverage');p=self.root/sec.PROJECT/'BUILD.gn';p.write_bytes((S/'fixtures/original'/sec.PROJECT/'BUILD.gn').read_bytes());a=self.snapshot();self.entry(O,False);self.entry(C,False);self.assertEqual(self.snapshot(),a)
if __name__=='__main__':unittest.main()
