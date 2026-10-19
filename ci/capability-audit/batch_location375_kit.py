"""Assemble the reviewed Location tools in a fresh canonical-checkout kit.

This command performs bounded file operations only. It never launches a resource
or creates package/native/runtime evidence. The source lock records the original
immutable inputs; the resulting manifest records every actual successor byte.
"""
from pathlib import Path, PurePosixPath
import argparse
import ast
import hashlib
import json
import re
import stat

ROOT = Path(__file__).resolve().parents[2]
H = ROOT / '.tmp/parallel-capability-20261016'
OUTPUT_PARENT = H / 'round375-location'
SCHEMA = 'location375-complete-kit/v1'
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
COMPILE = 'F-location-compile-query368-draft'
INVENTORY = 'F-location-inventory-fix354-draft'
GN = 'F-location-GN-export370-draft'
SUPPORT = 'F-runtime-support35-draft'
SUPPORT_FILES = ('owned_resource35.py', 'support_common35.py')
PRIVATE_FILES = (
    'run_gnss_existing_trace_steps16.py', 'run_location_switch_bootstrap16.py',
    'location_switch_owned16.py', 'publish_root_location_selection16.py',
    'location-owned16/location_runtime_contract16.py', 'location-owned16/location_privacy_owner16.py',
    'location-owned16/gnss_public_boundary16.py', 'location-owned16/location_native_session16.py',
)


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def decode(data):
    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, 'duplicate JSON field: ' + key)
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def relative(value):
    need(type(value) is str and value and '\\' not in value and '\x00' not in value,
         'literal relative path required')
    path = PurePosixPath(value)
    need(not path.is_absolute() and '..' not in path.parts and '.' not in path.parts and
         path.as_posix() == value, 'canonical finite relative path required: ' + value)
    return value


def canonical(path, *, directory=False):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and
         all(not item.is_symlink() for item in (path, *path.parents)), 'canonical unaliased path required')
    if directory:
        need(path.is_dir(), 'actual directory required')
    else:
        info = path.lstat()
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'one regular input file required')
    return path


def read(path):
    path = canonical(path)
    before = path.stat()
    need(0 <= before.st_size <= MAX_FILE, 'source file cap exceeded')
    with path.open('rb') as stream:
        data = stream.read(MAX_FILE + 1)
    after = path.stat()
    keys = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    need(len(data) == before.st_size and all(getattr(before, k) == getattr(after, k) for k in keys),
         'source changed during bounded read')
    return data


def row(data):
    return {'sha256': sha(data), 'bytes': len(data)}


def inputs(lock_path, expected):
    need(type(expected) is str and re.fullmatch('[a-f0-9]{64}', expected), 'explicit source-lock SHA required')
    raw = read(lock_path)
    need(sha(raw) == expected, 'reviewed source lock changed')
    lock = decode(raw)
    need(lock['schema'] == 'location375-source-lock/v1' and lock['canonical_checkout'] == str(ROOT),
         'source lock belongs to another canonical checkout')
    need(type(lock['files']) is dict and 1 <= len(lock['files']) <= 256, 'finite complete source list required')
    retained = {}; total = 0
    for name, info in lock['files'].items():
        relative(name)
        data = read(H / name)
        total += len(data)
        need(total <= MAX_TOTAL and row(data) == info, 'immutable source changed or aggregate cap exceeded: ' + name)
        retained[name] = data
    need(type(lock['copy']) is dict and 1 <= len(lock['copy']) <= 256, 'finite copy recipe required')
    for destination, source in lock['copy'].items():
        relative(destination); relative(source)
        need(source in retained and destination != 'SOURCE_MANIFEST375.json', 'copy input not pinned')
    for destination, pair in lock['overlays'].items():
        relative(destination)
        need(type(pair) is dict and set(pair) == {'pre', 'post'} and
             pair['pre'] in retained and pair['post'] in retained and
             lock['copy'].get(destination) in retained and
             retained[lock['copy'][destination]] == retained[pair['pre']], 'overlay preimage mismatch')
    return lock, retained


def replace_once(source, old, new):
    need(source.count(old) == 1, 'exact successor preimage required: ' + old[:100])
    return source.replace(old, new)


def function(source, name, replacement):
    definitions = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == name]
    need(len(definitions) == 1, 'one exact original function required: ' + name)
    node = definitions[0]; lines = source.splitlines(keepends=True)
    return ''.join(lines[:node.lineno - 1]) + replacement + '\n\n' + ''.join(lines[node.end_lineno:])


