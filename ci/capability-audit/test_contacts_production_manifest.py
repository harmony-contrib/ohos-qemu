import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
FIX=ROOT/'ci/capability-audit/fixtures/contacts_production_manifest'


class ContactsProductionManifest(unittest.TestCase):
    def test_real_duplicate_URI_fix_preserves_entries_and_replays(self):
        provenance=json.loads((FIX/'provenance.json').read_text())
        plugin='/Volumes/PSSD/qemu/openharmony/prebuilts/tool/command-line-tools/6.x/hvigor/hvigor-ohos-plugin/node_modules/json5'
        def parse(data):
            return json.loads(subprocess.check_output(['node','-e',
                'const fs=require("fs"),j=require(process.argv[1]);process.stdout.write(JSON.stringify(j.parse(fs.readFileSync(0,"utf8"))))',plugin],input=data))
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary).resolve();project=source/'applications/standard/contacts';originals={}
            for name,row in provenance['files'].items():
                data=gzip.decompress(base64.b64decode((FIX/row['file']).read_bytes()))
                self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256'])
                p=project/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);originals[name]=data
            argv=['bash',str(ROOT/'patches/common/applications/standard/contacts/production_manifest/apply.sh'),'--source-root',str(source)]
            for _ in range(3):
                r=subprocess.run(argv,capture_output=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            actual=parse((project/'entry/src/main/module.json5').read_bytes());expected=parse(originals['entry/src/main/module.json5'])
            expected['module']['abilities'][0]['skills'][0]['uris'].insert(0,{'scheme':'tel'})
            self.assertEqual(actual,expected)
            self.assertEqual(actual['module']['dependencies'],[{'bundleName':'com.ohos.security.pickersheet','moduleName':'pickersheetlibrary'}])
            expected=parse(originals['oh-package.json5']);expected['devDependencies'].pop('@ohos/hypium')
            self.assertEqual(parse((project/'oh-package.json5').read_bytes()),expected)
            p=project/'entry/src/main/module.json5';p.write_bytes(p.read_bytes()+b'\n//unknown edit\n')
            before=p.read_bytes();self.assertNotEqual(subprocess.run(argv,capture_output=True).returncode,0);self.assertEqual(p.read_bytes(),before)


if __name__=='__main__':unittest.main()
