"""Executable photo slice INSIDE the original Knowledge collector actor.

All commands use that collector's existing command/shell/GuestUi route. There
is no constructor for a Collector, Guest, Owner, runner or process. The original
22 phase order and asset cleanup remain authoritative. Prepared callers are
real root-built/signature-verified inputs, not fabricated fixture results.
"""
import hashlib
import json
from pathlib import Path
import re
import secrets
import shlex
import shutil
import zipfile

from apps_providers579_bindings import bind, raw
from apps_providers579_project import bundle, module_fields, require, source_files
from guest_ui import command_exit

PHASES = ('prepare', 'hidden', 'unhidden', 'trashed', 'recovered', 'deleted', 'cleanup')


def reference(path):
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), 'actual regular file required')
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def prepare_knowledge_manifest(root_io, prepared, form_prepared=None):
    """Read real builder receipts; optional real 2in1 FormHost callers only.

    Parent first prepares the original Photos three-role set. For a true 2in1
    package it may additionally prepare case photosform roles normal/grant/
    denied through that SAME held root IO, then pass its actual result here.
    Phone keeps the old three callers and never prepares a fake FormHost.
    """
    io = root_io
    environment = io.test_environment if hasattr(io, 'test_environment') else io.guest.report['test_environment']
    parameters = {'profile': environment['device_type'], 'udid': io.udid}
    manifest = {'run_id': io.run_id, 'udid': io.udid, 'boot_id': io.boot_id,
                'archive_sha256': io.archive_sha256, 'callers': {}}
    groups = [('photos', prepared, ('normal', 'foreign', 'janitor'), 'callers')]
    if form_prepared is not None:
        require(parameters['profile'] == '2in1', 'actual SDK/guest 2in1 profile is required for FormHost')
        groups.append(('photosform', form_prepared, ('normal', 'grant', 'denied'), 'form_callers'))
        manifest['form_callers'] = {}
    for case, generated, roles, key in groups:
        require(generated['case'] == case and generated['run_id'] == io.run_id and
                generated['boot_id'] == io.boot_id and set(generated['callers']) == set(roles),
                'actual original root builder exact-case roles required')
        for role, produced in generated['callers'].items():
            root = Path(produced['project'])
            require(root.is_relative_to(io.output) and root.name == 'caller-' + case + '-' + role + '-' + io.run_id,
                    'actual same owned caller project required')
            source_manifest = reference(root / 'capability578-source-inputs.json')
            inputs = json.loads(raw(source_manifest))
            expected = source_files(case, io.run_id, role, parameters)
            sources = {name: inputs[name] for name in expected}
            require(all(raw(sources[name]).decode() == text for name, text in expected.items()), 'actual producer overlays differ')
            verified = [row for row in produced['verify_commands'] if 'verify-app' in row['argv']]
            require(len(verified) == 1 and verified[0]['exit_code'] == 0 and not verified[0]['timed_out'] and
                    verified[0]['boot_id'] == io.boot_id, 'one actual successful verify-app receipt required')
            row = verified[0]
            raw(row['stdout']); raw(row['stderr']); raw(produced['signed']); raw(produced['verified_profile'])
            manifest[key][role] = dict(produced, source_files=sources, source_manifest=source_manifest,
                verify_stdout=row['stdout'], verify_stderr=row['stderr'], verify_argv=row['argv'], verify_exit_code=row['exit_code'])
    destination = Path(io.output) / ('apps579-knowledge-callers-' + io.run_id + '.json')
    require(not destination.exists() and not destination.is_symlink(), 'fresh manifest under original owned output required')
    destination.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    return reference(destination)


