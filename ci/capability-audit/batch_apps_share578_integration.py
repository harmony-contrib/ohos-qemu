"""Source-only hook candidate for the original full suite's actual owned guest.

No boot/attach/process launcher exists here. Root must explicitly add the
reviewed callable seam to run_packaged_qemu_suite.run, then inject this stage.
Old four-family plan/verifiers and the first-artifact gate are unchanged.
"""
import importlib.util
import json
from pathlib import Path
import re
import secrets
import shlex
import time

from boot_package import QemuGuest
import batch_apps_share578_project as project
import batch_apps_share578_project_verify as verifier
import batch_apps_contact_picker_coordinator as signing
from enclosing_acceptance_guest import validate_binding
from guest_ui import command_exit
from hdc_transport import failed as transport_failed
from parallel_runtime_suite import FAMILIES, boot_copy, load_plan, representative, verify_family
from batch_network_openvpn_runtime_collect import capture_snapshot

ROOT = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
def require(ok, message):
    if not ok: raise ValueError(message)


def write(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return project.record(path)


def frozen_collector():
    # The committed challenge pins all new producer/runtime modules and their
    # unchanged canonical raw/SDK/signer dependencies. No external old kit is
    # imported by pathname and no dynamic owner factory is accepted.
    import batch_apps_share578_collect
    return batch_apps_share578_collect


def signing_text_bridge(command):
    """Original full-suite command returns a record, not text or allow_failure.

    It retains its process-group timeout/termination behavior. No own Popen and
    no QemuGuest.command fallback is used for the signer process tree.
    """
    require(callable(command), 'actual enclosing suite process runner required')
    def text(argv, label):
        argv = [str(x) for x in argv]
        row = command(argv, 'share578-' + label, timeout=300)
        require(type(row) is dict and row.get('argv') == argv and type(row.get('exit_code')) is int and
                row['exit_code'] == 0 and not row.get('timed_out', False), 'actual suite signer command failed')
        log = project.regular(row['log'])
        require(project.sha(log) == row['sha256'], 'actual suite signer raw changed')
        return log.read_text()
    return text


def validate_owner(guest, suite_report, archive, suite_work, held_binding):
    require(isinstance(guest, QemuGuest), 'the original suite must pass its actual controlled QemuGuest')
    require(callable(held_binding), 'root held-handle binding callback required')
    held_binding(guest)  # raises unless this exact object is owned; never a report boolean
    archive = project.regular(archive); suite_work = Path(suite_work)
    require(suite_work.is_absolute() and suite_work.resolve() == suite_work and suite_work.is_dir(),
            'actual enclosing suite work directory required')
    require(suite_report.get('scope') == 'new_packaged_qemu_behavior' and suite_report.get('work') == str(suite_work) and
            Path(guest.args.output) == suite_work / 'boot' and Path(guest.args.archive) == archive and
            guest.report.get('archive') == str(archive), 'original suite/guest archive and output identity differ')
    require(suite_report.get('package', {}).get('sha256') == project.sha(archive) == guest.report.get('archive_sha256'),
            'new archive bytes differ from original owned boot')
    env = validate_binding(guest.report, project.sha(archive))
    require(representative(env) and suite_report.get('test_environment') == env and
            env.get('target') == guest.target and env.get('udid') == guest.udid and
            type(env.get('qemu_pid')) is int and env['qemu_pid'] > 0 and guest.process.poll() is None,
            'actual same representative process/environment required')
    guest.healthy()
    return env


class Stage:
    def __init__(self, *, guest, suite_report, suite_command, same_guest, save_suite,
                 suite_work, archive, capability_inputs, challenge, role_inputs,
                 signer_dist, signer_jar, output, held_binding, owned_family_verifier, mms_provider_verifier=None):
        require(callable(suite_command) and callable(same_guest) and callable(save_suite),
                'actual original suite callbacks required')
        self.guest, self.parent = guest, suite_report
        self.same_guest, self.save_suite = same_guest, save_suite
        self.archive, self.work = project.regular(archive), Path(suite_work)
        self.held_binding = held_binding
        require(callable(owned_family_verifier), 'trusted original family-verifier callback required')
        self.owned_family_verifier = owned_family_verifier
        self.env = validate_owner(guest, suite_report, self.archive, self.work, self.held_binding)
        self.capability_inputs = project.regular(capability_inputs)
        self.plan = load_plan(self.capability_inputs, self.env)  # original exact four keys
        self.challenge = project.regular(challenge); project.load_challenge(self.challenge)
        require(type(role_inputs) is dict and set(role_inputs) == set(project.ROLES) and all(
                set(row) == {'source_project', 'sdk_evidence', 'unsigned_hap'} for row in role_inputs.values()),
                'three actual unsigned SDK105 role descriptors required')
        self.mms_provider_verifier = mms_provider_verifier
        self.inputs = role_inputs
        self.signer_dist, self.signer_jar = Path(signer_dist), Path(signer_jar)
        self.output = Path(output)
        require(self.output == self.work / 'share578' and not self.output.exists() and not self.output.is_symlink(),
                'fresh share578 output inside actual suite work required')
        self.output.mkdir()
        self.collector = frozen_collector()
        self.transport = self.collector.root_record_bridge(guest.command, lambda: guest.report['commands'])
        self.sign_command = signing_text_bridge(suite_command)
        self.installed, self.identities, self.proofs = [], {}, {}
        self.report = dict(schema_version=1, scope='same_original_suite_guest_share578_additional_raw_slice_ONLY',
            status='running', archive=project.record(self.archive), archive_sha256=self.env_archive,
            boot_id=self.env['boot_id'], input_plan=project.record(self.capability_inputs),
            collector_source=project.record(Path(self.collector.__file__).resolve()), commands=[], signing={},
            applications={}, verified_families={}, failures=[], cleanup_errors=[],
            installed_bundles_attempted=[], cleanup_complete=False, public_payload_cleanup_verified=False,
            native_owner_release_verified_here=False, first_artifact_behavior_gate_passed=False, ledger_closed=False)
        self.save()

    @property
    def env_archive(self):
        return self.guest.report['archive_sha256']

    def save(self):
        write(self.output / 'integration-report.json', self.report)
        self.parent.setdefault('supplemental_checks', {})['share578'] = dict(
            status=self.report['status'], evidence=str(self.output / 'integration-report.json'),
            sha256=project.sha(self.output / 'integration-report.json'),
            scope=self.report['scope'], not_a_registered_first_artifact_or_gap_closure_check=True)
        self.save_suite()

    def command(self, argv, label, timeout=30):
        row = self.transport(list(map(str, argv)), label='share578-' + label, timeout=timeout)
        self.report['commands'].append(dict(label=label, observation=row)); self.save()
        raw = project.checked(row['raw']).read_text()
        require(type(row['host_exit_code']) is int and row['host_exit_code'] == 0 and not transport_failed(raw),
                'actual owned HDC operation failed: ' + label)
        self.guest.healthy()
        return raw, row

    def shell(self, script, label):
        marker = '__SHARE578_STAGE_EXIT_' + secrets.token_hex(16) + '__='
        wrapped = '(' + script + '); share578_stage_rc=$?; printf "\\n' + marker + '%s\\n" "$share578_stage_rc"'
        raw, row = self.command([self.guest.args.hdc, '-t', self.guest.target, 'shell', wrapped], label)
        body, code = command_exit(raw, marker)
        require(code == 0, 'actual stage guest command failed: ' + label)
        return body, row

    def verify_four_finished(self):
        # Conservative integration point: require all four original strict
        # verifiers/cleanup before this additional stage touches shared UI.
        for name in FAMILIES:
            evidence = self.work / name / 'evidence.json'
            parent = self.parent.get('checks', {}).get(name, {})
            require(parent.get('status') == 'pass' and parent.get('evidence') == str(evidence) and
                    parent.get('sha256') == project.sha(project.regular(evidence)),
                    'original family is not a completed verified/clean check: ' + name)
            result = self.owned_family_verifier(name, evidence, self.archive, self.env)
            self.report['verified_families'][name] = dict(evidence=project.record(evidence),
                verifier=FAMILIES[name][0] + '.verify_evidence')
        self.save()

    def own_installation(self, role, label):
        body, row = self.shell('bm dump -n ' + project.ROLES[role]['bundle'], label + '-bms')
        identity = verifier.identity(body, role)
        body, hashrow = self.shell('sha256sum ' + shlex.quote(identity['hap_path']), label + '-hash')
        signed = project.checked(self.proofs[role]['signed_hap'])
        require(body == project.sha(signed) + '  ' + identity['hap_path'] + '\n',
                'refuse to own/remove another installed HAP')
        old = self.identities.get(role)
        require(old is None or old == identity, 'installed role identity changed')
        self.identities[role] = identity
        return identity, row, hashrow

    def prepare_apps(self):
        self.same_guest('share578-before-install')
        body, row = self.shell('bm dump -a', 'initial-bundle-list')
        require(re.search(r'(?<![A-Za-z0-9_.])com\.ohos\.[A-Za-z0-9_.]+', body), 'actual system bundle baseline missing')
        require(not any(re.search(r'(?<![A-Za-z0-9_.])' + re.escape(x['bundle']) + r'(?![A-Za-z0-9_.])', body)
                        for x in project.ROLES.values()), 'fresh guest already has a share578 role; preserve it')
        # Every source/SDK provenance is checked before the first install.
        for role in project.ROLES:
            verifier.sdk_binding(self.inputs[role], role, self.challenge)
        for role, policy in project.ROLES.items():
            proof = signing.sign_normal_hap(project.checked(self.inputs[role]['unsigned_hap']), policy['bundle'], [],
                self.env['udid'], self.signer_dist, self.signer_jar, self.output / ('sign-' + role), self.sign_command)
            self.proofs[role] = proof; self.report['signing'][role] = proof; self.save()
            # Once install is dispatched, an ambiguous outcome still requires
            # ownership re-observation or root guest disposal; never assume absent.
            self.installed.append(role); self.report['installed_bundles_attempted'].append(policy['bundle']); self.save()
            self.command([self.guest.args.hdc, '-t', self.guest.target, 'install', project.checked(proof['signed_hap'])], role + '-install', 120)
            identity, bms, hashed = self.own_installation(role, role + '-installed')
            local = self.output / (role + '-actual-installed.hap')
            self.command([self.guest.args.hdc, '-t', self.guest.target, 'file', 'recv', identity['hap_path'], local], role + '-pull-installed', 60)
            require(project.sha(project.regular(local)) == project.sha(project.checked(proof['signed_hap'])), 'actual guest-pulled HAP differs')
            self.report['applications'][role] = dict(self.inputs[role], signed_hap=proof['signed_hap'],
                installed_hap=project.record(local), decoded_profile=proof['decoded_profile'], actual_guest_udid=self.env['udid'])
            self.save()

    def cleanup_apps(self):
        for role in reversed(self.installed):
            try:
                identity, _, _ = self.own_installation(role, role + '-cleanup-owner')
                # Fixed three audit bundles only, after the original operation
                # finished/failed and their installed signed bytes rechecked.
                self.shell('bm uninstall -n ' + project.ROLES[role]['bundle'], role + '-uninstall')
            except Exception as error:
                self.report['cleanup_errors'].append(role + ': ' + type(error).__name__ + ': ' + str(error))
        try:
            body, row = self.shell('bm dump -a', 'final-bundle-list')
            require(re.search(r'(?<![A-Za-z0-9_.])com\.ohos\.[A-Za-z0-9_.]+', body), 'actual final system bundle list missing')
            require(not any(re.search(r'(?<![A-Za-z0-9_.])' + re.escape(project.ROLES[r]['bundle']) + r'(?![A-Za-z0-9_.])', body)
                            for r in self.installed), 'attempted select role still installed')
            self.report['cleanup_BMS'] = row
            for role in self.installed:
                require(role in self.identities, 'unknown installed UID cannot certify cleanup')
                identity = self.identities[role]
                deadline = time.monotonic() + 10
                for number in (1, 2):
                    attempt = 0
                    while True:
                        raw, result = capture_snapshot(lambda script,label:self.shell(script,label)[0],
                            role + '-cleanup-processes-' + str(number) + '-' + str(attempt),
                            self.env['boot_id'], mode='uid', uid=identity['uid'], bundle=project.ROLES[role]['bundle'])
                        if not result['processes']:
                            break
                        require(time.monotonic() < deadline, 'actual audit UID/bundle process remains after bounded wait')
                        attempt += 1; time.sleep(.25)
                    self.report.setdefault('process_absence', []).append(dict(role=role, observation=number,
                        nonce=result['nonce'], uid=identity['uid'], bundle=project.ROLES[role]['bundle'],
                        command_index=len(self.report['commands']) - 1))
                    if number == 1:
                        time.sleep(.25)
        except Exception as error:
            self.report['cleanup_errors'].append(type(error).__name__ + ': ' + str(error))
        self.report['cleanup_complete'] = not self.report['cleanup_errors']

    def run(self):
        try:
            self.verify_four_finished()
            self.guest.save()
            stable = boot_copy(self.work / 'boot/boot.json', self.work / 'boot/share578-boot.json')
            require(validate_binding(verifier.decode(stable.read_text()), self.env_archive) == self.env,
                    'stable select boot differs from actual owned suite')
            self.report['boot'] = project.record(stable)
            self.prepare_apps()
            result = self.collector.collect(challenge=self.challenge, applications=self.report['applications'],
                boot_id=self.env['boot_id'], archive_sha256=self.env_archive, guest_udid=self.env['udid'],
                hdc=Path(self.guest.args.hdc), endpoint=self.guest.target, output=self.output / 'runtime',
                command=self.transport, healthy=self.guest.healthy, pins=self.challenge.parent / 'runtime-source-pins.json')
            self.report['collector_report'] = project.record(self.output / 'runtime/collector-report.json')
            # A returned record alone is not sufficient: re-read all eight
            # modal raw API/UI/death joins through the strict new verifier once more.
            require(len(result['cases']) == len(project.CONTRACT['cases']), 'all eight actual modal cases required')
            for item, case in zip(result['cases'], project.CONTRACT['cases']):
                require(item['case_id'] == case, 'case sequence differs')
                evidence = verifier.decode(project.checked(item['evidence']).read_text())
                req = project.checked(item['request'])
                verifier.verify_case(evidence, self.challenge, req, self.guest.args.hdc, self.guest.target, self.env_archive)
            if self.mms_provider_verifier is None:
                self.report['MMS_draft_cancel'] = {'status': 'pending_actual_parent_MMS_image_verifier_callback', 'ledger_closed': False}
            else:
                import batch_apps_mms578_runtime
                mms = batch_apps_mms578_runtime.collect(archive=self.archive, provider_verifier=self.mms_provider_verifier,
                    previous_share_report=project.record(self.output / 'runtime/collector-report.json'),
                    challenge=self.challenge, applications=self.report['applications'], boot_id=self.env['boot_id'],
                    archive_sha256=self.env_archive, guest_udid=self.env['udid'], hdc=Path(self.guest.args.hdc), endpoint=self.guest.target,
                    output=self.output / 'mms-runtime', command=self.transport, healthy=self.guest.healthy,
                    pins=self.challenge.parent / 'runtime-source-pins.json')
                self.report['MMS_draft_cancel'] = {'scope': mms['status'], 'evidence': project.record(self.output / 'mms-runtime/collector-report.json'), 'ledger_closed': False}
            self.report['public_payload_cleanup_verified'] = False
            self.report['normal_payload_FileIO_cleanup_verified'] = True
            self.report['death_payload_requires_uninstall_cleanup'] = True
            self.report['status'] = 'pass_share578_additional_raw_API_slice_ONLY'
        except Exception as error:
            self.report['status'] = 'fail'; self.report['failures'].append(type(error).__name__ + ': ' + str(error))
        finally:
            if self.installed:
                self.cleanup_apps()
                try:
                    require('result' in locals(), 'collection failed; no death success may be inferred')
                    death_request = verifier.decode(project.checked(next(x['request'] for x in result['cases'] if x['case_id'] == 'death')).read_text())
                    orphan = '/data/app/el2/100/base/' + project.ROLES['caller']['bundle'] + '/files/share578-' + death_request['run_id'] + '-' + death_request['operation_id'] + '.txt'
                    self.shell('test ! -e ' + shlex.quote(orphan), 'death-owned-payload-absent-after-uninstall')
                    self.report['death_payload_uninstall_cleanup_verified'] = True
                except Exception as error:
                    self.report['cleanup_complete'] = False
                    self.report['cleanup_errors'].append('death payload cleanup: ' + type(error).__name__ + ': ' + str(error))
            else:
                self.report['cleanup_complete'] = True
            if self.report['cleanup_errors']:
                self.report['status'] = 'fail'
            self.guest.save(); self.save()
        if self.report['status'] == 'fail':
            raise ValueError('share578 failed; preserve evidence and let original suite finally restore/close its owned guest')
        try:
            self.same_guest('share578-after-cleanup')
            validate_owner(self.guest, self.parent, self.archive, self.work, self.held_binding)
        except Exception as error:
            self.report['status'] = 'fail'
            self.report['failures'].append('final same guest: ' + type(error).__name__ + ': ' + str(error))
            self.save()
            raise
        self.save()
        return self.report


def run_owned_share_stage(**kwargs):
    return Stage(**kwargs).run()
