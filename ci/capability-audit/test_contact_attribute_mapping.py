"""Public-to-storage boundary fixtures; not a guest/provider acceptance claim."""
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run, patch_sections, write_preimages
from contact_sync_mode_contract import ATTRIBUTE_MEMBERS

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/applications/standard/contacts_data/attribute_mapping'
PATCH = COMPONENT / '0001-separate-public-attributes-from-storage-types.patch'
HEADER = 'applications/standard/contacts_data/contacts/include/contacts_napi_object.h'
SOURCE = 'applications/standard/contacts_data/contacts/src/contacts_build.cpp'


class ContactAttributeMappingTests(unittest.TestCase):
    def test_all_sdk_ids_translate_without_changing_database_ids(self):
        sections = patch_sections(PATCH)
        header = '\n'.join('\n'.join(after) for _, _, after in sections[HEADER])
        values = dict((name, int(value)) for name, value in re.findall(r'(ATTR_\w+) = (\d+)', header))
        # EMAIL is unchanged and outside the diff hunk.
        values.setdefault('ATTR_EMAIL', 1)
        self.assertEqual(values, dict(zip(ATTRIBUTE_MEMBERS, range(14))))
        code = '\n'.join(sections[SOURCE][0][2])
        helper = code[code.index('static int AttributeToDataType'):code.index('ContactAttributes ContactsBuild::')]
        names = ('CONTACT_EVENT', 'EMAIL', 'GROUP_MEMBERSHIP', 'IM', 'NAME', 'NICKNAME', 'NOTE',
                 'ORGANIZATION', 'PHONE', 'PHOTO', 'POSTAL_ADDRESS', 'RELATION', 'SIP_ADDRESS', 'WEBSITE')
        storage = (11, 1, 9, 2, 6, 3, 10, 4, 5, 8, 7, 13, 17, 12)
        prefix = '#include <cassert>\n#include <cstdint>\n#include <limits>\n'
        prefix += 'enum class Attribute { ' + ','.join(name + '=' + str(value) for name, value in values.items()) + ' };\n'
        prefix += '\n'.join('constexpr int ' + name + '=' + str(value) + ';' for name, value in zip(names, storage))
        main = '\nint main() {\n'
        for public, internal in enumerate(storage):
            main += f'assert(AttributeToDataType({public}) == {internal});\n'
        main += '''for (int64_t bad : {-1LL, 14LL, 17LL, 99LL, 4294967296LL}) {
            assert(AttributeToDataType(bad) == -1);
        }
        assert(AttributeToDataType(std::numeric_limits<int64_t>::min()) == -1);
        assert(AttributeToDataType(std::numeric_limits<int64_t>::max()) == -1);
        }'''
        compile_run('#include <initializer_list>\n' + prefix + helper + main, language='c++')

    def test_exact_repeat_and_partial_unknown_states(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_preimages(root, PATCH)
            # The original upstream CPP intentionally has no final newline.
            source = root / SOURCE
            source.write_bytes(source.read_bytes().rstrip(b'\n'))
            old = {name: (root / name).read_bytes() for name in (HEADER, SOURCE)}
            subprocess.run(['git', '-C', str(root), 'apply', str(PATCH)], check=True, capture_output=True)
            new = {name: (root / name).read_bytes() for name in old}
            component = root / 'recipe' / COMPONENT.relative_to(ROOT)
            shutil.copytree(COMPONENT, component)
            shutil.copytree(ROOT / 'patches/lib', root / 'recipe/patches/lib')
            verifier = component / 'verify_source.py'
            text = verifier.read_text()
            hashes = re.findall(r"'([0-9a-f]{64})'", text)
            for original, replacement in zip(hashes, [hashlib.sha256(data).hexdigest()
                    for name in (HEADER, SOURCE) for data in (old[name], new[name])]):
                text = text.replace(original, replacement)
            verifier.write_text(text)
            for name, data in old.items():
                (root / name).write_bytes(data)
            command = ['bash', str(component / 'apply.sh'), '--source-root', str(root)]
            for _ in range(2):
                subprocess.run(command, check=True, capture_output=True)
            self.assertEqual({name: (root / name).read_bytes() for name in old}, new)
            (root / HEADER).write_bytes(old[HEADER])
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual((root / SOURCE).read_bytes(), new[SOURCE])
            (root / HEADER).write_bytes(new[HEADER] + b'// unknown edit\n')
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_input_translation_is_single_boundary_and_unknown_is_not_all(self):
        patch = PATCH.read_text()
        self.assertIn('+        attrVector.push_back(AttributeToDataType(intNapiValue));', patch)
        self.assertIn('+            attrVector.push_back(-1);', patch)
        self.assertIn('-        if (intNapiValue != 0)', patch)
        self.assertNotIn('contacts_napi_common.h', patch)
        script = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(script.count('bash "${CONTACT_ATTRIBUTE_MAPPING_SCRIPT}" --source-root "${OHOS_ROOT}"'), 1)


if __name__ == '__main__':
    unittest.main()
