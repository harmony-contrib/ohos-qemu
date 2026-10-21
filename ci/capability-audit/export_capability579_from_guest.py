"""Read real selected package inputs through the original held-guest OwnedIO.

No Owner/VM/lease/Popen/Docker/SDK/compiler/signing/image parser or new launcher.
Only the existing Owner's shell/receive commands run when root calls produce.
The module is an unexecuted source candidate; exported facts never mean pass.
"""
from pathlib import Path, PurePosixPath
import json
import re
import secrets
import shlex

from assemble_capability579_inputs import (PROVIDERS, checked_ref,
    document, hap_metadata, json_ref, raw, ref, require)
from hdc_transport import failed as hdc_failed
from production579_target import context as package_context

COMMON = {'archive', 'source_commit', 'package_receipt', 'build_inputs', 'package_manifest'}
SYSTEM_HAP_PREFIXES = ('/system/app/', '/system_ext/app/', '/sys_prod/app/')


def write(path, value):
    require(not path.exists(), 'fresh original-owner export file required')
    with path.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return ref(path)


def data_common(inputs):
    require(type(inputs) is dict and set(inputs) == COMMON and
        re.fullmatch('[a-f0-9]{40}', inputs['source_commit'] or ''), 'explicit actual completed package inputs required')
    result = {key: checked_ref(inputs[key]) for key in COMMON - {'source_commit'}}
    result['source_commit'] = inputs['source_commit']
    receipt = json_ref(result['package_receipt'])
    require(type(receipt.get('exit_code')) is int and receipt['exit_code'] == 0 and
        receipt.get('source_commit') == result['source_commit'] and
        receipt.get('owned_container_absent') is True and receipt.get('owned_launcher_group_closed') is True and
        checked_ref({key: receipt['package'][key] for key in ('path', 'sha256')}) == result['archive'],
        'original completed package receipt and its actual archive required')
    build = json_ref(result['build_inputs'])
    require(build['source_git_revision'] == result['source_commit'], 'actual package source/build inputs differ')
    return result


def bms_body(text, bundle):
    begin = text.find('{')
    require(begin >= 0 and text[:begin].strip() == bundle + ':', 'original single provider BMS header required')
    value = document(text[begin:])
    app = value['applicationInfo']
    require(value['name'] == app['name'] == app['bundleName'] == bundle and
        type(value.get('appIndex')) is int and value['appIndex'] == 0 and
        type(app.get('appIndex')) is int and app['appIndex'] == 0 and
        type(app.get('uid')) is int and 0 < app['uid'] < 2**31 and
        type(app.get('accessTokenId')) is int and 0 < app['accessTokenId'] < 2**32 and
        type(value.get('userInfo')) is list and value['userInfo'] and
        all(type(row) is dict for row in value['userInfo']), 'actual provider bundle/instance/identity required')
    # The original token reader's account-100 requirement belongs to test
    # callers. A singleton system provider may have a real system UID; do not
    # relabel it as a caller UID or guess an account from integer division.
    matches = [row for row in value['userInfo'] if row.get('bundleName') == bundle and
        row.get('uid') == app['uid'] and row.get('accessTokenId') == app['accessTokenId']]
    require(matches and all(type(row.get('bundleUserInfo')) is dict and
        type(row['bundleUserInfo'].get('userId')) is int and 0 <= row['bundleUserInfo']['userId'] < 2**31
        for row in matches), 'actual provider BMS application/per-user identity does not agree')
    users = [row['bundleUserInfo']['userId'] for row in matches]
    require(len(users) == len(set(users)), 'ambiguous actual provider per-user identity')
    identity = {'schema': 'actual-system-bms-provider-identity/v1', 'bundle': bundle, 'uid': app['uid'],
        'token_id': app['accessTokenId'], 'inst_index': 0, 'actual_matching_user_ids': users}
    require(value['applicationInfo'].get('isSystemApp') is True and type(value.get('hapModuleInfos')) is list and
        type(value.get('reqPermissions')) is list, 'real preinstalled system bundle/profile required')
    modules = {}
    for row in value['hapModuleInfos']:
        name, path = row.get('moduleName'), row.get('hapPath')
        require(type(name) is str and re.fullmatch('[A-Za-z0-9_]{1,80}', name) and name not in modules and
            type(path) is str, 'actual unique BMS module/HAP path required')
        modules[name] = path
    require(modules, 'actual BMS module inventory is empty')
    return value, identity, modules


