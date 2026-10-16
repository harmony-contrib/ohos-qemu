#!/usr/bin/env python3
"""Check real Wallpaper SERVICE connections and unique same-user process evidence.

The fixed AMS dump omits PID/UID and caller identity inside a non-UI SERVICE
record. This helper does not invent that direct association or prove GN/image
selection: the enclosing verifier must separately bind the actual source HAP,
product GN, linked DSO and current image, and real public wallpaper challenges.
"""
import argparse
import json
from pathlib import Path
import re

from batch_apps_contact_picker_coordinator import checked_artifact, descriptor, load, require
from batch_apps_contact_picker_runtime import objects

BUNDLE = 'com.ohos.wallpaper'
ABILITY = 'WallpaperExtAbility'
REQUIRED_STAGES = ('desktop-1', 'desktop-2')


def exact(pattern, text, reason):
    matches = re.findall(pattern, text, re.M)
    require(len(matches) == 1, reason)
    return matches[0]


def command_output(runtime, label, script, artifact, target):
    """Tie each derived raw file to the actual GuestUi shell command and exit."""
    rows = [row for row in runtime['commands'] if row.get('label') == label]
    require(len(rows) == 1, 'missing or repeated actual Wallpaper command: ' + label)
    row = rows[0]; argv = row['argv']
    require(row.get('exit_code') == 0 and len(argv) == 5 and argv[1:4] == ['-t', target, 'shell'],
            'Wallpaper observation targets another guest or failed transport')
    raw = checked_artifact(artifact).read_text()
    transport = checked_artifact(row).read_text().replace('\r', '')
    marker = re.findall(r'__UITEST_EXIT_[a-f0-9]{32}__=', argv[4])
    require(len(marker) == 1 and argv[4].startswith(script + '; task_ui_rc=$?; printf "\\n' + marker[0]),
            'Wallpaper observation is not the exact actual requested shell command')
    require(transport.count(marker[0]) == 1 and transport.rstrip().endswith(marker[0] + '0'),
            'Wallpaper observation lacks successful actual guest exit')
    prefix = transport[:transport.index(marker[0])].rstrip('\n')
    require(prefix == raw, 'Wallpaper raw observation differs from actual guest transport bytes')
    return raw


