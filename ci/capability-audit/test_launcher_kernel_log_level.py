"""Actual generated launcher argument fixtures, not real guest boot evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class KernelLoggingLauncherTests(unittest.TestCase):
    def test_three_abis_default_cli_env_override_invalid_and_idempotent(self):
        for arch, product, binary, cpu in (
                ('arm64', 'arm64_virt', 'qemu-system-aarch64', 'cortex-a57'),
                ('armv7a', 'armv7a_virt', 'qemu-system-arm', 'cortex-a7'),
                ('x86_64', 'x86_64_virt', 'qemu-system-x86_64', 'max')):
            with self.subTest(arch=arch), tempfile.TemporaryDirectory() as directory:
                package = Path(directory)
                (package / 'launch').mkdir()
                (package / 'images').mkdir()
                (package / 'manifest.json').write_text(json.dumps({
                    'product': product, 'guest_arch': arch,
                    'device_type_profile': 'qemu_phone_full_source',
                    'capabilities': {'absolute_pointer_sync': True}}))
                # Exercise the real packager's double-quoted ARM command and
                # direct x86 exec styles, both present in upstream products.
                base = ('#!/bin/bash\nOHOS_IMG="out/' + product + '/packages/phone/images"\n'
                        'DISPLAY_TYPE="${QEMU_DISPLAY:-none}"\n'
                        'HDC_HOST_PORT="${QEMU_HDC_HOST_PORT:-5555}"\n'
                        'case "${DISPLAY_TYPE}" in\n'
                        '  none) DISPLAY_ARGS="-device virtio-gpu-pci -display none -monitor none" ;;\n'
                        '  vnc) DISPLAY_ARGS="-device virtio-gpu-pci -vnc :21" ;;\n'
                        'esac\n')
                if arch == 'x86_64':
                    base += ('exec ' + binary + ' -cpu ' + cpu + ' -smp 4 -m 4096 '
                             '-device virtio-mouse-pci ${DISPLAY_ARGS} -append "oemmode=rd init=/init '
                             'ohos.required_mount.data=/dev/block/vda@/data@ext4@nosuid,nodev@wait"\n')
                else:
                    base += ('QEMU_CMD="' + binary + ' -cpu ' + cpu + ' -smp 4 -m 4096 '
                             '-device virtio-mouse-pci ${DISPLAY_ARGS} '
                             '-append \\"oemmode=rd loglevel=4 init=/init '
                             'ohos.required_mount.data=/dev/block/vda@/data@ext4@nosuid,nodev@wait\\""\n'
                             'eval "$QEMU_CMD"\n')
                launcher = package / 'launch/qemu_run.sh'
                launcher.write_text(base)
                launcher.chmod(0o700)
                rewrite = ['bash', str(ROOT / 'scripts/package_standard_qemu.sh'),
                           '--rewrite-package', str(package)]
                result = subprocess.run(rewrite, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                normalized = launcher.read_bytes()
                subprocess.run(rewrite, check=True, capture_output=True)
                self.assertEqual(launcher.read_bytes(), normalized)
                qemu = package / 'fixture-qemu'
                qemu.write_text('#!' + sys.executable + '\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
                qemu.chmod(0o700)
                argv = ['bash', str(package / 'launch/linux.sh'), '--headless', '--accel', 'tcg',
                        '--qemu', str(qemu)]
                environment = {key: value for key, value in os.environ.items()
                               if not key.startswith('QEMU_')}
                for options, level, inherited in (([], '4', None), ([], '2', '2'),
                        (['--kernel-log-level', '7'], '7', '2')):
                    env = dict(environment)
                    if inherited is not None:
                        env['QEMU_KERNEL_LOG_LEVEL'] = inherited
                    result = subprocess.run(argv + options, env=env, check=True,
                                            capture_output=True, text=True)
                    actual = json.loads(result.stdout.splitlines()[-1])
                    command_line = actual[actual.index('-append') + 1]
                    self.assertEqual([item for item in command_line.split() if item.startswith('loglevel=')],
                                     ['loglevel=' + level])
                    for parameter in ('snd-ens1370.index=0', 'snd-aloop.index=1',
                                      'snd-aloop.id=QemuCapture', 'snd-aloop.pcm_substreams=1'):
                        self.assertEqual(command_line.split().count(parameter), 1)
                if arch == 'x86_64':
                    powershell = (package / 'launch/windows.ps1').read_text()
                    for parameter in ('snd-ens1370.index=0', 'snd-aloop.index=1',
                                      'snd-aloop.id=QemuCapture', 'snd-aloop.pcm_substreams=1'):
                        self.assertIn(parameter, powershell)
                for invalid in ('-1', '9', '7 8', '7;exit 0'):
                    result = subprocess.run(argv + ['--kernel-log-level', invalid],
                        env=environment, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2)
                    result = subprocess.run(['bash', str(launcher)],
                        env=dict(environment, QEMU_KERNEL_LOG_LEVEL=invalid, QEMU_BIN=str(qemu)),
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
