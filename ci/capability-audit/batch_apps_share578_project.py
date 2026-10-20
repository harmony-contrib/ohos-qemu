#!/usr/bin/env python3
"""Prepare ordinary share578 SDK105 projects; no compiler/signing/guest action."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FIX = HERE / 'fixtures/batch_apps/share578'
CONTRACT = json.loads((FIX / 'contract.json').read_text())
ROLES = CONTRACT['roles']
TOOLS = ('batch_apps_share578_project.py', 'batch_apps_share578_project_build.py',
         'batch_apps_share578_project_verify.py', 'batch_apps_share578_collect.py',
         'batch_apps_share578_integration.py', 'guest_ui.py', 'hdc_transport.py',
         'hap_identity_binding.py', 'boot_package.py', 'parallel_runtime_suite.py',
         'enclosing_acceptance_guest.py', 'batch_apps_mms578_runtime.py', 'batch_apps_contact_picker_coordinator.py',
         'batch_network_openvpn_runtime_collect.py')
HEX = re.compile('[a-f0-9]{64}')
BOOT = re.compile('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def regular(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink() and
            path.is_file() and path.stat().st_nlink == 1, 'canonical regular unaliased file required')
    return path


def record(path):
    path = regular(path)
    return {'path': str(path), 'sha256': sha(path)}


def checked(value):
    require(isinstance(value, dict) and set(value) == {'path', 'sha256'} and
            HEX.fullmatch(value['sha256']) is not None, 'exact artifact descriptor required')
    path = regular(value['path'])
    require(sha(path) == value['sha256'], 'artifact bytes changed: ' + str(path))
    return path


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def source_tools():
    return {name: sha(regular(HERE / name)) for name in TOOLS}


def fixtures():
    return {p.name: sha(regular(p)) for p in sorted(FIX.iterdir()) if p.is_file()}


def repository(commit):
    require(re.fullmatch('[a-f0-9]{40}', commit) is not None, 'explicit final commit required')
    actual = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain', '--untracked-files=no'], text=True)
    require(actual == commit and not dirty, 'root must freeze and commit all tracked source before preparation/build')
    # Ignoring unrelated private output must never let untracked producer
    # inputs borrow a commit that does not actually contain them.
    for path in [*(HERE / name for name in TOOLS), *(p for p in FIX.iterdir() if p.is_file())]:
        relative = path.relative_to(ROOT).as_posix()
        committed = subprocess.check_output(['git', '-C', str(ROOT), 'show', commit + ':' + relative])
        require(committed == regular(path).read_bytes(), 'producer input is not exact committed source: ' + relative)


def challenge(output, commit):
    repository(commit)
    output = Path(output).absolute()
    require(not output.exists() and output.parent.resolve() == output.parent and ROOT not in output.parents,
            'fresh canonical private challenge outside repository required')
    output.mkdir(parents=True)
    value = {'schema_version': 1, 'run_id': secrets.token_hex(16), 'source_commit': commit,
             'fixtures': fixtures(), 'source_tools': source_tools(), 'case_ids': list(CONTRACT['cases']) + list(CONTRACT['mms_cases']),
             'runtime_validated': False, 'first_artifact_behavior_gate_passed': False}
    write(output / 'challenge.json', value)
    write(output / 'runtime-source-pins.json', {'schema_version': 1, 'files': source_tools()})
    return output / 'challenge.json'


def load_challenge(path):
    value = json.loads(regular(path).read_text())
    require(set(value) == {'schema_version', 'run_id', 'source_commit', 'fixtures', 'source_tools', 'case_ids',
            'runtime_validated', 'first_artifact_behavior_gate_passed'} and type(value['schema_version']) is int and value['schema_version'] == 1 and
            re.fullmatch('[a-f0-9]{32}', value['run_id']) and
            re.fullmatch('[a-f0-9]{40}', value['source_commit']) and value['fixtures'] == fixtures() and
            value['source_tools'] == source_tools() and value['case_ids'] == list(CONTRACT['cases']) + list(CONTRACT['mms_cases']) and
            value['runtime_validated'] is False and value['first_artifact_behavior_gate_passed'] is False,
            'current exact challenge/source contract required')
    return value


def sdk_contract(sdk):
    sdk = Path(sdk).resolve()
    metadata = sdk / 'ets/oh-uni-package.json'
    value = json.loads(metadata.read_text())
    require(value.get('version') == '26.0.0.105' and value.get('apiVersion') == '26', 'actual official SDK105 required')
    required = {
        'application/UIAbilityContext.d.ts': ['startAbilityForResult(want: Want, options?: StartOptions): Promise<AbilityResult>;',
            'terminateSelfWithResult(parameter: AbilityResult): Promise<void>;', 'startAbility(want: Want',
            'startAbilityByType(', 'AbilityStartCallback'],
        'application/Context.d.ts': ['getApplicationContext(): ApplicationContext;'],
        '@ohos.app.ability.common.d.ts': ['export type AbilityResult = _AbilityResult;'],
        '@ohos.app.ability.Want.d.ts': ['flags?: number', 'uri?: string', 'parameters?:'],
        '@ohos.file.fileuri.d.ts': ['function getUriFromPath(path: string): string;'],
        '@ohos.file.fs.d.ts': ['declare function statSync(file: string | number): Stat;', 'readonly ino: bigint;',
            'declare function openSync(path: string, mode?: number): File;', 'const NOFOLLOW', 'declare function fsyncSync(fd: number): void;'],
        '@ohos.app.ability.wantConstant.d.ts': ['FLAG_AUTH_READ_URI_PERMISSION = 0x00000001', 'FLAG_AUTH_WRITE_URI_PERMISSION = 0x00000002'],
        '@ohos.bundle.bundleManager.d.ts': ['function getBundleInfoForSelfSync(bundleFlags: number): BundleInfo;'],
        '@ohos.util.d.ts': ['decodeToString(input: Uint8Array', 'encodeInto(input?: string): Uint8Array;'],
        '@ohos.process.d.ts': ['const uid: number;', 'const pid: number;'],
    }
    proof = {'metadata': record(metadata)}
    for name, tokens in required.items():
        path = sdk / 'ets/api' / name
        text = path.read_text()
        require(all(token in text for token in tokens), 'official declaration differs: ' + name)
        proof[name] = record(path)
    proof['ability_kit'] = record(sdk / 'ets/kits/@kit.AbilityKit.d.ts')
    device = sdk / 'ets/api/device-define/default.json'
    caps = set(json.loads(device.read_text())['SysCaps'])
    require({'SystemCapability.Ability.AbilityRuntime.Core', 'SystemCapability.FileManagement.File.FileIO'} <= caps,
            'SDK public Ability/FileIO capability missing')
    proof['device_default'] = record(device)
    return proof


def expected_sources(data, role, sdk):
    require(role in ROLES, 'exact role required')
    files = {}
    def put(name, value):
        files[name] = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    put('AppScope/app.json5', {'app': {'bundleName': ROLES[role]['bundle'], 'vendor': 'Harmony Contrib',
        'versionCode': 1, 'versionName': '1.0.0', 'icon': '$media:app_icon', 'label': '$string:app_name'}})
    put('AppScope/resources/base/element/string.json', {'string': [{'name': 'app_name', 'value': 'Share578 ' + role + ' ' + data['run_id']}]})
    put('AppScope/resources/base/media/app_icon.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#305C84"/></svg>\n')
    put('build-profile.json5', {'app': {'products': [{'name': 'default', 'compileSdkVersion': '26.0.0',
        'compatibleSdkVersion': '26.0.0', 'targetSdkVersion': '26.0.0', 'runtimeOS': 'OpenHarmony'}]},
        'modules': [{'name': 'entry', 'srcPath': './entry', 'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]})
    put('oh-package.json5', {'modelVersion': '6.0.0', 'name': 'share578-' + role, 'version': '1.0.0', 'dependencies': {}, 'devDependencies': {}})
    put('hvigor/hvigor-config.json5', {'modelVersion': '6.0.0', 'dependencies': {}, 'execution': {'daemon': False, 'parallel': False}})
    put('hvigorfile.ts', "import { appTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: appTasks, plugins: [] };\n")
    put('entry/hvigorfile.ts', "import { hapTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: hapTasks, plugins: [] };\n")
    put('entry/build-profile.json5', {'apiType': 'stageMode', 'targets': [{'name': 'default'}]})
    put('entry/oh-package.json5', {'name': 'entry', 'version': '1.0.0', 'dependencies': {}})
    put('local.properties', 'sdk.dir=' + str(Path(sdk).resolve().parent) + '\n')
    ability = {'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets',
        'launchType': 'singleton' if role == 'caller' else 'standard', 'exported': True,
        'label': '$string:app_name', 'icon': '$media:app_icon', 'startWindowIcon': '$media:app_icon',
        'startWindowBackground': '$color:background'}
    if role != 'caller':
        ability['skills'] = [{'actions': [CONTRACT['action']],
            'uris': [{'type': CONTRACT['mime']}, {'type': 'text/plain'}]}]
    put('entry/src/main/module.json5', {'module': {'name': 'entry', 'type': 'entry', 'mainElement': 'EntryAbility',
        'deviceTypes': ['default'], 'deliveryWithInstall': True, 'installationFree': False,
        'pages': '$profile:main_pages', 'requestPermissions': [], 'abilities': [ability]}})
    put('entry/src/main/resources/base/element/color.json', {'color': [{'name': 'background', 'value': '#FFFFFF'}]})
    put('entry/src/main/resources/base/profile/main_pages.json', {'src': ['pages/Index']})
    for name, target in [('EntryAbility.ets', 'entryability/EntryAbility.ets'), ('Index.ets', 'pages/Index.ets'), ('ShareAudit.ets', 'model/ShareAudit.ets'), ('MmsAudit.ets', 'model/MmsAudit.ets')]:
        put('entry/src/main/ets/' + target, (FIX / name).read_text().replace('__RUN__', data['run_id']).replace('__ROLE__', role))
    return files


def prepare(output, role, challenge_path, sdk):
    data = load_challenge(challenge_path); repository(data['source_commit'])
    proof = sdk_contract(sdk)
    output = Path(output).absolute()
    require(not output.exists() and output.parent.resolve() == output.parent and ROOT not in output.parents,
            'fresh canonical private source directory required')
    output.mkdir(parents=True)
    files = expected_sources(data, role, sdk)
    for name, text in files.items(): write(output / name, text)
    manifest = {'schema_version': 1, 'scope': 'ordinary share578 unsigned project only', 'run_id': data['run_id'],
        'source_commit': data['source_commit'], 'role': role, **ROLES[role], 'challenge': record(challenge_path),
        'sdk': proof, 'fixtures': fixtures(), 'source_tools': source_tools(),
        'source_files': {name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()},
        'signed': False, 'runtime_validated': False}
    write(output / 'share578-source-manifest.json', manifest)
    return output / 'share578-source-manifest.json'


def prepared(project, role, challenge_path):
    project = Path(project)
    require(project.is_absolute() and project.resolve() == project and project.is_dir(), 'canonical source project required')
    data = load_challenge(challenge_path)
    manifest = json.loads(regular(project / 'share578-source-manifest.json').read_text())
    require(role in ROLES and manifest.get('schema_version') == 1 and manifest.get('role') == role and
            manifest.get('run_id') == data['run_id'] and manifest.get('source_commit') == data['source_commit'] and
            manifest.get('challenge') == record(challenge_path) and all(manifest.get(k) == v for k, v in ROLES[role].items()) and
            manifest.get('fixtures') == fixtures() and manifest.get('source_tools') == source_tools() and
            manifest.get('signed') is False and manifest.get('runtime_validated') is False, 'exact prepared role/source required')
    sdk = checked(manifest['sdk']['metadata']).parent.parent
    require(manifest['sdk'] == sdk_contract(sdk), 'SDK105 metadata/declarations changed')
    files = expected_sources(data, role, sdk)
    hashes = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()}
    require(manifest['source_files'] == hashes, 'source inventory differs')
    for name, text in files.items(): require(regular(project / name).read_bytes() == text.encode(), 'source bytes differ: ' + name)
    for prefix in ('AppScope', 'entry/src/main', 'hvigor'):
        for p in (project / prefix).rglob('*'):
            if p.is_file() or p.is_symlink(): require(p.relative_to(project).as_posix() in hashes and not p.is_symlink(), 'unlisted/alias source input')
    hashes['share578-source-manifest.json'] = sha(project / 'share578-source-manifest.json')
    return manifest, hashes


def request(challenge_path, boot, archive_sha, case):
    data = load_challenge(challenge_path)
    require(BOOT.fullmatch(boot) and HEX.fullmatch(archive_sha) and case in list(CONTRACT['cases']) + list(CONTRACT['mms_cases']), 'actual boot/archive/case required')
    return {'schema_version': 1, 'run_id': data['run_id'], 'boot_id': boot, 'archive_sha256': archive_sha,
            'operation_id': secrets.token_hex(16), 'case_id': case, 'phase': 'run', 'kind': 'caller'}


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('challenge'); p.add_argument('--output', type=Path, required=True); p.add_argument('--commit', required=True)
    p = sub.add_parser('project')
    for name in ('output', 'challenge', 'sdk'): p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--role', choices=ROLES, required=True)
    p = sub.add_parser('request'); p.add_argument('--challenge', type=Path, required=True)
    for name in ('boot', 'archive-sha', 'case'): p.add_argument('--' + name, required=True)
    args = parser.parse_args()
    if args.mode == 'challenge': print(challenge(args.output, args.commit))
    elif args.mode == 'project': print(prepare(args.output, args.role, args.challenge, args.sdk))
    else: print(json.dumps(request(args.challenge, args.boot, args.archive_sha, args.case), separators=(',', ':')))


if __name__ == '__main__': main()