def generated(lock, retained):
    """Return complete new bytes; original policy functions remain unchanged."""
    files = {name: retained[source] for name, source in lock['copy'].items()}
    for name, pair in lock['overlays'].items():
        files[name] = retained[pair['post']]
    for folder in (COMPILE, INVENTORY, GN):
        name = folder + '/SOURCE_MANIFEST.json'
        files['provenance375/' + folder + '-SOURCE_MANIFEST.json'] = files[name]
    owner_name = SUPPORT + '/owned_resource35.py'
    owner = files[owner_name].decode()
    owner = replace_once(owner,
        "HERE = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016')",
        'HERE = Path(__file__).resolve().parent.parent')
    owner = replace_once(owner,
        "QA_ROOT = Path('/Users/ranger/.codex/worktrees/capability-batched-repair-f/ohos-qemu')",
        'QA_ROOT = Path(' + repr(str(ROOT)) + ')')
    files[owner_name] = owner.encode()
    common_name = SUPPORT + '/support_common35.py'
    common = files[common_name].decode()
    common = function(common, 'clean', '''def clean(owner, root, commit):
    require(type(commit) is str and len(commit) == 40 and all(c in '0123456789abcdef' for c in commit) and
            commit != E_COMMIT, 'explicit complete new source commit required; no E default')
    require(root == QA_ROOT and
            git(owner, root, 'symbolic-ref', '--short', 'HEAD') == 'codex/ohos7-integrated-development' and
            git(owner, root, 'rev-parse', 'HEAD') == commit and not git(owner, root, 'status', '--short'),
            'actual clean canonical development branch and exact source commit required')''')
    files[common_name] = common.encode()
    pins = {name: sha(files[SUPPORT + '/' + name]) for name in SUPPORT_FILES}
    for folder, entry in ((COMPILE, 'run_location_compile129.py'), (INVENTORY, 'run_inventory354.py'), (GN, 'run_GN_export370.py')):
        name = folder + '/' + entry
        source = files[name].decode()
        for filename in SUPPORT_FILES:
            original = sha(retained[SUPPORT + '/' + filename])
            source = replace_once(source, repr(original), repr(pins[filename]))
        files[name] = source.encode()
    # Inventory is rebuilt first because GN's provenance pins include its manifest.
    for folder in (INVENTORY, COMPILE, GN):
        name = folder + '/SOURCE_MANIFEST.json'; manifest = decode(files[name])
        manifest['successor375'] = {
            'canonical_checkout': str(ROOT), 'branch': 'codex/ohos7-integrated-development',
            'predecessor_manifest': row(files['provenance375/' + folder + '-SOURCE_MANIFEST.json']),
            'source_only': True, 'actual_resources_executed_by_assembly': False,
            'original_protocol_names_retained': True,
        }
        if folder == COMPILE:
            for item in manifest['files']:
                item.update(row(files[folder + '/' + item['relative']]))
            manifest['support_pins'] = pins
        else:
            for child in manifest['files_except_manifest']:
                manifest['files_except_manifest'][child] = row(files[folder + '/' + child])
            for external in manifest['external_source_pins']:
                manifest['external_source_pins'][external] = row(files[external])
        files[name] = (json.dumps(manifest, indent=2, allow_nan=False) + '\n').encode()
    for name, data in files.items():
        if name.endswith('.py'):
            ast.parse(data, filename=name)
    return files


def assemble(lock_path, expected, output):
    lock, retained = inputs(lock_path, expected)
    output = Path(output)
    canonical(output.parent, directory=True)
    need(output.parent == OUTPUT_PARENT and output.name not in ('', '.', '..') and
         not output.exists() and not output.is_symlink(), 'fresh direct round375-location output required')
    files = generated(lock, retained)
    files['provenance375/batch_location375_kit.py'] = read(Path(__file__).resolve())
    files['provenance375/source-lock375.json'] = read(lock_path)
    # Validate all inputs before creating output; a failure after here leaves an
    # incomplete directory without a manifest, which consumers must refuse.
    output.mkdir(mode=0o700)
    for name, data in sorted(files.items()):
        target = output / relative(name); target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
    manifest = {
        'schema': SCHEMA, 'canonical_checkout': str(ROOT), 'branch': 'codex/ohos7-integrated-development',
        'source_lock': {'path': str(output / 'provenance375/source-lock375.json'), 'sha256': expected},
        'source_lock_original_path': str(canonical(lock_path)),
        'assembler': {'path': str(output / 'provenance375/batch_location375_kit.py'),
                      **row(files['provenance375/batch_location375_kit.py'])},
        'assembler_original_path': str(Path(__file__).resolve()),
        'files': {name: row(data) for name, data in sorted(files.items())},
        'entry_points': {
            'inventory': INVENTORY + '/run_inventory354.py', 'compile': COMPILE + '/run_location_compile129.py',
            'gn_raw_export': GN + '/run_GN_export370.py', 'role_image_export': 'prepare_location_roles16.py',
            'trace_runtime': 'run_gnss_existing_trace_steps16.py', 'switch_runtime': 'run_location_switch_bootstrap16.py',
        },
        'source_and_paths_repaired': True, 'compiled': False, 'relinked': False, 'new_image_built': False,
        'runtime_passed': False, 'capability_ids_closed': 0, 'first_artifact_behavior_gate_passed': False,
        'requires_actual_same_commit_package_profile_inventory': True,
        'original_actual_whole_TU_CFI_LTO_noRTTI_requirements_preserved': True,
    }
    # Check predecessor stability before publishing the complete-kit manifest.
    need(inputs(lock_path, expected) == (lock, retained), 'immutable inputs changed during kit assembly')
    path = output / 'SOURCE_MANIFEST375.json'
    with path.open('x') as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False); stream.write('\n')
    verify(path, sha(read(path)))
    return {'path': str(path), **row(read(path))}