class CollectorIO:
    """Concrete primitive adapter; original merged command stream is explicit."""
    def __init__(self, collector, artifacts):
        self.collector, self.guest, self.ui = collector, collector.guest, collector.ui
        self.boot_id = collector.env['boot_id']
        self.test_environment = collector.env
        self.archive_sha256 = collector.value['archive_sha256']
        self.hdc, self.target = str(collector.args.hdc), collector.guest.target
        self.output = collector.args.output / 'apps579_photos'
        self.output.mkdir(exist_ok=False)
        self.artifacts = json.loads(Path(artifacts).read_bytes())
        self.run_id = self.artifacts['run_id']
        self.udid = self.artifacts['udid']
        require(re.fullmatch('[a-f0-9]{32}', self.run_id) and self.artifacts['boot_id'] == self.boot_id and
                self.artifacts['archive_sha256'] == self.archive_sha256 and self.udid == collector.env['udid'],
                'prepared caller package/boot/actual guest UDID differs')
        self.environment, self.receipts, self.qmp_receipts, self.package_inputs = {}, [], [], {}
        self._serial, self._cleanup = 0, []

    def _write(self, label, body):
        self._serial += 1
        path = self.output / ('%05d_' % self._serial + label)
        path.write_bytes(body.encode() if type(body) is str else body)
        return reference(path)

    def command(self, argv, label, timeout=60, allow_failure=False, **options):
        require(not options and argv[:3] == [self.hdc, '-t', self.target] and
                argv[3] in ('shell', 'file'), 'only original held collector HDC route')
        before = len(self.collector.value['commands'])
        try:
            text = self.collector.command(argv, label, timeout=timeout)
        except ValueError:
            require(allow_failure and len(self.collector.value['commands']) == before + 1, 'original collector command failed')
            text = raw(self.collector.value['commands'][-1]['raw']).decode(errors='replace')
        original = self.collector.value['commands'][-1]
        require(len(self.collector.value['commands']) == before + 1 and original['argv'] == list(map(str, argv)),
                'one original actual command receipt required')
        row = {'argv': original['argv'], 'exit_code': original['exit_code'], 'stdout': text, 'stderr': None,
               'stdout_ref': original['raw'], 'stderr_ref': None, 'log': original['raw'],
               'stream_layout': 'stdout_stderr_merged_by_original_collector', 'boot_id': self.boot_id,
               'timed_out': original['timed_out'], 'timeout_seconds': original['timeout_seconds']}
        self.receipts.append(row)
        return row

    def shell(self, script, label, timeout=60, allow_failure=False):
        require(re.fullmatch('[A-Za-z0-9_-]+', label), 'finite Guest shell label')
        # Keep the original strict Knowledge transport contract unchanged:
        # its canonical GuestUi footer describes this enclosing shell. A
        # distinct inner nonce records the actual requested program status,
        # including expected nonzero ls/permission boundaries. Both remain
        # in the original complete merged HDC bytes, never normalized away.
        marker = '__APPS579_EXIT_' + secrets.token_hex(16) + '__='
        outer = '__UITEST_EXIT_' + secrets.token_hex(16) + '__='
        program = shlex.join(['sh', '-c', script]) + '; apps579_rc=$?; printf "\\n' + marker + '%s\\n" "$apps579_rc"'
        wrapped = program + '; task_ui_rc=$?; printf "\\n' + outer + '%s\\n" "$task_ui_rc"'
        original = self.command([self.hdc, '-t', self.target, 'shell', wrapped], label, timeout=timeout,
                                allow_failure=allow_failure)
        enclosed, outer_code = command_exit(original['stdout'], outer)
        body, code = command_exit(enclosed, marker)
        require(outer_code == 0 and original['exit_code'] == 0 and not original['timed_out'], 'original transport envelope failed')
        require(allow_failure or code == 0, 'actual guest program failed')
        cooked = dict(original, stdout=body, stdout_ref=self._write(label + '.body', body), exit_code=code,
                      transport_stdout_ref=original['stdout_ref'], transport_exit_code=original['exit_code'],
                      envelope_exit_code=outer_code)
        self.receipts[-1] = cooked
        return cooked

    @staticmethod
    def ref_receipt(row):
        result = {key: row[key] for key in ('argv', 'exit_code', 'boot_id', 'timed_out', 'stream_layout')} | {
            'merged_stream': row['log'], 'stderr_separate': None}
        if 'timeout_seconds' in row:
            result['timeout_seconds'] = row['timeout_seconds']
        if 'transport_exit_code' in row:
            result.update(program_stdout=row['stdout_ref'], transport_exit_code=row['transport_exit_code'],
                          transport_stdout=row['transport_stdout_ref'], envelope_exit_code=row['envelope_exit_code'])
        return result

    def send(self, local, remote, label):
        raw(reference(local))
        return self.command([self.hdc, '-t', self.target, 'file', 'send', str(local), remote], label)

    def receive(self, remote, local, label):
        local = Path(local)
        require(local.is_relative_to(self.output) and not local.exists(), 'fresh actual collector receive')
        before = len(self.collector.value['commands'])
        source = self.collector.receive(remote, label)
        shutil.copyfile(source['path'], local)
        require(reference(local)['sha256'] == source['sha256'], 'actual original receive changed')
        for row in self.collector.value['commands'][before:]:
            self.receipts.append({'argv': row['argv'], 'exit_code': row['exit_code'], 'boot_id': self.boot_id,
                'timed_out': row['timed_out'], 'stream_layout': 'stdout_stderr_merged_by_original_collector', 'log': row['raw']})
        return source

    def frame(self, label):
        return reference(self.ui.screenshot(label=label))

    def register_cleanup(self, function):
        self._cleanup.append(function)

    def prepare_callers(self, family, case, run, roles, parameters):
        require(family == 'apps_providers579' and run == self.run_id and
                (case, tuple(roles)) in (('photos', ('normal', 'foreign', 'janitor')),
                                        ('photosform', ('normal', 'grant', 'denied'))),
                'only fixed actual prebuilt Photos consumers and optional FormHost')
        require(case != 'photosform' or (parameters['profile'] == '2in1' and self.collector.env['device_type'] == '2in1'),
                'actual 2in1 original actor and SDK profile required')
        callers = self.artifacts['callers' if case == 'photos' else 'form_callers']
        require(set(callers) == set(roles), 'exact declared same-boot consumer set required')
        selected_sdk = None
        if case == 'photosform':
            projects = self.collector.value['artifacts_data']['projects']
            proofs = [json.loads(raw(spec['source_manifest']))['sdk'] for spec in projects.values()]
            require(proofs and all(proof['device_2in1'] == proofs[0]['device_2in1'] for proof in proofs),
                    'original four real 2in1 callers must bind one actual SDK profile')
            selected_sdk = proofs[0]['device_2in1']
            profile_path = Path(selected_sdk['path'])
            require(profile_path.as_posix().endswith('/ets/api/device-define/2in1.json') and
                    'SystemCapability.Ability.Form' in json.loads(raw(selected_sdk))['SysCaps'] and
                    all(json.loads(raw(proof['metadata']))['version'] == '26.0.0.105' for proof in proofs),
                    'actual original SDK105 2in1 profile must support FormHost')
        for role in roles:
            item = callers[role]
            if case == 'photosform':
                generated = json.loads(raw(item['source_manifest']))
                properties = raw(generated['local.properties']).decode().splitlines()
                sdk_dirs = [line[len('sdk.dir='):] for line in properties if line.startswith('sdk.dir=')]
                require(len(sdk_dirs) == 1 and Path(sdk_dirs[0]).resolve() == profile_path.parents[4].resolve(),
                        'actual FormHost build SDK path differs from the original real SDK2in1 source proof')
            raw(item['signed'])
            verified = raw(item['verify_stdout']).decode() + raw(item['verify_stderr']).decode()
            require(item['verify_exit_code'] == 0 and 'verify-app' in item['verify_argv'], 'actual crypto verification required')
            fingerprint = re.search(r'certificate\s*#0\b(?:(?!certificate\s*#\d).)*?SHA256:\s*([A-Fa-f0-9:]{64,95})', verified, re.S)
            require(fingerprint and fingerprint[1].replace(':', '').upper() == item['identity']['fingerprint'].upper(),
                    'prepared signer must come from actual verify-app certificate')
            profile = json.loads(raw(item['verified_profile']))
            require(profile['bundle-info']['bundle-name'] == bundle(case, role) and
                    profile['bundle-info']['apl'] == ('system_core' if role in ('grant', 'denied', 'janitor') else 'normal') and
                    profile['bundle-info']['app-feature'] == ('hos_system_app' if role in ('grant', 'denied', 'janitor') else 'hos_normal_app') and
                    self.udid in profile['debug-info']['device-ids'], 'ordinary same-UDID signed profile required')
            with zipfile.ZipFile(item['signed']['path']) as archive:
                compiled = json.loads(archive.read('module.json')); require(archive.read('ets/modules.abc'), 'actual caller ABC')
            require(compiled['app']['bundleName'] == bundle(case, role) and
                    compiled['module']['deviceTypes'] == module_fields(case, role, parameters)['deviceTypes'] and
                    [p['name'] for p in compiled['module'].get('requestPermissions', [])] ==
                    [p['name'] for p in module_fields(case, role)['requestPermissions']], 'caller has unexpected permission')
            actual_sources = item['source_files']
            expected = source_files(case, run, role, parameters)
            require(set(actual_sources) == set(expected), 'fixed exact generated caller source set')
            require(all(raw(actual_sources[path]).decode() == text for path, text in expected.items()), 'prepared caller source differs')
        return {'case': case, 'run_id': run, 'boot_id': self.boot_id, 'callers': callers,
                'selected_sdk_profile': selected_sdk}


