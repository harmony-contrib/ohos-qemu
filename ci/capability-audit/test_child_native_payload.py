"""Actual SDK stripping fixture and native parameter-format rejection vectors."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import os
from child_native_payload import processed_payload, parameter_matches


class ChildNativePayloadTests(unittest.TestCase):
    fixtures=Path(__file__).with_name('fixtures')/'child_native_strip_diagnostic'

    def strip_tool(self):
        sdk=os.environ.get('QEMU_TEST_SDK_HOME','/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0')
        candidates=[str(Path(sdk)/'native/llvm/bin/llvm-strip'),shutil.which('llvm-strip'),
                    '/opt/homebrew/opt/llvm/bin/llvm-strip']
        for candidate in candidates:
            if candidate and Path(candidate).is_file():return Path(candidate)
        self.skipTest('LLVM strip unavailable on this host')

    def test_actual_native_ELF_reproduces_official_Hvigor_member(self):
        strip=self.strip_tool();p=json.loads((self.fixtures/'provenance.json').read_text())
        raw=self.fixtures/'compiled.elf';expected=(self.fixtures/'HAP-member.elf').read_bytes()
        self.assertNotEqual(raw.read_bytes(),expected)
        output=processed_payload(raw,strip,p['compiled_sha256'],hashlib.sha256(strip.read_bytes()).hexdigest())
        self.assertEqual(output,expected)
        with self.assertRaisesRegex(ValueError,'native input differs'):
            processed_payload(raw,strip,'0'*64,hashlib.sha256(strip.read_bytes()).hexdigest())
        with self.assertRaisesRegex(ValueError,'strip identity differs'):
            processed_payload(raw,strip,p['compiled_sha256'],'0'*64)
        with tempfile.TemporaryDirectory() as temporary:
            alias_dir=Path(temporary)/'official-tool-name';alias_dir.mkdir()
            strip_alias=alias_dir/'llvm-strip';strip_alias.symlink_to(strip.resolve())
            self.assertEqual(processed_payload(raw,strip_alias,p['compiled_sha256'],
                hashlib.sha256(strip.read_bytes()).hexdigest()),expected)
            link=Path(temporary)/'borrowed.elf';link.symlink_to(raw.resolve())
            with self.assertRaises(ValueError):
                processed_payload(link,strip,p['compiled_sha256'],hashlib.sha256(strip.read_bytes()).hexdigest())

    def test_native_trailing_whitespace_preserves_exact_single_parameter_value(self):
        for expected in ('false','0','phone','2in1'):
            for actual in (expected+' \n',expected+'\r\n',expected+'\n'):
                with self.subTest(expected=expected,actual=actual):self.assertTrue(parameter_matches(actual,expected+'\n'))
            for actual in (None,True,0,'',expected+' foreign','foreign '+expected,'true' if expected!='true' else 'false'):
                with self.subTest(expected=expected,actual=actual):self.assertFalse(parameter_matches(actual,expected))


if __name__=='__main__':unittest.main()
