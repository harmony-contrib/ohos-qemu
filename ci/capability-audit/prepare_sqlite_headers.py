"""Run the real product SQLite patch action into owned scratch for TU checks."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(root, cwd, compiler_argv, output):
    output.mkdir(exist_ok=False)
    source, patch_dir = root / 'third_party/sqlite', root / 'third_party/sqlite/patch'
    inputs = {str(p): digest(p) for p in source.rglob('*')
              if p.is_file() and '.git' not in p.parts}
    query = [root / 'prebuilts/build-tools/linux-x86/bin/ninja', '-w', 'dupbuild=warn',
             '-C', cwd, '-t', 'commands', '-s', 'patched_sqlite/include/sqlite3sym.h']
    child = subprocess.run(list(map(str, query)), capture_output=True, text=True, check=True)
    (output / 'query.log').write_text(child.stdout + child.stderr)
    argv = shlex.split(child.stdout.splitlines()[-1])
    if (len(argv) != 5 or argv[0] != '/usr/bin/env' or
            (cwd / argv[1]).resolve() != patch_dir / 'apply_patch.sh' or
            (cwd / argv[2]).resolve() != source or argv[3] != 'patched_sqlite' or
            (cwd / argv[4]).resolve() != patch_dir):
        raise ValueError('unexpected actual product SQLite header action')
    patched = output / 'patched_sqlite'
    argv[3] = str(patched)
    with (output / 'generate.log').open('x') as stream:
        subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=True)
    include = '-Ipatched_sqlite/include'
    if compiler_argv.count(include) != 1 or not (patched / 'include/sqlite3sym.h').is_file():
        raise ValueError('actual compiler must consume generated SQLite headers')
    revised = [('-I' + str(patched / 'include')) if item == include else item for item in compiler_argv]
    if any(digest(Path(name)) != sha for name, sha in inputs.items()):
        raise ValueError('read-only SQLite action inputs changed')
    report = dict(scope='real_selected_product_SQLite_patch_action_ONLY_NOT_guest',
                  query_argv=list(map(str, query)), executed_argv=argv, source_inputs_sha256=inputs,
                  generated_headers_sha256={p.name: digest(p) for p in (patched / 'include').glob('*.h')},
                  source_inputs_unchanged=True)
    (output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return revised, [dict(kind='actual_SQLite_header_action', evidence=str(output / 'evidence.json'),
                          sha256=digest(output / 'evidence.json'))]
