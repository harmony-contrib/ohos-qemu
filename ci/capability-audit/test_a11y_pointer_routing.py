"""Actual generated launch commands, not package/guest behavior acceptance."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class AccessibilityPointerRoutingTests(unittest.TestCase):
    def test_six_profiles_multitouch_before_pointer_cli_env_and_rewrite(self):
        for device in ('phone', '2in1'):
            for arch, product, binary, cpu in (
                    ('arm64', 'arm64_virt', 'qemu-system-aarch64', 'cortex-a57'),
                    ('armv7a', 'armv7a_virt', 'qemu-system-arm', 'cortex-a7'),
                    ('x86_64', 'x86_64_virt', 'qemu-system-x86_64', 'max')):
                with self.subTest(device=device, arch=arch), tempfile.TemporaryDirectory() as directory:
                    package = Path(directory)
                    (package / 'launch').mkdir(); (package / 'images').mkdir()
                    (package / 'manifest.json').write_text(json.dumps(dict(product=product, guest_arch=arch,
                        device_type_profile='qemu_' + device + '_full_source', device_type=device,
                        capabilities=dict(absolute_pointer_sync=True))))
                    base = ('#!/bin/bash\nOHOS_IMG="out/' + product + '/packages/' + device + '/images"\n'
                        'DISPLAY_TYPE="${QEMU_DISPLAY:-none}"\nHDC_HOST_PORT="${QEMU_HDC_HOST_PORT:-5555}"\n'
                        'case "${DISPLAY_TYPE}" in\n'
                        '  none) DISPLAY_ARGS="-device virtio-gpu-pci -display none -monitor none" ;;\n'
                        '  vnc) DISPLAY_ARGS="-device virtio-gpu-pci -vnc :21" ;;\nesac\n')
                    suffix = (' -cpu ' + cpu + ' -smp 4 -m 4096 -device virtio-mouse-pci ${DISPLAY_ARGS} '
                              '-append "oemmode=rd init=/init '
                              'ohos.required_mount.data=/dev/block/vda@/data@ext4@nosuid,nodev@wait"')
                    if arch == 'x86_64': base += 'exec ' + binary + suffix + '\n'
                    else:
                        base += 'QEMU_CMD="' + binary + suffix.replace('"', '\\"') + '"\neval "$QEMU_CMD"\n'
                    core = package / 'launch/qemu_run.sh'; core.write_text(base); core.chmod(0o700)
                    rewrite = ['bash', str(ROOT / 'scripts/package_standard_qemu.sh'),
                               '--rewrite-package', str(package)]
                    result = subprocess.run(rewrite, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    before = core.read_bytes()
                    subprocess.run(rewrite, check=True, capture_output=True)
                    self.assertEqual(before, core.read_bytes())
                    self.assertEqual(core.read_text().count('${QEMU_A11Y_INPUT_ARGS} -device'), 1)
                    qemu = package / 'fixture-qemu'
                    qemu.write_text('#!' + sys.executable + '\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
                    qemu.chmod(0o700)
                    environment = {key: value for key, value in os.environ.items() if not key.startswith('QEMU_')}
                    for wrapper in ('linux.sh', 'macos.command'):
                        argv = ['bash', str(package / 'launch' / wrapper), '--headless', '--accel', 'tcg',
                                '--qemu', str(qemu), '--qmp-socket', str(package / 'owned-test.sock')]
                        for enabled, options, inherited in ((False, [], {}), (True, ['--a11y'], {}),
                                (True, [], dict(QEMU_ACCESSIBILITY='1'))):
                            reply = subprocess.run(argv + options, env=dict(environment, **inherited),
                                                   check=True, capture_output=True, text=True)
                            actual = json.loads(reply.stdout.splitlines()[-1])
                            devices = [actual[index + 1] for index, arg in enumerate(actual[:-1]) if arg == '-device']
                            self.assertEqual(devices.count('virtio-tablet-pci'), 1)
                            self.assertEqual(devices.count('virtio-multitouch-pci'), int(enabled))
                            if enabled:
                                self.assertLess(devices.index('virtio-multitouch-pci'), devices.index('virtio-tablet-pci'))
                                self.assertIn('unix:' + str(package / 'owned-test.sock') + ',server=on,wait=off', actual)
                    # The generated core also handles environment selection
                    # directly, not only the shell wrapper's --a11y flag.
                    reply = subprocess.run(['bash', str(core)], env=dict(environment, QEMU_BIN=str(qemu),
                        QEMU_DISPLAY='none', QEMU_ACCESSIBILITY='1'), check=True, capture_output=True, text=True)
                    actual = json.loads(reply.stdout.splitlines()[-1])
                    self.assertLess(actual.index('virtio-multitouch-pci'), actual.index('virtio-tablet-pci'))
                    for invalid in ('2', '-1', '1;exit 0'):
                        reply = subprocess.run(['bash', str(core)], env=dict(environment, QEMU_BIN=str(qemu),
                            QEMU_ACCESSIBILITY=invalid), capture_output=True, text=True)
                        self.assertEqual(reply.returncode, 2)
                    # Source ordering only: no claim of running PowerShell.
                    if arch == 'x86_64':
                        windows = (package / 'launch/windows.ps1').read_text()
                        self.assertIn('$A11yInputArgs,\n  "-device", "virtio-tablet-pci"', windows)
                        self.assertNotIn('$ArgsList += @("-device", "virtio-multitouch-pci")', windows)


if __name__ == '__main__': unittest.main()
