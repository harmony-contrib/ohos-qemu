"""Original-Owner callback stage. No Owner/lease/process/SDK/HDC implementation.

The parent supplies seven fixed callbacks; see communications578/README.md. It
retains the original owner.finish, signing, mapped-process, native-origin and
cleanup gates. Raw behavior matches here never close an original capability ID.
"""
import hashlib
import json
from pathlib import Path
import re
import secrets
import time
import traceback
from communications578_commands import commands
from communications578_contract import IDS, plan
from communications578_raw import decode, receipt, require, review, rows_from_text

CALLBACKS = {'prepare_callers', 'install', 'start', 'input', 'collect', 'network', 'cleanup'}


def run(guest, root_callbacks, *, profile, run_id, boot_id, output, executables, timeout_s=40):
    require(type(root_callbacks) is dict and set(root_callbacks) == CALLBACKS and
            all(callable(c) for c in root_callbacks.values()), 'Exact original-Owner callbacks required')
    require(re.fullmatch('[a-f0-9]{32}', run_id) and re.fullmatch('[a-f0-9-]{36}', boot_id) and
            type(executables) in (list, tuple) and executables and
            all(type(p) is str and Path(p).is_absolute() for p in executables) and 10 <= timeout_s <= 90,
            'Actual original Owner identities/executables required')
    output = Path(output); output.mkdir(exist_ok=False)
    spec = plan(profile)
    requests = commands(profile, run_id, boot_id, [secrets.token_hex(16) for _ in spec])
    role = 'denied' if profile.endswith('-denied') else 'ordinary' if profile.endswith('-ordinary') else 'system'
    report = {'schema': 'communications578-runtime/v1', 'profile': profile, 'run_id': run_id, 'boot_id': boot_id,
              'original_ids': list(IDS), 'receipts': [], 'raw_captures': [], 'cleanup_errors': [],
              'status': 'incomplete', 'actual_new_image_pass': False}
    identity = None; retained = ''; rows = []; counter = 0; at_open = False

    def keep(name, data):
        raw = data.encode() if type(data) is str else (json.dumps(data, indent=2, allow_nan=False) + '\n').encode()
        path = output / name; path.write_bytes(raw)
        return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}

    def save(): keep('result.json', report)

    def checked(result):
        require(type(result) is dict and type(result.get('receipts')) is list and result['receipts'], 'Actual callback receipts missing')
        for item in result['receipts']: receipt(item, boot_id, executables)
        report['receipts'].extend(result['receipts']); save()
        return result

    def collect(request_id):
        nonlocal identity, retained, rows, counter
        result = checked(root_callbacks['collect'](guest, role, request_id))
        raw = result.get('raw')
        require(type(raw) is str and len(raw.encode()) <= 16 * 1024 * 1024 and raw.startswith(retained), 'Journal truncated/replaced/foreign')
        counter += 1
        report['raw_captures'].append(keep('raw-' + str(counter).zfill(5) + '.jsonl', raw))
        if not raw: require(not retained, 'Journal vanished'); save(); return []
        first = decode(raw.splitlines()[0]); require(type(first['pid']) is int and first['pid'] > 0 and type(first['uid']) is int and first['uid'] > 0, 'Actual caller PID/UID absent')
        if identity is None:
            identity = {'pid': first['pid'], 'uid': first['uid']}
            # Parent collects these using existing complete mapping/BMS helpers;
            # preserve their actual transcripts, never a supplied passed flag.
            require(type(result.get('process_identity_raw')) is str and result['process_identity_raw'] and
                    type(result.get('bms_raw')) is str and result['bms_raw'] and
                    type(result.get('module_files_raw')) is str and result['module_files_raw'], 'BMS/process/module-file binding raw missing')
            bms = decode(result['bms_raw'])
            app = bms['applicationInfo']
            require(app['uid'] == identity['uid'] and type(app.get('bundleName')) is str and
                    app['bundleName'].startswith('org.harmonycontrib.communications578'), 'Actual BMS UID/bundle mismatch')
            require(app.get('isSystemApp') is (role != 'ordinary'), 'Installed caller system role differs')
            report['identity'] = dict(identity, bms_raw=result['bms_raw'], process_identity_raw=result['process_identity_raw'],
                                      module_files_raw=result['module_files_raw'])
        rows = rows_from_text(raw, run_id, boot_id, identity['pid'], identity['uid'])
        retained = raw; save(); return rows

    def wait(request):
        deadline = time.monotonic() + max(timeout_s, request.get('wait_ms', 0) / 1000 + 15)
        while time.monotonic() < deadline:
            current = collect(request['operation_id'])
            if any(r['kind'] == 'end' and r['operation_id'] == request['operation_id'] for r in current): return current
            time.sleep(.2)
        raise ValueError('No actual caller completion: ' + request['case_id'])

    try:
        report['prepared'] = checked(root_callbacks['prepare_callers'](guest, 'communications578', run_id, (role,)))
        report['installed'] = checked(root_callbacks['install'](guest, role))
        if profile == 'observer':
            # Opens the C peer under the root's held-process machinery, binds
            # only the currently configured absent AT device, records ownership.
            report['at_open'] = checked(root_callbacks['network'](guest, 'communications-at-open',
                {'run_id': run_id, 'boot_id': boot_id}))
            at_open = True
        for expected, request in zip(spec, requests):
            if expected.get('restart_bluetooth'):
                restart = checked(root_callbacks['network'](guest, 'communications-bluetooth-native-restart', {}))
                require(type(restart.get('raw')) is str and restart['raw'] and
                        type(restart.get('before')) is dict and type(restart.get('after')) is dict and
                        set(restart['before']) == set(restart['after']) == {'pid', 'start_ticks', 'boot_id'} and
                        restart['before']['boot_id'] == restart['after']['boot_id'] == boot_id and
                        all(type(x[k]) is int and x[k] > 0 for x in (restart['before'], restart['after']) for k in ('pid', 'start_ticks')) and
                        (restart['before']['pid'], restart['before']['start_ticks']) != (restart['after']['pid'], restart['after']['start_ticks']),
                        'Actual Bluetooth service restart generation/raw missing')
                report['bluetooth_service_restart'] = keep('bluetooth-service-restart.json', restart)
            report.setdefault('requests', []).append(keep(request['case_id'] + '.request.json', request)); save()
            checked(root_callbacks['start'](guest, role, 'EntryAbility', request))
            if request['action'] == 'consent':
                checked(root_callbacks['input'](guest, 'communications-permission-consent',
                    {'bundle_prefix': 'org.harmonycontrib.communications578', 'permission': 'ohos.permission.ACCESS_BLUETOOTH'}))
            if expected.get('stimulus'):
                # Read the actual begin row before writing to the actual PTY.
                deadline = time.monotonic() + timeout_s
                while time.monotonic() < deadline:
                    if any(r['kind'] == 'begin' and r['operation_id'] == request['operation_id'] for r in collect(request['operation_id'])): break
                    time.sleep(.1)
                else: raise ValueError('Stimulus window was never armed')
                checked(root_callbacks['network'](guest, 'communications-at-write',
                    {'operation_id': request['operation_id'], 'kind': expected['stimulus']}))
            rows = wait(request)
        if at_open:
            evidence = checked(root_callbacks['network'](guest, 'communications-at-evidence', {}))
            report['at_evidence'] = keep('at-evidence.json', evidence)
        else: evidence = {}
        report['review'] = review(rows, profile, requests, peer_raw=evidence.get('peer_raw'),
                                 at_binding_raw=evidence.get('binding_raw'), run=run_id, boot=boot_id)
        report['status'] = 'raw_behavior_matched_NOT_capability_closure'
    except Exception as error:
        report['status'] = 'fail_raw_preserved'; report['error'] = type(error).__name__ + ': ' + str(error)
        report['traceback'] = traceback.format_exc()
    finally:
        # The root cleanup MUST attempt every held resource on every path,
        # preserve the C journal, send zero before channel close, restore the
        # absent configured AT path, kill/wait its exact held peer generation,
        # force-stop/uninstall callers and use its existing complete UID scans.
        try:
            report['cleanup'] = checked(root_callbacks['cleanup'](guest))
            require(type(report['cleanup'].get('raw')) is str and report['cleanup']['raw'], 'Original Owner cleanup raw missing')
        except Exception as error:
            report['cleanup_errors'].append(type(error).__name__ + ': ' + str(error))
            report['status'] = 'fail_raw_preserved'
        keep('final-raw.jsonl', retained); save()
    return report
