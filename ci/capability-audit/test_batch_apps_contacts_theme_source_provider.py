#!/usr/bin/env python3
"""Check the actual fixed metadata, exact replay and retained provider contracts."""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / 'ci/capability-audit/fixtures/batch_apps/contacts_theme'
CONTACTS = 'applications/standard/contacts'
THEME = 'applications/standard/theme'
PLUGIN = os.environ.get('OHOS_HVIGOR_PLUGIN',
    '/Volumes/PSSD/qemu/openharmony/prebuilts/tool/command-line-tools/6.x/hvigor/hvigor-ohos-plugin')


def parse(raw):
    script = 'const f=require("fs"),j=require(process.argv[1]);process.stdout.write(JSON.stringify(j.parse(f.readFileSync(0,"utf8"))))'
    return json.loads(subprocess.check_output(['node', '-e', script, PLUGIN + '/node_modules/json5'], input=raw))


class SourceProvider(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='apps-provider-metadata-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.meta = json.loads((FIX / 'inspection.json').read_text())
        self.final = json.loads((FIX / 'candidate-hashes.json').read_text())
        for relative, record in self.meta['files'].items():
            raw = gzip.decompress(base64.b64decode(record['gzip_base64']))
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record['sha256'])
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)

    def apply(self, project):
        component = ROOT / 'patches/common' / project / 'source_provider'
        return subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def prepare(self):
        for project in (CONTACTS, THEME):
            result = self.apply(project)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exact_targets_apply_and_two_replays(self):
        self.assertEqual(len(self.final), 8)
        self.prepare()
        for _ in range(2):
            self.prepare()
        for relative, expected in self.final.items():
            self.assertEqual(hashlib.sha256((self.root / relative).read_bytes()).hexdigest(), expected)
        # The snapshot includes real UI, all original manifests, signing profiles
        # and external metadata. A packaging patch may not change any of them.
        for relative, item in self.meta['files'].items():
            if relative not in self.final:
                self.assertEqual(hashlib.sha256((self.root / relative).read_bytes()).hexdigest(), item['sha256'])

    def test_partial_unknown_and_redirected_inputs_fail_before_mutating(self):
        project = self.root / CONTACTS
        baseline = (project / 'build-profile.json5').read_bytes()
        (project / 'BUILD.gn').write_text('unknown existing target\n')
        self.assertNotEqual(self.apply(CONTACTS).returncode, 0)
        self.assertEqual((project / 'build-profile.json5').read_bytes(), baseline)
        (project / 'BUILD.gn').unlink()
        self.prepare()
        final = (project / 'BUILD.gn').read_bytes()
        (project / 'build-profile.json5').write_bytes(baseline)
        self.assertNotEqual(self.apply(CONTACTS).returncode, 0)
        self.assertEqual((project / 'BUILD.gn').read_bytes(), final)
        (project / 'build-profile.json5').unlink()
        elsewhere = self.root / 'redirected.json5'
        elsewhere.write_bytes(baseline)
        (project / 'build-profile.json5').symlink_to(elsewhere)
        self.assertNotEqual(self.apply(CONTACTS).returncode, 0)
        self.assertEqual(elsewhere.read_bytes(), baseline)

    def test_build_schema_module_graph_profiles_and_identity_preserved(self):
        before = {p: parse((self.root / p / 'build-profile.json5').read_bytes()) for p in (CONTACTS, THEME)}
        contacts_raw = (self.root / CONTACTS / 'build-profile.json5').read_bytes()
        self.prepare()
        self.assertEqual((self.root / CONTACTS / 'build-profile.json5').read_bytes(),
                         contacts_raw.replace(b'        "signingConfig": "release",\n', b''))
        after = {p: parse((self.root / p / 'build-profile.json5').read_bytes()) for p in (CONTACTS, THEME)}
        contacts = before[CONTACTS]
        for product in contacts['app']['products']:
            product.pop('signingConfig')
        self.assertEqual(after[CONTACTS], contacts)
        self.assertEqual(len(after[CONTACTS]['modules']), 7)
        for project in (CONTACTS, THEME):
            self.assertEqual(after[project]['modules'], before[project]['modules'])
        theme = after[THEME]['app']['products'][0]
        self.assertEqual(theme, {'name': 'default', 'compileSdkVersion': '26.0.0',
                               'compatibleSdkVersion': 9, 'targetSdkVersion': 9, 'runtimeOS': 'OpenHarmony'})
        # Local HARs and the actual external HSP dependency are retained.
        for module in after[CONTACTS]['modules']:
            directory = self.root / CONTACTS / module['srcPath']
            meta = parse((directory / 'oh-package.json5').read_bytes())
            for dependency in meta.get('dependencies', {}).values():
                if dependency.startswith('file:'):
                    self.assertTrue((directory / dependency[5:] / 'oh-package.json5').is_file())
        entry = parse((self.root / CONTACTS / 'entry/src/main/module.json5').read_bytes())['module']
        self.assertIn({'bundleName': 'com.ohos.security.pickersheet', 'moduleName': 'pickersheetlibrary'}, entry['dependencies'])
        self.assertEqual(len(entry['requestPermissions']), 38)
        picker = next(x for x in entry['extensionAbilities'] if x['name'] == 'ContactUiExtentionAbility')
        self.assertEqual((picker['type'], picker['exported'], picker['permissions']), ('sys/commonUI', True, []))
        for product, device in [('phone', 'phone'), ('pad', 'tablet')]:
            module = parse((self.root / THEME / 'product' / product / 'src/main/module.json5').read_bytes())['module']
            self.assertEqual((module['type'], module['deviceTypes']), ('feature', [device]))
            self.assertFalse(module.get('abilities'))
            extension = next(x for x in module['extensionAbilities'] if x['name'] == 'WallpaperExtAbility')
            self.assertEqual(extension['type'], 'wallpaper')
            self.assertEqual([x['name'] for x in module['requestPermissions']],
                             ['ohos.permission.GET_WALLPAPER', 'ohos.permission.READ_USER_STORAGE'])
        schema = PLUGIN + '/res/schemas/ohos-project-build-profile-schema.json'
        script = '''const f=require('fs'),A=require(process.argv[1]+'/node_modules/ajv');
const validate=new A({strict:false,allErrors:true}).compile(JSON.parse(f.readFileSync(process.argv[2])));
for(const doc of JSON.parse(f.readFileSync(0,'utf8'))){if(!validate(doc))throw Error(JSON.stringify(validate.errors));}'''
        result = subprocess.run(['node', '-e', script, PLUGIN, schema],
                                input=json.dumps(list(after.values())), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # Actual GN keeps normal OS app signing and selects real modules.
        for project, expected in [(CONTACTS, ['entry']), (THEME, ['phone-wallpaper', 'pad-wallpaper'])]:
            text = (self.root / project / 'BUILD.gn').read_text()
            self.assertEqual(text.count('ohos_app('), len(expected))
            self.assertIn('part_name = "prebuilt_hap"', text)
            self.assertIn('certificate_profile = "signature/' + ('contacts' if project == CONTACTS else 'wallpaper') + '.p7b"', text)
            self.assertNotIn('ohos_js_assets(', text)
            for module in expected:
                self.assertIn(f'build_modules = [ "{module}" ]', text)

    def test_real_picker_and_wallpaper_renderer_contracts_are_distinct(self):
        # Inspect real implementation, not manufactured success handlers.
        extension = (self.root / CONTACTS / 'entry/src/main/ets/uiExtentionAbility/ContactUiExtentionAbility.ets').read_text()
        presenter = (self.root / CONTACTS / 'entry/src/main/ets/presenter/contact/batchselectcontacts/ContactsPickerPresenter.ets').read_text()
        page = (self.root / CONTACTS / 'entry/src/main/ets/pages/contacts/batchselectcontacts/ContactsPickerPage.ets').read_text()
        self.assertIn('extends UIExtensionAbility', extension)
        self.assertIn("loadContent('pages/ContactUiExtentionIndex', storage)", extension)
        self.assertIn('const len = 100;', presenter)
        for field in ['pickerData', 'index', 'total', 'contactObjects', 'selectContactIds']:
            self.assertIn("'" + field + "'", presenter)
        self.assertIn('sendData(parameters)', presenter)
        self.assertIn('terminateSelfWithResult(result)', presenter)
        self.assertIn('terminateSelfWithResult({ resultCode: 1 })', page)
        self.assertIn('returnDefaultSelectContactData()', page)
        native = (self.root / 'applications/standard/contacts_data/contacts/include/contacts_napi_utils.h').read_text()
        self.assertIn('CONTACT_UI_EXT_ABILITY_NAME = "ContactUiExtentionAbility"', native)
        self.assertIn('CONTACT_PACKAGE_NAME = "com.ohos.contacts"', native)
        self.assertIn('CONTACT_UI_EXT_TYPE = "sys/commonUI"', native)
        for product in ('phone', 'pad'):
            source = (self.root / THEME / 'product' / product / 'src/main/ets/WallpaperExtAbility/WallpaperExtAbility.ts').read_text()
            self.assertIn("from '@ohos.WallpaperExtension'", source)
            self.assertIn('wallPaper.getPixelMap(0,', source)
            self.assertNotIn('extends UIExtensionAbility', source)
        service = (self.root / 'base/theme/wallpaper_mgr/services/src/wallpaper_service.cpp').read_text()
        self.assertIn('OHOS_WALLPAPER_BUNDLE_NAME = "com.ohos.launcher"', service)
        self.assertIn('want.SetElementName(OHOS_WALLPAPER_BUNDLE_NAME, "WallpaperExtAbility")', service)


if __name__ == '__main__':
    unittest.main()
