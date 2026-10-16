#!/usr/bin/env python3
"""Prepare unsigned API26 Knowledge callers and external, EXIF-bearing JPEGs.

This command does not build, sign, install, grant, boot or write a media database.
The calendar is a real input, not a claim that arbitrary dates are holidays.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIX = HERE / 'fixtures/batch_media/knowledge_runtime'
READ = 'ohos.permission.READ_IMAGEVIDEO'
WRITE = 'ohos.permission.WRITE_IMAGEVIDEO'
# SDK105 does not ship device-define/phone.json. Its own diagnostic selects
# default for the phone family; the acceptance runner still requires phone.
SDK_DEVICE_TYPES = ['default']
ACCEPTANCE_DEVICE = 'phone'
REQUIRED_SYSCAPS = {
    'SystemCapability.Base',
    'SystemCapability.ArkUI.ArkUI.Full',
    'SystemCapability.Ability.AbilityRuntime.Core',
    'SystemCapability.WindowManager.WindowManager.Core',
    'SystemCapability.BundleManager.BundleFramework.Core',
    'SystemCapability.Security.AccessToken',
    'SystemCapability.Utils.Lang',
    'SystemCapability.FileManagement.File.FileIO',
    'SystemCapability.FileManagement.AppFileService',
    'SystemCapability.FileManagement.PhotoAccessHelper.Core',
    'SystemCapability.DistributedDataManager.DataShare.Core',
    'SystemCapability.Multimedia.Image.Core',
    'SystemCapability.Multimedia.Image.ImageSource',
}
ROLES = {
    'importer': ('org.harmonycontrib.knowledgeimporter', 'normal', [], 'Importer.ets'),
    'denied': ('org.harmonycontrib.knowledgedenied', 'normal', [], 'Denied.ets'),
    'query': ('org.harmonycontrib.knowledgequery', 'system_basic', [READ], 'Query.ets'),
    'curator': ('org.harmonycontrib.knowledgecurator', 'system_basic', [READ, WRITE], 'Curator.ets'),
}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'regular input required')
    return {'path': str(path.resolve()), 'sha256': sha(path)}


def checked(value):
    require(isinstance(value, dict) and set(value) == {'path', 'sha256'}, 'exact artifact descriptor required')
    path = Path(value['path'])
    require(path.is_absolute() and record(path) == value, 'artifact bytes/path changed')
    return path


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def calendar_events(path):
    """Independent all-day fixture oracle; deliberately rejects unhandled ICS."""
    raw = Path(path).read_bytes()
    require(0 < len(raw) <= 1048576 and b'\x00' not in raw, 'bounded UTF-8 ICS required')
    physical = raw.decode('utf-8').replace('\r\n', '\n').splitlines()
    lines = []
    for line in physical:
        if line.startswith((' ', '\t')):
            require(bool(lines), 'invalid initial fold')
            lines[-1] += line[1:]
        else:
            lines.append(line)
    require(lines[0] == 'BEGIN:VCALENDAR' and lines[-1] == 'END:VCALENDAR', 'calendar envelope required')
    events, current = [], None
    for line in lines[1:-1]:
        if line == 'BEGIN:VEVENT':
            require(current is None, 'nested event')
            current = {}
        elif line == 'END:VEVENT':
            require(current is not None and set(current) == {'UID', 'DTSTART;VALUE=DATE', 'DTEND;VALUE=DATE', 'SUMMARY'},
                    'complete bounded all-day interval required')
            first = datetime.strptime(current['DTSTART;VALUE=DATE'], '%Y%m%d').date()
            end = datetime.strptime(current['DTEND;VALUE=DATE'], '%Y%m%d').date()
            require(0 < (end-first).days <= 370 and len(events) < 1000, 'bounded positive event span required')
            uid, name = current['UID'], current['SUMMARY']
            require(uid and name and len(uid.encode()) <= 4096 and len(name.encode()) <= 4096, 'bounded UID/name required')
            events.append({'uid': uid, 'start': first.strftime('%Y%m%d'), 'end': end.strftime('%Y%m%d'),
                           'name': name, 'id': str(len(uid.encode())) + ':' + uid + ':' + first.strftime('%Y%m%d')})
            current = None
        elif current is not None:
            require(':' in line, 'invalid property')
            key, value = line.split(':', 1)
            if key.startswith('SUMMARY;LANGUAGE='):
                key = 'SUMMARY'
            require(key in {'UID', 'SUMMARY', 'DTSTART;VALUE=DATE', 'DTEND;VALUE=DATE'} and key not in current,
                    'unsupported or repeated authoritative event property')
            value = re.sub(r'\\([nN,;\\])', lambda m: '\n' if m[1] in 'nN' else m[1], value)
            require('\\' not in value, 'unsupported ICS escape')
            current[key] = value
        else:
            require(not line.startswith(('BEGIN:', 'END:')), 'unsupported calendar component')
    require(current is None and events, 'complete nonempty calendar required')
    require(len({(e['uid'], e['start']) for e in events}) == len(events), 'duplicate calendar instance')
    return events


def expected_entities(events, day):
    return sorted([{'field': 7, 'id': e['id'], 'name': e['name'], 'alias': []}
                   for e in events if e['start'] <= day < e['end']], key=lambda e: e['id'])


def check_device_profile(sdk):
    """Read the real SDK profile; never synthesize or override capabilities."""
    profile = Path(sdk) / 'ets/api/device-define/default.json'
    capabilities = json.loads(profile.read_text()).get('SysCaps')
    require(isinstance(capabilities, list) and all(isinstance(value, str) for value in capabilities) and
            REQUIRED_SYSCAPS <= set(capabilities), 'actual SDK105 default profile lacks a required caller capability')
    return record(profile)


def check_sdk(sdk):
    sdk = Path(sdk).resolve()
    metadata = sdk / 'ets/oh-uni-package.json'
    require(json.loads(metadata.read_text()).get('version') == '26.0.0.105', 'fixed actual SDK105 ETS required')
    declaration = sdk / 'ets/api/@ohos.file.photoAccessHelper.d.ts'
    source = declaration.read_text()
    for text in ['class KnowledgeContent', 'static getRelatedEntity(topic: string, context: ContextMap, option?: Options)',
                 'static getSearchSuggestion(searchSuggestionTypes:', "DATE_DAY = 'date_day'", 'setHidden(hiddenState: boolean)',
                 'showAssetsCreationDialog(srcFileUris:', 'recoverAssetsWithUri(assetUris:', 'deleteAssetsWithUri(assetUris:']:
        require(text in source, 'actual SDK declaration missing: ' + text)
    return {'metadata': record(metadata), 'photoAccessHelper': record(declaration),
            'image': record(sdk / 'ets/api/@ohos.multimedia.image.d.ts'),
            'device_default': check_device_profile(sdk)}


def make_challenge(output, calendar, provenance, run=None):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    run = run or secrets.token_hex(16)
    require(re.fullmatch('[0-9a-f]{32}', run) is not None, 'fresh 32-lowerhex run required')
    events = calendar_events(calendar)
    provenance = Path(provenance)
    facts = json.loads(provenance.read_text())
    require(facts.get('asset', {}).get('sha256') == sha(calendar), 'provenance does not bind actual ICS')
    reasons = {}
    def add(day, reason):
        reasons.setdefault(day, []).append(reason)
    for event in events:
        add(event['start'], 'first:' + event['uid'])
        add((datetime.strptime(event['end'], '%Y%m%d').date()-timedelta(days=1)).strftime('%Y%m%d'), 'last:' + event['uid'])
        add(event['end'], 'exclusive-end:' + event['uid'])
    for day in facts['makeup_workdays_not_in_holiday_ics']:
        add(date.fromisoformat(day).strftime('%Y%m%d'), 'makeup-workday')
    years = [int(e['start'][:4]) for e in events]
    add(f'{min(years)-1:04}1231', 'outside-calendar-before')
    add(f'{max(years)+1:04}0101', 'outside-calendar-after')
    require(len(reasons) <= 64, 'single bounded creation dialog limited to 64 images')
    cases = []
    for day, labels in sorted(reasons.items()):
        stamp = datetime.strptime(day+'120000', '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
        exif_time = stamp.strftime('%Y:%m:%d %H:%M:%S')
        case_id = 'd' + day
        image = Image.new('RGB', (320, 240))
        draw = ImageDraw.Draw(image)
        for y in range(0, 240, 20):
            for x in range(0, 320, 20):
                draw.rectangle((x, y, x+19, y+19), fill=tuple(secrets.randbelow(256) for _ in range(3)))
        draw.text((8, 8), run + ' ' + day, fill='white')
        exif = Image.Exif()
        exif[306] = exif_time
        # DateTimeOriginal/OffsetTimeOriginal belong in the actual Exif sub-IFD,
        # not arbitrary IFD0 tags that a standards-compliant scanner may ignore.
        exif[34665] = {36867: exif_time, 36868: exif_time, 36880: '+00:00',
                       36881: '+00:00', 36882: '+00:00', 42016: secrets.token_hex(16)}
        path = output / (case_id + '.jpg')
        image.save(path, format='JPEG', quality=93, exif=exif)
        cases.append({'case_id': case_id, 'day': day, 'reasons': labels, 'file_name': path.name,
                      'title': 'kh-' + run + '-' + case_id, 'image': record(path),
                      'exif_datetime': exif_time, 'offset_time_original': '+00:00',
                      'date_taken_utc_seconds': int(stamp.timestamp()), 'entities': expected_entities(events, day)})
    lifecycle = next(c['case_id'] for c in cases if c['entities'])
    value = {'schema_version': 1, 'run_id': run, 'calendar': record(calendar), 'calendar_provenance': record(provenance),
             'generator': record(Path(__file__)), 'cases': cases, 'lifecycle_case': lifecycle, 'user_id': 100,
             'scope': 'account100_HOLIDAY_asset_relations_NOT_account_isolation_or_analysis_producers',
             'first_artifact_behavior_gate_passed': False}
    write(output / 'challenge.json', value)
    return output / 'challenge.json'


def prepare_project(output, role, challenge, sdk):
    require(role in ROLES, 'unknown exact caller role')
    challenge = Path(challenge).resolve()
    data = json.loads(challenge.read_text())
    run = data['run_id']
    require(re.fullmatch('[0-9a-f]{32}', run) is not None, 'challenge run invalid')
    sdk_proof = check_sdk(sdk)
    output = Path(output).resolve()
    require(not output.exists() and output != ROOT and ROOT not in output.parents, 'fresh private project outside repository required')
    output.mkdir(parents=True)
    bundle, apl, permissions, template = ROLES[role]
    def put(name, value):
        write(output / name, value)
    put('AppScope/app.json5', {'app': {'bundleName': bundle, 'vendor': 'Harmony Contrib', 'versionCode': 1,
        'versionName': '1.0.0', 'icon': '$media:app_icon', 'label': '$string:app_name'}})
    put('AppScope/resources/base/element/string.json', {'string': [{'name': 'app_name', 'value': 'Knowledge audit ' + role},
        {'name': 'permission_reason', 'value': 'Read temporary Knowledge test photos' if role == 'query' else 'Read and remove only temporary Knowledge test photos'}]})
    put('AppScope/resources/base/media/app_icon.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#394c82"/></svg>\n')
    put('build-profile.json5', {'app': {'products': [{'name': 'default', 'compileSdkVersion': '26.0.0',
        'compatibleSdkVersion': '26.0.0', 'targetSdkVersion': '26.0.0', 'runtimeOS': 'OpenHarmony'}]},
        'modules': [{'name': 'entry', 'srcPath': './entry', 'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]})
    put('oh-package.json5', {'modelVersion': '6.0.0', 'name': 'knowledge-' + role, 'version': '1.0.0', 'dependencies': {}, 'devDependencies': {}})
    put('hvigor/hvigor-config.json5', {'modelVersion': '6.0.0', 'dependencies': {}, 'execution': {'daemon': False, 'parallel': False}})
    put('hvigorfile.ts', "import { appTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: appTasks, plugins: [] };\n")
    put('entry/hvigorfile.ts', "import { hapTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: hapTasks, plugins: [] };\n")
    put('entry/build-profile.json5', {'apiType': 'stageMode', 'targets': [{'name': 'default'}]})
    put('entry/oh-package.json5', {'name': 'entry', 'version': '1.0.0', 'dependencies': {}})
    put('entry/src/main/module.json5', {'module': {'name': 'entry', 'type': 'entry', 'mainElement': 'EntryAbility',
        'deviceTypes': list(SDK_DEVICE_TYPES), 'deliveryWithInstall': True, 'installationFree': False,
        'pages': '$profile:main_pages', 'requestPermissions': [{'name': p, 'reason': '$string:permission_reason',
        'usedScene': {'abilities': ['EntryAbility'], 'when': 'inuse'}} for p in permissions],
        'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets', 'launchType': 'singleton',
        'exported': True, 'label': '$string:app_name', 'icon': '$media:app_icon', 'startWindowIcon': '$media:app_icon',
        'startWindowBackground': '$color:start_window_background'}]}})
    put('entry/src/main/resources/base/element/color.json', {'color': [{'name': 'start_window_background', 'value': '#FFFFFF'}]})
    put('entry/src/main/resources/base/profile/main_pages.json', {'src': ['pages/Index']})
    for source, target in [(template, 'pages/Index.ets'), ('AuditStore.ets', 'model/AuditStore.ets'),
                           ('EntryAbility.ets', 'entryability/EntryAbility.ets')]:
        put('entry/src/main/ets/' + target, (FIX / source).read_text().replace('__KNOWLEDGE_RUN__', run).replace('__KNOWLEDGE_ROLE__', role))
    manifest = {'schema_version': 1, 'role': role, 'run_id': run, 'bundle_name': bundle,
        'requested_permissions': permissions, 'apl_required_at_signing': apl, 'system_app_required_at_install': apl != 'normal',
        'sdk_device_types': list(SDK_DEVICE_TYPES), 'acceptance_device': ACCEPTANCE_DEVICE,
        'allowed_acls': [], 'restricted_permissions': [], 'challenge': record(challenge), 'sdk': sdk_proof,
        'fixture_hashes': {p.name: sha(p) for p in sorted(FIX.iterdir()) if p.is_file()},
        'source_hashes': {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()},
        'signed': False, 'runtime_acceptance': False}
    put('knowledge-source-manifest.json', manifest)
    return output / 'knowledge-source-manifest.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    challenge = sub.add_parser('challenge')
    challenge.add_argument('--calendar', type=Path, required=True)
    challenge.add_argument('--provenance', type=Path, required=True)
    challenge.add_argument('--output', type=Path, required=True)
    project = sub.add_parser('project')
    project.add_argument('--role', choices=ROLES, required=True)
    project.add_argument('--challenge', type=Path, required=True)
    project.add_argument('--sdk', type=Path, required=True)
    project.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'challenge':
        print(make_challenge(args.output, args.calendar, args.provenance))
    else:
        print(prepare_project(args.output, args.role, args.challenge, args.sdk))


if __name__ == '__main__':
    main()
