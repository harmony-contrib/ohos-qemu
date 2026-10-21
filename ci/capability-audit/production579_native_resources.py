"""Pure replay of the two reviewed normal package Owners' actual raw records.

This is a source successor, never a production/runtime positive.  Historical
v17 stays in its original checker.  JSON selects only one finite data target;
this module never imports or executes a producer supplied by an evidence path.
"""
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import re
import tempfile
from batch_apps_completed_provider_binding import (
    ROOT, SOURCE, ENGINE376, NATIVE376_IMAGE, NATIVE376_SOURCE, NATIVE376_OUT,
    require, sha, checked, regular, decode, tree_digest, record, raw_ok,
    exact_absent, local_endpoint, host_mount_options, inspected, mount_table)

B = Path('/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006')
CACHE = Path('/Volumes/PSSD/qemu')
OWNER_SOURCES = {
    'F-representative-source-owner/v18': (
        'F-representative578-source-only/v1', 'run_F_representative17.py',
        '5b7200dd0ad8c1ca9f62a1ec7fe38ff8eaacc3bd1eb74f3d72ad6bd5481706cc'),
    'remaining579-one-target-source-owner/v1': (
        'remaining579-one-target-source-inputs/v1', 'run_remaining_one579.py',
        '7b8e07195feb1b857c3cd50174fb3dee45d787b0ebff4d540c96cc958320a046'),
}
ADMIT = ROOT / '.tmp/parallel-capability-20261016/root-six579-final-gate-review-candidate/admit_remaining579.py'
ADMIT_SHA = '11266e65103e8728ae1645d1b2de92de730535d5473dc426a7abcd9eb4f7dab6'
CLI_SHA = '70d5a06adf388bd09b652f47ddc9ca31663a3e5353d24188bdb0054b3014ab3e'
LAUNCHER_SHA = '106c4aadb1fa612676bd438a318539d13b06583973771a688caceae9d044790a'
CAPTION = B / 'r66-asr-product-assets579-05/product-assets.json'
CAPTION_SHA = '601c869bb39fc8cc3aff277a37a65618dd9f406074ad1530b58b8be34366bc95'
LOTTIE = B / 'r66-lottie-production-input579-06/lottie-input.json'
LOTTIE_SHA = 'a42bc70af6507e010c614799a3399a698ae42b1d8edaaf4662a87796899d91d3'
REMAINING_TEMPLATE = ROOT / '.tmp/parallel-capability-20261016/root-remaining579-single-owner-candidate/run_remaining_one579.py'
REMAINING_TEMPLATE_FREEZE_SHA = '437312312967e3518b8871fc9ea8bf8185dd862b038d9714c61e782138cc7c63'
REMAINING_BINDINGS = ('APPROVED_HEAD', 'APPROVED_FINAL_SOURCE', 'REPRESENTATIVE_ARCHIVE', 'FIRST_GATE')


def profile(product, device):
    require(product in ('arm64_virt', 'armv7a_virt', 'x86_64_virt') and
            device in ('phone', '2in1'), 'one actual finite product/device required')
    arch, dependency_arch, abi = {
        'arm64_virt': ('arm64', 'arm64', 'arm64-v8a'),
        'armv7a_virt': ('armv7a', 'arm', 'armeabi-v7a'),
        'x86_64_virt': ('x86_64', 'x86_64', 'x86_64'),
    }[product]
    return dict(product=product, device=device, arch=arch, dependency_arch=dependency_arch,
        abi=abi, container_name='ohos-qemu-' + device + '-build',
        package='openharmony-qemu-' + arch + '-' + product + '-' + device + '.tar.gz')


