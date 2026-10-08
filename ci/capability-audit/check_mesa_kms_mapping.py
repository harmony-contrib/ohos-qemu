#!/usr/bin/env python3
"""Actual pinned recipes/historical KMS three-ABI TUs; not GN/link/package proof."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
KMS = ROOT / 'patches/common/third_party/mesa3d/kms_mapping_synchronization'
RECIPES = ROOT / 'patches/common/device/qemu/kms_mesa_build'
GN = ROOT / 'patches/common/third_party/mesa3d/kms_mapping_build'
TARGETS = (
    ('arm64', 'build-ohos-qemu-arm64-21.3.3-fixed', 'aarch64-linux-ohos', 183),
    ('armv7a', 'build-ohos-armv7a-qemu-21.3.3', 'arm-linux-ohos', 40),
    ('x86_64', 'build-ohos-qemu-x86_64-21.3.3-fixed', 'x86_64-linux-ohos', 62),
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, out = args.source_root.resolve(), args.output.resolve()
    if not all(os.statvfs(path).f_flag & os.ST_RDONLY for path in (root, root / 'out')):
        raise ValueError('actual source and product outputs must both be read-only')
    if out.parent != Path('/tmp') or not out.name.startswith('mesa-kms-'):
        raise ValueError('exclusive /tmp/mesa-kms-* output required')
    out.mkdir()
    report = {'status': 'fail', 'scope': 'actual_pinned_recipes_and_three_ABI_KMS_TUs_only',
              'first_artifact_behavior_gate_passed': False, 'commands': [], 'objects': [], 'failures': []}
    inputs = {str(path): digest(path) for component in (KMS, RECIPES, GN)
              for path in component.rglob('*') if path.is_file() and path.suffix in ('.py', '.patch', '.sh')}

    def command(argv, label, cwd=None):
        argv = list(map(str, argv))
        log = out / (label + '.log')
        with log.open('x') as stream:
            process = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
        report['commands'].append({'argv': argv, 'cwd': str(cwd) if cwd else None,
                                   'exit_code': process.returncode, 'log': str(log), 'sha256': digest(log)})
        if process.returncode:
            raise ValueError('actual KMS build check failed: ' + label)

    try:
        helper = module(KMS / 'files/apply_mesa_kms_mapping.py', 'actual_kms_source')
        recipes = module(RECIPES / 'apply_recipe.py', 'actual_kms_recipes')
        staged = out / 'recipe-source'
        for relative, _, _, _, _ in recipes.FILES:
            path = root / recipes.PROJECT / relative
            inputs[str(path)] = digest(path)
            target = staged / recipes.PROJECT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        gn_source = root / 'third_party/mesa3d/ohos/BUILD.gn'
        inputs[str(gn_source)] = digest(gn_source)
        target = staged / 'third_party/mesa3d/ohos/BUILD.gn'
        target.parent.mkdir(parents=True)
        shutil.copy2(gn_source, target)
        report['project_revisions'] = {}
        for project, expected in ((recipes.PROJECT, recipes.REVISION),
                                   ('third_party/mesa3d', '952a438c56ce20610d88f0c4d8c673485aefeff7')):
            actual = subprocess.check_output(['git', '-C', str(root / project), 'rev-parse', 'HEAD'], text=True).strip()
            if actual != expected:
                raise ValueError('unexpected actual project revision')
            report['project_revisions'][str(project)] = actual
        for attempt in (1, 2):
            for component in (RECIPES, GN):
                command(['bash', component / 'apply.sh', '--source-root', staged], component.name + '-' + str(attempt))
        report['patched_recipe_sha256'] = {str(path.relative_to(staged)): digest(path)
                                          for path in staged.rglob('*') if path.is_file() and path.suffix in ('.py', '.gn')}
        from test_mesa_kms_mapping import functions
        for arch, directory, triple, machine in TARGETS:
            build = root / 'third_party/mesa3d' / directory
            database = build / 'compile_commands.json'
            inputs[str(database)] = digest(database)
            rows = [row for row in json.loads(database.read_text()) if row['file'].endswith(str(helper.RELATIVE))]
            if len(rows) != 1 or Path(rows[0]['directory']).resolve() != build:
                raise ValueError('unexpected actual KMS command database')
            original = shlex.split(rows[0]['command'])
            if Path(original[0]).name == 'ccache':
                original.pop(0)
            if (Path(original[0]).name != 'clang' or '--target=' + triple not in original or
                    any(original.count(flag) != 1 for flag in ('-c', '-o', '-MF', '-MQ'))):
                raise ValueError('unexpected actual KMS compiler arguments')
            actual_source = (build / original[original.index('-c') + 1]).resolve()
            source_root = actual_source.parents[5]
            if actual_source != source_root / helper.RELATIVE:
                raise ValueError('unexpected historical KMS source path')
            inputs[str(actual_source)] = digest(actual_source)
            inputs[str(source_root / 'VERSION')] = digest(source_root / 'VERSION')
            private = out / (arch + '-source')
            source = private / helper.RELATIVE
            source.parent.mkdir(parents=True)
            shutil.copy2(actual_source, source)
            shutil.copy2(source_root / 'VERSION', private / 'VERSION')
            contents = actual_source.read_text()
            for name in ('kms_sw_displaytarget_map', 'kms_sw_displaytarget_unmap'):
                if next(part for part in functions(False).split('\nstatic ') if name + '(' in part).strip() not in contents:
                    raise ValueError('host fixture differs from the actual original native function')
            for attempt in (1, 2):
                helper.apply(private, KMS / '0001-serialize-displaytarget-mapping.patch')
            obj = out / (arch + '-kms.o')
            dep = out / (arch + '-kms.d')
            argv = original[:]
            argv[1:1] = ['-iquote', str(actual_source.parent)]
            for flag, value in (('-c', source), ('-o', obj), ('-MF', dep), ('-MQ', obj)):
                argv[argv.index(flag) + 1] = str(value)
            command(argv, arch + '-actual-tu', build)
            data = obj.read_bytes()
            if data[:4] != b'\x7fELF' or int.from_bytes(data[18:20], 'little') != machine:
                raise ValueError('KMS compiler output ABI mismatch')
            report['objects'].append({'arch': arch, 'original_argv': original,
                                      'patched_source_sha256': digest(source), 'object_sha256': digest(obj),
                                      'dependency_sha256': digest(dep), 'elf_machine': machine})
        if any(digest(path) != expected for path, expected in inputs.items()):
            raise ValueError('read-only source or recipes changed during KMS check')
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(str(error))
        raise
    finally:
        report['inputs_sha256'] = inputs
        (out / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'scope')}))


if __name__ == '__main__':
    main()
