#!/usr/bin/env python3
"""Compile both actual luminance TUs for three ABIs; not guest acceptance."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from compile_contact_sync_mode import PRODUCTS, ROOT, digest

COMPONENT = ROOT / 'patches/common/foundation/arkui/ace_engine/luminance_numeric_error'


def run(args):
    root = args.source_root.resolve()
    if not all(os.statvfs(p).f_flag & os.ST_RDONLY for p in (root, root / 'out')):
        raise ValueError('source and build outputs must be read-only')
    args.output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('luminance_baseline', COMPONENT / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    if baseline.validate(root):
        raise ValueError('pristine pinned component required')
    staged = args.output / 'candidate'
    originals = {}
    for relative, original, _ in baseline.FILES:
        path = Path(baseline.PROJECT) / relative
        originals[str(path)] = digest(root / path) if original else None
        (staged / path).parent.mkdir(parents=True, exist_ok=True)
        if original:
            shutil.copy2(root / path, staged / path)
    inputs = {str(p): digest(p) for p in COMPONENT.iterdir() if p.is_file()}
    inputs[str(Path(__file__))] = digest(Path(__file__))
    report = dict(status='fail', scope='six_real_TU_compiles_NOT_link_or_guest',
                  first_artifact_behavior_gate_passed=False, commands=[], inputs=inputs,
                  originals=originals, source_revision=baseline.REVISION)
    try:
        for attempt in (1, 2):
            with (args.output / f'apply-{attempt}.log').open('x') as log:
                subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(staged)],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
        baseline.validate(staged, require_patched=True)
        overlay = args.output / 'vfs.json'
        overlay.write_text(json.dumps(dict(version=0, roots=[
            dict(type='file', name=str(root / path), **{'external-contents': str(staged / path)})
            for path in originals])) + '\n')
        report['candidate'] = {p: digest(staged / p) for p in originals}
        for product, triple in PRODUCTS.items():
            cwd = root / 'out' / product
            for name in ('js_luminance_sampler', 'sampler_instance'):
                source = Path(baseline.PROJECT) / baseline.BASE / (name + '.cpp')
                target = ('obj/foundation/arkui/ace_engine/interfaces/napi/kits/luminance_sampler/'
                          'luminancesampler_static_ohos/' + name + '.o')
                query = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
                    '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', target],
                    capture_output=True, text=True, check=True)
                prefix = args.output / (product + '-' + name)
                prefix.with_suffix('.query').write_text(query.stdout + query.stderr)
                argv = shlex.split(query.stdout.splitlines()[-1])
                if Path(argv[0]).name == 'ccache':
                    argv.pop(0)
                if (Path(argv[0]).name != 'clang++' or '--target=' + triple not in argv or
                        any(x in argv for x in ('&&', ';', '|')) or
                        any(argv.count(x) != 1 for x in ('-c', '-o', '-MF')) or
                        (cwd / argv[argv.index('-c') + 1]).resolve() != root / source):
                    raise ValueError('unexpected real compiler command')
                original_argv = argv[:]
                argv[1:1] = ['-ivfsoverlay', str(overlay)]
                obj, dep, log = (prefix.with_suffix(ext) for ext in ('.o', '.d', '.log'))
                argv[argv.index('-o') + 1] = str(obj)
                argv[argv.index('-MF') + 1] = str(dep)
                with log.open('x') as stream:
                    result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                            env=dict(os.environ, CCACHE_DISABLE='1'))
                row = dict(product=product, source=str(source), original_argv=original_argv,
                           argv=argv, exit_code=result.returncode, log_sha256=digest(log))
                report['commands'].append(row)
                if result.returncode:
                    raise ValueError('real TU failed: ' + product + '/' + name)
                for required in (source, Path(baseline.PROJECT) / baseline.BASE / 'luminance_error.h'):
                    if str(staged / required) not in dep.read_text():
                        raise ValueError('compiler did not consume candidate: ' + str(required))
                row.update(object_sha256=digest(obj), dependencies_sha256=digest(dep))
        baseline.validate(root)
        if any(digest(Path(p)) != value for p, value in inputs.items()):
            raise ValueError('recipe changed during compilation')
        report['status'] = 'pass'
    except Exception as error:
        report['error'] = str(error)
    (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return int(report['status'] != 'pass')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(run(parser.parse_args()))