def remaining_projection(manifest, wrapper, expected):
    """Accept only four data literals over the entire immutable Root template."""
    template = regular(REMAINING_TEMPLATE)
    template_freeze = regular(template.parent / 'FROZEN.json')
    require(sha(template_freeze) == REMAINING_TEMPLATE_FREEZE_SHA and
            sha(template) == OWNER_SOURCES['remaining579-one-target-source-owner/v1'][2],
            'complete reviewed remaining Owner template/freeze changed')
    frozen = decode(template_freeze.read_bytes())
    template_rows = [r for r in frozen['members'] if r.get('path') == template.name]
    require(len(template_rows) == 1 and template_rows[0]['sha256'] == sha(template) and
            template_rows[0]['bytes'] == template.stat().st_size, 'actual full remaining template member differs')
    raw = wrapper.read_bytes()
    require(len(raw) <= 128 * 1024, 'bounded generated remaining Owner source required')
    text = raw.decode('utf-8')
    bindings = {}
    for name in REMAINING_BINDINGS:
        pattern = re.compile(r'^' + name + r' = ([^\r\n]+)$', re.M)
        matches = list(pattern.finditer(text))
        require(len(matches) == 1 and len(matches[0].group(1)) <= 16 * 1024,
                'one finite exact remaining data assignment required: ' + name)
        # literal_eval is deliberately not exec/eval/import: any code expression,
        # module/path selector, call, operator or unknown statement is refused.
        datum = ast.literal_eval(matches[0].group(1))
        if name == 'APPROVED_HEAD':
            require(type(datum) is str and re.fullmatch('[a-f0-9]{40}', datum) and datum == expected,
                    'actual generated remaining HEAD literal differs')
        else:
            require(type(datum) is dict and set(datum) == {'path', 'sha256', 'bytes'},
                    'actual completed remaining context requires exact Ref3')
            checked(datum)
        bindings[name] = datum
        text = pattern.sub(lambda m: name + ' = None', text, count=1)
    require(text.encode('utf-8') == template.read_bytes(),
            'remaining Owner differs beyond the four exact approved data literals')
    projection = manifest.get('remaining_source_projection')
    require(type(projection) is dict and set(projection) == {'schema', 'template', 'actual_owner', 'bindings'} and
            projection['schema'] == 'remaining579-four-data-literal-source-projection/v1' and
            projection['template'] == record(template) and projection['actual_owner'] == record(wrapper) and
            projection['bindings'] == bindings, 'generated Owner manifest must retain exact template/context/actual bytes')
    return projection


def owner_source(value, expected):
    schema = value.get('schema')
    require(schema in OWNER_SOURCES, 'unreviewed normal Owner schema')
    manifest_path = checked(value['private_manifest'])
    manifest = decode(manifest_path.read_bytes())
    expected_schema, filename, digest = OWNER_SOURCES[schema]
    require(manifest.get('schema') == expected_schema, 'reviewed normal Owner manifest schema required')
    wrapper = regular(manifest_path.parent / filename)
    require(manifest.get('files_sha256', {}).get(filename) == sha(wrapper),
            'complete generated normal Owner source bytes must be in the actual manifest')
    if schema == 'remaining579-one-target-source-owner/v1':
        projection = remaining_projection(manifest, wrapper, expected)
    else:
        require(sha(wrapper) == digest, 'exact reviewed F18 Owner source bytes required')
        projection = None
    for name, checksum in manifest['files_sha256'].items():
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts and
                sha(regular(manifest_path.parent / relative)) == checksum,
                'actual frozen normal Owner private source changed')
    for row in manifest['external_inputs'].values():
        checked(row)
    return dict(manifest=record(manifest_path), wrapper=record(wrapper), projection=projection)


