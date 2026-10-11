"""Synthetic pointer/evidence rejection fixtures, never packaged guest passes."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from run_root_probe import digest
from spring_loading_input import (SCOPE, binding, button_arguments, center, move_arguments,
                                  require_process, verify_actions)
from test_spring_loading_results import NONCE, fixture


def evidence(root):
    root.mkdir(parents=True, exist_ok=True)
    command = ('qemu-system-aarch64 -kernel /synthetic/images/Image '
               '-device virtio-gpu-pci,xres=800,yres=500 '
               '-qmp unix:/synthetic/qmp.sock,server=on,wait=off')
    env = dict(boot_id='boot', guest_arch='arm64', device_type='phone', target='127.0.0.1:12345',
        external_keepalive=False, qemu_pid=11, launcher_pid=11, qmp_socket='/synthetic/qmp.sock',
        freshly_extracted_directory='/synthetic', qemu_command=command)
    boot = dict(status='pass', purpose='acceptance', scope='fresh_packaged_QEMU_boot_NOT_full_behavior_gate',
                archive_sha256='archive', test_environment=env)
    def save(name, text):
        path = root / name
        path.write_text(text)
        return str(path), digest(path)
    actions = dict(scope=SCOPE, status='input_complete', run_id=NONCE, archive_sha256='archive',
        boot_id='boot', arch='arm64', device='phone', target=env['target'], resolution=[800, 500],
        requests=[], cycles=[], failures=[], pointer_released=True, first_artifact_behavior_gate_passed=False,
        runner_sha256=digest(Path(__file__).with_name('spring_loading_input.py')))
    actions['boot'], actions['boot_sha256'] = save('boot.json', json.dumps(boot))
    process, process_sha = save('process.txt', '11 11 ' + command + '\n')
    for label in ('pointer-owner-before', 'pointer-owner-after',
                  *(f'g{generation}-pointer-owner' for generation in range(1, 5))):
        actions[label] = dict(process=process, process_sha256=process_sha)
    clock = 1_000_000_000
    def request(name, label, arguments=None, reply=None, delay=100_000_000):
        nonlocal clock
        clock += delay
        row = dict(execute=name, label=label, arguments=arguments, reply={} if reply is None else reply,
                   host_ns=clock, completed_ns=clock + 1000)
        clock += 1000
        actions['requests'].append(row)
    schema = [dict(name=name, **{'meta-type': 'command'})
              for name in ('input-send-event', 'query-mice', 'query-status', 'human-monitor-command')]
    request('query-qmp-schema', 'actual-schema', reply=schema)
    mice = [dict(current=True, absolute=True, index=1, name='QEMU Virtio Tablet')]
    request('query-mice', 'actual-absolute-pointer', reply=mice)
    request('query-status', 'actual-running-state', reply=dict(running=True))
    request('human-monitor-command', 'actual-pointer-activate', {'command-line': 'mouse_set 1'}, reply='')
    request('query-mice', 'actual-pointer-after-activate', reply=copy.deepcopy(mice))
    all_rows = fixture()
    raw = ''.join(json.dumps(row) + '\n' for row in all_rows)
    nodes = {}
    layout = dict(attributes={'bundleName': 'org.harmonycontrib.capabilityaudit'}, children=[])
    for name, rect in (('source', [100, 100, 400, 100]), ('target', [100, 300, 400, 160]),
                       ('mode-normal', [10, 10, 100, 20]), ('mode-abort', [120, 10, 100, 20]),
                       ('mode-cancel', [230, 10, 100, 20]), ('quiet', [100, 470, 150, 20])):
        left, top, width, height = rect
        attributes = dict(id='spring-' + name, visible='true', enabled='true', clickable='true',
                          bounds=f'[{left},{top}][{left+width},{top+height}]')
        layout['children'].append(dict(attributes=attributes, children=[]))
        nodes[name] = dict(attributes=attributes, bundle='org.harmonycontrib.capabilityaudit', rect=rect)
    layout_path, layout_sha = save('layout.json', json.dumps(layout))
    screen = root / 'screen.png'
    Image.new('RGB', (800, 500), '#206080').save(screen)
    size = actions['resolution']
    for generation, mode in ((1, 'normal'), (2, 'abort'), (3, 'normal'), (4, 'cancel')):
        prefix = f'g{generation}'
        cycle = dict(generation=generation, mode=mode, checkpoints=[],
            selection=dict(layout=layout_path, layout_sha256=layout_sha, node=nodes['mode-' + mode]),
            quiet=dict(layout=layout_path, layout_sha256=layout_sha, node=nodes['quiet']),
            geometry=dict(layout=layout_path, layout_sha256=layout_sha,
                nodes={key: nodes[key] for key in ('source', 'target')},
                screenshot=str(screen), screenshot_sha256=digest(screen)))
        actions['cycles'].append(cycle)
        rows = [row for row in all_rows if row['generation'] == generation]
        start_index = all_rows.index(rows[0])
        def checkpoint(name, index, delay=10_000_000):
            nonlocal clock
            clock += delay
            path, sha = save(prefix + '-' + name + '.jsonl',
                ''.join(json.dumps(row) + '\n' for row in all_rows[:start_index + index + 1]))
            cycle['checkpoints'].append(dict(name=name, results=path, results_sha256=sha,
                host_ns=clock, request_count=len(actions['requests'])))
        def click(key, label):
            request('input-send-event', label + '.move', move_arguments(center(nodes[key], size), size))
            request('input-send-event', label + '.down', button_arguments(True))
            request('input-send-event', label + '.up', button_arguments(False))
        click('mode-' + mode, prefix + '.mode')
        checkpoint('ready', 0)
        start, finish = (center(nodes[key], size) for key in ('source', 'target'))
        request('input-send-event', prefix + '.drag.source', move_arguments(start, size))
        request('input-send-event', prefix + '.drag.press', button_arguments(True))
        for step in range(1, 9):
            point = [a + (b - a) * step // 8 for a, b in zip(start, finish)]
            request('input-send-event', prefix + '.drag.step.' + str(step), move_arguments(point, size),
                    delay=1_100_000_000 if step == 1 else 100_000_000)
        checkpoint('initiated', 1)
        request('input-send-event', prefix + '.drag.post-start-arrival',
                move_arguments([finish[0] + 2, finish[1]], size), delay=1_100_000_000)
        begin_index = 2 if mode == 'cancel' else 3
        checkpoint('begin', begin_index)
        if mode != 'cancel':
            checkpoint('terminal', next(i for i, row in enumerate(rows) if row['name'] == 'drop') - 1)
        if mode == 'abort':
            for step, offset in enumerate((2, -2, 0), 1):
                request('input-send-event', prefix + '.abort.nudge.' + str(step),
                        move_arguments([finish[0] + offset, finish[1]], size))
            checkpoint('held-quiet', 3, delay=1_500_000_000)
        request('input-send-event', prefix + '.drag.release', button_arguments(False))
        checkpoint('released', next(i for i, row in enumerate(rows) if row['name'] == 'drag.ended'))
        click('quiet', prefix + '.quiet')
        checkpoint('quiet', len(rows) - 1)
    return actions, raw


def check(actions, raw):
    return verify_actions(actions, raw, NONCE, 'archive', 'boot', 'arm64', 'phone', '127.0.0.1:12345')


class SpringLoadingInputTests(unittest.TestCase):
    def test_synthetic_exact_pointer_proof_not_guest_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            actions, raw = evidence(Path(directory))
            self.assertEqual(check(actions, raw)['physical_drag_cycles'], 4)

    def test_coordinates_are_actual_pixels_bounded_and_unrotated(self):
        self.assertEqual(move_arguments([799, 499], [800, 500])['events'][0]['data']['value'], 32767)
        self.assertEqual(move_arguments([0, 0], [800, 500])['events'][1]['data']['value'], 0)
        for point, size in (([800, 0], [800, 500]), ([-1, 0], [800, 500]),
                            ([True, 0], [800, 500]), ([0, 0], [1, 500]), ([0, 0], [800, False])):
            with self.subTest(point=point, size=size), self.assertRaises(ValueError): move_arguments(point, size)
        with self.assertRaises(ValueError): button_arguments(1)

    def test_foreign_diagnostic_boot_socket_and_process_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            actions, _ = evidence(Path(directory))
            boot = json.loads(Path(actions['boot']).read_text())
            for key, value in (('purpose', 'diagnostic'), ('archive_sha256', 'old'),
                               ('candidate_kernel', 'substitute')):
                changed = copy.deepcopy(boot); changed[key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    binding(changed, 'archive', 'boot', 'arm64', 'phone', '127.0.0.1:12345')
            changed = copy.deepcopy(boot); changed['test_environment']['qmp_socket'] = '/another.sock'
            with self.assertRaises(ValueError): binding(changed, 'archive', 'boot', 'arm64', 'phone', '127.0.0.1:12345')
            with self.assertRaises(ValueError): require_process('12 11 unrelated-qemu', boot['test_environment'])

    def test_every_missing_failed_duplicate_or_changed_input_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            actions, raw = evidence(Path(directory))
            for index in range(5, len(actions['requests'])):
                for mutation in ('missing', 'duplicate', 'failed', 'changed'):
                    changed = copy.deepcopy(actions)
                    if mutation == 'missing': del changed['requests'][index]
                    elif mutation == 'duplicate': changed['requests'].insert(index, changed['requests'][index])
                    elif mutation == 'failed': changed['requests'][index]['reply'] = {'error': 'failure'}
                    else: changed['requests'][index]['arguments'] = button_arguments(True)
                    # Some existing press requests already have these arguments.
                    if mutation == 'changed' and changed['requests'][index] == actions['requests'][index]: continue
                    with self.subTest(index=index, mutation=mutation), self.assertRaises(ValueError): check(changed, raw)

    def test_abort_nudges_long_press_quiet_and_physical_cleanup_not_optional(self):
        with tempfile.TemporaryDirectory() as directory:
            actions, raw = evidence(Path(directory))
            for field, value in (('pointer_released', False), ('run_id', 'old'), ('target', 'foreign'),
                                 ('resolution', [500, 800]), ('runner_sha256', 'old')):
                changed = copy.deepcopy(actions); changed[field] = value
                with self.subTest(field=field), self.assertRaises(ValueError): check(changed, raw)
            changed = copy.deepcopy(actions)
            changed['cycles'][1]['checkpoints'][4]['host_ns'] -= 1_500_000_000
            with self.assertRaises(ValueError): check(changed, raw)
            changed = copy.deepcopy(actions)
            next(row for row in changed['requests'] if row['label'] == 'g1.drag.step.1')['host_ns'] -= 1_000_000_000
            with self.assertRaises(ValueError): check(changed, raw)
            changed = copy.deepcopy(actions)
            changed['requests'][1]['reply'][0]['absolute'] = False
            with self.assertRaises(ValueError): check(changed, raw)

    def test_raw_callbacks_and_all_files_are_replayed_not_a_summary_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            actions, raw = evidence(Path(directory))
            for path in (Path(actions['boot']), Path(actions['pointer-owner-before']['process']),
                         Path(actions['cycles'][0]['geometry']['layout']),
                         Path(actions['cycles'][0]['geometry']['screenshot']),
                         Path(actions['cycles'][1]['checkpoints'][4]['results'])):
                original = path.read_bytes(); path.write_bytes(original + b' changed')
                with self.subTest(path=path), self.assertRaises(ValueError): check(actions, raw)
                path.write_bytes(original)
            with self.assertRaises(ValueError): check(actions, raw + '{}\n')
            with self.assertRaises(ValueError): check(actions, raw.replace('abort.called', 'fabricated'))

    def test_real_pointer_activation_is_required_bound_and_not_a_guessed_index(self):
        with tempfile.TemporaryDirectory() as directory:
            actions, raw = evidence(Path(directory))
            for index in (3, 4):
                changed = copy.deepcopy(actions); del changed['requests'][index]
                with self.subTest(index=index), self.assertRaises(ValueError): check(changed, raw)
            for key, value in (('arguments', {'command-line': 'mouse_set 2'}),
                               ('reply', 'Mouse not found'), ('execute', 'input-send-event')):
                changed = copy.deepcopy(actions); changed['requests'][3][key] = value
                with self.subTest(key=key), self.assertRaises(ValueError): check(changed, raw)
            for key, value in (('index', 2), ('name', 'another pointer'), ('absolute', False), ('current', False)):
                changed = copy.deepcopy(actions); changed['requests'][4]['reply'][0][key] = value
                with self.subTest(key=key), self.assertRaises(ValueError): check(changed, raw)
            changed = copy.deepcopy(actions)
            changed['requests'][0]['reply'] = [row for row in changed['requests'][0]['reply']
                                               if row['name'] != 'human-monitor-command']
            with self.assertRaises(ValueError): check(changed, raw)

    def test_observed_startup_and_real_held_arrival_are_not_optional(self):
        with tempfile.TemporaryDirectory() as directory:
            actions, raw = evidence(Path(directory))
            for cycle_index in range(4):
                changed = copy.deepcopy(actions)
                del changed['cycles'][cycle_index]['checkpoints'][1]
                with self.subTest(cycle=cycle_index, mutation='no-startup-observation'), self.assertRaises(ValueError):
                    check(changed, raw)
                changed = copy.deepcopy(actions)
                cycle = changed['cycles'][cycle_index]
                arrival = next(row for row in changed['requests'] if row['label'] ==
                               'g' + str(cycle['generation']) + '.drag.post-start-arrival')
                arrival['host_ns'] = cycle['checkpoints'][1]['host_ns'] + 900_000_000
                arrival['completed_ns'] = arrival['host_ns'] + 1000
                with self.subTest(cycle=cycle_index, mutation='arrival-too-early'), self.assertRaises(ValueError):
                    check(changed, raw)


if __name__ == '__main__': unittest.main()
