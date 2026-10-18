#!/usr/bin/env python3
"""Prepare fresh ordinary AudioHaptic QA projects/challenges; never build or boot."""
import argparse
import json
from pathlib import Path
import re
import secrets
import shlex
import wave

import batch_media_audio_capture_challenge as pcm
import batch_media_knowledge_project as shared_project
import batch_apps_contact_picker_coordinator as signatures

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIX = HERE / 'fixtures/batch_media/audio_haptic_runtime'
PROBE = HERE / 'fixtures/batch_media/audio_haptic/AudioHapticProbe.ets'
ROLES = {'normal': ('org.harmonycontrib.audiohapticqa', ['ohos.permission.VIBRATE']),
         'denied': ('org.harmonycontrib.audiohapticdenied', [])}
PIN = '248a21a014a0794fc8d1853387d139f815df9a56'
SDK_SCOPE = 'actual_SDK105_full_unsigned_AudioHaptic_HAPs_ONLY_NOT_signature_or_guest'
SDK_SOURCE_TOOLS = ('batch_media_audio_haptic_project.py', 'batch_media_audio_haptic_build_callers.py')


def sdk_inputs(sdk):
    sdk = Path(sdk).resolve()
    return {name: record(sdk / relative) for name, relative in {
        'metadata': 'ets/oh-uni-package.json', 'audio_haptic': 'ets/api/@ohos.multimedia.audioHaptic.d.ts',
        'device_default': 'ets/api/device-define/default.json'}.items()}


def sampler_script(remote, mode, run, boot, *arguments):
    require(mode in ('clock', 'token'), 'only exact read-only observation modes')
    return 'unset LD_LIBRARY_PATH LD_PRELOAD; ' + ' '.join(map(shlex.quote,
        [remote + '/sampler', mode, run, boot, *map(str, arguments)]))


def private_cleanup_script(remote, ui_paths):
    require(re.fullmatch('/data/local/tmp/audio-haptic-[a-f0-9]{32}', remote), 'owned helper directory required')
    paths = [remote + '/sampler'] + sorted(set(ui_paths))
    require(all(re.fullmatch(r'/data/local/tmp/qemu-capability-ui-[a-f0-9]{32}-[1-9][0-9]*\.(?:json|png)', p)
                for p in paths[1:]), 'only genuine owned UI paths may be removed')
    script = 'rm -f -- ' + ' '.join(map(shlex.quote, paths)) + ' && ' + ' && '.join(
        'test ! -e ' + shlex.quote(p) + ' && test ! -L ' + shlex.quote(p) for p in paths)
    script += ' && rmdir ' + remote + ' && test ! -e ' + remote + ' && test ! -L ' + remote
    return paths, script

require, sha, record, checked, write = (getattr(shared_project, n) for n in ('require', 'sha', 'record', 'checked', 'write'))


def load(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=signatures.unique)


def upstream():
    proof = load(FIX / 'upstream/provenance.json')
    lock = load(ROOT / 'scripts/openharmony_7_0_release_source_lock.json')
    require(proof['revision'] == PIN and any(p['name'] == 'sensors_miscdevice' and p['revision'] == PIN
            for p in lock['projects']), 'public decoder must match the real product source lock')
    for row in proof['files']:
        name = Path(row['relative_path'])
        require(not name.is_absolute() and '..' not in name.parts and sha(FIX / 'upstream' / name) == row['sha256'],
                'pinned public primary source changed')
    return proof


