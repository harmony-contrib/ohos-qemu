"""Register only complete signed dynamic-intent proofs on the exact enclosing boot."""
import copy
import json
from pathlib import Path
import re
import zipfile
import build_insight_driver_probe as driver
import build_insight_form_host_probe as form
import build_insight_navigation_probe as navigation
import sign_insight_driver_probe as driver_signer
import sign_insight_form_host_probe as form_signer
import sign_insight_navigation_probe as navigation_signer
from sign_ethernet_control_probe import configure_profile as target_profile
from insight_contract_common import EVIDENCE_SCOPE, checked_file, identity, verify_application
from verify_insight_decorator_build import verify as verify_target
from verify_insight_complete_driver_results import verify as verify_driver
from verify_insight_form_host_results import verify as verify_form, verify_provider, verify_pixels
from verify_insight_navigation_results import verify as verify_navigation, verify_receiver, verify_views
from run_root_probe import digest

CONTRACTS = tuple('arkts_export:@ohos.app.ability.InsightIntentDecorator:InsightIntent' + name
                  for name in ('Entity', 'Entry', 'Form', 'Function', 'FunctionMethod', 'Link', 'Page'))


def verify_evidence(document, archive_sha, boot_id, arch, device, target):
    if (document.get('status') != 'pass' or document.get('scope') != EVIDENCE_SCOPE or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('device') != device or document.get('target') != target or
            document.get('failures') != [] or document.get('caller_cleanup_verified') is not True or
            set(document.get('cleanup', {})) != {driver.BUNDLE, form.BUNDLE, navigation.BUNDLE, driver.TARGET_BUNDLE} or
            any(row != {'process_absent': True} for row in document['cleanup'].values()) or
            re.fullmatch('[a-fA-F0-9]{64}', document.get('udid', '')) is None):
        raise ValueError('complete dynamic intent proof on the exact enclosing archive/guest required')
    journal = []
    for row in document.get('commands', []):
        path = Path(row['log'])
        if (path.is_symlink() or not path.is_file() or digest(path) != row.get('sha256') or
                not isinstance(row.get('argv'), list) or any(type(arg) is not str for arg in row['argv']) or
                type(row.get('exit_code')) is not int or row.get('timed_out')):
            raise ValueError('dynamic intent command evidence missing, malformed or changed')
        journal.append((path.name.split('-', 1)[1][:-4], row, path.read_text().replace('\r', '')))
    if not journal: raise ValueError('actual intent command journal required')

    def one_command(label):
        matches = [(index, row, reply) for index, (actual_label, row, reply) in enumerate(journal) if actual_label == label]
        if len(matches) != 1 or matches[0][1]['exit_code'] != 0:
            raise ValueError('one successful actual intent command required: ' + label)
        return matches[0]

    def shell_rows(label, script):
        result = []
        for actual_label, command, reply in journal:
            if actual_label != label: continue
            argv = command['argv']
            if len(argv) != 5 or argv[1:4] != ['-t', target, 'shell'] or not argv[4].startswith(script + '; task_intent_rc=$?; printf "\\n__INTENT_SHELL_EXIT_'):
                raise ValueError('intent shell evidence escaped its exact guest/script')
            match = re.search(r'(?:^|\n)__INTENT_SHELL_EXIT_[a-f0-9]{32}__=(\d+)\s*$', reply)
            if command['exit_code'] == 0 and match and match.group(1) == '0': result.append(reply[:match.start()])
        return result

    def actual_read(label, script, text):
        if text not in shell_rows(label, script): raise ValueError('intent observation did not originate in an actual successful HDC read: ' + label)

    def one_shell(label, script, reply):
        values = shell_rows(label, script)
        if len(values) != 1 or values[0].strip() != reply:
            raise ValueError('one exact successful intent guest boundary/cleanup reply required: ' + label)

    def presentation(record):
        from PIL import Image
        if record.get('status') != 'pass_presentation_only' or len(record.get('samples', [])) < 3:
            raise ValueError('three stable actual intent compositor samples required')
        selected = record['samples'][-3:]; previous = None
        for index, sample in enumerate(selected, 1):
            layout = Path(sample['layout']); picture = Path(sample['screenshot'])
            if (layout.is_symlink() or picture.is_symlink() or digest(layout) != sample.get('layout_sha256') or
                    digest(picture) != sample.get('screenshot_sha256') or sample.get('not_ready') or
                    sample.get('consecutive_identical_presentations', 0) < index):
                raise ValueError('intent presentation sample is missing, changed or not stable')
            actual = json.loads(layout.read_text())
            linked = False
            for label, command, reply in journal:
                argv = command['argv']
                if command['exit_code'] != 0 or len(argv) != 5 or argv[1:4] != ['-t', target, 'shell']:
                    continue
                if not argv[4].startswith('cat /data/local/tmp/qemu-capability-ui-') or not label.endswith('-read'): continue
                match = re.search(r'(?:^|\n)__UITEST_EXIT_[a-f0-9]{32}__=0\s*$', reply)
                if match and json.loads(reply[:match.start()]) == actual: linked = True; break
            if not linked: raise ValueError('intent view did not originate in the actual guest UITest read')
            received = [command for label, command, reply in journal if command['exit_code'] == 0 and
                command['argv'][1:4] == ['-t', target, 'file'] and len(command['argv']) == 7 and
                command['argv'][4] == 'recv' and command['argv'][6] == str(picture) and
                command['argv'][5].startswith('/data/local/tmp/qemu-capability-ui-') and label.endswith('-receive-compositor-capture')]
            if len(received) != 1: raise ValueError('intent pixels lack their actual guest compositor transfer')
            node = sample.get('selected_node') or sample.get('nodes', {}).get('marker')
            x, y, width, height = node['rect']
            with Image.open(picture) as image: fingerprint = image.convert('RGB').crop((x, y, x + width, y + height)).tobytes()
            current = node['rect'], fingerprint
            if previous is not None and previous != current: raise ValueError('intent claimed stability with changing compositor text')
            previous = current

    identity_values = shell_rows('guest-identity', 'id -u; param get const.product.devicetype; uname -m')
    if len(identity_values) != 1 or identity_values[0].split() != [
            '0', device, {'arm64': 'aarch64', 'armv7a': 'armv7l', 'x86_64': 'x86_64'}[arch]]:
        raise ValueError('actual intent guest UID/profile/architecture differs')
    for label in ('boot-before', 'boot-final'):
        one_shell(label, 'cat /proc/sys/kernel/random/boot_id', boot_id)
    expected_apps = {'target'} | {prefix + role for prefix in ('caller-', 'function-caller-', 'navigation-caller-') for role in driver.ROLES}
    if set(document.get('applications', {})) != expected_apps: raise ValueError('actual decorator target and all nine signed callers required')
    target_record = document['applications']['target']; nonce = document['target_nonce']
    built = verify_target(Path(target_record['project']), nonce)
    source = {'extractInsightIntents': built['metadata']}
    target_paths = {key: checked_file(target_record[key]) for key in (
        'signed_hap', 'unsigned_hap', 'signing_receipt', 'application_identity', 'inputs')}
    if digest(target_paths['unsigned_hap']) != built['unsigned_hap_sha256'] or digest(target_paths['inputs']) != built['inputs_sha256']:
        raise ValueError('installed decorator target differs from actual compiler/SDK proof')
    signing = json.loads(target_paths['signing_receipt'].read_text())
    with zipfile.ZipFile(target_paths['signed_hap']) as signed, zipfile.ZipFile(target_paths['unsigned_hap']) as unsigned:
        compiled = json.loads(signed.read('module.json'))
        for name in ('module.json', 'ets/modules.abc', 'ets/widgets.abc', 'resources/base/profile/insight_intent.json', 'resources/base/profile/form_config.json'):
            if signed.read(name) != unsigned.read(name): raise ValueError('signature changed a decorator target implementation/profile')
    profile = signing.get('verified_profile', {})
    if (signing.get('status') != 'pass' or signing.get('role') != 'normal' or
            signing.get('signed_sha256') != digest(target_paths['signed_hap']) or
            signing.get('unsigned_sha256') != digest(target_paths['unsigned_hap']) or
            target_profile(copy.deepcopy(profile), 'normal', document['udid'], compiled) != profile):
        raise ValueError('actual ordinary decorated target signature differs')
    target_uid = identity(target_paths['application_identity'].read_text(), driver.TARGET_BUNDLE, 'normal')
    if target_record.get('actual_uid') != target_uid: raise ValueError('actual decorated target UID differs')
    for name, app in document['applications'].items():
        installed, command, reply = one_command(name + '-install')
        signed = checked_file(app['signed_hap'])
        if command['argv'][1:] != ['-t', target, 'install', str(signed)] or not re.search('success', reply, re.I) or re.search('failed to install', reply, re.I):
            raise ValueError('actual exact signed intent HAP installation required')
        identity_index, _, _ = one_command(name + '-actual-BMS-record')
        actual_read(name + '-actual-BMS-record', 'bm dump -n ' + app['bundle'], checked_file(app['application_identity']).read_text())
        if identity_index <= installed: raise ValueError('intent identity preceded its successful installation')
        signed_index, sign_command, _ = one_command(name + '-sign')
        if signed_index >= installed or sign_command['argv'][:3] != ['docker', 'run', '--rm'] or '--udid' not in sign_command['argv'] or sign_command['argv'][sign_command['argv'].index('--udid') + 1] != document['udid']:
            raise ValueError('actual intent device-bound signing must precede installation')
    nonces = {nonce}
    for family, prefix, builder, signer in (
            ('roles', 'caller-', form, form_signer), ('complete_driver_roles', 'function-caller-', driver, driver_signer),
            ('navigation_roles', 'navigation-caller-', navigation, navigation_signer)):
        if set(document.get(family, {})) != set(driver.ROLES): raise ValueError('all three signed caller roles required for every intent family')
        for role, record in document[family].items():
            name = prefix + role; app = document['applications'][name]; challenge = record['run_id']; nonces.add(challenge)
            uid = verify_application(app, builder, signer, challenge, role, arch, document['udid'], nonce if family == 'navigation_roles' else None)
            if record.get('uid') != uid: raise ValueError('intent native caller UID summary differs')
            raw_path = Path(record['raw_results'])
            if raw_path.is_symlink() or not raw_path.is_file() or digest(raw_path) != record.get('raw_results_sha256'):
                raise ValueError('actual intent caller journal changed')
            raw = raw_path.read_text()
            app_base = '/data/app/el2/100/base/' + builder.BUNDLE + '/files/'
            leaf = ('insight-form-host-' if family == 'roles' else 'insight-driver-' if family == 'complete_driver_roles' else 'insight-navigation-') + challenge + '-results.log'
            label = role + ('-intent-own-results' if family == 'roles' else '-complete-driver-own-results' if family == 'complete_driver_roles' else '-navigation-own-results')
            actual_read(label, 'cat ' + app_base + leaf + ' 2>/dev/null', raw)
            if family == 'roles':
                ids = verify_form(raw, challenge, role, uid)
                provider = Path(record['provider_results'])
                if provider.is_symlink() or digest(provider) != record.get('provider_results_sha256'): raise ValueError('actual card provider journal changed')
                provider_remote = '/data/app/el2/100/base/' + driver.TARGET_BUNDLE + '/files/insight-form-' + nonce + '-results.log'
                actual_read(role + '-real-form-provider-journal', 'if test -e ' + provider_remote + '; then cat ' + provider_remote + '; fi', provider.read_text())
                if role == 'system':
                    verify_provider(provider.read_text(), nonce, ids)
                    phases = document['phases']['system']
                    if len(phases) != 2: raise ValueError('both actual card recreation view phases required')
                    for phase, identifier in zip(phases, ids):
                        if phase.get('form_id') != identifier: raise ValueError('card image/ID differs')
                        presentation(phase['acquired_presentation']); presentation(phase['updated_presentation'])
                        verify_pixels(phase['acquired_screenshot'], phase['updated_screenshot'], json.loads(Path(phase['acquired_layout']).read_text()), json.loads(Path(phase['updated_layout']).read_text()), nonce, identifier)
                elif provider.read_text(): raise ValueError('denied caller caused provider work')
            elif family == 'complete_driver_roles': verify_driver(raw, challenge, role, uid, source, nonce)
            else:
                observations = verify_navigation(raw, challenge, role, uid, source, nonce)
                if role == 'system':
                    target_journal, page_journal = (Path(record[key]) for key in ('target_results', 'page_results'))
                    for key, path in (('target_results', target_journal), ('page_results', page_journal)):
                        if path.is_symlink() or digest(path) != record.get(key + '_sha256'): raise ValueError('actual navigation receiver journal changed')
                    verify_receiver(target_journal.read_text(), page_journal.read_text(), nonce, challenge, uid, target_uid, observations[0]['values'][2])
                    for kind, path in (('target', target_journal), ('page', page_journal)):
                        actual_read('navigation-system-actual-' + kind + '-journal',
                            'cat /data/app/el2/100/base/' + driver.TARGET_BUNDLE + '/files/insight-' + kind + '-' + nonce + '-results.log 2>/dev/null', path.read_text())
                    verify_views(record['phases'], nonce, challenge)
                    for phase in record['phases']: presentation(phase['presentation'])
    if len(nonces) != 10: raise ValueError('independent fresh target and nine caller challenges required')
    for bundle in document['cleanup']:
        one_shell('cleanup-process-absence-' + bundle, 'pidof ' + bundle + ' || true', '')
    return list(CONTRACTS)
