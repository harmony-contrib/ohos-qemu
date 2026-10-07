#!/usr/bin/env python3
"""Execute the actual HAP ABI checker's isolated copied Python closure.

Import/CLI proof only: does not package an engine or pass any guest gate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copied_modules(script):
    modules = []
    for line in script.read_text().replace('\\\n', ' ').splitlines():
        if not line.startswith('cp '):
            continue
        tokens = shlex.split(line)
        if tokens[-1] != '${FROZEN}/':
            continue
        prefix = '${NATIVE_FROZEN}/scripts/'
        for token in tokens[1:-1]:
            if not token.startswith(prefix):
                continue
            name = token.removeprefix(prefix)
            if Path(name).name != name or not name.endswith('.py') or name in modules:
                raise ValueError('ambiguous or unsafe actual HAP Python copy input')
            modules.append(name)
    if 'verify_arkweb_core_image.py' not in modules:
        raise ValueError('actual HAP checker copy command missing')
    return modules


def verify(root):
    script = root / 'scripts/package_m144_arkweb_core_in_docker.sh'
    modules = copied_modules(script)
    report = {'status': 'fail', 'scope': 'actual_isolated_HAP_checker_python_imports_NOT_HAP_or_guest',
        'package_script_sha256': digest(script), 'copied_modules': {}, 'failures': [],
        'first_artifact_behavior_gate_passed': False}
    with tempfile.TemporaryDirectory(prefix='m144-hap-python-closure-') as directory:
        work = Path(directory)
        for name in modules:
            source = root / 'scripts' / name
            if source.is_symlink() or not source.is_file():
                raise ValueError('owned regular HAP checker module required: ' + name)
            shutil.copy2(source, work / name)
            report['copied_modules'][name] = digest(source)
        argv = [sys.executable, '-E', '-S', str(work / 'verify_arkweb_core_image.py'), '--help']
        completed = subprocess.run(argv, cwd=work, text=True, capture_output=True, timeout=30)
        report.update(argv=argv, exit_code=completed.returncode,
            stdout=completed.stdout, stderr=completed.stderr)
        if completed.returncode or '--hap' not in completed.stdout or '--arch' not in completed.stdout:
            report['failures'].append('actual copied HAP checker cannot import/run in its isolated staging')
        else:
            report['status'] = 'pass'
    if digest(script) != report['package_script_sha256'] or any(digest(root / 'scripts' / name) != value
            for name, value in report['copied_modules'].items()):
        raise ValueError('HAP checker copy inputs changed during closure verification')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('fresh HAP Python closure evidence path required')
    report = verify(args.repository.resolve())
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'scope', 'failures')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