def challenge(output, run_id=None):
    upstream()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    run_id = run_id or secrets.token_hex(16)
    require(re.fullmatch('[a-f0-9]{32}', run_id), 'fresh bounded run ID required')
    pcm.generate(output / 'reference', run_id)
    reference = (output / 'reference/challenge.pcm').read_bytes()
    with wave.open(str(output / 'challenge.wav'), 'wb') as stream:
        stream.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
        stream.writeframes(reference * 4)
    original = FIX / 'upstream/utils/tools/haptic_format_converter/tests/test_data/oh_no_curve_sample.json'
    effect = load(original)
    event = effect['Channels'][0]['Pattern'][0]['Event']
    # Exact keys and supported ranges come from the pinned original JSON and
    # DefaultVibratorDecoder::ParseEvent/CheckEventParameters, never guessed.
    event['StartTime'] = 0
    event['Duration'] = 4000
    write(output / 'haptic.json', effect)
    (output / 'bad.wav').write_bytes(b'INVALID-WAV-' + secrets.token_bytes(128))
    (output / 'bad.json').write_bytes(b'{"MetaData": invalid-' + secrets.token_bytes(64).hex().encode())
    result = {'schema_version': 1, 'run_id': run_id, 'rate': 48000, 'channels': 2,
        'format': 'S16LE', 'duration_ms': 4000, 'reference': record(output / 'reference/challenge.pcm'),
        'pcm_manifest': record(output / 'reference/challenge.json'),
        'files': {name: record(output / name) for name in ('challenge.wav', 'haptic.json', 'bad.wav', 'bad.json')},
        'haptic_source': record(original), 'haptic_provenance': record(FIX / 'upstream/provenance.json'),
        'haptic_transform': {'StartTime': {'before': 100, 'after': 0}, 'Duration': {'before': 1200, 'after': 4000}},
        'decoder_runtime_validated': False, 'first_artifact_behavior_gate_passed': False}
    write(output / 'challenge.json', result)
    return output / 'challenge.json'


def validate_challenge(path):
    value = load(path)
    require(value['schema_version'] == 1 and re.fullmatch('[a-f0-9]{32}', value['run_id']) and
            (value['rate'], value['channels'], value['format'], value['duration_ms']) == (48000, 2, 'S16LE', 4000),
            'actual fresh AudioHaptic challenge required')
    upstream()
    require(value['haptic_provenance'] == record(FIX / 'upstream/provenance.json') and
            value['haptic_source'] == record(FIX / 'upstream/utils/tools/haptic_format_converter/tests/test_data/oh_no_curve_sample.json'),
            'wrong real decoder/sample provenance')
    ref = checked(value['reference']).read_bytes()
    require(len(ref) == 48000 * 4 and load(checked(value['pcm_manifest']))['run_id'] == value['run_id'] and
            load(checked(value['pcm_manifest']))['sha256'] == value['reference']['sha256'], 'fresh PCM reference binding differs')
    for item in value['files'].values(): checked(item)
    with wave.open(str(checked(value['files']['challenge.wav'])), 'rb') as stream:
        require((stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes()) ==
                (2, 2, 48000, 192000) and stream.readframes(192000) == ref * 4, 'WAV bytes differ from fresh independent reference')
    effect = load(checked(value['haptic_source']))
    effect['Channels'][0]['Pattern'][0]['Event'].update(StartTime=0, Duration=4000)
    require(load(checked(value['files']['haptic.json'])) == effect, 'time-effect schema/content changed')
    return value


