#!/usr/bin/env python3
"""Prepare same-guest Knowledge requests; independently check original JSONL.

No VM, HDC, UI, build, sign, install, grant or SQL driver. Root must collect the
real transport/build/signature/token evidence. Raw semantic checks alone always
report guest_identity_verified=False and never close a package gate.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from PIL import Image

from batch_media_knowledge_project import (FIX, ROLES, READ, WRITE, calendar_events, expected_entities,
                                          checked, record, require, sha, write)

# No inferred user/account switching; every role is a distinct actual UID in 100.
STEPS = [
    ('normal-denied', 'denied', 'access'), ('system-denied', 'query', 'access'),
    ('read-permission', 'query', 'permission'), ('write-permission', 'curator', 'permission'),
    ('baseline', 'query', 'baseline'), ('import', 'importer', 'import'),
    ('present', 'query', 'query'), ('prepare', 'curator', 'prepare'),
    ('hide', 'curator', 'hide'), ('hidden', 'query', 'query'),
    ('unhide', 'curator', 'unhide'), ('unhidden', 'query', 'query'),
    ('trash', 'curator', 'trash'), ('trashed', 'query', 'query'),
    ('recover', 'curator', 'recover'), ('recovered', 'query', 'query'),
    ('trash-again', 'curator', 'trash'), ('delete', 'curator', 'delete'),
    ('deleted', 'query', 'query'), ('cleanup-assets', 'curator', 'cleanup'),
    ('cleanup', 'query', 'query'), ('cleanup-private', 'importer', 'remove-private'),
]
ROW_KEYS = {'schema_version', 'run_id', 'boot_id', 'operation_id', 'role', 'phase', 'sequence',
            'timestamp_ms', 'uid', 'token_id', 'event', 'api', 'value_json', 'error_code', 'error_message'}
EVENT_APIS = {'begin': 'request', 'complete': 'request', 'access': 'abilityAccessCtrl.checkAccessTokenSync',
              'permission': 'abilityAccessCtrl.requestPermissionsFromUser', 'source': 'ImageSource.getImageProperty',
              'consent_request': 'PhotoAccessHelper.showAssetsCreationDialog', 'consent_result': 'PhotoAccessHelper.showAssetsCreationDialog',
              'created': 'fs.writeSync+closeSync', 'asset': 'PhotoAccessHelper.getAssets', 'baseline_assets': 'PhotoAccessHelper.getAssets',
              'related': 'KnowledgeContent.getRelatedEntity', 'search': 'KnowledgeContent.getSearchSuggestion',
              'zero_count': 'KnowledgeContent.getRelatedEntity', 'trash_album': 'PhotoAccessHelper.getAlbums',
              'trash_asset': 'Album.getAssets', 'held': 'PhotoAccessHelper.getAssets', 'private_removed': 'fs.unlinkSync'}


def load(path):
    return json.loads(Path(path).read_text())


def validate_challenge(path):
    value = load(path)
    require(type(value.get('schema_version')) is int and value['schema_version'] == 1 and
            re.fullmatch('[a-f0-9]{32}', value.get('run_id', '')) and value.get('user_id') == 100 and
            value.get('first_artifact_behavior_gate_passed') is False, 'fresh exact challenge identity required')
    calendar = checked(value['calendar'])
    facts = load(checked(value['calendar_provenance']))
    require(facts.get('asset', {}).get('sha256') == sha(calendar), 'calendar provenance/hash differs')
    events = calendar_events(calendar)
    cases = value['cases']
    require(1 <= len(cases) <= 64 and len({c['case_id'] for c in cases}) == len(cases), 'bounded unique cases required')
    days = {c['day'] for c in cases}
    for event in events:
        from datetime import timedelta
        last = (datetime.strptime(event['end'], '%Y%m%d').date()-timedelta(days=1)).strftime('%Y%m%d')
        require({event['start'], last, event['end']} <= days, 'first/last/exclusive-end omitted')
    makeup = {day.replace('-', '') for day in facts['makeup_workdays_not_in_holiday_ics']}
    require(makeup <= days and all(not expected_entities(events, day) for day in makeup), 'makeup days missing or mislabeled holidays')
    years = [int(e['start'][:4]) for e in events]
    require({f'{min(years)-1:04}1231', f'{max(years)+1:04}0101'} <= days, 'outside-calendar years missing')
    image_hashes = set()
    for case in cases:
        day = case['day']
        stamp = datetime.strptime(day+'120000', '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
        require(case['case_id'] == 'd'+day and case['file_name'] == 'd'+day+'.jpg' and
                case['title'] == 'kh-'+value['run_id']+'-d'+day and
                case['date_taken_utc_seconds'] == int(stamp.timestamp()) and
                case['exif_datetime'] == stamp.strftime('%Y:%m:%d %H:%M:%S') and
                case['entities'] == expected_entities(events, day), 'case does not match actual calendar/EXIF contract')
        image_path = checked(case['image'])
        with Image.open(image_path) as image:
            exif = image.getexif()
            details = exif.get_ifd(34665)
            require(image.format == 'JPEG' and image.size == (320, 240) and
                    exif.get(306) == case['exif_datetime'] and
                    all(details.get(key) == case['exif_datetime'] for key in (36867, 36868)) and
                    all(details.get(key) == '+00:00' for key in (36880, 36881, 36882)) and
                    re.fullmatch('[a-f0-9]{32}', details.get(42016, '')), 'actual JPEG EXIF missing/changed')
        require(case['image']['sha256'] not in image_hashes, 'reused challenge image bytes')
        image_hashes.add(case['image']['sha256'])
    require(value['lifecycle_case'] in {c['case_id'] for c in cases if c['entities']}, 'lifecycle needs a real holiday asset')
    return value


def prepare_request(challenge, boot_id, phase, uris=None, operation_id=None):
    import secrets
    data = validate_challenge(challenge)
    require(re.fullmatch('[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', boot_id or ''), 'real guest boot UUID required')
    matches = [row for row in STEPS if row[0] == phase]
    require(len(matches) == 1, 'unknown exact phase')
    _, role, action = matches[0]
    uris = uris or {}
    selected = data['cases']
    if phase == 'present':
        # The HAP's count=0 boundary must use a truly nonempty holiday topic.
        selected = sorted(selected, key=lambda c: c['case_id'] != data['lifecycle_case'])
    if role == 'curator' and action not in ('permission', 'prepare', 'cleanup'):
        selected = [c for c in selected if c['case_id'] == data['lifecycle_case']]
    elif action == 'cleanup':
        selected = [c for c in selected if c['case_id'] != data['lifecycle_case']]
    needs_uris = action not in ('access', 'permission', 'baseline', 'import', 'remove-private')
    if needs_uris:
        require(set(uris) == {c['case_id'] for c in data['cases']} and len(set(uris.values())) == len(uris) and
                all(re.fullmatch(r'file://media/Photo/[1-9][0-9]*/[^\s\x00]+', uri) for uri in uris.values()), 'original unique public-created URI mapping required')
    operation_id = operation_id or secrets.token_hex(16)
    require(re.fullmatch('[a-f0-9]{32}', operation_id), 'fresh operation nonce required')
    return {'schema_version': 1, 'run_id': data['run_id'], 'boot_id': boot_id, 'operation_id': operation_id,
            'role': role, 'phase': phase, 'action': action,
            'items': [{k: c[k] for k in ('case_id', 'day', 'title', 'file_name')} |
                      {'uri': uris[c['case_id']] if needs_uris else ''} for c in selected]}


def parse_journal(raw, run, boot, role):
    require(role in ROLES and isinstance(raw, str) and 0 < len(raw.encode()) <= 16777216 and raw.endswith('\n'), 'complete bounded role JSONL required')
    rows = []
    identity = None
    for line in raw.splitlines():
        row = json.loads(line)
        require(set(row) == ROW_KEYS and type(row['schema_version']) is int and row['schema_version'] == 1 and
                row['run_id'] == run and row['boot_id'] == boot and row['role'] == role and
                type(row['sequence']) is int and row['sequence'] == len(rows)+1 and
                re.fullmatch('[a-f0-9]{32}', row['operation_id']), 'stale, reordered or malformed role journal')
        for key in ('timestamp_ms', 'uid', 'token_id'):
            require(type(row[key]) is int and row[key] > 0, 'actual numeric identity/time required')
        require(row['uid']//200000 == 100 and row['uid'] % 200000 >= 10000 and row['token_id'] < 2**32 and
                type(row['error_code']) is int and isinstance(row['error_message'], str) and
                isinstance(row['value_json'], str) and len(row['value_json'].encode()) <= 1048576, 'invalid raw identity/value/error')
        current = (row['uid'], row['token_id'])
        identity = identity or current
        require(identity == current, 'UID/token changed during role session')
        require(row['event'] != 'error', 'actual public caller error: '+row['api']+' '+row['error_message'])
        require(row['event'] in {'begin', 'complete', 'access', 'permission', 'source', 'consent_request', 'consent_result',
                'created', 'related', 'baseline_assets', 'asset', 'search', 'zero_count', 'boundary_error',
                'boundary_resolved', 'access_error', 'access_resolved', 'trash_album', 'trash_asset', 'held',
                'mutation', 'private_removed'}, 'unknown raw event')
        if row['event'] not in {'boundary_error', 'access_error'}:
            require(row['error_code'] == 0 and row['error_message'] == '', 'successful event carries a hidden error')
        if row['event'] in EVENT_APIS:
            require(row['api'] == EVENT_APIS[row['event']], 'raw event claims another API')
        row = dict(row, value=json.loads(row['value_json']))
        rows.append(row)
    return rows


def _one(rows, event, api=None):
    result = [row for row in rows if row['event'] == event and (api is None or row['api'] == api)]
    require(len(result) == 1, 'exactly one actual '+event+' result required')
    return result[0]


def _indexed(rows, event):
    result = {}
    for row in rows:
        if row['event'] == event:
            case = row['value']['case_id']
            require(case not in result, 'duplicate '+event+' case')
            result[case] = row['value']
    return result


def _entities(value):
    require(isinstance(value, list) and len(value) <= 64, 'bounded actual entity array required')
    for entity in value:
        require(isinstance(entity, dict) and set(entity) == {'id', 'name', 'field', 'alias'} and
                type(entity['field']) is int and entity['field'] == 7 and isinstance(entity['id'], str) and
                isinstance(entity['name'], str) and entity['id'] and entity['name'] and entity['alias'] == [], 'actual SDK HOLIDAY entity shape differs')
    require(len({e['id'] for e in value}) == len(value), 'duplicate holiday entity')
    return sorted(value, key=lambda e: e['id'])


def verify_raw(challenge, journals, *, boot_id):
    """Semantic oracle ONLY. Caller/source/signature/transport must be checked separately."""
    data = validate_challenge(challenge)
    require(set(journals) == set(ROLES), 'all four real role journals required')
    parsed = {role: parse_journal(Path(path).read_text(), data['run_id'], boot_id, role) for role, path in journals.items()}
    require(len({rows[0]['uid'] for rows in parsed.values()}) == 4 and
            len({rows[0]['token_id'] for rows in parsed.values()}) == 4, 'four separate actual UID/token roles required')
    operations = {}
    for role, rows in parsed.items():
        groups = {}
        for row in rows:
            groups.setdefault(row['operation_id'], []).append(row)
        for op, group in groups.items():
            begin = _one(group, 'begin', 'request')
            complete = _one(group, 'complete', 'request')
            require(group[0] is begin and group[-1] is complete and begin['timestamp_ms'] <= complete['timestamp_ms'], 'unfinished/reordered operation')
            phase = begin['phase']
            require(phase not in operations and all(row['phase'] == phase for row in group), 'repeated or mixed phase')
            operations[phase] = group
    require(set(operations) == {s[0] for s in STEPS}, 'missing/extra lifecycle, denial or cleanup phase')
    created = _indexed(operations['import'], 'created')
    cases = {case['case_id']: case for case in data['cases']}
    require(set(created) == set(cases), 'all external images must actually be publicly created')
    uris = {key: row['uri'] for key, row in created.items()}
    previous_time = 0
    for phase, role, action in STEPS:
        group = operations[phase]
        request = group[0]['value']
        expected = prepare_request(challenge, boot_id, phase, uris, group[0]['operation_id'])
        require(json.dumps(request, sort_keys=True) == json.dumps(expected, sort_keys=True) and
                all(row['role'] == role for row in group), 'actual caller request differs from exact prepared phase')
        require(group[0]['timestamp_ms'] >= previous_time, 'cross-role operation order differs')
        previous_time = group[-1]['timestamp_ms']
        access = [row['value'] for row in group if row['event'] == 'access']
        require(access and all(set(v) == {'read', 'write'} and type(v['read']) is int and type(v['write']) is int and
                v['read'] in (-1, 0) and v['write'] in (-1, 0) for v in access), 'actual self permission checks absent')
        if role in ('importer', 'denied'):
            require(all(v == {'read': -1, 'write': -1} for v in access), 'normal zero-permission role has broad media access')
        elif action not in ('permission', 'access'):
            require(all(v['read'] == 0 and v['write'] == (0 if role == 'curator' else -1) for v in access), 'actual needed/minimal grant differs')
    # Real nonsystem / system-without-read checks; undefined API/TypeError is never 202.
    denied = [r for r in operations['normal-denied'] if r['event'] == 'access_error']
    require({r['api'] for r in denied} == {'KnowledgeContent.getRelatedEntity', 'KnowledgeContent.getSearchSuggestion'} and
            len(denied) == 2 and all(r['error_code'] == 202 for r in denied) and
            not any(r['event'] == 'access_resolved' for r in operations['normal-denied']), 'actual normal caller 202 checks failed')
    before = _one(operations['system-denied'], 'access_error', 'KnowledgeContent.getRelatedEntity')
    require(before['error_code'] == 201 and _one(operations['system-denied'], 'access')['value']['read'] == -1, 'actual pre-grant system 201 absent')
    for phase, names in [('read-permission', [READ]), ('write-permission', [READ, WRITE])]:
        permission = _one(operations[phase], 'permission', 'abilityAccessCtrl.requestPermissionsFromUser')['value']
        require(permission['permissions'] == names and permission['authResults'] == [0]*len(names) and
                all(type(v) is int for v in permission['authResults']), 'actual user permission decision missing/denied')
        accesses = [r['value'] for r in operations[phase] if r['event'] == 'access']
        require(accesses[-1]['read'] == 0 and (phase != 'write-permission' or accesses[-1]['write'] == 0), 'actual post-dialog token still denied')
    source = _indexed(operations['import'], 'source')
    require(set(source) == set(cases), 'actual source EXIF observations absent')
    consent = _one(operations['import'], 'consent_result')['value']['uris']
    require(consent == [uris[i['case_id']] for i in operations['import'][0]['value']['items']], 'created URIs differ from actual dialog result')
    _one(operations['import'], 'consent_request', 'PhotoAccessHelper.showAssetsCreationDialog')
    for key, case in cases.items():
        require(source[key]['date_time_original'] == case['exif_datetime'] and source[key]['date_time_digitized'] == case['exif_datetime'] and
                source[key]['bytes'] == checked(case['image']).stat().st_size and created[key]['bytes'] == source[key]['bytes'] and
                created[key]['title'] == case['title'], 'EXIF source/public write does not match challenge')
    lifecycle = data['lifecycle_case']
    query_phases = ['baseline', 'present', 'hidden', 'unhidden', 'trashed', 'recovered', 'deleted', 'cleanup']
    for phase in query_phases:
        group = operations[phase]
        related = _indexed(group, 'related')
        require(set(related) == set(cases), 'missing actual related query')
        assets = _indexed(group, 'baseline_assets' if phase == 'baseline' else 'asset')
        require(set(assets) == set(cases), 'missing actual per-image/date asset query')
        for key, case in cases.items():
            absent = phase in ('baseline', 'cleanup') or (key == lifecycle and phase in ('hidden', 'trashed', 'deleted'))
            require(type(assets[key]['count']) is int and assets[key]['count'] == (0 if absent else 1), 'actual asset visibility differs: '+phase+'/'+key)
            row = related[key]
            require(row['topic'] == case['day'] and row['context'] == {'topicField': [6]} and
                    row['options'] == {'suggestionFields': [7], 'recommendationCount': 64} and
                    _entities(row['entities']) == ([] if absent else case['entities']), 'actual HOLIDAY relation differs: '+phase+'/'+key)
            if phase != 'baseline':
                asset = assets[key]
                require(asset['requested_uri'] == uris[key], 'query switched URI')
                if not absent:
                    require(asset['uri'] == uris[key] and asset['title'] == case['title'] and
                            asset['date_day'] == case['day'] and type(asset['date_taken']) is int and
                            asset['date_taken'] == case['date_taken_utc_seconds'], 'real EXIF/DATE_DAY/DATE_TAKEN producer mismatch: '+key)
        search = _one(group, 'search', 'KnowledgeContent.getSearchSuggestion')['value']
        require(search['types'] == [6] and isinstance(search['results'], list), 'real TIME_PEOPLE query absent')
        # Public creation of JPEGs does not produce people analysis. Do not claim
        # an empty result is a validated nonempty analysis producer.
        require(search['results'] == [], 'unexpected people index on controlled fresh test corpus; requires separate analysis evidence')
        if phase in ('deleted', 'cleanup'):
            album = _one(group, 'trash_album', 'PhotoAccessHelper.getAlbums')['value']['count']
            require(type(album) is int and album in (0, 1), 'actual trash album query missing')
            if album == 1:
                trash = _indexed(group, 'trash_asset')
                require(set(trash) == set(cases) and all(type(v['count']) is int and v['count'] == 0 and v['uri'] == uris[k]
                        for k, v in trash.items()), 'permanently deleted assets remain in actual trash')
    require(_one(operations['present'], 'zero_count')['value'] == [], 'recommendationCount=0 did not return actual empty result')
    errors = {r['api']: r['error_code'] for r in operations['present'] if r['event'] == 'boundary_error'}
    require(errors == {'negative-count': 13900020, 'none-field': 13900020, 'empty-search': 23800151} and
            not any(r['event'] == 'boundary_resolved' for r in operations['present']), 'actual parameter boundary checks failed')
    held = _indexed(operations['prepare'], 'held')
    require(set(held) == set(cases) and all(v['uri'] == uris[k] and v['title'] == cases[k]['title'] for k, v in held.items()), 'curator did not retain exact public-owned assets')
    for phase, hidden in [('hide', True), ('unhide', False)]:
        value = _one(operations[phase], 'mutation', 'MediaAssetChangeRequest.setHidden+PhotoAccessHelper.applyChanges')['value']
        require(value == {'case_id': lifecycle, 'uri': uris[lifecycle], 'hidden': hidden}, 'actual hidden mutation targets another asset')
    for phase, api in [('trash', 'MediaAssetChangeRequest.deleteAssets'), ('trash-again', 'MediaAssetChangeRequest.deleteAssets'),
                       ('recover', 'MediaAlbumChangeRequest.recoverAssetsWithUri+PhotoAccessHelper.applyChanges'),
                       ('delete', 'MediaAlbumChangeRequest.deleteAssetsWithUri+PhotoAccessHelper.applyChanges')]:
        require(_one(operations[phase], 'mutation', api)['value'] == {'uris': [uris[lifecycle]]}, 'actual lifecycle mutation missing/wrong URI')
    remaining = [uris[c['case_id']] for c in data['cases'] if c['case_id'] != lifecycle]
    for api in ('MediaAssetChangeRequest.deleteAssets', 'MediaAlbumChangeRequest.deleteAssetsWithUri+PhotoAccessHelper.applyChanges'):
        require(_one(operations['cleanup-assets'], 'mutation', api)['value'] == {'uris': remaining}, 'owned media cleanup incomplete')
    private = _indexed(operations['cleanup-private'], 'private_removed')
    require(set(private) == set(cases) and all(v['exists_after'] is False and v['file_name'] == cases[k]['file_name'] for k, v in private.items()), 'private JPEG cleanup incomplete')
    return {'scope': data['scope'], 'raw_semantics_passed': True, 'guest_identity_verified': False,
            'stages_verified': len(STEPS), 'images_verified': len(cases), 'account_isolation_verified': False,
            'nonempty_analysis_producer_verified': False, 'first_artifact_behavior_gate_passed': False,
            'identities_from_raw_only': {role: {'uid': rows[0]['uid'], 'token_id': rows[0]['token_id']} for role, rows in parsed.items()},
            'uris': uris, 'ledger_closed': False}


def _objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def verify_role_bindings(capture, challenge, env, *, command, output):
    """Recompute SDK source, real Java/CMS signature, BMS and token artifacts.

    Root supplies command(argv,label) for actual read-only Java/OpenSSL checks.
    This does not certify that HDC command output really came from the enclosing
    guest, or that a native observer ELF/DSO was built from its claimed source.
    Root must independently bind its collector and product-built observer. No
    full guest/pass entry point is exposed before those shared pieces exist.
    """
    import batch_apps_contact_picker_coordinator as signatures
    data = validate_challenge(challenge)
    require(set(capture['roles']) == set(ROLES) and env['user_id'] == 100 and
            capture['run_id'] == data['run_id'] and capture['boot_id'] == env['boot_id'] and
            re.fullmatch('[a-fA-F0-9]{64}', env['udid']) and
            capture['archive_sha256'] == env['archive_sha256'], 'capture/acceptance boot binding differs')
    require(sha(checked(capture['archive'])) == env['archive_sha256'], 'actual current package archive changed')
    require(sha(checked(capture['guest_calendar'])) == data['calendar']['sha256'], 'guest system holiday resource differs from challenge')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    result = {}
    for role, (bundle, apl, permissions, template) in ROLES.items():
        item = capture['roles'][role]
        sdk = signatures.verify_sdk_project(item['sdk'])
        source = Path(item['sdk']['source_project']).resolve()
        manifest_path = checked(item['sdk']['source_manifest'])
        require(manifest_path == source / 'knowledge-source-manifest.json', 'wrong compiled source manifest')
        manifest = load(manifest_path)
        require(manifest['run_id'] == data['run_id'] and manifest['role'] == role and manifest['bundle_name'] == bundle and
                manifest['requested_permissions'] == permissions and manifest['allowed_acls'] == [] and
                manifest['restricted_permissions'] == [] and manifest['challenge'] == record(challenge) and
                manifest['fixture_hashes'] == {p.name: sha(p) for p in sorted(FIX.iterdir()) if p.is_file()}, 'compiled role/run/fixture manifest differs')
        evidence = load(checked(item['sdk']['sdk_evidence']))
        project = item['sdk']['sdk_project']
        source_rows = signatures.source_rows(evidence, project)
        require('knowledge-source-manifest.json' in source_rows and source_rows['knowledge-source-manifest.json'] == sha(manifest_path), 'SDK did not freeze role source manifest')
        for name, expected in manifest['source_hashes'].items():
            require(source_rows.get(name) == expected and sha(source / name) == expected, 'compiled source file changed')
        for fixture_name, relative in [(template, 'pages/Index.ets'), ('AuditStore.ets', 'model/AuditStore.ets'),
                                       ('EntryAbility.ets', 'entryability/EntryAbility.ets')]:
            expected = (FIX / fixture_name).read_text().replace('__KNOWLEDGE_RUN__', data['run_id']).replace('__KNOWLEDGE_ROLE__', role)
            require((source / 'entry/src/main/ets' / relative).read_text() == expected, 'actual compiled caller changed API logic')
        proof = signatures.verify_signed_hap_artifacts(checked(item['signed_hap']), bundle, permissions, env['udid'],
            capture['signer']['dist'], checked(capture['signer']['jar']), output / role, command,
            apl=apl, system_app=apl != 'normal')
        unsigned = checked(item['sdk']['unsigned_hap'])
        signatures.verify_signed_payload(unsigned, checked(item['signed_hap']))
        require(sha(checked(item['installed_hap'])) == item['signed_hap']['sha256'],
                'actual installation changed the signed HAP payload')
        bms_raw = checked(item['bms']).read_text()
        if bms_raw.startswith(bundle+':\n'):
            bms_raw = bms_raw[len(bundle)+2:]
        bms = json.loads(bms_raw)
        app = bms['applicationInfo']
        require((app.get('name') or app.get('bundleName')) == bundle and app.get('isSystemApp') is (apl != 'normal') and
                app.get('appPrivilegeLevel') == apl and type(app.get('uid')) is int and app['uid']//200000 == 100 and
                type(app.get('accessTokenId')) is int and app['accessTokenId'] > 0, 'actual BMS role/UID/token mismatch')
        paths = {obj['hapPath'] for obj in _objects(bms) if isinstance(obj.get('hapPath'), str) and obj['hapPath'].startswith('/data/app/')}
        require(paths == {item['installed_remote']} and item['installed_remote'].endswith('.hap'), 'installed HAP not selected by actual unique BMS path')
        journals = parse_journal(checked(item['journal']).read_text(), data['run_id'], env['boot_id'], role)
        require(all(row['uid'] == app['uid'] and row['token_id'] == app['accessTokenId'] for row in journals), 'raw journal is not the actual installed role UID/token')
        for phase in ('initial', 'final'):
            token = load(checked(item['token_'+phase]))
            expected_read = -1 if phase == 'initial' or apl == 'normal' else 0
            expected_write = (-1 if phase == 'initial' else 0) if role == 'curator' else None
            require(token.get('schema_version') == 1 and token.get('api') == 'AccessTokenKit::VerifyAccessToken' and
                    token.get('run_id') == data['run_id'] and token.get('boot_id') == env['boot_id'] and token.get('bundle') == bundle and
                    token.get('uid') == app['uid'] and token.get('token_id') == app['accessTokenId'] and token.get('user_id') == 100 and
                    type(token.get('READ_IMAGEVIDEO')) is int and token['READ_IMAGEVIDEO'] == expected_read and
                    token.get('WRITE_IMAGEVIDEO') == expected_write and
                    (expected_write is None or type(token.get('WRITE_IMAGEVIDEO')) is int) and
                    type(token.get('before_ns')) is int and type(token.get('after_ns')) is int and
                    0 < token['before_ns'] <= token['after_ns'], 'actual read-only product token observation differs')
        require(set(item.get('private_source_readbacks', {})) == ({c['case_id'] for c in data['cases']} if role == 'importer' else set()), 'actual private JPEG readbacks incomplete')
        for case in data['cases'] if role == 'importer' else []:
            require(sha(checked(item['private_source_readbacks'][case['case_id']])) == case['image']['sha256'], 'guest private source is not current external nonce JPEG')
        result[role] = {'sdk': sdk, 'signature': proof, 'BMS': item['bms'], 'uid': app['uid'],
                        'token_id': app['accessTokenId'], 'installed_hap': item['installed_hap']}
    require(len({v['uid'] for v in result.values()}) == 4 and len({v['token_id'] for v in result.values()}) == 4, 'real role identities overlap')
    return {'scope': 'compiled_sources_actual_signatures_installed_HAP_BMS_and_token_artifacts_ONLY', 'roles': result,
            'transport_guest_binding_verified': False, 'observer_product_ABI_verified': False,
            'account_isolation_verified': False, 'first_artifact_behavior_gate_passed': False, 'ledger_closed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    request = sub.add_parser('request')
    request.add_argument('--challenge', type=Path, required=True)
    request.add_argument('--boot-id', required=True)
    request.add_argument('--phase', choices=[s[0] for s in STEPS], required=True)
    request.add_argument('--uris', type=Path)
    request.add_argument('--output', type=Path, required=True)
    verify = sub.add_parser('verify-raw')
    verify.add_argument('--challenge', type=Path, required=True)
    verify.add_argument('--boot-id', required=True)
    for role in ROLES:
        verify.add_argument('--'+role, type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'request':
        write(args.output, prepare_request(args.challenge, args.boot_id, args.phase, load(args.uris) if args.uris else None))
        print(args.output)
    else:
        print(json.dumps(verify_raw(args.challenge, {role: getattr(args, role) for role in ROLES}, boot_id=args.boot_id), indent=2))


if __name__ == '__main__':
    main()
