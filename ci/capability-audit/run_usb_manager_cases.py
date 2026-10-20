#!/usr/bin/env python3
"""USB host cases inside the existing Serial runner and enclosing boot Owner.

No resource Owner, container, VM, HDC server or alternate acceptance entry is
created here. The original runner supplies all commands, actual UI selection,
signing, ordinary identity checks, and its one private attachment endpoint.
"""
import json
import re
import secrets
import time

from serial_host_attachment_control import AttachmentControl
from run_root_probe import digest
from verify_usb_manager_results import rows, verify_saved

OWNER_BUNDLE = 'org.harmonycontrib.usbqueryaudit'
PEER_BUNDLE = 'org.harmonycontrib.usbqueryisolated'
RESULT = 'usb-manager-results.log'


def run_cases(args, environment, report, endpoint, ui, command, dialog, device,
              same_boot, build_install, launch, result):
    directory = args.output / 'usb-manager'
    directory.mkdir(exist_ok=False)
    nonce = secrets.token_hex(16)
    journal_path = directory / 'host-attachment.jsonl'
    host = {'scope': 'actual_USB_host_query_descriptor_right_and_attachment_raw_witnesses',
            'witnesses': [], 'socket_journal': [], 'ui_actions': [], 'normal_uids': {},
            'normal_identity_commands': {}, 'cleanup': {}}
    installed = []
    control = None
    journal = None
    body_error = None
    owner_raw = None
    peer_raw = None

    def save():
        if journal_path.exists():
            try:
                host['socket_journal'] = rows(journal_path.read_text())
            except ValueError as error:
                # Preserve a failed endpoint setup, including its empty raw
                # journal, without replacing the original body exception.
                host['socket_journal_error'] = str(error)
                host['socket_journal'] = []
        (directory / 'host-witnesses.json').write_text(json.dumps(host, indent=2) + '\n')

    def witness(label, present):
        device(present, 'usb-manager-' + label)
        if present:
            text = ui.shell('set -e; task_usb_query_path=$(readlink -f /sys/class/tty/ttyUSB0/device); '
                'while test "$task_usb_query_path" != /sys && ! test -f "$task_usb_query_path/idVendor"; do '
                'task_usb_query_path=${task_usb_query_path%/*}; done; '
                'test -f "$task_usb_query_path/idVendor"; printf "%s\\n" "$task_usb_query_path"; '
                'cat "$task_usb_query_path/busnum" "$task_usb_query_path/devnum" '
                '"$task_usb_query_path/idVendor" "$task_usb_query_path/idProduct" '
                '"$task_usb_query_path/serial" "$task_usb_query_path/bNumConfigurations"; '
                'od -An -tx1 -v "$task_usb_query_path/descriptors"', 'usb-manager-' + label + '-raw-sysfs')
        else:
            text = ui.shell('if test -c /dev/ttyUSB0; then echo PRESENT; else echo ABSENT; fi',
                            'usb-manager-' + label + '-raw-absence')
        host['witnesses'].append({'label': label, 'raw': text,
                                  'command': dict(report['commands'][-1])})
        save()

    def click(bundle, label, expected, decision=None):
        report['ui_actions'].append(ui.click(bundle, identifier='usb-manager-next', label=label))
        if decision is not None:
            previous = len(report['ui_actions'])
            dialog(decision, label)
            actions = report['ui_actions'][previous:]
            if len(actions) != 1:
                raise ValueError('one actual trusted USB dialog decision required')
            host['ui_actions'].append({**actions[0], 'click_command': dict(report['commands'][-1])})
        return result(RESULT, expected, label + '-actual-caller-record', bundle=bundle)

    try:
        same_boot('usb-manager-before')
        witness('initial', False)
        installed.append(OWNER_BUNDLE)  # own the attempt before install can partially succeed
        build_install('usb-manager', nonce, bundle=OWNER_BUNDLE,
                      scenario_key='usb-owner', usb_actor='owner')
        host['normal_uids'][OWNER_BUNDLE] = report['scenarios']['usb-owner']['ordinary_uid']
        host['normal_identity_commands'][OWNER_BUNDLE] = report['scenarios']['usb-owner']['identity_command']
        launch(bundle=OWNER_BUNDLE)
        result(RESULT, 'begin', 'usb-owner-ready', bundle=OWNER_BUNDLE)
        click(OWNER_BUNDLE, 'usb-initial-absence', 'query_absent_initial')
        journal = journal_path.open('x')
        control = AttachmentControl(endpoint, nonce, journal)
        control.record('begin', True)
        control.attach()
        witness('original', True)
        click(OWNER_BUNDLE, 'usb-original-denied', 'connect_denied_original')
        click(OWNER_BUNDLE, 'usb-trusted-deny', 'connect_denied_after_user_denial', 'notAllowButton')
        click(OWNER_BUNDLE, 'usb-trusted-allow', 'descriptors_original_close', 'allowButton')

        installed.append(PEER_BUNDLE)  # own the attempt before install can partially succeed
        build_install('usb-manager', nonce, bundle=PEER_BUNDLE,
                      scenario_key='usb-peer', usb_actor='peer')
        host['normal_uids'][PEER_BUNDLE] = report['scenarios']['usb-peer']['ordinary_uid']
        host['normal_identity_commands'][PEER_BUNDLE] = report['scenarios']['usb-peer']['identity_command']
        launch(bundle=PEER_BUNDLE)
        result(RESULT, 'begin', 'usb-peer-ready', bundle=PEER_BUNDLE)
        peer_raw = click(PEER_BUNDLE, 'usb-other-bundle-isolation', 'completed')
        (directory / 'peer-results.jsonl').write_text(peer_raw)
        # The USB-only ability is singleton. Foregrounding preserves its phase,
        # open handles and original raw log; no result is synthesized on restart.
        launch(bundle=OWNER_BUNDLE)
        click(OWNER_BUNDLE, 'usb-owner-right-retained-and-revoked', 'connect_denied_after_revoke')
        click(OWNER_BUNDLE, 'usb-trusted-allow-live', 'descriptors_live', 'allowButton')
        witness('live', True)
        control.detach()
        witness('detached', False)
        click(OWNER_BUNDLE, 'usb-detached-stale-pipe', 'stale_pipe_close_rejected')
        control.attach()
        witness('replug', True)
        click(OWNER_BUNDLE, 'usb-replug-right-not-inherited', 'connect_denied_replug')
        click(OWNER_BUNDLE, 'usb-trusted-deny-replug', 'connect_denied_replug_after_denial', 'notAllowButton')
        click(OWNER_BUNDLE, 'usb-trusted-allow-replug', 'right_removed_final', 'allowButton')
        control.detach()
        control.record('quit', True)
        witness('final', False)
        owner_raw = click(OWNER_BUNDLE, 'usb-final-absence', 'completed')
        (directory / 'owner-results.jsonl').write_text(owner_raw)
        same_boot('usb-manager-after')
    except Exception as error:
        body_error = error
    finally:
        if control is not None and control.connection is not None:
            try:
                control.detach('cleanup_detach')
            except Exception as error:
                host['endpoint_cleanup_error'] = str(error)
        if journal is not None and not journal.closed:
            journal.close()
        for bundle in reversed(installed):
            cleanup = {}
            host['cleanup'][bundle] = cleanup
            try:
                cleanup['stop_reply'] = ui.shell('aa force-stop ' + bundle, 'usb-cleanup-stop-' + bundle)
                cleanup['stop_command'] = dict(report['commands'][-1])
                if cleanup['stop_reply'] != 'force stop process successfully.':
                    raise ValueError('USB caller force-stop did not report actual success')
                deadline = time.monotonic() + 30
                absent = 0
                absence_commands = []
                while time.monotonic() < deadline:
                    observed = ui.shell('pidof ' + bundle + ' || true', 'usb-cleanup-pid-' + bundle)
                    absent = absent + 1 if not observed else 0
                    absence_commands = absence_commands + [dict(report['commands'][-1])] if not observed else []
                    if absent >= 2:
                        break
                    time.sleep(0.25)
                if absent < 2:
                    raise ValueError('own USB caller kernel process did not exit')
                cleanup['pidof'] = observed
                cleanup['pid_command'] = dict(report['commands'][-1])
                cleanup['absence_observations'] = absent
                cleanup['absence_commands'] = absence_commands
                remote = '/data/app/el2/100/base/' + bundle + '/files/' + RESULT
                partial = ui.shell('if test -f ' + remote + '; then cat ' + remote + '; fi',
                                   'usb-cleanup-retain-raw-' + bundle)
                retained = directory / ('owner-results.jsonl' if bundle == OWNER_BUNDLE else 'peer-results.jsonl')
                retained.write_text(partial)
                cleanup['retained_result_command'] = dict(report['commands'][-1])
                cleanup['uninstall_reply'] = command([args.hdc, '-t', environment['target'], 'uninstall', bundle],
                                                      'usb-cleanup-uninstall-' + bundle)
                cleanup['uninstall_command'] = dict(report['commands'][-1])
                if re.search(r'\bsuccess\b', cleanup['uninstall_reply'], re.I) is None:
                    raise ValueError('own USB caller uninstall did not report success')
            except Exception as error:
                cleanup['error'] = str(error)
        save()
    if body_error is not None:
        raise ValueError('actual USB host scenario failed: ' + str(body_error)) from body_error
    if any('error' in row for row in host['cleanup'].values()) or 'endpoint_cleanup_error' in host:
        raise ValueError('actual USB host scenario cleanup failed')
    errors = verify_saved(directory, nonce, OWNER_BUNDLE, PEER_BUNDLE)
    if errors:
        raise ValueError('actual USB host raw oracle failed: ' + '; '.join(errors))
    paths = ('owner-results.jsonl', 'peer-results.jsonl', 'host-witnesses.json', 'host-attachment.jsonl')
    report['scenarios']['usb-manager'] = {
        'run_id': nonce, 'status': 'pass', 'owner_bundle': OWNER_BUNDLE, 'peer_bundle': PEER_BUNDLE,
        'raw_files': {name: {'path': str(directory / name), 'sha256': digest(directory / name)} for name in paths},
        'verified_contracts': ['ordinary_USB_host_query_sysfs_descriptor_match',
                               'temporary_right_denial_allow_revoke_other_bundle_isolation',
                               'actual_USB_detach_stale_control_and_replug_fresh_right'],
        'closed': [], 'first_package_gate_passed': False,
        'not_claimed': ['device_mode_UDC_configfs', 'MTP', 'USB_bulk_payload', 'process_death_right_policy',
                        'full_historical_USB_aggregate', 'phone_profile_USB_host_endpoint']}