def _after_phase(collector, phase, artifacts):
    if phase not in PHASES:
        return
    require(collector.value['phases'][-1]['phase'] == phase and collector.value['phases'][-1]['complete'], 'actual completed original phase')
    if not hasattr(collector, '_apps579_io'):
        require(phase == 'prepare', 'first photo hook is after actual live curator prepare')
        collector.value['apps579_artifacts'] = reference(artifacts)
        collector.value['apps579_tools'] = tool_records()
        collector._apps579_io = CollectorIO(collector, artifacts)
        collector._apps579_callbacks = bind(collector._apps579_io)
    io, callbacks = collector._apps579_io, collector._apps579_callbacks
    boot = collector.identity('apps579_' + phase + '_same_boot')
    pid = collector.pid()
    fixture = {'archive_sha256': io.archive_sha256, 'boot_id': io.boot_id, 'phase': phase,
        'uris': dict(collector.uris), 'challenge': collector.data, 'curator_pid': pid,
        'curator_journal': collector.journal('curator', 'apps579_' + phase + '_curator'),
        'phase_journal': collector.value['phases'][-1]['journal'], 'boot_raw': boot,
        'cleanup_owner': 'original_batch_media_knowledge_suite_Collector'}
    fixture_ref = io._write(phase + '_fixture.json', json.dumps(fixture, indent=2) + '\n')
    io.package_inputs['apps579_knowledge_fixture'] = fixture_ref
    from apps_providers579_runtime import run, observe_photos_phase
    result = {'failures': []}
    if not getattr(collector, '_apps579_hook_failed', False):
        if phase == 'prepare':
            result = run(collector.guest, callbacks, {'case': 'photos', 'run_id': io.run_id,
                'profile': collector.env['device_type'], 'knowledge_hook': True})
        else:
            result = observe_photos_phase(callbacks, io.run_id, phase)
        result_ref = io._write(phase + '_observations.json', json.dumps(result, indent=2, ensure_ascii=False) + '\n')
        collector.value.setdefault('apps579_photo_phases', []).append({'phase': phase, 'fixture': fixture_ref, 'observations': result_ref})
    if collector.env['device_type'] == '2in1' and 'form_callers' in io.artifacts and not getattr(collector, '_apps579_form_failed', False):
        try:
            from apps_providers579_photoform import run as form_run, observe_phase
            if phase == 'prepare':
                collector._apps579_form_callbacks = bind(io)
                form = form_run(collector.guest, collector._apps579_form_callbacks,
                    {'run_id': io.run_id, 'profile': '2in1'})
                collector._apps579_form_id = form.get('form_id')
            else:
                form = observe_phase(collector._apps579_form_callbacks, io.run_id, phase, collector._apps579_form_id)
            form_ref = io._write(phase + '_form_observations.json', json.dumps(form, indent=2, ensure_ascii=False) + '\n')
            collector.value.setdefault('apps579_form_phases', []).append({'phase': phase, 'fixture': fixture_ref, 'observations': form_ref})
            require(not form['failures'], 'actual native FormHost phase failed: ' + repr(form['failures']))
        except Exception as error:
            collector._apps579_form_failed = True
            collector.value.setdefault('apps579_form_errors', []).append({'phase': phase,
                'error': type(error).__name__ + ': ' + str(error)})
    elif collector.env['device_type'] == '2in1' and 'form_callers' not in io.artifacts:
        collector.value['apps579_form_profile_scope'] = 'not_run_missing_explicit_real_2in1_FormHost_callers'
    elif collector.env['device_type'] == '2in1':
        collector.value['apps579_form_profile_scope'] = 'failed_actual_FormHost_stage_requires_repair'
    else:
        collector.value['apps579_form_profile_scope'] = 'not_applicable_phone_related_slice_cannot_accept_2in1_ID'
    collector.persist()
    return result


