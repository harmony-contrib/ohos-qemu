#!/usr/bin/env python3
"""Prepare finite Root source-author JSON and byte captures, never execute it.

No business imports, AST, SourceGen, Git, SDK, Owner, transport or subprocess.
The separate original author still checks the actual future clean Git HEAD.
"""
from pathlib import Path, PurePosixPath
import argparse
import copy
import hashlib
import json
import os
import re
import stat
import sys

sys.dont_write_bytecode = True
ROOT = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
H = ROOT / '.tmp/parallel-capability-20261016'
BASE = H / 'root-next579-concrete-source-plan-candidate'
UNION = H / 'root-private579-family-union-candidate'
PREIMAGE = '67765265103a932b9a562face76a882f07bed3e3'
BASE_FROZEN_SHA = '7e2a288e01ff93cf2a8316354af8d616ae00ef7608307a49eefb7306db649b79'
UNION_FROZEN_SHA = '3c2b9ea49e58371d718c273838cfea911e87005e138fdfb703b20bc3648af90c'
FAMILIES = ('kit', 'normal', 'network', 'api', 'gnss', 'gap', 'calendar', 'paired', 'system', 'final', 'post', 'seam', 'au')
SLOTS = ('canonical_batch', 'additional_apps', 'media', 'networking', 'owning_services_ads', 'usb_midi', 'final_actions', 'post_collectors', 'provider_stage')
ACKS = ('canonical_final_with_USB_and_VPN', 'USB_MIDI_whole_and_native_fields', 'VPN_P2P_whole_provider_and_peer', 'complete_Main_Final_services_USB_hooks', 'complete_POST_collectors_real_supplemental_receipts', 'all_active_sourcevector_additions_and_literal_dispositions')
PEER_DESCRIPTOR = H / 'root-networking579-vpn-p2p-whole-candidate/candidate/network_whole579/PEER-SOURCES.json'
NEW_MEMBERS = {
    ('final', 'candidate/media579/provider579_replay.py'): ('final', 'candidate/media579/provider579_replay.py', 'media'),
    ('final', 'candidate/media579/usb579_registration.py'): ('final', 'candidate/media579/usb579_registration.py', 'usb_midi'),
    ('final', 'candidate/media579/usb579_replay.py'): ('final', 'candidate/media579/usb579_replay.py', 'usb_midi'),
    ('post', 'produce_telephony579_product.py'): ('post', 'produce_telephony579_product.py', 'networking'),
    ('post', 'produce_usb579_product.py'): ('post', 'produce_usb579_product.py', 'usb_midi'),
}
PEER_NAMES = ('backend_proof.py', 'configure-peer.patch', 'frozen-base.json', 'frozen-netlink.json', 'linux_rtnetlink.py', 'peer_linux_build.py', 'peer_lock.json', 'peer_plan.py', 'peer_server.py', 'recipe-lock.json', 'source_recipe.py')
for _name in PEER_NAMES:
    NEW_MEMBERS[('vpn-peer', 'peer_linux/' + _name)] = ('normal', 'peer_linux/' + _name, 'networking')
NUMBER_MEMBERS = ('number/owner499.py', 'number/corpus580.py', 'number/protocol580.py', 'number/register580.py', 'number/project580.py', 'number/CONTRACT580.json', 'number/caller/NumberCorpus580.ets', 'number/caller/LegacyNumberCorpus580.js', 'number/caller/LegacyNumberCorpus580.d.ts', 'number/produce580.py')
NUMBER_RUNTIME_CANONICAL = ('ci/capability-audit/fixtures/batch_apps/number_runtime/number_token_query395.cpp', 'ci/capability-audit/number_native496/__init__.py', 'ci/capability-audit/number_native496/candidate/native_observation411.py', 'ci/capability-audit/number_native496/candidate/number_token_query395.cpp', 'ci/capability-audit/number_native496/consumer496.py', 'ci/capability-audit/number_native496/evidence_join496.py', 'ci/capability-audit/number_native496/support/guest_ui.py', 'ci/capability-audit/number_native496/support/napi_protocol411.py', 'ci/capability-audit/number_native496/support/number_local_collector411.py', 'ci/capability-audit/fixtures/number_native_source_loader499/owner499_final.py', 'ci/capability-audit/number_native497/number-observer-sourcekit497/MANIFEST.json', 'ci/capability-audit/number_native497/number-observer-sourcekit497/observer_admission396.py', 'ci/capability-audit/number_native497/number-observer-sourcekit497/helper-kit/manifest.json', 'ci/capability-audit/number_native497/number-observer-sourcekit497/helper-kit/scripts/verify_alsa_config_image.py', 'ci/capability-audit/number_native497/number-observer-sourcekit497/helper-kit/scripts/verify_runtime_elf_contract.py', 'ci/capability-audit/number_native497/number-observer-sourcekit497/helper-kit/scripts/ext_image_entries.py', 'ci/capability-audit/number_native497/number-observer-sourcekit497/helper-kit/ci/capability-audit/fixtures/batch_apps/number_runtime/number_token_query395.cpp', 'ci/capability-audit/number_native497/number-observer-sourcekit497/helper-kit/ci/capability-audit/build_number_observer396.py', 'ci/capability-audit/number_native497/number-observer-sourcekit497/helper-kit/ci/capability-audit/batch_system_build_runtime_helpers.py')
REQUEST_KEYS = {'number_members', 'schema', 'source_commit', 'canonical_composition', 'source_review', 'source_capsules', 'node_successors', 'slots', 'acknowledgements', 'literal_rules', 'vector_additions', 'source_aliases', 'external_additions', 'locations', 'generation_output'}
MAX_FILE = 64 * 1024 * 1024
MAX_CAPTURE = 512 * 1024 * 1024


