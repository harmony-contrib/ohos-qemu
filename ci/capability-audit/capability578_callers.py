"""Build/sign real inputs for the actual held QEMU stages, serially.

Uses the original API26 project generator, SDK command recipe and signer. These
are guest fixtures, never a separate SDK/host acceptance stage.
"""
from pathlib import Path
import importlib
import json
import re
import shutil
from types import SimpleNamespace
import zipfile

from batch_apps_contact_picker_runtime import prepare_project
from batch_system_calendar_runtime_binding import sdk_commands
from capability578_owned_io import reference, require
from sign_certificate_probe import sign

FAMILIES = ('apps_ui578', 'communications578', 'system_services578', 'settings_idle579', 'apps_providers579',
            'livecaptions579')


def compiled_fields_match(actual, expected):
    """Compare all source role fields while retaining compiler-added metadata.

    Lists keep their exact cardinality/order: an extra permission, ability or
    skill can never be hidden by a subset comparison.
    """
    if type(expected) is dict:
        return type(actual) is dict and all(k in actual and compiled_fields_match(actual[k], v)
                                           for k, v in expected.items())
    if type(expected) is list:
        return type(actual) is list and len(actual) == len(expected) and all(
            compiled_fields_match(a, e) for a, e in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


def adapter(family, case, run, role, parameters):
    require(family in FAMILIES and re.fullmatch('[a-z0-9_-]+', case) and
            re.fullmatch('[a-z0-9_-]+', role) and re.fullmatch('[a-f0-9]{32}', run),
            'fixed source family/case/role and fresh run required')
    module = importlib.import_module(family + '_project')
    if family == 'apps_ui578':
        return module, module.source_files(run, case, role), module.module_fields(case, role), module.bundle(role)
    if family == 'system_services578':
        hosts = parameters.get('hosts')
        return module, module.source_files(case, run, role, hosts), module.module_fields(case, role, hosts), module.bundle(case, role)
    return (module, module.source_files(case, run, role, parameters),
            module.module_fields(case, role, parameters), module.bundle(case, role))


def prepare_callers(io, family, case, run, roles, parameters):
    require(type(roles) is tuple and roles and len(roles) == len(set(roles)) and
            type(parameters) is dict, 'finite actual caller roles required')
    command_start = len(io.receipts)
    if family == 'apps_ui578' and case == 'certificate-dialog':
        from capability578_certificate import prepare as prepare_certificate
        prepare_certificate(io, run)
    sdk = Path(io.owner.config['sdk'])
    cli = Path(io.environment['QEMU_TEST_HVIGOR_HOME']).parent.parent
    node = Path(io.environment['QEMU_TEST_NODE_HOME']) / 'bin/node'
    tools = {'node': reference(node), 'ohpm': reference(cli / 'ohpm/bin/pm-cli.js'),
             'hvigor': reference(Path(io.environment['QEMU_TEST_HVIGOR_HOME']) / 'bin/hvigorw.js')}
    cache = io.output / 'sdk-cache'
    if not cache.exists():
        cache.mkdir()
        wrapper = Path(io.environment['HVIGOR_USER_HOME']) / 'wrapper'
        require(wrapper.is_dir(), 'original actual Hvigor wrapper cache required')
        shutil.copytree(wrapper, cache / 'hvigor-home/wrapper', symlinks=False)
        cpu = Path(__file__).with_name('fixtures') / 'batch_system/calendar_runtime/cpu-cap.cjs'
        shutil.copyfile(cpu, cache / 'cpu-cap.cjs')
    tools['cpu_cap'] = reference(cache / 'cpu-cap.cjs')
    environment = dict(io.environment, NODE_HOME=str(node.parent.parent),
        OHOS_SDK_HOME=str(sdk), DEVECO_SDK_HOME=str(sdk.parent),
        HVIGOR_USER_HOME=str(cache / 'hvigor-home'), OHPM_HOME=str(cache / 'ohpm-home'))
    result = {'case': case, 'run_id': run, 'boot_id': io.boot_id, 'callers': {}}
    for role in roles:
        module, sources, fields, bundle = adapter(family, case, run, role, parameters)
        root = io.output / ('caller-' + case + '-' + role + '-' + run)
        prepare_project(root)
        # Remove only the seed recipe that the original generator wrote.
        shutil.rmtree(root / 'entry/src/main/ets/model')
        (root / 'caller-source-manifest.json').unlink()
        app = root / 'AppScope/app.json5'
        value = json.loads(app.read_text()); value['app']['bundleName'] = bundle
        if family == 'apps_ui578' and case == 'intelligent-scene' and role in ('a', 'b'):
            value['app']['label'] = module.label_overlay(run, case, role)['app_label']
        app.write_text(json.dumps(value, indent=2) + '\n')
        manifest = root / 'entry/src/main/module.json5'
        value = json.loads(manifest.read_text()); value['module'].update(fields)
        manifest.write_text(json.dumps(value, indent=2) + '\n')
        for name, text in sources.items():
            rel = Path(name)
            require(not rel.is_absolute() and '..' not in rel.parts and type(text) is str,
                    'fixed caller source overlay required')
            target = root / rel; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(text)
        if family == 'livecaptions579':
            speech = io.package_inputs['livecaptions579']['speech']
            require(set(speech) == {'a', 'b'}, 'two independent original speech inputs required')
            for name, destination in module.asset_destinations(case, role).items():
                key = name.removeprefix('license_')
                artifact = speech[key]['license' if name.startswith('license_') else 'audio']
                require(reference(artifact['path']) == artifact,
                        'original speech/license bytes changed before fixture compilation')
                target = root / destination
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(artifact['path'], target)
        if family == 'settings_idle579':
            native = io.package_inputs['native_addons']['settings_idle579']
            require(type(native) is dict and set(native) == {'binary', 'build', 'abi'} and
                    native['abi'] == 'arm64-v8a', 'actual first-artifact platform addon required')
            for kind in ('binary', 'build'):
                require(reference(native[kind]['path']) == native[kind], 'actual platform addon input changed')
            destination = root / module.native_artifact_destination()
            require(destination == root / 'entry/libs/arm64-v8a/libsettings_idle579.so',
                    'fixed actual addon destination required')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(native['binary']['path'], destination)
            # Preserve the exact platform-built diagnostic addon through the
            # ordinary HAP fixture packaging task. The shipped product's strip,
            # CFI and optimization policies are unaffected. This option is the
            # actual API26 Hvigor nativeLib.debugSymbol schema.
            profile_path = root / 'entry/build-profile.json5'
            profile_value = json.loads(profile_path.read_text())
            profile_value.setdefault('buildOption', {})['nativeLib'] = {
                'debugSymbol': {'strip': False}}
            profile_path.write_text(json.dumps(profile_value, indent=2) + '\n')
        (root / 'local.properties').write_text('sdk.dir=' + str(sdk.parent) + '\nnodejs.dir=' + str(node.parent.parent) + '\n')
        inputs = {str(p.relative_to(root)): reference(p) for p in root.rglob('*') if p.is_file()}
        (root / 'capability578-source-inputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
        build_commands = []
        for label, argv in sdk_commands(tools):
            row = io.command(['/usr/bin/nice', '-n', '10', *argv], 'caller_' + role + '_' + label,
                             timeout=1800, cwd=root, env=environment)
            build_commands.append(io.ref_receipt(row))
            if label == 'compile':
                require('BUILD SUCCESSFUL' in row['stdout'] + row['stderr'], 'real Hvigor build did not complete')
        haps = list(root.glob('entry/build/default/outputs/default/*-unsigned.hap'))
        require(len(haps) == 1, 'one newly compiled unsigned caller required')
        unsigned = haps[0]
        with zipfile.ZipFile(unsigned) as hap:
            names = hap.namelist()
            require(len(names) == len(set(names)) and hap.read('ets/modules.abc'), 'actual complete caller HAP required')
            compiled = json.loads(hap.read('module.json'))
            if family == 'settings_idle579':
                require(hap.read('libs/arm64-v8a/libsettings_idle579.so') ==
                        Path(native['binary']['path']).read_bytes(), 'Hvigor changed the actual platform addon')
        require(compiled['app']['bundleName'] == bundle and compiled_fields_match(compiled['module'], fields),
                'compiled caller role fields differ from actual source recipe')
        if family == 'apps_ui578' and case == 'intelligent-scene' and role in ('a', 'b'):
            require(compiled['app']['label'] == module.label_overlay(run, case, role)['app_label'],
                    'compiled DND caller did not keep its actual unique label resource')
        signed = root / 'caller-signed.hap'
        sign_rows = []

        def actual_sign_command(argv, **options):
            require(options.get('text', True) is True, 'signer must retain actual textual streams')
            row = io.command(list(map(str, argv)), 'caller_' + role + '_sign_' + str(len(sign_rows)),
                             timeout=300, allow_failure=not options.get('check', False))
            sign_rows.append(row)
            return SimpleNamespace(returncode=row['exit_code'], stdout=row['stdout'], stderr=row['stderr'])

        signer = io.owner.config['select']
        arguments = SimpleNamespace(unsigned=unsigned, output=signed, role=role, udid=io.udid,
            signer_dist=Path(signer['signer_dist']), jar=Path(signer['signer_jar']))
        sign(arguments, configure=module.configure_profile(case), command=actual_sign_command)
        if family == 'settings_idle579':
            with zipfile.ZipFile(signed) as hap:
                require(hap.read('libs/arm64-v8a/libsettings_idle579.so') ==
                        Path(native['binary']['path']).read_bytes(), 'signer changed the actual platform addon')
        signing = signed.with_suffix('.signing.json')
        signed_record = json.loads(signing.read_text())
        profile = root / 'verified-profile.json'
        profile.write_text(json.dumps(signed_record['verified_profile'], indent=2) + '\n')
        verify_rows = [r for r in sign_rows if 'verify-app' in r['argv'] or 'verify-profile' in r['argv']]
        actual_leaf = next((r['stdout'] + r['stderr'] for r in verify_rows if 'verify-app' in r['argv']), None)
        require(actual_leaf is not None, 'actual signer certificate transcript missing')
        sections = re.split(r'certificate #0\b', actual_leaf, maxsplit=1)
        require(len(sections) == 2, 'actual application leaf absent')
        leaf = re.split(r'certificate #1\b', sections[1], maxsplit=1)[0]
        values = re.findall(r'SHA256:\s*([0-9A-Fa-f:]+)', leaf)
        require(len(values) == 1 and re.fullmatch('[0-9A-Fa-f]{64}', values[0].replace(':', '')),
                'actual application certificate SHA256 absent')
        result['callers'][role] = {'bundle': bundle, 'project': str(root),
            'unsigned': reference(unsigned), 'signed': reference(signed), 'signing': reference(signing),
            'verified_profile': reference(profile), 'build_commands': build_commands,
            'sign_commands': [io.ref_receipt(r) for r in sign_rows if r not in verify_rows],
            'verify_commands': [io.ref_receipt(r) for r in verify_rows],
            'identity': {'fingerprint': values[0].replace(':', '').upper()}}
    if family == 'apps_ui578':
        # The app binding's fixed role-map API carries the actual decoded
        # provision object as well as its immutable extracted-file reference.
        return {role: dict(row, verified_profile=json.loads(Path(row['verified_profile']['path']).read_text()),
                           verified_profile_ref=row['verified_profile'])
                for role, row in result['callers'].items()}
    if family == 'communications578':
        native = io.package_inputs['native_helpers']['communications578']
        require(type(native) is dict and set(native) == {'at_peer', 'permission_controller'},
                'both real pre-VM communications helper builds are required')
        binaries = {}
        for name, actual in native.items():
            require(type(actual) is dict and set(actual) == {'binary', 'build'},
                    'actual binary and original helper-build receipt required')
            for kind in ('binary', 'build'):
                require(reference(actual[kind]['path']) == actual[kind], 'actual helper artifact changed')
            binaries[name] = actual['binary']
        result.update(applications=result['callers'], native_helpers=binaries,
            native_helper_builds=native, receipts=io.receipts[command_start:])
    if family == 'settings_idle579':
        result['native_addons'] = {'settings_idle579': io.package_inputs['native_addons']['settings_idle579']}
    if family == 'livecaptions579':
        speech = io.package_inputs['livecaptions579']['speech']
        result.update(audio_fixtures={k: speech[k]['audio'] for k in ('a', 'b')},
                      license_fixtures={k: speech[k]['license'] for k in ('a', 'b')})
    return result
