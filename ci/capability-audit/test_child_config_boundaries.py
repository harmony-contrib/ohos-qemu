"""Exact source patch and real extracted functions; never packaged acceptance."""
import base64
import gzip
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from compile_child_config_boundaries import run

ROOT=Path(__file__).resolve().parents[2]
COMPONENT=ROOT/'patches/common/foundation/ability/ability_runtime/native_child_process'
spec=importlib.util.spec_from_file_location('child_config_source',COMPONENT/'verify_config_source.py')
baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)


class ChildConfigBoundariesTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.target=self.root/baseline.PROJECT/baseline.RELATIVE
        self.target.parent.mkdir(parents=True)
        raw=gzip.decompress(base64.b64decode((ROOT/'ci/capability-audit/fixtures/child_config_after_argument_patches.cpp.gz.b64').read_bytes()))
        self.assertEqual(hashlib.sha256(raw).hexdigest(),baseline.ORIGINAL)
        self.target.write_bytes(raw)

    def apply(self):
        return subprocess.run(['bash',str(ROOT/'patches/lib/apply_patch.sh'),str(self.root),
            str(COMPONENT/'0003-validate-config-boundaries.patch')],capture_output=True,text=True)

    def test_exact_apply_idempotence_and_unknown_source_preservation(self):
        self.assertFalse(baseline.validate(self.root))
        self.assertEqual(self.apply().returncode,0)
        self.assertTrue(baseline.validate(self.root,True))
        repaired=self.target.read_bytes()
        self.assertEqual(self.apply().returncode,0);self.assertEqual(self.target.read_bytes(),repaired)
        self.target.write_bytes(repaired+b'// unrelated user edit\n')
        with self.assertRaises(ValueError):baseline.validate(self.root)
        self.assertEqual(self.target.read_bytes(),repaired+b'// unrelated user edit\n')

    def test_actual_functions_compile_and_reject_invalid_modes_without_mutation(self):
        run(SimpleNamespace(source_root=self.root,output=self.root/'compile',cxx='c++'))
        self.assertFalse(baseline.validate(self.root))

    def test_symlink_source_rejected(self):
        original=self.target.read_bytes();other=self.root/'external.cpp';other.write_bytes(original)
        self.target.unlink();self.target.symlink_to(other)
        with self.assertRaises(ValueError):baseline.validate(self.root)
        self.assertEqual(other.read_bytes(),original)


if __name__=='__main__':unittest.main()
