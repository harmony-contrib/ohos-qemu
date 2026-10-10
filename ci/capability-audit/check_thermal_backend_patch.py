#!/usr/bin/env python3
"""Real pinned thermal configuration patch/migration checks, not guest proof."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/drivers/peripheral/thermal/qemu_backend'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(source, output):
    if output.exists() or not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise ValueError('new output and read-only actual source required')
    spec = importlib.util.spec_from_file_location('thermal_baseline', COMPONENT / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    project = source / baseline.PROJECT
    revision = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != baseline.REVISION:
        raise ValueError('source project is not the pinned release revision')
    relative = baseline.FILES[0][0]
    original = subprocess.check_output(['git', '-C', str(project), 'show', revision + ':' + relative])
    if sha(original) != baseline.FILES[0][1]:
        raise ValueError('unexpected pristine pinned GN file')
    rows = []
    with tempfile.TemporaryDirectory(prefix='thermal-exact-check-') as directory:
        root = Path(directory)

        def seed(name):
            path = root / name
            target = path / baseline.PROJECT / relative
            target.parent.mkdir(parents=True)
            target.write_bytes(original)
            return path

        def apply(path, success=True):
            result = subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(path)],
                                    capture_output=True, text=True)
            if (result.returncode == 0) != success:
                raise ValueError('unexpected exact patch result: ' + result.stdout + result.stderr)
            rows.append({'case': path.name, 'expected_success': success, 'exit_code': result.returncode,
                         'stdout': result.stdout, 'stderr': result.stderr})

        def data(path):
            return {name: (path / baseline.PROJECT / name).read_bytes()
                    if (path / baseline.PROJECT / name).exists() else None for name, _, _ in baseline.FILES}

        fresh = seed('fresh')
        apply(fresh)
        baseline.validate(fresh, require_patched=True)
        final = data(fresh)
        apply(fresh)
        assert data(fresh) == final
        old = seed('exact_previous')
        for patch in sorted(COMPONENT.glob('000[12]-*.patch')):
            subprocess.run(['git', '-C', str(old), 'apply', str(patch)], check=True)
        baseline.validate_component(old, baseline.PROJECT, revision, baseline.PREVIOUS, require_patched=True)
        apply(old)
        apply(old)
        assert data(old) == final
        for name, text in (('unknown_previous', b'\n<!-- unrelated -->\n'),
                           ('partial', None)):
            path = seed(name)
            for patch in sorted(COMPONENT.glob('000[12]-*.patch')):
                subprocess.run(['git', '-C', str(path), 'apply', str(patch)], check=True)
            if text is None:
                (path / baseline.PROJECT / relative).write_bytes(original)
            else:
                xml = path / baseline.PROJECT / baseline.FILES[1][0]
                xml.write_bytes(xml.read_bytes() + text)
            before = data(path)
            apply(path, False)
            assert data(path) == before
        outside = root / 'outside.xml'
        outside.write_bytes(final[baseline.FILES[1][0]])
        linked = seed('symlink')
        (linked / baseline.PROJECT / baseline.FILES[1][0]).symlink_to(outside)
        apply(linked, False)
        assert outside.read_bytes() == final[baseline.FILES[1][0]]
    report = {'status': 'pass', 'scope': 'pinned_configuration_apply_migration_boundaries_NOT_guest',
              'revision': revision, 'source_readonly': True, 'original_gn_sha256': sha(original),
              'inputs': {str(path.relative_to(ROOT)): sha(path.read_bytes())
                         for path in COMPONENT.iterdir() if path.is_file()},
              'final': {name: sha(value) for name, value in final.items()}, 'cases': rows,
              'first_artifact_behavior_gate_passed': False}
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'cases': len(rows)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    check(args.source_root, args.output)
