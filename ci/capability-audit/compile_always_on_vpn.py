#!/usr/bin/env python3
"""Compile VPN policy candidates and real regenerated IPC for all three ABIs.

Production source/output mounts remain read-only. This is not runtime closure.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

from compile_taskpool_thread_info import PRODUCTS, digest

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = [ROOT / 'patches/common/foundation/communication' / name for name in (
    'netmanager_base/optional_settings_read', 'netmanager_ext/always_on_vpn')]
IDL = Path('foundation/communication/netmanager_ext/interfaces/innerkits/netvpnclient')
TARGETS = (
    'obj/foundation/communication/netmanager_base/utils/data_share/src/net_data_share/net_datashare_utils.o',
    'obj/foundation/communication/netmanager_base/utils/data_share/src/net_data_share/net_datashare_utils_iface.o',
    'obj/foundation/communication/netmanager_ext/frameworks/js/napi/vpnext/src/vpnextension/vpn_module_ext.o',
    'obj/foundation/communication/netmanager_ext/frameworks/native/netvpnclient/src/net_vpn_manager_if/networkvpn_client.o',
    'obj/foundation/communication/netmanager_ext/services/vpnmanager/src/net_vpn_manager/networkvpn_service.o',
    'obj/out/{product}/gen/' + str(IDL) + '/net_vpn_manager_if/network_vpn_service_proxy.o',
    'obj/out/{product}/gen/' + str(IDL) + '/networkvpn_interface_stub/network_vpn_service_stub.o',
)


def query(source, cwd, target, log):
    result = subprocess.run([str(source / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', target],
        capture_output=True, text=True, check=True)
    log.write_text(result.stdout + result.stderr)
    command = shlex.split(result.stdout.splitlines()[-1])
    if any(token in command for token in ('&&', ';', '|')):
        raise ValueError('unexpected shell command')
    return command


def generate(source, cwd, staged, output):
    original = query(source, cwd, str(Path('gen') / IDL / 'inetwork_vpn_service.h'),
                     output / 'query.log')
    # Product diagnostics can retain the original host's absolute GN root.
    # Derive it from the exact fixed IDL suffix and relocate only that prefix.
    old_idl = original[original.index('--src-idl') + 1]
    suffix = str(IDL) + '/INetworkVpnService.idl'
    if not old_idl.endswith('/' + suffix):
        raise ValueError('one canonical fixed VPN service IDL source required')
    old_root = old_idl[:-len(suffix)]
    command = [','.join(str(source / part[len(old_root):])
                       if part.startswith(old_root) else part
                       for part in token.split(',')) for token in original]
    flags = ('--src-idl', '--dst-path', '--dst-file', '--idl-tool-path')
    if command[:2] != ['/usr/bin/env', '../../build/config/components/idl_tool/idl.py'] or any(
            command.count(flag) != 1 for flag in flags):
        raise ValueError('unexpected VPN IDL rule')
    destination = cwd / 'gen' / IDL
    if Path(command[command.index('--dst-path') + 1]) != destination:
        raise ValueError('unexpected VPN IDL destination')
    inputs, generated = output / 'inputs', output / 'generated'
    inputs.mkdir()
    hashes = {}
    for path in sorted((source / IDL).glob('*.idl')):
        candidate = staged / IDL / path.name
        selected = candidate if candidate.exists() else path
        shutil.copy2(selected, inputs / path.name)
        hashes[path.name] = digest(selected)
        if digest(inputs / path.name) != hashes[path.name]:
            raise ValueError('IDL copy differs')
    sources = command[command.index('--src-idl') + 1].split(',')
    files = command[command.index('--dst-file') + 1].split(',')
    if any(Path(path).parent != source / IDL or Path(path).name not in hashes for path in sources):
        raise ValueError('unexpected VPN IDL input')
    if any(Path(path).parent != destination for path in files):
        raise ValueError('unexpected VPN IDL output')
    command[command.index('--src-idl') + 1] = ','.join(str(inputs / Path(p).name) for p in sources)
    command[command.index('--dst-file') + 1] = ','.join(str(generated / Path(p).name) for p in files)
    command[command.index('--dst-path') + 1] = str(generated)
    with (output / 'generate.log').open('x') as log:
        subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True)
    header = generated / 'inetwork_vpn_service.h'
    if not header.is_file() or any(name not in header.read_text() for name in (
            'SetAlwaysOnVpnEnabled', 'IsAlwaysOnVpnEnabled')):
        raise ValueError('candidate IPC methods not generated')
    paths = sorted(p for p in generated.iterdir() if p.suffix in ('.h', '.cpp'))
    return dict(original_argv=original, argv=command, input_sha256=hashes,
                output_sha256={p.name: digest(p) for p in paths}), [
        {'type': 'file', 'name': str(destination / p.name), 'external-contents': str(p)} for p in paths]


def run(args):
    source = args.source_root.resolve()
    if not all(os.statvfs(path).f_flag & os.ST_RDONLY for path in (source, source / 'out')):
        raise ValueError('source and outputs must both be read-only')
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(status='fail', scope='actual_three_ABI_compilation_NOT_link_or_runtime',
                  closed=[], first_artifact_behavior_gate_passed=False, commands=[])
    try:
        baselines, paths = [], []
        for index, component in enumerate(COMPONENTS):
            spec = importlib.util.spec_from_file_location('vpn_baseline_' + str(index), component / 'verify_source.py')
            baseline = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(baseline)
            if baseline.validate(source):
                raise ValueError('isolated candidate requires original baseline')
            baselines.append(baseline)
            paths.extend(Path(baseline.PROJECT) / item[0] for item in baseline.FILES)
        before = {str(p): digest(source / p) if (source / p).exists() else None for p in paths}
        report['original_sha256'] = before
        with tempfile.TemporaryDirectory(prefix='always-on-vpn-tu-') as directory:
            staged = Path(directory)
            for path in paths:
                (staged / path).parent.mkdir(parents=True, exist_ok=True)
                if (source / path).exists():
                    shutil.copy2(source / path, staged / path)
            for index, component in enumerate(COMPONENTS):
                for attempt in (1, 2):
                    with (args.output / f'apply-{index}-{attempt}.log').open('x') as log:
                        subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(staged)],
                                       stdout=log, stderr=subprocess.STDOUT, check=True)
                baselines[index].validate(staged, require_patched=True)
            report['candidate_sha256'] = {str(p): digest(staged / p) for p in paths}
            for product, triple in PRODUCTS.items():
                cwd = source / 'out' / product
                generation = args.output / (product + '-idl')
                generation.mkdir()
                metadata, entries = generate(source, cwd, staged, generation)
                overlay = args.output / (product + '-vfs.json')
                overlay.write_text(json.dumps({'version': 0, 'roots': entries + [
                    {'type': 'file', 'name': str(source / p), 'external-contents': str(staged / p)}
                    for p in paths]}, indent=2) + '\n')
                for index, target in enumerate(TARGETS):
                    if args.unit is not None and index not in args.unit:
                        continue
                    name = f'{product}-{index}'
                    original = query(source, cwd, target.format(product=product), args.output / (name + '-query.log'))
                    argv = original[:]
                    if Path(argv[0]).name == 'ccache':
                        argv.pop(0)
                    if Path(argv[0]).name != 'clang++' or '--target=' + triple not in argv or any(
                            argv.count(flag) != 1 for flag in ('-c', '-o', '-MF')):
                        raise ValueError('unexpected compiler command: ' + name)
                    unit = (cwd / argv[argv.index('-c') + 1]).resolve()
                    candidates = {str(source / p): str(staged / p) for p in paths}
                    candidates.update({entry['name']: entry['external-contents'] for entry in entries})
                    if str(unit) not in candidates:
                        raise ValueError('compiler source not part of candidate: ' + str(unit))
                    argv[1:1] = ['-ivfsoverlay', str(overlay)]
                    obj, deps = args.output / (name + '.o'), args.output / (name + '.d')
                    argv[argv.index('-o') + 1] = str(obj)
                    argv[argv.index('-MF') + 1] = str(deps)
                    log = args.output / (name + '-compile.log')
                    with log.open('x') as stream:
                        result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                                env=dict(os.environ, CCACHE_DISABLE='1'))
                    row = dict(product=product, target=target, original_argv=original, candidate_argv=argv,
                               exit_code=result.returncode, log_sha256=digest(log), generated_idl=metadata)
                    report['commands'].append(row)
                    if result.returncode:
                        raise ValueError('candidate compilation failed: ' + name)
                    if candidates[str(unit)] not in deps.read_text():
                        raise ValueError('candidate source not consumed: ' + name)
                    row.update(object_sha256=digest(obj), dependencies_sha256=digest(deps))
            if before != {str(p): digest(source / p) if (source / p).exists() else None for p in paths}:
                raise ValueError('production source changed')
            report['status'] = 'pass'
    except Exception as error:
        report['error'] = str(error)
    (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return int(report['status'] != 'pass')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--unit', type=int, choices=range(len(TARGETS)), action='append',
                        help='Compile selected unit indexes only; report lists exact coverage')
    raise SystemExit(run(parser.parse_args()))
