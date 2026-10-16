"""Thirteen-source exact upgrade/forward guard/review patch tests using actual source fixtures."""
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
COMP=ROOT/'patches/common/foundation/multimedia/media_library/knowledge_holiday_index'
FIX=Path(__file__).parent/'fixtures/batch_media/knowledge'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
install=load('holiday_installer',COMP/'apply.py')
old=load('holiday_prior_installer',COMP.parent/'knowledge_content/apply.py')

def baseline(root):
    for filename in ['baseline.json','holiday-baseline.json']:
        fixture=json.loads((FIX/filename).read_text())
        for name,entry in fixture['files'].items():
            data=gzip.decompress(base64.b64decode(entry['gzip_base64']));assert hashlib.sha256(data).hexdigest()==entry['sha256']
            path=root/old.transforms.PROJECT/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)

class Install(unittest.TestCase):
    def test_actual_old_install_then_thirteen_source_upgrade_and_both_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);baseline(root);old.run(root)
            line_endings={path:b'\r\n' in path.read_bytes() for path in root.rglob('*.gn')}
            self.assertFalse(install.validate(root));install.run(root)
            self.assertTrue(install.validate(root,True));self.assertTrue(old.validate(root,True));before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            old.run(root);install.run(root);self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            for path,crlf in line_endings.items():
                if crlf:self.assertNotIn(b'\n',path.read_bytes().replace(b'\r\n',b''))

    def test_partial_unknown_symlink_reject_and_preserve_all_files(self):
        for mode in ['partial','unknown','symlink']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);baseline(root);old.run(root)
                path=root/old.transforms.PROJECT/'frameworks/js/src/knowledge_content_napi.cpp'
                if mode=='partial':path.write_bytes((COMP/'files/knowledge_content_napi.cpp').read_bytes())
                elif mode=='unknown':path.write_bytes(path.read_bytes()+b'// unrelated user changes\n')
                else:
                    saved=root/'real.cpp';path.rename(saved);path.symlink_to(saved)
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                with self.assertRaises(ValueError):install.run(root)
                self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
                if mode=='partial':
                    with self.assertRaises(ValueError):old.validate(root,True)

    def test_review_diff_matches_final_install_and_includes_true_service_hook(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);baseline(root);old.run(root)
            for name in install.MANIFEST['files']:
                path=root/name
                if path.exists():path.write_bytes(path.read_bytes().replace(b'\r\n',b'\n'))
            patch=next(COMP.glob('0001-*.patch'));subprocess.run(['git','-C',str(root),'apply','--check',str(patch)],check=True)
            before={name:(root/name).read_bytes() if (root/name).exists() else None for name in install.MANIFEST['files']}
            subprocess.run(['git','-C',str(root),'apply',str(patch)],check=True)
            for name,entry in install.MANIFEST['files'].items():
                if 'payload' in entry:expected=(COMP/'files'/entry['payload']).read_bytes()
                elif 'transform' in entry:expected=install.transforms.repair(entry['transform'],before[name])
                else:expected=before[name]
                self.assertEqual((root/name).read_bytes(),expected.replace(b'\r\n',b'\n'))
            service=(root/old.transforms.PROJECT/'services/media_rdbstore/src/rdbstore/medialibrary_rdbstore.cpp').read_text()
            self.assertIn('KnowledgeHolidayIndex::Refresh(*rdbStore_)',service);self.assertIn('KnowledgeHolidayIndex::Observe(rdbStore_)',service);self.assertEqual(service.count('KnowledgeHolidayIndex::Refresh(*rdbStore_)'),2);self.assertEqual(service.count('KnowledgeHolidayIndex::StopObserver()'),3)
            helper=(root/old.transforms.PROJECT/'frameworks/innerkitsimpl/media_library_helper/src/media_asset_rdbstore.cpp').read_text();self.assertIn('store->QueryByStep(sql, args, false)',helper)

if __name__=='__main__':unittest.main(verbosity=2)
