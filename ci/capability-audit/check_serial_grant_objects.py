#!/usr/bin/env python3
"""Compile complete changed Serial grant sources with each actual product GN.

This reuses no host replacement interface, generated-header fabrication or
compiler suppression. The service and unit variants compile their full actual
production translation unit. Object-only evidence is not a link/test/guest
pass; missing genuine generated inputs remain explicit failures.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

TARGETS = (
    'obj/base/busmanager/serial_manager/services/native/src/serialservice/serial_right_manager.o',
    'obj/base/busmanager/serial_manager/services/native/src/SerialRightTest/serial_right_manager.o',
    'obj/base/busmanager/serial_manager/test/unittest/serial_service/SerialRightTest/serial_authorization_boundary_test.o',
)


def actual_commands(ninja, product_output):
    # Parse the large real graph once, rather than serially parsing it for each
    # object. -s emits only the requested edges; no dependency action is faked.
    query = [str(ninja), '-w', 'dupbuild=warn', '-C', str(product_output), '-t', 'commands', '-s', *TARGETS]
    queried = subprocess.run(query, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    selected = {}
    for line in queried.stdout.strip().splitlines():
        command = shlex.split(line)
        if not command or Path(command[0]).name != 'clang++' or '-c' not in command or '-o' not in command:
            raise ValueError('expected genuine product C++ object commands only')
        target = command[command.index('-o') + 1]
        if target not in TARGETS or target in selected:
            raise ValueError('unexpected or duplicate product compilation edge')
        selected[target] = (line, command)
    if set(selected) != set(TARGETS):
        raise ValueError('a real grant production/unit compilation edge is missing')
    return query, selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--scratch-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=('arm64_virt', 'armv7a_virt', 'x86_64_virt'), required=True)
    args = parser.parse_args()
    root, staged, output = (value.resolve() for value in (args.source_root, args.scratch_source, args.output))
    for owned in (staged, output):
        if owned == root or owned.is_relative_to(root) or root.is_relative_to(owned):
            raise ValueError('grant scratch must remain separate from production')
    if output == staged or output.is_relative_to(staged) or staged.is_relative_to(output) or output.exists():
        raise ValueError('grant diagnostics require fresh separate object outputs')
    for live in (root, root / 'out'):
        if not os.statvfs(live).f_flag & os.ST_RDONLY:
            raise ValueError('production source/output must remain read-only')
    evidence_path = staged / 'serial-build-evidence.json'
    prepared = json.loads(evidence_path.read_text())
    if (prepared.get('scratch_source') != str(staged) or prepared.get('gn_exit_code') != 0
            or prepared.get('product') != args.product or prepared.get('device_type') != '2in1'
            or prepared.get('first_package_gate_passed') is not False):
        raise ValueError('grant objects require the matching fresh full-GN scratch evidence')
    manifest = Path(prepared['candidate_source_manifest'])
    if (manifest != staged / 'serial-candidate-source-manifest.json'
            or hashlib.sha256(manifest.read_bytes()).hexdigest() != prepared['candidate_source_manifest_sha256']):
        raise ValueError('grant candidate source manifest differs from full GN')
    for row in json.loads(manifest.read_text()):
        source = staged / row['source']
        if hashlib.sha256(source.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('grant candidate source changed after full GN: ' + row['source'])
    product_output = staged / 'out' / args.product
    if 'device_type = "2in1"' not in (product_output / 'args.gn').read_text():
        raise ValueError('grant product must actually select 2in1')
    ninja = root / 'prebuilts/build-tools/linux-x86/bin/ninja'
    output.mkdir(parents=True)
    query, selected = actual_commands(ninja, product_output)
    rows = []
    for index, target in enumerate(TARGETS):
        original, command = selected[target]
        source = (product_output / command[command.index('-c') + 1]).resolve()
        if not source.is_relative_to(staged / 'base/busmanager/serial_manager'):
            raise ValueError('grant source escapes the genuine imported candidate')
        object_path = output / ('{}-{}'.format(index, Path(target).name))
        command[command.index('-o') + 1] = str(object_path)
        if '-MF' in command:
            command[command.index('-MF') + 1] = str(object_path) + '.d'
        log = output / ('{}-compile.log'.format(index))
        with log.open('x') as stream:
            compiled = subprocess.run(command, cwd=product_output, stdout=stream, stderr=subprocess.STDOUT)
        row = {'target': target, 'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
               'actual_GN_command': original, 'diagnostic_command': command, 'exit_code': compiled.returncode,
               'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(), 'object': str(object_path)}
        if object_path.is_file():
            row['object_sha256'] = hashlib.sha256(object_path.read_bytes()).hexdigest()
        rows.append(row)
    result = {'scope': 'real_full_translation_units_product_and_unit_variants_object_only_NOT_link_or_test_execution',
              'product': args.product, 'device_type': '2in1', 'scratch_source': str(staged),
              'full_GN_evidence_sha256': hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
              'candidate_source_manifest_sha256': prepared['candidate_source_manifest_sha256'],
              'query_command': query, 'objects': rows,
              'all_changed_objects_compiled': all(row['exit_code'] == 0 for row in rows),
              'product_component_compile_passed': False, 'unit_tests_executed': False,
              'first_package_gate_passed': False}
    (output / 'serial-grant-object-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: value for name, value in result.items() if name != 'objects'}, indent=2))
    for row in rows:
        print(row['target'], row['exit_code'])
    return 0 if result['all_changed_objects_compiled'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
