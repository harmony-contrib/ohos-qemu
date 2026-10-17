#!/usr/bin/env python3
"""Prepare an inert typed SDK105 system-caller project; never build or sign it."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import secrets
import uuid

import batch_apps_contact_picker_runtime as base_project
import batch_apps_contact_picker_coordinator as shared

HERE = Path(__file__).resolve().parent
FIX = HERE / 'fixtures/batch_network/openvpn_runtime'
BUNDLE = 'org.harmonycontrib.openvpncleanupqa'
PERMISSION = 'ohos.permission.MANAGE_VPN'
ROOT = '/data/service/el1/public/vpn/qemu_openvpn'
SCOPE = 'actual_guest_OpenVPN_cleanup_failure_recovery_NOT_CONNECTED_OR_PGID_signal_or_full_gate'
SDK_SCOPE = 'actual_SDK105_OpenVPN_QA_unsigned_HAP_ONLY_NOT_signature_or_guest'
SDK_NAME = 'openvpn-cleanup'
SOURCE_TOOLS = ('batch_network_openvpn_runtime_project.py', 'batch_apps_contact_picker_runtime.py',
                'batch_apps_contact_picker_coordinator.py')
require, sha, checked, load = shared.require, shared.verifier.sha, shared.checked_artifact, shared.load


def descriptor(path):
    path = shared.regular(path)
    return {'path': str(path), 'sha256': sha(path)}


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')


def profile_input(path, port, run):
    raw = shared.regular(path).read_text()
    require(1024 <= port <= 65535 and 0 < len(raw.encode()) <= 1024 * 1024 - 1024 and '\x00' not in raw,
            'bounded owned test profile and unprivileged loopback UDP port required')
    # Force one exact controlled endpoint; never send this QA profile outside
    # the disposable guest. Production OpenVPN still validates TLS/syntax.
    lines = [line.strip() for line in raw.splitlines() if line.strip() and not line.lstrip().startswith(('#', ';'))]
    options, blocks, active = [], set(), None
    for line in lines:
        if active is not None:
            if line == '</' + active + '>': active = None
            continue
        if line in ('<ca>', '<cert>', '<key>'):
            active = line[1:-1]
            require(active not in blocks, 'duplicate inline credential block')
            blocks.add(active)
        else:
            require(not line.startswith('<'), 'unsupported inline configuration block')
            options.append(line)
    require(active is None, 'unterminated inline credentials')
    require([line for line in options if line.split()[0] == 'remote'] == [f'remote 127.0.0.1 {port}'] and
            [line for line in options if line.split()[0] == 'proto'] == ['proto udp4'], 'one exact loopback UDP remote required')
    require(all(not line.startswith(('<connection', '--', 'config ', 'remote-random', 'daemon', 'up ', 'down ', 'plugin '))
                for line in options), 'no alternative endpoint, include, daemon or executable hooks allowed')
    require('<ca>' in lines and '</ca>' in lines and ('<cert>' in lines or 'peer-fingerprint' in raw),
            'owned real inline test credentials required; no generated successful TLS claim')
    return raw.rstrip() + '\n# qemu-owned-run-' + run + '\n'


def prepare(output, sdk, profile, port):
    output, sdk = Path(output).resolve(), Path(sdk).resolve()
    metadata = sdk / 'ets/oh-uni-package.json'; declaration = sdk / 'ets/api/@ohos.net.vpn.d.ts'
    require(load(metadata)['version'] == '26.0.0.105', 'actual prepared SDK105 required')
    text = declaration.read_text()
    for signature in ('setUp(config: VpnConfig): Promise<number>', 'destroy(): Promise<void>',
                      'interface OpenVpnConfig extends SysVpnConfig', 'getConnectedSysVpnConfig()', 'getConnectedVpnAppInfo()'):
        require(signature in text, 'actual SDK API missing: ' + signature)
    device = sdk / 'ets/api/device-define/default.json'
    require('SystemCapability.Communication.NetManager.Vpn' in load(device)['SysCaps'], 'real SDK VPN SysCap absent')
    run = secrets.token_hex(16); vpn_id = str(uuid.UUID(run))
    raw = profile_input(profile, port, run)
    base_project.prepare_project(output)
    output.chmod(0o700)  # Before embedding the owned ephemeral test credentials.
    for path in (output / 'entry/src/main/ets').rglob('*.ets'):
        path.unlink()  # Only this fresh private project, just created above.
    app_path = output / 'AppScope/app.json5'; app = load(app_path); app['app']['bundleName'] = BUNDLE; write(app_path, app)
    package_path = output / 'oh-package.json5'; package = load(package_path)
    package['name'] = 'openvpn-cleanup-caller'; write(package_path, package)
    write(output / 'AppScope/resources/base/element/string.json',
          {'string': [{'name': 'app_name', 'value': 'OpenVPN cleanup QA'}]})
    module_path = output / 'entry/src/main/module.json5'; module = load(module_path)
    module['module']['deviceTypes'] = ['default']; module['module']['requestPermissions'] = [{'name': PERMISSION}]
    module['module']['abilities'][0].pop('skills', None); write(module_path, module)
    entry = (FIX / 'EntryAbility.ets').read_text()
    for name, value in {'__RUN__': run, '__VPN_ID__': vpn_id, '__PORT__': str(port),
                        '__PROFILE_BASE64__': base64.b64encode(raw.encode()).decode()}.items():
        entry = entry.replace(name, value)
    write(output / 'entry/src/main/ets/entryability/EntryAbility.ets', entry)
    write(output / 'entry/src/main/ets/pages/Index.ets', (FIX / 'Index.ets').read_text())
    (output / 'caller-source-manifest.json').unlink()
    manifest = dict(schema_version=1, scope=SCOPE, run_id=run, vpn_id=vpn_id, bundle=BUNDLE, port=port,
        requested_permissions=[PERMISSION], apl='system_core', system_app=True,
        profile_input=descriptor(profile), profile_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        sdk={name: descriptor(path) for name, path in [('metadata', metadata), ('declaration', declaration), ('device', device)]},
        fixtures={p.name: sha(p) for p in FIX.glob('*.ets')},
        sources={str(p.relative_to(output)): sha(p) for p in output.rglob('*') if p.is_file()},
        native_build_or_runtime_proof=False, first_artifact_behavior_gate_passed=False)
    write(output / 'openvpn-runtime-source.json', manifest)
    output.chmod(0o700)  # The supplied profile may contain owned ephemeral test keys.
    return manifest


def verify_sdk_receipt(report, evidence, source, unsigned_hap):
    require(report['scope'] == SDK_SCOPE and type(report['exit_code']) is int and report['exit_code'] == 0 and
            report['failures'] == [] and report['node_version'] == 'v18.20.1' and
            re.fullmatch('[a-f0-9]{40}', report['source_commit']) and
            report['runner_sha256'] == sha(HERE / 'batch_network_openvpn_runtime_build.py') and
            report['source_tools'] == {name: sha(HERE / name) for name in SOURCE_TOOLS} and
            set(report['source_files']) == {SDK_NAME} and len(report['haps']) == 1,
            'successful exact independent OpenVPN SDK builder receipt required')
    hap = report['haps'][0]
    require(hap['project'] == SDK_NAME and hap['path'] == str(unsigned_hap) and
            hap['sha256'] == sha(unsigned_hap) and hap['bytes'] == unsigned_hap.stat().st_size,
            'independent SDK receipt HAP differs')
    tools = {name: checked(report['tools'][name]) for name in ('node', 'ohpm', 'hvigor', 'cpu_cap')}
    require(tools['cpu_cap'] == evidence.parent / 'cpu-cap.cjs' and
            sha(tools['cpu_cap']) == sha(HERE / 'fixtures/batch_media/audio_haptic_runtime/cpu-cap.cjs'),
            'SDK CPU preload differs from the recorded bounded builder')
    prefix = [str(tools['node']), '--max-old-space-size=2048', '--require', str(tools['cpu_cap'])]
    expected = [('dependencies', prefix + [str(tools['ohpm']), 'install', '--all', '--registry',
                 'http://127.0.0.1:9', '--fetch_timeout', '10000', '--retry_times', '0']),
                ('compile', prefix + [str(tools['hvigor']), 'assembleHap', '--mode', 'module', '-p',
                 'product=default', '-p', 'module=entry', '-p', 'debuggable=false', '-p',
                 'hvigor-obfuscation=false', '--no-daemon', '--no-parallel', '--no-incremental',
                 '--max-old-space-size', '2048'])]
    require(len(report['commands']) == len(expected), 'exact two serial SDK commands required')
    for row, (label, argv) in zip(report['commands'], expected):
        require(row['project'] == SDK_NAME and row['label'] == label and row['argv'] == argv and
                row['cwd'] == str(source) and type(row['exit_code']) is int and row['exit_code'] == 0 and
                not row.get('timed_out', False), 'independent SDK command/cwd/outcome differs')


def binding(spec):
    shared.verify_sdk_project(spec)
    require(spec['sdk_project'] == SDK_NAME, 'exact independent OpenVPN SDK project required')
    verify_sdk_receipt(load(checked(spec['sdk_evidence'])), checked(spec['sdk_evidence']),
                       Path(spec['source_project']), checked(spec['unsigned_hap']))
    source = Path(spec['source_project']); manifest_path = checked(spec['source_manifest']); value = load(manifest_path)
    require(manifest_path == source / 'openvpn-runtime-source.json' and value['scope'] == SCOPE and
            value['bundle'] == BUNDLE and value['requested_permissions'] == [PERMISSION] and
            value['apl'] == 'system_core' and value['system_app'] is True and
            re.fullmatch('[a-f0-9]{32}', value['run_id']), 'exact own system QA source required')
    require(load(checked(spec['sdk_evidence']))['sdk'] == value['sdk'], 'compiled SDK metadata differs from prepared SDK')
    for item in value['sdk'].values(): checked(item)
    require(load(checked(value['sdk']['metadata']))['version'] == '26.0.0.105', 'SDK105 source binding changed')
    require(value['fixtures'] == {p.name: sha(p) for p in FIX.glob('*.ets')}, 'QA fixture changed')
    require(value['vpn_id'] == str(uuid.UUID(value['run_id'])), 'owned UUID differs from run')
    raw = profile_input(checked(value['profile_input']), value['port'], value['run_id'])
    require(hashlib.sha256(raw.encode()).hexdigest() == value['profile_sha256'], 'owned source profile changed')
    expected = (FIX / 'EntryAbility.ets').read_text()
    for name, replacement in {'__RUN__': value['run_id'], '__VPN_ID__': value['vpn_id'], '__PORT__': str(value['port']),
                              '__PROFILE_BASE64__': base64.b64encode(raw.encode()).decode()}.items():
        expected = expected.replace(name, replacement)
    require((source / 'entry/src/main/ets/entryability/EntryAbility.ets').read_text() == expected and
            (source / 'entry/src/main/ets/pages/Index.ets').read_bytes() == (FIX / 'Index.ets').read_bytes(), 'generated caller differs from fixed fixture')
    rows = shared.source_rows(load(checked(spec['sdk_evidence'])), spec['sdk_project'])
    require(rows.get(manifest_path.name) == sha(manifest_path), 'compiled SDK manifest binding missing')
    for name, digest in value['sources'].items():
        require(rows.get(name) == digest and sha(source / name) == digest, 'compiled QA source changed: ' + name)
    compiled, _ = shared.hap_contents(checked(spec['unsigned_hap']))
    require(compiled['app']['bundleName'] == BUNDLE and compiled['module']['requestPermissions'] == [{'name': PERMISSION}],
            'compiled system caller identity/permission differs')
    return value


def proc_stat(line):
    end = line.rfind(')'); require(end > 0, 'bad /proc stat')
    pid = int(line.split(' ', 1)[0]); fields = line[end + 2:].split()
    require(len(fields) >= 20 and pid > 0, 'short /proc stat')
    return {'pid': pid, 'state': fields[0], 'ppid': int(fields[1]), 'pgrp': int(fields[2]), 'start': fields[19]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'sdk', 'profile'): parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args(); result = prepare(args.output, args.sdk, args.profile, args.port)
    print(json.dumps({'run_id': result['run_id'], 'scope': result['scope'], 'runtime_validated': False}))
