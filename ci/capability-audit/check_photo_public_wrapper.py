#!/usr/bin/env python3
"""Validate real pinned Native/public-wrapper patches and actual product ABC.

Uses only owned scratch and read-only production inputs. Bytecode compilation
is not a public-module runtime or photo provider/package acceptance result.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/media_library/fusion_asset_type'
TARGET = 'multimedia/media_library/photoaccesshelper.abc'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    root, work = args.source_root.resolve(), args.work.resolve()
    if (not os.statvfs(root).f_flag & os.ST_RDONLY or
            not os.statvfs(root / 'out').f_flag & os.ST_RDONLY):
        raise ValueError('actual product/source inputs must remain read-only')
    if work.parent != Path('/tmp').resolve() or not work.name.startswith('photo-public-wrapper-'):
        raise ValueError('fresh owned /tmp/photo-public-wrapper-* required')
    work.mkdir(exist_ok=False)
    report = {'status': 'fail', 'scope': 'actual_pinned_photo_component_and_product_ABC_NOT_guest_or_first_gate',
              'first_artifact_behavior_gate_passed': False, 'public_module_execution_verified': False,
              'failures': [], 'commands': []}

    def command(argv, label, cwd=None):
        argv = list(map(str, argv))
        path = work / (label + '.log')
        process = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=120,
                                 env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        path.write_text(process.stdout + process.stderr)
        report['commands'].append({'argv': argv, 'cwd': str(cwd) if cwd else None,
                                  'exit_code': process.returncode, 'log_sha256': digest(path)})
        if process.returncode:
            raise ValueError('actual component/product command failed: ' + label)
        return process.stdout

    try:
        spec = importlib.util.spec_from_file_location('photo_baseline', COMPONENT / 'verify_source.py')
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        baseline.validate(root)
        actual_head = command(['git', '-C', root / baseline.PROJECT, 'rev-parse', 'HEAD'], 'pinned-head').strip()
        if actual_head != baseline.REVISION:
            raise ValueError('actual pinned MediaLibrary revision required')
        originals = {str(Path(baseline.PROJECT) / entry[0]): digest(root / baseline.PROJECT / entry[0])
                     for entry in baseline.FILES}
        inputs = [*sorted(COMPONENT.glob('*.patch')), COMPONENT / 'apply.sh', COMPONENT / 'verify_source.py',
                  ROOT / 'patches/lib/apply_component_stack.py', ROOT / 'patches/lib/exact_source_states.py']
        recipes = {str(path.relative_to(ROOT)): digest(path) for path in inputs}
        staged = work / 'source'
        for relative, before, after in baseline.FILES:
            data = subprocess.check_output(['git', '-C', str(root / baseline.PROJECT),
                                            'show', baseline.REVISION + ':' + relative])
            if hashlib.sha256(data).hexdigest() != before:
                raise ValueError('pinned original source hash differs from exact baseline: ' + relative)
            destination = staged / baseline.PROJECT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        baseline.validate(staged)
        for attempt in (1, 2):
            command(['bash', COMPONENT / 'apply.sh', '--source-root', staged], 'apply-' + str(attempt))
        baseline.validate(staged, require_patched=True)
        candidate = staged / baseline.PROJECT / 'frameworks/js/src/photoaccesshelperinf.js'
        cwd = root / 'out' / args.product
        queried = command([root / 'prebuilts/build-tools/linux-x86/bin/ninja', '-w', 'dupbuild=warn',
                           '-C', cwd, '-t', 'commands', '-s', TARGET], 'actual-product-command')
        argv = shlex.split(queried.splitlines()[-1])
        script = (cwd / argv[1]).resolve() if len(argv) > 1 else None
        expected_source = (root / baseline.PROJECT / 'frameworks/js/src/photoaccesshelperinf.js').resolve()
        if (len(argv) != 8 or argv[0] != '/usr/bin/env' or script != root / 'build/scripts/ohos_abc.py' or
                argv[2] != '--outputs' or Path(argv[3]).resolve() != cwd / TARGET or
                argv[4] != '--es2abc' or argv[6] != '--sources' or
                (cwd / argv[7]).resolve() != expected_source):
            raise ValueError('unexpected actual public-wrapper ABC command; no guessed compiler inputs')
        tool = Path(argv[5]) / 'es2abc'
        tool_sha, script_sha = digest(tool), digest(script)
        output = work / 'photoaccesshelper.abc'
        argv[3], argv[7] = str(output), str(candidate)
        command(argv, 'actual-product-ABC-compile', cwd=cwd)
        data = output.read_bytes()
        if not data.startswith(b'PANDA\x00\x00\x00') or b'FusionAssetType' not in data:
            raise ValueError('actual compiled ABC lacks its format or repaired public enum name')
        if (any(digest(root / name) != value for name, value in originals.items()) or
                any(digest(ROOT / name) != value for name, value in recipes.items()) or
                digest(tool) != tool_sha or digest(script) != script_sha):
            raise ValueError('actual source, component, product compiler or driver changed')
        report.update(status='pass', source_revision=actual_head, source_inputs_unchanged=True,
                      actual_source_sha256=originals, component_inputs_sha256=recipes,
                      repaired_source_sha256={str(Path(baseline.PROJECT) / row[0]):
                          digest(staged / baseline.PROJECT / row[0]) for row in baseline.FILES},
                      product=args.product, product_compiler_sha256=tool_sha,
                      product_driver_sha256=script_sha, abc_sha256=digest(output), abc_size=len(data))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    (work / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--product', choices=('arm64_virt', 'armv7a_virt', 'x86_64_virt'), default='arm64_virt')
    result = run(parser.parse_args())
    print(json.dumps({key: result[key] for key in ('status', 'scope', 'failures')}))
    raise SystemExit(0 if result['status'] == 'pass' else 1)