def mount_fields(text):
    def unescape(value):
        return re.sub(r'\\(040|011|012|134)', lambda match: chr(int(match[1], 8)), value)
    rows = []
    require(text and len(text.encode()) < 4 * 1024 * 1024, 'actual bounded complete mountinfo required')
    for line in text.splitlines():
        left, right = line.split(' - ', 1); a, b = left.split(), right.split()
        require(len(a) >= 6 and len(b) >= 3, 'actual mountinfo row is malformed')
        rows.append({'mount_id': a[0], 'parent_id': a[1], 'device': a[2],
            'root': unescape(a[3]), 'target': unescape(a[4]), 'options': a[5],
            'filesystem': b[0], 'source': unescape(b[1]), 'super_options': b[2], 'raw': line})
    return rows


def package_mount(path, mounts):
    candidates = [row for row in mounts if path == row['target'] or
        path.startswith(row['target'].rstrip('/') + '/')]
    require(candidates, 'no actual mount covers the exported file')
    longest = max(len(row['target']) for row in candidates)
    candidates = [row for row in candidates if len(row['target']) == longest]
    require(len(candidates) == 1, 'ambiguous covering mount; no guessed image origin')
    actual = candidates[0]
    require(actual['filesystem'] in ('ext4', 'erofs') and actual['source'].startswith('/dev/') and
        not actual['target'].startswith(('/data', '/mnt', '/storage')),
        'export must be on an actual package block filesystem; data/overlay/tmpfs fallback refused')
    return dict(actual, read_only_mount='ro' in actual['options'].split(','))


