#!/usr/bin/env python3
"""Test real project quota on a disposable boot of one packaged artifact.

Never attach to an existing guest, change global mounts, or modify app quotas.
This kernel diagnostic does not attest Storage API or the full package gate.
"""
import argparse
import json
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_package import QemuGuest
from run_root_probe import digest, validate_elf
from verify_project_quota import verify


def data_device(text):
    rows = [line.split() for line in text.splitlines() if len(line.split()) == 6 and line.split()[1] == '/data']
    if (len(rows) != 1 or rows[0][2] != 'f2fs' or
            not re.fullmatch(r'/dev/block/vd[a-z]+[0-9]*', rows[0][0])):
        raise ValueError('one actual QEMU F2FS /data block device required')
    options = set(rows[0][3].split(','))
    if not {'rw', 'nosuid', 'nodev', 'usrquota', 'grpquota', 'prjquota'} <= options:
        raise ValueError('actual secure mount with all quota enforcement options required')
    return rows[0][0]


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'fail', 'scope': 'new_package_kernel_quota_NOT_Storage_API_or_full_gate',
              'archive': str(args.archive), 'archive_sha256': digest(args.archive),
              'probe': str(args.probe), 'probe_sha256': digest(args.probe),
              'nonce': secrets.token_hex(16), 'failures': [], 'commands': [],
              'first_artifact_behavior_gate_passed': False}
    guest = None
    try:
        with socket.socket() as connection:
            connection.bind(('127.0.0.1', 0))
            port = connection.getsockname()[1]
        guest = QemuGuest(argparse.Namespace(archive=args.archive, output=args.output / 'boot',
            hdc=args.hdc, hdc_port=port, accel='auto', resolution='1280x800', purpose='acceptance',
            wait_seconds=1800, stable_seconds=60, kernel_diagnostic=None,
            power_diagnostic_wakeup=False, hold=False)).start()
        env = guest.report['test_environment']
        report['test_environment'] = env
        validate_elf(args.probe, env['guest_arch'])
        mounts = guest.shell('cat /proc/mounts', 'quota-actual-mounts')
        device = data_device(mounts)
        report['actual_mounts'] = mounts
        remote = '/data/local/tmp/qemu-project-quota-probe-' + report['nonce']
        argv = [args.hdc, '-t', guest.target, 'file', 'send', str(args.probe), remote]
        sent = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        log = args.output / 'send-probe.log'
        log.write_text(sent.stdout + sent.stderr)
        report['commands'].append({'argv': argv, 'exit_code': sent.returncode,
                                   'log': str(log), 'sha256': digest(log)})
        if sent.returncode or '[Fail]' in log.read_text():
            raise ValueError('sending actual native probe failed')
        guest.shell('chmod 700 ' + remote, 'quota-probe-mode')
        command = ('unset LD_LIBRARY_PATH LD_PRELOAD; ' + remote + ' --disposable-guest ' + device +
                   ' ' + report['nonce'] + '; quota_probe_rc=$?; echo QEMU_QUOTA_EXIT:$quota_probe_rc')
        observed = guest.shell(command, 'quota-kernel-enforcement')
        raw = args.output / 'kernel-observation.log'
        raw.write_text(observed)
        report['commands'].append({'shell': command, 'log': str(raw), 'sha256': digest(raw)})
        if [line for line in observed.splitlines() if line.startswith('QEMU_QUOTA_EXIT:')] != ['QEMU_QUOTA_EXIT:0']:
            raise ValueError('actual kernel quota test failed')
        report['verified'] = verify(observed, report['nonce'])
        if guest.shell('cat /proc/sys/kernel/random/boot_id', 'quota-final-boot-id').strip() != env['boot_id']:
            raise ValueError('guest boot changed during quota test')
        guest.healthy()
        if digest(args.archive) != report['archive_sha256'] or digest(args.probe) != report['probe_sha256']:
            raise ValueError('archive or native probe changed during test')
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
    finally:
        if guest is not None:
            guest.close()
            report['disposable_guest_closed'] = True
        (args.output / 'diagnostic.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'output', 'probe'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--hdc', default='hdc')
    raise SystemExit(run(parser.parse_args()))