def need(value, message):
    if not value:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate ordinary metadata key: ' + key)
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw.decode(), object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite metadata')))


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()


def raw(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and not any(p.is_symlink() for p in (path, *path.parents)), 'unaliased actual source path')
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= MAX_FILE, 'bounded one-link source file')
    value = path.read_bytes()
    after = path.lstat()
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    need(tuple(getattr(before, k) for k in fields) == tuple(getattr(after, k) for k in fields) and len(value) == before.st_size, 'source changed during metadata read')
    return value


def ref(path):
    value = raw(path)
    return dict(path=str(path), sha256=hashlib.sha256(value).hexdigest(), bytes=len(value))


def ref3(value):
    need(type(value) is dict and {'path', 'sha256', 'bytes'} <= set(value), 'actual Ref3 or explicit Ref4 projection')
    return {key: value[key] for key in ('path', 'sha256', 'bytes')}


def checked(value):
    need(type(value) is dict and set(value) == {'path', 'sha256', 'bytes'} and type(value['bytes']) is int and value['bytes'] >= 0, 'exact Ref3')
    path = Path(value['path'])
    need(ref(path) == value, 'actual source Ref changed: ' + str(path))
    return path


def put(path, value, mode=0o444):
    path = Path(path)
    need(not path.exists() and not path.is_symlink(), 'fresh source-author destination only')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(mode)
    return ref(path)


def physical(marker):
    path = checked(marker)
    document = decode(raw(path))
    need(type(document.get('members')) is list, 'complete actual physical source capsule')
    files = {str(path): marker}
    for row in document['members']:
        name = Path(row['path'])
        name = name if name.is_absolute() else path.parent / name
        need(name.is_relative_to(path.parent) and str(name) not in files, 'unique contained capsule member')
        actual = ref(name)
        need(actual['sha256'] == row['sha256'] and actual['bytes'] == row['bytes'] and stat.S_IMODE(name.stat().st_mode) == row['mode'], 'complete physical source member/mode')
        files[str(name)] = actual
    actual_paths = {str(p) for p in path.parent.rglob('*') if p.is_file() or p.is_symlink()}
    need(actual_paths == set(files), 'capsule complete physical fullset; no unlisted source')
    return files


def merge_members(target, incoming):
    for path, value in incoming.items():
        need(path not in target or target[path] == value, 'conflicting physical source membership')
        target[path] = value


def admitted(value, members):
    path = checked(value)
    need(members.get(str(path)) == value, 'input is not physically sealed in a supplied source capsule: ' + str(path))
    return path


def literal_cut(value, before, after):
    a, b = before.encode(), after.encode()
    need(a and b and a != b and value.count(a) == 1, 'one actual literal source cut')
    result = value.replace(a, b, 1)
    need(result.count(b) == 1 and result.replace(b, a, 1) == value, 'whole literal inverse')
    return result


def semantic(before, after, cuts):
    need(type(cuts) is list and cuts, 'every changed whole source has its full finite cuts')
    value = before
    for cut in cuts:
        need(set(cut) == {'before', 'after'}, 'source cut data only')
        value = literal_cut(value, cut['before'], cut['after'])
    need(value == after, 'cuts do not reconstruct the complete actual source')
    for cut in reversed(cuts):
        value = literal_cut(value, cut['after'], cut['before'])
    need(value == before, 'complete source inverse differs')


def node_id(family, path):
    return family + '-' + hashlib.sha256(path.encode()).hexdigest()[:16]


def relative(path):
    name = PurePosixPath(path)
    need(path and not name.is_absolute() and '..' not in name.parts and str(name) == path, 'exact relative source member')


