"""Linux host checks of the actual C reader; no guest or policy claims."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('cc'),
                     'actual Linux bpf.h and host C compiler required; run in local Docker')
class BpfNetstatsReadbackTest(unittest.TestCase):
    def test_actual_readonly_probe_body_and_failures(self):
        nonce = '0123456789abcdef' * 2
        with tempfile.TemporaryDirectory(prefix='bpf-readonly-host-') as temporary:
            binary = Path(temporary) / 'probe'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O1', '-g',
                            '-fsanitize=undefined', '-fno-sanitize-recover=all',
                            str(HERE / 'fixtures/bpf_netstats_readback_host.c'), '-o', str(binary)], check=True)
            def run(scenario, identity=nonce, uid='20010000', expected=1):
                return subprocess.run([str(binary), scenario, identity, uid, str(expected)],
                                      text=True, capture_output=True, check=True)
            for scenario in ('open-failure', 'info-failure', 'wrong-type', 'legacy-key',
                             'wrong-value', 'zero-id', 'zero-capacity', 'lookup-failure'):
                with self.subTest(scenario=scenario):
                    self.assertEqual(run(scenario).stdout, '')
            for uid in ('', '-1', '+1', '1x', ' 1', '4294967296', '00000000000'):
                with self.subTest(uid=uid):
                    self.assertEqual(run('invalid', uid=uid, expected=2).stdout, '')
            for identity in ('', 'a' * 31, 'a' * 33, 'G' * 32):
                with self.subTest(identity=identity):
                    self.assertEqual(run('invalid', identity=identity, expected=2).stdout, '')
            self.assertEqual(run('unprivileged', expected=2).stdout, '')
            value = json.loads(run('present', uid='4294967295', expected=0).stdout)
            self.assertEqual(value, dict(run_id=nonce, caller_uid=0, uid=4294967295, map_id=42,
                key_bytes=8, value_bytes=32, present=True, rx_packets='1', rx_bytes=str(2**64 - 1),
                tx_packets='3', tx_bytes=str(2**63 + 5)))
            value = json.loads(run('absent', expected=0).stdout)
            self.assertIs(value['present'], False)
            self.assertEqual([value[key] for key in ('rx_packets', 'rx_bytes', 'tx_packets', 'tx_bytes')], ['0'] * 4)
            # Exit failure must remain observable even after successful output.
            self.assertTrue(json.loads(run('close-failure').stdout)['present'])


if __name__ == '__main__':
    unittest.main()
