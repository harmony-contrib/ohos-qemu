"""Root-supplied callbacks only; retained observations, never a resource owner.

No executable CLI, process creation, SDK, signing, permission grant or generic
database deletion. Missing actual device field mappings remain pending.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import types
import math
import stat
import zipfile
import shlex
import napi_protocol411 as napi411

GET = 'ohos.permission.GET_TELEPHONY_STATE'
SET = 'ohos.permission.SET_TELEPHONY_STATE'
ROLES = {
    'system-granted': ('org.harmonycontrib.numberlocal376.systemgranted', True, 0, 0),
    'system-readonly': ('org.harmonycontrib.numberlocal376.systemreadonly', True, 0, -1),
    'ordinary': ('org.harmonycontrib.numberlocal376.ordinary', False, -1, -1),
}
VERIFIER = 'root-number-local375-review02/verify_caller_journal.py'
VERIFIER_SHA = '8f7d76866c07e81487871929f5d9c067e7bc2ca98de650ca1929a84ee087f545'
SOURCE_SHA = {
    'common_errors_sha256': 'df8da91d96d16d2aaca88cb6d07b4124c07624587ce824cdc3ac7a7f0ce5476e',
    'number_errors_sha256': '616363b7a3708d9060373583e18fbc936c41ea7ea151558314df48b281a7b6a3',
    'mark_source_sha256': '781f7bb3b699ee933d32f1c9c790bcc4c9824a8375c5c5e1ac1472f273d52bb8',
}
# Host seed candidate only. Matching target source/compile-dependency proof is
# required separately; these constants do not establish Docker/target identity.
PERMISSION_ERROR = ((40 << 21) | (0x21 << 16)) + 8
TOKEN_FIELDS = set(('schema scope run phase role bundle uid accessTokenId systemApp getPermission '
    'setPermission getResult setResult expectedGet expectedSet expectedSystemApp status operation '
    'errorCode error time actualIdentityProven firstArtifactGatePassed aggregateProviderPassed').split())


class Pending(ValueError):
    pass


def need(value, message):
    if not value:
        raise ValueError(message)


def decode(raw):
    def unique(rows):
        result = {}
        for key, value in rows:
            need(key not in result, 'duplicate JSON field'); result[key] = value
        return result
    need(type(raw) is bytes and 0 < len(raw) <= 16 * 1024 * 1024, 'bounded actual JSON bytes required')
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def record(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and path.is_file() and
         all(not p.is_symlink() for p in (path, *path.parents)), 'canonical real evidence required')
    raw = path.read_bytes()
    return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def checked(row):
    need(type(row) is dict and {'path', 'sha256'} <= row.keys(), 'actual evidence descriptor required')
    actual = record(row['path'])
    need(actual['sha256'] == row['sha256'] and ('bytes' not in row or
         type(row['bytes']) is int and row['bytes'] == actual['bytes']), 'evidence descriptor changed')
    return Path(actual['path'])


def selected(raw, fields, names):
    if type(fields) is not dict or set(fields) != set(names) or any(fields[k] is None for k in names):
        raise Pending('actual raw JSON field selectors pending: ' + ','.join(names))
    result = {}; source = decode(raw)
    for name in names:
        value = source; route = fields[name]
        need(type(route) is list and route, 'explicit raw field path required')
        for key in route:
            need(type(key) in (str, int) and type(key) is not bool, 'raw selector key required')
            value = value[key]
        result[name] = value
    return result


def material(spec, names):
    if spec is None:
        raise Pending('actual root evidence/mapping not supplied')
    return selected(checked(spec['record']).read_bytes(), spec.get('fields'), names)


VM_FIELDS = ('purpose', 'qemu_pid', 'qemu_start_ticks', 'writable_image', 'image_dev',
             'image_inode', 'lease_held', 'package_sha256', 'hdc_target')


def vm_identity(spec, archive_sha):
    row = material(spec, VM_FIELDS)
    need(row['purpose'] == 'number-only' and row['lease_held'] is True and
         row['package_sha256'] == archive_sha, 'dedicated held Number VM/new package required; no suite VM')
    for name in ('qemu_pid', 'qemu_start_ticks', 'image_dev', 'image_inode'):
        need(type(row[name]) is int and row[name] > 0, 'actual QEMU/image identity required: ' + name)
    guest_path(row['writable_image'])
    need(type(row['hdc_target']) is str and row['hdc_target'] and not any(c.isspace() for c in row['hdc_target']),
         'actual dedicated guest HDC target required')
    return row


def reboot_join(before, after, first_boot, second_boot):
    need(before == after and before['lease_held'] is True and before['purpose'] == 'number-only',
         'same held QEMU incarnation and writable image identity required across controlled reboot')
    need(first_boot != second_boot, 'a different actual guest boot_id is required')


def guest_path(value):
    need(type(value) is str and value.startswith('/') and
         str(PurePosixPath(value)) == value and '..' not in PurePosixPath(value).parts and
         not any(c.isspace() for c in value), 'explicit canonical guest path required')
    return value


def token_join(raw, role, run, phase, bms, access):
    row = decode(raw); bundle, system, get, set_ = ROLES[role]
    need(type(row) is dict and set(row) == TOKEN_FIELDS and
         row['schema'] == 'number-local377-token-observation/v1' and
         row['scope'] == 'self_observation_only_requires_independent_BMS_signature_join' and
         (row['run'], row['phase'], row['role'], row['bundle']) == (run, phase, role, bundle),
         'exact Token377 role/challenge/schema required')
    need(all(row[k] is False for k in ('actualIdentityProven', 'firstArtifactGatePassed', 'aggregateProviderPassed')),
         'self report cannot promote identity/runtime gates')
    for key in ('uid', 'accessTokenId', 'getResult', 'setResult', 'expectedGet', 'expectedSet', 'errorCode', 'time'):
        need(type(row[key]) is int, 'typed Token377 integer required: ' + key)
    need(row['uid'] > 0 and row['accessTokenId'] > 0 and row['time'] > 0 and
         row['systemApp'] is system and row['expectedSystemApp'] is system and
         (row['getResult'], row['setResult'], row['expectedGet'], row['expectedSet']) == (get, set_, get, set_) and
         row['getPermission'] == GET and row['setPermission'] == SET and
         row['status'] == 'observed_expected_role_only' and row['errorCode'] == 0 and row['error'] == '' and
         row['operation'] == 'checkAccessTokenSync.SET_TELEPHONY_STATE', 'actual Token377 role result mismatch')
    need(all(type(bms[k]) is int for k in ('uid', 'token')) and
         all(type(access[k]) is int for k in ('token', 'getResult', 'setResult')) and
         type(bms['systemApp']) is bool, 'typed independent BMS/token observations required')
    need((bms['bundle'], bms['uid'], bms['token'], bms['systemApp']) ==
         (bundle, row['uid'], row['accessTokenId'], system) and
         (access['bundle'], access['token'], access['getResult'], access['setResult']) ==
         (bundle, row['accessTokenId'], get, set_), 'independent actual BMS/UID/token/GET/SET join differs')
    return dict(bundle=bundle, uid=row['uid'], token=row['accessTokenId'], systemApp=system,
                getResult=get, setResult=set_, scope='actual_BMS_UID_and_token_bound_query_join; query_has_no_UID')


def permission_source(spec, commit):
    proof = material(spec, (*SOURCE_SHA, 'source_commit'))
    need(proof['source_commit'] == commit and all(proof[k] == v for k, v in SOURCE_SHA.items()),
         'actual target source export/compile dependency identity differs from candidate sources')
    return PERMISSION_ERROR


SDK_SCHEMA = 'number-local411-actual-SDK/v1'
SDK_DRIVER_SHA = '041cdf3ad97a16336cab858a3e515ac0e808cf817631355164708719ad488d69'
NAPI_MANIFEST_SHA = '942d4cfd8dc6777f36e5462ae16739366691e6efbd4dc3a87285a0198ffc2fa1'
CALLER_MANIFEST_SHA = '26c1ad1612ba3b1919242dce976215d55f176fe05832b8beaaffa5ea9b62987e'
TOKEN_MANIFEST_SHA = '1c4c3f02b9310bd218f40fd62da88ccda009001532897b3908fd11d3fcca8ee6'
CPU_CAP_SHA = '3807e82d9e777a81e4ff3eb683d0f3fad807533e4e0c0dff1d73ad3f909abe62'
ACCESS_CTRL_SHA = '13a80a514850e33572ae463f6852c9951fad03e97be616be1ea45c76f5093758'
NODE = '/Volumes/PSSD/qemu/openharmony/prebuilts/build-tools/common/nodejs/node-v18.20.1-darwin-arm64/bin/node'
CLI = '/Volumes/PSSD/qemu/openharmony/prebuilts/tool/command-line-tools'
ADMISSION_TOOLS = {
    'node': (NODE, 'b98965e9a1cb8efffde21f63d360d5e99d6ef1b0b826dad922c1554d5c86e644'),
    'ohpm': (CLI + '/ohpm/bin/pm-cli.js', '55e585b3706790bc2a2b1e98ae375fc999113f8ad9a108aa1b10ed6c27a6effb'),
    'hvigor': (CLI + '/6.x/hvigor/bin/hvigorw.js', '11798a97fd537d2cf8bdea90f66dbf650cbeefd328493bf2f552f2fae75e6911'),
}
SDK_SHAS = {'metadata': '250b53f383be634ada496cfb4a1cbebd1e7ad6f14f44fd136ca55d2d9a35acab', 'application/UIAbilityContext.d.ts': 'd23c784fccf8f8eacdf3023a2db2a835bd8a68742670a154fb02eb3beae39f49', 'application/Context.d.ts': '9dfb180ce3aa01ba778c201f6742f6e9355e96545c3cddae654b14f802e28161', '@ohos.app.ability.common.d.ts': '581aef56e1d9a3fb7f4d86e9d26a35dc1ccdae9e3198c069feeb589c5b1710a5', '@ohos.app.ability.Want.d.ts': '01fe0cb09dec5add50713939b915c4170dd04ada26cd3614718f0591a687f1bc', '@ohos.file.fileuri.d.ts': 'ab53a9664ac62ace44096a551cb7f4210cd4083206302d91f709515dd3f48937', '@ohos.file.fs.d.ts': 'c5e016e71c327437ab39af63df7f1d0651edf8aa38456e10c07916a486cf50a0', '@ohos.app.ability.wantConstant.d.ts': 'a582881ec0c896069e804ca9ca267f049c8ee6659b1d57bdbeecaaac3a466466', '@ohos.bundle.bundleManager.d.ts': '9eb16dc9d886672b8f7add1ae74cc2272f32ab1cfff642bdadbb8b5883e24e21', '@ohos.util.d.ts': '4e9e3fab06f332635126f0235a282caf9bee4501175c0e45e51e00fb7d411677', '@ohos.process.d.ts': '874cb85465d52631024ab710b364c275aff4c844fabfb38bd27c06ca0e2b5bd2', 'ability_kit': '0570bdd14f3095c8a15a2b6e33f951fcb9c080fe4d1f9af2fbac7e5f5dc0254a', 'device_default': '9fc6cd7512b7fdf772a18796e6ddf8ed094599b4042d0d25141ba75e0f2c13cf'}
PROJECT_FILES = frozenset(('AppScope/app.json5', 'AppScope/resources/base/element/string.json', 'AppScope/resources/base/media/app_icon.svg', 'build-profile.json5', 'oh-package.json5', 'hvigor/hvigor-config.json5', 'hvigorfile.ts', 'entry/hvigorfile.ts', 'entry/build-profile.json5', 'entry/oh-package.json5', 'local.properties', 'entry/src/main/module.json5', 'entry/src/main/resources/base/element/color.json', 'entry/src/main/resources/base/profile/main_pages.json', 'entry/src/main/ets/entryability/EntryAbility.ets', 'entry/src/main/ets/entryability/NumberLocalProbe.ets', 'entry/src/main/ets/entryability/TokenObservation.ets'))
PROJECT_FILES = PROJECT_FILES | frozenset('entry/src/main/ets/entryability/' + name for name in ('LegacyNapiNumberProbe.js','LegacyNapiNumberProbe.d.ts','NapiProbe411.ets','NapiToken411.ets'))


def sdk_role_artifacts(item, role, commit):
    """Replay the real Number SDK schema; no synthetic haps compatibility view."""
    materials = {}
    def source(descriptor):
        path = checked(descriptor)
        materials[str(path)] = record(path)
        return path
    def parsed(descriptor):
        return decode(source(descriptor).read_bytes())
    evidence = parsed(item['sdk_evidence'])
    need(type(commit) is str and re.fullmatch('[0-9a-f]{40}', commit) and
         evidence.get('schema') == SDK_SCHEMA and evidence.get('source_commit') == commit and
         type(evidence.get('exit_code')) is int and evidence['exit_code'] == 0 and
         evidence.get('failures') == [] and evidence.get('signed') is False and
         evidence.get('guest_executed') is False and
         evidence.get('first_artifact_behavior_gate_passed') is False,
         'actual Number SDK schema/source/complete compile required')
    source(evidence['driver'])
    need(evidence['driver']['sha256'] == SDK_DRIVER_SHA, 'reviewed Number SDK driver required')
    # The closed receipt includes a large cache inventory. Parse it with an
    # explicit bound, consuming only its actual source/SDK/tool admission;
    # none of its fields is accepted as resource ownership or runtime success.
    admission_raw = source(evidence['input_admission']).read_bytes()
    need(0 < len(admission_raw) <= 64 * 1024 * 1024, 'bounded actual SDK admission required')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            need(key not in value, 'duplicate SDK admission field')
            value[key] = item
        return value
    admission = json.loads(admission_raw, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite SDK admission')))
    need(admission['schema'] == 'F-SDK-batch29-input-admission/v1' and
         admission['source_commit'] == commit and admission['status'] == 'input_admitted' and
         type(admission['exit_code']) is int and admission['exit_code'] == 0 and
         admission['failures'] == [] and all(admission[k] is False for k in
             ('sdk_started', 'docker_started', 'resource_commands_started')),
         'actual SDK pre-launch source/input admission differs')
    for name, (literal, digest) in ADMISSION_TOOLS.items():
        tool = admission['tools'][name]
        need(tool['requested'] == tool['resolved'] == literal and tool['sha256'] == digest,
             'reviewed actual SDK executor input differs: ' + name)
    caller = parsed(evidence['caller_manifest']); supplement = parsed(evidence['token_supplement'])
    need(evidence['caller_manifest']['sha256'] == CALLER_MANIFEST_SHA and
         evidence['token_supplement']['sha256'] == TOKEN_MANIFEST_SHA,
         'reviewed Number caller and Token377 manifest pins required')
    sdk = evidence['sdk']
    need(type(sdk) is dict and set(sdk) == set(SDK_SHAS), 'complete actual SDK declaration set required')
    for name, digest in SDK_SHAS.items():
        need(sdk[name]['sha256'] == digest, 'reviewed SDK105 input differs: ' + name)
        source(sdk[name])
    meta = parsed(sdk['metadata'])
    need((meta['apiVersion'], meta['version'], meta['platformVersion'], meta['releaseType']) ==
         ('26', '26.0.0.105', '26.0.0', 'Release'), 'actual SDK105 metadata required')
    ets = admission['metadata']['ets']
    need(ets['requested'] == sdk['metadata']['path'] and
         ets['sha256'] == sdk['metadata']['sha256'] and ets['value'] == meta,
         'SDK admission metadata differs from compile source manifest')
    access = admission['declarations']['@ohos.abilityAccessCtrl.d.ts']
    need(access['sha256'] == ACCESS_CTRL_SHA and access['requested'] ==
         str(Path(sdk['metadata']['path']).parent / 'api/@ohos.abilityAccessCtrl.d.ts'),
         'actual Token377 AccessToken declaration differs')
    source(dict(path=access['requested'], sha256=access['sha256'], bytes=access['bytes']))
    def frozen(manifest, descriptor, relative):
        files = manifest['files']
        if type(files) is list:
            rows = [row for row in files if row['path'] == relative]
            need(len(rows) == 1, 'unique frozen caller source required')
            row = rows[0]
        else:
            need(type(files) is dict and relative in files, 'frozen Token377 source required')
            row = files[relative]
        path = str(Path(descriptor['path']).parent / relative)
        return source(dict(path=path, sha256=row['sha256'], bytes=row['bytes'])).read_bytes()
    napi = parsed(evidence['napi_supplement'])
    need(evidence['napi_supplement']['sha256'] == NAPI_MANIFEST_SHA and
         napi['schema'] == 'number411-fixed-source-extension/v1', 'exact reviewed NAPI source extension required')
    napi_sources = {name: frozen(napi, evidence['napi_supplement'], 'caller/' + name) for name in
        ('EntryAbility.ets','LegacyNapiNumberProbe.js','LegacyNapiNumberProbe.d.ts','NapiProbe411.ets','NapiToken411.ets')}
    frozen(napi, evidence['napi_supplement'], 'project411.py')
    probe = frozen(caller, evidence['caller_manifest'], 'caller/NumberLocalProbe.ets')
    token_sources = {name: frozen(supplement, evidence['token_supplement'],
        'candidate/caller/entry/src/main/ets/entryability/' + name)
        for name in ('EntryAbility.ets', 'TokenObservation.ets')}
    rows = evidence['roles']
    need(type(rows) is list and len(rows) == 3 and
         [row.get('role') for row in rows] == list(ROLES), 'exact three Number SDK roles required')
    roots = {}; selected_role = None
    for row in rows:
        need(set(row) == {'role', 'bundle', 'exit_code', 'source_manifest', 'unsigned_hap', 'permissions'},
             'actual Number SDK role record shape required')
        name = row['role']; bundle, system, get, set_ = ROLES[name]
        permissions = [p for p, value in [(GET, get), (SET, set_)] if value == 0]
        need(type(row['exit_code']) is int and row['exit_code'] == 0 and
             row['bundle'] == bundle and row['permissions'] == permissions,
             'compiled Number SDK role/bundle/permission differs')
        root = Path(row['source_manifest']['path']).parent; roots[name] = root
        manifest = parsed(row['source_manifest'])
        need(manifest['source_commit'] == commit and manifest['role'] == name and
             manifest['caller_manifest'] == evidence['caller_manifest'] and
             manifest['token_supplement'] == evidence['token_supplement'] and manifest['napi_supplement'] == evidence['napi_supplement'] and manifest['sdk'] == sdk and
             type(manifest['files_sha256']) is dict and set(manifest['files_sha256']) == PROJECT_FILES,
             'actual Number project/source/SDK lineage differs')
        project = {}
        for relative, digest in manifest['files_sha256'].items():
            need(str(PurePosixPath(relative)) == relative and not relative.startswith('/') and
                 '..' not in PurePosixPath(relative).parts, 'canonical SDK project source required')
            project[relative] = source(dict(path=str(root / relative), sha256=digest)).read_bytes()
        token_sources['EntryAbility.ets'] = napi_sources['EntryAbility.ets']
        for filename, expected in dict(token_sources, **{'NumberLocalProbe.ets': probe}, **napi_sources).items():
            need(project['entry/src/main/ets/entryability/' + filename] == expected,
                 'actual compiled caller/Token377 source differs')
        original_module = decode(frozen(caller, evidence['caller_manifest'], 'caller/' + name + '.module.json5'))
        original_module['module']['deviceTypes'] = ['default']
        original_module['module']['abilities'][0].update(label='$string:app_name', icon='$media:app_icon',
            startWindowIcon='$media:app_icon', startWindowBackground='$color:background')
        need(decode(project['entry/src/main/module.json5']) == original_module and
             decode(project['AppScope/app.json5'])['app']['bundleName'] == bundle,
             'compiled source bundle/module/permissions differs from reviewed caller')
        hap = source(row['unsigned_hap'])
        with zipfile.ZipFile(hap) as archive:
            members = archive.infolist(); names = [m.filename for m in members]
            need(len(names) == len(set(names)) and all(not n.startswith('/') and
                 '..' not in PurePosixPath(n).parts and str(PurePosixPath(n)) == n for n in names) and
                 all(stat.S_IFMT(m.external_attr >> 16) != stat.S_IFLNK for m in members),
                 'safe unique actual unsigned HAP members required')
            need('module.json' in names and 'ets/modules.abc' in names and
                 0 < archive.getinfo('module.json').file_size < 1024 * 1024 and
                 archive.getinfo('ets/modules.abc').file_size > 0, 'actual compiled HAP/ABC required')
            module = decode(archive.read('module.json'))
        app, entry = module['app'], module['module']
        need(app['bundleName'] == bundle and app['debug'] is False and
             (app['compileSdkVersion'], app['minAPIVersion'], app['targetAPIVersion']) ==
             ('26.0.0.105', 26, 26) and entry['name'] == 'entry' and entry['type'] == 'entry' and
             entry['deviceTypes'] == ['default'] and entry['mainElement'] == 'EntryAbility' and
             entry.get('extensionAbilities', []) == [] and
             entry.get('requestPermissions', []) == [{'name': p} for p in permissions] and
             len(entry['abilities']) == 1 and entry['abilities'][0]['name'] == 'EntryAbility' and
             entry['abilities'][0]['exported'] is True and
             entry['abilities'][0]['srcEntry'] == './ets/entryability/EntryAbility.ets',
             'actual compiled HAP role/API/entry/permission contract differs')
        if name == role:
            need(all(row['unsigned_hap'][k] == item['unsigned_hap'][k] for k in ('path', 'sha256')),
                 'selected unsigned HAP is not this actual SDK role output')
            selected_role = row
    sdk_root = Path(item['sdk_evidence']['path']).parent
    need(all(roots[name] == sdk_root / name for name in ROLES), 'SDK output/source roots differ')
    cpu = sdk_root / 'cpu-cap.cjs'; source(dict(path=str(cpu), sha256=CPU_CAP_SHA))
    commands = evidence['commands']; labels = [(name, phase) for name in ROLES
                                              for phase in ('dependencies', 'compile')]
    need(type(commands) is list and len(commands) == 6, 'six actual serial SDK commands required')
    previous_end = None
    for command, (name, phase) in zip(commands, labels):
        tail = ([CLI + '/ohpm/bin/pm-cli.js', 'install', '--all', '--registry',
                 'http://127.0.0.1:9', '--fetch_timeout', '10000', '--retry_times', '0']
                if phase == 'dependencies' else [CLI + '/6.x/hvigor/bin/hvigorw.js', 'assembleHap',
                '--mode', 'module', '-p', 'product=default', '-p', 'module=entry', '-p',
                'debuggable=false', '-p', 'hvigor-obfuscation=false', '--no-daemon', '--no-parallel',
                '--no-incremental', '--max-old-space-size', '2048'])
        need(command['argv'] == [NODE, '--max-old-space-size=2048', '--require', str(cpu), *tail] and
             command['label'] == name + '-' + phase and command['project'] == name and
             command['cwd'] == str(roots[name]) and type(command['exit_code']) is int and
             command['exit_code'] == 0 and command['timed_out'] is False and
             command['owned_outer_leader_reaped'] is True and
             all(type(command[k]) is int and command[k] > 0 for k in ('owned_pid', 'owned_initial_pgid')),
             'actual fixed serial SDK argv/exit/owned completion differs')
        start, seconds = command['started_monotonic'], command['seconds']
        need(all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in (start, seconds)) and
             (previous_end is None or start >= previous_end), 'actual SDK command ordering differs')
        previous_end = start + seconds
        need(command['log'] == str(sdk_root / (name + '-' + phase + '.log')), 'actual SDK command log path differs')
        log = source(dict(path=command['log'], sha256=command['sha256'])).read_bytes()
        if phase == 'compile':
            need(b'BUILD SUCCESSFUL' in log and b'BUILD FAILED' not in log, 'actual Hvigor success log required')
    need(selected_role is not None, 'selected actual SDK role missing')
    return dict(scope='actual_SDK_source_chain_ONLY_NOT_signature_install_or_runtime', source_commit=commit,
                role=role, unsigned_hap=selected_role['unsigned_hap'],
                source_manifest=selected_role['source_manifest'], sdk_evidence=item['sdk_evidence'],
                materials=list(materials.values()), guest_executed=False,
                first_artifact_behavior_gate_passed=False)


def bms_document(raw, bundle):
    """Accept bare JSON or only the exact actual expected-bundle heading."""
    need(type(bundle) is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]*', bundle),
         'explicit expected BMS bundle required')
    need(type(raw) is bytes and 0 < len(raw) <= 16 * 1024 * 1024, 'bounded raw BMS bytes required')
    body = raw
    if not body.lstrip(b' \t\r\n').startswith(b'{'):
        prefix = bundle.encode('ascii') + b':'
        if body.startswith(prefix + b'\r\n'):
            body = body[len(prefix) + 2:]
        elif body.startswith(prefix + b'\n'):
            body = body[len(prefix) + 1:]
        else:
            raise ValueError('exact expected-bundle BMS heading required')
    value = decode(body)
    need(type(value) is dict and value.get('name') == bundle and
         type(value.get('applicationInfo')) is dict and
         value['applicationInfo'].get('bundleName') == bundle,
         'BMS root/application bundle identity differs')
    return value


def entry_hap_path(document, bundle):
    need(document.get('name') == bundle and document['applicationInfo'].get('bundleName') == bundle,
         'entry HAP must belong to exact BMS bundle')
    modules = document.get('hapModuleInfos')
    need(type(modules) is list and modules, 'actual BMS HAP module records required')
    entries = []
    for module in modules:
        need(type(module) is dict and module.get('bundleName') == bundle,
             'foreign or malformed BMS module record')
        if module.get('moduleName') == 'entry' or module.get('name') == 'entry':
            need(module.get('moduleName') == module.get('name') == 'entry' and
                 module.get('mainElementName') == 'EntryAbility', 'conflicting BMS entry module identity')
            entries.append(module)
    need(len(entries) == 1, 'unique exact bundle/entry HAP required')
    path = guest_path(entries[0].get('hapPath'))
    need(re.fullmatch(r'/[A-Za-z0-9_./-]+\.hap', path) is not None,
         'canonical actual entry HAP file path required')
    return path


def bms_fields(raw, bundle, fields):
    document = bms_document(raw, bundle)
    installed_hap = entry_hap_path(document, bundle)
    names = ('bundle', 'uid', 'token', 'systemApp')
    if type(fields) is not dict or set(fields) != set(names) or any(fields[k] is None for k in names):
        raise Pending('actual raw BMS field selectors pending: ' + ','.join(names))
    result = {}
    for name in names:
        value = document; route = fields[name]
        need(type(route) is list and route, 'explicit actual BMS field path required')
        for key in route:
            need(type(key) in (str, int) and type(key) is not bool, 'actual BMS selector key required')
            value = value[key]
        result[name] = value
    # This is an internal derived selection from the retained actual module
    # record, not a fabricated applicationInfo.codePath/filesDir field.
    result['installedHapPath'] = installed_hap
    return result


TOKEN_QUERY = '/data/local/tmp/number-token395'


def query_access(raw, role, run, phase, boot, bms):
    row = decode(raw)
    fields = {'schema', 'api', 'run', 'phase', 'boot_id', 'bundle_name', 'token_id',
              'user_id', 'inst_index', 'GET_TELEPHONY_STATE', 'SET_TELEPHONY_STATE'}
    need(type(row) is dict and set(row) == fields and
         row['schema'] == 'number-token395-readonly/v1' and row['api'] == 'AccessTokenKit::VerifyAccessToken' and
         (row['run'], row['phase'], row['boot_id'], row['bundle_name']) == (run, phase, boot, ROLES[role][0]),
         'exact independent Number query run/phase/boot/bundle required')
    need(all(type(row[k]) is int for k in ('token_id', 'user_id', 'inst_index', 'GET_TELEPHONY_STATE', 'SET_TELEPHONY_STATE')) and
         row['token_id'] == bms['token'] and row['user_id'] == 100 and row['inst_index'] == 0 and
         (row['GET_TELEPHONY_STATE'], row['SET_TELEPHONY_STATE']) == ROLES[role][2:],
         'actual independent token/GET/SET result differs')
    # Deliberately no UID field. UID authority is separately BMS + Token377.
    return dict(bundle=row['bundle_name'], token=row['token_id'],
                getResult=row['GET_TELEPHONY_STATE'], setResult=row['SET_TELEPHONY_STATE'])


def phase_names(run, phase):
    need(re.fullmatch('[a-f0-9]{32}', run) and phase in
         ('cycle', 'prepare-persist', 'verify-persist', 'system-denied', 'ordinary-denied'), 'finite phase file names required')
    return ('number-local375-' + run + '-' + phase + '.jsonl',
            'number-token377-' + run + '-' + phase + '.json')


def find_script(run, phase):
    journal, token = phase_names(run, phase)
    return 'find /data -type f \\( -name ' + shlex.quote(journal) + ' -o -name ' + shlex.quote(token) + ' \\) -print'


def discovered_files(raw, run, phase):
    need(type(raw) is bytes and 0 < len(raw) <= 65536, 'bounded actual find output required')
    names = phase_names(run, phase); result = {}
    lines = raw.decode('ascii').splitlines()
    need(len(lines) == 2 and len(set(lines)) == 2, 'exactly two unique actual run/phase file hits required')
    for path in lines:
        guest_path(path)
        need(path.startswith('/data/') and re.fullmatch(r'/[A-Za-z0-9_./+-]+', path), 'safe actual /data file path required')
        basename = PurePosixPath(path).name
        need(basename in names and basename not in result, 'duplicate/foreign actual run/phase file hit')
        result[basename] = path
    need(set(result) == set(names) and len({str(PurePosixPath(p).parent) for p in result.values()}) == 1,
         'actual journal/Token must share one observed directory')
    return tuple(result[name] for name in names)


def stat_script(path, *, process_root=False):
    guest_path(path); quoted = shlex.quote(path)
    parents = [] if process_root else list(reversed(PurePosixPath(path).parents))
    prefix = ''.join('test ! -L ' + shlex.quote(str(p)) + ' && ' for p in parents)
    return prefix + 'test -f ' + quoted + ' && test ! -L ' + quoted + \
           " && stat -c '%u %g %a %s %d %i %h' " + quoted + ' && sha256sum ' + quoted


def file_stat(raw, path, uid):
    need(type(raw) is bytes and len(raw) <= 65536, 'bounded actual stat/hash raw required')
    lines = raw.decode('ascii').splitlines()
    need(len(lines) == 2 and re.fullmatch(r'[0-9]+ [0-9]+ [0-7]{3,4} [0-9]+ [0-9]+ [0-9]+ [0-9]+', lines[0]),
         'exact actual file stat grammar required')
    text = lines[0].split(); values = [int(v, 8 if i == 2 else 10) for i, v in enumerate(text)]
    need(type(uid) is int and uid > 0 and values[0] == uid and 0 < values[3] <= 1048576 and
         values[4] > 0 and values[5] > 0 and values[6] == 1,
         'actual file UID/size/device/inode/nonalias differs')
    match = re.fullmatch(r'([a-f0-9]{64}) [ *](.+)', lines[1])
    need(match is not None and match[2] == path, 'actual file hash/path differs')
    return dict(uid=values[0], gid=values[1], mode=values[2], bytes=values[3],
                dev=values[4], inode=values[5], nlink=values[6], sha256=match[1])


def logged_context(calls, run, phase):
    found = set()
    for call in calls:
        for line in call['stdout'].decode('utf-8').splitlines():
            if 'NUMBER_LOCAL375 ' not in line:
                continue
            try: row = decode(line.split('NUMBER_LOCAL375 ', 1)[1].encode())
            except ValueError: continue
            if (row.get('run'), row.get('phase'), row.get('event')) == (run, phase, 'begin'):
                found.add(row['detail'])
    need(len(found) == 1, 'one actual fresh run/phase D2 begin context log required')
    context = found.pop(); guest_path(context)
    need(re.fullmatch(r'/[A-Za-z0-9_./+-]+', context), 'safe actual context.filesDir log required')
    return context


def process_identity(pid, status, cmdline, process_stat, bundle, uid):
    need(re.fullmatch('[1-9][0-9]*', pid), 'one actual PID required')
    need(cmdline.split(b'\0')[0] == bundle.encode() and all(not p for p in cmdline.split(b'\0')[1:]),
         'actual process cmdline is not this Number role')
    matches = re.findall(rb'(?m)^Uid:[ \t]+([0-9]+)[ \t]+([0-9]+)[ \t]+([0-9]+)[ \t]+([0-9]+)[ \t]*\r?$', status)
    need(type(uid) is int and uid > 0 and len(matches) == 1 and all(int(p) == uid for p in matches[0]),
         'one actual process UID observation must match BMS')
    raw = process_stat.decode('ascii').strip()
    need(raw.startswith(pid + ' (') and ')' in raw, 'actual proc stat PID differs')
    rest = raw.rsplit(')', 1)[1].split()
    need(len(rest) >= 20 and rest[19].isdigit() and int(rest[19]) > 0, 'actual process kernel start ticks required')
    return dict(pid=int(pid), uid=uid, start_ticks=int(rest[19]), bundle=bundle)


def identity395(self, role, phase='identity'):
    item = self.spec['roles'][role]; bundle, system, get, set_ = ROLES[role]
    if item.get('bms') is None or item['bms'].get('argv') is None:
        raise Pending('actual read-only BMS raw field mappings pending')
    need(item['bms']['argv'] == ['bm', 'dump', '-n', bundle], 'exact independent BMS command required')
    before_boot = self.boot()
    before = bms_fields(self.shell(item['bms']['argv']), bundle, item['bms'].get('fields'))
    need(before['bundle'] == bundle and before['systemApp'] is system and
         type(before['uid']) is int and before['uid'] > 0 and type(before['token']) is int and before['token'] > 0,
         'typed real BMS role identity required')
    raw = self.shell([TOKEN_QUERY, self.spec['runs'][role], phase, bundle, str(before['token'])])
    access = query_access(raw, role, self.spec['runs'][role], phase, before_boot, before)
    after = bms_fields(self.shell(item['bms']['argv']), bundle, item['bms'].get('fields'))
    need(before == after and self.boot() == before_boot, 'BMS UID/token/install/system identity or boot changed around permission query')
    path = before['installedHapPath']; guest_path(path)
    code = self.shell(['sha256sum', path]).decode('utf-8').strip().split()
    need(len(code) == 2 and code[0] == item['signed_hap']['sha256'] and code[1] == path,
         'actual installed HAP differs from authenticated signed role')
    return before, access


def mapped_context395(self, role, context, paths, stats):
    directory = str(PurePosixPath(paths[0]).parent)
    if context == directory:
        return dict(kind='same_actual_root_and_context_directory', directory=directory)
    bundle = ROLES[role][0]; uid = stats[0]['uid']
    pid = self.shell(['pidof', bundle]).decode('ascii').strip()
    need(re.fullmatch('[1-9][0-9]*', pid), 'namespace mapping needs exactly one actual Number role PID; no guessed PID')
    def incarnation():
        return process_identity(pid, self.shell(['cat', '/proc/' + pid + '/status']),
            self.shell(['cat', '/proc/' + pid + '/cmdline']), self.shell(['cat', '/proc/' + pid + '/stat']), bundle, uid)
    before = incarnation(); observations = []
    for path, expected in zip(paths, stats):
        observed = '/proc/' + pid + '/root' + context + '/' + PurePosixPath(path).name
        actual = file_stat(self.shell([stat_script(observed, process_root=True)]), observed, uid)
        need(actual == expected, 'actual process-root context file is not the independently found root file inode/hash')
        observations.append(dict(path=observed, stat=actual))
    need(incarnation() == before, 'Number process incarnation changed while observing namespace mapping')
    return dict(kind='actual_process_root_file_inode_mapping', process=before,
                context=context, directory=directory, observations=observations)


class Collector:
    def __init__(self, spec, callbacks, output, here):
        self.spec, self.callbacks = spec, callbacks
        need(set(callbacks) == {'shell', 'pull', 'ui', 'controlled_reboot'} and
             all(callable(v) for v in callbacks.values()), 'only four root-owned real callbacks required')
        self.output = Path(output)
        need(self.output.is_absolute() and self.output.resolve() == self.output and
             not self.output.exists(), 'fresh canonical private collector output required')
        self.output.mkdir(); self.calls = []; self.phases = []; self.materials = []; self.napi_phases = []
        path = Path(here) / VERIFIER
        need(record(path)['sha256'] == VERIFIER_SHA, 'original D2 journal verifier changed')
        source = path.read_bytes()
        need(hashlib.sha256(source).hexdigest() == VERIFIER_SHA, 'D2 verifier changed during source read')
        self.journal = types.ModuleType('original_number_journal_d2')
        self.journal.__file__ = str(path)
        exec(compile(source, str(path), 'exec'), self.journal.__dict__)

    def save(self, name, value):
        path = self.output / name
        with path.open('x') as stream: json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')
        return record(path)

    def observed(self, kind, requested, actual):
        need(type(actual) is dict and set(actual) == {'argv', 'exit_code', 'stdout', 'stderr'} and
             type(actual['argv']) is list and actual['argv'] and all(type(x) is str for x in actual['argv']) and
             type(actual['exit_code']) is int and all(type(actual[k]) is bytes for k in ('stdout', 'stderr')),
             'root callback must return actual argv/int exit/raw bytes, including failures')
        index = len(self.calls); item = dict(kind=kind, requested=requested,
            argv=actual['argv'], exit_code=actual['exit_code'])
        for key in ('stdout', 'stderr'):
            path = self.output / (str(index).zfill(3) + '-' + key + '.raw')
            with path.open('xb') as stream: stream.write(actual[key])
            item[key] = record(path)
        self.calls.append(item); item['receipt'] = self.save(str(index).zfill(3) + '-call.json', item)
        return actual['stdout']

    def shell(self, argv):
        actual = self.callbacks['shell'](argv)
        raw = self.observed('shell', argv, actual)
        need(actual['exit_code'] == 0, 'actual root shell callback failed')
        need(actual['argv'][-len(argv):] == argv, 'actual shell argv does not retain requested arguments')
        self.target(actual['argv'])
        return raw

    def target(self, argv):
        need(argv.count('-t') == 1 and argv.index('-t') + 1 < len(argv) and
             argv[argv.index('-t') + 1] == self.hdc_target, 'actual callback HDC target differs from held Number VM')

    def pull(self, remote):
        result = self.callbacks['pull'](remote)
        need(type(result) is dict and set(result) == {'call', 'file'}, 'actual pull command and local file descriptor required')
        actual = result['call']
        self.observed('pull', remote, actual)
        need(actual['exit_code'] == 0, 'actual root pull callback failed')
        self.target(actual['argv'])
        path = checked(result['file'])
        need(remote in actual['argv'] and str(path) in actual['argv'],
             'actual pull argv must name both requested guest source and retained local destination')
        raw = path.read_bytes()
        need(hashlib.sha256(raw).hexdigest() == result['file']['sha256'], 'pulled file changed during capture')
        need(0 < len(raw) <= 1048576, 'bounded complete actual caller file required')
        captured = self.output / (str(len(self.calls) - 1).zfill(3) + '-payload.raw')
        with captured.open('xb') as stream: stream.write(raw)
        saved = record(captured)
        self.save(str(len(self.calls) - 1).zfill(3) + '-payload.json',
                  dict(pulled_file=result['file'], captured_file=saved))
        return raw, saved

    def boot(self):
        raw = self.shell(['cat', '/proc/sys/kernel/random/boot_id'])
        value = raw.decode('ascii').strip()
        need(re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', value), 'actual boot_id required')
        return value

    def role_artifacts(self, role):
        item = self.spec['roles'][role]; bundle, system, get, set_ = ROLES[role]
        paths = {k: checked(item[k]) for k in ('unsigned_hap', 'signed_hap', 'signing_receipt', 'sdk_evidence')}
        self.materials.extend(record(p) for p in paths.values())
        sign = decode(paths['signing_receipt'].read_bytes()); profile = sign['verified_profile']
        permissions = [name for name, result in [(GET, get), (SET, set_)] if result == 0]
        need(sign['status'] == 'pass' and sign['scope'] == 'actual_signature_profile_and_codesign_NOT_guest' and
             sign['role'] == role and sign['signed_sha256'] == item['signed_hap']['sha256'] and
             sign['unsigned_sha256'] == item['unsigned_hap']['sha256'], 'actual role signed/unsigned receipt mismatch')
        need(profile['bundle-info']['bundle-name'] == bundle and
             profile['bundle-info']['apl'] == ('system_core' if system else 'normal') and
             profile['bundle-info']['app-feature'] == ('hos_system_app' if system else 'hos_normal_app') and
             profile['acls']['allowed-acls'] == permissions and
             profile['permissions']['restricted-permissions'] == permissions, 'exact role signing/ACL policy mismatch')
        proof = sdk_role_artifacts(item, role, self.spec['source_commit'])
        self.materials.extend(proof['materials'])
        self.save(role + '-sdk-source-binding.json', proof)

    def identity(self, role, phase="identity"):
        return identity395(self, role, phase)

    def phase(self, role, phase):
        run, number = self.spec['runs'][role], self.spec['number']
        bms, access = self.identity(role, phase); before_boot = self.boot()
        need(before_boot == self.current_boot and
             (bms['uid'], bms['token']) == (self.initial[role]['uid'], self.initial[role]['token']),
             'caller UID/token or guest boot changed outside the controlled transition')
        self.shell(['aa', 'start', '-b', ROLES[role][0], '-a', 'EntryAbility',
                    '--ps', 'run', run, '--ps', 'phase', phase, '--ps', 'number', number])
        action = dict(kind='wait_actual_number_summary', bundle=ROLES[role][0], run=run, phase=phase,
                      timeout_seconds=self.spec['phase_timeout_seconds'])
        calls = self.callbacks['ui'](action)
        need(type(calls) is list and calls, 'actual UI/wait command receipts required')
        for call in calls: self.observed('ui', action, call)
        need(all(call['exit_code'] == 0 for call in calls), 'actual UI/wait callback failed')
        paths = discovered_files(self.shell([find_script(run, phase)]), run, phase)
        context = logged_context(calls, run, phase)
        stats = tuple(file_stat(self.shell([stat_script(path)]), path, bms['uid']) for path in paths)
        need((stats[0]['dev'], stats[0]['inode']) != (stats[1]['dev'], stats[1]['inode']),
             'journal and Token must be distinct actual files')
        mapping = mapped_context395(self, role, context, paths, stats)
        file_binding = dict(root_paths=paths, actual_stats=stats, actual_D2_context=context, mapping=mapping)
        pair = None; proof = None
        for _ in range(2):
            journal, jd = self.pull(paths[0])
            token, td = self.pull(paths[1])
            need(tuple(file_stat(self.shell([stat_script(path)]), path, bms['uid']) for path in paths) == stats and
                 (jd['sha256'], td['sha256']) == (stats[0]['sha256'], stats[1]['sha256']),
                 'actual caller files changed after discovery or do not match retained pulls')
            review = self.journal.review(checked(jd).read_bytes(), run, phase, number)
            joined = token_join(checked(td).read_bytes(), role, run, phase, bms, access)
            if pair is not None: need(pair == (journal, token), 'caller files changed between independent pulls')
            pair = journal, token
            rows = [decode(line) for line in journal.splitlines() if line.strip()]
            need(rows and rows[0]['event'] == 'begin' and rows[0]['detail'] == context,
                 'pulled D2 begin context differs from actual run/phase log and mapping')
            reads = [decode(r['detail'].encode('utf-8')) for r in rows if r['event'] == 'read']
            if phase != 'ordinary-denied':
                need(reads and reads[0]['count'] == (1 if phase == 'verify-persist' else 0),
                     'refuse preexisting number mark; persistence must first observe its owned row')
            if phase == 'system-denied':
                writes = [r for r in rows if r['event'] == 'write']
                denied = [r for r in rows if r['event'] == 'system_permission_observation_requires_root_review']
                need(len(writes) == len(denied) == 1 and writes[0]['code'] == denied[0]['code'] == self.permission_code and
                     reads[-1]['count'] == 0 and sum(r['event'] == 'helper_closed' for r in rows) == 1,
                     'readonly nonzero is not an exact source-bound SET permission denial')
            proof = dict(role=role, run=run, phase=phase, journal=jd, token=td,
                         journal_review=review, token_join=joined, boot_id=before_boot, actual_file_binding=file_binding)
        need(self.boot() == before_boot, 'phase crossed an uncontrolled boot')
        self.phases.append(proof); self.save(phase + '.json', proof)

    def napi_phase(self, role):
        # Independent finite extension. Original five DataShare phase() is unchanged.
        run = self.spec['runs'][role]; owner = self.spec['runs']['system-granted']
        number = self.spec['number']; bms, access = self.identity(role)
        before_boot = self.boot()
        need(before_boot == self.current_boot and bms == self.initial[role],
             'NAPI must use same original installed role and same boot')
        self.shell(['aa','start','-b',ROLES[role][0],'-a','EntryAbility',
            '--ps','run',run,'--ps','phase','napi-read','--ps','number',number,'--ps','ownerRun',owner])
        action = dict(kind='wait_actual_number_summary',bundle=ROLES[role][0],run=run,
                      phase='napi-read',timeout_seconds=self.spec['phase_timeout_seconds'])
        calls = self.callbacks['ui'](action)
        need(type(calls) is list and calls, 'actual NAPI summary receipts required')
        for call in calls:
            self.observed('ui',action,call); self.target(call['argv'])
            need(type(call['exit_code']) is int and call['exit_code'] == 0, 'actual NAPI wait failed')
        paths = napi411.discovered(self.shell([napi411.find_script(run)]),run)
        context = napi411.context(calls,run,owner,number)
        stats = tuple(file_stat(self.shell([stat_script(path)]),path,bms['uid']) for path in paths)
        need(len({(v['dev'],v['inode']) for v in stats}) == 3, 'distinct NAPI/Token actual files required')
        mapping = mapped_context395(self,role,context,paths,stats)
        after_bms, after_access = self.identity(role)
        need(after_bms == bms and after_access == access, 'actual BMS/GET/SET changed during NAPI read')
        previous = None; proof = None
        for _ in range(2):
            values = [self.pull(path) for path in paths]
            need(tuple(file_stat(self.shell([stat_script(path)]),path,bms['uid']) for path in paths) == stats and
                 all(desc['sha256'] == actual['sha256'] for (_,desc),actual in zip(values,stats)),
                 'actual NAPI files changed during independent pulls')
            blobs = tuple(raw for raw,_ in values)
            if previous is not None: need(previous == blobs, 'NAPI files changed between pulls')
            previous = blobs
            review = napi411.review(blobs[0],role=role,run=run,owner=owner,number=number,actual_context=context)
            tokens = [token_join(raw,role,run,phase,bms,access) for raw,phase in
                      zip(blobs[1:],('napi-before','napi-after'))]
            need(tokens[0] == tokens[1], 'actual before/after NAPI token mismatch')
            proof = dict(role=role,phase='napi-read',run=run,owner_run=owner,boot_id=before_boot,
                files=[desc for _,desc in values],review=review,token_joins=tokens,
                actual_file_binding=dict(root_paths=paths,stats=stats,actual_context=context,mapping=mapping))
        need(self.boot() == before_boot, 'NAPI crossed uncontrolled boot')
        self.napi_phases.append(proof); self.save(role+'-napi-read.json',proof)

    def collect(self):
        report = dict(status='fail_collector_checks_ONLY', failures=[], pending=[], phases=self.phases,
            calls=self.calls, napi_phases=self.napi_phases, runtime_ready=False, first_artifact_behavior_gate_passed=False,
            original_aggregate_finding_closed=False, actual_identity_proven_by_this_file=False,
            cleanup_pending=False, source_scope='public local subset only; root must verify actual callback provenance')
        persistence_started = False; persistence_removed = False
        try:
            s = self.spec
            if any(s.get(k) is None for k in ('archive_sha256', 'source_commit', 'number', 'runs')) or \
                    any(v is None for v in s.get('runs', {}).values()):
                raise Pending('actual new package/source, fresh random role runs and unused number not supplied')
            need(re.fullmatch('[0-9a-f]{40}', s['source_commit']) and
                 re.fullmatch('[0-9a-f]{64}', s['archive_sha256']), 'actual new package/source identity required')
            need(set(s['runs']) == set(ROLES) and set(s['roles']) == set(ROLES) and
                 len(set(s['runs'].values())) == 3 and all(re.fullmatch('[a-f0-9]{32}', v) and
                 v not in ('0' * 32, 'f' * 32) for v in s['runs'].values()) and
                 re.fullmatch(r'\+?[0-9]{7,20}', s['number']), 'fresh separate run IDs and root-owned unused number required')
            need(type(s['phase_timeout_seconds']) is int and 1 <= s['phase_timeout_seconds'] <= 300,
                 'bounded callback wait required')
            vm = vm_identity(s.get('vm'), s['archive_sha256'])
            self.hdc_target = vm['hdc_target']
            self.materials.append(s['vm']['record'])
            self.permission_code = permission_source(s.get('target_permission_source'), s['source_commit'])
            self.materials.append(s['target_permission_source']['record'])
            for role in ROLES: self.role_artifacts(role)
            region = self.shell(['param', 'get', 'const.global.region']).decode('utf-8').strip()
            if region != 'CN': raise Pending('actual const.global.region=' + region + '; native CN guard retained, no mutation')
            self.initial = {r: self.identity(r)[0] for r in ROLES}
            need(len({r['uid'] for r in self.initial.values()}) == 3 and len({r['token'] for r in self.initial.values()}) == 3,
                 'distinct independently installed role UIDs/tokens required; never borrow provider UID')
            first_boot = self.boot()
            self.current_boot = first_boot
            self.phase('system-granted', 'cycle')
            persistence_started = True
            self.phase('system-granted', 'prepare-persist')
            for role in ROLES: self.napi_phase(role)
            reboot = self.callbacks['controlled_reboot'](dict(expected_vm=vm, previous_boot_id=first_boot))
            need(type(reboot) is dict and set(reboot) == {'calls', 'after_vm'} and
                 type(reboot['calls']) is list and reboot['calls'], 'actual root controlled reboot receipts required')
            for call in reboot['calls']: self.observed('controlled_reboot', vm, call)
            need(all(call['exit_code'] == 0 for call in reboot['calls']), 'actual controlled reboot callback failed')
            need(reboot['after_vm']['record']['path'] != s['vm']['record']['path'] and
                 reboot['after_vm']['record']['sha256'] != s['vm']['record']['sha256'],
                 'a separately captured actual post-reboot held-VM receipt is required')
            self.materials.append(reboot['after_vm']['record'])
            after_vm = vm_identity(reboot['after_vm'], s['archive_sha256']); second_boot = self.boot()
            reboot_join(vm, after_vm, first_boot, second_boot)
            self.current_boot = second_boot
            report['controlled_reboot'] = dict(before_vm=vm, after_vm=after_vm,
                before_boot_id=first_boot, after_boot_id=second_boot, after_vm_evidence=reboot['after_vm'])
            self.phase('system-granted', 'verify-persist'); persistence_removed = True
            self.phase('system-readonly', 'system-denied')
            self.phase('ordinary', 'ordinary-denied')
            for descriptor in self.materials: checked(descriptor)
            report['pending'].extend(p for phase in self.napi_phases for p in phase['review']['pending'])
            report['pending'].append('Native creator/OnConnect/MainThread and new-image loaded DSO proofs require independent retained observations; no API resolve substitutes')
            report['status'] = 'pending_napi_native_acceptance_ONLY' if report['pending'] else 'pass_collector_checks_ONLY'
        except Pending as error:
            report['status'] = 'pending_actual_inputs_ONLY'; report['pending'].append(str(error))
        except Exception as error:
            report['failures'].append(type(error).__name__ + ': ' + str(error))
        finally:
            report['cleanup_pending'] = persistence_started and not persistence_removed
            report['cleanup_policy'] = 'D2 caller deletes only its own run-tagged rows; no collector generic delete/retry/permission changes. Failed persistence requires root inspection of retained run/number before any cleanup.'
            self.save('collector.json', report)
        return report
