#!/usr/bin/env python3
"""Prepare unsigned Calendar QA sources/requests; never build/sign/install/boot."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets

ROOT = Path(__file__).resolve().parents[2]
FIX = Path(__file__).with_name('fixtures') / 'batch_system/calendar_runtime'
CONTRACT = json.loads((FIX / 'contract.json').read_text())
ROLES = CONTRACT['roles']
HEX = re.compile('[a-f0-9]{64}')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def record(path):
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), 'absolute regular evidence required')
    return {'path': str(path), 'sha256': sha(path)}


def checked(item):
    path = Path(item['path'])
    require(HEX.fullmatch(item['sha256']) and record(path)['sha256'] == item['sha256'], 'artifact path/hash differs')
    return path


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as output:
        output.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def challenge(output):
    output = Path(output).absolute()
    require(not output.exists() and ROOT not in output.parents, 'fresh private challenge directory required')
    output.mkdir(parents=True)
    run = secrets.token_hex(16)
    data = {'schema_version': 1, 'run_id': run, 'account_name': 'qcal_' + run,
            'cases': [{'case_id': case, 'title': 'QCAL_' + run + '_' + case,
                       'description': 'QNOTE_' + run + '_' + case} for case in CONTRACT['case_ids']],
            'contract': record(FIX / 'contract.json'), 'first_artifact_behavior_gate_passed': False}
    write(output / 'challenge.json', data)
    return output / 'challenge.json'


def load_challenge(path):
    value = json.loads(Path(path).read_text())
    run = value.get('run_id', '')
    require(value.get('schema_version') == 1 and re.fullmatch('[a-f0-9]{32}', run) and
            value.get('account_name') == 'qcal_' + run and value.get('contract') == record(FIX / 'contract.json'),
            'actual current challenge required')
    require(value['cases'] == [{'case_id': case, 'title': 'QCAL_' + run + '_' + case,
            'description': 'QNOTE_' + run + '_' + case} for case in CONTRACT['case_ids']], 'case payload changed')
    return value


def sdk_contract(sdk):
    sdk = Path(sdk).resolve()
    metadata = sdk / 'ets/oh-uni-package.json'
    require(json.loads(metadata.read_text()).get('version') == '26.0.0.105', 'real SDK26.105 required')
    declarations = {
        '@ohos.calendarManager.d.ts': ['createCalendar(calendarAccount:', 'getAllCalendars():',
            'getEvents(eventFilter?:', 'setConfig(config:', 'reminderTime?: number[];', 'updateEvent(event:', 'deleteEvent(id:'],
        '@ohos.notificationManager.d.ts': ['function getAllActiveNotifications():'],
        '@ohos.app.ability.wantAgent.d.ts': ['function getWant(agent:', 'function getBundleName(agent:', 'function getUid(agent:'],
        '@ohos.abilityAccessCtrl.d.ts': ['requestPermissionsFromUser(', 'checkAccessTokenSync('],
        'application/UIAbilityContext.d.ts': ['startAbility(want:', 'startRecentAbility(want:'],
    }
    proof = {'metadata': record(metadata)}
    for name, required in declarations.items():
        path = sdk / 'ets/api' / name
        text = path.read_text()
        require(all(part in text for part in required), 'actual SDK declaration differs: ' + name)
        proof[name] = record(path)
    profile = sdk / 'ets/api/device-define/default.json'
    caps = json.loads(profile.read_text())['SysCaps']
    require('SystemCapability.Applications.CalendarData' in caps, 'SDK default CalendarData capability missing')
    proof['device_default'] = record(profile)
    return proof


def expected_sources(data, role, sdk):
    """Pure source recipe shared by preparation and independent SDK binding."""
    require(role in ROLES, 'known exact role required')
    policy = ROLES[role]
    files = {}
    def put(name, value):
        files[name] = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    put('AppScope/app.json5', {'app': {'bundleName': policy['bundle'], 'vendor': 'Harmony Contrib', 'versionCode': 1,
        'versionName': '1.0.0', 'icon': '$media:app_icon', 'label': '$string:app_name'}})
    put('AppScope/resources/base/element/string.json', {'string': [
        {'name': 'app_name', 'value': 'Calendar QA ' + role + ' ' + data['run_id']},
        {'name': 'calendar_reason', 'value': 'Read and manage only temporary Calendar QA records with your permission'}]})
    put('AppScope/resources/base/media/app_icon.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#296848"/></svg>\n')
    put('build-profile.json5', {'app': {'products': [{'name': 'default', 'compileSdkVersion': '26.0.0',
        'compatibleSdkVersion': '26.0.0', 'targetSdkVersion': '26.0.0', 'runtimeOS': 'OpenHarmony'}]},
        'modules': [{'name': 'entry', 'srcPath': './entry', 'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]})
    put('oh-package.json5', {'modelVersion': '6.0.0', 'name': 'calendar-qa-' + role, 'version': '1.0.0', 'dependencies': {}, 'devDependencies': {}})
    put('hvigor/hvigor-config.json5', {'modelVersion': '6.0.0', 'dependencies': {}, 'execution': {'daemon': False, 'parallel': False}})
    put('hvigorfile.ts', "import { appTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: appTasks, plugins: [] };\n")
    put('entry/hvigorfile.ts', "import { hapTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: hapTasks, plugins: [] };\n")
    put('entry/build-profile.json5', {'apiType': 'stageMode', 'targets': [{'name': 'default'}]})
    put('entry/oh-package.json5', {'name': 'entry', 'version': '1.0.0', 'dependencies': {}})
    put('local.properties', 'sdk.dir=' + str(Path(sdk).resolve().parent) + '\n')
    permissions = []
    for name in policy['permissions']:
        row = {'name': name}
        if name != 'ohos.permission.NOTIFICATION_CONTROLLER':
            row.update(reason='$string:calendar_reason', usedScene={'abilities': ['EntryAbility'], 'when': 'inuse'})
        permissions.append(row)
    put('entry/src/main/module.json5', {'module': {'name': 'entry', 'type': 'entry', 'mainElement': 'EntryAbility',
        'deviceTypes': ['default', 'tablet'], 'deliveryWithInstall': True, 'installationFree': False,
        'pages': '$profile:main_pages', 'requestPermissions': permissions,
        'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets', 'launchType': 'singleton',
        'exported': True, 'label': '$string:app_name', 'icon': '$media:app_icon', 'startWindowIcon': '$media:app_icon',
        'startWindowBackground': '$color:start_window_background'}]}})
    put('entry/src/main/resources/base/element/color.json', {'color': [{'name': 'start_window_background', 'value': '#FFFFFF'}]})
    put('entry/src/main/resources/base/profile/main_pages.json', {'src': ['pages/Index']})
    for source, target in [('EntryAbility.ets', 'entryability/EntryAbility.ets'), ('Index.ets', 'pages/Index.ets'), ('CalendarAudit.ets', 'model/CalendarAudit.ets')]:
        text = (FIX / source).read_text()
        if source == 'CalendarAudit.ets' and role != 'observer':
            for block, replacement in [('imports', ''), ('observation', "    throw new Error('Observer-only operation');\n")]:
                pattern = r'(?ms)^ *// observer-only ' + block + r' BEGIN\n.*?^ *// observer-only ' + block + r' END\n'
                text, count = re.subn(pattern, lambda _: replacement, text)
                require(count == 1, 'exact observer-only source block missing')
            require('notificationManager.' not in text and 'wantAgent.' not in text,
                    'normal producer/denied source must not import or call observer system APIs')
        put('entry/src/main/ets/' + target, text.replace('__ROLE__', role).replace('__RUN__', data['run_id']))
    return files


def prepare(output, role, challenge_path, sdk):
    data = load_challenge(challenge_path)
    sdk_proof = sdk_contract(sdk)
    output = Path(output).absolute()
    require(not output.exists() and ROOT not in output.parents and not output.is_symlink(), 'fresh private source project required')
    output.mkdir(parents=True)
    files = expected_sources(data, role, sdk)
    for name, text in files.items():
        write(output / name, text)
    manifest = {'schema_version': 1, 'run_id': data['run_id'], 'role': role, **ROLES[role],
        'sdk': sdk_proof, 'challenge': record(Path(challenge_path).resolve()),
        'fixture_hashes': {p.name: sha(p) for p in sorted(FIX.iterdir()) if p.is_file()},
        'source_hashes': {name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()},
        'signed': False, 'runtime_acceptance': False}
    write(output / 'calendar-source-manifest.json', manifest)
    return output / 'calendar-source-manifest.json'


def request(challenge_path, boot, archive_sha, role, action, case, *, lead_minutes=2, spacing_minutes=2):
    data = load_challenge(challenge_path)
    require(role in ROLES and re.fullmatch('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', boot) and
            HEX.fullmatch(archive_sha) and re.fullmatch('[a-z][a-z0-9-]{0,39}', case), 'bound actual run/boot/archive/role/case required')
    allowed = {'producer': {'permission', 'access', 'create', 'read', 'update', 'delete', 'cleanup', 'routes'},
               'observer': {'permission', 'access', 'read', 'notifications'}, 'denied': {'access', 'read'}}
    require(action in allowed[role], 'role cannot execute this action')
    if action in ('update', 'delete'):
        require(case in CONTRACT['case_ids'], 'owned case required')
    value = {'schema_version': 1, 'run_id': data['run_id'], 'boot_id': boot, 'archive_sha256': archive_sha,
            'operation_id': secrets.token_hex(16), 'role': role, 'action': action, 'case_id': case}
    if action == 'create':
        require(type(lead_minutes) is int and 2 <= lead_minutes <= 30 and
                type(spacing_minutes) is int and 2 <= spacing_minutes <= 30, 'bounded real future schedule required')
        value.update(lead_minutes=lead_minutes, spacing_minutes=spacing_minutes)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    first = sub.add_parser('challenge'); first.add_argument('--output', type=Path, required=True)
    project = sub.add_parser('project')
    for name in ('output', 'challenge', 'sdk'):
        project.add_argument('--' + name, type=Path, required=True)
    project.add_argument('--role', choices=ROLES, required=True)
    args = parser.parse_args()
    path = challenge(args.output) if args.mode == 'challenge' else prepare(args.output, args.role, args.challenge, args.sdk)
    print(path)


if __name__ == '__main__':
    main()
