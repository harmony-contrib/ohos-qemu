"""Create nonce certificate data for one actual held-guest UI case.

This is a fixture producer, not a certificate or host acceptance test. Every
OpenSSL command uses the original Owner's process authority and raw receipts.
The guest independently imports, selects, consumes and removes these bytes.
"""
from pathlib import Path
import json
import os
import re

from capability578_owned_io import reference, require


def prepare(io, run):
    require(re.fullmatch('[a-f0-9]{32}', run) is not None and
            'apps_ui578_certificate_input' not in io.environment,
            'one fresh actual nonce certificate fixture required')
    root = io.output / ('certificate-' + run)
    root.mkdir(mode=0o700, exist_ok=False)
    key, pem, der, p12 = [root / name for name in ('private.key', 'public.pem', 'public.der', 'credential.p12')]
    commands = []

    def openssl(label, *arguments):
        row = io.command(['openssl', *map(str, arguments)], 'certificate_' + label, timeout=90)
        commands.append(io.ref_receipt(row))

    openssl('create', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', '2',
            '-subj', '/CN=apps578-' + run, '-keyout', key, '-out', pem)
    openssl('der', 'x509', '-in', pem, '-outform', 'DER', '-out', der)
    openssl('pkcs12', 'pkcs12', '-export', '-inkey', key, '-in', pem,
            '-name', 'apps_' + run[:16], '-passout', 'pass:qemu_test_only', '-out', p12)
    for path in (key, pem, der, p12):
        require(path.is_file() and not path.is_symlink(), 'actual generated certificate fixture missing')
        os.chmod(path, 0o600)
    require(0 < der.stat().st_size <= 8192 and 0 < p12.stat().st_size <= 20480,
            'actual certificate fixture exceeds guest input bounds')
    producer = {'schema': 'actual-owned578-certificate-producer/v1', 'run': run,
        'boot_id': io.boot_id, 'archive_sha256': io.archive_sha256,
        'p12': reference(p12), 'der': reference(der), 'commands': commands}
    producer_path = root / 'producer.json'
    producer_path.write_text(json.dumps(producer, indent=2) + '\n')
    value = {k: producer[k] for k in ('run', 'boot_id', 'archive_sha256', 'p12', 'der')}
    value.update(schema='actual-apps578-certificate-input/v1', producer=reference(producer_path))
    path = root / 'input.json'
    path.write_text(json.dumps(value, indent=2) + '\n')
    io.environment['apps_ui578_certificate_input'] = reference(path)
    return reference(path)