def parse_connection(ams, bms, pids, *, user_id=100, module_name='phone_wallpaper'):
    require(type(user_id) is int and user_id == 100 and module_name in ('phone_wallpaper', 'pad_wallpaper'),
            'exact standard user/module required')
    apps = [row for row in objects(bms) if row.get('bundleName') == BUNDLE and 'isSystemApp' in row]
    require(len(apps) == 1 and apps[0].get('isSystemApp') is True, 'real system Wallpaper BMS application missing or ambiguous')
    uid = apps[0].get('uid')
    require(type(uid) is int and uid // 200000 == user_id, 'Wallpaper BMS UID belongs to a different user')
    require(re.fullmatch(r'[1-9][0-9]*', pids.strip()), 'one actual Wallpaper PID required')
    pid = int(pids.strip())
    require(len(re.findall(r'^  ExtensionRecords:$', ams, re.M)) == 1 and
            len(re.findall(r'^  AppRunningRecords:$', ams, re.M)) == 1, 'complete actual AMS service/process dump required')
    processes = []
    all_pids = set()
    process_section = ams.split('  AppRunningRecords:\n', 1)[1]
    for block in re.split(r'(?=^    AppRunningRecord ID #)', process_section, flags=re.M)[1:]:
        identity = exact(r'^      pid #([1-9][0-9]*)  uid #([1-9][0-9]*)$', block, 'malformed actual AMS PID/UID')
        process_pid, process_uid = map(int, identity)
        require(process_pid not in all_pids, 'duplicate actual AMS process PID'); all_pids.add(process_pid)
        name = exact(r'^      process name \[([^\]\n]+)\]$', block, 'actual AMS process name missing or ambiguous')
        if name == BUNDLE or name.startswith(BUNDLE + ':'):
            processes.append((process_pid, process_uid, name))
    require(processes == [(pid, uid, BUNDLE)], 'Wallpaper renderer is absent, ambiguous, another PID/UID or an extra process')
    section = ams.split('  ExtensionRecords:\n', 1)[1].split('  AppRunningRecords:\n', 1)[0]
    section = re.split(r'^  [A-Za-z][^\n]*:$', section, maxsplit=1, flags=re.M)[0]
    services = []
    uri = '/' + BUNDLE + '/' + module_name + '/' + ABILITY
    for block in re.split(r'(?=^    uri \[)', section, flags=re.M)[1:]:
        actual_uri = exact(r'^    uri \[([^\]\n]+)\]$', block, 'malformed actual AMS extension URI')
        # Reject ordinary/similarly named records rather than selecting whichever
        # looks most convenient. The image guard must bind this exact module to
        # its single actual wallpaper extension; SERVICE alone is not that type.
        if BUNDLE not in actual_uri and not re.search(r'^      bundle name \[' + re.escape(BUNDLE) + r'\]$', block, re.M):
            continue
        require(actual_uri == uri and exact(r'^      bundle name \[([^\]\n]+)\]$', block, 'AMS Wallpaper bundle missing') == BUNDLE and
                exact(r'^      main name \[([^\]\n]+)\]$', block, 'AMS Wallpaper name missing') == ABILITY and
                exact(r'^      ability type \[([^\]\n]+)\]$', block, 'AMS Wallpaper service type missing') == 'SERVICE',
                'wrong or ordinary similarly named Wallpaper ability')
        record = exact(r'^      AbilityRecord ID #([0-9]+)   state #([A-Z_]+)   start time \[([0-9]+)\]$', block,
                       'actual Wallpaper ability record missing or ambiguous')
        require(record[1] in ('INACTIVE', 'ACTIVE') and int(record[2]) > 0, 'Wallpaper service is not in a connected-capable state')
        count = int(exact(r'^      Connections: ([0-9]+)$', block, 'actual Wallpaper connection count missing or duplicated'))
        connections = re.findall(r'^       > ([^\n]+?)   connectionState #([A-Z]+)$', block, re.M)
        require(count > 0 and len(connections) == count and
                all(name == BUNDLE + '/' + ABILITY and state in ('INIT', 'CONNECTING', 'CONNECTED', 'DISCONNECTING', 'DISCONNECTED')
                    for name, state in connections) and any(state == 'CONNECTED' for _, state in connections),
                'real connected Wallpaper extension connection missing or malformed')
        services.append({'uri': uri, 'record_id': int(record[0]), 'ability_state': record[1],
                         'start_time': int(record[2]), 'connection_states': [state for _, state in connections]})
    require(len(services) == 1, 'one actual connected Wallpaper extension record required')
    return {'scope': 'AMS_connected_Wallpaper_SERVICE_and_unique_same_user_process_ONLY', 'bundle': BUNDLE,
            'ability': ABILITY, 'module': module_name, 'pid': pid, 'uid': uid, 'user_id': user_id,
            'connection': services[0], 'service_token_to_pid_directly_observed': False,
            'connection_caller_identity_observed': False, 'theme_service_GN_selection_verified': False,
            'source_HAP_and_product_DSO_image_binding_required': True,
            'first_artifact_behavior_gate_passed': False, 'ledger_closed': False}


def verify_runtime_connections(runtime_path, *, target, user_id=100, module_name='phone_wallpaper'):
    runtime = load(runtime_path)
    require(re.fullmatch(r'127\.0\.0\.1:[0-9]+', target), 'actual enclosing target required')
    bms_descriptor = runtime['renderer_identity']
    bms_raw = command_output(runtime, 'renderer-BMS', 'bm dump -n ' + BUNDLE, bms_descriptor, target)
    start = bms_raw.find('{'); require(start >= 0, 'actual renderer BMS JSON missing')
    bms = json.JSONDecoder().raw_decode(bms_raw[start:])[0]
    stages = []
    for name in REQUIRED_STAGES:
        matches = [stage for stage in runtime['stages'] if stage.get('name') == name]
        require(len(matches) == 1, 'both real new desktop challenge stages required')
        stage = matches[0]
        require(type(stage.get('started_ns')) is int and type(stage.get('finished_ns')) is int and
                0 < stage['started_ns'] < stage['finished_ns'], 'actual Wallpaper stage interval missing')
        ams = command_output(runtime, name + '-AMS', 'aa dump -a -u ' + str(user_id), stage['ams'], target)
        pids = command_output(runtime, name + '-renderer-pid', 'pidof ' + BUNDLE, stage['renderer_pids'], target)
        value = parse_connection(ams, bms, pids, user_id=user_id, module_name=module_name)
        stages.append({'stage': name, **value, 'raw_AMS': stage['ams'], 'raw_renderer_pids': stage['renderer_pids']})
    return {'scope': 'two_actual_public_desktop_challenge_stage_AMS_connections_ONLY',
            'runtime': descriptor(runtime_path), 'renderer_BMS': bms_descriptor, 'stages': stages,
            'service_token_to_pid_directly_observed': False, 'connection_caller_identity_observed': False,
            'theme_service_GN_selection_verified': False, 'source_HAP_and_product_DSO_image_binding_required': True,
            'first_artifact_behavior_gate_passed': False, 'ledger_closed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True); parser.add_argument('--target', required=True)
    parser.add_argument('--module', choices=('phone_wallpaper', 'pad_wallpaper'), default='phone_wallpaper')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify_runtime_connections(args.runtime, target=args.target, module_name=args.module)
    with args.output.open('x') as stream: stream.write(json.dumps(result, indent=2) + '\n')
    return 0


if __name__ == '__main__': raise SystemExit(main())
