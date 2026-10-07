#!/usr/bin/env python3
"""Check real pinned patch inputs in private scratch; not compile/link/guest acceptance."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = (
    'common/foundation/communication/ipc/binder_connector_initialization',
    'common/foundation/communication/ipc/binder_object_safety',
    'common/foundation/graphic/graphic_2d/async_caller_identity',
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    source, work = args.source_root.resolve(), args.work.resolve()
    if not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise ValueError('actual source must be mounted read-only')
    if work.parent != Path('/tmp').resolve() or not work.name.startswith('exact-component-'):
        raise ValueError('exclusive /tmp/exact-component-* scratch required')
    work.mkdir()
    inputs = [ROOT / 'patches/lib/apply_exact_component.py',
              ROOT / 'patches/lib/exact_source_states.py']
    for name in COMPONENTS:
        inputs.extend(path for path in (ROOT / 'patches' / name).iterdir()
                      if path.is_file() and path.suffix in ('.patch', '.py', '.sh'))
    before = {str(path): digest(path) for path in sorted(inputs)}
    rows = []
    for index, name in enumerate(COMPONENTS):
        component = ROOT / 'patches' / name
        spec = importlib.util.spec_from_file_location('actual_baseline_' + str(index),
                                                      component / 'verify_source.py')
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        if baseline.validate(source):
            raise ValueError('requires actual pristine pinned inputs, not a previously patched fixture')
        staged = work / component.name
        original = {}
        for relative, _, _ in baseline.FILES:
            input_path = source / baseline.PROJECT / relative
            target = staged / baseline.PROJECT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_path, target)
            original[str(input_path)] = digest(input_path)
        baseline.validate(staged)
        argv = ['bash', str(component / 'apply.sh'), '--source-root', str(staged)]
        codes = []
        for attempt in (1, 2):
            with (staged / ('apply-' + str(attempt) + '.log')).open('x') as output:
                codes.append(subprocess.run(argv, stdout=output, stderr=subprocess.STDOUT).returncode)
            if codes[-1] != 0:
                raise RuntimeError('actual patch-stack application failed; preserve private scratch')
        baseline.validate(staged, require_patched=True)
        if any(digest(Path(path)) != value for path, value in original.items()):
            raise ValueError('actual read-only input changed during patch-stack verification')
        rows.append({'component': name, 'source_revision': baseline.REVISION,
                     'original_sources_sha256': original,
                     'repaired_sources_sha256': {
                         str(Path(baseline.PROJECT) / relative): digest(staged / baseline.PROJECT / relative)
                         for relative, _, _ in baseline.FILES},
                     'argv': argv, 'fresh_and_repeat_exit_codes': codes,
                     'log_sha256': {str(attempt): digest(staged / ('apply-' + str(attempt) + '.log'))
                                    for attempt in (1, 2)}})
    if any(digest(Path(path)) != value for path, value in before.items()):
        raise ValueError('component recipes changed during verification')
    evidence = {'scope': 'actual_pinned_pristine_inputs_fresh_and_idempotent_patch_stack_only',
                'source_readonly': True, 'input_sha256': before, 'results': rows,
                'passed': True, 'compile_link_or_guest_acceptance': False,
                'first_artifact_behavior_gate_passed': False}
    (work / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print('all three actual pinned component stacks applied fresh and twice; not guest acceptance')


if __name__ == '__main__':
    main()