def adopted_environment(value, target, out, stage):
    env = value['adopted_complete_host_environment']
    require(type(env) is dict and all(type(k) is str and type(v) is str and '\n' not in v and
            '\r' not in v for k, v in env.items()), 'complete one-line actual adopted environment required')
    # Original Owner code fixes this entire key set. HOME and Docker's local
    # context/CLI directory are observations, never compiler/source overrides.
    template = dict(ENGINE376['adopted'])
    optional = {'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG'}
    for key in optional:
        template.pop(key, None)
    require(Path(env.get('HOME', '')).is_absolute(), 'actual absolute user HOME required')
    path_parts = env.get('PATH', '').split(':')
    require(len(path_parts) == 7 and Path(path_parts[0]).is_absolute() and
            path_parts[1:] == ['/opt/homebrew/bin', '/usr/local/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin'],
            'actual original Owner sanitized PATH grammar differs')
    require(sha(regular(Path(path_parts[0]) / 'docker')) == CLI_SHA, 'actual normal Docker CLI bytes changed')
    old = str(CACHE / 'artifacts/m144-7.0-dependencies/549ee0f06b5cf4f24845e667041b47f5cfa7d21b33018dae236808888137b90d' / target['dependency_arch'])
    template.update(HOME=env['HOME'], PATH=env['PATH'], DEVICE_TYPE=target['device'], PRODUCTS=target['product'],
        PACKAGE_ROOT=str(out / ('no-packages-prepare-only' if stage == 'prepare' else 'packages')),
        LOG_DIR=str(out / 'logs'), BUILD_JOBS='2' if stage == 'prepare' else '4',
        DOCKER_BUILD_CPUS='2' if stage == 'prepare' else '4',
        DOCKER_BUILD_MEMORY='5g' if stage == 'prepare' else '14g', PREPARE_ONLY='1' if stage == 'prepare' else '0',
        JSVM_ENGINE_ARTIFACTS=old + '/jsvm', QEMU_VULKAN_ARTIFACTS=old + '/swiftshader', QEMU_AVC_ARTIFACTS=old + '/avc')
    if stage == 'build':
        template['DOCKER_BUILD_MEMORY_SWAP'] = '38g'
    if value['schema'] == 'F-representative-source-owner/v18':
        caption = dict(path=str(CAPTION), sha256=CAPTION_SHA)
    else:
        caption = value['prerequisite_descriptors']['caption_inputs']
    checked(caption)
    require(sha(regular(LOTTIE)) == LOTTIE_SHA, 'actual fixed normal Lottie input changed')
    template.update(QEMU_LIVE_CAPTIONS_INPUTS=caption['path'], QEMU_LIVE_CAPTIONS_INPUTS_SHA256=caption['sha256'],
        QEMU_LIVE_CAPTIONS_ABI=target['abi'], QEMU_LOTTIE_INPUT=str(LOTTIE))
    require({k: v for k, v in env.items() if k not in optional} == template,
            'complete adopted normal source Owner environment differs')
    if 'DOCKER_CONFIG' in env:
        require(Path(env['DOCKER_CONFIG']).is_absolute(), 'actual local Docker config path required')
    return env


