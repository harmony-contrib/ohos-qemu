#!/usr/bin/env python3
"""Exercise actual pinned OHPM before/after bootstrap in a private container.

An empty dependency fixture checks the host cache, not HAP construction,
signing, ArkWeb execution or the first packaged-artifact gate.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('fresh OHPM cache evidence path required')
    source = args.source_root.resolve()
    if not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise ValueError('actual pinned source tools must be mounted read-only')
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != 'a8168622b056f25c2e68d5f12fe2759bad2d9a44':
        raise ValueError('OHPM cache reproduction requires the fixed release source')
    node = source / 'third_party/node/linux/node-linux-x64/bin/node'
    if subprocess.check_output([str(node), '--version'], text=True).strip() != 'v24.11.1':
        raise ValueError('OHPM cache reproduction requires the actual pinned Node')
    ohpm = source / 'ohos_build/ohpm/bin/ohpm'
    helper = args.repository / 'scripts/prepare_m144_host_cache.py'
    spec = importlib.util.spec_from_file_location('actual_m144_host_cache', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cache = Path.home() / '.ohpm'
    if not cache.is_symlink() or cache.exists():
        raise ValueError('expected actual prepared-image dangling OHPM alias is absent')
    alias = cache.readlink()
    inputs = {str(helper): digest(helper), str(ohpm.resolve()): digest(ohpm.resolve()),
              str(node): digest(node)}
    env = dict(os.environ, NODE_HOME=str(node.parent.parent),
               PATH=str(node.parent) + ':' + os.environ.get('PATH', ''))
    rows = []
    with tempfile.TemporaryDirectory(prefix='m144-real-ohpm-cache-') as directory:
        for label in ('before', 'after'):
            project = Path(directory) / label
            project.mkdir()
            (project / 'oh-package.json5').write_text(json.dumps({
                'name': 'm144-cache-audit', 'version': '1.0.0', 'dependencies': {}}) + '\n')
            if label == 'after':
                prepared = module.prepare_cache(Path.home())
            argv = [str(ohpm), '--strict_ssl', 'false', 'install']
            result = subprocess.run(argv, cwd=project, env=env, text=True,
                                    capture_output=True, timeout=45)
            rows.append({'label': label, 'argv': argv, 'exit_code': result.returncode,
                         'stdout': result.stdout, 'stderr': result.stderr})
    failures = []
    if rows[0]['exit_code'] == 0 or 'ENOENT' not in rows[0]['stderr'] or str(cache) not in rows[0]['stderr']:
        failures.append('actual before-bootstrap failure did not reproduce the cache alias error')
    if rows[1]['exit_code'] != 0:
        failures.append('actual OHPM install failed after host cache bootstrap')
    if cache.readlink() != alias or not cache.is_dir():
        failures.append('cache alias was replaced or target remains absent')
    if any(digest(Path(path)) != value for path, value in inputs.items()):
        failures.append('actual source/helper inputs changed during reproduction')
    report = {'status': 'fail' if failures else 'pass',
              'scope': 'actual_pinned_OHPM_empty_project_cache_bootstrap_NOT_HAP_or_guest',
              'source_revision': revision, 'inputs_sha256': inputs, 'commands': rows,
              'prepared_cache': prepared, 'failures': failures,
              'first_artifact_behavior_gate_passed': False}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'scope', 'failures')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