class Export:
    def __init__(self, io, inputs, services):
        self.io, self.common = io, data_common(inputs)
        io.owner.held_binding(io.guest)
        require(io.owner.vm is io.guest and io.guest.report['archive_sha256'] == self.common['archive']['sha256'] ==
            io.archive_sha256 and io.owner.archive == Path(self.common['archive']['path']) and
            io.guest.report['test_environment']['boot_id'] == io.boot_id and
            io.guest.args.purpose == 'acceptance' and not io.guest.report.get('candidate_kernel') and
            io.guest.report['test_environment'].get('external_keepalive') is False,
            'one original unassisted newly packaged acceptance guest required')
        require(type(services) is dict and set(services) == {'services', 'library_paths'} and
            set(services['services']) == {'ril', 'bluetooth'} and type(services['library_paths']) is dict,
            'root actual fixed service/init/library path DATA required; no defaults')
        self.services_spec = services
        self.output = io.output / 'selected-package-export579'
        self.output.mkdir(mode=0o700, exist_ok=False)
        self.value = {'schema': 'actual-owned-capability579-guest-export/v1',
            'boot_id': io.boot_id, 'udid': io.udid, 'target': io.target, 'package': self.common,
            'scope': 'read-only guest export facts; no capability or first-artifact verdict',
            'commands': [], 'files': [], 'bundles': {}, 'complete': False,
            'runtime_pass': False, 'formally_closed': [], 'first_artifact_behavior_gate_passed': False}
        self.bundles, self.haps = {}, {}
        self.save()

    def save(self):
        (self.output / 'raw-export.json').write_text(json.dumps(self.value, ensure_ascii=False, indent=2) + '\n')

    def observe(self, row, operation):
        require(type(row) is dict and row['boot_id'] == self.io.boot_id and row['timed_out'] is False and
            raw(row['stdout_ref']) == row['stdout'].encode() and raw(row['stderr_ref']) == row['stderr'].encode(),
            'actual original stdout/stderr/boot/timeout records required')
        transport = row.get('transport_stdout', row['stdout'])
        require(row.get('transport_exit_code', row['exit_code']) == 0 and
            not hdc_failed(transport, row['stderr']), 'actual HDC transport failed')
        if 'transport_exit_code' in row:
            require(raw(row['transport_stdout_ref']) == transport.encode() and
                row['shell_exit_code'] == row['exit_code'], 'original guest footer/transport receipt differs')
        checked_ref(row['log'])
        require(raw(row['log']) == (transport + row['stderr']).encode(), 'original actual IO log differs')
        saved = {'operation': operation, 'original_receipt': self.io.ref_receipt(row),
            'body': checked_ref(row['stdout_ref']), 'stderr': checked_ref(row['stderr_ref']),
            'log': checked_ref(row['log'])}
        self.value['commands'].append(saved); self.save()
        return row

    def shell(self, script, operation, allow_failure=False):
        name = 'export579_' + str(len(self.value['commands'])).zfill(5)
        row = self.observe(self.io.shell(script, name, timeout=90, allow_failure=True), operation)
        require(allow_failure or row['exit_code'] == 0, 'actual guest read failed: ' + operation)
        return row

    def boot(self):
        self.io.owner.held_binding(self.io.guest)
        require(self.shell('cat /proc/sys/kernel/random/boot_id', 'same_boot')['stdout'].strip() == self.io.boot_id,
            'selected input export escaped the original held boot')

    def origins(self):
        self.boot()
        guest = self.io.guest
        for key, filename in (('build_inputs', 'build-inputs.json'), ('package_manifest', 'manifest.json')):
            require((guest.directory / filename).read_bytes() == raw(self.common[key]),
                'supplied metadata does not equal the actual archive-extracted guest file')
        manifest = json_ref(self.common['package_manifest'])
        actual = package_context(manifest); environment = guest.report['test_environment']
        require(actual['product'] == environment['product'] and actual['arch'] == environment['guest_arch'] and
            actual['device'] == environment['device_type'] == guest.device and actual['arch'] == guest.arch,
            'actual package/held guest product, architecture and profile differ')
        self.library_directory = 'lib' if actual['arch'] == 'armv7a' else 'lib64'
        initial = guest.report['initial_package_file_sha256']
        require(initial['build-inputs.json'] == self.common['build_inputs']['sha256'] and
            initial['manifest.json'] == self.common['package_manifest']['sha256'] and
            re.fullmatch('[a-f0-9]{64}', initial['images/system.img']),
            'original archive checksum verification did not bind this guest metadata/system image')
        # Snapshot actual mutable boot report, not a Ref to a file that later
        # original operations will rewrite. Its existing raw log paths remain.
        boot = write(self.output / 'original-boot-snapshot.json', guest.report)
        self.value['origin'] = {'original_boot_snapshot': boot,
            'archive_extracted_system_image': {'path': str(guest.directory / 'images/system.img'),
                'initial_archive_sha256': initial['images/system.img']},
            'note': 'Initial image checksum is the original QemuGuest archive proof; live image bytes are not relabeled as immutable archive bytes.'}
        mount = self.shell('cat /proc/self/mountinfo', 'actual_mounts_before')
        self.mounts = mount_fields(mount['stdout'])
        self.value['mountinfo_before'] = checked_ref(mount['stdout_ref']); self.save()

    def path(self, value, prefixes):
        require(type(value) is str and 1 < len(value) <= 768 and value.startswith(prefixes) and
            str(PurePosixPath(value)) == value and '..' not in PurePosixPath(value).parts and
            not any(char in value for char in ('\n', '\r', '\x00', '\\')),
            'literal actual selected system/vendor path required')
        return value

    def file(self, remote, kind, limit):
        prefixes = SYSTEM_HAP_PREFIXES if kind == 'hap' else ('/system/', '/vendor/', '/system_ext/', '/sys_prod/')
        remote = self.path(remote, prefixes)
        if kind == 'hap' and remote in self.haps:
            return self.haps[remote]['hap']
        self.boot(); quoted = shlex.quote(remote)
        resolved = self.shell('readlink -f ' + quoted, kind + '_resolved')['stdout'].strip()
        self.path(resolved, ('/system/', '/vendor/', '/system_ext/', '/sys_prod/', '/app/', '/' + self.library_directory + '/', '/etc/'))
        mount = package_mount(resolved, self.mounts)
        stat_script = 'test -f ' + quoted + ' && stat -Lc ' + shlex.quote('%d:%i:%s:%u:%g:%a:%F') + ' ' + quoted
        first = self.shell(stat_script, kind + '_stat_before')['stdout'].strip()
        fields = first.split(':')
        require(len(fields) == 7 and all(re.fullmatch('[0-9]+', value) for value in fields[:6]) and
            fields[-1] == 'regular file' and 0 < int(fields[2]) <= limit, 'actual regular bounded selected file required')
        before = self.shell('sha256sum ' + quoted, kind + '_sha_before')['stdout'].strip()
        match = re.fullmatch('([a-f0-9]{64})  ' + re.escape(remote), before)
        require(match, 'actual selected-file SHA256 reply is malformed')
        sequence = len(self.value['files'])
        destination = self.output / ('file_%03d' % sequence) / PurePosixPath(remote).name
        row = self.observe(self.io.receive(remote, destination, 'export579_recv_' + str(sequence).zfill(3)), kind + '_receive')
        require(row['exit_code'] == 0 and row['argv'] == [str(self.io.hdc), '-t', self.io.target,
            'file', 'recv', remote, str(destination)], 'original held guest receive failed or changed target')
        result = ref(destination)
        require(result['sha256'] == match[1] and destination.stat().st_size == int(fields[2]),
            'received bytes differ from actual source file SHA/size')
        after = self.shell('sha256sum ' + quoted, kind + '_sha_after')['stdout'].strip()
        final = self.shell(stat_script, kind + '_stat_after')['stdout'].strip()
        resolved_after = self.shell('readlink -f ' + quoted, kind + '_resolved_after')['stdout'].strip()
        require(before == after and first == final and resolved_after == resolved,
            'actual selected source file changed during export')
        item = {'kind': kind, 'guest_path': remote, 'resolved': resolved, 'covering_mount': mount,
            'stat_before': first, 'stat_after': final, 'sha256_before': match[1], 'sha256_after': match[1],
            'received': result, 'bytes': destination.stat().st_size}
        self.value['files'].append(item); self.save()
        if kind == 'hap':
            self.haps[remote] = {'package_path': remote, 'hap': result}
        self.boot()
        return result

    def bundle(self, name):
        if name in self.bundles:
            return self.bundles[name]
        row = self.shell('bm dump -n ' + name, 'bms_before_' + name)
        doc, identity, modules = bms_body(row['stdout'], name)
        self.bundles[name] = (doc, identity, modules)
        self.value['bundles'][name] = {'identity': identity, 'bms_before': checked_ref(row['stdout_ref']),
            'actual_module_paths': modules, 'actual_applicationInfo': doc['applicationInfo'],
            'actual_signatureInfo': doc.get('signatureInfo'),
            'actual_reqPermissions': doc['reqPermissions'], 'selected_modules': {}}
        self.save()
        return self.bundles[name]

    def module(self, name, module):
        doc, identity, modules = self.bundle(name)
        require(module in modules, 'target names a module absent from real BMS')
        path = modules[module]
        # A data-updated HAP is not proof of this new image's selected file.
        # There is no guessed preinstall directory or source/out fallback.
        self.path(path, SYSTEM_HAP_PREFIXES)
        require(path.endswith('.hap'), 'real selected BMS HAP path required')
        hap = self.file(path, 'hap', 1024 * 1024 * 1024)
        metadata = hap_metadata(hap)
        require(metadata['app'].get('bundleName') == name and metadata['module'].get('name') == module,
            'actual received HAP metadata does not match BMS bundle/module')
        self.value['bundles'][name]['selected_modules'][module] = {'hap': hap, 'actual_compiled_metadata': metadata}
        self.save()
        return {'hap': hap}

    def provider(self, case, bundle, target):
        doc, identity, modules = self.bundle(bundle)
        targets = [row for row in doc.get('abilityInfos', []) + doc.get('extensionAbilityInfo', []) if row.get('name') == target]
        require(len(targets) <= 1, 'ambiguous actual BMS target declaration')
        if not targets:
            require(case == 'notification-subscription', 'actual selected provider entry missing: ' + case)
            # The existing bounded-absence case uses the actual management
            # module selected by the real notification-settings declaration.
            target = PROVIDERS['notification-settings'][1]
            targets = [row for row in doc.get('extensionAbilityInfo', []) if row.get('name') == target]
            require(len(targets) == 1, 'actual notification-management source module is missing')
        module = targets[0].get('moduleName')
        require(type(module) is str and module in modules, 'actual BMS target/module relationship missing')
        return {'bundle': bundle, 'modules': {module: self.module(bundle, module)}}

    def services(self):
        result, configs, libraries = {}, {}, {}
        spec = self.services_spec; required = set()
        for kind in ('ril', 'bluetooth'):
            value = spec['services'][kind]
            require(type(value) is dict and set(value) == {'name', 'init_path', 'process_name', 'libraries'} and
                all(re.fullmatch('[A-Za-z0-9_-]{1,64}', value[key] or '') for key in ('name', 'process_name')) and
                re.fullmatch(r'/(?:system|vendor)/etc/init/[A-Za-z0-9_.-]+\.cfg', value['init_path'] or '') and
                type(value['libraries']) is list and value['libraries'] and
                len(value['libraries']) == len(set(value['libraries'])) and
                all(re.fullmatch(r'lib[A-Za-z0-9_.-]+\.so', item) for item in value['libraries']),
                'root actual finite service specification required')
            actual = self.file(value['init_path'], 'init', 4 * 1024 * 1024)
            config = json_ref(actual)
            require(len([row for row in config['services'] if row.get('name') == value['name']]) == 1,
                'actual exported init does not declare this service')
            configs[kind] = {'guest_path': value['init_path'], 'file': actual}; result[kind] = value
            required.update(value['libraries'])
            # Actual process observation is retained as a fact. Absence is not
            # filled with a made-up PID and does not stand in for service tests.
            row = self.shell('pidof ' + value['process_name'], 'service_process_' + kind, allow_failure=True)
            self.value.setdefault('initial_process_observations', {})[kind] = {
                'exit_code': row['exit_code'], 'stdout': checked_ref(row['stdout_ref']),
                'stderr': checked_ref(row['stderr_ref'])}
        require(set(spec['library_paths']) == required, 'actual complete finite service DSO path map required')
        for name in sorted(required):
            path = spec['library_paths'][name]
            require(type(path) is str and PurePosixPath(path).name == name and
                re.fullmatch(r'/(?:system|vendor)/' + self.library_directory + r'/(?:[A-Za-z0-9_.-]+/)*' + re.escape(name), path),
                'root actual selected DSO path required; no basename search/default')
            actual = self.file(path, 'dso', 256 * 1024 * 1024)
            libraries[name] = {'guest_path': path, 'file': actual}
        self.save()
        return result, configs, libraries

    def recheck_bundles(self):
        for name, (before, identity, modules) in self.bundles.items():
            row = self.shell('bm dump -n ' + name, 'bms_after_' + name)
            after, current, paths = bms_body(row['stdout'], name)
            require(current == identity and paths == modules and after['applicationInfo'] == before['applicationInfo'] and
                after.get('signatureInfo') == before.get('signatureInfo') and
                after['reqPermissions'] == before['reqPermissions'],
                'actual BMS identity/module/permission inventory changed during read-only export')
            self.value['bundles'][name]['bms_after'] = checked_ref(row['stdout_ref'])
        current = self.shell('cat /proc/self/mountinfo', 'actual_mounts_after')
        mounts = mount_fields(current['stdout'])
        for item in self.value['files']:
            require(package_mount(item['resolved'], mounts) == item['covering_mount'],
                'actual package mount origin changed during export')
        self.value['mountinfo_after'] = checked_ref(current['stdout_ref']); self.boot(); self.save()

    def mms(self):
        name = 'com.ohos.mms'
        row = self.shell('bm dump -n ' + name, 'mms_bms_query')
        fact = {'schema': 'actual-owned-capability579-mms-facts/v1', 'package': self.common,
            'boot_id': self.io.boot_id, 'bms_query': checked_ref(row['stdout_ref']),
            'bms_stderr': checked_ref(row['stderr_ref']), 'bms_exit_code': row['exit_code'],
            'runtime_pass': False, 'first_artifact_behavior_gate_passed': False}
        doc, identity, modules = bms_body(row['stdout'], name)
        self.bundles[name] = (doc, identity, modules)
        self.value['bundles'][name] = {'identity': identity, 'bms_before': checked_ref(row['stdout_ref']),
            'actual_module_paths': modules, 'actual_applicationInfo': doc['applicationInfo'],
            'actual_signatureInfo': doc.get('signatureInfo'),
            'actual_reqPermissions': doc['reqPermissions'], 'selected_modules': {}}
        require(1 <= len(modules) <= 8, 'bounded actual MMS module inventory required')
        selected = {module: self.module(name, module) for module in modules}
        fact.update(status='actual_system_hap_facts_exported_NOT_runtime_pass', identity=identity,
            actual_applicationInfo=doc['applicationInfo'], actual_signatureInfo=doc.get('signatureInfo'),
            actual_module_paths=modules, actual_reqPermissions=doc['reqPermissions'], modules=selected)
        return write(self.output / 'mms-facts.json', fact)

    def run(self):
        self.origins()
        providers = {case: self.provider(case, bundle, target) for case, (bundle, target) in PROVIDERS.items()}
        captions = self.provider('livecaptions', 'com.ohos.vassistant', 'AiCaptionServiceExtAbility')
        require(len(captions['modules']) == 1 and 'entry' in captions['modules'], 'actual caption entry module required')
        services, configs, libraries = self.services()
        mms = self.mms(); self.recheck_bundles()
        base = {key: value for key, value in self.common.items() if key != 'package_manifest'}
        package = dict(base, schema='actual-root-capability579-package-export/v1',
            package_manifest=self.common['package_manifest'], providers=providers,
            hap_exports=list(self.haps.values()), caption_provider_hap=captions['modules']['entry']['hap'])
        service = dict(base, schema='actual-root-capability579-services-export/v1',
            services=services, init_files=configs, library_files=libraries)
        package_ref = write(self.output / 'package-export.json', package)
        services_ref = write(self.output / 'services-export.json', service)
        self.value.update(complete=True, package_export=package_ref, services_export=services_ref, mms_facts=mms)
        self.save()
        return {'package_export': package_ref, 'services_export': services_ref,
            'mms_facts': mms, 'raw_export': ref(self.output / 'raw-export.json')}


