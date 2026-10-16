"""Mocked SDK tool output/ELF fixtures, never actual strip or SDK compilation."""
import copy
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import batch_system_sdk_native_strip as strip


def elf(tag=b'hosttest'):
    data=bytearray(512);data[:7]=b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHIQQQIHHHHHH',data,16,3,183,1,0,64,256,0,64,56,1,64,3,2)
    struct.pack_into('<IIQQQQQQ',data,64,1,5,0,0,0,512,512,4096)
    data[128:136]=tag;names=b'\0.text\0.shstrtab\0';data[144:144+len(names)]=names
    struct.pack_into('<IIQQQQIIQQ',data,320,1,1,6,0x1000,128,8,0,0,4,0)
    struct.pack_into('<IIQQQQIIQQ',data,384,7,3,0,0,144,len(names),0,0,1,0)
    return bytes(data)


class NativeStripTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup);self.root=Path(self.temporary.name).resolve()
        self.sdk=self.root/'sdk/native';(self.sdk/'llvm/bin').mkdir(parents=True)
        self.tool=self.sdk/'llvm/bin/llvm-strip';self.tool.write_bytes(b'HOST MOCK TOOL NOT EXECUTABLE')
        self.metadata={'path':'native','apiVersion':'26','platformVersion':'26.0.0','version':'26.0.0.39','releaseType':'Release'}
        (self.sdk/'oh-uni-package.json').write_text(json.dumps(self.metadata))
        self.project=self.root/'project';self.libs=self.project/'entry/libs/arm64-v8a';self.libs.mkdir(parents=True)
        self.source=self.project/'probe.cpp';self.source.write_text('// host fixture only')
        self.native=self.libs/'libaudit.so';self.native.write_bytes(elf()+b'DEBUG HOST FIXTURE')
        self.runtime=self.libs/'libc++_shared.so';self.runtime.write_bytes(elf(b'hostcpp!'))
        self.member='libs/arm64-v8a/libaudit.so';self.packed={self.member:elf(),'libs/arm64-v8a/libc++_shared.so':self.runtime.read_bytes()}
        self.hap=self.root/'actual.hap';self.write_hap()
        commands=[]
        for label,argv,text in [('compile-native',[str(self.sdk/'llvm/bin/clang++'),str(self.source)],''),
            ('compile',['node','hvigorw.js','assembleHap'],'Finished :entry:default@DoNativeStrip...\nBUILD SUCCESSFUL\n')]:
            path=self.root/(label+'.log');path.write_text(text)
            commands.append({'project':'project','label':label,'argv':argv,'exit_code':0,'log':str(path),'sha256':strip.digest(path)})
        self.build={'project':'project','source':strip.descriptor(self.source),'binary':strip.descriptor(self.native),
            'compiler':{'path':str(self.sdk/'llvm/bin/clang++'),'sha256':'c'*64},'command_label':'compile-native',
            'sdk_native_metadata_sha256':strip.digest(self.sdk/'oh-uni-package.json'),
            'runtime_libraries':[{'path':str(self.runtime),'source':str(self.sdk/'llvm/lib/aarch64-linux-ohos/libc++_shared.so'),'sha256':strip.digest(self.runtime)}]}
        self.original={'exit_code':0,'source_files':{'project/probe.cpp':strip.digest(self.source)},'native_builds':[self.build],
            'commands':commands,'haps':[{'project':'project',**strip.descriptor(self.hap),'bytes':self.hap.stat().st_size}]}
        self.evidence=self.root/'original-sdk.json';self.evidence.write_text(json.dumps(self.original))
        self.out=self.root/'new-recheck';self.calls=[]

    def write_hap(self):
        with zipfile.ZipFile(self.hap,'w')as hap:
            for name,data in self.packed.items():hap.writestr(name,data)

    def command(self,argv,label,output):
        self.calls.append(argv);row={'argv':argv,'exit_code':0,'seconds':0.01}
        if label=='strip-version':stdout=b'LLVM host fixture VERSION NOT REAL\n'
        else:
            original=Path(argv[1]).read_bytes();destination=Path(argv[2][2:]);destination.parent.mkdir(exist_ok=True)
            destination.write_bytes(elf()if original==self.native.read_bytes()else self.runtime.read_bytes());stdout=b''
        for key,data in [('stdout',stdout),('stderr',b'')]:
            path=output/'logs'/(label+'.'+key);path.parent.mkdir(exist_ok=True);path.write_bytes(data)
            row[key]={'path':str(path.relative_to(output)),'sha256':strip.digest(path)}
        return row

    def run_recheck(self,command=None):
        with (patch.object(strip,'SDK_STRIP_SHA256',strip.digest(self.tool)),
              patch.object(strip.os,'statvfs',return_value=SimpleNamespace(f_flag=strip.os.ST_RDONLY)),
              patch.object(strip,'run_command',side_effect=command or self.command)):
            return strip.recheck(self.sdk,self.native,self.hap,self.member,self.evidence,self.out)

    def caller(self):
        return {'sdk_project':'project','sdk_evidence':strip.descriptor(self.evidence),'unsigned_hap':strip.descriptor(self.hap),
            'native_strip_receipt':strip.descriptor(self.out/'receipt.json')}

    def verify(self,caller=None,build=None,native=None):
        with patch.object(strip,'SDK_STRIP_SHA256',strip.digest(self.tool)):
            return strip.verify(caller or self.caller(),build or self.build,native or self.native)

    def rewrite_receipt(self,change):
        path=self.out/'receipt.json';value=strip.load(path);change(value);path.write_text(json.dumps(value))

    def test_exact_main_and_noop_runtime_are_both_replayed_and_independently_reverified(self):
        original_hash=strip.digest(self.evidence);result=self.run_recheck()
        self.assertEqual(strip.STATUS,result['status']);self.assertEqual(3,len(self.calls))
        self.assertEqual(original_hash,strip.digest(self.evidence));actual=self.verify()
        self.assertEqual(set(self.packed),set(actual['libraries']));self.assertFalse(actual['runtime_validated'])
        self.assertNotEqual(actual['libraries'][self.member]['original_sha256'],actual['libraries'][self.member]['HAP_member_sha256'])

    def test_verifier_never_executes_strip_or_another_subprocess(self):
        self.run_recheck()
        with patch.object(strip.subprocess,'run',side_effect=AssertionError('forbidden actual tool execution')):
            self.assertEqual(strip.STATUS,self.verify()['status'])

    def test_sdk105_rejected_even_with_the_expected_tool_hash(self):
        self.metadata['version']='26.0.0.105';(self.sdk/'oh-uni-package.json').write_text(json.dumps(self.metadata))
        self.build['sdk_native_metadata_sha256']=strip.digest(self.sdk/'oh-uni-package.json');self.evidence.write_text(json.dumps(self.original))
        result=self.run_recheck();self.assertEqual('fail',result['status']);self.assertEqual([],self.calls)

    def test_read_write_sdk_and_wrong_tool_fail_without_running_native_strip(self):
        with (patch.object(strip.os,'statvfs',return_value=SimpleNamespace(f_flag=0)),
              patch.object(strip,'run_command',side_effect=AssertionError('must not execute'))):
            self.assertEqual('fail',strip.recheck(self.sdk,self.native,self.hap,self.member,self.evidence,self.out)['status'])

    def test_unpinned_strip_tool_cannot_execute_even_on_read_only_sdk(self):
        with (patch.object(strip.os,'statvfs',return_value=SimpleNamespace(f_flag=strip.os.ST_RDONLY)),
              patch.object(strip,'run_command',side_effect=AssertionError('unpinned tool must not execute'))):
            self.assertEqual('fail',strip.recheck(self.sdk,self.native,self.hap,self.member,self.evidence,self.out)['status'])

    def test_elf_similarity_never_accepts_different_actual_hap_bytes(self):
        self.packed[self.member]=elf()+b'UNREPRODUCED TAIL';self.write_hap()
        self.original['haps'][0].update(**strip.descriptor(self.hap),bytes=self.hap.stat().st_size);self.evidence.write_text(json.dumps(self.original))
        result=self.run_recheck();self.assertEqual('fail',result['status']);self.assertIn('exact HAP',result['failures'][0])

    def test_original_runtime_member_cannot_be_omitted_or_ignored(self):
        self.build['runtime_libraries']=[];self.evidence.write_text(json.dumps(self.original))
        result=self.run_recheck();self.assertEqual('fail',result['status']);self.assertEqual([],self.calls)

    def test_extra_native_abi_or_library_is_not_ignored(self):
        self.packed['libs/x86_64/libother.so']=elf();self.write_hap()
        self.original['haps'][0].update(**strip.descriptor(self.hap),bytes=self.hap.stat().st_size);self.evidence.write_text(json.dumps(self.original))
        self.assertEqual('fail',self.run_recheck()['status'])

    def test_hvigor_zero_without_actual_completed_nativestrip_task_is_not_sufficient(self):
        row=self.original['commands'][1];path=Path(row['log']);path.write_text('BUILD SUCCESSFUL\n');row['sha256']=strip.digest(path)
        self.evidence.write_text(json.dumps(self.original));self.assertEqual('fail',self.run_recheck()['status'])

    def test_failed_actual_strip_cannot_be_promoted_by_a_result_file(self):
        def failure(argv,label,output):
            row=self.command(argv,label,output)
            if label.startswith('strip-')and label!='strip-version':row['exit_code']=1
            return row
        result=self.run_recheck(failure);self.assertEqual('fail',result['status'])
        with self.assertRaises(ValueError):self.verify()

    def test_status_only_or_wrong_scope_cannot_pass_replay(self):
        self.run_recheck();self.rewrite_receipt(lambda v:v.update(scope='status-only'))
        with self.assertRaises(ValueError):self.verify()

    def test_retained_output_must_still_equal_current_hap_not_just_stored_hash(self):
        self.run_recheck();self.packed[self.member]=elf()+b'new caller HAP';self.write_hap()
        # Even if the summary HAP digest is replaced, exact member comparison remains.
        self.rewrite_receipt(lambda v:v['HAP'].update(sha256=strip.digest(self.hap)))
        with self.assertRaises(ValueError):self.verify()

    def test_same_native_members_cannot_borrow_different_hap_resources(self):
        self.run_recheck()
        with zipfile.ZipFile(self.hap,'a')as hap:hap.writestr('resources.index',b'different compiled resources')
        self.rewrite_receipt(lambda v:v['HAP'].update(sha256=strip.digest(self.hap)))
        with self.assertRaisesRegex(ValueError,'unchanged original SDK report'):self.verify()

    def test_current_runtime_source_and_full_coverage_are_rechecked(self):
        self.run_recheck();self.runtime.write_bytes(elf(b'changed!'))
        with self.assertRaises(ValueError):self.verify()

    def test_changed_strip_tool_snapshot_metadata_log_argv_and_script_rejected(self):
        self.run_recheck();receipt=self.out/'receipt.json';original=receipt.read_bytes()
        changes=[lambda v:v['commands'][1]['argv'].__setitem__(2,'--strip-debug'),
                 lambda v:v.update(script_sha256='0'*64),lambda v:v['sdk_inputs']['strip'].update(sha256='0'*64),
                 lambda v:v['sdk_metadata'].update(version='26.0.0.105'),lambda v:v['libraries'].pop('libs/arm64-v8a/libc++_shared.so'),
                 lambda v:v['commands'][1].update(exit_code=False)]
        for change in changes:
            receipt.write_bytes(original);self.rewrite_receipt(change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.verify()
        receipt.write_bytes(original);log=self.out/strip.load(receipt)['commands'][0]['stdout']['path'];log.write_text('tampered')
        with self.assertRaises(ValueError):self.verify()

    def test_derived_receipt_can_be_copied_whole_without_rewriting_original_execution_paths(self):
        self.run_recheck();import shutil
        moved=self.root/'private-captured-recheck';shutil.copytree(self.out,moved)
        caller=self.caller();caller['native_strip_receipt']=strip.descriptor(moved/'receipt.json')
        self.assertEqual(strip.STATUS,self.verify(caller)['status'])

    def test_only_exact_copy_of_original_native_is_accepted_after_private_capture(self):
        self.run_recheck();copy=self.root/'captured/libaudit.so';copy.parent.mkdir();copy.write_bytes(self.native.read_bytes())
        runtime=copy.parent/self.runtime.name;runtime.write_bytes(self.runtime.read_bytes())
        self.assertEqual(strip.STATUS,self.verify(native=copy)['status']);copy.write_bytes(elf())
        with self.assertRaises(ValueError):self.verify(native=copy)


if __name__=='__main__':unittest.main()
