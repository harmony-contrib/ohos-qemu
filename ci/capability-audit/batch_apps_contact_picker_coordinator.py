#!/usr/bin/env python3
"""Sign, install and independently verify Contacts in the suite's fresh guest.

This wrapper does not build, boot, seed a database, grant a permission with bm,
or decide the enclosing first-artifact gate. Public test keys are intentional.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shlex
import struct
import subprocess
import sys
import tempfile
import time
import zipfile

import batch_apps_contact_picker_runtime as verifier
import batch_apps_run_contact_picker_runtime as driver
from check_m144_core_package import verified_profile_content
from enclosing_acceptance_guest import EnclosingAcceptanceGuest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HEX = re.compile('[0-9a-f]{64}')
APP_LEAF = '8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5'
PROFILE_LEAF = '8F6EABDB9ED89D86C5AF6884E6AF834569C1962DD9FC145BD33922609AA5AD43'
SIGNER_INPUTS = {
    'hap-sign-tool.jar': 'a434b6747e6c5d0b14e73837a46b39f4816ab25b42d1833d6f767bf867cf616d',
    'OpenHarmonyApplication.pem': 'b5c1d6254faa91eab645a32fc3ce136128c94d88a739a0e956e6a49b331387e5',
    'OpenHarmonyProfileDebug.pem': 'a7232bdad96a24bf8c5ac3460cd8163b4af605e38ce8a14d9381572ce1ea0344',
    'UnsgnedDebugProfileTemplate.json': 'e7793d8501b56137b625e66ae8ff832adbbaf95b6e7c8440282c9423d174d16f',
}
FULL_BOUNDARY_CASES = ('deadline', 'navigation-dismiss')
descriptor = driver.descriptor
write_json = driver.write_json
require = verifier.require


def regular(path):
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), 'absolute regular input required: ' + str(path))
    return path.resolve()


def checked_artifact(value):
    path = regular(value['path'])
    require(HEX.fullmatch(value['sha256']) and verifier.sha(path) == value['sha256'], 'input artifact hash differs: ' + str(path))
    return path


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def load(path):
    return json.loads(regular(path).read_text(), object_pairs_hook=unique)


def hap_contents(path):
    """Compare actual compiled payload, not a caller-supplied description."""
    with zipfile.ZipFile(regular(path)) as archive:
        entries = archive.infolist()
        require(len(entries) <= 10000 and sum(e.file_size for e in entries) <= 256 * 1024 * 1024, 'HAP archive exceeds bounds')
        contents = {}
        for entry in entries:
            name = entry.filename; p = PurePosixPath(name)
            require(name not in contents and not p.is_absolute() and '..' not in p.parts and '\\' not in name and
                    p.as_posix() == name.rstrip('/') and not entry.flag_bits & 1 and entry.file_size <= 64 * 1024 * 1024 and
                    (entry.external_attr >> 16) & 0o170000 != 0o120000, 'unsafe or duplicate HAP member')
            contents[name] = hashlib.sha256(archive.read(entry)).hexdigest()
        require({'module.json', 'ets/modules.abc', 'resources.index'} <= contents.keys(), 'real compiled HAP required')
        require(archive.getinfo('ets/modules.abc').file_size > 0 and archive.getinfo('resources.index').file_size > 0,
                'empty compiled HAP payload')
        module = json.loads(archive.read('module.json'), object_pairs_hook=unique)
    return module, contents


def ordinary_hap(path, bundle, permissions):
    value, contents = hap_contents(path)
    module = value['module']
    require(value['app'].get('bundleName') == bundle and value['app'].get('debug') is False and
            module.get('name') == 'entry' and module.get('type') == 'entry' and
            module.get('extensionAbilities', []) == [] and module.get('dependencies', []) == [], 'ordinary app module identity differs')
    requests = module.get('requestPermissions', [])
    require(len(requests) == len(permissions) and sorted(row['name'] for row in requests) == sorted(permissions),
            'ordinary app permission surface differs')
    require(len(module.get('abilities', [])) == 1 and module['abilities'][0].get('name') == 'EntryAbility',
            'ordinary EntryAbility required')
    return contents


def source_rows(evidence, project):
    rows = evidence['source_files']
    if isinstance(rows.get(project), dict):
        return rows[project]
    return {key[len(project) + 1:]: value for key, value in rows.items() if key.startswith(project + '/')}


def verify_sdk_project(spec, *, fixture=None, source_manifest=None, module_name=None):
    """A successful project may belong to a failed multi-project batch."""
    evidence_path = checked_artifact(spec['sdk_evidence']); evidence = load(evidence_path)
    project = spec['sdk_project']; source = Path(spec['source_project'])
    require(re.fullmatch('[A-Za-z0-9_-]{1,80}', project) and source.is_absolute() and source.is_dir() and not source.is_symlink(),
            'actual SDK project required')
    require(type(evidence.get('exit_code')) is int and re.fullmatch('[0-9a-f]{40}', evidence.get('source_commit', '')) and
            HEX.fullmatch(evidence.get('runner_sha256', '')), 'actual SDK batch provenance absent')
    rows = source_rows(evidence, project)
    require(module_name is None or project == 'theme' and module_name in ('phone_wallpaper', 'pad_wallpaper'),
            'only explicit actual Theme product modules may select a shared SDK project')
    product_directory = ('product/' + ('phone' if module_name == 'phone_wallpaper' else 'pad')) if module_name else 'entry'
    require(rows and product_directory + '/src/main/module.json5' in rows, 'SDK project source inventory absent')
    for name, expected in rows.items():
        p = PurePosixPath(name)
        require(not p.is_absolute() and '..' not in p.parts and p.as_posix() == name and '\\' not in name,
                'unsafe SDK source path')
        path = regular(source / name)
        require(path.is_relative_to(source.resolve()) and HEX.fullmatch(expected) and verifier.sha(path) == expected,
                'SDK source changed after compilation: ' + name)
    commands = [row for row in evidence['commands'] if row.get('project') == project]
    require(commands and all(type(row.get('exit_code')) is int and row['exit_code'] == 0 for row in commands),
            'this SDK project has a failed or incomplete command')
    def selected_compile(row):
        argv = row.get('argv', [])
        if 'assembleHap' not in argv: return False
        if module_name is None: return True
        selected = 'module=' + module_name
        return ([flag for flag in argv if flag.startswith('module=')] == [selected] and
                argv.index(selected) > 0 and argv[argv.index(selected) - 1] == '-p')
    compile_rows = [row for row in commands if selected_compile(row)]
    require(len(compile_rows) == 1, 'one actual project assembleHap command required')
    for row in commands:
        log = checked_artifact({'path': row['log'], 'sha256': row['sha256']})
        if row is compile_rows[0]:
            require(re.search(r'BUILD SUCCESSFUL', log.read_text(errors='replace')), 'actual Hvigor success log absent')
    hap = checked_artifact(spec['unsigned_hap'])
    # Older provider reports do not have project on the HAP row; match the
    # real path under this already-verified source project in that format.
    haps = [row for row in evidence['haps'] if row.get('project') == project or
            ('project' not in row and Path(row['path']).resolve().is_relative_to(source.resolve()))]
    if module_name is not None:
        haps = [row for row in haps if Path(row['path']).resolve().is_relative_to((source / product_directory).resolve())]
    require(len(haps) == 1 and checked_artifact(haps[0]) == hap and haps[0].get('bytes') == hap.stat().st_size,
            'SDK HAP artifact/project binding differs')
    if fixture is not None:
        manifest = checked_artifact(spec['source_manifest'])
        require(manifest == (source / source_manifest).resolve() and source_manifest in rows and
                load(manifest).get('fixture_hashes') == {p.name: verifier.sha(p) for p in sorted(fixture.iterdir()) if p.is_file()},
                'compiled source fixture manifest differs')
        for p in fixture.glob('*.ets'):
            targets = [name for name in rows if name.endswith('/' + p.name)]
            require(len(targets) == 1 and rows[targets[0]] == verifier.sha(p), 'actual compiled ETS differs from frozen fixture: ' + p.name)
    hap_contents(hap)
    return {'sdk_evidence': descriptor(evidence_path), 'sdk_project': project, 'batch_exit_code': evidence['exit_code'],
            'project_commands_verified': len(commands), 'source_files_verified': len(rows), 'unsigned_hap': descriptor(hap)}


def signer_inputs(signer_dist, signer_jar=None):
    dist = Path(signer_dist).resolve(); jar = regular(signer_jar or dist / 'hap-sign-tool.jar')
    result = {}
    for name, expected in SIGNER_INPUTS.items():
        path = jar if name == 'hap-sign-tool.jar' else regular(dist / name)
        require(verifier.sha(path) == expected, 'fixed public signer input differs: ' + name)
        result[name] = descriptor(path)
    return dist, jar, result


def application_leaf(log):
    sections = re.split(r'certificate #0\b', log, maxsplit=1)
    require(len(sections) == 2, 'actual verify-app leaf certificate absent')
    leaf = re.split(r'certificate #1\b', sections[1], maxsplit=1)[0]
    values = re.findall(r'SHA256:\s*([0-9A-Fa-f:]+)', leaf)
    require(len(values) == 1 and values[0].replace(':', '').upper() == APP_LEAF, 'actual application signer leaf differs')


def verify_profile(profile, bundle, permissions, udid, *, apl='normal', system_app=False):
    require(apl in ('normal', 'system_basic') and system_app == (apl == 'system_basic'), 'explicit narrow app profile role required')
    require(re.fullmatch('[0-9a-fA-F]{64}', udid), 'fresh guest UDID required')
    info = profile['bundle-info']; validity = profile['validity']; now = int(time.time())
    require(profile.get('type') == 'debug' and info.get('bundle-name') == bundle and info.get('apl') == apl and
            info.get('app-feature') == ('hos_system_app' if system_app else 'hos_normal_app') and
            profile.get('debug-info', {}).get('device-ids') == [udid] and
            profile.get('acls', {}).get('allowed-acls') == [] and
            profile.get('permissions', {}).get('restricted-permissions') == [] and
            type(validity.get('not-before')) is int and type(validity.get('not-after')) is int and
            validity['not-before'] <= now < validity['not-after'], 'signed profile identity/UDID/ACL/validity differs')
    # User-grant permissions live in module.json, never in restricted ACLs.
    require(len(permissions) == len(set(permissions)), 'duplicate expected permission')


def verify_signed_hap_artifacts(signed, bundle, permissions, udid, signer_dist, signer_jar, output, command,
                                *, apl='normal', system_app=False):
    """Reusable actual Java/CMS verifier; command(argv, label) must fail on exit != 0.

    Wallpaper may use system_basic/hos_system_app with its exact module permission
    set and empty ACL/restricted sets. This never grants special permissions.
    """
    signed = regular(signed); output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    dist, jar, inputs = signer_inputs(signer_dist, signer_jar)
    if not system_app: ordinary_hap(signed, bundle, permissions)
    else:
        module, _ = hap_contents(signed)
        require(module['app'].get('bundleName') == bundle and
                sorted(p['name'] for p in module['module'].get('requestPermissions', [])) == sorted(permissions),
                'system query exact bundle/permission surface differs')
    chain, profile = output / 'verified-chain.cer', output / 'verified-profile.p7b'
    argv = ['java', '-jar', str(jar), 'verify-app', '-inFile', str(signed), '-outCertChain', str(chain), '-outProfile', str(profile)]
    log = command(argv, 'verify-app')
    require(all(marker in log for marker in ('verify codesign success', 'Digest verify result: true',
                    'verify permission sign success', 'verify-app success')), 'actual code-sign/digest/permission verification missing')
    application_leaf(log); require(regular(chain).stat().st_size and regular(profile).stat().st_size, 'signature extraction empty')
    verified = output / 'verified-profile.json'
    result = command(['java', '-jar', str(jar), 'verify-profile', '-inFile', str(profile), '-outFile', str(verified)], 'verify-profile')
    require('verify-profile success' in result, 'actual verify-profile failed')
    value = verified_profile_content(load(verified))
    # Force CMS verification to use the fixed profile leaf, not an arbitrary
    # certificate embedded by the HAP. -noverify skips PKI dates, not signatures.
    certs = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',
                       (dist / 'OpenHarmonyProfileDebug.pem').read_text(), re.S)
    require(len(certs) == 3, 'fixed profile chain shape differs')
    leaf = output / 'profile-leaf.pem'; leaf.write_text(certs[-1] + '\n')
    fingerprint = command(['openssl', 'x509', '-in', str(leaf), '-noout', '-fingerprint', '-sha256'], 'profile-leaf-fingerprint')
    require(fingerprint.strip().split('=')[-1].replace(':', '').upper() == PROFILE_LEAF, 'profile leaf differs')
    cms = output / 'cms-profile.json'
    command(['openssl', 'cms', '-verify', '-inform', 'DER', '-in', str(profile), '-nointern', '-certfile', str(leaf),
             '-noverify', '-out', str(cms)], 'profile-CMS-signature')
    require(load(cms) == value, 'CMS decoded profile differs from Java verified content')
    verify_profile(value, bundle, permissions, udid, apl=apl, system_app=system_app)
    decoded = write_json(output / 'decoded-profile.json', value)
    proof = write_json(output / 'signature-verification.json', {'command': argv, 'exit_code': 0,
        'hap_sha256': verifier.sha(signed), 'decoded_profile_sha256': decoded['sha256'],
        'signer_inputs': inputs, 'application_signer_sha256': APP_LEAF, 'profile_signer_sha256': PROFILE_LEAF,
        'verified_chain': descriptor(chain), 'embedded_profile': descriptor(profile), 'verified_profile_report': descriptor(verified),
        'CMS_decoded_profile': descriptor(cms)})
    return {'signed_hap': descriptor(signed), 'decoded_profile': decoded, 'signature_verification': proof,
            'verified_profile': value}


def sign_normal_hap(unsigned, bundle, permissions, udid, signer_dist, signer_jar, output, command):
    unsigned = regular(unsigned); expected = ordinary_hap(unsigned, bundle, permissions)
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    dist, jar, _ = signer_inputs(signer_dist, signer_jar)
    signed = output / 'signed.hap'
    command([sys.executable, str(HERE / 'sign_web_probe.py'), '--signer-dist', str(dist), '--jar', str(jar),
             '--unsigned', str(unsigned), '--output', str(signed), '--bundle-name', bundle, '--udid', udid, '--sign-code', '1'], 'sign-normal-HAP')
    require(hap_contents(signed)[1] == expected, 'signing changed compiled HAP payload')
    proof = verify_signed_hap_artifacts(signed, bundle, permissions, udid, dist, jar, output / 'verification', command)
    proof['unsigned_hap'] = descriptor(unsigned)
    return proof


def witness_path(path, path_map):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'absolute unaliased helper witness path required')
    for prefix, destination in sorted(path_map.items(), key=lambda item: -len(item[0])):
        if path.is_relative_to(prefix): return Path(destination) / path.relative_to(prefix)
    return path


def witness_artifact(record, path_map):
    return checked_artifact({**record, 'path': str(witness_path(record['path'], path_map))})


def verify_observer(binary, receipt, path_map=None):
    binary = regular(binary); receipt = regular(receipt); report = load(receipt)
    path_map = path_map or {}
    require(not path_map or set(path_map) == {'/evidence/helpers', '/work'}, 'only the two explicit original helper prefix mappings are supported')
    for destination in path_map.values():
        p = Path(destination)
        require(p.is_absolute() and p.is_dir() and not p.is_symlink() and '..' not in p.parts, 'actual retained helper mapping directory required')
    require(report.get('plan_only') is False and report.get('product') == 'arm64_virt' and
            report.get('changed_inputs') == [], 'actual immutable product helper build required')
    builder = HERE / 'batch_system_build_runtime_helpers.py'
    require(builder.is_file() and report.get('builder_sha256') == verifier.sha(builder), 'helper builder source differs')
    row = report['helpers']['contact_picker_observer']; fixture = driver.FIX / 'observer.cpp'
    original = None
    if report.get('verify_existing') is True:
        origin = report['original_report']; original = load(witness_artifact(origin, path_map))
        require(origin.get('rewritten') is False and origin.get('status') == original.get('status') and
                original.get('plan_only') is False and original.get('product') == 'arm64_virt' and original.get('changed_inputs') == [] and
                original.get('builder_sha256') == origin.get('builder_sha256'), 'original helper build receipt changed')
        old = original['helpers']['contact_picker_observer']
        require(row.get('compile_command') == old.get('compile_command') and row.get('link_command') == old.get('link_command'),
                'helper recheck changed original compile/link command')
        reused = row['reused_artifacts']
        require(witness_artifact(reused['binary'], path_map) == binary and verifier.sha(witness_artifact(reused['source'], path_map)) == verifier.sha(fixture),
                'helper reused binary/source hash differs')
        row = {**old, **row}
    require(row.get('status') == 'pass_compile_link_ONLY' and row.get('fixture') == 'batch_apps/contact_picker_seed/observer.cpp' and
            row.get('private_source_sha256') == verifier.sha(fixture) and row['source']['sha256'] == verifier.sha(fixture) and
            row.get('binary_sha256') == verifier.sha(binary) and witness_path(row['binary'], path_map).resolve() == binary and row.get('CFI_preserved') is True,
            'actual helper source/binary/CFI binding differs')
    require(verifier.sha(witness_artifact(row['source'], path_map)) == verifier.sha(fixture), 'retained original helper fixture differs')
    for kind in ('compile', 'link'):
        commands = report['original_commands'] if original is not None else report['commands']
        rows = [c for c in commands if c.get('label') == 'contact_picker_observer-' + kind]
        require(len(rows) == 1 and rows[0].get('exit_code') == 0 and rows[0]['argv'] == row[kind + '_command'],
                'actual helper compile/link command failed or differs')
        if original is not None:
            old_commands = [c for c in original['commands'] if c.get('label') == rows[0]['label']]
            require(len(old_commands) == 1 and all(rows[0][key] == old_commands[0][key] for key in ('argv', 'exit_code', 'sha256', 'log')),
                    'helper original compile/link receipt differs')
            require(rows[0]['verified_log']['sha256'] == rows[0]['sha256'], 'helper original log SHA differs')
            witness_artifact(rows[0]['verified_log'], path_map)
        else:
            witness_artifact({'path': rows[0]['log'], 'sha256': rows[0]['sha256']}, path_map)
    elf_commands = [c for c in report['commands'] if c.get('label') == 'contact_picker_observer-actual-ELF-ABI']
    require(len(elf_commands) == 1 and elf_commands[0].get('exit_code') == 0 and
            Path(elf_commands[0]['argv'][0]).name == 'llvm-readelf' and witness_path(elf_commands[0]['argv'][-1], path_map).resolve() == binary,
            'actual helper ELF recheck missing')
    elf_log = witness_artifact({'path': elf_commands[0]['log'], 'sha256': elf_commands[0]['sha256']}, path_map).read_text()
    require('__cfi_check' in elf_log and 'std::__h::' in elf_log and 'std::__n1::' not in elf_log,
            'actual helper ELF ABI/CFI evidence missing')
    require(row.get('anchors') and row.get('actual_compiler_dependencies') and row.get('actual_link_inputs') and
            {'libapp_manager.z.so', 'libaccesstoken_sdk.z.so'} <= set(row.get('DT_NEEDED', [])), 'helper actual innerkit/header/link evidence missing')
    compile_argv = row['compile_command']; link_argv = row['link_command']
    require('--target=aarch64-linux-ohos' in compile_argv and '-fno-exceptions' in compile_argv and
            '-fsanitize-cfi-cross-dso' in compile_argv and any(x.startswith('-fsanitize=') and 'cfi' in x for x in compile_argv) and
            '-pie' in link_argv and (original is not None or witness_path(link_argv[link_argv.index('-o') + 1], path_map).resolve() == binary),
            'helper product ABI/CFI command missing')
    compiled_source = witness_artifact(row['reused_artifacts']['source'], path_map) if original is not None else regular(witness_path(compile_argv[compile_argv.index('-c') + 1], path_map))
    require(verifier.sha(compiled_source) == verifier.sha(fixture), 'actual helper compiled source differs from frozen observer')
    data = binary.read_bytes()
    require(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01' and
            struct.unpack_from('<HH', data, 16) == (3, 183), 'actual ARM64 PIE ELF required')
    offset = struct.unpack_from('<Q', data, 32)[0]; size, count = struct.unpack_from('<HH', data, 54)
    require(size == 56 and count > 0 and offset + size * count <= len(data), 'helper real program headers absent')
    interpreters = []; executable = False
    for i in range(count):
        kind, flags, start, _, _, length, _, _ = struct.unpack_from('<IIQQQQQQ', data, offset + i * size)
        require(start + length <= len(data), 'helper program segment exceeds ELF')
        if kind == 3: interpreters.append(data[start:start + length].rstrip(b'\0').decode('ascii'))
        executable |= kind == 1 and bool(flags & 1) and length > 0
    require(interpreters == ['/lib/ld-musl-aarch64.so.1'] and executable, 'helper actual guest loader/code absent')
    return {'binary': descriptor(binary), 'receipt': descriptor(receipt), 'source_sha256': verifier.sha(fixture),
            'path_map': path_map, 'container_product_inputs_rechecked_by_builder_only': True, 'runtime_validated': False}


def verify_provider_release_profile(profile, source_project, provider_name, signer_dist, output, command):
    """Recompute exact original OS release policy using fixed public issuers."""
    sys.path.insert(0, str(ROOT / 'scripts'))
    image_guard = importlib.import_module('verify_contacts_theme_provider_image')
    require(provider_name in ('contacts', 'theme'), 'fixed source provider role required')
    config = image_guard.provider.PROFILES[provider_name]
    output, dist = Path(output), Path(signer_dist)
    original = regular(Path(source_project) / config['profile'])
    release = regular(dist / 'OpenHarmonyProfileRelease.pem')
    application_path = regular(dist / 'OpenHarmonyApplication.pem')
    require(verifier.sha(original) == config['sha256'] and
            all(verifier.sha(path) == image_guard.provider.SIGNING_INPUTS[path.name]
                for path in (release, application_path)),
            'fixed original provider profile or public OS release signer differs')
    certs = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', release.read_text(), re.S)
    require(len(certs) == 3, 'fixed OS release issuer chain differs')
    leaf = output / 'OS-release-leaf.pem'; leaf.write_text(certs[-1] + '\n')
    decoded, old_decoded = output / 'OS-release-profile.json', output / 'original-release-profile.json'
    command(['openssl', 'cms', '-verify', '-inform', 'DER', '-in', str(profile), '-nointern', '-certfile', str(leaf),
             '-noverify', '-out', str(decoded)], 'image-provider-release-CMS')
    command(['openssl', 'cms', '-verify', '-inform', 'DER', '-in', str(original), '-noverify', '-out', str(old_decoded)],
            'image-provider-original-CMS')
    application = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', application_path.read_text(), re.S)
    require(len(application) == 3, 'fixed application signer chain differs')
    expected = image_guard.provider.desired_profile(load(old_decoded), (application[-1] + '\n').encode(), config)
    actual = load(decoded); require(actual == expected, 'image provider changed original release permissions/APL/ACL policy')
    require(actual['validity']['not-before'] <= int(time.time()) < actual['validity']['not-after'],
            'image provider release profile is outside its valid interval')
    return {'OS_release_issuer': descriptor(release), 'original_source_profile': descriptor(original),
            'decoded_release_profile': descriptor(decoded)}


def provider_from_image(boot, spec, output, signer_dist, signer_jar, command, *, provider_name='contacts', device='phone'):
    """Only the immutable system.img of the actual enclosing package is used."""
    sys.path.insert(0, str(ROOT / 'scripts'))
    image_guard = importlib.import_module('verify_contacts_theme_provider_image')
    require(provider_name in ('contacts', 'theme') and device in ('phone', '2in1') and
            (provider_name != 'contacts' or device == 'phone'), 'explicit Contacts phone or Wallpaper product role required')
    config = image_guard.provider.PROFILES[provider_name]
    module_name = ('pad_wallpaper' if device == '2in1' else 'phone_wallpaper') if provider_name == 'theme' else None
    relative = ('product/' + ('pad' if device == '2in1' else 'phone') if provider_name == 'theme' else 'entry')
    filename = 'Wallpaper.hap' if provider_name == 'theme' else 'Contacts.hap'
    ext = importlib.import_module('ext_image_entries')
    debugfs = importlib.import_module('verify_alsa_config_image').debugfs_path()
    boot_value = load(boot); env = boot_value['test_environment']
    directory = Path(env['freshly_extracted_directory']).resolve()
    image = regular(directory / 'images/system.img')
    require(env['device_type'] == device and str(image) in env['qemu_command'] and verifier.sha(image) == boot_value['initial_package_file_sha256']['images/system.img'],
            'system image differs from actual freshly booted archive')
    guard_path = regular(directory / 'contacts-theme-provider-evidence.json')
    require(verifier.sha(guard_path) == boot_value['initial_package_file_sha256']['contacts-theme-provider-evidence.json'],
            'archive provider guard changed')
    guard = load(guard_path); row = guard['providers'][provider_name]
    require(guard.get('status') == 'pass' and guard.get('failures') == [] and guard.get('device') == device and
            guard.get('system_image_sha256') == verifier.sha(image), 'current package provider guard failed or mismatched')
    output = Path(output); output.mkdir()
    hap, inode = ext.dump_unique_file(image, tuple(prefix + '/app/' + config['bundle'] + '/' + filename
        for prefix in ('', '/system')), output, debugfs)
    require(verifier.sha(hap) == row['hap_sha256'] and all(inode[key] == row[key] for key in inode), 'actual current-image provider differs from archive guard')
    sdk = verify_sdk_project(spec, module_name=module_name)
    source = Path(spec['source_project']) / relative / 'src/main/module.json5'
    # The full SDK source inventory above binds this actual module, not a
    # standalone hand-written manifest. json5 rejects duplicate keys.
    import json5
    source_module = json5.loads(source.read_text(), allow_duplicate_keys=False)['module']
    image_guard.inspect_hap(hap, source_module, provider_name, device)
    unsigned = checked_artifact(spec['unsigned_hap'])
    require(hap_contents(hap)[1] == hap_contents(unsigned)[1], 'image provider ABC/resources/module differ from actual SDK HAP')
    dist, jar, pins = signer_inputs(signer_dist, signer_jar)
    chain, profile = output / 'verified-chain.cer', output / 'embedded-profile.p7b'
    argv = ['java', '-jar', str(jar), 'verify-app', '-inFile', str(hap), '-outCertChain', str(chain), '-outProfile', str(profile)]
    log = command(argv, 'image-provider-verify-app')
    require(all(m in log for m in ('verify codesign success', 'Digest verify result: true',
            'verify permission sign success', 'verify-app success')), 'image provider actual signature verification failed')
    application_leaf(log)
    require(regular(chain).stat().st_size and verifier.sha(regular(profile)) == row['embedded_profile_sha256'] and
            row.get('application_signer_sha256') == APP_LEAF and row.get('digest_codesign_permission_verification') == 'pass',
            'image provider profile/signature differs from exact source/image guard')
    # Independently reproduce the exact original OS release policy. The source
    # profile and fixed public issuer are pinned, including original permissions,
    # ACLs and APL; an internally consistent hand-written package guard cannot
    # introduce a different release policy.
    release_proof = verify_provider_release_profile(profile, spec['source_project'], provider_name, dist, output, command)
    return {'hap': descriptor(hap), 'system_image': descriptor(image), 'image_identity': inode,
            'archive_guard': descriptor(guard_path), 'sdk': sdk, 'signer_inputs': pins, 'embedded_profile': descriptor(profile),
            **release_proof}


class Commands:
    def __init__(self, output, rows, guest=None):
        self.output, self.rows, self.guest = Path(output), rows, guest
        self.output.mkdir()

    def __call__(self, argv, label):
        require(re.fullmatch('[A-Za-z0-9_-]+', label), 'bounded command label required')
        if self.guest: self.guest.healthy()
        path = self.output / (str(len(self.rows)).zfill(4) + '-' + label + '.log')
        row = {'argv': list(map(str, argv)), 'label': label, 'log': str(path)}; self.rows.append(row)
        try:
            completed = subprocess.run(row['argv'], capture_output=True, text=True, timeout=180,
                                       env=dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C', PYTHONDONTWRITEBYTECODE='1'))
            text = completed.stdout + completed.stderr; row['exit_code'] = completed.returncode
        except subprocess.TimeoutExpired as error:
            text = str(error); row['exit_code'] = 124
        path.write_text(text); row['sha256'] = verifier.sha(path)
        require(row['exit_code'] == 0 and '[Fail]' not in text, 'actual command failed: ' + label)
        if self.guest: self.guest.healthy()
        return text


def installed_path(raw, bundle):
    value = json.loads(raw[raw.index('{'):raw.rindex('}') + 1], object_pairs_hook=unique)
    paths = {item for obj in verifier.objects(value) for key, item in obj.items() if key in ('hapPath', 'hapSourceDir', 'moduleSourceDir') and
             isinstance(item, str) and item.startswith('/data/app/el1/bundle/public/' + bundle + '/') and item.endswith('.hap') and
             '..' not in PurePosixPath(item).parts}
    require(len(paths) == 1, 'unique actual BMS-installed ordinary HAP path required')
    return paths.pop()


def independent_result(output, run_id, boot_id, full_boundaries=False):
    output = Path(output); report = load(output / 'driver-report.json')
    require(report.get('run_id') == run_id and report.get('status') == 'pass' and report.get('failures') == [] and
            report['test_environment']['boot_id'] == boot_id, 'driver failure or different guest/run')
    result = verifier.verify_runtime(output / 'journal.jsonl', output / 'seed.json', output / 'cleanup.json',
        output / 'ui.json', output / 'caller-identity.json', output / 'build.json')
    wanted = {row['id'] for row in verifier.MATRIX.values() if row['required']}
    if full_boundaries: wanted.update(FULL_BOUNDARY_CASES)
    observations = result['observations']
    require(result.get('raw_results_verified') is True and result.get('scope') == 'required_caller_matrix' and
            result.get('run_id') == run_id and {row['case_id'] for row in observations} == wanted and
            len(observations) == sum(len(verifier.MATRIX[name]['slots']) for name in wanted),
            'independent complete matrix verification missing')
    if full_boundaries:
        home = [row for row in report['commands'] if 'actual-home' in Path(row['path']).name]
        require(len(home) == 1 and home[0].get('exit_code') == 0 and
                len(home[0]['argv']) == 5 and
                home[0]['argv'][1:4] == ['-t', report['test_environment']['target'], 'shell'] and
                home[0]['argv'][4].startswith('uitest uiInput keyEvent Home; task_ui_rc=$?; printf '),
                'full navigation boundary lacks actual Home command')
        markers = re.findall(r'__UITEST_EXIT_[a-f0-9]{32}__=', home[0]['argv'][4])
        raw = checked_artifact(home[0]).read_text().replace('\r', '')
        require(len(markers) == 1 and raw.count(markers[0]) == 1 and raw.rstrip().endswith(markers[0] + '0'),
                'actual navigation Home remote command failed')
    return {**result, 'full_boundaries_verified': bool(full_boundaries),
            'required_boundary_case_ids': list(FULL_BOUNDARY_CASES) if full_boundaries else [],
            'observed_case_ids': sorted({row['case_id'] for row in observations})}


def verify_runtime_identities(runtime, build, env, permissions_bundle, allow_texts):
    report = load(runtime / 'driver-report.json'); ui = load(runtime / 'ui.json')
    for row in report['commands']:
        require(row.get('exit_code') == 0, 'actual runtime transport failed')
        checked_artifact(row)
    for key, bundle in [('caller', driver.CALLER), ('seed', driver.SEED)]:
        identity = load(runtime / (key + '-identity.json')); signed = checked_artifact(build[key + '_hap'])
        app = driver.application_info(checked_artifact(identity['bms_dump']).read_text(), bundle)
        require(verifier.sha(checked_artifact(identity['installed_caller_hap'])) == verifier.sha(signed), 'BMS-installed audit HAP differs')
        before = load(checked_artifact(identity['permission_probe']))
        require(before.get('api') == 'AccessTokenKit::VerifyAccessToken' and before.get('token_id') == app['accessTokenId'] and
                before.get('bundle_name') == bundle and before.get('READ_CONTACTS') == before.get('WRITE_CONTACTS') == -1,
                'fresh ordinary audit app already had broad Contacts access')
        after = report['identity_after'][key]
        again = driver.application_info(checked_artifact(after['bms_dump']).read_text(), bundle)
        require(all(again[name] == app[name] for name in ('uid', 'accessTokenId')), 'audit UID/token changed during run')
        token = load(checked_artifact(after['permission_probe'])); expected = -1 if key == 'caller' else 0
        require(token.get('api') == 'AccessTokenKit::VerifyAccessToken' and token.get('token_id') == app['accessTokenId'] and
                token.get('bundle_name') == bundle and token.get('READ_CONTACTS') == token.get('WRITE_CONTACTS') == expected,
                'audit app final permission state differs')
        if key == 'seed':
            for field, expected in [('seed_permission_before', -1), ('seed_permission_after', 0)]:
                raw = load(checked_artifact(ui[field]))
                require(raw.get('api') == 'AccessTokenKit::VerifyAccessToken' and raw.get('token_id') == app['accessTokenId'] and
                        raw.get('bundle_name') == bundle and raw.get('READ_CONTACTS') == raw.get('WRITE_CONTACTS') == expected,
                        'actual seed user grant token transition missing')
    inputs = ui.get('seed_user_permission_inputs', [])
    require(inputs, 'real permission dialog input evidence missing')
    for event in inputs:
        layout = load(checked_artifact(event['layout'])); checked_artifact(event['screenshot'])
        nodes = []
        for text in allow_texts:
            try: nodes.append(driver.clickable_for_text(layout, permissions_bundle, text))
            except driver.NodeNotReady: pass
        require(len(nodes) == 1 and nodes[0] == event['selected_node'], 'actual permission dialog control differs')
        x, y, width, height = nodes[0]['rect']
        argv = ['-t', env['target'], 'shell', 'uitest uiInput click ' + str(x + width // 2) + ' ' + str(y + height // 2)]
        require(any(row['argv'][1:] == argv and 'user-allow-contacts' in Path(row['path']).name for row in report['commands']),
                'permission input lacks an actual successful UITest command')


def verify_public_cleanup(path, run_id):
    """Also works after partial seed creation; does not require 205 successes."""
    value = load(path)
    require(value.get('run_id') == run_id and value.get('delete_api') == 'contact.deleteContact' and
            value.get('read_api') in ('contact.queryContact', 'contact.queryContacts') and value.get('remaining_contacts') == [],
            'actual public CRUD cleanup receipt missing or nonempty')
    deleted = load(checked_artifact(value['raw_delete'])); read = load(checked_artifact(value['raw_readback']))
    require(deleted.get('run_id') == run_id and deleted.get('api') == value['delete_api'] and deleted.get('error') is None and
            deleted.get('keys') == value.get('deleted_keys') and read.get('run_id') == run_id and
            read.get('api') == value['read_api'] and read.get('error') is None and read.get('contacts') == [],
            'actual public delete/read-back cleanup failed')
    return descriptor(path)


def cleanup_capture(guest, cleanup, script, label, path):
    raw = guest.shell(script, label); path = Path(path); path.write_text(raw)
    desc = descriptor(path)
    cleanup.setdefault('captures', {})[desc['path']] = {'artifact': desc, 'command': dict(guest.report['commands'][-1]), 'script': script}
    return raw, desc


def verify_resources_cleanup(cleanup, run_id, target=None):
    if target is not None: require(cleanup.get('target') == target, 'cleanup belongs to a different guest')
    def captured(desc, script):
        proof = cleanup['captures'][desc['path']]
        require(proof['artifact'] == desc and proof['script'] == script, 'cleanup capture/script mismatch')
        row = proof['command']; argv = row['argv']
        require(row.get('exit_code') == 0 and argv[1:4] == ['-t', cleanup['target'], 'shell'] and
                argv[-1].startswith('(' + script + '); task_child_rc=$?;'), 'actual cleanup command/guest mismatch')
        raw = checked_artifact(desc).read_text()
        transport = checked_artifact({'path': row['log'], 'sha256': row['sha256']}).read_text().replace('\r', '')
        sections = transport.rsplit('\n__QEMU_CHILD_EXIT_', 1)
        require(len(sections) == 2 and sections[0] == raw and re.fullmatch('[0-9a-f]{32}__=0\n', sections[1]),
                'cleanup capture is not the actual successful guest output')
        return raw
    if cleanup.get('public_CRUD_required'):
        require(set(cleanup.get('installed_bundles', [])) == {driver.CALLER, driver.SEED} and
                len(cleanup['installed_bundles']) == 2 and cleanup.get('AMS_after'), 'complete audit app/session cleanup evidence missing')
        require(verify_public_cleanup(checked_artifact(cleanup['public_CRUD']), run_id) == cleanup['public_CRUD'],
                'public CRUD cleanup changed')
    for bundle, desc in cleanup.get('processes', {}).items():
        value = json.loads(captured(desc, shlex.join(['/data/local/tmp/' + run_id + '_observer', 'processes', bundle])), object_pairs_hook=unique)
        require(bundle in (driver.CALLER, driver.SEED) and value.get('api') == 'AppMgrClient::GetAllRunningProcesses' and
                value.get('error_code') == 0 and value.get('bundle_name') == bundle and value.get('processes') == [],
                'actual audit application process remains or observer failed')
    if cleanup.get('installed_bundles'):
        require(set(cleanup['processes']) == set(cleanup['installed_bundles']), 'missing own process cleanup observation')
        raw = captured(cleanup['BMS_after'], 'bm dump -a')
        require(driver.PROVIDER in raw and not any(re.search(r'(?<![A-Za-z0-9_.])' + re.escape(bundle) +
                r'(?![A-Za-z0-9_.])', raw) for bundle in cleanup['installed_bundles']), 'actual audit BMS entry remains')
    if cleanup.get('AMS_after'):
        raw = captured(cleanup['AMS_after'], 'aa dump -a -u 100')
        require(not verifier.ams_sessions(raw, cleanup['provider_uid'], cleanup['caller_uid']), 'actual Contacts modal sessions remain')
    require(cleanup.get('observer_removed') is True, 'own observer removal was not verified')
    if cleanup.get('observer_removal'):
        remote = '/data/local/tmp/' + run_id + '_observer'
        captured(cleanup['observer_removal'], 'rm -f ' + remote + ' && test ! -e ' + remote)
    else:
        require(not cleanup.get('installed_bundles') and not cleanup.get('public_CRUD_required'), 'own observer removal proof missing')


def verify_evidence(evidence_path, archive_path, boot_path):
    """Parent gate entry: reconsume raw proof and rerun real cryptography.

    Does not contact a guest, install, compile, or trust a subprocess pass field.
    Keep the suite's extracted system image and SDK snapshots with the evidence.
    """
    evidence_path, archive_path, boot_path = map(regular, (evidence_path, archive_path, boot_path))
    report = load(evidence_path); boot = load(boot_path)
    from enclosing_acceptance_guest import validate_binding
    env = validate_binding(boot, verifier.sha(archive_path))
    require(report.get('status') == 'pass' and report.get('failures') == [] and
            report.get('archive_sha256') == verifier.sha(archive_path) and report.get('boot_id') == env['boot_id'] and
            checked_artifact(report['archive']) == archive_path and checked_artifact(report['boot']) == boot_path and
            report.get('first_artifact_behavior_gate_passed') is False and report.get('ledger_closed') is False and
            report.get('cleanup_complete') is True and report.get('cleanup_errors') == [],
            'coordinator archive/boot/status binding differs')
    require(report['cleanup'].get('public_CRUD_required') is True, 'successful Contacts run must include actual CRUD cleanup')
    require(type(report.get('full_boundaries_requested')) is bool and
            type(report.get('full_boundaries_verified')) is bool, 'explicit Contacts boundary scope required')
    verify_resources_cleanup(report['cleanup'], report['run_id'], env['target'])
    spec = load(checked_artifact(report['inputs']))
    sdk = {'caller': verify_sdk_project(spec['caller'], fixture=verifier.FIX, source_manifest='caller-source-manifest.json'),
           'seed': verify_sdk_project(spec['seed'], fixture=driver.FIX, source_manifest='seed-source-manifest.json')}
    require(sdk == report['sdk'], 'coordinator SDK provenance changed')
    observer = report['observer']
    require(observer['path_map'] == spec.get('helper_path_map', {}) and
            verify_observer(checked_artifact(observer['binary']), checked_artifact(observer['receipt']), observer['path_map']) == observer,
            'coordinator helper evidence changed')
    for row in report['commands']:
        require(row.get('exit_code') == 0 and isinstance(row.get('argv'), list), 'coordinator recorded a failed command')
        checked_artifact({'path': row['log'], 'sha256': row['sha256']})
    for row in report['guest_commands']:
        require(row.get('exit_code') == 0, 'coordinator guest command failed')
        checked_artifact({'path': row['log'], 'sha256': row['sha256']})
    runtime = checked_artifact(report['driver_report']).parent
    require(runtime == evidence_path.parent / 'runtime', 'driver evidence escapes coordinator output')
    build = load(runtime / 'build.json')
    require(build.get('boot_session_id') == env['boot_id'] and build.get('booted_package_sha256') == verifier.sha(archive_path) and
            checked_artifact(build['representative_package']) == archive_path, 'raw runtime build binding differs')
    verify_runtime_identities(runtime, build, env, report['permission_bundle'], report['allow_texts'])
    signatures = {}; signer = report['signer']
    with tempfile.TemporaryDirectory(prefix='contacts-parent-reverify-') as scratch:
        scratch = Path(scratch); rows = []; command = Commands(scratch / 'commands', rows)
        provider = provider_from_image(boot_path, spec['provider'], scratch / 'provider', signer['dist'], signer['jar'], command)
        require(checked_artifact(build['provider_hap']).read_bytes() == checked_artifact(provider['hap']).read_bytes() and
                provider['system_image'] == report['provider']['system_image'] and
                provider['archive_guard'] == report['provider']['archive_guard'] and provider['sdk'] == report['provider']['sdk'],
                'raw provider does not belong to current boot image/source')
        for key, bundle, permissions in [('caller', driver.CALLER, []), ('seed', driver.SEED, driver.PERMISSIONS)]:
            signed = checked_artifact(build[key + '_hap'])
            require(hap_contents(signed)[1] == hap_contents(checked_artifact(spec[key]['unsigned_hap']))[1],
                    'raw runtime signed app differs from actual compiled SDK source')
            # Reverify the physical HAP, CMS and exact fresh-UDID profile, rather
            # than relying on a signature-verification receipt status.
            proof = verify_signed_hap_artifacts(signed, bundle, permissions, env['udid'], signer['dist'], signer['jar'],
                                               scratch / (key + '-verification'), command)
            identity = load(runtime / (key + '-identity.json'))
            require(load(checked_artifact(identity['decoded_profile'])) == proof['verified_profile'], 'runtime profile differs from actual embedded profile')
            signatures[key] = {'signed_hap': descriptor(signed), 'application_signer_sha256': APP_LEAF,
                               'profile_signer_sha256': PROFILE_LEAF}
        crypto_commands = len(rows)
    result = independent_result(runtime, report['run_id'], env['boot_id'], report['full_boundaries_requested'])
    require(report['full_boundaries_verified'] == result['full_boundaries_verified'], 'Contacts boundary summary differs from raw re-verification')
    require(load(checked_artifact(report['independent_verifier'])) == result, 'stored independent result differs from raw re-verification')
    return {'status': 'pass', 'archive_sha256': verifier.sha(archive_path), 'boot_id': env['boot_id'],
            'scope': 'Contacts_raw_source_signature_image_UI_results_reverified_NOT_full_behavior_gate',
            'evidence': descriptor(evidence_path), 'raw_results': result, 'signatures': signatures,
            'full_boundaries_verified': result['full_boundaries_verified'],
            'actual_crypto_commands_reexecuted': crypto_commands,
            'first_artifact_behavior_gate_passed': False, 'ledger_closed': False}


def run(args):
    output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 1, 'status': 'fail', 'scope': 'fresh_guest_Contacts_component_NOT_full_behavior_gate',
              'first_artifact_behavior_gate_passed': False, 'ledger_closed': False, 'commands': [], 'failures': [],
              'cleanup_complete': False, 'cleanup_errors': [], 'cleanup': {'public_CRUD_required': False, 'processes': {},
                  'installed_bundles': [], 'observer_removed': True}}
    report['permission_bundle'] = args.permission_bundle; report['allow_texts'] = args.allow_text or ['允许', 'Allow']
    report['full_boundaries_requested'] = args.full_boundaries; report['full_boundaries_verified'] = False
    guest = None; installed = []; observer_remote = None; caller_uid = None
    try:
        spec = load(args.inputs)
        report['inputs'] = descriptor(args.inputs); report['boot'] = descriptor(args.boot); report['archive'] = descriptor(args.archive)
        report['archive_sha256'] = verifier.sha(args.archive)
        report['signer'] = {'dist': str(Path(args.signer_dist).resolve()),
                            'jar': str(Path(args.signer_jar or Path(args.signer_dist) / 'hap-sign-tool.jar').resolve())}
        report['sdk'] = {
            'caller': verify_sdk_project(spec['caller'], fixture=verifier.FIX, source_manifest='caller-source-manifest.json'),
            'seed': verify_sdk_project(spec['seed'], fixture=driver.FIX, source_manifest='seed-source-manifest.json')}
        report['observer'] = verify_observer(args.observer_local, args.observer_receipt, spec.get('helper_path_map'))
        guest = EnclosingAcceptanceGuest(args.boot, args.archive, args.hdc, output / 'guest').start()
        require(guest.env['guest_arch'] == 'arm64' and guest.env['device_type'] == 'phone', 'representative ARM64 phone guest required')
        report['boot_id'] = guest.env['boot_id']
        report['cleanup']['target'] = guest.target
        command = Commands(output / 'commands', report['commands'], guest)
        report['provider'] = provider_from_image(args.boot, spec['provider'], output / 'provider', args.signer_dist, args.signer_jar, command)
        run_id = 'contacts_' + secrets.token_hex(12); report['run_id'] = run_id
        observer_remote = '/data/local/tmp/' + run_id + '_observer'
        report['cleanup']['observer_removed'] = False
        command([args.hdc, '-t', guest.target, 'file', 'send', args.observer_local, observer_remote], 'push-observer')
        ready = guest.shell('chmod 700 ' + observer_remote + ' && sha256sum ' + observer_remote, 'observer-ready')
        require(ready.split()[0] == verifier.sha(args.observer_local), 'actual guest observer differs')
        before = guest.shell('bm dump -a', 'BMS-before-audit-install')
        require(driver.PROVIDER in before, 'actual installed bundle list/provider missing')
        require(not any(re.search(r'(?<![A-Za-z0-9_.])' + re.escape(bundle) + r'(?![A-Za-z0-9_.])', before)
                        for bundle in (driver.CALLER, driver.SEED)),
                'audit bundle already installed; fresh normal identity/permission baseline required')
        proofs = {}
        for key, bundle, permissions in [('caller', driver.CALLER, []), ('seed', driver.SEED, driver.PERMISSIONS)]:
            proofs[key] = sign_normal_hap(checked_artifact(spec[key]['unsigned_hap']), bundle, permissions, guest.udid,
                args.signer_dist, args.signer_jar, output / (key + '-signing'), command)
            installed.append(bundle)
            install = command([args.hdc, '-t', guest.target, 'install', checked_artifact(proofs[key]['signed_hap'])], key + '-install')
            require(re.search(r'(?i)successfully|install success', install), 'actual HDC install did not report success')
            raw = guest.shell('bm dump -n ' + bundle, key + '-BMS-installed')
            app = driver.application_info(raw, bundle)
            if key == 'caller': caller_uid = app['uid']
            require(app.get('isSystemApp') is False and app.get('appPrivilegeLevel', app.get('apl')) == 'normal' and
                    type(app.get('uid')) is int and app['uid'] > 10000 and type(app.get('accessTokenId')) is int and
                    app['accessTokenId'] > 0, 'installed app is not an ordinary normal UID/token')
            identity = {**proofs[key], 'installed_remote_hap': installed_path(raw, bundle)}
            write_json(output / (key + '-signed-identity.json'), identity)
        build = {'run_id': run_id, 'representative_package': descriptor(args.archive), 'booted_package_sha256': verifier.sha(args.archive),
            'boot_session_id': guest.env['boot_id'], 'architecture': 'arm64', 'device_profile': 'phone',
            'caller_hap': proofs['caller']['signed_hap'], 'seed_hap': proofs['seed']['signed_hap'], 'provider_hap': report['provider']['hap'],
            'caller_source_manifest': spec['caller']['source_manifest'], 'seed_source_manifest': spec['seed']['source_manifest'],
            'caller_fixture_hashes': {p.name: verifier.sha(p) for p in sorted(verifier.FIX.iterdir()) if p.is_file()}}
        write_json(output / 'build.json', build)
        report['cleanup']['public_CRUD_required'] = True
        driver_report = driver.run(argparse.Namespace(boot=args.boot, archive=args.archive, hdc=args.hdc,
            build=output / 'build.json', identity=output / 'caller-signed-identity.json', seed_identity=output / 'seed-signed-identity.json',
            observer_local=args.observer_local, observer=observer_remote, output=output / 'runtime', run_id=run_id,
            permission_bundle=args.permission_bundle, allow_text=args.allow_text,
            optional_case=list(FULL_BOUNDARY_CASES) if args.full_boundaries else []))
        report['driver_report'] = descriptor(output / 'runtime/driver-report.json')
        # A child's pass string cannot substitute for consuming all raw inputs.
        result = independent_result(output / 'runtime', run_id, guest.env['boot_id'], args.full_boundaries)
        verify_runtime_identities(output / 'runtime', load(output / 'runtime/build.json'), guest.env,
                                  report['permission_bundle'], report['allow_texts'])
        report['independent_verifier'] = write_json(output / 'coordinator-independent-verifier.json', result)
        report['full_boundaries_verified'] = result['full_boundaries_verified']
        require(driver_report['failures'] == [], 'runtime driver failed')
        require(guest.shell('cat /proc/sys/kernel/random/boot_id', 'currentboot-after').strip() == guest.env['boot_id'], 'guest rebooted')
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(str(error))
    finally:
        if guest:
            if report['cleanup']['public_CRUD_required']:
                try:
                    report['cleanup']['public_CRUD'] = verify_public_cleanup(output / 'runtime/cleanup.json', report['run_id'])
                except Exception as error: report['cleanup_errors'].append(str(error))
            for bundle in reversed(installed):
                try:
                    # Public CRUD cleanup is the driver's finally operation and
                    # is independently verified before status can pass. Uninstall
                    # only our two normal apps, never the actual provider.
                    text = guest.shell('bm uninstall -n ' + bundle, 'uninstall-' + bundle.split('.')[-1])
                    require('success' in text.lower(), 'actual audit app uninstall failed')
                except Exception as error: report['cleanup_errors'].append(str(error))
            report['cleanup']['installed_bundles'] = installed
            if installed:
                try:
                    raw, desc = cleanup_capture(guest, report['cleanup'], 'bm dump -a', 'BMS-after-audit-uninstall', output / 'BMS-after-uninstall.log')
                    require(driver.PROVIDER in raw and not any(re.search(r'(?<![A-Za-z0-9_.])' + re.escape(bundle) +
                            r'(?![A-Za-z0-9_.])', raw) for bundle in installed), 'audit app uninstall did not restore absence')
                    report['cleanup']['BMS_after'] = desc
                except Exception as error: report['cleanup_errors'].append(str(error))
                for bundle in installed:
                    try:
                        deadline = time.monotonic() + 10
                        while True:
                            raw, desc = cleanup_capture(guest, report['cleanup'], shlex.join([observer_remote, 'processes', bundle]),
                                'processes-after-' + bundle.split('.')[-1], output / ('processes-after-' + bundle.split('.')[-1] + '.json'))
                            value = json.loads(raw)
                            require(value.get('error_code') == 0 and value.get('api') == 'AppMgrClient::GetAllRunningProcesses', 'actual cleanup process observer failed')
                            if value.get('processes') == [] or time.monotonic() >= deadline: break
                            time.sleep(0.25)
                        report['cleanup']['processes'][bundle] = desc
                    except Exception as error: report['cleanup_errors'].append(str(error))
            if caller_uid and (output / 'runtime/ui.json').is_file():
                try:
                    ui = load(output / 'runtime/ui.json'); provider_uid = verifier.provider_uid(ui)
                    raw, desc = cleanup_capture(guest, report['cleanup'], 'aa dump -a -u 100', 'AMS-after-owned-app-cleanup', output / 'AMS-after-cleanup.log')
                    report['cleanup'].update(AMS_after=desc, caller_uid=caller_uid, provider_uid=provider_uid)
                except Exception as error: report['cleanup_errors'].append(str(error))
            if observer_remote:
                try:
                    _, desc = cleanup_capture(guest, report['cleanup'], 'rm -f ' + observer_remote + ' && test ! -e ' + observer_remote,
                                              'remove-own-observer', output / 'observer-removal.log')
                    report['cleanup']['observer_removal'] = desc
                    report['cleanup']['observer_removed'] = True
                except Exception as error: report['cleanup_errors'].append(str(error))
            report['test_environment'] = guest.env; report['guest_commands'] = guest.report['commands']; guest.close()
        try: verify_resources_cleanup(report['cleanup'], report.get('run_id'))
        except Exception as error: report['cleanup_errors'].append(str(error))
        report['cleanup_complete'] = not report['cleanup_errors']
        if report['failures'] or report['cleanup_errors']: report['status'] = 'fail'
        write_json(output / 'evidence.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('boot', 'archive', 'inputs', 'signer-dist', 'observer-local', 'observer-receipt', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--signer-jar', type=Path)
    parser.add_argument('--hdc', required=True)
    parser.add_argument('--permission-bundle', default='com.ohos.permissionmanager')
    parser.add_argument('--allow-text', action='append')
    parser.add_argument('--full-boundaries', action='store_true',
                        help='also run the real 600000ms native deadline and navigation dismissal; required by the first-package gate')
    args = parser.parse_args(); report = run(args)
    print(json.dumps({key: report[key] for key in ('status', 'failures', 'first_artifact_behavior_gate_passed')}))
    return report['status'] != 'pass'


if __name__ == '__main__': raise SystemExit(main())