def peer_identity(selected, catalog, locations, payload):
    """Fixed peer literal identity only; no AST or business/source execution.

    A full selected source and unique complete line cut preserve every original
    statement/condition. Typed hash bindings are left for the original author.
    """
    rules, records = [], []
    peer_root = str(Path(locations['normal']) / 'peer_linux')
    old_linux = 'openvpn-owned-peer-capng-review'
    old_api = str(Path(catalog['roots']['api']).relative_to(H)) + '/peer-connected'
    new_linux = str(Path(peer_root).relative_to(H))
    new_api = str(Path(locations['api']).relative_to(H)) + '/peer-connected'
    def entry(family, path):
        identity = node_id(family, path)
        need(identity in selected and selected[identity]['base'] is not None, 'fixed existing peer source node')
        row = selected[identity]
        return identity, row, raw(checked(row['current'])).decode()
    def add_rule(identity, source, site, before, binding, evidence):
        rules.append(dict(node=identity, site=site, before=before, binding=binding, historical=False))
        records.append(dict(node=identity, source=source, site=site, before=before, binding=binding, evidence=evidence))
    for family, path in (('normal', 'peer/openvpn-owned-peer-guest15/peer_case12.py'), ('api', 'peer-connected/openvpn-owned-peer-guest15/peer_case12.py')):
        identity, row, text = entry(family, path)
        line = "PEER = Path(" + repr(str(H / old_linux)) + ")"
        need(text.splitlines().count(line) == 1, 'fixed original peer controller root assignment')
        add_rule(identity, row['current'], 'assignment/PEER/value/args/0', str(H / old_linux), {'literal': peer_root}, line)
    identity, row, text = entry('network', 'verify_peer482.py')
    line = "LINUX = H / 'openvpn-owned-peer-capng-review'"
    need(text.splitlines().count(line) == 1, 'fixed original Network Linux verifier root assignment')
    # pathlib discards H when its right operand is this fixed absolute path.
    add_rule(identity, row['current'], 'assignment/LINUX/value/right', old_linux, {'literal': peer_root}, line)
    identity, row, text = entry('api', 'peer-connected/protocol375/batch_network375_peer_protocol.py')
    prior = row['current']
    need(prior['sha256'] == '6af43e001462e0df27b804d8c1ae654ceaf5ff760c87b6959a71e3ec024b202e' and prior['bytes'] == 67504, 'fixed actual active protocol375 complete preimage; no arbitrary prefix rewriting')
    protocol_cuts = []
    for line in text.splitlines(keepends=True):
        if old_api not in line and old_linux not in line:
            continue
        replacement = line.replace(old_api, new_api).replace(old_linux, new_linux)
        need(line != replacement and line.count('\n') <= 1, 'fixed complete protocol identity line')
        protocol_cuts.append(dict(before=line, after=replacement))
    need(protocol_cuts and sum(old_api in r['before'] for r in protocol_cuts) == 7 and sum(old_linux in r['before'] for r in protocol_cuts) == 12, 'all seven API-key and twelve Linux-key source lines; no guessed protocol grammar')
    result = text.encode()
    for cut in protocol_cuts:
        result = literal_cut(result, cut['before'], cut['after'])
    semantic(text.encode(), result, protocol_cuts)
    row['current'] = put(payload / 'peer-identity' / (identity + '.py'), result)
    row['cuts'] += protocol_cuts
    records.append(dict(node=identity, before=prior, after=row['current'], cuts=protocol_cuts, reason='only old API/Linux source-key directory literals; original17 protocol behavior remains unchanged'))
    source_line = [line for line in result.decode().splitlines() if line.startswith('SOURCE_SHA = ')]
    need(len(source_line) == 1, 'one complete original SOURCE_SHA assignment')
    items = re.findall(r"'([^']+)': '([a-f0-9]{64})'", source_line[0])
    need(source_line[0] == 'SOURCE_SHA = {' + ', '.join(repr(k) + ': ' + repr(v) for k, v in items) + '}' and len(items) == len(dict(items)), 'fixed source SHA-map literal grammar; not a Python parser')
    values = dict(items)
    descriptor = decode(raw(PEER_DESCRIPTOR))
    for member in descriptor['files']:
        key = new_linux + '/' + member['relative']
        need(values.get(key) == member['before']['sha256'], 'exact original peer SHA literal at named logical source')
        add_rule(identity, row['current'], 'assignment/SOURCE_SHA/value/' + key, values[key], {'node': {'id': node_id('normal', 'peer_linux/' + member['relative']), 'field': 'sha256'}}, dict(source_key=key, original=member['before'], selected=member['after']))
    for path in ('openvpn-owned-peer-guest15/manifest.json', 'openvpn-owned-peer-guest15/common12.py', 'openvpn-owned-peer-guest15/peer_case12.py', 'run_peer_SDK15.py', 'run_peer_guest_steps15.py'):
        key = new_api + '/' + path
        target = node_id('api', 'peer-connected/' + path)
        need(target in selected and key in values, 'fixed API protocol source member')
        add_rule(identity, row['current'], 'assignment/SOURCE_SHA/value/' + key, values[key], {'node': {'id': target, 'field': 'sha256'}}, dict(source_key=key, actual_node=target))
    need("HERE = " + repr(str(H)) in result.decode().splitlines(), 'protocol actual fixed primary root retained')
    add_rule(identity, row['current'], 'assignment/HERE/value', str(H), {'literal': str(H)}, 'SOURCE_SHA keys remain exact actual H-relative paths, not logical labels')
    identity, row, text = entry('api', 'api26_connected579_sources.py')
    pins_line = [line for line in text.splitlines() if line.startswith('PINS=')]
    need(len(pins_line) == 1, 'one fixed loader PINS assignment')
    pins = re.findall(r"'([^']+)': '([a-f0-9]{64})'", pins_line[0])
    need(pins_line[0] == 'PINS={' + ', '.join(repr(k) + ': ' + repr(v) for k, v in pins) + '}' and len(pins) == 3, 'fixed complete loader PINS literal')
    for name, digest in pins:
        target = node_id('api', 'peer-connected/protocol375/' + name)
        need(target in selected, 'loader exact three protocol-source nodes')
        add_rule(identity, row['current'], 'assignment/PINS/value/' + name, digest, {'node': {'id': target, 'field': 'sha256'}}, dict(protocol_source=name, actual_node=target))
    manifest_line = [line for line in text.splitlines() if line.startswith('MANIFEST_SHA=')]
    need(len(manifest_line) == 1 and re.fullmatch("MANIFEST_SHA='[a-f0-9]{64}'", manifest_line[0]), 'fixed loader manifest SHA literal')
    add_rule(identity, row['current'], 'assignment/MANIFEST_SHA/value', manifest_line[0].split("'")[1], {'node': {'id': node_id('api', 'peer-connected/openvpn-owned-peer-guest15/manifest.json'), 'field': 'sha256'}}, manifest_line[0])
    identity, row, text = entry('api', 'SOURCE-PROJECTION579.json')
    projection = decode(text.encode())
    active = projection['active_external_sources']['files']
    need(len(active) == 141, 'complete inherited active141 preserved')
    peers = [(i, item) for i, item in enumerate(active) if item['disposition'] == 'normal-peer-manifest']
    need(len(peers) == 1, 'exact one active normal-peer manifest identity')
    i, item = peers[0]
    add_rule(identity, row['current'], '$/active_external_sources/files/' + str(i) + '/file', item['file'], {'node': {'id': catalog['roles']['peer_manifest'], 'field': 'ref'}}, dict(disposition='normal-peer-manifest', original_row=item, all_other140_rows_preserved=True))
    return rules, records


