#!/usr/bin/env python3
"""Verify pinned regdb bytes and their signer against the unmodified kernel key."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

ASSETS = {
    'device/soc/unisoc/p7885/hardware/wcn/regulatory.db':
        'd67150c8925a98a4783c2c9a3e652b5a21fcdf8119875e1d2860c7c180fa98f8',
    'device/soc/unisoc/p7885/hardware/wcn/regulatory.db.p7s':
        '704ba48e3b12a28d3ed9411e526f127870201ba5007ee0c17ae92dafe2444fa5',
    'kernel/linux/linux-6.6/net/wireless/certs/wens.hex':
        '6485f5ddecbecbf73113dc669fe23da07f1a5ab60fb1ad932b0062f9d7fe8753',
}


def verify(root):
    root = Path(root).resolve()
    for name, expected in ASSETS.items():
        path = root / name
        if path.resolve() != path or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('unknown regulatory input: ' + name)
    database, signature, key = [root / name for name in ASSETS]
    trusted = bytes(int(value, 16) for value in re.findall(r'0x([0-9a-fA-F]{2})', key.read_text()))
    with tempfile.TemporaryDirectory(prefix='qemu-regdb-verify-') as directory:
        certificate = Path(directory) / 'signer.pem'
        result = subprocess.run(['openssl', 'cms', '-verify', '-binary', '-inform', 'DER',
            '-in', str(signature), '-content', str(database), '-noverify',
            '-signer', str(certificate), '-out', '/dev/null'], capture_output=True, check=True)
        # -noverify only avoids the host CA store. Trust is the exact kernel DER
        # certificate, not an arbitrary self-signed certificate from the bundle.
        if certificate.read_text().count('-----BEGIN CERTIFICATE-----') != 1:
            raise ValueError('expected exactly one regulatory signer')
        actual = subprocess.check_output(['openssl', 'x509', '-in', str(certificate), '-outform', 'DER'])
        if actual != trusted:
            raise ValueError('regulatory signer is not the built-in kernel certificate')
    for product in ('arm', 'arm64', 'x86_64'):
        config = (root / ('device/qemu/common/virt_full/kernel/' + product + '_virt_defconfig')).read_text()
        for setting in ('CONFIG_CFG80211_REQUIRE_SIGNED_REGDB=y',
                        'CONFIG_CFG80211_USE_KERNEL_REGDB_KEYS=y', 'CONFIG_FW_LOADER=y'):
            if setting not in config.splitlines():
                raise ValueError('missing regulatory enforcement: ' + product + ': ' + setting)
    return {name: value for name, value in ASSETS.items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    verify(args.source_root)
    print('verified pinned regdb signature and exact built-in kernel signer')
