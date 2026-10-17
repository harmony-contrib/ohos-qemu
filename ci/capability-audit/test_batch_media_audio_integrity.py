#!/usr/bin/env python3
"""Bounded actual-function regressions; controlled Capturer is not backend capability evidence."""
import base64
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
COMP=ROOT/'patches/common/foundation/multimedia/av_codec/audio_capture_integrity'
FIXTURE=Path(__file__).parent/'fixtures/batch_media/audio'
BASE=json.loads((FIXTURE/'baseline.json').read_text())

def function(source, signature):
    start=source.index(signature)
    end=source.index('\n}',start)+2
    return source[start:end]

class Integrity(unittest.TestCase):
    def test_actual_module_filter_functions(self):
        module=(COMP/'files/audio_capture_module.cpp').read_text()
        filt=(COMP/'files/audio_capture_filter.cpp').read_text()
        functions=[]
        for signature in ['Status AudioCaptureModule::Start()', 'Status AudioCaptureModule::Stop()',
            'Status AudioCaptureModule::DoDeinit()', 'Status AudioCaptureModule::Read(std::shared_ptr<AVBuffer>',
            'Status AudioCaptureModule::Read(uint8_t', 'void AudioCaptureModule::TrackMaxAmplitude(',
            'int32_t AudioCaptureModule::GetMaxAmplitude()']:
            functions.append(function(module,signature))
        for name in ['DoStart','DoPause','DoResume','DoStop','DoRelease','RecordOneAudioFrame','RecordCachedData']:
            functions.append(function(filt,('void ' if name.startswith('Record') else 'Status ')+'AudioCaptureFilter::'+name+'('))
        harness=(FIXTURE/'integrity_harness.cpp').read_text().replace('// ACTUAL_FUNCTIONS','\n\n'.join(functions))
        with tempfile.TemporaryDirectory(prefix='batch-media-capture-') as temp:
            cpp=Path(temp)/'test.cpp';cpp.write_text(harness);exe=Path(temp)/'test'
            subprocess.run([os.environ.get('OHOS_QA_CXX','/usr/bin/clang++'),'-std=c++17','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(cpp),'-o',str(exe)],check=True)
            env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0' if os.uname().sysname!='Linux' else 'detect_leaks=1')
            subprocess.run([str(exe)],env=env,check=True,timeout=20)

    def test_complete_install_and_rejection(self):
        spec=importlib.util.spec_from_file_location('capture_install',COMP/'apply.py');installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory(prefix='batch-media-capture-source-') as temp:
            root=Path(temp)
            for project,info in BASE['projects'].items():
                if project!='foundation/multimedia/av_codec':continue
                for name,entry in info['files'].items():
                    data=gzip.decompress(base64.b64decode(entry['gzip_base64']));self.assertEqual(hashlib.sha256(data).hexdigest(),entry['sha256']);path=root/project/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            installer.run(root);installer.run(root);self.assertTrue(installer.validate(root,True))
            target=root/next(iter(installer.MANIFEST['files']));target.write_bytes(target.read_bytes()+b'// unknown\n')
            snapshots={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with self.assertRaises(ValueError):installer.run(root)
            self.assertEqual(snapshots,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})

if __name__=='__main__':unittest.main(verbosity=2)