def capture_composition(*, composition, approval, source_commit, output):
    """Seal only actual approved whole canonical payloads and Root approval.

    This is byte/capture metadata production, not source apply or acceptance.
    The actual-before R reference remains historical. Only the two admitted
    payload fields are rebound to their exact same-byte immutable copies.
    """
    need(re.fullmatch('[a-f0-9]{40}', source_commit) and source_commit != PREIMAGE, 'Root actual future source commit')
    composition_path = checked(composition)
    approval_path = checked(approval)
    document = decode(raw(composition_path))
    need(document['ancestor_commit'] == PREIMAGE and type(document['changes']) is list and type(document['new_sources']) is list, 'complete actual677 canonical composition')
    snapshot = decode(raw(H / 'root-suite-after579-generated/kit-6776526-579-01/CANONICAL_SNAPSHOT578.json'))
    original = {r['path']: r for r in snapshot['files']}
    need(len(original) == 5480, 'complete original677 tracked snapshot')
    output = Path(output)
    need(output.is_absolute() and output.parent == H and output.name.startswith('root-next579-closed-canonical-' + source_commit[:7] + '-') and not output.exists() and not output.is_symlink(), 'fresh explicit canonical input packet')
    output.mkdir(mode=0o700)
    bound = copy.deepcopy(document)
    origins, targets, total = [], set(), 0
    def capture(value, *, target, role):
        nonlocal total
        value = ref3(value)
        path = checked(value)
        total += value['bytes']
        need(total <= MAX_CAPTURE, 'bounded fixed canonical payload capture')
        destination = output / 'payloads' / value['sha256']
        captured = ref(destination) if destination.exists() else put(destination, raw(path))
        need(captured['sha256'] == value['sha256'] and captured['bytes'] == value['bytes'], 'same-byte canonical input capture')
        origins.append(dict(target=target, role=role, original=value, original_mode=stat.S_IMODE(path.stat().st_mode), captured=captured))
        return captured
    for row in bound['changes']:
        target = Path(row['target'])
        need(target.is_absolute() and target.is_relative_to(ROOT) and not target.is_relative_to(H) and str(target) not in targets, 'finite unique existing R target')
        targets.add(str(target))
        name = str(target.relative_to(ROOT))
        need(name in original and row['actual_before']['path'] == str(target), 'actual-before target retained as original source evidence')
        before, after = ref3(row['retained_before']), ref3(row['after'])
        need(before['sha256'] == original[name]['sha256'] and before['bytes'] == original[name]['bytes'], 'retained whole before equals original677 snapshot')
        need(ref(target)['sha256'] == after['sha256'] and ref(target)['bytes'] == after['bytes'], 'actual new canonical target equals approved complete after')
        row['retained_before'] = capture(before, target=str(target), role='retained-before-677')
        row['after'] = capture(after, target=str(target), role='approved-whole-after')
    for row in bound['new_sources']:
        target = Path(row['target'])
        need(target.is_absolute() and target.is_relative_to(ROOT) and not target.is_relative_to(H) and str(target) not in targets and str(target.relative_to(ROOT)) not in original, 'finite unique newly tracked source')
        targets.add(str(target))
        after = ref3(row['after'])
        actual = ref(target)
        need(actual['sha256'] == after['sha256'] and actual['bytes'] == after['bytes'], 'actual new R member equals approved complete source')
        row['after'] = capture(after, target=str(target), role='approved-new-source')
    bound_ref = put(output / 'COMPOSITION579.json', encode(bound))
    approval_ref = put(output / 'ROOT-SOURCE-APPROVAL579.json', raw(approval_path))
    put(output / 'CAPTURE-PROVENANCE579.json', encode(dict(schema='root-next579-canonical-input-byte-capture/v1', actual_source_commit=source_commit, original_composition=composition, original_approval=approval, actual_before_references_unchanged=True, targets_cuts_and_original_metadata_unchanged=True, rebound_fields_only=['changes[].retained_before', 'changes[].after', 'new_sources[].after'], payloads=origins, Git_or_cleanliness_checked=False, ordinary_metadata_authoring_executed=True, source_generation_executed=False, runtime_pass=False, first_artifact_behavior_gate_passed=False)))
    rows = []
    for path in sorted(p for p in output.rglob('*') if p.is_file()):
        record = ref(path)
        rows.append(dict(path=str(path.relative_to(output)), sha256=record['sha256'], bytes=record['bytes'], mode=stat.S_IMODE(path.stat().st_mode)))
    marker = put(output / 'FROZEN.json', encode(dict(schema='root-next579-canonical-input-capture-frozen/v1', members=rows, source_only=True, runtime_pass=False)))
    return dict(canonical_composition=bound_ref, source_review=approval_ref, source_capsule=marker, actual_clean_head_check_deferred_to_original_author=True, runtime_pass=False, first_artifact_behavior_gate_passed=False)