def produce(io, inputs, services):
    """Root supplied original OwnedIO; no resource acquisition or mutation."""
    return Export(io, inputs, services).run()


def make_deferred_inputs(*, package, services, native_export, caption_runtime_data,
                         caption_product_assets, permission_ui, recipes_root, profile):
    """Trusted root source chooses this one factory; JSON cannot select code.

    Return signature is deferred_inputs(owner, resources) -> exact two-key Ref.
    .exports exposes only actual produced refs for root's fixed MMS callback.
    """
    from assemble_capability579_inputs import assemble
    # Freeze DATA values, not a callable/executable supplied through JSON.
    package, services, permission_ui = [json.loads(json.dumps(value)) for value in (package, services, permission_ui)]
    native_export, caption_runtime_data, caption_product_assets = [checked_ref(value)
        for value in (native_export, caption_runtime_data, caption_product_assets)]
    package = data_common(package)
    recipes_root = Path(recipes_root)
    require(profile in ('phone', '2in1') and recipes_root.is_absolute() and recipes_root.resolve() == recipes_root and
        recipes_root.is_dir(), 'actual fixed package profile/recipe path required')
    require(json_ref(package['package_manifest'])['device_type'] == profile,
        'fixed factory profile does not match the actual package manifest')
    state = {'called': False}

    def deferred_inputs(owner, resources):
        from capability578_owned_io import OwnedIO
        from capability578_callers import prepare_callers
        from capability578_https import OwnedHTTPS
        require(not state['called'] and type(resources) is list and owner.vm is not None,
            'resolve capability inputs once on the original already-held guest')
        state['called'] = True
        owner.held_binding(owner.vm)
        io = OwnedIO(owner, owner.vm, owner.output / ('capability579-export-' + secrets.token_hex(8)),
            run_id=secrets.token_hex(16), package_inputs={}, prepare_callers=prepare_callers, https_factory=OwnedHTTPS)
        resources.append(io)  # BEFORE any producer command; original finish owns settlement.
        try:
            exports = produce(io, package, services)  # Original raw IO retained on failure.
            deferred_inputs.exports = exports
            request = {'schema': 'actual-root-capability579-input-request/v1',
                'package_export': exports['package_export'], 'services_export': exports['services_export'],
                'native_export': native_export, 'caption_runtime_data': caption_runtime_data,
                'caption_product_assets': caption_product_assets, 'permission_ui': permission_ui}
            request_ref = write(io.output / 'assembly-request.json', request)
            return assemble(request_ref, recipes_root, profile, io.output / 'assembled-inputs')
        finally:
            io.close()  # Paired scope may start only after all prior IO is closed.

    deferred_inputs.exports = None
    return deferred_inputs
