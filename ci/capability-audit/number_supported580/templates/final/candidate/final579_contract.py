"""Fixed Network source successor. No constructors or verdict shortcuts.

COMMIT/KIT below bind Root's actual source assembly inputs. They identify
source provenance; only the new QEMU raw replay and final closure can accept an archive.
"""
from pathlib import Path
import hashlib
import importlib
import json
import re
import sys

ROOT = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
H = ROOT / '.tmp/parallel-capability-20261016'
HERE = Path(__file__).resolve().parent
KIT = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-suite-after579-generated/kit-6776526-579-01')
KIT_SHA = 'ba7c0e3b363d30ffa2baef081edc7c29bba0bf6177e5e922b7fad08c0a89ecbb'
AU = H / 'root-au579-generated/runtime'
MAIN_ENTRY = H / 'root-postpackage579-onset-source/post/run_main579.py'
MAIN_LAUNCHER = H / 'root-postpackage579-onset-source/post/run_main_attempt579.py'
CANONICAL = ROOT / 'ci/capability-audit'
COMMIT = '67765265103a932b9a562face76a882f07bed3e3'
ORIGINAL = ROOT / 'docs/capability-audit/integration-20261019/remaining-requirements.json'
PHOTOS_2IN1 = 'behavior:photo-provider-not-activated-2in1'
CXX = 'cxx-arkts11-gaps'
LABEL = 'complete-Cxx-ArkTS11-gap-closure'
DERIVED = 'actual owned suite command failed: ' + LABEL
FINAL_PREIMAGE = {'path': '/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-final579-network-successor-candidate/FROZEN.json', 'sha256': '7d0ab4ec6f037464a9e0aaa94b803cf29d8242db12cb173f1d06d673d9f2f0f4'}
API_ANCESTOR = H / 'root-api26-579-typed-registration-candidate'
API_ANCESTOR_SHA = 'c1dc3f20f3777e0e4b098ae180d2d158b97dcba23f940005e3890af9cd92e8e6'
API_EXTERNAL_SHA = '2f24c26e8dd9725eebcacabf42ff36e5141be825aca675cace7a0bf8c7f20864'
DEPENDENCIES = {
    'gap': (Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-final579-identity-generated/source-6776526-whole04/gap'), 'c69e8346bcf53b7a7517a979225ff9f3c7c52e1afb62eed760dbf2d2cf7e4638'),
    'calendar': (Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-final579-identity-generated/source-6776526-whole04/calendar'), '52406319ad4330c2cf6e55a8d050c14018d5b000192bd0277e69c4ab8658507a'),
    'paired': (Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-final579-identity-generated/source-6776526-whole04/paired'), '23b88624ff5192f2dbbe8446fe018db6e271ec3e6e454beafd733b9433032229'),
    'system': (Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-final579-identity-generated/source-6776526-whole04/system'), 'c67579bfb44ff554270c114958abf72845946229472af92e8afd48f36658f9d7'),
    'network': (Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-network579-identity-6776526-whole03'), 'd92bd3260326cddc5df6ccc07cb61fb6fd3864c95361b202add571963d711356'),
    'api': (Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-network579-identity-6776526-whole03/api-successor'), 'ca6931bd1d87fbf571f47542a51c297a5166951520bb0153b842e2b3d9f2132e'),
}

OWN_PYTHON = frozenset(('final579_contract.py', 'final579_actor.py',
    'final579_baseline.py', 'final579_families.py', 'final579_union.py',
    'final579_integration.py', 'final579_seal.py'))


def need(ok, message):
    if not ok:
        raise ValueError(message)


def unique(pairs):
    out = {}
    for key, value in pairs:
        need(key not in out, 'duplicate raw key')
        out[key] = value
    return out


def loads(text):
    return json.loads(text, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite raw data')))


def ref(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and path.is_file() and
        not any(item.is_symlink() for item in (path, *path.parents)), 'regular immutable absolute file')
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def checked(value):
    need(type(value) is dict and set(value) in ({'path', 'sha256'}, {'path', 'sha256', 'bytes'}), 'actual Ref2/3')
    path = Path(value['path'])
    need(ref(path) == {key: value[key] for key in ('path', 'sha256')} and
        ('bytes' not in value or path.stat().st_size == value['bytes']), 'changed immutable raw')
    return path


def doc(value):
    return loads(checked(value).read_text())


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return ref(Path(path))


def fixed(name, folder):
    path = folder / (name + '.py')
    old = sys.modules.get(name)
    need(old is None or Path(old.__file__).resolve() == path, 'foreign cached source: ' + name)
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    value = importlib.import_module(name)
    need(Path(value.__file__).resolve() == path, 'source origin differs: ' + name)
    return value


def frozen_dependency(name):
    folder, digest = DEPENDENCIES[name]
    need(digest is not None, 'pending fixed source digest: ' + name)
    frozen = folder / 'FROZEN.json'
    need(ref(frozen)['sha256'] == digest, 'changed fixed frozen dependency: ' + name)
    value = loads(frozen.read_text())
    members = value.get('members', value.get('files'))
    need(type(members) is list and members, 'complete fixed frozen member vector: ' + name)
    for row in members:
        p = Path(row['path'])
        need('..' not in p.parts, 'finite frozen member path')
        if not p.is_absolute():
            p = folder / p
        need(ref(p)['sha256'] == row['sha256'] and ('bytes' not in row or p.stat().st_size == row['bytes']), 'frozen member bytes changed: ' + name)
    return folder


def own_sources():
    manifest = HERE.parent / 'SOURCE-MANIFEST.json'
    value = loads(manifest.read_text())
    need(value['schema'] == 'final579-network-successor-fixed-source-vector/v1' and
        value['inherits'] == FINAL_PREIMAGE and checked(value['inherits']) == Path(FINAL_PREIMAGE['path']) and
        value['source_commit'] == COMMIT and
        ref(KIT / 'manifest.json')['sha256'] == KIT_SHA, 'fixed original kit/source')
    need(value['original_kit'] == dict(path=str(KIT / 'manifest.json'), sha256=KIT_SHA) and
        value['pending_dependencies'] == [name for name, (_folder, digest) in DEPENDENCIES.items() if digest is None],
        'finite dependency readiness agrees with fixed code')
    need({str(HERE / name) for name in OWN_PYTHON} <= {row['path'] for row in value['files']} and
        {path.name for path in HERE.glob('*.py')} == OWN_PYTHON,
        'complete fixed seven-module entry closure required')
    for row in value['files']:
        checked(row)
    return ref(manifest)


def api_source_root():
    network = frozen_dependency('network')
    folder = frozen_dependency('api')
    outer, current = doc(ref(network / 'FROZEN.json')), doc(ref(folder / 'FROZEN.json'))
    identity = {'commit': '67765265103a932b9a562face76a882f07bed3e3', 'kit': {'path': '/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-suite-after579-generated/kit-6776526-579-01/manifest.json', 'sha256': 'ba7c0e3b363d30ffa2baef081edc7c29bba0bf6177e5e922b7fad08c0a89ecbb', 'bytes': 14938}, 'source': {'path': '/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-postpackage579-generated/source-6776526-579-01/SOURCE579.json', 'sha256': '9d0440c9ec3a31f21a9ef59ed161e5a8613dac691723f5d1dc4a52a25b1c1b31', 'bytes': 6675}, 'preparation': {'path': '/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-postpackage579-onset-source/source-history579/source-preparation-build02-target579/PREPARATION_FILES579.json', 'sha256': '27c3e9bf6cbec581c75458e1efeda312a96b0e778c9e651d689c475746f958d0', 'bytes': 4919}, 'projection': {'path': '/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-network579-identity-6776526-whole03/api-successor/SOURCE-PROJECTION579.json', 'sha256': '8096af4e9a8462bdce305d47cb83e8c70f052e33664049899fb5ebc608f16bf9', 'bytes': 107714}, 'old_api': {'path': '/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-network579-connected-owner-candidate/api-successor/FROZEN.json', 'sha256': '7fa49dea13433bfe74425045ba724f46becf88ca24f77816c51818ce71b013d0'}, 'old_network': {'path': '/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-network579-connected-owner-candidate/FROZEN.json', 'sha256': '8e6e649fcc04110b780eb7d7289cea70530b316d17061b362232fc89abd6e79d'}, 'c1': {'path': '/Volumes/PSSD/code/ohos-rs/ohos-qemu/.tmp/parallel-capability-20261016/root-api26-579-typed-registration-candidate/FROZEN.json', 'sha256': 'c1dc3f20f3777e0e4b098ae180d2d158b97dcba23f940005e3890af9cd92e8e6'}}
    need(outer['schema'] == 'network579-original-owner-source-frozen/v1' and
        current['schema'] == 'api26-producer-source-successor-frozen579/v1' and
        len(outer['members']) == 92 and len(current['members']) == 48 and
        checked(outer['api_successor']) == folder / 'FROZEN.json' and
        {key: outer['inherits'][key] for key in ('path', 'sha256')} == identity['old_network'] and
        {key: current['inherits'][key] for key in ('path', 'sha256')} == identity['old_api'], 'fixed new Comm source ancestry')
    for value in (outer, current):
        need(value['source_commit'] == COMMIT == identity['commit'] and
            value['source_commit_preimage'] == '72d4d45b6d52955ab8b2c6b6cf9993c50775e019' and
            value['source_kit_manifest'] == identity['kit'] and value['normal_source'] == identity['source'] and
            value['consumed_preparation_private'] == identity['preparation'], 'actual new Comm source identity')
    vector = doc(outer['source_manifest'])
    need(vector['schema'] == 'network579-fixed-admission-source-manifest/v1' and
        len(vector['files']) == 70, 'complete actual Network source admission')
    for row in vector['files']:
        checked(row)
    projection = doc(identity['projection'])
    active = projection['active_external_sources']
    need(active['schema'] == 'api26-active-external-source-vector579/v1' and
        active['source_commit'] == COMMIT and active['source_kit_manifest'] == identity['kit'] and
        active['normal_source'] == identity['source'] and len(active['files']) == 141, 'fixed new active external scope')
    for row in active['files']:
        checked(row['file'])
    # The c1/7fa physical freezes remain immutable ancestry. Their old live R
    # external SHA rows are never reinterpreted as this new package context.
    for ancestor in (identity['old_api'], identity['old_network'], identity['c1']):
        root = checked(ancestor).parent
        value = doc(ancestor)
        for row in value['members']:
            path = Path(row['path'])
            path = path if path.is_absolute() else root / path
            need(path.is_relative_to(root) and ref(path)['sha256'] == row['sha256'] and
                path.stat().st_size == row['bytes'], 'immutable original physical source inheritance changed')
    return folder


def actor_context():
    import subprocess
    actor = fixed('actor377', KIT)
    need(actor.STATE is not None and subprocess.Popen is actor.ProxyPopen and
        Path(actor.STATE['entry']) == HERE / 'final579_actor.py', 'original authenticated actor constructor context required')
    source_ref = own_sources()
    need(actor.STATE['sources'].get(source_ref['path']) == source_ref['sha256'],
        'Root must explicitly admit the final fixed source manifest')
    vector = doc(source_ref)
    for row in vector['files']:
        if row['path'].endswith('.py'):
            need(actor.STATE['sources'].get(row['path']) == row['sha256'], 'source not admitted by original Runner')
    return actor


def audio_sources(manifest_ref, *, actor=None):
    need(checked(manifest_ref) == AU / 'FROZEN.json', 'fixed actual AU path; manifest digest is sealed Root DATA')
    value = doc(manifest_ref)
    need(value['schema'] == 'private-AU-onset579-source-manifest/v1' and value['members'], 'actual final AU manifest')
    names = set()
    for row in value['members']:
        relative = Path(row['path'])
        need(not relative.is_absolute() and '..' not in relative.parts and row['path'] not in names, 'finite AU member')
        names.add(row['path'])
        path = AU / relative
        need(ref(path)['sha256'] == row['sha256'] and path.stat().st_size == row['bytes'], 'actual AU packet bytes changed')
    need({'bindings414.py', 'coordinator414.py', 'onset579_verify.py', 'SOURCES414.json'} <= names, 'complete actual AU source closure')
    pins = loads((AU / 'SOURCES414.json').read_text())
    for path, digest in pins.items():
        need(ref(Path(path))['sha256'] == digest, 'changed actual AU source closure')
        if actor is not None and path.endswith('.py'):
            need(actor.STATE['sources'].get(path) == digest, 'AU source not admitted to original actor')
    return manifest_ref


def packet(value):
    need(type(value) is dict and set(value) == {'schema', 'source_commit', 'archive',
        'main_suite', 'main_boot', 'main_attempt', 'runtime_root', 'main_settlement', 'system_index', 'calendar',
        'api', 'paired', 'au', 'audio_source_manifest', 'earlier_attempts', 'independent_owners', 'number_local'} and
        value['schema'] == 'actual-final579-root-packet/v1' and value['source_commit'] == COMMIT,
        'finite Root-sealed final raw DATA; no code/ID/result selectors')
    for key in ('archive', 'main_suite', 'main_boot', 'main_attempt', 'audio_source_manifest'):
        checked(value[key])
    need(type(value['main_settlement']) is dict and set(value['main_settlement']) == {'held', 'constructors'}, 'main original closure refs')
    for item in value['main_settlement'].values():
        checked(item)
    need(type(value['independent_owners']) is dict and
        set(value['independent_owners']) == {'network', 'gnss'}, 'both actual independently finished owners required')
    for owner in value['independent_owners'].values():
        need(type(owner) is dict and set(owner) == {'report', 'held', 'constructors'},
            'finite actual independent owner final report and closure refs')
        for item in owner.values():
            need(type(item) is dict and set(item) == {'path', 'sha256'}, 'exact independent owner Ref2 required')
            checked(item)
    number = value['number_local']
    need(number is None or type(number) is dict and set(number) == {
        'owner_report', 'corpus', 'owner_closure', 'command_attempt', 'config', 'spec', 'observer_proof'},
        'Number DATA is either profile-inapplicable or exact seven completed actual Refs')
    if number is not None:
        for item in number.values(): checked(item)
    need(type(value['earlier_attempts']) is list, 'retain actual earlier attempts')
    for item in value['earlier_attempts']:
        checked(item)
    return value


def original_modules():
    return (fixed('verify_first_artifact_gate', ROOT / 'scripts'),
            fixed('verify_gap_closure', CANONICAL), fixed('release_scope', CANONICAL))


def main_attempt_binding(packet_value, *, admitted_sources):
    """Actual external launch receipt, independent of the suite's verdict.

    Entry path is fixed source. Its digest is actual sealed Root DATA admitted
    to the original actor, avoiding a live post-source digest cycle.
    """
    value = doc(packet_value['main_attempt'])
    need(value['schema'] == 'actual-main579-command-attempt/v1' and
        value['suite'] == packet_value['main_suite'] and value['boot'] == packet_value['main_boot'] and
        value['settlement'] == packet_value['main_settlement'], 'actual main external receipt association')
    for name in ('entry', 'config', 'runtime_inputs', 'capability_request'):
        checked(value[name])
    need(checked(value['entry']) == MAIN_ENTRY and
        admitted_sources.get(str(MAIN_ENTRY)) == value['entry']['sha256'],
        'the actual fixed Root main entry must be sealed and explicitly admitted')
    need(checked(value['launcher']) == MAIN_LAUNCHER and
        admitted_sources.get(str(MAIN_LAUNCHER)) == value['launcher']['sha256'] and
        value['failures'] == [] and value.get('unsettled_child', False) is False and
        type(value['launcher_pid']) is int and value['launcher_pid'] > 0 and
        type(value['child_pid']) is int and value['child_pid'] > 0 and value['child_pid'] != value['launcher_pid'] and
        value['first_artifact_behavior_gate_passed'] is False,
        'actual fixed external launcher failed or its child wait was not retained')
    config = doc(value['config'])
    need({key: config['archive'][key] for key in ('path', 'sha256')} ==
        {key: packet_value['archive'][key] for key in ('path', 'sha256')}, 'actual main config changed archive')
    owner_output = checked(packet_value['main_settlement']['held']).parent
    command = value['command']
    wanted = [sys.executable, '-B', str(MAIN_ENTRY), '--root-entry-sha256', value['entry']['sha256'],
        '--config', value['config']['path'], '--config-sha256', value['config']['sha256'],
        '--runtime-inputs', value['runtime_inputs']['path'], '--runtime-inputs-sha256', value['runtime_inputs']['sha256'],
        '--output', str(owner_output), '--kit-manifest-sha256', KIT_SHA,
        '--capability-request', value['capability_request']['path'],
        '--capability-request-sha256', value['capability_request']['sha256'], '--execute']
    need(command['argv'] == wanted and type(command['exit_code']) is int and
        command['timed_out'] is False and
        ref(Path(command['log']))['sha256'] == command['sha256'],
        'actual complete original main launch argv/log/normal wait receipt required')
    need('Traceback (most recent call last)' not in Path(command['log']).read_text(),
        'an additional actual main exception cannot be deferred registration')
    return value
