#!/usr/bin/env python3
"""Run actual selected GN-generated input edges in owned Serial scratch.

Only the genuine musl header group, explicit generated-header edges and the
fixed jsoncpp generator output already present in the fresh graph are eligible.
This never fabricates headers,
uses an SDK sysroot instead of product inputs, or reports component acceptance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from compile_serial_component import build_environment


def allowed_input(target):
    jsoncpp_generator = 'gen/third_party/jsoncpp/jsoncpp-1.9.6/src/lib_json/json_reader.cpp'
    return target in ('musl_headers', jsoncpp_generator) or (
        bool(re.fullmatch(r'gen/[A-Za-z0-9_./-]+\.h', target)) and '..' not in Path(target).parts)


def quarantine_empty_jsoncpp_placeholder(staged, product_output, destination):
    """Preserve only the exact observed GN-created, directory-only skeleton.

    No file (even empty), symlink, generated header or unknown directory may be
    moved. This isolated workaround is not a common-installer fix or evidence
    that clean repository packaging works without a later normal-path test.
    """
    staged, product_output, destination = (value.resolve() for value in (staged, product_output, destination))
    tree = product_output / 'gen/third_party/jsoncpp/jsoncpp-1.9.6'
    if (not product_output.is_relative_to(staged / 'out') or tree.is_symlink()
            or not tree.resolve().is_relative_to(product_output) or destination.exists()
            or not destination.is_relative_to(staged) or destination.is_relative_to(product_output)):
        raise ValueError('JSONCPP placeholder quarantine must remain owned and separate')
    entries = [tree, *sorted(tree.rglob('*'))]
    if not tree.is_dir() or any(entry.is_symlink() or not entry.is_dir() for entry in entries):
        raise ValueError('only an entirely directory-only JSONCPP placeholder may be quarantined')
    names = sorted(str(entry.relative_to(tree)) for entry in entries)
    if names != ['.', 'src', 'src/lib_json']:
        raise ValueError('JSONCPP directory skeleton differs from the exactly observed GN placeholder')
    digest = hashlib.sha256(('\n'.join(names) + '\n').encode()).hexdigest()
    shutil.move(str(tree), str(destination))
    return {'scope': 'preserved_empty_owned_GN_directories_NOT_generated_header_substitution',
            'original_path': str(tree), 'quarantine_path': str(destination), 'directories': names,
            'directory_tree_sha256': digest, 'regular_file_count': 0, 'symlink_count': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--scratch-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target', action='append', required=True)
    parser.add_argument('--quarantine-empty-jsoncpp-placeholder', action='store_true')
    args = parser.parse_args()
    root, staged, output = (value.resolve() for value in (args.source_root, args.scratch_source, args.output))
    if any(owned == root or owned.is_relative_to(root) or root.is_relative_to(owned) for owned in (staged, output)):
        raise ValueError('generated inputs require independently owned Serial scratch')
    if output.exists() or not output.is_relative_to(staged):
        raise ValueError('generated-input evidence must be fresh and inside owned Serial scratch')
    for production in (root, root / 'out'):
        if not os.statvfs(production).f_flag & os.ST_RDONLY:
            raise ValueError('production inputs/output must remain read-only')
    evidence_path = staged / 'serial-build-evidence.json'
    prepared = json.loads(evidence_path.read_text())
    if (prepared.get('gn_exit_code') != 0 or prepared.get('scratch_source') != str(staged)
            or prepared.get('device_type') != '2in1' or prepared.get('first_package_gate_passed') is not False):
        raise ValueError('matching completed full GN required')
    if len(set(args.target)) != len(args.target) or not all(allowed_input(target) for target in args.target):
        raise ValueError('only genuine selected header-generation edges are eligible')
    product_output = staged / 'out' / prepared['product']
    output.mkdir()
    placeholder = None
    if args.quarantine_empty_jsoncpp_placeholder:
        generator = 'gen/third_party/jsoncpp/jsoncpp-1.9.6/src/lib_json/json_reader.cpp'
        if generator not in args.target:
            raise ValueError('JSONCPP placeholder isolation requires its genuine generator edge')
        placeholder = quarantine_empty_jsoncpp_placeholder(staged, product_output, output / 'empty-jsoncpp-placeholder')
    command = [str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'), '-w', 'dupbuild=warn',
               '-C', str(product_output), '-j', '2', *args.target]
    log = output / 'ninja-inputs.log'
    with log.open('x') as stream:
        built = subprocess.run(command, cwd=staged, env=build_environment(root, staged),
                               stdout=stream, stderr=subprocess.STDOUT)
    result = {'scope': 'actual_GN_generated_inputs_only_NOT_component_link_or_runtime_acceptance',
              'product': prepared['product'], 'command': command, 'exit_code': built.returncode,
              'full_GN_evidence_sha256': hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
              'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
              'source_manifest_sha256': prepared['candidate_source_manifest_sha256'],
              'first_package_gate_passed': False}
    if placeholder:
        result['empty_placeholder_quarantine'] = placeholder
    (output / 'generated-input-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return built.returncode


if __name__ == '__main__':
    raise SystemExit(main())
