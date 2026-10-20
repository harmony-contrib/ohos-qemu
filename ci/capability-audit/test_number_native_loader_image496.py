"""Synthetic host ELF/extraction boundaries only; no image, loader or guest pass."""
from pathlib import Path
import hashlib,json,os,struct,subprocess,sys,tempfile,unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import verify_number_identity_image as guard
import ext_image_entries

LIBRARY='libappkit_native.z.so'
MARKER=b'NUMBER_NATIVE495_LOAD v=1 event=HOST_SYNTHETIC_ONLY\0'
def sha(data):return hashlib.sha256(data).hexdigest()

def synthetic_elf(arch='arm64',*,kind=3,machine=None,execute=True,dynamic=True,zero_code=False,main_defined=True,marker=MARKER,library='loader'):
    """Manually formed metadata, never target-built or executed as machine code."""
    cls,expected,_=guard.ARCHES[arch];machine=expected if machine is None else machine
    data=bytearray(0x600);data[:7]=b'\x7fELF'+bytes((cls,1,1));struct.pack_into('<HHI',data,16,kind,machine,1)
    phoff=64 if cls==2 else 52;phsize=56 if cls==2 else 32;shsize=64 if cls==2 else 40
    if cls==2:
        struct.pack_into('<Q',data,32,phoff);struct.pack_into('<Q',data,40,0x500)
        struct.pack_into('<HHHHHH',data,52,64,phsize,3,shsize,4,0)
        programs=[(1,5 if execute else 4,0x180,0x1180,0x1180,32,32,0x1000),(1,4,0x1a0,0x11a0,0x11a0,0x460,0x460,0x1000),(2 if dynamic else 4,6,0x1a0,0x11a0,0x11a0,16,16,8)]
        for i,row in enumerate(programs):struct.pack_into('<IIQQQQQQ',data,phoff+i*phsize,*row)
    else:
        struct.pack_into('<I',data,28,phoff);struct.pack_into('<I',data,32,0x500)
        struct.pack_into('<HHHHHH',data,40,52,phsize,3,shsize,4,0)
        programs=[(1,0x180,0x1180,0x1180,32,32,5 if execute else 4,0x1000),(1,0x1a0,0x11a0,0x11a0,0x460,0x460,4,0x1000),(2 if dynamic else 4,0x1a0,0x11a0,0x11a0,16,16,6,4)]
        for i,row in enumerate(programs):struct.pack_into('<IIIIIIII',data,phoff+i*phsize,*row)
    if not zero_code:data[0x180:0x1a0]=(b'\x1f\x20\x03\xd5'*8 if arch=='arm64' else b'\x00\xf0\x20\xe3'*8 if arch=='armv7a' else b'\x90\xc3'*16)
    symbols=[('HostSyntheticDefined',True),('_ZN4OHOS10MainThread13HostOnlyEntryEv',main_defined)]
    if library=='provider':symbols=[('TelephonyNumberSyntheticProvider',True)]
    if library=='napi':symbols=[('HostSyntheticDefined',True),('napi_module_register',False)]
    strings=bytearray(b'\0');names=[]
    for name,defined in symbols:
        names.append((len(strings),defined));strings.extend(name.encode()+b'\0')
    data[0x300:0x300+len(strings)]=strings
    symsize=24 if cls==2 else 16
    for i,(offset,defined) in enumerate(names,1):
        if cls==2:struct.pack_into('<IBBHQQ',data,0x200+i*symsize,offset,0x12,0,3 if defined else 0,0x1180 if defined else 0,4 if defined else 0)
        else:struct.pack_into('<IIIBBH',data,0x200+i*symsize,offset,0x1180 if defined else 0,4 if defined else 0,0x12,0,3 if defined else 0)
    sections=[(0,0,0,0,0,0,0,0,0,0),(0,3,2,0x1300,0x300,len(strings),0,0,1,0),(0,11,2,0x1200,0x200,(len(names)+1)*symsize,1,1,8 if cls==2 else 4,symsize),(0,1,6,0x1180,0x180,32,0,0,4,0)]
    for i,row in enumerate(sections):struct.pack_into('<IIQQQQIIQQ' if cls==2 else '<IIIIIIIIII',data,0x500+i*shsize,*row)
    payload=marker+(b'telephony.numberidentity\0contact.numberlookup\0' if library=='napi' else b'')
    data[0x400:0x400+len(payload)]=payload
    return bytes(data)