def engine_contract(value, target, frozen, env):
    cid = value['container_id']
    cfg = dict(ENGINE376['config'], Hostname=cid[:12], WorkingDir='/work',
        Labels=ENGINE376['native_config_labels'],
        Cmd=['bash', '-lc', 'ulimit -n 1048576 2>/dev/null || true; ulimit -n; exec bash /work/scripts/build_standard_qemu_in_docker.sh ' + target['product'] + ' '])
    native = dict(token.split('=', 1) for token in ENGINE376['native_env'])
    native.update({k: env[k] for k in native if k in env and k not in ('PATH', 'LANG', 'LC_ALL', 'QEMU_KNOWLEDGE_ICS')})
    native.update(DEVICE_TYPE_BUILD_PROFILE='qemu_' + target['device'] + '_full_source',
        QEMU_2IN1_PROFILE_COMPONENT='1' if target['device'] == '2in1' else '0',
        QEMU_PHONE_PROFILE_COMPONENT='1' if target['device'] == 'phone' else '0')
    for key in ('QEMU_LIVE_CAPTIONS_INPUTS', 'QEMU_LIVE_CAPTIONS_INPUTS_SHA256', 'QEMU_LIVE_CAPTIONS_ABI', 'QEMU_LOTTIE_INPUT'):
        native[key] = env[key]
    cfg['Env'] = sorted(k + '=' + v for k, v in native.items())
    artifact_keys = ('JSVM_ENGINE_ARTIFACTS', 'QEMU_VULKAN_ARTIFACTS', 'QEMU_AVC_ARTIFACTS',
                     'QEMU_ARKWEB_CORE_ARTIFACTS', 'QEMU_MESA_LLVM_ARTIFACTS')
    artifacts = [native[k] for k in artifact_keys]
    mounts = {dest: dict(Type='bind', Source=dest, RW=False) for dest in artifacts}
    mounts['/qemu-inputs/knowledge/holidays.ics'] = dict(Type='bind', Source=env['QEMU_KNOWLEDGE_ICS'], RW=False)
    mounts[str(CACHE)] = dict(Type='bind', Source=str(CACHE), RW=True)
    if target['device'] == '2in1':
        serial = native['QEMU_SERIAL_SOURCE_REPO']
        mounts[serial] = dict(Type='bind', Source=serial, RW=False)
    mounts['/work'] = dict(Type='bind', Source=str(frozen), RW=False)
    for dest, name in ((SOURCE, NATIVE376_SOURCE), (SOURCE + '/out', NATIVE376_OUT)):
        mounts[dest] = dict(Type='volume', Name=name, Source='/var/lib/docker/volumes/' + name + '/_data', Driver='local', RW=True)
    ordered = ([native['QEMU_SERIAL_SOURCE_REPO']] if target['device'] == '2in1' else [])
    ordered += artifacts + ['/qemu-inputs/knowledge/holidays.ics', SOURCE, SOURCE + '/out']
    host = dict(ENGINE376['host'], AutoRemove=True, ContainerIDFile='', ReadonlyRootfs=False, NetworkMode='bridge',
        CapDrop=None, SecurityOpt=None, PidsLimit=None,
        Memory=(5 if env['PREPARE_ONLY'] == '1' else 14) * 1024**3,
        MemorySwap=(10 if env['PREPARE_ONLY'] == '1' else 38) * 1024**3,
        NanoCpus=(2 if env['PREPARE_ONLY'] == '1' else 4) * 10**9,
        Tmpfs={'/tmp': 'exec,mode=1777,size=32g'},
        Binds=[str(CACHE) + ':' + str(CACHE), str(frozen) + ':/work:ro'])
    host['Mounts'] = host_mount_options({dest: mounts[dest] for dest in ordered})
    return cfg, host, mounts


def inspect_native(row, cid, target, cfg, host, mounts, *, running=None):
    values = decode(raw_ok(row, row['argv'], native=True))
    require(type(values) is list and len(values) == 1 and type(values[0].get('Config', {}).get('Env')) is list,
            'one complete actual normal Docker Config/Env required')
    original = values[0]['Config']['Env']
    require(all(type(v) is str and '=' in v for v in original) and
            len({v.split('=', 1)[0] for v in original}) == len(original) and sorted(original) == cfg['Env'],
            'complete actual normal Docker environment differs')
    obs = inspected(row, cid, target['container_name'], NATIVE376_IMAGE, dict(cfg, Env=original), host,
                    mounts, native=True, running=running)
    return dict(obs, MountsByDestination=mount_table(obs))


def remaining_admission(value, target, expected):
    ref = value['representative_scheduling_admission']
    original = decode(checked(ref).read_bytes())
    require(original.get('schema') == 'actual-final579-next-product-scheduling-admission/v1' and
            original.get('source_commit') == expected and
            original.get('next_target') == dict(product=target['product'], device_type=target['device']),
            'actual same-source first-gate scheduling receipt required')
    require(sha(regular(ADMIT)) == ADMIT_SHA, 'fixed complete scheduling replayer changed')
    spec = importlib.util.spec_from_file_location('production579_fixed_remaining_admission', ADMIT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='provider579-scheduling-', dir=B) as scratch:
        result = module.admit_next(gate=original['final_gate'], archive=original['representative_archive'],
            approved_final_sources=original['approved_final_sources'], source_commit=expected,
            next_product=target['product'], next_device_type=target['device'], output=Path(scratch) / 'receipt.json')
        require(decode(checked(result).read_bytes()) == original, 'full actual scheduling proof replay differs')
    return ref


