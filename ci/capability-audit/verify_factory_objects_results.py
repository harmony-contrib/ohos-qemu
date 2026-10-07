#!/usr/bin/env python3
"""Check five factory-returned SDK contracts, not missing runtime constructors."""
import argparse
import json
import math
from pathlib import Path
import re

from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest

TEMPLATE = Path(__file__).with_name('factory_objects_probe.ets')
DECLARATIONS = ('@ohos.resourceManager.d.ts', '@ohos.taskpool.d.ts')
CONTRACTS = {'@ohos.resourceManager': ('Configuration', 'DeviceCapability'),
             '@ohos.taskpool': ('TaskInfo', 'ThreadInfo', 'TaskPoolInfo')}
NAMES = [name + '.' + mode for mode in ('sync', 'promise', 'callback', 'isolation')
         for name in ('configuration', 'capability')]
NAMES += ['taskpool.' + phase + '.' + str(generation) for generation in range(2)
          for phase in ('live', 'complete', 'idle')]
NAMES += ['summary']


def integer(value, minimum=0, maximum=0xffffffff):
    return type(value) is int and minimum <= value <= maximum


def verify_inputs(inputs, run_id, arch):
    page = Path(inputs['generated_source'])
    declarations = inputs['sdk_declarations']
    if (inputs.get('run_id') != run_id or inputs.get('arch') != arch or
            inputs.get('role') != 'ordinary_app' or inputs.get('request_permissions') != [] or
            inputs.get('scope') != 'five_real_factory_returned_types_only' or
            digest(TEMPLATE) != inputs.get('template_sha256') or
            page.is_symlink() or not page.is_file() or
            digest(page) != inputs.get('generated_source_sha256') or
            page.read_text() != TEMPLATE.read_text().replace('__FACTORY_RUN_ID__', run_id) or
            set(declarations) != set(DECLARATIONS)):
        raise ValueError('factory caller must match the complete current typed page')
    for name, metadata in declarations.items():
        path = Path(metadata['path'])
        if (path.name != name or path.is_symlink() or not path.is_file() or
                digest(path) != metadata.get('sha256')):
            raise ValueError('factory SDK declaration differs: ' + name)
        # These five are data-return types with no constructor/static members.
        # Retain the baseline and require actual factory use, not a fake export.
        for contract in CONTRACTS[name.removesuffix('.d.ts')]:
            match = re.search(r'\bclass\s+' + contract + r'\s*\{([^{}]*)\}', path.read_text())
            if not match or re.search(r'\b(constructor|static)\b', re.sub(r'/\*.*?\*/', '',
                                                                     match[1], flags=re.S)):
                raise ValueError('SDK contract is no longer a simple factory-return type: ' + contract)


