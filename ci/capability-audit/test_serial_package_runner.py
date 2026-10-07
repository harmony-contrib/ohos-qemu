"""Serial runner safety/completeness fixtures; not real guest acceptance."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest

from run_serial_package_probe import run, rows
from run_root_probe import digest


class SerialPackageRunnerTests(unittest.TestCase):
    def test_jsonl_parser_never_ignores_malformed_records(self):
        self.assertEqual(rows('{"case":"fixture"}\n'), [{'case': 'fixture'}])
        with self.assertRaises(ValueError):
            rows('printed PASS instead of an actual record')

    def test_old_diagnostic_boot_rejected_without_any_guest_operations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'fixture.tar.gz'
            archive.write_text('not a real package; early rejection fixture')
            boot = root / 'boot.json'
            boot.write_text(json.dumps({'status': 'pass', 'purpose': 'diagnostic',
                'archive_sha256': digest(archive), 'test_environment': {'boot_id': 'fixture',
                    'target': 'fixture', 'guest_arch': 'arm64', 'device_type': '2in1'}}))
            report = run(argparse.Namespace(boot=boot, archive=archive, output=root / 'test',
                hdc='not-an-executable', sdk=root, source_volume='fixture', docker_image='fixture'))
            self.assertEqual(report['status'], 'fail')
            self.assertEqual(report['commands'], [])
            self.assertFalse(report['first_artifact_behavior_gate_passed'])

    def test_default_suite_executes_serial_before_full_gap_closure(self):
        source = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        self.assertLess(source.index("'run_serial_package_probe.py'"), source.index("'verify_gap_closure.py'"))
        self.assertIn("check('serial', work / 'serial/evidence.json', [serial_record])", source)
        runner = Path(__file__).with_name('run_serial_package_probe.py').read_text()
        for forbidden in ('setenforce', 'chmod 666', 'AddPortAuthorization(', 'addPortAuthorization('):
            self.assertNotIn(forbidden, runner)
        for required in ('basic-trusted-deny', 'basic-trusted-allow', 'unplug-while-real-authorization-pending',
                         'replug-new-trusted-deny', 'verify_basic(', 'verify_attachment('):
            self.assertIn(required, runner)


if __name__ == '__main__':
    unittest.main()