def prepare(request_ref, output):
    request = decode(raw(checked(request_ref)))
    need(set(request) == REQUEST_KEYS and request['schema'] == 'root-next579-closed-input-preparer-request/v1', 'fixed preparer request shape')
    head = request['source_commit']
    need(type(head) is str and re.fullmatch('[0-9a-f]{40}', head) and head != PREIMAGE, 'Root must supply its actual future clean source commit; not a guessed preimage')
    output = Path(output)
    need(output.is_absolute() and output.parent == H and output.name.startswith('root-next579-closed-input-' + head[:7] + '-') and not output.exists() and not output.is_symlink(), 'fresh ordinary input author tree')
    need(set(request['locations']) == set(FAMILIES) and all(Path(p).is_absolute() and Path(p).is_relative_to(H) for p in request['locations'].values()), 'fixed thirteen actual future source roots')
    base_marker = ref(BASE / 'FROZEN.json')
    union_marker = ref(UNION / 'FROZEN.json')
    need(base_marker['sha256'] == BASE_FROZEN_SHA and union_marker['sha256'] == UNION_FROZEN_SHA, 'fixed BASE548 and semantic union source packets')
    markers = [base_marker, union_marker] + request['source_capsules']
    members = {}
    for marker in markers:
        merge_members(members, physical(marker))
    admitted(request['source_review'], members)
    composition = decode(raw(admitted(request['canonical_composition'], members)))
    need(composition['ancestor_commit'] == PREIMAGE and type(composition['changes']) is list and type(composition['new_sources']) is list, 'complete final canonical delta from actual677')
    catalog = decode(raw(BASE / 'BASE-NODES579.json'))
    template = decode(raw(BASE / 'ROOT-CLOSED-INPUT579.template.json'))
    original_external = decode(raw(BASE / 'EXTERNAL-PROVENANCE579.json'))
    correspondence = decode(raw(UNION / 'SOURCE-NODE-CORRESPONDENCE579.json'))
    aliases = decode(raw(UNION / 'SOURCE-PATH-ALIASES579.json'))['aliases']
    base_by_id = {n['id']: n for n in catalog['nodes']}
    # The complete union's nodes array is564 =548 existing +16 additions.
    # new_nodes is a duplicate explicit index of those same16, not another set.
    need(correspondence['schema'] == 'private579-complete548-source-node-correspondence/v1' and
         len(base_by_id) == 548 and len(correspondence['nodes']) == 564 and
         len(correspondence['new_nodes']) == 16 and len(original_external['rows']) == 680,
         'complete564 union, original548 and original680 external pairs')
    existing_rows = [r for r in correspondence['nodes'] if r['original_base548_node'] is not None]
    new_rows = [r for r in correspondence['nodes'] if r['original_base548_node'] is None]
    need(len(existing_rows) == 548 and len(new_rows) == 16 and
         all(r['new_node'] is False and r['node'] == r['original_base548_node'] for r in existing_rows) and
         {r['original_base548_node'] for r in existing_rows} == set(base_by_id) and
         len(correspondence['base_ids_preserved']) == 548 and
         set(correspondence['base_ids_preserved']) == set(base_by_id),
         'every original548 row/ID exactly once; additions are not overrides')
    need(new_rows == correspondence['new_nodes'] and len({r['node'] for r in new_rows}) == 16 and
         all(r['new_node'] is True and r['before_template'] is None and
             r['retained_before_template'] is None and r['cuts'] == [] for r in new_rows),
         'same exact16 new rows indexed once, no hidden predecessor or double application')
    selected, overrides, additions, renames = {}, [], [], {}
    approval = request['source_review']
    for row in existing_rows:
        identity = row['original_base548_node']
        need(identity in base_by_id and identity not in selected and row['node'] == identity, 'all original548 IDs preserved once')
        base = base_by_id[identity]
        need(row['before_template'] == base['template'], 'semantic source starts at the exact BASE template')
        current = ref3(row['current'])
        admitted(current, members)
        if current['sha256'] != base['template']['sha256'] or current['bytes'] != base['template']['bytes']:
            semantic(raw(admitted(base['template'], members)), raw(checked(current)), row['cuts'])
        else:
            need(not row['cuts'], 'unchanged source has no claimed semantic change')
        selected[identity] = dict(base=base, current=current, cuts=copy.deepcopy(row['cuts']))
    new_keys = {(r['family'], r['path']) for r in new_rows}
    need(len(new_keys) == 16 and new_keys == set(NEW_MEMBERS), 'only the fixed sixteen explicit additions; vpn-peer is not a runtime family')
    for row in new_rows:
        family, path, slot = NEW_MEMBERS[(row['family'], row['path'])]
        relative(path)
        identity = node_id(family, path)
        need(identity not in selected and family in FAMILIES, 'new member cannot collide with existing node')
        current = ref3(row['current'])
        admitted(current, members)
        selected[identity] = dict(base=None, current=current, cuts=[], family=family, path=path, slot=slot, mode=0o644)
        renames[row['node']] = identity
    # Number is an explicit fixed extension, not part of the retained16 union.
    number_rows = request['number_members']
    need(type(number_rows) is list and len(number_rows) == len(NUMBER_MEMBERS) and
         {row['path'] for row in number_rows} == set(NUMBER_MEMBERS),
         'exact ten fixed Number code/data members, no discovered source files')
    for row in number_rows:
        need(set(row) == {'path', 'source', 'mode'} and row['mode'] == 0o644,
             'fixed Number source member shape and ordinary source mode')
        relative(row['path'])
        identity = node_id('normal', row['path'])
        need(identity not in selected, 'Number source cannot replace an existing node')
        current = ref3(row['source'])
        admitted(current, members)
        need(stat.S_IMODE(Path(current['path']).stat().st_mode) == row['mode'],
             'actual physically sealed Number source mode')
        selected[identity] = dict(base=None, current=current, cuts=[],
            family='normal', path=row['path'], slot='networking', mode=row['mode'])
    # Root supplies only whole finite later semantic successors, never callback code.
    for row in request['node_successors']:
        need(set(row) == {'node', 'before', 'after', 'cuts', 'approval'}, 'fixed later semantic successor')
        identity = renames.get(row['node'], row['node'])
        need(identity in selected, 'later successor must name one of the exact564 semantic members')
        selected_row = selected[identity]
        need(selected_row['current'] == row['before'], 'later semantic cut must follow actual selected whole bytes')
        semantic(raw(admitted(row['before'], members)), raw(admitted(row['after'], members)), row['cuts'])
        admitted(row['approval'], members)
        selected_row['current'] = row['after']
        selected_row['cuts'] += row['cuts']
    # Root-approved derived DATA member, not a new runtime family or a second
    # materialization. All twelve files are produced solely by ordinary SourceGen.
    output.mkdir(mode=0o700)
    payload = output / 'inputs'
    payload.mkdir()
    peer_rules, peer_identity_records = peer_identity(selected, catalog, request['locations'], payload)
    peer_descriptor = decode(raw(PEER_DESCRIPTOR))
    need(len(peer_descriptor['files']) == 11 and {r['relative'] for r in peer_descriptor['files']} == set(PEER_NAMES), 'complete fixed peer Linux descriptor')
    canonical_descriptor_path = ROOT / 'ci/capability-audit/network_whole579/PEER-SOURCES.json'
    canonical_descriptor = ref(canonical_descriptor_path)
    need(canonical_descriptor['sha256'] == ref(PEER_DESCRIPTOR)['sha256'] and canonical_descriptor['bytes'] == ref(PEER_DESCRIPTOR)['bytes'], 'actual new canonical descriptor retains the reviewed full source declaration')
    projection_rows, projection_origin_rules = [], []
    projection_id = node_id('normal', 'peer_linux/SOURCE-PROJECTION579.json')
    for i, row in enumerate(peer_descriptor['files']):
        identity = node_id('normal', 'peer_linux/' + row['relative'])
        current = selected[identity]['current']
        need(current['sha256'] == row['after']['sha256'] and current['bytes'] == row['after']['bytes'], 'fixed peer full actual source bytes')
        projection_rows.append(dict(origin=row['before'], actual=current, relative=row['relative'], mode=row['mode']))
        projection_origin_rules.append(dict(node=projection_id, site='$/files/' + str(i) + '/origin', before=row['before'], binding=None, historical=True))
    projection = put(payload / 'peer-source-projection579.json', encode(dict(schema='network-whole579-peer-source-projection/v1', fixed_source={k: canonical_descriptor[k] for k in ('path', 'sha256')}, files=projection_rows, original_actor_count=2, original_protocol375_unchanged=True, original17_steps_unchanged=True, runtime_envelope=None, runtime_pass=False, first_artifact_behavior_gate_passed=False)))
    need(projection_id not in selected, 'derived metadata must be a unique explicit data node')
    selected[projection_id] = dict(base=None, current=projection, cuts=[], family='normal', path='peer_linux/SOURCE-PROJECTION579.json', slot='networking', mode=0o644)
    # Source aliases retain every original BASE alias. No dictionary shadowing.
    alias_rows, declared_aliases = [], dict(catalog['source_path_aliases'])
    def add_alias(path, identity, source, published=False):
        identity = renames.get(identity, identity)
        need(identity in selected and type(published) is bool, 'finite source alias node')
        if path in declared_aliases:
            need(declared_aliases[path] == dict(node=identity, published=published), 'cannot shadow any prior source alias')
            return
        need(source['path'] == path, 'alias records its real source path')
        checked(source)
        declared_aliases[path] = dict(node=identity, published=published)
        alias_rows.append(dict(path=path, node=identity, published=published, source=source))
    for path, item in aliases.items():
        if path in catalog['source_path_aliases']:
            need(item == catalog['source_path_aliases'][path], 'all original891 aliases unchanged')
            continue
        add_alias(path, item['node'], ref(Path(path)), item['published'])
    for row in peer_descriptor['files']:
        identity = node_id('normal', 'peer_linux/' + row['relative'])
        need(ref3(row['after'])['sha256'] == selected[identity]['current']['sha256'], 'normal peer members retain the descriptor actual full bytes')
        add_alias(row['after']['path'], identity, ref3(row['after']))
        for key in ('before', 'retained_before'):
            # An old hash changed by the peer proposal is historical, not a new alias.
            if row[key]['sha256'] == selected[identity]['current']['sha256']:
                add_alias(row[key]['path'], identity, ref3(row[key]))
    for row in request['source_aliases']:
        need(set(row) == {'path', 'node', 'published', 'source'}, 'explicit additional alias shape')
        add_alias(row['path'], row['node'], row['source'], row['published'])
    for identity, row in selected.items():
        if row['base'] is None or row['current']['path'] != row['base']['template']['path']:
            add_alias(row['current']['path'], identity, row['current'])
    # Retain all original34 Network guard rows. Append only the exact selected
    # peer inputs not already represented by a known original-path alias. This
    # avoids duplicate projected JSON keys and does not drop the old3 sources.
    pins_id = node_id('network', 'SOURCE-PINS.json')
    pins_row = selected[pins_id]
    pins_before = raw(checked(pins_row['current']))
    pins = decode(pins_before)
    need(type(pins) is dict and len(pins) == 34 and all(Path(k).is_absolute() and re.fullmatch('[a-f0-9]{64}', v) for k, v in pins.items()), 'complete original34 Network source-pin map')
    represented = {declared_aliases[p]['node'] for p in pins if p in declared_aliases}
    appended = []
    for path in ['peer_linux/' + name for name in PEER_NAMES] + ['peer_linux/SOURCE-PROJECTION579.json']:
        identity = node_id('normal', path)
        if identity in represented:
            continue
        source = selected[identity]['current']
        need(source['path'] not in pins, 'one exact new peer source-pin row')
        pins[source['path']] = source['sha256']
        appended.append(dict(node=identity, source=source))
    if appended:
        pins_after = encode(pins)
        cut = dict(before=pins_before.decode(), after=pins_after.decode())
        semantic(pins_before, pins_after, [cut])
        previous = pins_row['current']
        pins_row['current'] = put(payload / 'peer-identity' / (pins_id + '.json'), pins_after)
        pins_row['cuts'].append(cut)
        add_alias(pins_row['current']['path'], pins_id, pins_row['current'])
        peer_identity_records.append(dict(node=pins_id, before=previous, after=pins_row['current'], cuts=[cut], original34_retained=True, appended=appended, note='old immutable external sources remain explicit ancestry; selected normal peer source rows are independently pinned'))
    for identity, row in selected.items():
        if row['base'] is None:
            additions.append(dict(family=row['family'], path=row['path'], source=row['current'], mode=row['mode'], approval=approval, slot=row['slot']))
        elif row['current']['sha256'] != row['base']['template']['sha256'] or row['current']['bytes'] != row['base']['template']['bytes']:
            semantic(raw(admitted(row['base']['template'], members)), raw(checked(row['current'])), row['cuts'])
            overrides.append(dict(id=identity, before=row['base']['template'], after=row['current'], cuts=row['cuts'], approval=approval))
    # The full inherited733 is retained by the original author; this list adds only
    # exact Root-selected canonical paths, not discovered directory contents.
    inherited = decode(raw(H / 'root-suite-after579-generated/kit-6776526-579-01/SOURCES377.json'))
    inherited_paths = {str(Path(r['path']).relative_to(ROOT)) for r in inherited['files']}
    need(len(inherited_paths) == 733, 'actual whole inherited733 runtime vector')
    snapshot = decode(raw(H / 'root-suite-after579-generated/kit-6776526-579-01/CANONICAL_SNAPSHOT578.json'))
    universe = {r['path'] for r in snapshot['files']}
    targets = []
    for row in composition['changes'] + composition['new_sources']:
        target = Path(row['target'])
        need(target.is_absolute() and target.is_relative_to(ROOT) and not target.is_relative_to(H), 'reviewed actual canonical target')
        targets.append(str(target.relative_to(ROOT)))
    need(len(targets) == len(set(targets)), 'no duplicate canonical runtime admission target')
    universe |= set(targets)
    # Root expressly approves the conservative finite whole composition target
    # set, including assets. No source directory discovery or suffix guessing.
    need(set(NUMBER_RUNTIME_CANONICAL) <= universe,
         'all nineteen explicit Number runtime paths and immutable ancestry belong to the closed canonical snapshot')
    runtime = sorted((set(targets) | set(NUMBER_RUNTIME_CANONICAL)) - inherited_paths)
    need(set(runtime) <= universe, 'finite Root actual new canonical runtime paths')
    for name in runtime:
        relative(name)
    need(set(request['slots']) == set(SLOTS) and set(request['acknowledgements']) == set(ACKS), 'nine concrete source slot approvals and six source-completion acknowledgements')
    slots = copy.deepcopy(template['slots'])
    valid_ids = set(selected)
    for name, approval_row in request['slots'].items():
        need(set(approval_row) == {'approval', 'additional_node_ids'}, 'slot approval data shape')
        admitted(approval_row['approval'], members)
        extra_ids = [renames.get(n, n) for n in approval_row['additional_node_ids']]
        need(len(extra_ids) == len(set(extra_ids)) and set(extra_ids) <= valid_ids, 'slot finite node correspondence')
        required_additions = [node_id(r['family'], r['path']) for r in additions if name == 'canonical_batch' or r['slot'] == name]
        ids = list(dict.fromkeys(slots[name]['node_ids'] + required_additions + extra_ids))
        slots[name] = dict(closed=True, approval=approval_row['approval'], node_ids=ids)
    for name, acknowledgement in request['acknowledgements'].items():
        admitted(acknowledgement, members)
    # Original680 capture pairs remain exact. New pairs are actual same-byte
    # copies in a finite immutable child capsule, never refreshed live R hashes.
    external = copy.deepcopy(original_external['rows'])
    seen_external = {r['original']['path']: r for r in external}
    count_bytes = 0
    candidates = {}
    def consider(value):
        if type(value) is dict:
            if {'path', 'sha256', 'bytes'} <= set(value) and type(value['path']) is str and Path(value['path']).is_absolute():
                item = ref3(value)
                path = Path(item['path'])
                # These are actual host primary sources only. Live canonical R
                # is validated by the original author/new snapshot, never by
                # copying an old R digest into this external-source bridge.
                if path.is_relative_to(H) or path.is_relative_to(Path('/Volumes/PSSD/qemu/validation/first-20261005')):
                    need(item['path'] not in candidates or candidates[item['path']] == item, 'ambiguous fixed external Ref; Root must retain distinct historical sources')
                    candidates[item['path']] = item
                return
            for child in value.values():
                consider(child)
        elif type(value) is list:
            for child in value:
                consider(child)
    # Only complete fixed metadata vectors are traversed. No Python source/AST,
    # arbitrary directory or executable discovery is involved.
    for document in (request_ref, correspondence, composition, decode(raw(UNION / 'READ-REFS579.json'))):
        consider(document)
    for original in request['external_additions']:
        need(type(original) is dict and set(original) == {'path', 'sha256', 'bytes'}, 'explicit additional primary Ref3')
        consider(original)
    for original in candidates.values():
        if members.get(original['path']) == original or original['path'] in declared_aliases:
            continue
        path = checked(original)
        need(path.is_relative_to(H) or path.is_relative_to(Path('/Volumes/PSSD/qemu/validation/first-20261005')), 'external provenance can never bypass canonical R')
        mode = stat.S_IMODE(path.stat().st_mode)
        need(mode in (0o444, 0o555, 0o644, 0o755), 'actual external mode')
        if str(path) in seen_external:
            need(seen_external[str(path)]['original'] == original and seen_external[str(path)]['original_mode'] == mode, 'do not replace any original external pair')
            continue
        value = raw(path)
        count_bytes += len(value)
        need(count_bytes <= MAX_CAPTURE, 'finite fixed same-byte capture budget exceeded')
        captured_path = payload / 'captures' / original['sha256']
        captured = ref(captured_path) if captured_path.exists() else put(captured_path, value)
        need(captured['sha256'] == original['sha256'] and captured['bytes'] == original['bytes'], 'actual same-byte capture, never synthetic provenance')
        row = dict(original=original, captured=captured, original_mode=mode)
        external.append(row)
        seen_external[str(path)] = row
    for row in original_external['rows']:
        need(row['original']['sha256'] == row['captured']['sha256'] and row['original']['bytes'] == row['captured']['bytes'] and
             checked(row['original']) != checked(row['captured']) and stat.S_IMODE(Path(row['original']['path']).stat().st_mode) == row['original_mode'], 'all680 unchanged same-byte original provenance sources still real')
    peer_identity_ref = put(payload / 'PEER-IDENTITY579.json', encode(dict(schema='root-next579-fixed-peer-identity-source-sites/v1', rules=peer_rules, sources=peer_identity_records, materialize_peer_linux_executed=False, physical_producer='single ordinary SourceGen; eleven code/data members plus exact projection metadata', runtime_pass=False)))
    external_ref = put(payload / 'EXTERNAL-PROVENANCE579.json', encode(dict(schema='root-next579-closed-external-provenance/v1', rows=external, source_only=True)))
    report_ref = put(payload / 'PREPARATION-RECORD579.json', encode(dict(schema='root-next579-closed-input-byte-preparation/v1', source_commit=head, source_review=request['source_review'], canonical_composition=request['canonical_composition'], request=request_ref, base=base_marker, family_union=union_marker, original548_preserved=True, union_semantic_members=98, semantic_new_members=16 + len(NUMBER_MEMBERS), number_semantic_members=len(NUMBER_MEMBERS), derived_peer_metadata_members=1, planned_nodes=len(selected), original_external_pairs=680, additional_external_pairs=len(external)-680, remapped_new_nodes=renames, explicit_new_members=additions, runtime_additions=runtime, complete_acknowledgements=request['acknowledgements'], actual_git_cleanliness_checked=False, ordinary_metadata_authoring_executed=True, candidate_business_executed=False, source_generation_executed=False, runtime_pass=False, first_artifact_behavior_gate_passed=False)))
    rows = []
    for path in sorted(p for p in payload.rglob('*') if p.is_file()):
        record = ref(path)
        rows.append(dict(path=str(path.relative_to(payload)), sha256=record['sha256'], bytes=record['bytes'], mode=stat.S_IMODE(path.stat().st_mode)))
    payload_marker = put(payload / 'FROZEN.json', encode(dict(schema='root-next579-closed-input-captures-frozen/v1', members=rows, source_only=True, runtime_pass=False)))
    # The closed-input envelope is outside this immutable child packet. It does
    # not point to its own hash or become a source-capsule member of itself.
    literal_rules = request['literal_rules'] + projection_origin_rules + peer_rules
    rule_sites = [(r['node'], r['site']) for r in literal_rules]
    need(len(rule_sites) == len(set(rule_sites)), 'do not shadow exact peer origin-only historical rules')
    template.update(closed=True, source_commit=head, source_review=request['source_review'], source_capsules=markers[1:]+[payload_marker], canonical_composition=request['canonical_composition'], node_overrides=overrides, node_additions=additions, slots=slots, runtime_additions=runtime, literal_rules=literal_rules, source_aliases=alias_rows, vector_additions=request['vector_additions'], acknowledged_pending_slots=list(ACKS), external_provenance=external_ref, locations=request['locations'], generation_output=request['generation_output'])
    need(set(template['locations']) == set(FAMILIES), 'fixed13 generated source roots')
    closure = put(output / 'ROOT-CLOSED-INPUT579.json', encode(template))
    return dict(closed_input=closure, inputs_capsule=payload_marker, byte_preparation=report_ref, source_only=True, actual_clean_head_check_deferred_to_original_author=True, runtime_pass=False, first_artifact_behavior_gate_passed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', required=True, choices=('capture-canonical', 'prepare'))
    parser.add_argument('--request', type=Path)
    parser.add_argument('--request-sha256')
    parser.add_argument('--composition', type=Path)
    parser.add_argument('--composition-sha256')
    parser.add_argument('--approval', type=Path)
    parser.add_argument('--approval-sha256')
    parser.add_argument('--source-commit')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.mode == 'capture-canonical':
        need(args.composition is not None and args.approval is not None and args.source_commit is not None and args.request is None, 'fixed canonical/approval capture arguments')
        composition, approval = ref(args.composition), ref(args.approval)
        need(composition['sha256'] == args.composition_sha256 and approval['sha256'] == args.approval_sha256, 'actual complete Root canonical/approval source checksum')
        result = capture_composition(composition=composition, approval=approval, source_commit=args.source_commit, output=args.output)
    else:
        need(args.request is not None and args.composition is None and args.approval is None and args.source_commit is None, 'fixed closed-input metadata arguments')
        request = ref(args.request)
        need(request['sha256'] == args.request_sha256, 'Root actual finite preparation request checksum')
        result = prepare(request, args.output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