def fixture_hashes():
    return {str(p.relative_to(FIX)): sha(p) for p in sorted(FIX.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}


def render(output, role, challenge_path, sdk_proof):
    """Pure source preparation. CLI supplies independently read actual SDK facts."""
    data = validate_challenge(challenge_path)
    require(role in ROLES, 'exact normal/denied role required')
    output = Path(output).resolve()
    require(not output.exists() and output != ROOT and ROOT not in output.parents, 'fresh private output outside repository required')
    output.mkdir(parents=True)
    bundle, permissions = ROLES[role]
    def put(name, value): write(output / name, value)
    put('AppScope/app.json5', {'app': {'bundleName': bundle, 'vendor': 'Harmony Contrib', 'versionCode': 1,
        'versionName': '1.0.0', 'icon': '$media:app_icon', 'label': '$string:app_name'}})
    put('AppScope/resources/base/element/string.json', {'string': [{'name': 'app_name', 'value': 'AudioHaptic QA ' + role}]})
    put('AppScope/resources/base/media/app_icon.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#245267"/></svg>\n')
    put('build-profile.json5', {'app': {'products': [{'name': 'default', 'compileSdkVersion': '26.0.0',
        'compatibleSdkVersion': '26.0.0', 'targetSdkVersion': '26.0.0', 'runtimeOS': 'OpenHarmony'}]},
        'modules': [{'name': 'entry', 'srcPath': './entry', 'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]})
    put('oh-package.json5', {'modelVersion': '6.0.0', 'name': 'audio-haptic-' + role, 'version': '1.0.0', 'dependencies': {}, 'devDependencies': {}})
    put('hvigor/hvigor-config.json5', {'modelVersion': '6.0.0', 'dependencies': {}, 'execution': {'daemon': False, 'parallel': False}})
    put('hvigorfile.ts', "import { appTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: appTasks, plugins: [] };\n")
    put('entry/hvigorfile.ts', "import { hapTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: hapTasks, plugins: [] };\n")
    put('entry/build-profile.json5', {'apiType': 'stageMode', 'targets': [{'name': 'default'}]})
    put('entry/oh-package.json5', {'name': 'entry', 'version': '1.0.0', 'dependencies': {}})
    put('entry/src/main/module.json5', {'module': {'name': 'entry', 'type': 'entry', 'mainElement': 'EntryAbility',
        'deviceTypes': ['default'], 'deliveryWithInstall': True, 'installationFree': False, 'pages': '$profile:main_pages',
        'requestPermissions': [{'name': name} for name in permissions],
        'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets', 'launchType': 'singleton',
        'exported': True, 'label': '$string:app_name', 'icon': '$media:app_icon', 'startWindowIcon': '$media:app_icon',
        'startWindowBackground': '$color:start_window_background'}]}})
    put('entry/src/main/resources/base/element/color.json', {'color': [{'name': 'start_window_background', 'value': '#FFFFFF'}]})
    put('entry/src/main/resources/base/profile/main_pages.json', {'src': ['pages/Index']})
    put('entry/src/main/ets/pages/Index.ets', (FIX / 'Index.ets').read_text().replace('__HAPTIC_ROLE__', role).replace('__HAPTIC_RUN__', data['run_id']))
    put('entry/src/main/ets/pages/AudioHapticProbe.ets', PROBE.read_text())
    put('entry/src/main/ets/entryability/EntryAbility.ets', (FIX / 'EntryAbility.ets').read_text())
    manifest = {'schema_version': 1, 'role': role, 'run_id': data['run_id'], 'bundle_name': bundle,
        'requested_permissions': permissions, 'apl': 'normal', 'system_app': False, 'allowed_acls': [], 'restricted_permissions': [],
        'challenge': record(challenge_path), 'sdk': sdk_proof, 'fixture_hashes': fixture_hashes(), 'original_probe': record(PROBE),
        'sources': {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()},
        'built': False, 'signed': False, 'runtime_validated': False}
    put('audio-haptic-source-manifest.json', manifest)
    return output / 'audio-haptic-source-manifest.json'


def prepare_project(output, role, challenge_path, sdk):
    sdk = Path(sdk)
    require(load(sdk / 'ets/oh-uni-package.json').get('version') == '26.0.0.105', 'actual SDK105 metadata required')
    declaration = sdk / 'ets/api/@ohos.multimedia.audioHaptic.d.ts'
    text = declaration.read_text()
    for signature in ('registerSource(audioUri: string, hapticUri: string)', 'createPlayer(id: number',
                      'setAudioLatencyMode(id: number', 'setStreamUsage(id: number', "on(type: 'endOfStream'", "on(type: 'audioInterrupt'"):
        require(signature in text, 'actual SDK AudioHaptic contract missing: ' + signature)
    profile = sdk / 'ets/api/device-define/default.json'
    require({'SystemCapability.Multimedia.AudioHaptic.Core', 'SystemCapability.Multimedia.Audio.Core'} <=
            set(load(profile)['SysCaps']), 'actual SDK105 profile lacks caller capabilities')
    return render(output, role, challenge_path, {'metadata': record(sdk / 'ets/oh-uni-package.json'),
        'audio_haptic': record(declaration), 'device_default': record(profile)})


def verify_sdk_receipt(spec, role, sdk):
    evidence = checked(spec['sdk_evidence']); report = load(evidence)
    source = Path(spec['source_project']).resolve()
    require(spec['sdk_project'] == role and report['scope'] == SDK_SCOPE and
            type(report['exit_code']) is int and report['exit_code'] == 0 and report['failures'] == [] and
            re.fullmatch('[a-f0-9]{40}', report['source_commit']) and
            report['runner_sha256'] == sha(HERE / 'batch_media_audio_haptic_build_callers.py') and
            report['source_tools'] == {name: sha(HERE / name) for name in SDK_SOURCE_TOOLS} and
            report['fixture_hashes'] == fixture_hashes() and report['sdk'] == sdk and
            set(report['source_files']) == set(ROLES) and set(report['projects']) == set(ROLES),
            'successful exact dedicated AudioHaptic SDK builder receipt required')
    for item in report['sdk'].values(): checked(item)
    tools = {name: checked(report['runtime_inputs'][name]) for name in ('node', 'ohpm', 'hvigor', 'cpu_cap')}
    require(tools['cpu_cap'] == evidence.parent / 'cpu-cap.cjs' and
            sha(tools['cpu_cap']) == sha(FIX / 'cpu-cap.cjs'), 'actual bounded SDK preload differs')
    prefix = [str(tools['node']), '--max-old-space-size=2048', '--require', str(tools['cpu_cap'])]
    expected = [('_toolchain', 'node-version', [str(tools['node']), '--version'], str(evidence.parent))]
    for selected in ROLES:
        cwd = str(Path(report['projects'][selected]).resolve())
        expected += [(selected, 'dependencies', prefix + [str(tools['ohpm']), 'install', '--all', '--registry',
            'http://127.0.0.1:9', '--fetch_timeout', '10000', '--retry_times', '0'], cwd),
            (selected, 'compile', prefix + [str(tools['hvigor']), 'assembleHap', '--mode', 'module', '-p',
             'product=default', '-p', 'module=entry', '-p', 'debuggable=false', '-p', 'hvigor-obfuscation=false',
             '--no-daemon', '--no-parallel', '--no-incremental', '--max-old-space-size', '2048'], cwd)]
    require(len(report['commands']) == len(expected) and report['projects'][role] == str(source), 'SDK source/cwd set differs')
    for row, (selected, label, argv, cwd) in zip(report['commands'], expected):
        require((row['project'], row['label'], row['argv'], row['cwd']) == (selected, label, argv, cwd) and
                type(row['exit_code']) is int and row['exit_code'] == 0 and row['timed_out'] is False,
                'actual dedicated SDK command/cwd/outcome differs')
        checked({'path': row['log'], 'sha256': row['sha256']})
    require(checked({'path': report['commands'][0]['log'], 'sha256': report['commands'][0]['sha256']}).read_text().strip()
            == report['node_version'] == 'v18.20.1', 'actual SDK Node version receipt differs')
    require(len(report['haps']) == len(ROLES) and {h['project'] for h in report['haps']} == set(ROLES), 'both complete SDK HAPs required')
    selected = [h for h in report['haps'] if h['project'] == role]
    hap = checked(spec['unsigned_hap'])
    require(len(selected) == 1 and selected[0]['path'] == str(hap) and selected[0]['sha256'] == sha(hap) and
            selected[0]['bytes'] == hap.stat().st_size, 'dedicated SDK HAP differs')
    return report


def project_binding(spec, role, challenge_path):
    result = signatures.verify_sdk_project(spec)
    data = validate_challenge(challenge_path)
    source = Path(spec['source_project']).resolve()
    manifest = load(checked(spec['source_manifest']))
    require(checked(spec['source_manifest']) == source / 'audio-haptic-source-manifest.json' and manifest['role'] == role and
            manifest['run_id'] == data['run_id'] and manifest['bundle_name'] == ROLES[role][0] and
            manifest['requested_permissions'] == ROLES[role][1] and manifest['apl'] == 'normal' and manifest['system_app'] is False and
            manifest['allowed_acls'] == [] and manifest['restricted_permissions'] == [] and
            manifest['challenge'] == record(challenge_path) and manifest['fixture_hashes'] == fixture_hashes() and
            manifest['original_probe'] == record(PROBE), 'compiled fixed role/run/source manifest differs')
    require(isinstance(manifest['sdk'], dict) and set(manifest['sdk']) == {'metadata', 'audio_haptic', 'device_default'} and
            load(checked(manifest['sdk']['metadata'])).get('version') == '26.0.0.105', 'actual fixed SDK105 receipt required')
    for item in manifest['sdk'].values(): checked(item)
    verify_sdk_receipt(spec, role, manifest['sdk'])
    rows = signatures.source_rows(load(checked(spec['sdk_evidence'])), spec['sdk_project'])
    require(rows.get('audio-haptic-source-manifest.json') == sha(checked(spec['source_manifest'])), 'SDK must freeze source manifest')
    for name, digest in manifest['sources'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts and rows.get(name) == digest and sha(source / name) == digest,
                'compiled source changed: ' + name)
    require((source / 'entry/src/main/ets/pages/AudioHapticProbe.ets').read_bytes() == PROBE.read_bytes(), 'original public API class changed')
    require((source / 'entry/src/main/ets/pages/Index.ets').read_text() ==
            (FIX / 'Index.ets').read_text().replace('__HAPTIC_ROLE__', role).replace('__HAPTIC_RUN__', data['run_id']), 'persistent UI host changed')
    signatures.ordinary_hap(checked(spec['unsigned_hap']), *ROLES[role])
    return result


def phases():
    """Coverage is fixed here, never narrowed by the incoming capture report."""
    rows = []
    def add(name, action, *, role='normal', expected='ok', errors=(), hold=0, audio=None, haptic=None,
            eos=False, active_before=None, resources=None, **options):
        # Resource filenames and observed audio/haptic modes are different inputs.
        # In particular, **{'audio': 'bad.wav'} would bind the mode formal and
        # silently leave registerSource pointing at the normal challenge.
        resources = {} if resources is None else resources
        require(isinstance(resources, dict) and set(resources) <= {'audio', 'haptic'} and
                all(isinstance(value, str) and re.fullmatch('[a-z-]+\\.(?:wav|json)', value)
                    for value in resources.values()) and not set(resources) & set(options),
                'explicit private audio/haptic resource filenames required')
        rows.append(dict(name=name, role=role, action=action, options=dict(options, **resources), expected=expected, errors=list(errors),
                         hold_ms=hold, audio=audio, haptic=haptic, eos=eos, active_before=active_before))
    def source(prefix, **options):
        add(prefix + '-register', 'register', **options)
        add(prefix + '-create', 'create', **options)
    def stop(prefix, active_before=None): add(prefix, 'stop', hold=700, audio='quiet', haptic='quiet', active_before=active_before)
    def release(prefix, active_before=None): add(prefix, 'release', hold=700, audio='quiet', haptic='quiet', active_before=active_before)
    add('normal-access', 'access')
    source('base')
    add('base-loop-off', 'loop', loop=False)
    add('base-volume', 'volume', volume=0.5)
    for cycle in range(1, 4):
        add('normal-start-' + str(cycle), 'start', hold=1100, audio='active', haptic='active')
        stop('normal-stop-' + str(cycle), {'audio': True, 'haptic': True})
    for cycle in range(1, 3):
        add('eos-start-' + str(cycle), 'start', hold=5200, audio='eos', haptic='eos', eos=True)
    add('loop-enable', 'loop', loop=True)
    add('loop-start', 'start', hold=9200, audio='loop', haptic='loop')
    stop('loop-stop', {'audio': True, 'haptic': True})
    add('loop-disable', 'loop', loop=False)
    release('base-release')
    add('post-release-start', 'start', expected='error', errors=(5400102,), hold=700, audio='quiet', haptic='quiet')
    add('base-unregister', 'unregister')
    source('recreate')
    add('recreate-start', 'start', hold=1100, audio='active', haptic='active')
    release('recreate-active-release', {'audio': True, 'haptic': True})
    add('recreate-unregister', 'unregister')
    for label, mute_audio, mute_haptics in [('mute-audio', True, False), ('mute-haptics', False, True), ('mute-both', True, True)]:
        source(label, mute_audio=mute_audio, mute_haptics=mute_haptics)
        add(label + '-start', 'start', hold=1100, audio='quiet' if mute_audio else 'active', haptic='quiet' if mute_haptics else 'active')
        stop(label + '-stop', {'audio': not mute_audio, 'haptic': not mute_haptics})
        release(label + '-release')
        add(label + '-unregister', 'unregister')
    for bad, option in [('bad-wav', {'audio': 'bad.wav'}), ('bad-json', {'haptic': 'bad.json'}), ('missing-wav', {'audio': 'missing.wav'})]:
        add(bad + '-register', 'register', resources=option)
        add(bad + '-create', 'create', expected='error', errors=(5400103, 5400106), hold=700, audio='quiet', haptic='quiet')
        add(bad + '-unregister', 'unregister')
        source(bad + '-retry')
        add(bad + '-retry-start', 'start', hold=1100, audio='active', haptic='active')
        stop(bad + '-retry-stop', {'audio': True, 'haptic': True})
        release(bad + '-retry-release')
        add(bad + '-retry-unregister', 'unregister')
    add('denied-access', 'access', role='denied')
    add('denied-register', 'register', role='denied')
    add('denied-create', 'create', role='denied', expected='error', errors=(201,), hold=700, audio='quiet', haptic='quiet')
    add('denied-unregister', 'unregister', role='denied')
    return rows


def execution_plan():
    rows = phases(); result = []; index = 0
    while index < len(rows):
        first = rows[index]
        if (index + 1 < len(rows) and first['action'] == 'start' and first['expected'] == 'ok' and
                rows[index + 1]['action'] in ('stop', 'release') and rows[index + 1]['active_before'] is not None):
            result.append(rows[index:index + 2]); index += 2
        else: result.append([first]); index += 1
    return result


def capture_plan():
    return [block for block in execution_plan() if block[0]['hold_ms']]


def capture_name(block):
    return '--'.join(phase['name'] for phase in block)


def paired_request(first, following, delay_ms):
    require(first['role'] == following['role'] and first['request']['action'] == 'start' and
            following['request']['action'] in ('stop', 'release') and
            first['request']['operation_id'] != following['request']['operation_id'] and
            first['request']['run_id'] == following['request']['run_id'] and
            first['request']['boot_id'] == following['request']['boot_id'] and
            type(delay_ms) is int and 1 <= delay_ms <= 10000, 'exact fresh explicit lifecycle pair required')
    return dict(first, following_phase=following['phase'], following_request=following['request'], following_delay_ms=delay_ms)


def request(challenge_path, boot, phase, operation_id=None):
    data = validate_challenge(challenge_path)
    require(re.fullmatch('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', boot), 'actual kernel boot ID required')
    operation_id = operation_id or secrets.token_hex(16)
    require(re.fullmatch('[a-f0-9]{32}', operation_id), 'fresh explicit operation nonce required')
    row = next((v for v in phases() if v['name'] == phase), None)
    require(row is not None, 'unknown fixed phase')
    role = row['role']; options = row['options']
    prefix = '/data/storage/el2/base/files/'
    # Options persist in the native player only after create/loop/volume. Every
    # request still carries an explicit full public HapticRequest shape.
    return {'role': role, 'phase': phase, 'request': {'schema_version': 1, 'run_id': data['run_id'], 'boot_id': boot,
        'operation_id': operation_id, 'action': row['action'], 'audio_path': prefix + options.get('audio', 'challenge.wav'),
        'haptic_path': prefix + options.get('haptic', 'haptic.json'), 'fast': False,
        'mute_audio': options.get('mute_audio', False), 'mute_haptics': options.get('mute_haptics', False),
        'loop': options.get('loop', False), 'volume': options.get('volume', 0.5)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('challenge'); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('project')
    p.add_argument('--output', type=Path, required=True); p.add_argument('--role', choices=ROLES, required=True)
    p.add_argument('--challenge', type=Path, required=True); p.add_argument('--sdk', type=Path, required=True)
    p = sub.add_parser('request')
    p.add_argument('--challenge', type=Path, required=True); p.add_argument('--boot-id', required=True)
    p.add_argument('--phase', choices=[v['name'] for v in phases()], required=True); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('artifacts')
    for name in ('challenge', 'projects', 'signer-dist', 'jar', 'helper-build', 'helper-output', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--helper-path-map', type=Path, help='optional JSON object mapping original /work and /evidence/helpers prefixes')
    sub.add_parser('plan')
    args = parser.parse_args()
    if args.mode == 'challenge': print(challenge(args.output))
    elif args.mode == 'project': print(prepare_project(args.output, args.role, args.challenge, args.sdk))
    elif args.mode == 'request': write(args.output, request(args.challenge, args.boot_id, args.phase))
    elif args.mode == 'artifacts':
        from batch_media_audio_haptic_build_sampler import helper_binding
        validate_challenge(args.challenge)
        projects = load(args.projects)
        require(set(projects) == set(ROLES), 'both actual compiled roles required')
        for role, spec in projects.items(): project_binding(spec, role, args.challenge)
        signatures.signer_inputs(args.signer_dist, args.jar)
        helper = dict(build=record(args.helper_build), output_directory=str(args.helper_output.resolve()),
                      path_map=load(args.helper_path_map) if args.helper_path_map else {})
        helper_binding(helper)
        write(args.output, dict(schema_version=1, challenge=record(args.challenge), projects=projects,
            signer=dict(dist=str(args.signer_dist.resolve()), jar=record(args.jar)), helper=helper))
        print(args.output.resolve())
    else: print(json.dumps(phases(), indent=2))


if __name__ == '__main__': main()