def verify(text, run_id, identity_text):
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh factory challenge required')
    require_normal_identity(identity_text)
    rows = [json.loads(line) for line in text.splitlines()]
    keys = {'name', 'values', 'text', 'tasks', 'threads', 'error', 'runId'}
    if (len(rows) != len(NAMES) or any(not isinstance(row, dict) for row in rows) or
            [row.get('name') for row in rows] != NAMES):
        raise ValueError('factory observations incomplete, reordered or extra')
    for row in rows:
        if (set(row) != keys or row['runId'] != run_id or row['error'] != '' or
                not isinstance(row['text'], str) or not isinstance(row['values'], list) or
                any(type(value) not in (int, float) or not math.isfinite(value) for value in row['values']) or
                not isinstance(row['tasks'], list) or not isinstance(row['threads'], list)):
            raise ValueError('malformed, failed or stale factory observation: ' + row['name'])
    by_name = {row['name']: row for row in rows}
    configuration = by_name['configuration.sync']
    capability = by_name['capability.sync']
    values = configuration['values']
    if (len(values) != 6 or not all(integer(value) for value in values) or
            values[0] not in (0, 1) or values[1] not in (0, 7) or
            values[2] not in (120, 160, 240, 320, 480, 640) or values[3] not in (0, 1) or
            not re.fullmatch('[A-Za-z0-9_-]+', configuration['text']) or
            capability['values'] != values[1:3] or capability['text'] != ''):
        raise ValueError('invalid or inconsistent actual resource configuration/capability')
    for mode in ('sync', 'promise', 'callback', 'isolation'):
        for kind in ('configuration', 'capability'):
            actual = by_name[kind + '.' + mode]
            expected = configuration if kind == 'configuration' else capability
            if (actual['values'] != expected['values'] or actual['text'] != expected['text'] or
                    actual['tasks'] or actual['threads']):
                raise ValueError('resource factory callback/promise/isolation differs: ' + actual['name'])
    seed = int(run_id[:4], 16)
    for generation in range(2):
        live = by_name['taskpool.live.' + str(generation)]
        complete = by_name['taskpool.complete.' + str(generation)]
        idle = by_name['taskpool.idle.' + str(generation)]
        ids = live['values']
        if len(ids) != 4 or not all(integer(value, 1) for value in ids) or len(set(ids)) != 4:
            raise ValueError('four actual distinct task IDs required')
        for snapshot in (live, idle):
            tasks = snapshot['tasks']
            threads = snapshot['threads']
            if snapshot['text'] or any(not isinstance(row, dict) for row in tasks + threads):
                raise ValueError('taskpool returned malformed diagnostic objects')
            task_ids = []
            for task in tasks:
                if (set(task) != {'taskId', 'name', 'state', 'duration'} or
                        not integer(task['taskId'], 1) or not isinstance(task['name'], str) or
                        not integer(task['state'], 1, 3) or not integer(task['duration'])):
                    raise ValueError('invalid actual TaskInfo fields')
                task_ids.append(task['taskId'])
            if len(task_ids) != len(set(task_ids)):
                raise ValueError('duplicate actual TaskInfo IDs')
            tids = []
            for thread in threads:
                if (set(thread) != {'tid', 'priority', 'taskIds'} or not integer(thread['tid'], 1) or
                        not integer(thread['priority'], 0, 3) or not isinstance(thread['taskIds'], list) or
                        not all(integer(value, 1) for value in thread['taskIds']) or
                        len(set(thread['taskIds'])) != len(thread['taskIds'])):
                    raise ValueError('invalid actual ThreadInfo fields')
                tids.append(thread['tid'])
            if len(tids) != len(set(tids)):
                raise ValueError('duplicate actual worker IDs')
        live_tasks = {row['taskId']: row for row in live['tasks']}
        if (not set(ids) <= set(live_tasks) or
                not any(live_tasks[value]['state'] == 2 for value in ids) or
                any(live_tasks[value]['name'] != 'factory-' + str(generation) + '-' + str(index)
                    for index, value in enumerate(ids)) or
                not any(set(row['taskIds']) & set(ids) for row in live['threads'])):
            raise ValueError('live TaskInfo/ThreadInfo must describe the actual submitted tasks')
        expected = [((seed + generation * 8 + index + 32640) & 0xffff) for index in range(4)]
        if (complete['values'] != expected or complete['text'] or complete['tasks'] or complete['threads'] or
                idle['values'] != ids or any(row['taskId'] in ids for row in idle['tasks']) or
                any(set(row['taskIds']) & set(ids) for row in idle['threads'])):
            raise ValueError('task results or real completion/worker cleanup failed')
    summary = by_name['summary']
    if summary['values'] != [14, 0] or summary['text'] or summary['tasks'] or summary['threads']:
        raise ValueError('factory suite summary differs')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'application-identity', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': 'five_real_factory_returned_types_only', 'run_id': args.run_id,
              'arch': args.arch, 'failures': [], 'first_artifact_behavior_gate_passed': False}
    try:
        report.update(archive_sha256=digest(args.archive), results_sha256=digest(args.results),
                      inputs_sha256=digest(args.inputs), application_identity_sha256=digest(args.application_identity))
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        report['results'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report['status'] = 'pass'
    except (ValueError, OSError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'scope', 'failures')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