def tool_records():
    here = Path(__file__).parent
    names = ('apps_providers579_knowledge.py', 'apps_providers579_bindings.py', 'apps_providers579_project.py',
             'apps_providers579_runtime.py', 'apps_providers579_dialog.py', 'apps_providers579_photoform.py',
             'apps_providers579/Journal.ets', 'apps_providers579/EntryAbility.ets',
             'apps_providers579/PhotosDriver.ets', 'apps_providers579/PhotosPage.ets',
             'apps_providers579/PhotoFormDriver.ets', 'apps_providers579/PhotoFormPage.ets',
             'apps_providers579/JanitorDriver.ets', 'apps_providers579/PlainPage.ets', 'apps_providers579/MediaBytes.ets')
    return {name: reference(here / name) for name in names}


def verify_hook(value):
    if 'apps579_artifacts' not in value:
        require(not value.get('apps579_photo_phases') and not value.get('apps579_form_phases') and not value.get('apps579_errors'), 'unbound extra photo records')
        return
    raw(value['apps579_artifacts'])
    require(value['apps579_tools'] == tool_records(), 'actual in-process Apps579 implementation changed')
    for row in value.get('apps579_photo_phases', []) + value.get('apps579_form_phases', []):
        fixture = json.loads(raw(row['fixture']))
        require(fixture['boot_id'] == value['boot_id'] and fixture['archive_sha256'] == value['archive_sha256'] and
                fixture['phase'] == row['phase'] and fixture['cleanup_owner'] == 'original_batch_media_knowledge_suite_Collector',
                'extra photo fixture belongs to a different original actor/boot/package')
        result = json.loads(raw(row['observations']))
        require(result.get('runtime_pass') is False and result.get('closed_requirement_ids') == [],
                'extra photo stage cannot auto-close the original ID or first artifact')


