"""Patch idempotence/additive-public-export fixtures; no provider success."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import patch_sections, write_preimages

ROOT=Path(__file__).resolve().parents[2]
COMPONENT=ROOT/'patches/common/foundation/distributeddatamgr/relational_store/api26_cloud_flag'
PATCH=COMPONENT/'0001-export-existing-cloud-record-operation-flag.patch'


class CloudFlagTests(unittest.TestCase):
    def test_only_additive_enum_and_default_export_hunks(self):
        sections=patch_sections(PATCH)
        self.assertEqual(set(sections),{'foundation/distributeddatamgr/relational_store/frameworks/js/napi/cloud_extension/cloud_extension_stub.js'})
        self.assertEqual(len(next(iter(sections.values()))),2)
        removed=[line for line in PATCH.read_text().splitlines() if line.startswith('-') and not line.startswith('---')]
        self.assertEqual(removed,[])
        lines=[line[1:] for line in PATCH.read_text().splitlines() if line.startswith('+') and not line.startswith('+++')]
        self.assertEqual(lines,[
            '    let operationFlag;',
            '    (function (flag) {',
            '        flag[flag["INSERT"] = 0] = "INSERT";',
            '        flag[flag["UPDATE"] = 1] = "UPDATE";',
            '        flag[flag["DELETE"] = 2] = "DELETE";',
            '    })(operationFlag = a.Flag || (a.Flag = {}));',
            '    Flag: cloudExtension.Flag,'])

    def test_component_applies_twice_without_touching_protocol_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);write_preimages(root,PATCH)
            for _ in range(2):
                result=subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],
                                      capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            subprocess.run(['git','-C',str(root),'apply','--check','--reverse',str(PATCH)],check=True)


if __name__=='__main__':unittest.main()