class LoaderImage496(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name).resolve()
        self.image=self.root/'synthetic-image.ext';self.image.write_bytes(b'HOST_SYNTHETIC_IMAGE_ONLY')
        self.serial=0
    def fresh(self,name='export'):
        self.serial+=1;scratch=self.root/('scratch-'+str(self.serial));scratch.mkdir()
        return scratch,self.root/(name+'-'+str(self.serial))
    def extracted(self,payload):
        def extract(image,candidates,directory,executable):
            self.assertEqual(image,self.image);self.assertEqual(executable,'HOST_SYNTHETIC_DEBUGFS_ONLY')
            p=directory/'0.extracted';p.write_bytes(payload)
            return p,dict(image_path=candidates[0],image_inode=731,image_path_aliases=list(candidates))
        return extract
    def call_export(self,*,arch='arm64',payload=None,destination=None,copy=None):
        scratch,default=self.fresh();destination=default if destination is None else destination
        with mock.patch.object(guard,'dump_unique_file',side_effect=self.extracted(synthetic_elf(arch) if payload is None else payload)) as dump, mock.patch.object(guard,'debugfs_path',return_value='HOST_SYNTHETIC_DEBUGFS_ONLY'):
            if copy is None:report=guard.verify_loader_image(self.image,arch,scratch,destination)
            else:
                with mock.patch.object(guard.shutil,'copyfile',side_effect=copy):report=guard.verify_loader_image(self.image,arch,scratch,destination)
        return report,dump,destination
    def elf(self,payload):
        p=self.root/'synthetic.so';p.write_bytes(payload);return p
    def test_01_three_ABIs_real_parser_and_copy_hash_inode_report(self):
        for arch in guard.ARCHES:
            with self.subTest(arch=arch):
                payload=synthetic_elf(arch);report,dump,destination=self.call_export(arch=arch,payload=payload)
                target=destination/LIBRARY;self.assertTrue(target.is_file());self.assertFalse(target.is_symlink());self.assertEqual(target.read_bytes(),payload)
                self.assertEqual(destination.stat().st_mode&0o777,0o700)
                self.assertEqual(report['sha256'],sha(payload));self.assertEqual(report['bytes'],len(payload));self.assertEqual(report['system_image_sha256'],sha(self.image.read_bytes()));self.assertEqual(report['file'],str(target));self.assertEqual(report['basename'],LIBRARY)
                self.assertEqual(report['image_inode'],731);self.assertEqual(report['image_path_aliases'],['/'+guard.ARCHES[arch][2]+'/'+LIBRARY,'/system/'+guard.ARCHES[arch][2]+'/'+LIBRARY])
                self.assertEqual(report['elf_class'],guard.ARCHES[arch][0]);self.assertEqual(report['elf_machine'],guard.ARCHES[arch][1]);self.assertEqual(report['elf_type'],3)
                self.assertIs(report['loaded_process_verified'],False);self.assertIs(report['native_callback_proven'],False)
                self.assertIn('on-disk loader ELF only',report['scope']);dump.assert_called_once()
    def test_02_wrong_arch_or_ET_EXEC_rejects(self):
        for arch,payload in [('arm64',synthetic_elf('armv7a')),('armv7a',synthetic_elf('arm64')),('x86_64',synthetic_elf('arm64')),('arm64',synthetic_elf(kind=2))]:
            with self.subTest(arch=arch),self.assertRaisesRegex(ValueError,'ABI/type'):guard.inspect_elf(self.elf(payload),arch,LIBRARY)
    def test_03_executable_dynamic_and_nonzero_code_required(self):
        for options in [dict(execute=False),dict(dynamic=False),dict(zero_code=True)]:
            with self.subTest(options=options),self.assertRaisesRegex(ValueError,'empty/stub'):guard.inspect_elf(self.elf(synthetic_elf(**options)),'arm64',LIBRARY)
    def test_04_defined_MainThread_and_exact_new_marker_required(self):
        for options in [dict(main_defined=False),dict(marker=b'OLD_NUMBER_NATIVE_LOAD v=1 event=HOST\0'),dict(marker=b'')]:
            with self.subTest(options=options),self.assertRaisesRegex(ValueError,'loader implementation/observation'):guard.inspect_elf(self.elf(synthetic_elf(**options)),'arm64',LIBRARY)
    def test_05_header_program_and_segment_truncation_rejected(self):
        values=[b'HOST_NOT_ELF',synthetic_elf()[:64]]
        data=bytearray(synthetic_elf());struct.pack_into('<Q',data,64+2*56+32,0xffff);values.append(bytes(data))
        data=bytearray(synthetic_elf());struct.pack_into('<HH',data,54,1,3);values.append(bytes(data))
        for payload in values:
            with self.subTest(length=len(payload)),self.assertRaises(ValueError):guard.inspect_elf(self.elf(payload),'arm64',LIBRARY)
    def test_06_source_symlink_refused_by_real_elf_guard(self):
        p=self.elf(synthetic_elf());alias=self.root/'alias.so';alias.symlink_to(p)
        with self.assertRaisesRegex(ValueError,'regular'):guard.inspect_elf(alias,'arm64',LIBRARY)
    def test_07_relative_destination_refused(self):
        with self.assertRaisesRegex(ValueError,'fresh canonical'):self.call_export(destination=Path('relative-'+self.root.name))
    def test_08_existing_directory_file_and_broken_symlink_refused(self):
        directory=self.root/'existing';directory.mkdir();(directory/'untouched').write_bytes(b'original')
        regular=self.root/'file';regular.write_bytes(b'original')
        alias=self.root/'broken';alias.symlink_to(self.root/'absent')
        for dest in [directory,regular,alias]:
            with self.subTest(destination=dest),self.assertRaisesRegex(ValueError,'fresh canonical'):self.call_export(destination=dest)
        self.assertEqual((directory/'untouched').read_bytes(),b'original');self.assertEqual(regular.read_bytes(),b'original');self.assertTrue(alias.is_symlink())
    def test_09_parent_alias_and_lexical_dotdot_refused(self):
        real=self.root/'real';real.mkdir();alias=self.root/'alias';alias.symlink_to(real,target_is_directory=True)
        for dest in [alias/'export',real/'..'/'export']:
            with self.subTest(destination=dest),self.assertRaisesRegex(ValueError,'fresh canonical'):self.call_export(destination=dest)
        self.assertFalse((real/'export').exists());self.assertFalse((self.root/'export').exists())
    def test_10_copy_corruption_cannot_report_success(self):
        def corrupt(source,target):Path(target).write_bytes(b'HOST_CORRUPTION')
        with self.assertRaisesRegex(ValueError,'differs from image'):self.call_export(copy=corrupt)
    def test_11_unique_inode_actual_helper_replayed_with_synthetic_debugfs(self):
        for inodes,accepted in [([731,731],True),([731,None],True),([None,731],True),([731,732],False),([None,None],False)]:
            scratch,dest=self.fresh();payload=synthetic_elf();calls=[]
            def fake(argv,**kwargs):
                calls.append(argv);self.assertEqual(argv[0],'HOST_SYNTHETIC_DEBUGFS_ONLY');self.assertEqual(argv[1],'-R');self.assertEqual(argv[-1],str(self.image));self.assertIs(kwargs['check'],True)
                if argv[2].startswith('stat '):
                    index=1 if argv[2].startswith('stat /system/') else 0;inode=inodes[index]
                    text='File not found\n' if inode is None else f'Inode: {inode}   Type: regular Mode: 0644\n'
                    return subprocess.CompletedProcess(argv,0,stdout=text,stderr='')
                self.assertTrue(argv[2].startswith('dump '));target=Path(argv[2].split(' ',2)[2]);target.write_bytes(payload)
                return subprocess.CompletedProcess(argv,0,stdout=b'',stderr=b'')
            with mock.patch.object(ext_image_entries.subprocess,'run',side_effect=fake),mock.patch.object(guard,'debugfs_path',return_value='HOST_SYNTHETIC_DEBUGFS_ONLY'):
                if accepted:
                    report=guard.verify_loader_image(self.image,'arm64',scratch,dest);self.assertEqual(report['image_inode'],731);self.assertEqual((dest/LIBRARY).read_bytes(),payload)
                    aliases=[prefix+'/lib64/'+LIBRARY for prefix,inode in zip(['','/system'],inodes) if inode is not None]
                    self.assertEqual(report['image_path_aliases'],aliases);self.assertEqual(report['image_path'],aliases[0])
                else:
                    with self.assertRaisesRegex(ValueError,'unambiguous regular file inode'):guard.verify_loader_image(self.image,'arm64',scratch,dest)
                    self.assertFalse(dest.exists())
            self.assertTrue(calls)
    def test_12_original_LIBRARIES3_contract_not_replaced(self):
        self.assertEqual(guard.LIBRARIES,('libnumber_identity.z.so','module/telephony/libnumberidentity.z.so','module/contact/libnumberlookup.z.so'))
        guard.inspect_elf(self.elf(synthetic_elf(library='provider')),'arm64',guard.LIBRARIES[0])
        for library in guard.LIBRARIES[1:]:
            guard.inspect_elf(self.elf(synthetic_elf(library='napi')),'arm64',library)
            with self.assertRaisesRegex(ValueError,'NAPI registration'):guard.inspect_elf(self.elf(synthetic_elf()),'arm64',library)
    def cli(self,output,extra=()):
        return guard.main(['--system-image',str(self.image),'--source-root',str(self.root/'not-actual-source'),'--arch','arm64','--output',str(output),*extra])
    def test_13_legacy_CLI_does_not_call_new_export(self):
        output=self.root/'legacy.json';libraries={name:{'scope':'HOST_MOCK_ONLY'} for name in guard.LIBRARIES}
        with mock.patch.object(guard,'verify_image',return_value={'native_libraries':libraries}),mock.patch.object(guard,'verify_loader_image') as loader:
            self.assertEqual(self.cli(output),0);loader.assert_not_called()
        value=json.loads(output.read_bytes());self.assertEqual(list(value['native_libraries']),list(guard.LIBRARIES));self.assertNotIn('loader_library',value)
        for key in ['provider_runtime_validated','local_subset_runtime_validated','aggregate_provider_supported','full_number_library_supported','first_artifact_behavior_gate_passed']:self.assertIs(value[key],False)
    def test_14_new_CLI_keeps_original_guard_before_real_export(self):
        output=self.root/'new.json';dest=self.root/'cli-export';events=[]
        def original(*args):events.append('original-image-guards');return {'native_libraries':{name:{} for name in guard.LIBRARIES}}
        extractor=self.extracted(synthetic_elf())
        def dump(*args):events.append('synthetic-loader-extraction');return extractor(*args)
        with mock.patch.object(guard,'verify_image',side_effect=original),mock.patch.object(guard,'dump_unique_file',side_effect=dump),mock.patch.object(guard,'debugfs_path',return_value='HOST_SYNTHETIC_DEBUGFS_ONLY'):
            self.assertEqual(self.cli(output,['--loader-output-dir',str(dest)]),0)
        self.assertEqual(events,['original-image-guards','synthetic-loader-extraction']);value=json.loads(output.read_bytes());self.assertEqual(value['loader_library']['file'],str(dest/LIBRARY));self.assertIs(value['loader_library']['loaded_process_verified'],False);self.assertIs(value['first_artifact_behavior_gate_passed'],False)
    def test_15_original_guard_failure_prevents_export(self):
        output=self.root/'failed.json';dest=self.root/'forbidden-export'
        with mock.patch.object(guard,'verify_image',side_effect=ValueError('HOST_OLD_GUARD_FAIL')),mock.patch.object(guard,'verify_loader_image') as loader:
            self.assertEqual(self.cli(output,['--loader-output-dir',str(dest)]),1);loader.assert_not_called()
        self.assertFalse(dest.exists());self.assertEqual(json.loads(output.read_bytes())['status'],'fail')
    def test_16_virtual_memory_size_is_not_file_truncation(self):
        data=bytearray(synthetic_elf());struct.pack_into('<Q',data,64+56+40,0xffff)
        self.assertEqual(guard.inspect_elf(self.elf(bytes(data)),'arm64',LIBRARY)['elf_type'],3)
    def test_17_loader_copy_failure_makes_CLI_fail(self):
        output=self.root/'corrupt-copy.json';dest=self.root/'corrupt-export'
        def corrupt(source,target):Path(target).write_bytes(b'HOST_CORRUPTION')
        with mock.patch.object(guard,'verify_image',return_value={'native_libraries':{name:{} for name in guard.LIBRARIES}}),mock.patch.object(guard,'dump_unique_file',side_effect=self.extracted(synthetic_elf())),mock.patch.object(guard,'debugfs_path',return_value='HOST_SYNTHETIC_DEBUGFS_ONLY'),mock.patch.object(guard.shutil,'copyfile',side_effect=corrupt):
            self.assertEqual(self.cli(output,['--loader-output-dir',str(dest)]),1)
        value=json.loads(output.read_bytes());self.assertEqual(value['status'],'fail');self.assertNotIn('loader_library',value);self.assertIs(value['first_artifact_behavior_gate_passed'],False)

if __name__=='__main__':unittest.main()
