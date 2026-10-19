#!/usr/bin/env python3
"""Replay the Calendar source composition with five sealed actual source files.

This uses only a private host fixture. It does not build native code, contact a
guest, or write product source/out. Five other native dependencies remain fixture
inputs, explicitly distinguished from the actual read-only source export.
"""
import argparse
import hashlib
import json
from pathlib import Path

from test_batch_system_calendar375_composition import Calendar375CompositionTests, MANIFEST, COMPONENT


FILES = (
    'calendarmanager/napi/include/calendar_napi.h',
    'calendarmanager/napi/include/napi_queue.h',
    'calendarmanager/napi/include/napi_util.h',
    'calendarmanager/napi/src/calendar_napi.cpp',
    'calendarmanager/napi/src/napi_queue.cpp',
)
PROJECT = 'applications/standard/calendardata'


def checked(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular sealed source input required: ' + str(path))
    raw = path.read_bytes()
    if len(raw) > 1024 * 1024:
        raise ValueError('bounded Calendar source input required')
    return raw


def descriptor(path):
    raw = checked(path)
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def replay(vector):
    vector = Path(vector).resolve(strict=True)
    result_path, receipt_path = vector / 'result.json', vector / 'receipt.json'
    result, receipt = json.loads(checked(result_path)), json.loads(checked(receipt_path))
    if (result.get('scope') != 'actual readonly source volume vector; not build/runtime acceptance' or
            receipt.get('exit_code') != 0 or receipt.get('cleanup_verified') is not True or
            receipt.get('source_out_written') is not False or receipt.get('owned_container_absent') is not True):
        raise ValueError('completed closed actual read-only source vector required')
    result_record = receipt['result']
    if result_record['sha256'] != descriptor(result_path)['sha256']:
        raise ValueError('sealed vector receipt/result bytes differ')
    projects = [row for row in result['projects'] if row.get('path') == PROJECT]
    if len(projects) != 1 or projects[0].get('git_exit_code') != 0 or projects[0].get('HEAD') != MANIFEST['revision']:
        raise ValueError('actual pinned CalendarData revision required')
    originals = {}
    for name in FILES:
        relative = PROJECT + '/' + name
        rows = [row for row in result['files'] if row.get('path') == relative]
        if len(rows) != 1 or rows[0].get('exists') is not True:
            raise ValueError('one actual Calendar source file required: ' + relative)
        source = vector / 'source' / relative
        if any(parent.is_symlink() for parent in (source, *source.parents)):
            raise ValueError('sealed source input path must not contain links')
        raw = checked(source)
        expected = MANIFEST['files'].get(name, {}).get('before_sha256', MANIFEST['dependencies'].get(name))
        if hashlib.sha256(raw).hexdigest() != rows[0]['sha256'] or rows[0]['sha256'] != expected:
            raise ValueError('actual source does not match exact original native state: ' + relative)
        originals[name] = (source, raw, descriptor(source))
    suite = Calendar375CompositionTests('runTest')
    try:
        case = suite.viewer_case()
        for name, (_, raw, _) in originals.items():
            (case.project / name).write_bytes(raw)
        commands = []
        for name in ('filter_async_lifetime', 'main_ui', 'calendar_owner', 'source_provider',
                     'event_editor', 'editor_callback_dispatch', 'main_ui', 'calendar_owner',
                     'filter_async_lifetime'):
            process = case.run_component(name)
            commands.append({'component': name, 'exit_code': process.returncode,
                             'stdout': process.stdout, 'stderr': process.stderr})
            if process.returncode:
                raise ValueError('actual-source host composition failed: ' + name + ': ' + process.stderr)
        for name, (_, _, record) in originals.items():
            if descriptor(record['path']) != record:
                raise ValueError('original sealed source changed during replay')
        return {'scope': 'five_actual_source_files_plus_pinned_host_dependencies_ONLY_NOT_native_or_runtime',
                'status': 'pass_source_composition_only', 'commands': commands,
                'vector_result': descriptor(result_path), 'vector_receipt': descriptor(receipt_path),
                'actual_source_files': [record for _, _, record in originals.values()],
                'fixture_only_native_dependencies': sorted(set(MANIFEST['dependencies']) - set(FILES)),
                'component_manifest': descriptor(COMPONENT / 'manifest.json'),
                'native_compiled': False, 'guest_executed': False, 'requirements_closed': [],
                'first_artifact_behavior_gate_passed': False}
    finally:
        suite.doCleanups()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vector', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        result = replay(args.vector)
        code = 0
    except (ValueError, OSError, KeyError, AssertionError) as error:
        result = {'status': 'fail_preserved', 'error': type(error).__name__ + ': ' + str(error),
                  'first_artifact_behavior_gate_passed': False}
        code = 1
    (args.output / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    print(args.output / 'receipt.json')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
