#!/usr/bin/env python3
"""Portable finite flag/parser/ELF/consumer models; no target-build proof."""
from pathlib import Path
import importlib.util,struct,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location('guard486',ROOT/'ci/capability-audit/ace_cfi_closure_guard.py');g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
BASE=['-flto=thin','-fsanitize=cfi','-fsanitize-cfi-cross-dso','-fvisibility=default']
class Guard(unittest.TestCase):
 def test_01_effective_original_full_mode(self):self.assertTrue(g.check_flags(BASE,'HOST-MODEL')['vcall'])
 def test_02_real_form_mode_not_false_rejected(self):self.assertTrue(g.check_flags(BASE+['-fno-sanitize=cfi-nvcall','-fno-sanitize=cfi','-fsanitize=cfi-vcall','-fsanitize=cfi-icall'],'HOST-form-MODEL')['icall'])
 def test_03_late_disable_cfi_rejected(self):
  with self.assertRaisesRegex(ValueError,'incomplete'):g.check_flags(BASE+['-fno-sanitize=cfi'],'HOST')
 def test_04_late_disable_icall_rejected(self):
  with self.assertRaisesRegex(ValueError,'incomplete'):g.check_flags(BASE+['-fno-sanitize=cfi-icall'],'HOST')
 def test_05_late_disable_cross_rejected(self):
  with self.assertRaisesRegex(ValueError,'incomplete'):g.check_flags(BASE+['-fno-sanitize-cfi-cross-dso'],'HOST')
 def test_06_late_disable_lto_rejected(self):
  with self.assertRaisesRegex(ValueError,'incomplete'):g.check_flags(BASE+['-fno-lto'],'HOST')
 def test_07_vcall_only_cannot_replace_icall(self):
  with self.assertRaisesRegex(ValueError,'incomplete'):g.check_flags(['-fsanitize=cfi-vcall','-flto','-fsanitize-cfi-cross-dso','-fvisibility=default'],'HOST')
 def test_08_hidden_visibility_rejected(self):
  with self.assertRaisesRegex(ValueError,'visibility'):g.check_flags(BASE+['-fvisibility=hidden'],'HOST')
 def test_09_recover_rejected(self):
  with self.assertRaisesRegex(ValueError,'recovery'):g.check_flags(BASE+['-fsanitize-recover=cfi'],'HOST')
 def test_10_late_reenable_evaluates_order(self):self.assertTrue(g.check_flags(BASE+['-fno-sanitize=cfi','-fsanitize=cfi-vcall,cfi-icall'],'HOST')['vcall'])
 def test_11_unbound_variable_rejected(self):
  with self.assertRaisesRegex(ValueError,'unbound'):g.expand('$untracked',{})
 def test_12_recursive_variable_rejected(self):
  with self.assertRaisesRegex(ValueError,'recursive'):g.expand('$loop',dict(loop='$loop'))
 def test_13_escaped_literal_dollar(self):self.assertEqual(g.expand('$$ORIGIN',{}),'$ORIGIN')
 def test_17_unsafe_path_rejected(self):
  with self.assertRaises(ValueError):g.safe(ROOT,'../foreign')
 def test_18_empty_ar_is_exact_eight_bytes(self):
  with tempfile.TemporaryDirectory(dir=None) as t:
   p=Path(t)/'empty.a';p.write_bytes(b'!<arch>\n');self.assertEqual(g.ar_members(p),{});p.write_bytes(b'!<arch>\nOTHER')
   with self.assertRaises(ValueError):g.ar_members(p)
 def test_19_data_ELF_exec_section_rejected(self):
  with tempfile.TemporaryDirectory(dir=None) as t:
   p=Path(t)/'data.o';b=bytearray(64+64);b[:6]=b'\x7fELF\x02\x01';struct.pack_into('<HH',b,16,1,183);struct.pack_into('<Q',b,40,64);struct.pack_into('<HH',b,58,64,1);struct.pack_into('<IIQQQQIIQQ',b,64,0,1,4,0,0,1,0,0,1,0);p.write_bytes(b)
   with self.assertRaisesRegex(ValueError,'executable'):g.data_only_elf(p,183)
 def test_20_data_ELF_wrong_ABI_rejected(self):
  with tempfile.TemporaryDirectory(dir=None) as t:
   p=Path(t)/'data.o';b=bytearray(128);b[:6]=b'\x7fELF\x02\x01';struct.pack_into('<HH',b,16,1,62);p.write_bytes(b)
   with self.assertRaisesRegex(ValueError,'ABI'):g.data_only_elf(p,183)
 def test_21_no_resource_or_success_input_framework(self):
  text=(ROOT/'ci/capability-audit/ace_cfi_closure_guard.py').read_text()
  for forbidden in ('subprocess','Popen','os.system','runtime_passed=True','first_artifact_behavior_gate_passed=True'):self.assertNotIn(forbidden,text.replace('resource subprocesses','resource calls'))
 def test_22_symbol_visibility_options_are_not_link_inputs(self):
  for token in ('-Wl,--exclude-libs=libunwind_llvm.a','--exclude-libs=libunwind_llvm.a','-Wl,--exclude-libs,libunwind_llvm.a'):
   g.check_hidden_inputs([token],set())
 def test_23_real_hidden_archive_inputs_reject(self):
  for token in ('foreign.a','-Wl,/foreign/evil.o'):
   with self.assertRaisesRegex(ValueError,'hidden static'):g.check_hidden_inputs([token],set())
 def model_dso(self,path,machine=183,kind=3,symbol=b'__cfi_check',defined=True):
  # Minimal legal ELF/dynsym shape ONLY; not a compiled executable function.
  strings=b'\0'+symbol+b'\0';buf=bytearray(64);buf[:6]=b'\x7fELF\x02\x01';struct.pack_into('<HH',buf,16,kind,machine)
  text=64;buf+=b'\0'*16;strstart=len(buf);buf+=strings
  while len(buf)%8:buf+=b'\0'
  symstart=len(buf);buf+=b'\0'*24;buf+=struct.pack('<IBBHQQ',1,18,0,1 if defined else 0,0x1000,16)
  shoff=len(buf);headers=[(0,0,0,0,0,0,0,0,0,0),(0,1,6,0x1000,text,16,0,0,16,0),(0,3,0,0,strstart,len(strings),0,0,1,0),(0,11,0,0,symstart,48,2,0,8,24)]
  for header in headers:buf+=struct.pack('<IIQQQQIIQQ',*header)
  struct.pack_into('<Q',buf,40,shoff);struct.pack_into('<HH',buf,58,64,4);path.write_bytes(buf)
 def test_24_legal_ELF_dynsym_MODEL_only(self):
  with tempfile.TemporaryDirectory(dir=None) as t:
   p=Path(t)/'model.so';self.model_dso(p);v=g.cfi_dso_elf(p,183);self.assertEqual(v['exported_cfi_check']['name'],'__cfi_check');self.assertFalse(v['CFI_type_membership_verified'])
 def test_25_empty_and_nonELF_DSO_rejected(self):
  with tempfile.TemporaryDirectory(dir=None) as t:
   p=Path(t)/'model.so'
   for raw in (b'',b'NOT AN ELF'):
    p.write_bytes(raw)
    with self.assertRaises(ValueError):g.cfi_dso_elf(p,183)
 def test_26_wrong_DSO_arch_rejected(self):
  with tempfile.TemporaryDirectory(dir=None) as t:
   p=Path(t)/'model.so';self.model_dso(p,machine=62)
   with self.assertRaisesRegex(ValueError,'ABI'):g.cfi_dso_elf(p,183)
 def test_27_DSO_rel_not_dyn_rejected(self):
  with tempfile.TemporaryDirectory(dir=None) as t:
   p=Path(t)/'model.so';self.model_dso(p,kind=1)
   with self.assertRaisesRegex(ValueError,'ET_DYN'):g.cfi_dso_elf(p,183)
 def test_28_DSO_missing_check_rejected(self):
  with tempfile.TemporaryDirectory(dir=None) as t:
   p=Path(t)/'model.so';self.model_dso(p,symbol=b'not_cfi')
   with self.assertRaisesRegex(ValueError,'missing'):g.cfi_dso_elf(p,183)
 def test_29_DSO_check_UND_rejected(self):
  with tempfile.TemporaryDirectory(dir=None) as t:
   p=Path(t)/'model.so';self.model_dso(p,defined=False)
   with self.assertRaisesRegex(ValueError,'defined exported'):g.cfi_dso_elf(p,183)
 def consumer_model(self,root):
  # Restricted parse-only model: no artifact bytes or production build claim.
  q='obj/commonlibrary/qrcode_generator/libqrcodegen.a';sec='obj/third_party/bounds_checking_function/libsec_static_ace_cfi.a'
  outputs=['arkui/ace_engine/libace_compatible.z.so','arkui/ace_engine/libace_compatible_components.z.so','arkui/ace_engine/libarkui_qrcode.z.so']
  text=''.join('build '+o+': solink '+q+'\n' for o in outputs)+'build arkui/ace_engine/libsmartlayout.z.so: solink '+sec+'\n';(root/'model.ninja').write_text(text)
 def test_30_global_consumer_finite_MODEL(self):
  with tempfile.TemporaryDirectory(dir=None) as t:
   p=Path(t);self.consumer_model(p);self.assertEqual(sum(map(len,g.scan_archive_consumers(p).values())),4)
 def test_31_foreign_qrcode_consumer_refuses(self):
  with tempfile.TemporaryDirectory(dir=None) as t:
   p=Path(t);self.consumer_model(p);(p/'foreign.ninja').write_text('build foreign.z.so: solink obj/commonlibrary/qrcode_generator/libqrcodegen.a\n')
   with self.assertRaisesRegex(ValueError,'unreviewed'):g.scan_archive_consumers(p)
 def test_32_foreign_secvariant_consumer_refuses(self):
  with tempfile.TemporaryDirectory(dir=None) as t:
   p=Path(t);self.consumer_model(p);(p/'foreign.ninja').write_text('build foreign.z.so: solink obj/third_party/bounds_checking_function/libsec_static_ace_cfi.a\n')
   with self.assertRaisesRegex(ValueError,'unreviewed'):g.scan_archive_consumers(p)
 def test_33_missing_real_consumer_refuses(self):
  with tempfile.TemporaryDirectory(dir=None) as t:
   p=Path(t);self.consumer_model(p);f=p/'model.ninja';f.write_text('\n'.join(x for x in f.read_text().splitlines() if 'libarkui_qrcode' not in x)+'\n')
   with self.assertRaisesRegex(ValueError,'missing fixed'):g.scan_archive_consumers(p)
 def test_34_platform_named_search_allowlist(self):
  g.check_hidden_inputs(['-lunwind','-lc++','-lc','-ldl','-lm'],set())
  for tokens in (['-lforeign'],['-Wl,-Bstatic','-lc'],['-l:foreign.a'],['-Wl,--whole-archive','-lc']):
   with self.assertRaises(ValueError):g.check_hidden_inputs(tokens,set())
 def test_35_three_actual_link_fields_same_parser_reject_hidden(self):
  for field in ('ldflags','libs','solibs'):
   e=dict(inputs=[],values={field:'foreign.a'})
   self.assertIn('foreign.a',g.linkage(e)['names'])
   with self.assertRaisesRegex(ValueError,'hidden static'):g.checked_linkage(dict(inputs=[],values={field:('--sysroot=obj/third_party/musl foreign.a' if field=='ldflags' else 'foreign.a'),**({'ldflags':'--sysroot=obj/third_party/musl'} if field!='ldflags' else {})}),(),'aarch64-linux-ohos')
 def test_36_global_consumer_all_3_fields(self):
  for field in ('ldflags','libs','solibs'):
   with tempfile.TemporaryDirectory(dir=None) as t:
    root=Path(t);self.consumer_model(root);(root/'outside.ninja').write_text('build outside.z.so: solink\n  '+field+' = obj/commonlibrary/qrcode_generator/libqrcodegen.a\n')
    with self.assertRaisesRegex(ValueError,'unreviewed'):g.scan_archive_consumers(root)
 def test_37_recovery_all_disable_is_ordered(self):
  self.assertFalse(g.check_flags(BASE+['-fsanitize-recover=cfi','-fno-sanitize-recover=all'],'HOST MODEL')['recover_cfi'])
 def test_38_unknown_library_paths_and_modes_rejected(self):
  for token in ('-L/tmp/foreign','-Wl,--library-path=/tmp/foreign','@foreign.rsp'):
   with self.assertRaises(ValueError):g.check_hidden_inputs([token],set())
if __name__=='__main__':unittest.main()
