#!/usr/bin/env python3
"""Compile complete private RTT TUs; no modem, linking or package proof."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PROJECT = Path('base/telephony/call_manager')
COMPONENT = ROOT / 'patches/common' / PROJECT / 'api26_rtt_lifecycle'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    if not os.statvfs(root).f_flag & os.ST_RDONLY:
        raise ValueError('read-only fixed product source required')
    args.output.mkdir(exist_ok=False)
    evidence = json.loads((ROOT / 'docs/capability-audit/parallel/location/source-evidence.json').read_text())
    originals = evidence['original_rtt_file_sha256']
    head = subprocess.check_output(['git', '-C', str(root / PROJECT), 'rev-parse', 'HEAD'], text=True).strip()
    if head != evidence['project_heads'][str(PROJECT)]:
        raise ValueError('fixed CallManager HEAD required')
    if any(digest(root / name) != sha for name, sha in originals.items()):
        raise ValueError('complete RTT source differs from reviewed fixed inputs')
    rows = []
    with tempfile.TemporaryDirectory(prefix='rtt-full-tu-') as temporary:
        staged = Path(temporary)
        for name in originals:
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((root / name).read_bytes())
        for attempt in (1, 2):
            with (args.output / f'apply-{attempt}.log').open('xb') as log:
                subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(staged)],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
        overlay = args.output / 'headers.json'
        headers = [name for name in originals if name.endswith('.h')]
        overlay.write_text(json.dumps({'version': 0, 'roots': [
            {'type': 'file', 'name': str(root / name), 'external-contents': str(staged / name),
             'use-external-name': True} for name in headers]}) + '\n')
        cwd = root / 'out/arm64_virt'
        for unit in ('napi_call_manager', 'napi_call_ability_callback'):
            target = f'obj/{PROJECT}/frameworks/js/napi/src/call/{unit}.o'
            query = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
                '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', target],
                capture_output=True, text=True, check=True)
            (args.output / f'{unit}-query.log').write_text(query.stdout + query.stderr)
            argv = shlex.split(query.stdout.splitlines()[-1])
            if Path(argv[0]).name == 'ccache':
                argv.pop(0)
            name = str(PROJECT / f'frameworks/js/napi/src/{unit}.cpp')
            if (Path(argv[0]).name != 'clang++' or '--target=aarch64-linux-ohos' not in argv or
                    argv.count('-c') != 1 or argv.count('-o') != 1 or argv.count('-MF') != 1 or
                    (cwd / argv[argv.index('-c') + 1]).resolve() != root / name or
                    any(token in argv for token in ('&&', ';', '|'))):
                raise ValueError('exact actual ARM64 product compile command required')
            original = argv[:]
            diagnostic_define = '-DSUPPORT_RTT_CALL' not in argv
            if diagnostic_define:
                argv.insert(1, '-DSUPPORT_RTT_CALL')
            object_path, dep = args.output / f'{unit}.o', args.output / f'{unit}.d'
            argv[argv.index('-c') + 1] = str(staged / name)
            argv[argv.index('-o') + 1] = str(object_path)
            argv[argv.index('-MF') + 1] = str(dep)
            argv += ['-ivfsoverlay', str(overlay), '-iquote', str((root / name).parent)]
            with (args.output / f'{unit}-compile.log').open('xb') as log:
                result = subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
            row = {'unit': unit, 'exit_code': result.returncode, 'queried_argv': original,
                   'executed_argv': argv, 'explicit_diagnostic_RTT_define': diagnostic_define,
                   'candidate_sha256': digest(staged / name)}
            if result.returncode == 0:
                data = object_path.read_bytes()
                if data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', data, 18)[0] != 183:
                    raise ValueError('actual ARM64 object required')
                consumed = dep.read_text()
                if any(str(staged / header) not in consumed for header in headers):
                    raise ValueError('compiler did not consume both actual candidate headers')
                row['object_sha256'] = digest(object_path)
            rows.append(row)
    if any(digest(root / name) != sha for name, sha in originals.items()):
        raise ValueError('fixed source changed during isolated compilation')
    result = {'status': 'pass' if all(row['exit_code'] == 0 for row in rows) else 'fail',
              'scope': 'two_complete_ARM64_product_TUs_ONLY_NOT_IMS_or_new_package',
              'objects': rows, 'source_head': head, 'originals': originals,
              'first_artifact_behavior_gate_passed': False}
    (args.output / 'evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'units': len(rows)}))
    raise SystemExit(result['status'] != 'pass')


if __name__ == '__main__':
    main()
