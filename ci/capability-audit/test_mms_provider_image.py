"""Synthetic archive mutations only; never MMS/BMS/runtime proof."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import verify_mms_provider_image as V


class MmsImageBoundary(unittest.TestCase):
    def test_permission_export_and_intent_boundaries_are_exact(self):
        source = {'name': 'entry', 'type': 'entry', 'deviceTypes': ['default', 'tablet'],
            'mainElement': 'com.ohos.mms.MainAbility', 'requestPermissions': [{'name': 'ohos.permission.READ_MESSAGES'}],
            'abilities': [{'name': 'com.ohos.mms.MainAbility', 'visible': True, 'skills': [
                {'actions': ['ohos.want.action.sendData'], 'uris': [{'type': 'text/plain'}]}]}]}
        original = {'app': {'bundleName': 'com.ohos.mms', 'debug': False}, 'module': source}
        with tempfile.TemporaryDirectory() as directory:
            hap = Path(directory) / 'Mms.hap'
            def write(value, abc=b'synthetic-bytecode-only'):
                with zipfile.ZipFile(hap, 'w') as archive:
                    archive.writestr('module.json', json.dumps(value));archive.writestr('ets/modules.abc', abc)
                    archive.writestr('resources.index', b'fixture-resources')
            write(original);self.assertEqual(V.inspect_hap(hap, source)['bundle'], 'com.ohos.mms')
            for kind in ('identity', 'debug', 'extra-permission', 'duplicate-permission', 'visible', 'exported', 'skill', 'device', 'empty-abc'):
                broken = copy.deepcopy(original);module = broken['module']
                if kind == 'identity': broken['app']['bundleName'] = 'unrelated'
                elif kind == 'debug': broken['app']['debug'] = True
                elif kind == 'extra-permission': module['requestPermissions'].append({'name': 'ohos.permission.SEND_MESSAGES'})
                elif kind == 'duplicate-permission': module['requestPermissions'] *= 2
                elif kind == 'visible': module['abilities'][0]['visible'] = False
                elif kind == 'exported': module['abilities'][0]['exported'] = True
                elif kind == 'skill': module['abilities'][0]['skills'] = []
                elif kind == 'device': module['deviceTypes'] = ['2in1']
                write(broken, b'' if kind == 'empty-abc' else b'synthetic-bytecode-only')
                with self.subTest(kind=kind), self.assertRaises(ValueError): V.inspect_hap(hap, source)

    def test_package_recipe_mandates_the_actual_image_check(self):
        recipe = (ROOT / 'scripts/package_standard_qemu.sh').read_text()
        self.assertEqual(recipe.count('"${SCRIPT_DIR}/verify_mms_provider_image.py"'), 1)
        self.assertIn('--source-root "${SOURCE_ROOT}" --output "${PACKAGE_DIR}/mms-provider-evidence.json"', recipe)


if __name__ == '__main__': unittest.main()
