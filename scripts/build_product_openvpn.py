#!/usr/bin/env python3
"""Build after the product's real musl/OpenSSL targets, then publish atomically.

Standalone dependency builds retain their read-only source/output requirement.
The GN action has a separate, constrained generated-output directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import os
import secrets
import tempfile

from build_openvpn_ohos import TARGETS, build, digest, product_build_path, recipe_identity


def valid_sha256(value):
    return (isinstance(value, str) and len(value) == 64 and
            all(character in '0123456789abcdef' for character in value))


def safe_relative_path(value):
    if (not isinstance(value, str) or not value or '\\' in value or
            any(ord(character) < 32 or ord(character) == 127 for character in value)):
        return False
    path = Path(value)
    return (not path.is_absolute() and path.as_posix() == value and
            bool(path.parts) and not any(part in ('.', '..') for part in path.parts))


def valid_recipe(recipe):
    if not isinstance(recipe, dict) or set(recipe) != {'recipe_sha256', 'files_sha256'}:
        return False
    files = recipe['files_sha256']
    if (not isinstance(files, dict) or not files or not valid_sha256(recipe['recipe_sha256']) or
            any(not safe_relative_path(name) or not valid_sha256(value) for name, value in files.items())):
        return False
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest() == recipe['recipe_sha256']


def verified_output(directory, *, current=False, product=None):
    error = ('new OpenVPN output evidence is not the complete current source build' if current else
             'changed OpenVPN output evidence; preserving caller files')
    try:
        receipt, binary = directory / 'build-evidence.json', directory / 'openvpn'
        if (directory.is_symlink() or not directory.is_dir() or
                receipt.is_symlink() or not receipt.is_file()):
            raise ValueError(error)
        report = json.loads(receipt.read_text())
        if (not isinstance(report, dict) or type(report.get('schema_version')) is not int or
                report['schema_version'] != 2 or
                report.get('component') != 'fixed source OpenVPN for QEMU OHOS' or
                not isinstance(report.get('product'), str) or report['product'] not in TARGETS or
                (product is not None and report['product'] != product) or
                report.get('status') != 'pass_source_build_ONLY_NOT_packaged_or_runtime' or
                not valid_recipe(report.get('recipe')) or
                (current and report['recipe'] != recipe_identity()) or
                report.get('runtime_gate_passed') is not False or
                binary.is_symlink() or not binary.is_file() or
                not valid_sha256(report.get('binary_sha256')) or digest(binary) != report['binary_sha256']):
            raise ValueError(error)
        commands = report.get('commands')
        if not isinstance(commands, list) or not commands:
            raise ValueError(error)
        for command in commands:
            if (not isinstance(command, dict) or not safe_relative_path(command.get('log')) or
                    len(Path(command['log']).parts) != 1 or
                    type(command.get('exit_code')) is not int or command['exit_code'] != 0 or
                    not valid_sha256(command.get('sha256'))):
                raise ValueError(error)
            log = directory / command['log']
            if log.is_symlink() or not log.is_file() or digest(log) != command['sha256']:
                raise ValueError(error)
    except (OSError, ValueError, UnicodeError) as failure:
        raise ValueError(error) from failure
    return report


def publish(source, destination):
    if source.is_symlink() or destination.is_symlink():
        raise ValueError('OpenVPN output directory must not be an alias')
    report = verified_output(source, current=True)
    if destination.exists():
        if destination.is_dir() and not any(destination.iterdir()):
            # GN may pre-create the output directory. Let the kernel replace
            # only an empty real directory atomically: a raced-in child or
            # alias makes rename fail without deleting or following anything.
            os.replace(source, destination)
            return
        previous = destination / 'build-evidence.json'
        if previous.is_symlink() or not previous.is_file() or destination.is_symlink():
            raise ValueError('unknown OpenVPN output; preserving caller files')
        # A historical recipe may differ from today's files, but its own
        # mapping/hash and every successful command log must still agree.
        verified_output(destination, product=report['product'])
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
