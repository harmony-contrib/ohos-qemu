#!/usr/bin/env python3
"""Compile the exact public ResultSet facade with selected real product commands."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
from compile_contact_sync_mode import ROOT, PRODUCTS

COMPONENT = ROOT / 'patches/common/foundation/multimedia/media_library/result_set_export'
FIXTURE = ROOT / 'ci/capability-audit/fixtures/photo_result_set_public.js'
TARGET = 'multimedia/media_library/photoaccesshelper.abc'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    root, work = args.source_root.resolve(), args.work.resolve()
    if not all(os.statvfs(path).f_flag & os.ST_RDONLY for path in (root, root / 'out')):
        raise ValueError('real source and product outputs must remain read-only')
    if work.parent != Path('/tmp') or not work.name.startswith('photo-result-set-export-'):
        raise ValueError('fresh owned /tmp/photo-result-set-export-* required')
    work.mkdir(exist_ok=False)
    spec = importlib.util.spec_from_file_location('result_set_export_baseline', COMPONENT / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    baseline.validate(root)
    actual = root / baseline.PROJECT / baseline.FILES[0][0]
    if digest(FIXTURE) != baseline.FILES[0][1]:
        raise ValueError('complete exact parent facade fixture required')
    inputs = [actual, FIXTURE, Path(__file__).resolve(), COMPONENT / 'verify_source.py', COMPONENT / 'apply.sh',
              *COMPONENT.glob('*.patch'), ROOT / 'patches/lib/apply_exact_component.py',
              ROOT / 'patches/lib/exact_source_states.py']
    before = {str(path): digest(path) for path in inputs}
    products = args.product or list(PRODUCTS)
    if len(set(products)) != len(products):
        raise ValueError('duplicate products cannot count as separate architectures')
    report = dict(status='fail', scope='real_selected_product_public_facade_ABC_NOT_guest_or_gate',
                  first_artifact_behavior_gate_passed=False, commands=[], products=[])
    report.update(requested_products=products, all_three_products_checked=set(products) == set(PRODUCTS))

    def command(argv, label, cwd=None):
        argv = list(map(str, argv))
        child = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=180)
        log = work / (label + '.log'); log.write_text(child.stdout + child.stderr)
        report['commands'].append(dict(argv=argv, cwd=str(cwd) if cwd else None,
                                      exit_code=child.returncode, log_sha256=digest(log)))
        if child.returncode:
            raise ValueError('actual command failed: ' + label)
        return child.stdout

    try:
        head = command(['git', '-C', root / baseline.PROJECT, 'rev-parse', 'HEAD'], 'project-head').strip()
        if head != baseline.REVISION:
            raise ValueError('pinned MediaLibrary revision required')
        staged = work / 'source'
        candidate = staged / baseline.PROJECT / baseline.FILES[0][0]
        candidate.parent.mkdir(parents=True); candidate.write_bytes(FIXTURE.read_bytes())
        for attempt in (1, 2):
            command(['bash', COMPONENT / 'apply.sh', '--source-root', staged], 'apply-' + str(attempt))
        baseline.validate(staged, require_patched=True)
        for product in products:
            cwd = root / 'out' / product
            queried = command([root / 'prebuilts/build-tools/linux-x86/bin/ninja', '-w', 'dupbuild=warn',
                               '-C', cwd, '-t', 'commands', '-s', TARGET], product + '-query')
            argv = shlex.split(queried.splitlines()[-1])
            output_root = Path(argv[3]).parents[len(Path(TARGET).parts) - 1] if len(argv) == 8 else None
            if (len(argv) != 8 or argv[0] != '/usr/bin/env' or
                    (cwd / argv[1]).resolve() != root / 'build/scripts/ohos_abc.py' or
                    argv[2] != '--outputs' or not output_root.samefile(cwd) or
                    Path(argv[3]).relative_to(output_root) != Path(TARGET) or
                    argv[4] != '--es2abc' or argv[6] != '--sources' or
                    (cwd / argv[7]).resolve() != actual):
                raise ValueError('unexpected real product ABC command')
            compiler = Path(argv[5]) / 'es2abc'
            compiler_sha = digest(compiler)
            output = work / (product + '.abc')
            argv[3], argv[7] = str(output), str(candidate)
            command(argv, product + '-compile', cwd)
            data = output.read_bytes()
            if not data.startswith(b'PANDA\x00\x00\x00') or b'ResultSet' not in data:
                raise ValueError('compiled public facade lacks format or ResultSet export')
            if digest(compiler) != compiler_sha:
                raise ValueError('real product compiler changed')
            report['products'].append(dict(product=product, compiler_sha256=compiler_sha,
                                            abc_sha256=digest(output), abc_size=len(data)))
        if any(digest(Path(path)) != value for path, value in before.items()):
            raise ValueError('source or recipe inputs changed')
        report.update(status='pass', source_revision=head, source_inputs_unchanged=True,
                      inputs_sha256=before, repaired_facade_sha256=digest(candidate))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['failure'] = str(error)
    (work / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, action='append')
    result = run(parser.parse_args())
    print(json.dumps(dict(status=result['status'], products=len(result['products']),
                         failure=result.get('failure'), first_artifact_behavior_gate_passed=False)))
    raise SystemExit(result['status'] != 'pass')
