"""Read and exercise an existing suite-owned acceptance guest; never boot or kill it."""
import json
from pathlib import Path
import re
import secrets
import subprocess

from boot_package import FATAL, hdc_failed
from run_root_probe import digest, validate_identity


def validate_binding(boot, archive_sha):
    env = boot.get('test_environment', {})
    if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
            boot.get('scope') != 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate' or
            boot.get('archive_sha256') != archive_sha or env.get('external_keepalive') is not False or
            env.get('guest_arch') not in ('arm64', 'armv7a', 'x86_64') or
            env.get('device_type') not in ('phone', '2in1') or
            type(env.get('qemu_pid')) is not int or env['qemu_pid'] <= 1 or
            not isinstance(env.get('qemu_command'), str) or
            re.fullmatch(r'127\.0\.0\.1:[0-9]+', env.get('target', '')) is None or
            re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', env.get('boot_id', '')) is None or
            re.fullmatch(r'[a-fA-F0-9]{64}', env.get('udid', '')) is None or
            not Path(env.get('qmp_socket', '')).is_absolute() or
            env['qmp_socket'] not in env['qemu_command'] or
            any(boot.get(key) for key in ('candidate_kernel', 'kernel_command_line_diagnostic',
                'diagnostic_assistance', 'diagnostic_power_button'))):
        raise ValueError('unchanged enclosing acceptance guest required')
    return env


class EnclosingAcceptanceGuest:
    def __init__(self, boot, archive, hdc, output):
        self.boot = Path(boot)
        if self.boot.is_symlink() or not self.boot.is_file():
            raise ValueError('actual enclosing boot evidence required')
        self.env = validate_binding(json.loads(self.boot.read_text()), digest(archive))
        self.boot_sha = digest(self.boot)
        self.target, self.udid = self.env['target'], self.env['udid']
        self.hdc, self.output = str(hdc), Path(output)
        self.output.mkdir(exist_ok=False)
        self.report = dict(test_environment=self.env, commands=[])

    def healthy(self):
        if digest(self.boot) != self.boot_sha:
            raise ValueError('enclosing boot evidence changed during child test')
        actual = subprocess.check_output(['ps', '-p', str(self.env['qemu_pid']), '-o', 'command='],
                                         text=True, timeout=10).strip()
        if actual != self.env['qemu_command']:
            raise ValueError('enclosing QEMU process was replaced')
        if FATAL.search((self.boot.parent / 'qemu.log').read_text(errors='replace')):
            raise ValueError('enclosing guest has a fatal service/kernel failure')

    def shell(self, script, label):
        self.healthy()
        if re.fullmatch('[a-zA-Z0-9_-]+', label) is None:
            raise ValueError('bounded log label required')
        marker = '__QEMU_CHILD_EXIT_' + secrets.token_hex(16) + '__='
        wrapped = '(' + script + '); task_child_rc=$?; printf "\\n' + marker + '%s\\n" "$task_child_rc"'
        argv = [self.hdc, '-t', self.target, 'shell', wrapped]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        path = self.output / (str(len(self.report['commands'])).zfill(3) + '-' + label + '.log')
        path.write_text(result.stdout + result.stderr)
        self.report['commands'].append(dict(argv=argv, exit_code=result.returncode, log=str(path), sha256=digest(path)))
        text = result.stdout.replace('\r', '')
        if (result.returncode or hdc_failed(result.stdout, result.stderr) or
                not text.endswith('\n' + marker + '0\n') or text.count(marker) != 1):
            raise ValueError('enclosing guest command failed: ' + label)
        return text.rsplit('\n' + marker, 1)[0]

    def start(self):
        validate_identity(self.shell('id -u; param get const.product.devicetype; uname -m', 'identity-before'),
                          self.env['guest_arch'], self.env['device_type'])
        if self.shell('cat /proc/sys/kernel/random/boot_id', 'boot-before').strip() != self.env['boot_id']:
            raise ValueError('enclosing guest kernel identity changed')
        return self

    def close(self):
        # Ownership remains with the suite. In particular, never kill by PID.
        pass