def native_resources(value, launcher, expected, tree, *, stage='build'):
    """Finite raw lifecycle, complete engine config, original handle and source join."""
    require(stage in ('prepare', 'build') and value.get('schema') in OWNER_SOURCES and
        value.get('source_commit') == expected and type(value.get('exit_code')) is int and value['exit_code'] == 0 and
        value.get('tree_sha256') == tree and checked(value['launcher_log']) == launcher and
        all(value.get(k) is True for k in ('owned_resources_closed_while_lease_held',
            'resource_lease_release_authorized', 'resource_lease_released_after_verified_closure',
            'cleanup_verified', 'owned_container_absent', 'owned_launcher_group_closed')) and
        value.get('resource_lease_held') is False and value.get('host_tests_executed') is False and
        value.get('capability_acceptance') == 'newly_packaged_QEMU_runtime_only' and
        value.get('first_artifact_behavior_gate_passed') is False and
        not any(value.get(k) for k in ('timed_out', 'error', 'cleanup_error', 'postcondition_error',
            'root_settlements', 'unexpected_leader_reap', 'foreground_creator_forcibly_stopped_while_still_running',
            'group_signals', 'signals', 'evidence_write_errors', 'cleanup_attempt_errors',
            'must_resolve_owned_resources_before_next_stage')),
        'completed actual normal source Owner and full original closure required')
    require(launcher.parent.parent == B and launcher.name == 'launcher.log' and
        value.get('resource_lock') == str(B / '.representative10-resource.lock') and
        re.fullmatch('[a-f0-9]{32}', value.get('root_run_id', '')) and
        type(value.get('wrapper_pid')) is int and value['wrapper_pid'] > 1,
        'actual canonical normal Owner/lease/output identity required')
    owner = owner_source(value, expected)
    env = value['adopted_complete_host_environment']
    target = profile(env.get('PRODUCTS'), env.get('DEVICE_TYPE'))
    if value['schema'] == 'F-representative-source-owner/v18':
        require((target['product'], target['device']) == ('arm64_virt', 'phone') and
                value.get('remaining_five_started') is False, 'F18 stays exactly first ARM64 phone')
        admission = None
    else:
        require((target['product'], target['device']) != ('arm64_virt', 'phone') and value.get('target') == target and
                value.get('selected_target_started') is True and value.get('remaining_five_started') is (stage == 'build'),
                'actual one later target contract differs')
        admission = remaining_admission(value, target, expected)
        scheduled = decode(checked(admission).read_bytes())
        bindings = owner['projection']['bindings']
        require(bindings['APPROVED_HEAD'] == scheduled['source_commit'] and
            checked(bindings['APPROVED_FINAL_SOURCE']) == checked(scheduled['approved_final_sources']) and
            checked(bindings['REPRESENTATIVE_ARCHIVE']) == checked(scheduled['representative_archive']) and
            checked(bindings['FIRST_GATE']) == checked(scheduled['final_gate']) and
            all(bindings[k]['sha256'] == scheduled[v]['sha256'] for k, v in (
                ('APPROVED_FINAL_SOURCE', 'approved_final_sources'),
                ('REPRESENTATIVE_ARCHIVE', 'representative_archive'), ('FIRST_GATE', 'final_gate'))),
            'four actual generated Owner context literals must equal the full scheduling proof')
    if stage == 'build':
        archive = checked(value['package'])
        require(archive == launcher.parent / 'packages' / target['package'], 'unique actual normal target package path differs')
        from production579_target import archive_manifest
        context = archive_manifest(archive)['context']
        require((context['product'], context['device'], context['arch'], context['abi']) ==
                (target['product'], target['device'], target['arch'], target['abi']), 'actual archive target differs')
    inputs_file = checked(value['build_inputs'])
    frozen = Path(value['actual_frozen_inputs'])
    inputs = decode(inputs_file.read_bytes())
    require(inputs_file == frozen / 'build-inputs.json' and frozen.parent == CACHE / 'build-inputs' and
        inputs.get('source_git_revision') == expected and inputs.get('tree_sha256') == tree and
        tree_digest(inputs['files_sha256']) == tree, 'actual retained normal launcher snapshot differs')
    declarations = re.findall(r'^frozen build inputs: (\S+) sha256=([a-f0-9]{64})$', launcher.read_text(), re.M)
    require(declarations == [(str(frozen), tree)] and value.get('declared_launcher_tree_sha256') == tree and
        checked(value['launcher_snapshot_manifest']) == inputs_file, 'raw launcher snapshot declaration differs')
    from snapshot_build_inputs import digest_files
    require(digest_files(frozen) == inputs['files_sha256'], 'actual complete frozen normal source bytes changed')
    source_ref = value['prerequisite_descriptors']['source_inputs']
    source_identity = decode(checked(source_ref).read_bytes())
    require(source_identity == dict(schema='representative-source-identity578/v1', source_commit=expected,
        build_input_files_sha256=inputs['files_sha256'], tree_sha256=tree, host_tests_executed=False,
        capability_acceptance='newly_packaged_QEMU_runtime_only'), 'actual complete native source identity differs')
    require(value.get('argv') == ['bash', str(ROOT / 'scripts/run_2in1_full_build_docker.sh')] and
        inputs['files_sha256'].get('scripts/run_2in1_full_build_docker.sh') == LAUNCHER_SHA == sha(regular(frozen / 'scripts/run_2in1_full_build_docker.sh')),
        'actual original normal launcher argv/source differs')
    env = adopted_environment(value, target, launcher.parent, stage)
    if stage == 'build':
        prep_ref = value['prerequisite_descriptors']['prepare_receipt']
        prepare = decode(checked(prep_ref).read_bytes())
        require(prepare.get('schema') == value['schema'] and
                prepare['prerequisite_descriptors']['source_inputs'] == source_ref, 'actual same-source normal prepare receipt differs')
        prepare_resources = native_resources(prepare, checked(prepare['launcher_log']), expected, tree, stage='prepare')
        require(prepare_resources['target'] == target, 'prepare belongs to another actual target')
        if value['schema'] == 'remaining579-one-target-source-owner/v1':
            require(prepare['prerequisite_descriptors']['caption_inputs'] ==
                    value['prerequisite_descriptors']['caption_inputs'], 'normal prepare/build caption source differs')
    cid = value.get('container_id')
    require(re.fullmatch('[a-f0-9]{64}', cid or ''), 'actual full normal CID missing')
    cfg, host, mounts = engine_contract(value, target, frozen, env)
    rows = value.get('commands')
    require(type(rows) is list and rows, 'actual finite normal command journal missing')
    endpoint_env = {k: env[k] for k in ('DOCKER_HOST', 'DOCKER_CONTEXT') if k in env}
    endpoint, cursor = local_endpoint(rows, 0, endpoint_env, native=True)
    require(endpoint == value.get('actual_local_docker_endpoint'), 'raw normal local endpoint differs')
    exact_absent(rows[cursor], target['container_name'], native=True)
    require(rows[cursor].get('label') == 'before-build-name', 'initial exact normal name cut missing')
    cursor += 1
    observed = []
    while cursor < len(rows) and re.fullmatch('discover-build-[0-9]+', rows[cursor].get('label', '')):
        row = rows[cursor]
        require(row['argv'] == ['docker', 'inspect', target['container_name']], 'foreign normal discovery command')
        if row['exit_code'] == 1:
            require(not observed, 'actual normal CID must remain held after discovery')
            exact_absent(row, target['container_name'], native=True)
        else:
            require(not observed, 'duplicate normal CID adoption')
            observed.append(inspect_native(row, cid, target, cfg, host, mounts))
        cursor += 1
    require(len(observed) == 1, 'actual complete normal Config/HostConfig/Mounts observation missing')
    pid=value.get('launcher_pid');pgid=value.get('owned_launcher_pgid');wn=value.get('launcher_wnowait_exit',{})
    require(type(pid)is int and pid>1 and pgid==pid and value.get('launcher_start_new_session')is True and
            value.get('spawn_mask_restored_in_child')is True and value.get('foreground_creator_completed_normally_before_forced_stop')is True and
            wn.get('pid')==pid and type(wn.get('si_code'))is int and wn['si_code']==1 and
            type(wn.get('si_status'))is int and wn['si_status']==0 and type(wn.get('exit_code'))is int and wn['exit_code']==0 and wn.get('reaped')is False and
            value.get('leader_final_wait_completed')is True and value.get('owned_launcher_leader_reaped')is True and
            type(value.get('actual_launcher_exit_code_after_cleanup'))is int and value['actual_launcher_exit_code_after_cleanup']==0,
            'actual held-Popen WNOWAIT/final wait chain missing')
    cuts=value.get('registered_group_cuts');require(type(cuts)is list and cuts,'native raw PS/group cuts missing')
    replayed=[]
    while cursor<len(rows) and rows[cursor].get('label')=='owned-group-members':
        raw=raw_ok(rows[cursor],['ps','-axo','pid=,pgid=,stat='],native=True);members=[];seen=set()
        for line in raw.decode().splitlines():
            fields=line.split();require(len(fields)==3 and fields[0].isdigit() and fields[1].isdigit() and
                re.fullmatch('[A-Za-z][A-Za-z0-9+<>=?-]{0,15}',fields[2]),'invalid actual PS row')
            p,g=int(fields[0]),int(fields[1]);require(p not in seen,'duplicate actual PS PID');seen.add(p)
            if g==pgid:members.append(dict(pid=p,pgid=g,state=fields[2]))
        replayed.append(members);cursor+=1
    require(replayed and len(replayed)==len(cuts) and all(a==b.get('members') for a,b in zip(replayed,cuts)) and
            all(m['pid']==pid or m['state'].startswith('Z') for m in replayed[-1]) and
            type(wn.get('observed_monotonic_ns'))is int and type(value.get('cleanup_started_monotonic_ns'))is int and
            type(value.get('last_group_signal_boundary_monotonic_ns'))is int and
            all(type(cut.get('monotonic_ns'))is int for cut in cuts) and
            0<value['cleanup_started_monotonic_ns']<=wn['observed_monotonic_ns']<=cuts[0]['monotonic_ns'] and
            all(a['monotonic_ns']<=b['monotonic_ns'] for a,b in zip(cuts,cuts[1:])) and
            cuts[-1]['monotonic_ns']<=value['last_group_signal_boundary_monotonic_ns'],
            'raw final original group membership/WNOWAIT order differs')
    require(rows[cursor].get('label')=='cleanup-discover' and rows[cursor]['argv']==['docker','inspect',cid],
            'native cleanup must re-observe original CID after group completion')
    if rows[cursor]['exit_code']==0:
        inspect_native(rows[cursor],cid,target,cfg,host,mounts,running=False);cursor+=1
        raw_ok(rows[cursor],['docker','rm','--force',cid],native=True);cursor+=1
        exact_absent(rows[cursor],cid,native=True);cursor+=1
    else:exact_absent(rows[cursor],cid,native=True);cursor+=1
    for label in ('cleanup-name-absence-1','cleanup-name-absence-2'):
        require(rows[cursor].get('label')==label,'native separate post-group name cuts required')
        exact_absent(rows[cursor],target['container_name'],native=True);cursor+=1
    require(cursor==len(rows),'unknown/foreign native command outside reviewed finite success protocol')
    return dict(endpoint=endpoint,container_id=cid,target=target,owner_sources=owner,representative_scheduling_admission=admission,volumes={dest:observed[0]['MountsByDestination'][dest] for dest in (SOURCE,SOURCE+'/out')})

