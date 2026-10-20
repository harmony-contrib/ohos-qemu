#!/usr/bin/env python3
"""Assemble fixed input DATA after root's genuine representative package build.

No Owner, tools, subprocess, SDK, signer, VM, HDC, QMP, archive extraction,
network, caller compilation or capability verdict. Root supplies real immutable
exports. Actual installed BMS/HAP/API/UI/frames/callbacks and cleanup are checked
later by the original held-guest stage, never by this input assembler.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

ASR_RUNTIME_SHA = 'bf465a9dd0296023d7b9c7703e76acf9e174f6049eaa8eb207eb3b9c86faa517'
ASR_ASSETS_SHA = '601c869bb39fc8cc3aff277a37a65618dd9f406074ad1530b58b8be34366bc95'
LIBRARIES = {'libsherpa_onnx.so', 'libsherpa-onnx-c-api.so', 'libonnxruntime.so', 'libc++_shared.so'}
PROVIDERS = {
    'notification-settings': ('com.ohos.sceneboard', 'NotificationManangerUIExtensionAbility'),
    'notification-subscription': ('com.ohos.sceneboard', 'NotificationAccessGrantUIExtensionAbility'),
    'intelligent-scene': ('com.ohos.intelligentscene', 'IntelligentSceneUIExtSettingAbility'),
    'intelligent-scene-settings': ('com.ohos.settings', 'IntelligentSceneAppSelectExtensionAbility'),
    'network-policy': ('com.ohos.communicationsetting', 'UIExtensionProvider'),
    'accessibility-settings': ('com.ohos.settings', 'com.ohos.settings.MainAbility'),
    'certificate-dialog': ('com.ohos.certmanager', 'CertPickerUIExtAbility'),
    'enterprise': ('com.ohos.adminprovisioning', 'ByodAdminProvisionAbility'),
    'apn': ('com.ohos.callsetting', 'GeneralCallSettingDialogAbility'),
}
PLANS = {
    'notification-settings': 'notification-settings-en_US.json',
    'notification-subscription': 'notification-subscription-boundary.json',
    'intelligent-scene': 'intelligent-scene-current-en_GB.json',
    'network-policy': 'network-policy-current.json',
    'certificate-dialog': 'certificate-dialog-en_US.json',
    'enterprise': 'enterprise-zh_CN.json',
    'apn': 'apn-base.json',
    'shortkey': 'shortkey.json',
}
HELPERS = {
    'communications578_at_peer': 'ci/capability-audit/communications578_at_peer.c',
    'communications578_permission_controller': 'ci/capability-audit/communications578/PermissionController.cpp',
    'apps579_wifi_peer': 'ci/capability-audit/apps_providers579/wifi_peer.c',
    'settings_idle579_napi': 'ci/capability-audit/settings_idle579/native/SettingsIdleNative.cpp',
    'apn579_modem_peer': 'ci/capability-audit/apn579_modem_peer.c',
    'apps_paired579_net': 'ci/capability-audit/apps_paired579/paired_net.c',
    'alsa_inject': 'ci/capability-audit/batch_media_alsa_inject.c',
}
CONSUMERS = (
    'ci/capability-audit/capability578_stage.py',
    'ci/capability-audit/capability578_owned_io.py',
    'ci/capability-audit/capability578_callers.py',
    'ci/capability-audit/capability578_certificate.py',
    'ci/capability-audit/apps_ui578_contract.py',
    'ci/capability-audit/apps_ui578_runtime.py',
    'ci/capability-audit/apps_ui578_bindings.py',
    'ci/capability-audit/apps_ui578_verify.py',
    'ci/capability-audit/apps_ui578_project.py',
    'ci/capability-audit/apps_ui578_extra.py',
    'ci/capability-audit/apps_ui578_apn.py',
    'ci/capability-audit/apps_ui578_apn_verify.py',
    'ci/capability-audit/apps_ui578_ca.py',
    'ci/capability-audit/apps_ui578_ca_verify.py',
    'ci/capability-audit/apps_ui578/ApnProgram.ets',
    'ci/capability-audit/apps_ui578/CertificateProgram.ets',
    'ci/capability-audit/apps_ui578/ProviderPage.ets',
    'ci/capability-audit/apps_ui578/ui_plans/certificate-dialog-base.json',
    'ci/capability-audit/apps_ui578/ui_plans/certificate-dialog-en_US.json',
    'ci/capability-audit/apps_ui578/ui_plans/apn-base.json',
    'ci/capability-audit/apps_providers579_wifi_bindings.py',
    'ci/capability-audit/apps_providers579_wifi_runtime.py',
    'ci/capability-audit/system_services578_bindings.py',
    'ci/capability-audit/system_services578_runtime.py',
    'ci/capability-audit/settings_idle579_bindings.py',
    'ci/capability-audit/settings_idle579_runtime.py',
    'ci/capability-audit/livecaptions579_bindings.py',
    'ci/capability-audit/livecaptions579_runtime.py',
    'ci/capability-audit/livecaptions579_provider_project.py',
    'ci/capability-audit/batch_system_build_runtime_helpers.py',
    'ci/capability-audit/apn579_owned_bindings.py',
    'ci/capability-audit/apn579_owned_runtime.py',
    'ci/capability-audit/apn579_owned_oracle.py',
    'ci/capability-audit/apps_paired579_bindings.py',
    'ci/capability-audit/apps_paired579_runtime.py',
)
COMMON = {'archive', 'source_commit', 'package_receipt', 'build_inputs'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate JSON key: ' + key)
        value[key] = item
    return value


def document(data):
    return json.loads(data, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('non-finite JSON number')))


def regular(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and path.is_file() and
        not any(item.is_symlink() for item in (path, *path.parents)), 'real ordinary absolute input required')
    return path


def digest(path):
    state = hashlib.sha256()
    with regular(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            state.update(block)
    return state.hexdigest()


def checked_ref(value):
    require(type(value) is dict and set(value) in ({'path', 'sha256'}, {'path', 'sha256', 'bytes'}) and
        type(value['path']) is str and re.fullmatch('[a-f0-9]{64}', value['sha256'] or ''),
        'actual immutable Ref required; no missing-input placeholder')
    path = regular(value['path'])
    require(digest(path) == value['sha256'], 'input artifact changed: ' + str(path))
    if 'bytes' in value:
        require(type(value['bytes']) is int and path.stat().st_size == value['bytes'], 'input length differs')
    # Several original consumers compare reference(path) with exactly two keys.
    return {'path': str(path), 'sha256': value['sha256']}


def ref(path):
    return {'path': str(regular(path)), 'sha256': digest(path)}


def raw(value):
    return regular(checked_ref(value)['path']).read_bytes()


def json_ref(value):
    data = raw(value)
    require(0 < len(data) <= 32 * 1024 * 1024, 'bounded actual JSON export required')
    return document(data)


def recipe(root, relative, build):
    require(relative in build['files_sha256'], 'new package did not freeze required recipe: ' + relative)
    actual = ref(root / relative)
    require(actual['sha256'] == build['files_sha256'][relative],
        'runtime recipe/plan differs from the actual new package snapshot: ' + relative)
    return actual


def common(export, schema, package=None):
    require(type(export) is dict and export.get('schema') == schema and COMMON <= set(export),
        'fixed original-root export schema required')
    current = {key: checked_ref(export[key]) for key in ('archive', 'package_receipt', 'build_inputs')}
    current['source_commit'] = export['source_commit']
    require(type(current['source_commit']) is str and re.fullmatch('[a-f0-9]{40}', current['source_commit']),
        'actual package source commit required')
    require(json_ref(current['package_receipt']), 'original actual package receipt is empty')
    if package is not None:
        require(current == package, 'root exports do not belong to the exact same new package/build/receipt')
    return current


def hap_metadata(value):
    path = regular(checked_ref(value)['path'])
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist(); names = [row.filename for row in members]
        require(len(members) <= 30000 and len(names) == len(set(names)) and
            sum(row.file_size for row in members) <= 1024 * 1024 * 1024, 'bounded complete actual HAP required')
        for row in members:
            relative = PurePosixPath(row.filename)
            require(not relative.is_absolute() and '..' not in relative.parts and '\\' not in row.filename and
                not row.flag_bits & 1 and stat.S_IFMT(row.external_attr >> 16) != stat.S_IFLNK,
                'unsafe actual HAP member')
        require({'module.json', 'ets/modules.abc', 'resources.index'} <= set(names) and
            archive.read('ets/modules.abc') and archive.read('resources.index'), 'actual HAP ABC/resources missing')
        require(archive.getinfo('module.json').file_size <= 4 * 1024 * 1024, 'bounded HAP metadata required')
        value = document(archive.read('module.json'))
        require(type(value) is dict and type(value.get('app')) is dict and type(value.get('module')) is dict,
            'actual compiled module metadata required')
        return value


def provider_inputs(export):
    require(set(export) == COMMON | {'schema', 'package_manifest', 'providers', 'hap_exports', 'caption_provider_hap'},
        'finite package export required; JSON cannot choose code or an alternative provider')
    require(type(export['hap_exports']) is list and 1 <= len(export['hap_exports']) <= 128,
        'original root selected/staged HAP export inventory required')
    inventory = {}; paths = set()
    for row in export['hap_exports']:
        require(type(row) is dict and set(row) == {'package_path', 'hap'}, 'exact original HAP export row required')
        name = row['package_path']
        require(type(name) is str and name.startswith(('/system/app/', '/system_ext/app/', '/sys_prod/app/')) and
            '..' not in PurePosixPath(name).parts and '\\' not in name and '\n' not in name and
            PurePosixPath(name).suffix == '.hap' and name not in paths, 'literal selected package HAP path required')
        paths.add(name); actual = checked_ref(row['hap']); key = (actual['path'], actual['sha256'])
        require(key not in inventory, 'ambiguous original HAP export origin')
        inventory[key] = {'package_path': name, 'metadata': hap_metadata(actual)}
    require(type(export['providers']) is dict and set(export['providers']) == set(PROVIDERS),
        'all fixed Apps provider groups required; missing providers cannot be fabricated')
    providers = {}; declarations = {}
    for case, (bundle, target) in PROVIDERS.items():
        value = export['providers'][case]
        require(type(value) is dict and set(value) == {'bundle', 'modules'} and value['bundle'] == bundle and
            type(value['modules']) is dict and value['modules'], 'fixed literal provider group required: ' + case)
        result = {'bundle': bundle, 'modules': {}}; found = []
        for module, row in value['modules'].items():
            require(re.fullmatch('[A-Za-z0-9_]{1,80}', module) and type(row) is dict and set(row) == {'hap'},
                'actual module name/HAP row required')
            hap = checked_ref(row['hap']); key = (hap['path'], hap['sha256'])
            require(key in inventory, 'provider HAP is not in the original new-package selected export')
            info = inventory[key]['metadata']
            require(info['app'].get('bundleName') == bundle and info['module'].get('name') == module,
                'caller-supplied bundle/module does not match actual HAP metadata')
            found += [row for row in info['module'].get('abilities', []) +
                info['module'].get('extensionAbilities', []) if row.get('name') == target]
            result['modules'][module] = {'hap': hap}
        # Absence is retained as data for the existing missing-AccessGrant
        # boundary plan, never filled with SystemUI or a fabricated module.
        require(len(found) <= 1 and (found or case == 'notification-subscription'),
            'actual new package lacks required provider entry: ' + case)
        declarations[case] = {'target': target, 'actual_declarations': found}
        providers[case] = result
    captions = checked_ref(export['caption_provider_hap'])
    require((captions['path'], captions['sha256']) in inventory, 'caption provider is not a real selected export')
    info = inventory[(captions['path'], captions['sha256'])]['metadata']
    targets = info['module'].get('extensionAbilities', [])
    require(info['app'].get('bundleName') == 'com.ohos.vassistant' and info['module'].get('name') == 'entry' and
        len(targets) == 1 and targets[0].get('name') == 'AiCaptionServiceExtAbility' and
        targets[0].get('type') == 'service', 'actual full English caption provider required')
    return providers, captions, declarations


def elf_arm64(value, shared=False):
    data = raw(value)
    require(len(data) >= 64 and data[:6] == b'\x7fELF\x02\x01' and
        int.from_bytes(data[18:20], 'little') == 183 and
        int.from_bytes(data[16:18], 'little') in ((3,) if shared else (2, 3)),
        'actual ARM64 product helper/addon ELF required; no host or foreign-ABI fallback')


def native_inputs(export, package, root, build):
    common(export, 'actual-root-capability579-native-export/v1', package)
    require(set(export) == COMMON | {'schema', 'build'}, 'fixed original helper batch export required')
    build_ref = checked_ref(export['build']); report = json_ref(build_ref)
    require(report.get('status') == 'pass_compile_link_ONLY' and report.get('plan_only') is False and
        report.get('product') == 'arm64_virt' and type(report.get('helpers')) is dict and
        set(HELPERS) <= set(report['helpers']) and report.get('commands') and
        report.get('first_artifact_behavior_gate_passed') is False,
        'actual original completed product helper build required; plan/recheck/runtime summaries cannot replace it')
    runtime = report['installed_runtime_profile']['profile']
    require(checked_ref({key: runtime['archive'][key] for key in ('path', 'sha256')}) == package['archive'],
        'native helpers were built against another package installed-runtime profile')
    require(report['builder_sha256'] == recipe(root, 'ci/capability-audit/batch_system_build_runtime_helpers.py', build)['sha256'],
        'helper batch used another builder source')
    for row in report['commands']:
        require(type(row.get('argv')) is list and row['argv'] and row.get('exit_code') == 0 and
            not row.get('timed_out') and digest(row['log']) == row['sha256'], 'original helper command/raw receipt incomplete')
    helpers = {}
    for name, relative in HELPERS.items():
        row = report['helpers'][name]
        source = {key: row['source'][key] for key in ('path', 'sha256')}
        require(checked_ref(source)['sha256'] == recipe(root, relative, build)['sha256'] and
            row.get('status') == 'pass_compile_link_ONLY' and row.get('runtime_validated') is False and
            row.get('CFI_preserved') is True, 'actual fixed source/ABI-preserving helper build missing: ' + name)
        binary = checked_ref({'path': row['binary'], 'sha256': row['binary_sha256']})
        elf_arm64(binary, shared=name == 'settings_idle579_napi')
        helpers[name] = {'binary': binary, 'build': build_ref}
    wifi = dict(helpers['apps579_wifi_peer'], source=checked_ref({key: report['helpers']['apps579_wifi_peer']['source'][key]
        for key in ('path', 'sha256')}), abi='arm64')
    native = {'communications578': {'at_peer': helpers['communications578_at_peer'],
        'permission_controller': helpers['communications578_permission_controller']}, 'apps579_wifi': wifi}
    native['apn579'] = {'modem_peer': helpers['apn579_modem_peer']}
    for key, name in (('apps_paired579', 'apps_paired579_net'), ('apps_paired579_alsa', 'alsa_inject')):
        native[key] = dict(helpers[name], source=checked_ref({field: report['helpers'][name]['source'][field]
            for field in ('path', 'sha256')}), abi='arm64')
    addons = {'settings_idle579': dict(helpers['settings_idle579_napi'], abi='arm64-v8a')}
    return native, addons, build_ref


def services_inputs(export, package):
    common(export, 'actual-root-capability579-services-export/v1', package)
    require(set(export) == COMMON | {'schema', 'services', 'init_files', 'library_files'} and
        set(export['services']) == set(export['init_files']) == {'ril', 'bluetooth'} and
        type(export['library_files']) is dict, 'both actual original init/service exports required')
    result = {}
    used_libraries = set()
    for kind in ('ril', 'bluetooth'):
        value = export['services'][kind]
        require(type(value) is dict and set(value) == {'name', 'init_path', 'process_name', 'libraries'} and
            all(re.fullmatch('[A-Za-z0-9_-]{1,64}', value[key] or '') for key in ('name', 'process_name')) and
            re.fullmatch(r'/(?:system|vendor)/etc/init/[A-Za-z0-9_.-]+\.cfg', value['init_path'] or '') and
            type(value['libraries']) is list and value['libraries'] and
            len(value['libraries']) == len(set(value['libraries'])) and
            all(re.fullmatch(r'lib[A-Za-z0-9_.-]+\.so', library) for library in value['libraries']),
            'actual finite service fields required; no default service name')
        source = export['init_files'][kind]
        require(set(source) == {'guest_path', 'file'} and source['guest_path'] == value['init_path'],
            'service config must be the actual exported package init path')
        config = json_ref(source['file']); matches = [row for row in config['services'] if row.get('name') == value['name']]
        require(len(matches) == 1, 'actual selected init file does not contain this service')
        service = matches[0]
        if kind == 'ril':
            require(service['name'] == 'riladapter_host' and service['uid'] == 'radio' and
                service['secon'] == 'u:r:riladapter_host:s0' and service['path'][0] == '/vendor/bin/hdf_devhost' and
                service['path'][-2:] == ['-n', 'riladapter_host'] and set(value['libraries']) >=
                {'libril_driver.z.so', 'libril_service_1.5.z.so', 'libhril_hdf.z.so', 'libhril.z.so', 'libril_vendor.z.so'},
                'actual reference RIL service contract differs')
        else:
            require(service['name'] == 'bluetooth_service' and service['uid'] == 'bluetooth' and
                service['secon'] == 'u:r:bluetooth_service:s0' and
                service['path'] == ['/system/bin/sa_main', '/system/profile/bluetooth_service.json'],
                'actual reference Bluetooth service contract differs')
        for library in value['libraries']:
            used_libraries.add(library)
            item = export['library_files'][library]
            require(set(item) == {'guest_path', 'file'} and
                re.fullmatch(r'/(?:system|vendor)/lib64/(?:[A-Za-z0-9_.+-]+/)*' + re.escape(library), item['guest_path']),
                'actual packaged service DSO location required')
            elf_arm64(item['file'], shared=True)
        result[kind] = value
    require(set(export['library_files']) == used_libraries, 'unexpected or missing service library export')
    return result


def caption_inputs(runtime_ref, assets_ref, archive, provider):
    runtime_ref, assets_ref = checked_ref(runtime_ref), checked_ref(assets_ref)
    require(runtime_ref['sha256'] == ASR_RUNTIME_SHA and assets_ref['sha256'] == ASR_ASSETS_SHA,
        'exact root-produced r66 caption input DATA required; no generated expected transcript')
    value, assets = json_ref(runtime_ref), json_ref(assets_ref)
    require(assets['language'] == 'en' and assets['model'] == 'whisper-tiny.en' and
        checked_ref(value['admission']) == assets_ref and set(value['speech']) == {'a', 'b'} and
        set(value['libraries']['arm64-v8a']) == LIBRARIES, 'actual admitted English model/speech closure required')
    for group in ('assets', 'licenses'):
        for item in assets[group].values():
            checked_ref(item)
    checked_ref(assets['source_production_receipt'])
    for speaker in ('a', 'b'):
        item = value['speech'][speaker]
        require(set(item) == {'audio', 'license', 'groundtruth', 'utterance_id', 'contains'},
            'unchanged actual r66 speech DATA required')
        for field in ('audio', 'license', 'groundtruth'):
            checked_ref(item[field])
    libraries = {name: checked_ref(item) for name, item in value['libraries']['arm64-v8a'].items()}
    with zipfile.ZipFile(provider['path']) as hap:
        for library, item in libraries.items():
            require(hap.read('libs/arm64-v8a/' + library) == raw(item),
                'new selected caption provider contains different native inference bytes')
        for name, member in {'encoder': 'resources/rawfile/sherpa-onnx-whisper-tiny.en/tiny.en-encoder.int8.onnx',
            'decoder': 'resources/rawfile/sherpa-onnx-whisper-tiny.en/tiny.en-decoder.int8.onnx',
            'tokens': 'resources/rawfile/sherpa-onnx-whisper-tiny.en/tiny.en-tokens.txt',
            'vad': 'resources/rawfile/silero_vad.onnx', 'notices': 'resources/rawfile/LIVE_CAPTIONS_NOTICES.txt'}.items():
            require(hashlib.sha256(hap.read(member)).hexdigest() == assets['assets'][name]['sha256'],
                'new selected caption provider model/notices bytes differ')
    return {'archive_sha256': archive['sha256'], 'language': 'en', 'model': 'whisper-tiny.en',
        'abi': 'arm64-v8a', 'admission': assets_ref, 'provider_hap': provider,
        'libraries': libraries, 'speech': value['speech']}


def assemble(request_ref, recipes, profile, output):
    request_ref = checked_ref(request_ref); request = json_ref(request_ref)
    require(type(request) is dict and set(request) == {'schema', 'package_export', 'native_export',
        'services_export', 'caption_runtime_data', 'caption_product_assets', 'permission_ui'} and
        request['schema'] == 'actual-root-capability579-input-request/v1', 'finite input-only assembly request required')
    package_export = json_ref(request['package_export'])
    package = common(package_export, 'actual-root-capability579-package-export/v1')
    build = json_ref(package['build_inputs'])
    require(build.get('schema_version') == 1 and build.get('source_git_revision') == package['source_commit'] and
        type(build.get('files_sha256')) is dict and build['tree_sha256'] == hashlib.sha256(
            json.dumps(build['files_sha256'], sort_keys=True).encode()).hexdigest(), 'actual complete build-input vector differs')
    manifest = json_ref(package_export['package_manifest'])
    require(manifest['product'] == 'arm64_virt' and manifest['guest_arch'] == 'arm64' and
        manifest['device_type'] == profile, 'this finite native addon is only the actual ARM64 phone/2in1 representative')
    require(recipes.is_absolute() and recipes.resolve() == recipes and recipes.is_dir() and
        not any(path.is_symlink() for path in (recipes, *recipes.parents)), 'actual frozen recipe directory required')
    pinned = {name: recipe(recipes, name, build) for name in CONSUMERS}
    plans = dict(PLANS, **{'accessibility-settings': 'accessibility-settings-' +
        ('phone' if profile == 'phone' else 'pc') + '-base.json'})
    ui_plans = {}
    for case, filename in plans.items():
        relative = 'ci/capability-audit/apps_ui578/ui_plans/' + filename
        item = recipe(recipes, relative, build); value = json_ref(item)
        require(value['kind'] == case and value['schema'] ==
            ('actual-apps578-missing-provider-boundary/v1' if case == 'notification-subscription' else 'actual-packaged-apps578-ui/v1'),
            'current fixed UI plan schema/kind differs')
        for source in value['source_files']:
            checked_ref(source)
        ui_plans[case] = item
    providers, captions, declarations = provider_inputs(package_export)
    native, addons, helper_build = native_inputs(json_ref(request['native_export']), package, recipes, build)
    services = services_inputs(json_ref(request['services_export']), package)
    permission = request['permission_ui']
    require(type(permission) is dict and set(permission) == {'allow_text', 'source'} and
        type(permission['allow_text']) is str and 0 < len(permission['allow_text']) <= 128 and
        '\n' not in permission['allow_text'] and checked_ref(permission['source']),
        'root actual source-backed permission UI selector required; no default Allow label')
    captions = caption_inputs(request['caption_runtime_data'], request['caption_product_assets'], package['archive'], captions)
    value = {'schema': 'actual-qemu-capability578-inputs/v1', 'source_commit': package['source_commit'],
        'archive': package['archive'], 'providers': providers, 'native_helpers': native,
        'native_addons': addons, 'ui_plans': ui_plans, 'communications_services': services,
        'permission_allow_text': permission['allow_text'], 'livecaptions579': captions}
    provenance = {'schema': 'actual-root-capability579-input-assembly/v1', 'request': request_ref,
        'package': package, 'package_manifest': checked_ref(package_export['package_manifest']),
        'package_export': checked_ref(request['package_export']), 'native_export': checked_ref(request['native_export']),
        'services_export': checked_ref(request['services_export']), 'helper_build': helper_build,
        'caption_runtime_data': checked_ref(request['caption_runtime_data']),
        'caption_product_assets': checked_ref(request['caption_product_assets']), 'permission_ui': permission,
        'source_consumers': pinned, 'provider_declarations': declarations,
        'scope': 'input DATA assembly only; origin remains original root export receipts and actual guest binding',
        'runtime_validated': False, 'formally_closed': [], 'first_artifact_behavior_gate_passed': False}
    require(output.is_absolute() and output.parent.is_dir() and output.resolve() == output and
        not any(path.is_symlink() for path in (output, *output.parents)) and not output.exists(),
        'fresh original-root output directory required')
    # Every input is admitted before the fresh output is created. No caller,
    # executable, signing permission, result, boot ID or expected UID is made.
    output.mkdir(mode=0o700)
    path = output / 'capability578-inputs.json'
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    provenance['output'] = ref(path)
    with (output / 'assembly.json').open('x') as stream:
        stream.write(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n')
    return provenance['output']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--request-sha256', required=True)
    parser.add_argument('--recipes-root', type=Path, required=True)
    parser.add_argument('--profile', choices=('phone', '2in1'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(assemble({'path': str(arguments.request), 'sha256': arguments.request_sha256},
        arguments.recipes_root, arguments.profile, arguments.output), indent=2))
