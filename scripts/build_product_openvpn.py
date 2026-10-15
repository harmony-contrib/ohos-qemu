#!/usr/bin/env python3
"""Build after the product's real musl/OpenSSL targets, then publish atomically.

Standalone dependency builds retain their read-only source/output requirement.
The GN action has a separate, constrained generated-output directory.
"""
import argparse
import json
from pathlib import Path
import os
import secrets
import tempfile

from build_openvpn_ohos import TARGETS, build, digest, product_build_path, recipe_identity


def publish(source, destination):
    if source.is_symlink() or destination.is_symlink():
        raise ValueError('OpenVPN output directory must not be an alias')
    report = json.loads((source / 'build-evidence.json').read_text())
    if (report.get('schema_version') != 2 or
            report.get('component') != 'fixed source OpenVPN for QEMU OHOS' or
            report.get('product') not in TARGETS or
            report.get('status') != 'pass_source_build_ONLY_NOT_packaged_or_runtime' or
            report.get('recipe') != recipe_identity() or
            report.get('runtime_gate_passed') is not False or
            (source / 'openvpn').is_symlink() or
            digest(source / 'openvpn') != report.get('binary_sha256')):
        raise ValueError('new OpenVPN output is not the complete current source build')
    for command in report['commands']:
        log = Path(command['log'])
        if (log.name != str(log) or log.name in ('', '.', '..') or
                (source / log).is_symlink() or digest(source / log) != command['sha256'] or
                command['exit_code'] != 0):
            raise ValueError('OpenVPN command evidence is missing or changed')
    if destination.exists():
        previous = destination / 'build-evidence.json'
        if previous.is_symlink() or not previous.is_file() or destination.is_symlink():
            raise ValueError('unknown OpenVPN output; preserving caller files')
        old = json.loads(previous.read_text())
        if (old.get('schema_version') != 2 or old.get('component') != report['component'] or
                old.get('product') != report['product'] or
                old.get('status') != 'pass_source_build_ONLY_NOT_packaged_or_runtime' or
                old.get('runtime_gate_passed') is not False or
                (destination / 'openvpn').is_symlink() or
                digest(destination / 'openvpn') != old.get('binary_sha256')):
            raise ValueError('changed OpenVPN output; preserving caller files')
        # Retain the earlier successful binary and logs if recompilation is
        # needed. Failed new attempts also retain their own complete logs.
        backup = destination.with_name(destination.name + '.previous-' + secrets.token_hex(8))
        os.replace(destination, backup)
    os.replace(source, destination)


def run(args):
    source = args.source_root.resolve()
    if args.output.is_symlink():
        raise ValueError('OpenVPN output directory must not be an alias')
    target = args.output.resolve()
    product_build_path(source, args.product, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    attempt = Path(tempfile.mkdtemp(prefix='.openvpn-attempt-', dir=target.parent))
    output = attempt / 'artifact'
    report = build(argparse.Namespace(source_root=source, archive=args.archive,
        output=output, product=args.product, jobs=args.jobs, product_build=True))
    if report['status'] != 'pass_source_build_ONLY_NOT_packaged_or_runtime':
        raise ValueError('OpenVPN build failed; attempt logs preserved at ' + str(output))
    publish(output, target)
    attempt.rmdir()
    print('published current source-built OpenVPN; no guest runtime claim')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=TARGETS, required=True)
    parser.add_argument('--jobs', type=int, choices=range(1, 9), default=1)
    run(parser.parse_args())
