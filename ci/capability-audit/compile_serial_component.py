#!/usr/bin/env python3
"""Run full OHOS preload/load/GN for Serial in a separate scratch source/output.

Live sources and product outputs must be mounted read-only. This calls the
normal hb entry point after skipping build.sh's global npm/ohpm bootstrap;
it never invokes --fast-rebuild. GN success is not a product or runtime pass.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PRODUCT_PATHS = {'arm64_virt': 'qemu_arm64_linux_full', 'armv7a_virt': 'qemu_armv7a_linux_full',
                 'x86_64_virt': 'qemu_x86_64_linux_full'}
BUILD_TARGETS = ('serial_manager', 'serial_manager_tests', 'drivers_peripheral_serial', 'selinux_adapter')
NINJA_TARGETS = BUILD_TARGETS + ('base/usb/usb_manager/frameworks/dialog/dialog_ui/usb_right_dialog:dialog_hap',)
JSONCPP_ARCHIVE_SHA256 = 'f93b6dd7ce796b13d02c108bc9f79812245a82e577581c4c9aabe57075c90ea2'
NODE_RELATIVE_PATH = 'prebuilts/build-tools/common/nodejs/node-v18.20.1-linux-x64'


def jsoncpp_repair_evidence(repo, staged):
    """Bind the actual installer to the complete overlapping component stack."""
    component = repo / 'patches/common/third_party/jsoncpp/generated_source'
    patches = sorted(component.glob('[0-9][0-9][0-9][0-9]-*.patch'))
    if not patches:
        raise ValueError('JSONCPP repair evidence needs the complete numbered patch stack')
    installer = staged / 'third_party/jsoncpp/install.py'
    return {'installer_sha256': hashlib.sha256(installer.read_bytes()).hexdigest(),
            'patches': [{'path': patch.name, 'sha256': hashlib.sha256(patch.read_bytes()).hexdigest()}
                        for patch in patches],
            'applicator_sha256': hashlib.sha256((component / 'apply.py').read_bytes()).hexdigest()}


def build_environment(root, staged):
    """Use fixed release Node/npm, matching the production builder's Node18.

    r19's real TypeScript npm-pack failure is retained. Only this owned scratch
    cache is writable; no global bootstrap, install or network fetch is added.
    """
    root, staged = root.resolve(), staged.resolve()
    if staged == root or staged.is_relative_to(root) or root.is_relative_to(staged):
        raise ValueError('npm cache must remain in independently owned scratch')
    node_root = root / NODE_RELATIVE_PATH
    node_bin = node_root / 'bin'
    for name in ('node', 'npm'):
        tool = node_bin / name
        if not tool.is_file() or not tool.resolve().is_relative_to(root):
            raise ValueError('fixed release Node18 tool unavailable: ' + name)
    environment = dict(os.environ)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    environment['NODE_HOME'] = str(node_root)
    environment['PATH'] = os.pathsep.join((str(node_bin), str(root / 'prebuilts/build-tools/linux-x86/bin'),
                                           environment['PATH']))
    environment['npm_config_cache'] = str(staged / 'npm-cache')
    environment['npm_config_offline'] = 'true'
    environment['npm_config_update_notifier'] = 'false'
    return environment


def copy_jsoncpp_installer_workspace(root, staged, archive_sha256=JSONCPP_ARCHIVE_SHA256):
    """Isolate the fixed installer's actual source-adjacent extraction workspace.

    No installer changes, pre-generated inputs or production writes. Preserve
    r15's swallowed RO extraction failure independently from Serial status.
    """
    root, staged = root.resolve(), staged.resolve()
    if staged == root or staged.is_relative_to(root) or root.is_relative_to(staged):
        raise ValueError('jsoncpp installer workspace must be independently owned scratch')
    relative = Path('third_party/jsoncpp')
    original = root / relative
    archive = original / 'jsoncpp-1.9.6.tar.gz'
    if not original.resolve().is_relative_to(root) or hashlib.sha256(archive.read_bytes()).hexdigest() != archive_sha256:
        raise ValueError('jsoncpp input archive differs from fixed release bytes')
    target = staged / relative
    if not target.is_symlink() or target.resolve() != original.resolve():
        raise ValueError('unexpected jsoncpp installer scratch target')
    records = []
    for directory, subdirectories, filenames in os.walk(original, followlinks=False):
        subdirectories[:] = [name for name in subdirectories if name not in ('.git', '__pycache__')]
        if any((Path(directory) / name).is_symlink() for name in subdirectories):
            raise ValueError('jsoncpp installer directory must not escape through a symlink')
        for name in sorted(filenames):
            if name == '.git':
                continue
            source = Path(directory) / name
            if source.is_symlink():
                raise ValueError('jsoncpp installer input must not escape through a symlink')
            records.append({'source': str(source.relative_to(root)),
                            'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    target.unlink()
    shutil.copytree(original, target, symlinks=False, ignore=shutil.ignore_patterns('.git', '__pycache__'))
    for record in records:
        if hashlib.sha256((staged / record['source']).read_bytes()).hexdigest() != record['sha256']:
            raise ValueError('copied jsoncpp installer input changed')
    return sorted(records, key=lambda record: record['source'])


def materialize_idl_inputs(root, staged):
    """Preserve original IDL bytes locally for the fixed reader's W_OK check.

    This neither changes the reader nor copies generated headers. Production
    mount permissions and original inputs remain untouched.
    """
    records = []
    for top in ('base', 'foundation', 'interface', 'commonlibrary', 'domains', 'test', 'drivers'):
        if not (root / top).is_dir():
            continue
        for directory, subdirectories, filenames in os.walk(root / top, followlinks=False):
            subdirectories[:] = [name for name in subdirectories
                                 if name not in ('.git', '__pycache__', 'node_modules')]
            for name in sorted(filenames):
                if not name.endswith('.idl'):
                    continue
                source = Path(directory) / name
                relative = source.relative_to(root)
                if not source.resolve().is_relative_to(root):
                    raise ValueError('source IDL resolves outside the read-only production tree')
                cursor = staged
                for part in relative.parts[:-1]:
                    cursor = cursor / part
                    if cursor.is_symlink():
                        original = root / cursor.relative_to(staged)
                        if cursor.resolve() != original.resolve():
                            raise ValueError('unexpected scratch input directory symlink')
                        cursor.unlink()
                        cursor.mkdir()
                        for child in original.iterdir():
                            (cursor / child.name).symlink_to(child, target_is_directory=child.is_dir())
                    elif not cursor.is_dir():
                        raise ValueError('missing actual scratch IDL ancestor')
                target = staged / relative
                source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
                if target.is_symlink():
                    if target.resolve() != source.resolve():
                        raise ValueError('unexpected scratch IDL input symlink')
                    target.unlink()
                    shutil.copy2(source, target)
                if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != source_hash:
                    raise ValueError('existing scratch IDL source differs from fixed production input')
                records.append({'source': str(relative), 'sha256': source_hash})
    return sorted(records, key=lambda record: record['source'])


def expand_directory(root, staged, relative):
    directory = staged / relative
    if directory.is_symlink():
        directory.unlink()
        directory.mkdir()
        for child in (root / relative).iterdir():
            (directory / child.name).symlink_to(child, target_is_directory=child.is_dir())
    elif not directory.exists():
        directory.mkdir(parents=True)


def copy_component(root, staged, relative):
    path = Path(relative)
    for parent in reversed(path.parents):
        if parent != Path('.'):
            expand_directory(root, staged, parent)
    target = staged / path
    if target.is_symlink():
        target.unlink()
    shutil.copytree(root / path, target, symlinks=True)


def configure_serial_profile(repo, staged, product):
    """Remove every copied phone inherit before the scratch-wide PC params.

    All QEMU products share product_virt.para. Disabling only the selected ABI
    leaves another copied phone profile active and legitimately conflicts with
    FreeFormMultiWindow. This touches only the independently owned vendor copy.
    """
    existing = [name for name, relative in PRODUCT_PATHS.items()
                if (staged / 'vendor/ohemu' / relative / 'config.json').is_file()]
    if product not in existing:
        raise ValueError('selected Serial scratch product config is missing')
    selected = [argument for name in existing for argument in ('--product', name)]
    subprocess.run(['bash', str(repo / 'patches/phone/product_profile/apply.sh'),
                    '--source-root', str(staged), '--disable', *selected], check=True)
    subprocess.run(['bash', str(repo / 'patches/2in1/product_profile/apply.sh'),
                    '--source-root', str(staged), '--product', product], check=True)


def quarantine_moved_cmake_caches(root, staged, prior):
    """Preserve, but do not reuse, CMake binary directories bound to old paths.

    r20's real flatc failure is retained. Only independently owned, stopped
    incremental output is in scope; no source/cache bytes are rewritten.
    """
    root, staged, prior = root.resolve(), staged.resolve(), prior.resolve()
    output = staged / 'out'
    if (staged == root or staged.is_relative_to(root) or root.is_relative_to(staged)
            or output.is_symlink() or not output.is_dir()):
        raise ValueError('CMake cache quarantine requires independent owned output')
    destination = staged / 'serial-moved-cmake-cache'
    if destination.exists() or destination.is_symlink():
        raise ValueError('refusing to overwrite prior quarantined CMake cache')
    selected = []
    for directory, _, filenames in os.walk(output, followlinks=False):
        if 'CMakeCache.txt' not in filenames:
            continue
        cache = Path(directory) / 'CMakeCache.txt'
        if cache.is_symlink() or not cache.resolve().is_relative_to(output):
            raise ValueError('CMake input cache must not escape owned output')
        relative = cache.parent.relative_to(output)
        if len(relative.parts) < 2:
            raise ValueError('refusing to quarantine broad product output')
        values = [line.split('=', 1)[1] for line in cache.read_text().splitlines()
                  if line.startswith('CMAKE_CACHEFILE_DIR:INTERNAL=')]
        if values == [str(cache.parent)]:
            continue
        if values != [str(prior / 'out' / relative)]:
            raise ValueError('CMake cache does not match stopped prior scratch')
        selected.append((cache.parent, relative, hashlib.sha256(cache.read_bytes()).hexdigest(), values[0]))
    # Validate every input first. Nested build directories are preserved as
    # part of the outer binary directory, not moved twice.
    records = []
    for binary, relative, digest, old_directory in sorted(selected, key=lambda row: len(row[1].parts)):
        record = {'binary_directory': str(relative), 'prior_cache_directory': old_directory,
                  'cmake_cache_sha256': digest, 'operation': 'quarantined_owned_path_bound_binary_directory'}
        enclosing = next((row for row in records if binary.is_relative_to(output / row['binary_directory'])), None)
        if enclosing is None:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(binary), str(target))
        record['quarantine_directory'] = str(destination / relative)
        records.append(record)
    return records


def move_stopped_scratch_output(root, staged, output, product):
    seed = output.resolve()
    prior = seed.parent
    evidence_path = prior / 'serial-build-evidence.json'
    evidence = json.loads(evidence_path.read_text())
    if seed.name != 'out' or seed.is_relative_to(root) or seed == staged / 'out' or not seed.is_dir():
        raise ValueError('output seed must be a separate isolated Serial scratch out')
    if evidence.get('scratch_source') != str(prior) or evidence.get('product') != product:
        raise ValueError('output seed provenance does not match this isolated Serial product')
    ancestry = evidence
    seen = {str(prior)}
    while ancestry.get('gn_exit_code') != 0:
        inherited = ancestry.get('incremental_seed', {})
        ancestor = Path(inherited.get('prior_scratch', '')).resolve()
        ancestor_evidence = ancestor / 'serial-build-evidence.json'
        if (str(ancestor) in seen or ancestor.is_relative_to(root)
                or not ancestor_evidence.is_file()
                or hashlib.sha256(ancestor_evidence.read_bytes()).hexdigest()
                != inherited.get('prior_evidence_sha256')):
            raise ValueError('failed-GN output seed lacks an intact owned scratch ancestry')
        seen.add(str(ancestor))
        ancestry = json.loads(ancestor_evidence.read_text())
        if (ancestry.get('scratch_source') != str(ancestor) or ancestry.get('product') != product
                or ancestry.get('first_package_gate_passed') is not False):
            raise ValueError('output seed ancestry is not the same non-runtime Serial product')
    if 'compile_exit_code' not in ancestry or evidence.get('first_package_gate_passed') is not False:
        raise ValueError('output seed needs completed/interrupted non-runtime compile evidence')
    for process in Path('/proc').iterdir():
        if process.name.isdigit():
            try:
                arguments = (process / 'cmdline').read_bytes().split(b'\0')
                process_cwd = (process / 'cwd').resolve(strict=True)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
            if (process_cwd.is_relative_to(seed) or
                    (any(b'ninja' in argument for argument in arguments) and str(seed / product).encode() in arguments)):
                raise ValueError('refusing to move output used by a running scratch process')
    # A directory move retains ordinary Ninja state without copying 3+ GiB;
    # a symlink would resolve relative source paths back to the old candidate.
    shutil.move(str(seed), str(staged / 'out'))
    caches = quarantine_moved_cmake_caches(root, staged, prior)
    return {'prior_scratch': str(prior), 'prior_evidence_sha256': hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            'prior_compile_exit_code': ancestry['compile_exit_code'], 'operation': 'moved_stopped_owned_scratch_out',
            'path_bound_cmake_binary_directories': caches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--source-repo', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCT_PATHS, default='arm64_virt')
    parser.add_argument('--work-dir', type=Path)
    parser.add_argument('--compile', action='store_true', help='Run the component/test Ninja targets after full GN')
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--seed-output', type=Path, help='Move output from a stopped, evidenced Serial scratch only')
    args = parser.parse_args()
    root = args.source_root.resolve()
    repo = args.repo_root.resolve()
    if not os.statvfs(root).f_flag & os.ST_RDONLY:
        raise ValueError('release source must be mounted read-only')
    if (root / 'out').exists() and not os.statvfs(root / 'out').f_flag & os.ST_RDONLY:
        raise ValueError('live output must be mounted read-only')
    staged = args.work_dir.resolve() if args.work_dir else Path(tempfile.mkdtemp(prefix='serial-full-gn-'))
    staged.mkdir(parents=True, exist_ok=True)
    if any(staged.iterdir()) or staged == root or staged in root.parents or root in staged.parents or not 1 <= args.jobs <= 2:
        raise ValueError('scratch work directory must be empty and distinct from the source')
    for child in root.iterdir():
        if child.name not in {'out', 'build', '.ccache', '.git', '.gn', '.ohos-qemu-patches'}:
            (staged / child.name).symlink_to(child, target_is_directory=child.is_dir())
    shutil.copy2(root / '.gn', staged / '.gn')
    shutil.copytree(root / 'build', staged / 'build', symlinks=True)
    subprocess.run(['bash', str(repo / 'patches/common/build/notice/readonly_input/apply.sh'),
                    '--source-root', str(staged)], check=True)
    copy_component(root, staged, 'vendor/ohemu')
    copy_component(root, staged, 'productdefine')
    copy_component(root, staged, 'base/usb/usb_manager')
    copy_component(root, staged, 'base/startup')
    # Preserve LOAD topology: materialize all 125 MiB security siblings, not
    # one component behind child symlinks. Production remains read-only.
    copy_component(root, staged, 'base/security')
    subprocess.run(['bash', str(repo / 'patches/2in1/base/security/selinux_adapter/serial_metadata/apply.sh'),
                    '--source-root', str(staged)], check=True)
    copy_component(root, staged, 'device/qemu')
    copy_component(root, staged, 'foundation/window/window_manager/etc')
    # The loader recursively scans drivers without following child symlinks.
    # Materialize the whole 79 MiB tree, also isolating camera GN's config touch.
    copy_component(root, staged, 'drivers')
    expand_directory(root, staged, Path('base/busmanager'))
    subprocess.run(['bash', str(repo / 'patches/2in1/base/busmanager/serial_manager/apply.sh'),
                    '--source-root', str(staged), '--source-repo', str(args.source_repo.resolve())], check=True)
    subprocess.run(['bash', str(repo / 'patches/2in1/base/usb/usb_manager/serial_dialog/apply.sh'),
                    '--source-root', str(staged)], check=True)
    for component in ('base/startup/init/serial_devices', 'device/qemu/serial_usb_endpoint'):
        subprocess.run(['bash', str(repo / 'patches/2in1' / component / 'apply.sh'),
                        '--source-root', str(staged)], check=True)
    configure_serial_profile(repo, staged, args.product)
    config_path = staged / 'vendor/ohemu' / PRODUCT_PATHS[args.product] / 'config.json'
    config = json.loads(config_path.read_text())
    additions = {'busmanager': ['serial_manager'],
                 'hdf': ['drivers_interface_serial', 'drivers_peripheral_serial']}
    for subsystem, components in additions.items():
        entry = next((item for item in config['subsystems'] if item['subsystem'] == subsystem), None)
        if entry is None:
            entry = {'subsystem': subsystem, 'components': []}
            config['subsystems'].append(entry)
        for component in components:
            if not any(item['component'] == component for item in entry['components']):
                entry['components'].append({'component': component, 'features': []})
    config_path.write_text(json.dumps(config, indent=2) + '\n')
    source_manifest = staged / 'serial-candidate-source-manifest.json'
    candidate_inputs = []
    for component in ('base/busmanager/serial_manager',
                      'base/usb/usb_manager/frameworks/dialog/dialog_ui/usb_right_dialog/src/main/ets'):
        for source in sorted((staged / component).rglob('*')):
            if source.is_file():
                candidate_inputs.append({'source': str(source.relative_to(staged)),
                                         'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    source_manifest.write_text(json.dumps(candidate_inputs, indent=2) + '\n')
    policy = staged / 'base/security/selinux_adapter/sepolicy/ohos_policy/busmanager/serial_manager/system/serial_service.te'
    candidate_inputs.append({'source': str(policy.relative_to(staged)),
                             'sha256': hashlib.sha256(policy.read_bytes()).hexdigest()})
    source_manifest.write_text(json.dumps(candidate_inputs, indent=2) + '\n')
    seed_info = move_stopped_scratch_output(root, staged, args.seed_output, args.product) if args.seed_output else None
    python = root / 'prebuilts/python/linux-x86/3.11.4/bin/python3'
    if not python.is_file():
        python = Path(sys.executable)
    command = [str(python), str(staged / 'build/hb/main.py'), 'build', '--no-indep',
               '--product-name', args.product, '--prebuilt-sdk=true', '--build-target',
               *BUILD_TARGETS, '--build-only-gn', '--ccache=false',
               '--gn-args', 'device_type="2in1"']
    environment = build_environment(root, staged)
    log = staged / 'serial-full-gn.log'
    with log.open('w') as stream:
        process = subprocess.run(command, cwd=staged, env=environment, stdout=stream, stderr=subprocess.STDOUT)
    # LOAD's part discovery does not follow child directory symlinks. Keep the
    # proven GN staging topology until LOAD/GN finish, then materialize only
    # identical source IDL inputs for the real tool's separate W_OK requirement.
    idl_inputs = materialize_idl_inputs(root, staged) if process.returncode == 0 else []
    # LOAD does not follow child-directory links: preserve its original
    # third_party topology until GN succeeds, just like IDL materialization.
    installer_inputs = []
    if process.returncode == 0:
        expand_directory(root, staged, Path('third_party'))
        installer_inputs = copy_jsoncpp_installer_workspace(root, staged)
        fixed_git = (root / 'third_party/jsoncpp/.git').resolve()
        if not fixed_git.is_dir() or not fixed_git.is_relative_to(root):
            raise ValueError('jsoncpp fixed git metadata must remain in read-only production input')
        (staged / 'third_party/jsoncpp/.git').symlink_to(fixed_git, target_is_directory=True)
        subprocess.run(['bash', str(repo / 'patches/common/third_party/jsoncpp/generated_source/apply.sh'),
                        '--source-root', str(staged)], check=True, env=environment)
    installer_manifest = staged / 'serial-original-jsoncpp-inputs.json'
    installer_manifest.write_text(json.dumps(installer_inputs, indent=2) + '\n')
    idl_manifest = staged / 'serial-original-idl-inputs.json'
    idl_manifest.write_text(json.dumps(idl_inputs, indent=2) + '\n')
    result = {'scope': 'full_preload_load_gn_candidate_not_product_runtime_acceptance',
              'product': args.product, 'device_type': '2in1', 'scratch_source': str(staged),
              'command': command, 'gn_exit_code': process.returncode,
              'gn_log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
              'candidate_source_manifest': str(source_manifest),
              'candidate_source_manifest_sha256': hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
              'original_jsoncpp_inputs_manifest_sha256': hashlib.sha256(installer_manifest.read_bytes()).hexdigest(),
              'unmodified_materialized_source_IDL_count': len(idl_inputs),
              'source_IDL_manifest': str(idl_manifest),
              'source_IDL_manifest_sha256': hashlib.sha256(idl_manifest.read_bytes()).hexdigest(),
              'node_environment': {'node_home': environment['NODE_HOME'],
                  'node_sha256': hashlib.sha256((root / NODE_RELATIVE_PATH / 'bin/node').read_bytes()).hexdigest(),
                  'npm_cli_sha256': hashlib.sha256((root / NODE_RELATIVE_PATH / 'bin/npm').read_bytes()).hexdigest(),
                  'owned_npm_cache': environment['npm_config_cache'], 'npm_offline': True},
              'first_package_gate_passed': False, 'product_component_compile_passed': False}
    if process.returncode == 0:
        result['jsoncpp_generated_source_repair'] = jsoncpp_repair_evidence(repo, staged)
    if seed_info:
        result['incremental_seed'] = seed_info
    if process.returncode == 0 and args.compile:
        # Match the fixed release build/hb/services/ninja.py executor policy.
        compile_command = [str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'), '-w', 'dupbuild=warn', '-C',
                           str(staged / 'out' / args.product), '-j', str(args.jobs),
                           *NINJA_TARGETS]
        compile_log = staged / 'serial-component-build.log'
        with compile_log.open('w') as stream:
            compiled = subprocess.run(compile_command, cwd=staged, env=environment,
                                      stdout=stream, stderr=subprocess.STDOUT)
        result.update(compile_command=compile_command, compile_exit_code=compiled.returncode,
                      compile_log_sha256=hashlib.sha256(compile_log.read_bytes()).hexdigest(),
                      product_component_compile_passed=compiled.returncode == 0)
    (staged / 'serial-build-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    print(log.read_text()[-12000:])
    if process.returncode != 0:
        return process.returncode
    return result.get('compile_exit_code', 0)


if __name__ == '__main__':
    raise SystemExit(main())