def after_phase(collector, phase, artifacts):
    if phase not in PHASES:
        return
    try:
        result = _after_phase(collector, phase, artifacts)
        require(not result.get('failures'), 'extra Photos typed stage failed: ' + repr(result.get('failures')))
    except Exception as error:
        # Preserve the original complete 22-step investigation and finally.
        # This is an explicit failed extra stage, never a fabricated pass.
        collector._apps579_hook_failed = True
        collector.value.setdefault('apps579_errors', []).append({'phase': phase, 'error': type(error).__name__ + ': ' + str(error)})
        if hasattr(collector, '_apps579_callbacks'):
            try:
                outcome = collector._apps579_callbacks['cleanup']()
                collector.value.setdefault('apps579_error_cleanup', []).append(outcome)
            except Exception as cleanup_error:
                collector.value.setdefault('apps579_errors', []).append({'phase': phase,
                    'cleanup_error': type(cleanup_error).__name__ + ': ' + str(cleanup_error)})
        collector.persist()


def cleanup(collector):
    errors = []
    # Both sets use the same original actor IO. A failed extra stage cannot
    # prevent the other real caller/FMS cleanup or the original curator finally.
    for attribute, key in (('_apps579_form_callbacks', 'apps579_form_cleanup'),
                           ('_apps579_callbacks', 'apps579_cleanup')):
        if hasattr(collector, attribute):
            try:
                outcome = getattr(collector, attribute)['cleanup']()
                collector.value[key] = outcome
                require(not outcome.get('failures'), 'actual Apps579 cleanup reported failure')
            except Exception as error:
                errors.append({'stage': key, 'type': type(error).__name__, 'error': str(error)})
    if errors:
        collector.value.setdefault('apps579_cleanup_errors', []).extend(errors)
    collector.persist()
    require(not errors, 'actual Apps579 photo/FormHost cleanup failed')
