#!/usr/bin/env python3
"""Pinned GN naming/real CLI IDL emitter check; never package/guest acceptance."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/build/idl_common_type_outputs'
CLI = Path('foundation/ability/ability_runtime/cli_tool_framework/interfaces/cli_tool')
CASES = ('ICliToolData.idl', 'CommandData.idl', 'IData.idl', 'nested/ICliToolData.idl', 'RGBData.idl')
EXPECTED = ('icli_tool_data', 'command_data', 'idata', 'nested/icli_tool_data', 'rg_b_data')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fragment(source):
    """Execute the exact source language, not a Python reimplementation."""
    names = source.split('  # idl name transform\n', 1)[1].split('  # sources\n', 1)[0]
    common = source.split('  # common sources\n', 1)[1].split('\n  action("$target_name") {', 1)[0]
    if names.count('sources_all = []') != 1 or common.count('foreach(idl_full_name, idl_common_list)') != 1:
        raise ValueError('unexpected actual common-type template shape')
    return names, common


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    source, work = args.source_root.resolve(), args.output.resolve()
    if not os.statvfs(source).f_flag & os.ST_RDONLY or not os.statvfs(source / 'out').f_flag & os.ST_RDONLY:
        raise ValueError('actual source and product outputs must be read-only')
    if work.parent != Path('/tmp') or not work.name.startswith('idl-common-'):
        raise ValueError('exclusive /tmp/idl-common-* output required')
    work.mkdir()
    report = {'status': 'fail', 'scope': 'pinned_GN_fragment_and_real_CLI_IDL_emitter_only',
              'first_artifact_behavior_gate_passed': False, 'commands': [], 'failures': []}
    inputs = {str(path): digest(path) for path in COMPONENT.iterdir() if path.is_file()}

    def command(argv, label, cwd=None):
        argv = list(map(str, argv))
        result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=120)
        log = work / (label + '.log')
        log.write_text(result.stdout + result.stderr)
        report['commands'].append({'argv': argv, 'cwd': str(cwd) if cwd else None,
                                   'exit_code': result.returncode, 'log': str(log), 'sha256': digest(log)})
        if result.returncode:
            raise ValueError('actual build check failed: ' + label)
        return result.stdout

    try:
        spec = importlib.util.spec_from_file_location('idl_common_baseline', COMPONENT / 'verify_source.py')
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        if baseline.validate(source):
            raise ValueError('requires actual pristine pinned GNI')
        original = source / 'build/config/components/idl_tool/idl.gni'
        staged = work / 'patched/build/config/components/idl_tool/idl.gni'
        staged.parent.mkdir(parents=True)
        shutil.copy2(original, staged)
        inputs[str(original)] = digest(original)
        report['build_revision'] = baseline.REVISION
        for attempt in (1, 2):
            command(['bash', COMPONENT / 'apply.sh', '--source-root', work / 'patched'], 'apply-' + str(attempt))
        baseline.validate(work / 'patched', require_patched=True)
        report['patched_gni_sha256'] = digest(staged)
        gn = source / 'prebuilts/build-tools/linux-x86/bin/gn'
        inputs[str(gn)] = digest(gn)
        gn_command = ['/usr/bin/qemu-x86_64-static', '-cpu', 'max', str(gn)]
        command(gn_command + ['--version'], 'actual-gn-version')
        report['gn_cases'] = {}
        for kind, contents in (('original', original.read_text()), ('patched', staged.read_text())):
            directory = work / (kind + '-graph')
            directory.mkdir()
            (directory / '.gn').write_text('buildconfig = "//BUILDCONFIG.gn"\n')
            (directory / 'BUILDCONFIG.gn').write_text('set_default_toolchain("//:default")\n')
            (directory / 'noop.py').write_text('')
            names, common = fragment(contents)
            build = 'toolchain("default") { tool("stamp") { command = "touch {{output}}" } }\n'
            build += 'action("common") {\nidl_common_list = ' + json.dumps(CASES) + '\n'
            build += names + common + '\nnot_needed(["sources_proxy", "sources_stub"])\n'
            build += 'script = "//noop.py"\noutputs = sources_all\n}\n'
            (directory / 'BUILD.gn').write_text(build)
            command(gn_command + ['gen', 'out'], kind + '-gn-gen', directory)
            outputs = command(gn_command + ['desc', 'out', '//:common', 'outputs'], kind + '-gn-outputs', directory)
            actual = [line.strip().removeprefix('//out/gen/') for line in outputs.splitlines() if line.strip()]
            expected = sorted(name + suffix for name in EXPECTED for suffix in ('.h', '.cpp'))
            matches = sorted(actual) == expected
            if kind == 'patched' and not matches:
                raise ValueError('patched actual GN common outputs do not match expected names: ' + repr(actual))
            if kind == 'original' and (matches or 'iicli_tool_data.h' not in actual):
                raise ValueError('original actual GN did not reproduce the duplicate prefix')
            report['gn_cases'][kind] = {'declared_outputs': actual, 'expected_outputs': expected,
                                        'correct_output_contract': matches}
        # Generate byte-identical real CLI sources into exclusive private output.
        # The real emitter requires writable input files; source/out remain read-only.
        idl_sources = work / 'cli-inputs'
        idl_sources.mkdir()
        for name in ('ICliToolManager.idl', 'ICliToolManagerScheduler.idl', 'ICliToolData.idl'):
            path = source / CLI / name
            inputs[str(path)] = digest(path)
            shutil.copy2(path, idl_sources / name)
        tool = source / 'out/arm64_virt/clang_x64/ability/idl_tool/idl'
        inputs[str(tool)] = digest(tool)
        generated = work / 'actual-cli-outputs'
        generated.mkdir()
        for name in ('ICliToolManager.idl', 'ICliToolManagerScheduler.idl'):
            command([tool, '-gen-cpp', '-d', generated, '-c', idl_sources / name,
                     '-log-domainid', '0xD001365', '-log-tag', 'CliToolManager',
                     '-t', 'HITRACE_TAG_ABILITY_MANAGER'], 'real-cli-emitter-' + name)
        for name in ('icli_tool_data.h', 'icli_tool_data.cpp'):
            if not (generated / name).is_file() or not (generated / name).stat().st_size:
                raise ValueError('actual CLI emitter did not generate corrected common output')
        if (generated / 'iicli_tool_data.h').exists():
            raise ValueError('real emitter unexpectedly generates the old wrong name')
        report['real_cli_output_sha256'] = {path.name: digest(path) for path in sorted(generated.iterdir()) if path.is_file()}
        if any(digest(path) != value for path, value in inputs.items()):
            raise ValueError('read-only source/recipe changed during build check')
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(str(error))
        raise
    finally:
        report['inputs_sha256'] = inputs
        (work / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'scope')}))


if __name__ == '__main__':
    main()