def verify(manifest_path, expected):
    path = canonical(manifest_path); raw = read(path)
    need(type(expected) is str and sha(raw) == expected, 'actual kit manifest changed')
    manifest = decode(raw)
    need(manifest['schema'] == SCHEMA and manifest['canonical_checkout'] == str(ROOT) and
         manifest['branch'] == 'codex/ohos7-integrated-development', 'canonical kit identity required')
    need(type(manifest['files']) is dict and 1 <= len(manifest['files']) <= 256, 'finite full kit required')
    total = 0
    for name, info in manifest['files'].items():
        data = read(path.parent / relative(name)); total += len(data)
        need(total <= MAX_TOTAL and row(data) == info, 'actual successor member changed: ' + name)
    actual = set()
    for member in path.parent.rglob('*'):
        need(not member.is_symlink(), 'aliased successor member refused')
        if member.is_file():
            actual.add(member.relative_to(path.parent).as_posix())
        else:
            need(member.is_dir(), 'nonregular successor member refused')
        need(len(actual) <= 257, 'successor member count exceeded')
    need(actual == set(manifest['files']) | {path.name}, 'unlisted or missing successor members refused')
    need(all(relative(entry) in manifest['files'] for entry in manifest['entry_points'].values()), 'complete actual entries required')
    need(all(manifest[key] is False for key in ('compiled', 'relinked', 'new_image_built', 'runtime_passed', 'first_artifact_behavior_gate_passed')) and
         type(manifest['capability_ids_closed']) is int and manifest['capability_ids_closed'] == 0,
         'source assembly cannot certify runtime or capability closure')
    return manifest


def private_bindings(manifest_path, expected):
    """Actual source fields only, never a fabricated runtime execution config."""
    manifest = verify(manifest_path, expected)
    root = Path(manifest_path).parent
    files = manifest['files']
    need(set(PRIVATE_FILES) <= files.keys(), 'all eight actual private runtime files required')
    export_names = ('prepare_location_roles16.py', 'location-role-export16/location_role_export16.py')
    need(set(export_names) <= files.keys(), 'both actual private exporter files required')
    contract = 'location-owned16/location_runtime_contract16.py'
    return {
        'scope': 'actual private source bindings only; merge into genuine same-package inputs after independent validation',
        'runtime_config_private_sources': {name: files[name]['sha256'] for name in PRIVATE_FILES},
        'role_export_private_pins': {name: files[name]['sha256'] for name in export_names},
        'role_export_private_contract': {'path': str(root / contract), 'sha256': files[contract]['sha256']},
        'entries': {name: str(root / entry) for name, entry in manifest['entry_points'].items()},
        'source_commit_or_package_descriptors_synthesized': False,
        'ready': False, 'first_artifact_behavior_gate_passed': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--source-lock', type=Path); parser.add_argument('--source-lock-sha256')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', type=Path); parser.add_argument('--manifest-sha256')
    parser.add_argument('--print-private-bindings', action='store_true')
    args = parser.parse_args(argv)
    if args.verify is not None:
        need(not args.execute and args.manifest_sha256, 'verify requires exact manifest SHA and no assembly execute')
        if args.print_private_bindings:
            print(json.dumps(private_bindings(args.verify, args.manifest_sha256), indent=2)); return 0
        result = verify(args.verify, args.manifest_sha256)
        print(json.dumps({'verified_source_members': len(result['files']), 'resources_executed': False})); return 0
    if not args.execute:
        print(json.dumps({'mode': 'INERT_PLAN_ONLY', 'resources_executed': False, 'writes_performed': False,
                          'required': ['--execute', '--source-lock', '--source-lock-sha256', '--output']})); return 0
    need(args.source_lock is not None and args.source_lock_sha256 and args.output is not None, 'explicit complete source assembly inputs required')
    print(json.dumps(assemble(args.source_lock, args.source_lock_sha256, args.output))); return 0


if __name__ == '__main__':
    raise SystemExit(main())
