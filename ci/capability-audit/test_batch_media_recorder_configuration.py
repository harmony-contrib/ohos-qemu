"""Actual pinned public Recorder configuration functions; controlled inner failures are not runtime proof."""
import base64,gzip,hashlib,importlib.util,json,os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).parent
COMP=ROOT/'patches/common/foundation/multimedia/player_framework/recorder_configuration'
SDK=Path('/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0/native/sysroot/usr/include')
spec=importlib.util.spec_from_file_location('recorder_configuration_install',COMP/'apply.py');install=importlib.util.module_from_spec(spec);spec.loader.exec_module(install)
def function(source,signature):
 a=source.index(signature);return source[a:source.index('\n}',a)+2]
def baseline():
 fixture=json.loads((HERE/'fixtures/batch_media/recorder/native-baseline.json').read_text());entry=next(iter(fixture['files'].values()));data=gzip.decompress(base64.b64decode(entry['gzip_base64']));assert hashlib.sha256(data).hexdigest()==entry['sha256'];return data
class Recorder(unittest.TestCase):
 def test_actual_six_functions_all_failures_success_and_old_false_success(self):
  harness=(HERE/'fixtures/batch_media/recorder/configuration_harness.cpp').read_text()
  for old in [True,False]:
   source=(baseline() if old else (COMP/'files/native_avrecorder.cpp').read_bytes()).decode()
   functions='\n'.join(function(source,s) for s in ['int32_t GetVideoOrientation(', 'bool IsLocationValid(', 'OH_AVErrCode SetProfile(', 'OH_AVErrCode ConfigureUrl(', 'OH_AVErrCode Configure(', 'OH_AVErrCode OH_AVRecorder_Prepare('])
   with tempfile.TemporaryDirectory(prefix='batch-media-recorder-config-') as temp:
    root=Path(temp);p=root/'functions.cpp';p.write_text(harness.replace('// ACTUAL_FUNCTIONS',functions));flags=['clang++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-idirafter',str(SDK)]
    subprocess.run(flags+(['-DEXPECT_OLD'] if old else [])+[str(p),'-o',str(root/'test')],check=True)
    subprocess.run([str(root/'test')],check=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0' if os.uname().sysname!='Linux' else 'detect_leaks=1'),timeout=10)
 def test_exact_full_source_install_repeat_unknown_and_symlink(self):
  for state in ['known','unknown','symlink']:
   with self.subTest(state=state),tempfile.TemporaryDirectory() as temp:
    root=Path(temp);name=next(iter(install.MANIFEST['files']));p=root/name;p.parent.mkdir(parents=True);p.write_bytes(baseline())
    if state=='unknown':p.write_bytes(p.read_bytes()+b'// preserved user change\n')
    if state=='symlink':saved=root/'saved.cpp';p.rename(saved);p.symlink_to(saved)
    before=p.read_bytes()
    if state=='known':install.run(root);after=p.read_bytes();self.assertTrue(install.validate(root,True));install.run(root);self.assertEqual(after,p.read_bytes())
    else:
     with self.assertRaises(ValueError):install.run(root)
     self.assertEqual(before,p.read_bytes())
 def test_review_patch_produces_exact_payload(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);name=next(iter(install.MANIFEST['files']));p=root/name;p.parent.mkdir(parents=True);p.write_bytes(baseline().replace(b'\r\n',b'\n'))
   subprocess.run(['git','-C',str(root),'apply',str(next(COMP.glob('0001-*.patch')))],check=True)
   self.assertEqual(p.read_bytes(),(COMP/'files/native_avrecorder.cpp').read_bytes().replace(b'\r\n',b'\n'))
if __name__=='__main__':unittest.main(verbosity=2)
