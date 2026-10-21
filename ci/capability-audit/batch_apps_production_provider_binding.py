"""Replay historical native08/F09 or explicit completed same-source provider evidence.

No compiler, signer, guest, source-tree access, or invented fresh-build receipt.
Independent SDK projects remain separate evidence owned by the caller.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import tarfile

SOURCE = '/Volumes/PSSD/qemu/openharmony'
PRODUCT = 'arm64_virt'
NATIVE_COMMIT = '5efd8bab50092339a97f17ccf37d1c6b78c47872'
PACKAGE_COMMIT = 'fcabc7ec82be387761a3383a4ec5efa65cf915e3'
ARCHIVE_SHA256 = '19eeedad8aabde7c8af3534fc643793cbb179bff4a630d13a430f6b3ece5ed4a'
DISCOVERY_SHA256 = 'f6f41151f6a432b91a2be30d81288571b112bdc76c5a39771686f0cdd9e2fbdf'
SUPPLEMENT_SHA256 = '1e0a6627d49f969201f7caedb33fc9d13a7274f953bc3523a471495bf0daf509'
PROVIDERS = {
    'contacts': ('applications/standard/contacts', 'contacts_hap', 'Contacts', 'entry',
                 '65de33df8d6d7aaa5797a5625ed0e5938e5cb050', 'b695ce39',
                 'entry/build/default/outputs/default/entry-default-unsigned.hap'),
    'theme': ('applications/standard/theme', 'wallpaper_phone_hap', 'Wallpaper', 'phone_wallpaper',
              'a436a43f1c0948fa12df6d520ec695ae4388a057', '62182905',
              'product/phone/build/default/outputs/default/phone_wallpaper-default-unsigned.hap'),
}
FIELDS = {'schema_version', 'discovery', 'supplement', 'native_evidence', 'native_build_log',
          'native_launcher_log', 'archive'}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            result.update(block)
    return result.hexdigest()


def regular(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and path.is_file() and
            not any(p.is_symlink() for p in (path, *path.parents)), 'unaliased retained production evidence required')
    return path


def record(path):
    path = regular(path)
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def checked(value):
    require(isinstance(value, dict) and {'path', 'sha256'} <= value.keys() <= {'path', 'sha256', 'bytes'},
            'exact retained artifact descriptor required')
    path = regular(value['path'])
    require(re.fullmatch('[a-f0-9]{64}', value.get('sha256', '')) and sha(path) == value['sha256'],
            'production evidence hash changed')
    if 'bytes' in value:
        require(type(value['bytes']) is int and path.stat().st_size == value['bytes'], 'production evidence size changed')
    return path


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate production JSON field')
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique)


def tree_digest(files):
    require(isinstance(files, dict) and files and all(isinstance(k, str) and isinstance(v, str) and
            re.fullmatch('[a-f0-9]{64}', v) for k, v in files.items()), 'complete frozen production input map required')
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def retained_exports(document, directory):
    """Only open exported regular files; never follow original source/key paths."""
    result = {}
    for row in document:
        name = row['path']
        require(name.startswith(SOURCE + '/') and '..' not in PurePosixPath(name).parts,
                'fixed production source prefix required')
        resolved = row.get('resolved')
        # The fixed discovery also inventories this unrelated staged symlink.
        # Provider/source/runner consumers below still require unaliased inputs.
        alias = (SOURCE + '/out/arm64_virt/packages/phone/system/lib64/platformsdk/libutils.z.so',
                 SOURCE + '/out/arm64_virt/packages/phone/system/lib64/chipset-sdk-sp/libutils.z.so')
        require(resolved == name or (name, resolved) == alias, 'export redirected a production input')
        relative = resolved.removeprefix(SOURCE + '/')
        require(row.get('export_relative') == 'files/' + relative, 'export path differs from actual resolved input')
        path = regular(directory / row['export_relative'])
        require(sha(path) == row['sha256'] and path.stat().st_size == row['bytes'], 'retained exported bytes changed')
        if name in result:
            require(result[name][0] == row, 'conflicting duplicate production export')
        result[name] = (row, path)
    return result



def verify_prior_inputs(first, second):
    # Supplement 05 re-stats source inventories/HAPs; the complete graphs and
    # kernel headers remain actual immutable 04 exports, not a second capture.
    original = [*first['project_haps'], *first['staged'],
                *(row for inventory in first['source_inventory'].values() for row in inventory.values())]
    previous = {row['path']: row for row in original}
    observed = {row['path']: row for row in second['unchanged_prior_inputs']}
    require(len(previous) == len(original) and len(observed) == len(second['unchanged_prior_inputs']) and
            previous.keys() == observed.keys(), 'complete actual source/HAP prior re-stat inventory required')
    for name, row in previous.items():
        require(all(observed[name][key] == row[key] for key in ('resolved', 'sha256', 'bytes', 'mode', 'mtime_ns')),
                'original producer source/HAP input changed before supplementation')
    return len(previous)



def native_launcher_phases(raw):
    """Distinguish the real load-only preparation from the later image build."""
    lines = re.sub(r'\x1b\[[0-9;]*m', '', raw).splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith('Build args: ')]
    success = [index for index, line in enumerate(lines)
               if re.fullmatch(r'\[OHOS INFO\]\s+arm64_virt build success\s*', line)]
    require(len(starts) == len(success) == 2, 'actual load-only and native-image success phases required')
    result = []
    for sequence, (stage, load_only, device) in enumerate((('load_only', 'true', 'default'), ('native_images', 'false', 'phone'))):
        begin = starts[sequence]; end = starts[sequence + 1] if sequence + 1 < len(starts) else len(lines)
        argv = shlex.split(lines[begin].removeprefix('Build args: '))
        selected = [index for index in success if begin < index < end]
        require(option(argv, '--product-name') == PRODUCT and option(argv, '--build-target') == 'images' and
                option(argv, '--device-type') == device and
                [value for value in argv if value.startswith('--build-only-load=')] == ['--build-only-load=' + load_only] and
                len(selected) == 1, 'native launcher success belongs to another preparation/build phase')
        index = selected[0]
        cost = re.fullmatch(r'\[OHOS INFO\]\s+Cost Time:\s+([0-9]+:[0-9]{2}:[0-9]{2})\s*', lines[index + 1] if index + 1 < end else '')
        require(cost is not None, 'actual native phase completion/cost footer missing')
        result.append({'stage': stage, 'build_only_load': load_only == 'true',
                       'build_args_line': begin + 1, 'success_line': index + 1, 'cost_time': cost[1]})
    return result


def selected_byte_source(relative, provider_name):
    if relative == 'local.properties':
        return False
    return ('/src/main/' in relative or relative.startswith('AppScope/') or
            (Path(relative).suffix in ('.ets', '.ts', '.js', '.json5') and not relative.startswith(('sign/', 'signature/'))) or
            relative == 'BUILD.gn' or (provider_name == 'contacts' and relative == 'entry/modules.ap'))


def local_properties_proof(first, second, directory, provider_name):
    """Hash the dedicated public export without pretending it is source_bytes."""
    project = PROVIDERS[provider_name][0]; original = first['source_inventory'][provider_name]['local.properties']
    expected = SOURCE + '/' + project + '/local.properties'
    require(original['path'] == original['resolved'] == expected, 'original local.properties inventory path differs')
    descriptor = second['public_properties'][project]
    retained = retained_exports([descriptor], directory)
    require(set(retained) == {expected} and descriptor['resolved'] == expected,
            'actual selected public-properties export path differs')
    path = retained[expected][1]
    return {'scope': 'inventory_restat_plus_separate_public_export_NOT_complete_original_source_bytes_replay',
            'original_inventory': dict(original), 'public_export_metadata': dict(descriptor),
            'retained_public_export': record(path),
            'public_export_matches_inventory_sha256': descriptor['sha256'] == original['sha256'],
            'counted_in_source_files_verified': False, 'original_source_path_opened': False,
            'complete_original_source_bytes_replayed': False}


def ninja_decode(value):
    """Decode only actual Ninja literal escapes, without shell execution."""
    result = []; index = 0
    while index < len(value):
        char = value[index]
        if char == '$':
            index += 1
            require(index < len(value) and value[index] in ' $:', 'unexpanded production Ninja variable')
            char = value[index]
        result.append(char); index += 1
    return ''.join(result)


def option(argv, name):
    require(argv.count(name) == 1 and argv.index(name) + 1 < len(argv), 'unique production command option required: ' + name)
    return argv[argv.index(name) + 1]


def graph_actions(path, project, target):
    """Read exact inline rules and their actual edges from the whole raw graph."""
    labels = {part: 'ACTION //' + project + ':' + target + suffix + '(//build/toolchain/ohos:ohos_clang_arm64)'
              for part, suffix in (('compile', '_compile_app'), ('sign', ''), ('info', '_info'))}
    found = {}; names = {}; edges = {}; rule = command = None
    with Path(path).open() as stream:
        for line in stream:
            if line.startswith('rule '):
                rule = line[5:].strip(); command = None
            elif rule and line.startswith('  command = '):
                command = line.removeprefix('  command = ').rstrip('\n')
            elif rule and line.startswith('  description = '):
                description = line.removeprefix('  description = ').rstrip('\n')
                for part, label in labels.items():
                    if description == label:
                        require(part not in found and command is not None, 'duplicate/missing production action')
                        found[part] = shlex.split(ninja_decode(command)); names[rule] = part
            elif line.startswith('build '):
                for name, part in names.items():
                    token = ': ' + name + ' '
                    if token in line:
                        require(part not in edges, 'duplicate production action edge')
                        output, dependencies = line[6:].split(token, 1)
                        edges[part] = {'output': output, 'dependencies': shlex.split(ninja_decode(dependencies))}
    require(set(found) == set(labels) == set(edges), 'actual compile/sign/module-info edges missing')
    stem = 'obj/' + project + '/' + target
    require(edges['compile']['output'] == stem + '/unsigned_hap_path_list.json' and
            edges['sign']['output'] == stem + '.stamp' and edges['info']['output'] == stem + '_module_info.json',
            'production action outputs differ')
    for part, script in (('compile', 'compile_app.py'), ('sign', 'app_sign.py')):
        require(found[part][:2] == ['/usr/bin/env', '../../build/scripts/' + script], 'production runner differs')
    for name, value in {'--cwd': '../../' + project + '/', '--build-profile': '../../' + project + '/build-profile.json5',
                        '--sdk-home': SOURCE + '/prebuilts/ohos-sdk/linux', '--product': 'default',
                        '--assemble-type': 'assembleHap', '--build-level': 'module',
                        '--output-file': stem + '/unsigned_hap_path_list.json'}.items():
        require(option(found['compile'], name) == value, 'wrong selected production compile input')
    require('--hvigor-obfuscation' in found['compile'], 'actual selected production obfuscation option missing')
    require(stem + '_compile_app.stamp' in edges['sign']['dependencies'] and
            stem + '_info.stamp' in edges['sign']['dependencies'], 'sign action is disconnected from production compile/info')
    return found, edges


def public_commands(commands):
    result = {}
    for name, values in commands.items():
        values = list(values)
        for flag in ('--keyPwd', '--keystorePwd'):
            if flag in values:
                values[values.index(flag) + 1] = '<redacted>'
        result[name] = values
    return result


def archive_metadata(archive):
    from boot_package import members_checked
    root = archive.name.removesuffix('.tar.gz')
    wanted = {'build-inputs.json', 'native-build-inputs.json', 'native-to-package-lineage.json',
              'openharmony-project-heads.json', 'contacts-theme-provider-evidence.json', 'SHA256SUMS'}
    result = {}; members = []
    with tarfile.open(archive, 'r|gz') as stream:
        for item in stream:
            members.append(item)
            require(len(members) < 50000, 'bounded production archive required')
            relative = item.name.removeprefix(root + '/')
            if relative not in wanted:
                continue
            require(item.name == root + '/' + relative and item.isfile() and item.size <= 8 * 1024 * 1024 and
                    relative not in result, 'unique bounded top-level production metadata required')
            result[relative] = stream.extractfile(item).read()
    members_checked(members, root)
    require(set(result) == wanted, 'complete native-A/package-B provenance required')
    checksums = {}
    for line in result['SHA256SUMS'].decode().splitlines():
        match = re.fullmatch(r'([a-f0-9]{64}) [ *](?:\./)?(.+)', line)
        require(match is not None and match[2] not in checksums, 'unambiguous package checksums required')
        checksums[match[2]] = match[1]
    for name, raw in result.items():
        if name != 'SHA256SUMS':
            require(checksums.get(name) == hashlib.sha256(raw).hexdigest(), 'production metadata differs from package inventory')
    return {name: decode(raw) for name, raw in result.items() if name != 'SHA256SUMS'}


def verify_historical_provider(config, *, provider_name, device, signed_hap, system_image_sha256):
    """Pure file replay API used by both capture and independent re-verification."""
    require(isinstance(config, dict) and set(config) == FIELDS and type(config['schema_version']) is int and
            config['schema_version'] == 1 and provider_name in PROVIDERS and device == 'phone',
            'exact retained native08 representative provider configuration required')
    paths = {key: checked(value) for key, value in config.items() if key != 'schema_version'}
    require(sha(paths['archive']) == ARCHIVE_SHA256 and sha(paths['discovery']) == DISCOVERY_SHA256 and
            sha(paths['supplement']) == SUPPLEMENT_SHA256,
            'actual F09/native producer discovery identity required')
    first, second = decode(paths['discovery'].read_bytes()), decode(paths['supplement'].read_bytes())
    require(second['prior_discovery_sha256'] == sha(paths['discovery']), 'producer supplement differs from original capture')
    rows = [row for key in ('graphs', 'project_haps', 'staged', 'kernel', 'source_bytes') for row in first[key]]
    exported = retained_exports(rows, paths['discovery'].parent)
    prior_count = verify_prior_inputs(first, second)
    extra = retained_exports(second['files'], paths['supplement'].parent)
    for name, value in extra.items():
        require(name not in exported or exported[name][0]['sha256'] == value[0]['sha256'], 'supplement replaced an original producer input')
        exported[name] = value
    def artifact(relative):
        require(SOURCE + '/' + relative in exported, 'actual exported production input missing: ' + relative)
        selected, path = exported[SOURCE + '/' + relative]
        require(selected['resolved'] == selected['path'], 'selected provider/source/runner input must not be aliased')
        return path
    metadata = archive_metadata(paths['archive'])
    native_inputs, package_inputs = metadata['native-build-inputs.json'], metadata['build-inputs.json']
    lineage = metadata['native-to-package-lineage.json']
    require(tree_digest(native_inputs['files_sha256']) == native_inputs['tree_sha256'] == lineage['native_build_inputs_tree_sha256'] and
            tree_digest(package_inputs['files_sha256']) == package_inputs['tree_sha256'] == lineage['package_build_inputs_tree_sha256'],
            'native/package frozen trees differ from actual F09 lineage')
    delta = {p: {'native_A': native_inputs['files_sha256'].get(p), 'packaging_B': package_inputs['files_sha256'].get(p)}
             for p in sorted(native_inputs['files_sha256'].keys() | package_inputs['files_sha256'].keys())
             if native_inputs['files_sha256'].get(p) != package_inputs['files_sha256'].get(p)}
    require(delta == lineage['complete_input_delta'] and not any(p.startswith('patches/') for p in delta) and
            lineage['native_source_commit'] == NATIVE_COMMIT and lineage['packaging_and_validation_commit'] == PACKAGE_COMMIT and
            lineage['native_overall_attempt_exit_code'] == 1 and lineage['native_product_and_images_build_success'] is True and
            lineage['all_native_recipes_and_tool_inputs_unchanged'] is True and lineage['packager_image_transformations_unchanged'] is True,
            'original failed native08 attempt/package09 lineage differs')
    native = decode(paths['native_evidence'].read_bytes())
    require(native['source_commit'] == NATIVE_COMMIT and type(native['exit_code']) is int and native['exit_code'] == 1 and
            native['launcher_log_sha256'] == sha(paths['native_launcher_log']) and not native.get('package'),
            'preserve actual original native08 overall failure and launcher bytes')
    for key in ('native_evidence', 'native_build_log', 'native_launcher_log'):
        require(any(item['sha256'] == sha(paths[key]) and item['bytes'] == paths[key].stat().st_size
                    for item in lineage['external_evidence']), 'native evidence is outside actual archive lineage')
    launcher = paths['native_launcher_log'].read_text()
    launcher_phases = native_launcher_phases(launcher)
    project, target, title, module, revision, trace, unsigned_relative = PROVIDERS[provider_name]
    selected_git = [row for row in second['project_git'] if row['argv'] == ['git', '-C', SOURCE + '/' + project, 'rev-parse', 'HEAD']]
    require(len(selected_git) == 1 and selected_git[0]['exit_code'] == 0 and selected_git[0]['stdout'] == revision,
            'actual selected production project HEAD differs')
    heads = metadata['openharmony-project-heads.json']
    require(heads['status'] == 'pass' and len([row for row in heads['projects'] if row['path'] == project and
            row['revision'] == row['observed_head'] == revision]) == 1, 'F09 production source project differs')
    inventory = first['source_inventory'][provider_name]
    selected_sources = {}
    for relative, source in inventory.items():
        if selected_byte_source(relative, provider_name):
            file = artifact(project + '/' + relative)
            require(source['sha256'] == sha(file), 'actual production source snapshot differs')
            selected_sources[relative] = source['sha256']
    properties = local_properties_proof(first, second, paths['supplement'].parent, provider_name)
    prefix = 'out/' + PRODUCT + '/obj/' + project + '/' + target
    unsigned_list = decode(artifact(prefix + '/unsigned_hap_path_list.json').read_bytes())
    require(set(unsigned_list) == {'unsigned_hap_path_list'} and len(unsigned_list['unsigned_hap_path_list']) == 1 and
            str(PurePosixPath(unsigned_list['unsigned_hap_path_list'][0])) == SOURCE + '/' + project + '/' + unsigned_relative,
            'actual compile action selected another unsigned HAP')
    unsigned = artifact(project + '/' + unsigned_relative)
    produced = artifact(prefix + '/' + title + '.hap')
    staged = artifact('out/' + PRODUCT + '/packages/phone/system/app/' + ('com.ohos.contacts' if provider_name == 'contacts' else 'com.ohos.wallpaper') + '/' + title + '.hap')
    signed_hap = regular(signed_hap)
    guard = metadata['contacts-theme-provider-evidence.json']
    require(guard['status'] == 'pass' and guard['failures'] == [] and guard['device'] == device and
            guard['system_image_sha256'] == system_image_sha256 and
            sha(produced) == sha(staged) == sha(signed_hap) == guard['providers'][provider_name]['hap_sha256'] and
            lineage['native_to_packaged_images']['system.img']['packaged_sha256'] == system_image_sha256,
            'actual produced/staged/F09 signed provider bytes differ')
    stem = 'obj/' + project + '/' + target
    info = decode(artifact(prefix + '_module_info.json').read_bytes())
    install = decode(artifact(prefix + '_install_info.json').read_bytes())
    label = '//' + project + ':' + target + '(//build/toolchain/ohos:ohos_clang_arm64)'
    bundle = 'com.ohos.contacts' if provider_name == 'contacts' else 'com.ohos.wallpaper'
    require(info['source'] == stem and info['dest'] == ['system/app/' + bundle + '/'] and info['install_enable'] is True and
            info['label'] == label and info['label_name'] == target and info['part_name'] == 'prebuilt_hap' and info['type'] == 'app' and
            install == [{'module_def': label, 'module_info_file': stem + '_module_info.json', 'part_name': 'prebuilt_hap',
                         'subsystem_name': 'applications', 'toolchain': '//build/toolchain/ohos:ohos_clang_arm64', 'toolchain_out_dir': '.'}],
            'actual production signed-to-install mapping differs')
    graph = artifact('out/' + PRODUCT + '/toolchain.ninja')
    commands, edges = graph_actions(graph, project, target)
    require(option(commands['compile'], '--build-modules') == module, 'selected native compile module differs')
    for flag, expected in {'--unsigned-hap-path-list': stem + '/unsigned_hap_path_list.json', '--hap-out-dir': stem,
                           '--hap-name': title, '--hap-list': stem + '/hap_list.json',
                           '--profileFile': '../../' + project + '/signature/' + ('contacts.p7b' if provider_name == 'contacts' else 'wallpaper.p7b'),
                           '--hapsigner': '../../developtools/hapsigner/dist/hap-sign-tool.jar'}.items():
        require(option(commands['sign'], flag) == expected, 'actual producer signing input differs')
    require(SOURCE + '/' + prefix + '/hap_list.json' in second['absent'], 'unreviewed producer HAP rename/filter selection')
    runner_files = ('build/scripts/compile_app.py', 'build/scripts/app_sign.py', 'build/scripts/check_hvigor_hap.py',
                    'build/templates/metadata/gen_module_info.py', 'build/ohos/app/app.gni', 'build/ohos/app/app_internal.gni')
    runners = {name: record(artifact(name)) for name in runner_files}
    build_log = paths['native_build_log'].read_text()
    expected_hvigor = 'hvigor cmd: bash ' + SOURCE + '/prebuilts/tool/command-line-tools/6.x/hvigor/bin/hvigorw assembleHap --mode module -p product=default -p module=' + module + ' -p debuggable=false -p buildMode=release --no-daemon'
    require(build_log.count('[' + trace + '] ' + expected_hvigor) == 1 and
            '[' + trace + '] project dir: ' + SOURCE + '/' + project in build_log and
            '[' + trace + '] Hvigor info: > hvigor BUILD SUCCESSFUL' in build_log and
            '[' + trace + '] Hvigor info: > hvigor UP-TO-DATE :' + module + ':default@CompileArkTS' in build_log and
            'ACTION //' + project + ':' + target + '_compile_app(' in build_log and
            'ACTION //' + project + ':' + target + '(' in build_log, 'actual native08 selected cached build/sign trace missing')
    from batch_apps_contact_picker_coordinator import verify_signed_payload
    verify_signed_payload(unsigned, signed_hap)
    relative_module = 'entry/src/main/module.json5' if provider_name == 'contacts' else 'product/phone/src/main/module.json5'
    return {'schema_version': 1, 'scope': 'actual_native08_cached_provider_unsigned_to_F09_NOT_fresh_compile_or_guest',
            'native_source_commit': NATIVE_COMMIT, 'packaging_source_commit': PACKAGE_COMMIT,
            'archive': record(paths['archive']), 'system_image_sha256': system_image_sha256,
            'producer_discovery': record(paths['discovery']), 'producer_supplement': record(paths['supplement']),
            'native_evidence': record(paths['native_evidence']), 'native_build_log': record(paths['native_build_log']),
            'native_launcher_log': record(paths['native_launcher_log']), 'native_launcher_phases': launcher_phases,
            'source_project': project, 'source_revision': revision,
            'source_module': record(artifact(project + '/' + relative_module)),
            'source_inventory_sha256': hashlib.sha256(json.dumps(selected_sources, sort_keys=True).encode()).hexdigest(),
            'source_files_verified': len(selected_sources),
            'source_inventory_scope': 'selected_actual_exported_source_bytes_excluding_local_properties',
            'source_bytes_replay_complete': False, 'local_properties': properties,
            'supplement_prior_source_hap_inputs_rechecked': prior_count,
            'graphs_from_original_discovery': True, 'production_unsigned_hap': record(unsigned),
            'production_signed_hap': record(produced), 'staged_signed_hap': record(staged),
            'image_signed_hap_sha256': sha(signed_hap),
            'unsigned_path_list': record(artifact(prefix + '/unsigned_hap_path_list.json')),
            'module_info': record(artifact(prefix + '_module_info.json')),
            'install_info': record(artifact(prefix + '_install_info.json')),
            'graph': record(graph), 'commands': public_commands(commands), 'edges': edges, 'public_runners': runners,
            'native_build_inputs_tree_sha256': native_inputs['tree_sha256'],
            'package_build_inputs_tree_sha256': package_inputs['tree_sha256'], 'cached_compile_arkts': True,
            'fresh_es2abc_claimed': False, 'runtime_validated': False, 'first_artifact_behavior_gate_passed': False}


def verify_production_provider(config, *, provider_name, device, signed_hap, system_image_sha256):
    """Exact schema dispatch; never relabel historical bytes as a fresh package."""
    if isinstance(config, dict) and config.get('kind') in ('completed_same_source_2in1_wallpaper_provider579/v1',
            'completed_same_source_nondefault_phone_provider579/v1'):
        from production579_completed_2in1_provider import verify_completed_provider as verify_2in1
        return verify_2in1(config, provider_name=provider_name, device=device,
            signed_hap=signed_hap, system_image_sha256=system_image_sha256)
    if isinstance(config, dict) and 'kind' in config:
        from batch_apps_completed_provider_binding import KIND, verify_completed_provider
        require(config['kind'] == KIND, 'unknown production provider lineage kind')
        return verify_completed_provider(config, provider_name=provider_name, device=device,
            signed_hap=signed_hap, system_image_sha256=system_image_sha256)
    return verify_historical_provider(config, provider_name=provider_name, device=device,
        signed_hap=signed_hap, system_image_sha256=system_image_sha256)
