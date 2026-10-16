"""Host selection counterexamples only; constructed HAP/receipts are not builds."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import batch_apps_contact_picker_coordinator as c


class ThemeModuleSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.source = self.root / 'theme'; self.source.mkdir()
        self.rows = {}; self.haps = []
        self.commands = []
        for kind in ('phone', 'pad'):
            module = kind + '_wallpaper'; directory = self.source / 'product' / kind
            source = directory / 'src/main/module.json5'; source.parent.mkdir(parents=True); source.write_text('{"module":{}}')
            self.rows[str(source.relative_to(self.source))] = c.verifier.sha(source)
            hap = directory / 'build/default/outputs/default' / (module + '-default-unsigned.hap')
            hap.parent.mkdir(parents=True)
            with zipfile.ZipFile(hap, 'w') as archive:
                archive.writestr('module.json', json.dumps({'app': {'bundleName': 'com.ohos.wallpaper'}, 'module': {'name': module}}))
                archive.writestr('ets/modules.abc', b'HOST-ORACLE-ONLY'); archive.writestr('resources.index', b'HOST-ORACLE-ONLY')
            self.haps.append({**c.descriptor(hap), 'bytes': hap.stat().st_size})
            log = self.root / (kind + '.log'); log.write_text('BUILD SUCCESSFUL\n')
            self.commands.append({'project':'theme','label':module,'argv':['node','hvigor','assembleHap','-p','module='+module],
                'exit_code':0,'log':str(log),'sha256':c.verifier.sha(log)})
        self.report = {'exit_code':0,'source_commit':'a'*40,'runner_sha256':'b'*64,
            'source_files':{'theme':self.rows},'commands':self.commands,'haps':self.haps}
        self.evidence = self.root / 'sdk.json'; self.spec = {'source_project':str(self.source),'sdk_project':'theme',
            'unsigned_hap':c.descriptor(Path(self.haps[0]['path']))}
        self.save()

    def save(self):
        self.evidence.write_text(json.dumps(self.report)); self.spec['sdk_evidence'] = c.descriptor(self.evidence)

    def test_actual_module_shape_selects_one_hap_with_all_original_commands_preserved(self):
        result = c.verify_sdk_project(self.spec, module_name='phone_wallpaper')
        self.assertEqual(result['project_commands_verified'],2)
        self.assertEqual(result['source_files_verified'],2)
        self.spec['unsigned_hap'] = c.descriptor(Path(self.haps[1]['path']))
        c.verify_sdk_project(self.spec, module_name='pad_wallpaper')

    def test_shared_project_cannot_be_accepted_as_single_entry_build(self):
        with self.assertRaises(ValueError): c.verify_sdk_project(self.spec)

    def test_module_selection_is_limited_to_explicit_theme_modules(self):
        for module in ('entry','arbitrary',''):
            with self.assertRaises(ValueError): c.verify_sdk_project(self.spec,module_name=module)
        self.spec['sdk_project']='contacts'
        with self.assertRaises(ValueError): c.verify_sdk_project(self.spec,module_name='phone_wallpaper')

    def test_wrong_product_hap_cannot_borrow_selected_compile(self):
        self.spec['unsigned_hap']=c.descriptor(Path(self.haps[1]['path']))
        with self.assertRaises(ValueError): c.verify_sdk_project(self.spec,module_name='phone_wallpaper')

    def test_duplicate_compile_missing_p_flag_and_competing_module_rejected(self):
        original=list(self.commands[0]['argv'])
        for argv in (original[:-2]+['module=phone_wallpaper'],original+['-p','module=pad_wallpaper'],['node','assembleHap']):
            self.commands[0]['argv']=argv; self.save()
            with self.assertRaises(ValueError): c.verify_sdk_project(self.spec,module_name='phone_wallpaper')
        self.commands[0]['argv']=original; self.commands.append(dict(self.commands[0])); self.save()
        with self.assertRaises(ValueError): c.verify_sdk_project(self.spec,module_name='phone_wallpaper')

    def test_failed_sibling_or_tampered_source_remains_failure(self):
        self.commands[1]['exit_code']=1; self.save()
        with self.assertRaises(ValueError): c.verify_sdk_project(self.spec,module_name='phone_wallpaper')
        self.commands[1]['exit_code']=0; self.save()
        (self.source/'product/phone/src/main/module.json5').write_text('changed')
        with self.assertRaises(ValueError): c.verify_sdk_project(self.spec,module_name='phone_wallpaper')


if __name__ == '__main__': unittest.main()
