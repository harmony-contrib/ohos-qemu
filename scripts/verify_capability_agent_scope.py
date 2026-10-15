#!/usr/bin/env python3
"""Check capability branch ownership before centralized integration.

This inspects Git commits and reports; it does not execute agent code or prove
new-package behavior. Upstream target declarations also cover generated files
which cannot be inferred from a numbered patch alone.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def relative_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError('canonical repository-relative target required: ' + str(value))
    path = PurePosixPath(value)
    if (path.is_absolute() or '..' in path.parts or path.as_posix() != value or value == '.'):
        raise ValueError('canonical repository-relative target required: ' + str(value))
    return value


def check_scope(plan: dict, agent: str, changed: list[str], report: dict,
                patch_targets: set[str], other_reports: list[dict]) -> dict:
    allocation = plan['agents'][agent]
    for name in changed:
        relative_path(name)
        if (name not in allocation.get('files', []) and
                not any(name.startswith(prefix) for prefix in allocation['prefixes'])):
            raise ValueError('agent changed a parent-owned or other-group file: ' + name)
    review = report.get('requirements_review', [])
    identifiers = list(review) if isinstance(review, dict) else [
        row if isinstance(row, str) else row['id'] for row in review]
    expected = {row['id'] for row in allocation['requirements']}
    if len(identifiers) != len(set(identifiers)) or set(identifiers) != expected:
        raise ValueError('agent report must review every assigned requirement exactly once')
    declared = report.get('upstream_targets', [])
    if not isinstance(declared, list) or len(declared) != len(set(declared)):
        raise ValueError('upstream targets must be an explicit unique list')
    targets = {relative_path(name) for name in declared}
    upstream_prefixes = [prefix.removeprefix('patches/common/')
                         for prefix in allocation['prefixes'] if prefix.startswith('patches/common/')]
    for target in targets:
        if not any(target.startswith(prefix) for prefix in upstream_prefixes):
            raise ValueError('agent changed an upstream target owned by another group or parent: ' + target)
    if not patch_targets <= targets:
        raise ValueError('patch changes undeclared upstream files: ' +
                         ', '.join(sorted(patch_targets - targets)))
    if 'remaining_gaps' not in report or 'tests' not in report or 'integration_requests' not in report:
        raise ValueError('remaining gaps, test evidence and integration requests are required')
    for other in other_reports:
        overlap = targets & {relative_path(name) for name in other['upstream_targets']}
        if overlap:
            raise ValueError('two agents modify the same upstream file: ' + ', '.join(sorted(overlap)))
    return {'status': 'pass', 'agent': agent, 'requirements_reviewed': len(expected),
            'changed_files': sorted(changed), 'upstream_targets': sorted(targets),
            'scope': 'branch_and_declared_upstream_ownership_only_NOT_runtime_acceptance',
            'first_artifact_behavior_gate_passed': False}


def git(*arguments: str) -> str:
    return subprocess.check_output(['git', '-C', str(ROOT), *arguments], text=True)


def verify(plan: dict, agent: str, base: str, head: str,
           other_reports: list[dict]) -> dict:
    base = git('rev-parse', '--verify', '--end-of-options', base + '^{commit}').strip()
    head = git('rev-parse', '--verify', '--end-of-options', head + '^{commit}').strip()
    changed = git('diff', '--name-only', '--no-renames', base, head, '--').splitlines()
    report_path = f'docs/capability-audit/parallel/{agent}/result.json'
    report = json.loads(git('show', head + ':' + report_path))
    targets = set()
    for name in changed:
        if name.endswith('.patch'):
            # Deleted patch files remain relevant to conflict detection too.
            present = subprocess.run(['git', '-C', str(ROOT), 'cat-file', '-e', head + ':' + name],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
            patch = git('show', (head if present else base) + ':' + name)
            for line in patch.splitlines():
                if line.startswith(('+++ b/', '--- a/')):
                    targets.add(relative_path(line[6:].split('\t', 1)[0]))
    return {**check_scope(plan, agent, changed, report, targets, other_reports),
            'base': base, 'head': head}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=ROOT / 'docs/capability-audit/parallel-work-plan.json')
    parser.add_argument('--agent', required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--other-report', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = verify(json.loads(args.plan.read_text()), args.agent, args.base, args.head,
                        [json.loads(path.read_text()) for path in args.other_report])
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result = {'status': 'fail', 'agent': args.agent, 'failure': str(error),
                  'first_artifact_behavior_gate_passed': False}
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(result['status'] != 'pass')


if __name__ == '__main__':
    main()
