"""Compose immutable Number source DATA and final authority; no candidate runs."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import stat

R = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
H = R / '.tmp/parallel-capability-20261016'
SDK = H / 'root-number580-normal-sdk-successor01'
FINAL = H / 'root-number580-final-mandatory-successor02'
NAMES = ('owner499.py', 'corpus580.py', 'protocol580.py', 'register580.py',
    'project580.py', 'CONTRACT580.json', 'caller/NumberCorpus580.ets',
    'caller/LegacyNumberCorpus580.js', 'caller/LegacyNumberCorpus580.d.ts', 'produce580.py')
CANONICAL = (
    'ci/capability-audit/fixtures/batch_apps/number_runtime/number_token_query395.cpp',
    'ci/capability-audit/number_native496/__init__.py',
    'ci/capability-audit/number_native496/candidate/native_observation411.py',
    'ci/capability-audit/number_native496/candidate/number_token_query395.cpp',
    'ci/capability-audit/number_native496/consumer496.py',
    'ci/capability-audit/number_native496/evidence_join496.py',
    'ci/capability-audit/number_native496/support/guest_ui.py',
    'ci/capability-audit/number_native496/support/napi_protocol411.py',
    'ci/capability-audit/number_native496/support/number_local_collector411.py',
    'ci/capability-audit/fixtures/number_native_source_loader499/owner499_final.py',
    'ci/capability-audit/number_native497/number-observer-sourcekit497/MANIFEST.json',
    'ci/capability-audit/number_native497/number-observer-sourcekit497/observer_admission396.py',
    'ci/capability-audit/number_native497/number-observer-sourcekit497/helper-kit/manifest.json',
    'ci/capability-audit/number_native497/number-observer-sourcekit497/helper-kit/scripts/verify_alsa_config_image.py',
    'ci/capability-audit/number_native497/number-observer-sourcekit497/helper-kit/scripts/verify_runtime_elf_contract.py',
    'ci/capability-audit/number_native497/number-observer-sourcekit497/helper-kit/scripts/ext_image_entries.py',
    'ci/capability-audit/number_native497/number-observer-sourcekit497/helper-kit/ci/capability-audit/fixtures/batch_apps/number_runtime/number_token_query395.cpp',
    'ci/capability-audit/number_native497/number-observer-sourcekit497/helper-kit/ci/capability-audit/build_number_observer396.py',
    'ci/capability-audit/number_native497/number-observer-sourcekit497/helper-kit/ci/capability-audit/batch_system_build_runtime_helpers.py')


def ref(path):
    assert path.is_absolute() and path.resolve() == path
    assert not any(p.is_symlink() for p in (path, *path.parents))
    s = path.lstat()
    assert stat.S_ISREG(s.st_mode) and s.st_nlink == 1
    raw = path.read_bytes()
    return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def checked(row):
    p = Path(row['path'])
    assert ref(p) == {k: row[k] for k in ('path', 'sha256', 'bytes')}
    return p


def put(path, raw):
    assert not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(0o644)
    return ref(path)


def encode(doc):
    return (json.dumps(doc, indent=2, ensure_ascii=False) + '\n').encode()


def physical(marker):
    p = checked(marker)
    m = json.loads(p.read_bytes())
    assert type(m['members']) is list
    found = {str(p): marker}
    for row in m['members']:
        q = Path(row['path'])
        q = q if q.is_absolute() else p.parent / q
        assert q.is_relative_to(p.parent) and str(q) not in found
        actual = ref(q)
        assert actual['sha256'] == row['sha256'] and actual['bytes'] == row['bytes']
        assert stat.S_IMODE(q.stat().st_mode) == row['mode']
        found[str(q)] = actual
    assert {str(q) for q in p.parent.rglob('*') if q.is_file() or q.is_symlink()} == set(found)
    return found


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sys-directory', type=Path, required=True)
parser.add_argument('--sys-frozen-sha256', required=True)
parser.add_argument('--locations', type=Path, required=True)
parser.add_argument('--locations-sha256', required=True)
parser.add_argument('--additional-authority', type=Path, required=True)
parser.add_argument('--additional-authority-sha256', required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
SYS = args.sys_directory
assert SYS.parent == H and SYS.name.startswith('root-number580-supported-local-successor')
sys_marker = ref(SYS / 'FROZEN.json')
assert sys_marker['sha256'] == args.sys_frozen_sha256
sys_sources = physical(sys_marker)
sdk_marker = ref(SDK / 'FROZEN.json')
assert sdk_marker['sha256'] == 'b67a20e1c97259cbd4c59d5ce51c7ff49b8b620989aaa5e06ecd9dd2e12b32ea'
sdk_sources = physical(sdk_marker)
extra_ref = ref(args.additional_authority)
assert extra_ref['sha256'] == args.additional_authority_sha256
extra = json.loads(args.additional_authority.read_bytes())
assert set(extra) == {'schema', 'files'} and extra['schema'] == 'root580-fixed-additional-number-authority/v1'
assert type(extra['files']) is list and extra['files']
for row in extra['files']:
    checked(row)
output = args.output
assert output.parent == H and output.name.startswith('root-number580-source-authority-successor') and not output.exists()
output.mkdir()
sources, aliases, identity_cuts, identity_rules = {}, [], [], []
catalog = json.loads((H / 'root-next579-concrete-source-plan-candidate/BASE-NODES579.json').read_bytes())
locations_ref = ref(args.locations)
assert locations_ref['sha256'] == args.locations_sha256
locations_doc = json.loads(args.locations.read_bytes())
assert set(locations_doc) == {'schema', 'source_commit', 'locations', 'generation_output'} and locations_doc['schema'] == 'root580-committed-next-source-locations/v1'
identity_commit = locations_doc['source_commit']
assert type(identity_commit) is str and re.fullmatch('[a-f0-9]{40}', identity_commit) and identity_commit != '67765265103a932b9a562face76a882f07bed3e3'
locations = locations_doc['locations']
assert set(locations) == set(catalog['roots']) and len(set(locations.values())) == 13
for value in [*locations.values(), locations_doc['generation_output']]:
    location = Path(value)
    assert location.is_absolute() and location.is_relative_to(H) and location.resolve() == location
    assert not location.exists() and not any(p.is_symlink() for p in (location, *location.parents))
assert locations['final'] == str(H / 'root-final579-identity-generated/source-whole579-next01')
generation = Path(locations_doc['generation_output'])
assert generation.parent == H and generation.name.startswith('root-next579-generated-' + identity_commit[:7] + '-')
parents = {'kit': H / 'root-suite-after579-generated', 'normal': H / 'root-postpackage579-generated'}
for family, value in locations.items():
    location = Path(value)
    if family in parents:
        assert location.parent == parents[family] and identity_commit[:7] in location.name
    elif family == 'api':
        assert location == Path(locations['network']) / 'api-successor'
    elif family != 'final':
        assert location == generation / family
for first, left in locations.items():
    for second, right in locations.items():
        if first == second or {first, second} == {'network', 'api'}:
            continue
        assert not Path(left).is_relative_to(right) and not Path(right).is_relative_to(left)
old_kit = Path(catalog['roots']['kit'])
old_normal = Path(catalog['roots']['normal'])
old_kit_manifest = ref(old_kit / 'manifest.json')
contract_preimage = ref(SYS / 'candidate/normal/number/CONTRACT580.json')
boot_preimage = ref(R / 'ci/capability-audit/boot_package.py')


def identity_rule(name, site, before, binding):
    identity_rules.append(dict(node='normal-' + hashlib.sha256(('number/' + name).encode()).hexdigest()[:16],
        site=site, before=before, binding=binding, historical=False))


def materialize_identity(name, raw):
    text = raw.decode()
    cuts = []
    declarations = []
    if name == 'owner499.py':
        declarations = [
            ('KIT', 'Path(' + repr(str(old_kit)) + ')',
             'assignment/KIT/value/args/0', str(old_kit), {'literal': locations['kit']}),
            ('KIT_SHA', repr(old_kit_manifest['sha256']), 'assignment/KIT_SHA/value',
             old_kit_manifest['sha256'], {'node': {'id': catalog['roles']['kit_manifest'], 'field': 'sha256'}}),
            ('SOURCE_COMMIT', repr('67765265103a932b9a562face76a882f07bed3e3'),
             'assignment/SOURCE_COMMIT/value', '67765265103a932b9a562face76a882f07bed3e3', {'context': 'head'}),
            ('NUMBER580_DIRECTORY', 'Path(' + repr(str(old_normal / 'number')) + ')',
             'assignment/NUMBER580_DIRECTORY/value/args/0', str(old_normal / 'number'),
             {'literal': str(Path(locations['normal']) / 'number')}),
            ('BOOT_SHA', repr(boot_preimage['sha256']), 'assignment/BOOT_SHA/value',
             boot_preimage['sha256'], {'canonical': {'path': 'ci/capability-audit/boot_package.py', 'field': 'sha256'}})]
        for sibling in ('corpus580.py', 'protocol580.py', 'register580.py', 'project580.py', 'CONTRACT580.json'):
            identity_rule(name, 'assignment/NUMBER580_PINS/value/' + sibling, None,
                {'node': {'id': 'normal-' + hashlib.sha256(('number/' + sibling).encode()).hexdigest()[:16], 'field': 'sha256'}})
    elif name == 'protocol580.py':
        declarations = [('CONTRACT_SHA', repr(contract_preimage['sha256']), 'assignment/CONTRACT_SHA/value',
            contract_preimage['sha256'], {'node': {'id': 'normal-' + hashlib.sha256(b'number/CONTRACT580.json').hexdigest()[:16], 'field': 'sha256'}})]
    for variable, expression, site, before_value, binding in declarations:
        before = variable + ' = None'
        after = variable + ' = ' + expression
        assert text.count(before) == 1
        changed = text.replace(before, after, 1)
        assert changed.count(after) == 1 and changed.replace(after, before, 1) == text
        text = changed
        cuts.append(dict(before=before, after=after))
        identity_rule(name, site, before_value, binding)
    if cuts:
        identity_cuts.append(dict(name=name, original=ref(SYS / 'candidate/normal/number' / name),
            cuts=cuts, purpose='Real retained identity preimages for original SourceGen; no business edits or ready claim'))
    return text.encode()


for name in NAMES:
    old = (SDK if name == 'produce580.py' else SYS) / 'candidate/normal/number' / name
    actual = ref(old)
    assert (sdk_sources if name == 'produce580.py' else sys_sources)[str(old)] == actual
    copied = put(output / 'candidate/normal/number' / name, materialize_identity(name, old.read_bytes()))
    sources[name] = copied
    if copied['sha256'] == actual['sha256'] and copied['bytes'] == actual['bytes']:
        aliases.append(dict(path=actual['path'], node='normal-' + hashlib.sha256(('number/' + name).encode()).hexdigest()[:16],
            published=False, source=actual))
review = json.loads((H / 'root-next579-review-27af963-next01/ROOT-REVIEW579.json').read_bytes())
nodes = {n['id']: n for n in review['nodes']}
successors = []


def whole_successor(identity, before, after_doc):
    raw = checked(before).read_bytes()
    after = put(output / 'candidate' / nodes[identity]['family'] / nodes[identity]['path'], encode(after_doc))
    assert after['sha256'] != before['sha256']
    cuts = [dict(before=raw.decode(), after=checked(after).read_text())]
    successors.append(dict(node=identity, before=before, after=after, cuts=cuts, mode=0o644))
    return after


sdk_cuts = json.loads((SDK / 'ROOT-CUTS.json').read_bytes())
source_before = next(row['after'] for row in sdk_cuts['changes'] if row['path'] == 'SOURCE579.json')
source_doc = json.loads(checked(source_before).read_bytes())
five = source_doc['number_local']['sources']
assert len(five) == 5 and all(v is None for v in five.values())
for name in five:
    five[name] = sources[name]
source_after = whole_successor('normal-ea740d8654afe24c', source_before, source_doc)
manifest_id = 'normal-a8a807f48846b1c2'
manifest_before = nodes[manifest_id]['template']
manifest = json.loads(checked(manifest_before).read_bytes())
old_inputs = dict(manifest['external_inputs'])
assert len(old_inputs) == 20
for name in five:
    key = 'number580/' + name
    assert key not in manifest['external_inputs']
    manifest['external_inputs'][key] = {k: sources[name][k] for k in ('path', 'sha256')}
assert all(manifest['external_inputs'][k] == v for k, v in old_inputs.items())
assert len({v['path'] for v in manifest['external_inputs'].values()}) == 25
whole_successor(manifest_id, manifest_before, manifest)
final_cuts = json.loads((FINAL / 'ROOT-CUTS.json').read_bytes())
for row in final_cuts['node_successors']:
    identity = row['node']
    assert nodes[identity]['template'] == row['original_template']
    original = checked(row['before']).read_text()
    current = original
    cuts = [dict(before=c['before'], after=c['after']) for c in row['cuts']]
    for c in cuts:
        assert current.count(c['before']) == 1
        current = current.replace(c['before'], c['after'], 1)
    assert current == checked(row['after']).read_text()
    if nodes[identity]['path'] == 'candidate/final579_seal.py':
        old = "statement='only the completed fixed raw union plus all four original final resource closures can seal this archive'"
        new = "statement='the completed fixed raw union, all four original final resource closures and every applicable independent local Number obligation must seal this archive'"
        assert current.count(old) == 1
        current = current.replace(old, new, 1)
        cuts.append(dict(before=old, after=new))
    before = put(output / 'before/final' / nodes[identity]['path'], original.encode())
    after = put(output / 'candidate/final' / nodes[identity]['path'], current.encode())
    inverse = current
    for c in reversed(cuts):
        assert inverse.count(c['after']) == 1
        inverse = inverse.replace(c['after'], c['before'], 1)
    assert inverse == original
    successors.append(dict(node=identity, before=row['original_template'], retained_before=before,
        after=after, cuts=cuts, mode=0o644))
authority_id = 'final-51502c53a800925d'
authority_before = nodes[authority_id]['template']
authority = json.loads(checked(authority_before).read_bytes())
old_files = list(authority['files'])
assert len(old_files) == 1149
seen = {row['path']: row for row in old_files}
assert len(seen) == 1149
appended = []
for row in [*sources.values(), *(ref(R / name) for name in CANONICAL), *extra['files']]:
    item = {k: row[k] for k in ('path', 'sha256')}
    if item['path'] in seen:
        assert seen[item['path']] == item
        continue
    seen[item['path']] = item
    authority['files'].append(item)
    appended.append(row)
assert authority['files'][:1149] == old_files
assert str(R / 'ci/capability-audit/batch_network_openvpn_runtime_collect.py') in seen
assert str(R / 'ci/capability-audit/boot_package.py') in seen
whole_successor(authority_id, authority_before, authority)
put(output / 'ROOT-CUTS.json', encode(dict(schema='root580-Number-SDK-and-Final-source-authority/v1',
    source_only=True, node_successors=successors, number_members=[dict(path='number/' + name,
        source=sources[name], mode=0o644) for name in NAMES], source_aliases=aliases,
    complete_ten_normal_sources=sources, appended_final_authority=appended,
    identity_preimage_cuts=identity_cuts, exact_identity_rules=identity_rules,
    identity_preimages=dict(kit_manifest=old_kit_manifest, contract=contract_preimage,
        boot=boot_preimage, old_kit_root=str(old_kit), old_normal_root=str(old_normal)),
    retained_final_authority_count=1149, final_authority_count=len(authority['files']),
    retained_sdk_external_count=20, sdk_external_count=25,
    inputs=dict(sys_frozen=sys_marker, sdk_frozen=sdk_marker, final_draft=ref(FINAL / 'ROOT-CUTS.json'), additional_authority=extra_ref),
    committed_locations=locations_ref, materialization_source_commit=identity_commit,
    required_request_locations=locations,
    required_generation_output=locations_doc['generation_output'],
    source_identity_projection_pending=True, candidate_executed=False, runtime_pass=False,
    first_artifact_behavior_gate_passed=False)))
members = []
for path in sorted(p for p in output.rglob('*') if p.is_file()):
    row = ref(path)
    members.append(dict(path=str(path.relative_to(output)), sha256=row['sha256'], bytes=row['bytes'], mode=0o644))
marker = put(output / 'FROZEN.json', encode(dict(schema='root580-number-authority-composition-frozen/v1',
    members=members, source_only=True, runtime_pass=False, first_artifact_behavior_gate_passed=False)))
print(json.dumps(marker))
