"""Read actual ext4 install/uninstall selection and reject BMS counterexamples."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_preinstall_selection import verify_selection
from preinstall_selection import entry, uninstall_policy

BUNDLES = ('com.ohos.settings', 'com.ohos.photos', 'com.ohos.adminprovisioning', 'com.ohos.mms')


class PreinstallSelectionTests(unittest.TestCase):
    def test_exact_selection_rejects_missing_duplicate_type_and_path_changes(self):
        for bundle in BUNDLES:
            good = {'app_dir': '/system/app/' + bundle, 'removable': False}
            self.assertEqual(entry(json.dumps({'install_list': [good]}), bundle), good)
            for rows in ([], [good, good], [dict(good, removable=True)], [dict(good, removable=0)],
                         [dict(good, app_dir='/app/' + bundle)], [None]):
                with self.subTest(bundle=bundle, rows=rows), self.assertRaises(ValueError):
                    entry(json.dumps({'install_list': rows}), bundle)

    def test_uninstall_veto_and_recovery_follow_real_BMS_order(self):
        bundle = BUNDLES[0];directory = '/system/app/' + bundle
        with self.assertRaises(ValueError):
            uninstall_policy(json.dumps({'uninstall_list': [directory], 'recover_list': []}), bundle)
        recovered = {'uninstall_list': [directory], 'recover_list': [directory]}
        self.assertEqual(uninstall_policy(json.dumps(recovered), bundle), recovered)
        for bad in ('{}', '{"uninstall_list":[],"recover_list":[0]}',
                    '{"uninstall_list":[],"uninstall_list":[],"recover_list":[]}'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):uninstall_policy(bad, bundle)

    def test_actual_ext4_selection_and_veto_for_all_four_apps(self):
        mkfs = shutil.which('mkfs.ext4')
        if not mkfs:
            candidate = Path('/opt/homebrew/opt/e2fsprogs/sbin/mkfs.ext4')
            if candidate.is_file():mkfs = str(candidate)
        if not mkfs:self.skipTest('actual ext4 mkfs unavailable')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve();source = root/'source'
            source_policy = source/'vendor/ohemu/virt/preinstall-config';source_policy.mkdir(parents=True)
            staged = root/'staging/etc/app';staged.mkdir(parents=True)
            installs = {'install_list': [{'app_dir':'/system/app/'+b, 'removable':False} for b in BUNDLES]}
            veto = {'uninstall_list': [], 'recover_list': []}
            (source_policy/'install_list.json').write_text(json.dumps(installs))
            (source_policy/'uninstall_list.json').write_text(json.dumps(veto))
            cases = ['positive', 'missing', 'duplicate', 'removable', 'numeric', 'veto', 'ambiguous']
            for case in cases:
                data = json.loads(json.dumps(installs));blocked = json.loads(json.dumps(veto))
                if case == 'missing':data['install_list'] = []
                elif case == 'duplicate':data['install_list'] *= 2
                elif case in ('removable', 'numeric'):
                    for row in data['install_list']:row['removable'] = True if case == 'removable' else 0
                elif case == 'veto':blocked['uninstall_list'] = [r['app_dir'] for r in data['install_list']]
                (staged/'install_list.json').write_text(json.dumps(data))
                (staged/'uninstall_list.json').write_text(json.dumps(blocked))
                if case == 'ambiguous':
                    duplicate = root/'staging/system/etc/app';duplicate.mkdir(parents=True)
                    shutil.copy2(staged/'install_list.json', duplicate/'install_list.json')
                image = root/(case+'.ext4')
                with image.open('wb') as stream:stream.truncate(16*1024*1024)
                subprocess.run([mkfs,'-q','-F','-d',str(root/'staging'),str(image)],check=True,capture_output=True,timeout=30)
                for bundle in BUNDLES:
                    scratch=root/(case+'-'+bundle);scratch.mkdir()
                    with self.subTest(case=case, bundle=bundle):
                        if case == 'positive':
                            result=verify_selection(source,bundle,image,scratch)
                            self.assertEqual(result['entry']['app_dir'],'/system/app/'+bundle)
                            self.assertIn('image_inode',result['uninstall_policy'])
                        else:
                            with self.assertRaises(ValueError):verify_selection(source,bundle,image,scratch)


if __name__ == '__main__':unittest.main()
