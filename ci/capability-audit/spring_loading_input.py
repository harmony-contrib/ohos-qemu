"""Real pointer input on the enclosing package-owned VM, never callback replay."""
import json
from pathlib import Path
import re
import shlex
import socket
import stat
import time

from guest_ui import LayoutNotReady, select_node
from run_root_probe import digest

BUNDLE = 'org.harmonycontrib.capabilityaudit'
SCOPE = 'owned_package_QMP_pointer_four_real_spring_hover_generations'
# QEMU include/ui/input.h INPUT_EVENT_ABS_MAX. This is the device protocol,
# not a guessed guest position; pixels come from actual UITest/compositor data.
ABS_MAX = 0x7FFF


def binding(boot, archive_sha, boot_id, arch, device, target):
    env = boot.get('test_environment', {})
    if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
            boot.get('scope') != 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate' or
            boot.get('archive_sha256') != archive_sha or env.get('boot_id') != boot_id or
            env.get('guest_arch') != arch or env.get('device_type') != device or
            env.get('target') != target or env.get('external_keepalive') is not False or
            any(boot.get(k) for k in ('candidate_kernel', 'kernel_command_line_diagnostic',
                                     'diagnostic_assistance', 'diagnostic_power_button')) or
            any(type(env.get(k)) is not int or env[k] <= 0 for k in ('qemu_pid', 'launcher_pid'))):
        raise ValueError('pointer input requires the unchanged enclosing acceptance VM')
    argv = shlex.split(env.get('qemu_command', ''))
    qmp = 'unix:' + env.get('qmp_socket', '') + ',server=on,wait=off'
    images = str(Path(env.get('freshly_extracted_directory', '')) / 'images') + '/'
    gpus = [word for word in argv if word.startswith('virtio-gpu-pci,')]
    if (len(gpus) != 1 or '-qmp' not in argv or argv[argv.index('-qmp') + 1] != qmp or
            not any(word.startswith(images) for word in argv) or
            not Path(env.get('qmp_socket', '')).is_absolute() or not images.startswith('/')):
        raise ValueError('pointer QMP socket and images are not bound to the actual QEMU command')
    match = re.fullmatch(r'virtio-gpu-pci,xres=(\d+),yres=(\d+)', gpus[0])
    if not match or any(not 100 <= int(value) <= 16384 for value in match.groups()):
        raise ValueError('one actual GPU resolution without rotation or guessed scaling required')
    return env, list(map(int, match.groups()))


def require_process(text, env):
    rows = [line.strip().split(None, 2) for line in text.splitlines() if line.strip()]
    if (len(rows) != 1 or len(rows[0]) != 3 or rows[0][:2] !=
            [str(env['qemu_pid']), str(env['launcher_pid'])] or rows[0][2] != env['qemu_command']):
        raise ValueError('recorded package-owned QEMU process is no longer the same live session')


def center(node, size):
    left, top, width, height = node['rect']
    if (any(type(v) is not int for v in (*node['rect'], *size)) or min(width, height) < 4 or
            min(left, top) < 0 or left + width > size[0] or top + height > size[1]):
        raise ValueError('actual pointer node is outside the unrotated compositor')
    return [left + width // 2, top + height // 2]


def move_arguments(point, size):
    if (len(point) != 2 or len(size) != 2 or
            any(type(v) is not int for v in (*point, *size)) or
            any(not 100 <= v <= 16384 for v in size) or
            any(not 0 <= p < dimension for p, dimension in zip(point, size))):
        raise ValueError('bounded actual compositor pixel coordinates required')
    return {'events': [{'type': 'abs', 'data': {'axis': axis, 'value': p * ABS_MAX // (dimension - 1)}}
                       for axis, p, dimension in zip(('x', 'y'), point, size)]}


def button_arguments(down):
    if type(down) is not bool:
        raise ValueError('real pointer button state must be boolean')
    return {'events': [{'type': 'btn', 'data': {'button': 'left', 'down': down}}]}


def protocol(schema, mice):
    if (not isinstance(schema, list) or not all(isinstance(row, dict) for row in schema) or
            not all(any(row.get('name') == name and row.get('meta-type') == 'command' for row in schema)
                    for name in ('input-send-event', 'query-mice', 'query-status')) or
            not isinstance(mice, list)):
        raise ValueError('actual QEMU pointer command schema required')
    current = [mouse for mouse in mice if isinstance(mouse, dict) and mouse.get('current') is True]
    if len(current) != 1 or current[0].get('absolute') is not True:
        raise ValueError('actual current QEMU pointer must be absolute; no guessed relative scaling')


class OwnedPointer:
    def __init__(self, command, boot_path, output, archive_sha, boot_id, arch, device, target):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.command = command
        self.boot = json.loads(Path(boot_path).read_text())
        self.env, self.size = binding(self.boot, archive_sha, boot_id, arch, device, target)
        saved = self.output / 'acceptance-boot.json'
        saved.write_text(json.dumps(self.boot, indent=2) + '\n')
        self.report = dict(scope=SCOPE, status='fail', archive_sha256=archive_sha, boot_id=boot_id,
            arch=arch, device=device, target=target, resolution=self.size, boot=str(saved),
            boot_sha256=digest(saved), runner_sha256=digest(Path(__file__)), requests=[], cycles=[],
            failures=[], pointer_released=False, first_artifact_behavior_gate_passed=False)
        self.pressed = False
        self.healthy('pointer-owner-before')
        schema = self.qmp('query-qmp-schema', 'actual-schema')
        mice = self.qmp('query-mice', 'actual-absolute-pointer')
        protocol(schema, mice)
        if self.qmp('query-status', 'actual-running-state').get('running') is not True:
            raise ValueError('owned QEMU is not running')

    def healthy(self, label):
        text = self.command(['ps', '-p', str(self.env['qemu_pid']), '-o', 'pid=,pgid=,command='], label)
        require_process(text, self.env)
        path = self.output / (label + '.txt')
        path.write_text(text)
        self.report[label] = dict(process=str(path), process_sha256=digest(path))
        if not stat.S_ISSOCK(Path(self.env['qmp_socket']).stat().st_mode):
            raise ValueError('owned QMP endpoint is not an actual local socket')

    def qmp(self, execute, label, arguments=None):
        record = dict(execute=execute, label=label, arguments=arguments, host_ns=time.monotonic_ns())
        self.report['requests'].append(record)
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(10)
            connection.connect(self.env['qmp_socket'])
            with connection.makefile('rb') as stream:
                if 'QMP' not in json.loads(stream.readline()):
                    raise ValueError('owned pointer QMP greeting missing')
                for identifier, name, params in (('capabilities', 'qmp_capabilities', None),
                                                 ('pointer', execute, arguments)):
                    request = {'execute': name, 'id': identifier}
                    if params is not None:
                        request['arguments'] = params
                    connection.sendall(json.dumps(request).encode() + b'\n')
                    while True:
                        line = stream.readline()
                        if not line:
                            raise ValueError('owned pointer QMP disconnected')
                        reply = json.loads(line)
                        if reply.get('id') == identifier:
                            if 'error' in reply or 'return' not in reply:
                                record['failure_reply'] = reply
                                raise ValueError('actual owned pointer operation rejected')
                            break
                record.update(reply=reply['return'], completed_ns=time.monotonic_ns())
                return reply['return']

    def move(self, point, label):
        self.qmp('input-send-event', label, move_arguments(point, self.size))

    def button(self, down, label):
        # Mark before sending: even an ambiguous transport failure must attempt
        # release in finally, never leave an owned button held in the suite VM.
        if down:
            self.pressed = True
        self.qmp('input-send-event', label, button_arguments(down))
        if not down:
            self.pressed = False

    def click(self, node, label):
        self.move(center(node, self.size), label + '.move')
        self.button(True, label + '.down')
        time.sleep(0.1)
        self.button(False, label + '.up')

    def save(self):
        path = self.output / 'actions.json'
        path.write_text(json.dumps(self.report, indent=2) + '\n')
        return path


def exercise(ui, pointer, read_results, run_id, timeout=60):
    """Four real drags, including held abort nudges and physical boundary re-entry."""
    def observed(predicate, label):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            text = read_results()
            if text.endswith('\n'):
                rows = [json.loads(line) for line in text.splitlines()]
                if any(row.get('runId') != run_id or row.get('error') != '' or
                       row.get('instance') is not True for row in rows):
                    raise ValueError('real spring caller failed or reported a foreign context')
                if predicate(rows):
                    return text, rows
            time.sleep(0.05)
        raise ValueError('actual physical spring action did not complete: ' + label)

    def selected(identifier, label, clickable=False):
        deadline = time.monotonic() + timeout
        last = ''
        while time.monotonic() < deadline:
            try:
                layout, path = ui.layout(bundle=BUNDLE, label=label)
                node = select_node(layout, BUNDLE, identifier=identifier, clickable=clickable)
                center(node, pointer.size)
                return dict(layout=str(path), layout_sha256=digest(path), node=node)
            except (ValueError, LayoutNotReady) as error:
                last = str(error)
                time.sleep(0.25)
        raise ValueError('actual spring UI not ready: ' + label + ': ' + last)

    def checkpoint(cycle, name, text):
        path = pointer.output / ('generation-' + str(cycle['generation']) + '-' + name + '.jsonl')
        path.write_text(text)
        cycle['checkpoints'].append(dict(name=name, results=str(path), results_sha256=digest(path),
            host_ns=time.monotonic_ns(), request_count=len(pointer.report['requests'])))

    def has(rows, generation, name, state=None):
        return any(row.get('generation') == generation and row.get('name') == name and
                   (state is None or row.get('state') == state) for row in rows)

    try:
        observed(lambda rows: bool(rows) and rows[0]['name'] == 'constructor', 'public-constructor')
        for generation, mode in ((1, 'normal'), (2, 'abort'), (3, 'normal'), (4, 'cancel')):
            prefix = 'g' + str(generation)
            cycle = dict(generation=generation, mode=mode, checkpoints=[])
            pointer.report['cycles'].append(cycle)
            pointer.healthy(prefix + '-pointer-owner')
            cycle['selection'] = selected('spring-mode-' + mode, prefix + '-mode', clickable=True)
            pointer.click(cycle['selection']['node'], prefix + '.mode')
            text, _ = observed(lambda rows: has(rows, generation, 'ready.' + str(
                {'normal': 1, 'abort': 2, 'cancel': 3}[mode])), prefix + '-ready')
            checkpoint(cycle, 'ready', text)
            layout, path = ui.layout(bundle=BUNDLE, label=prefix + '-source-and-target')
            nodes = {key: select_node(layout, BUNDLE, identifier='spring-' + key) for key in ('source', 'target')}
            screen = ui.screenshot(label=prefix + '-actual-compositor')
            from PIL import Image
            with Image.open(screen) as image:
                if list(image.size) != pointer.size:
                    raise ValueError('guest compositor is rotated/scaled relative to owned QEMU GPU')
            cycle['geometry'] = dict(layout=str(path), layout_sha256=digest(path), nodes=nodes,
                screenshot=str(screen), screenshot_sha256=digest(screen))
            start, finish = (center(nodes[key], pointer.size) for key in ('source', 'target'))
            pointer.move(start, prefix + '.drag.source')
            pointer.button(True, prefix + '.drag.press')
            time.sleep(1)
            for step in range(1, 9):
                point = [a + (b - a) * step // 8 for a, b in zip(start, finish)]
                pointer.move(point, prefix + '.drag.step.' + str(step))
                time.sleep(0.02)
            text, _ = observed(lambda rows: has(rows, generation, 'callback', 0), prefix + '-real-BEGIN')
            checkpoint(cycle, 'begin', text)
            if mode == 'normal':
                text, _ = observed(lambda rows: has(rows, generation, 'callback', 2), prefix + '-real-END')
                checkpoint(cycle, 'terminal', text)
            elif mode == 'abort':
                text, _ = observed(lambda rows: has(rows, generation, 'abort.called'), prefix + '-real-abort')
                checkpoint(cycle, 'terminal', text)
                for step, offset in enumerate((2, -2, 0), 1):
                    pointer.move([finish[0] + offset, finish[1]], prefix + '.abort.nudge.' + str(step))
                    time.sleep(0.2)
                time.sleep(1.5)
                text, _ = observed(lambda rows: has(rows, generation, 'abort.called'), prefix + '-held-abort-quiet')
                checkpoint(cycle, 'held-quiet', text)
            pointer.button(False, prefix + '.drag.release')
            text, _ = observed(lambda rows: has(rows, generation, 'drag.ended') and
                (mode != 'cancel' or has(rows, generation, 'callback', 3)), prefix + '-real-release')
            checkpoint(cycle, 'released', text)
            cycle['quiet'] = selected('spring-quiet', prefix + '-quiet', clickable=True)
            pointer.click(cycle['quiet']['node'], prefix + '.quiet')
            text, _ = observed(lambda rows: has(rows, generation, 'quiet.end'), prefix + '-cleanup-quiet')
            checkpoint(cycle, 'quiet', text)
        pointer.healthy('pointer-owner-after')
        # Caller binds the actual BMS identity in its strict verifier below.
        pointer.report.update(status='input_complete', pointer_released=not pointer.pressed,
                              run_id=run_id)
        return pointer.save(), text
    except Exception as error:
        pointer.report['failures'].append(type(error).__name__ + ': ' + str(error))
        raise
    finally:
        if pointer.pressed:
            try:
                pointer.button(False, 'failure.release-owned-pointer')
            except Exception as error:
                pointer.report['failures'].append('owned pointer cleanup failed: ' + str(error))
        pointer.report['pointer_released'] = not pointer.pressed
        pointer.save()


def checked_path(value, key):
    path = Path(value.get(key, ''))
    if (not path.is_absolute() or path.is_symlink() or not path.is_file() or
            digest(path) != value.get(key + '_sha256')):
        raise ValueError('actual spring pointer evidence missing or changed: ' + key)
    return path


def verify_actions(actions, raw_text, run_id, archive_sha, boot_id, arch, device, target):
    """Replay captured physical actions and raw prefix observations, not a pass flag."""
    if (actions.get('scope') != SCOPE or actions.get('status') != 'input_complete' or
            actions.get('run_id') != run_id or actions.get('archive_sha256') != archive_sha or
            actions.get('boot_id') != boot_id or actions.get('arch') != arch or
            actions.get('device') != device or actions.get('target') != target or
            actions.get('failures') != [] or actions.get('pointer_released') is not True or
            actions.get('first_artifact_behavior_gate_passed') is not False or
            actions.get('runner_sha256') != digest(Path(__file__))):
        raise ValueError('physical spring actions belong to another run/package/boot or did not clean up')
    boot = json.loads(checked_path(actions, 'boot').read_text())
    env, size = binding(boot, archive_sha, boot_id, arch, device, target)
    if actions.get('resolution') != size:
        raise ValueError('actual GPU resolution differs from physical input scaling')
    for label in ('pointer-owner-before', 'pointer-owner-after',
                  *(f'g{generation}-pointer-owner' for generation in range(1, 5))):
        require_process(checked_path(actions.get(label, {}), 'process').read_text(), env)
    requests = actions.get('requests')
    if not isinstance(requests, list) or len(requests) < 3:
        raise ValueError('actual QMP replies and owned pointer inputs required')
    previous = 0
    for row in requests:
        if (set(row) != {'execute', 'label', 'arguments', 'host_ns', 'completed_ns', 'reply'} or
                any(type(row[k]) is not int for k in ('host_ns', 'completed_ns')) or
                not previous < row['host_ns'] <= row['completed_ns']):
            raise ValueError('missing, failed or out-of-order actual QMP reply')
        previous = row['completed_ns']
    for row, name, label in zip(requests[:3], ('query-qmp-schema', 'query-mice', 'query-status'),
                               ('actual-schema', 'actual-absolute-pointer', 'actual-running-state')):
        if row['execute'] != name or row['label'] != label or row['arguments'] is not None:
            raise ValueError('actual QMP protocol/device setup missing')
    protocol(requests[0]['reply'], requests[1]['reply'])
    if requests[2]['reply'].get('running') is not True:
        raise ValueError('physical input did not use a running owned QEMU')
    cursor = 3
    previous_checkpoint = 0
    previous_prefix = ''

    def input_request(label, arguments):
        nonlocal cursor
        if cursor >= len(requests):
            raise ValueError('incomplete real pointer sequence')
        row = requests[cursor]
        cursor += 1
        if (row['execute'] != 'input-send-event' or row['label'] != label or
                row['arguments'] != arguments or row['reply'] != {}):
            raise ValueError('real pointer request/reply differs from actual selected node')
        return row

    def node(record, identifier, clickable=False):
        layout = json.loads(checked_path(record, 'layout').read_text())
        actual = select_node(layout, BUNDLE, identifier=identifier, clickable=clickable)
        if record.get('node') != actual:
            raise ValueError('spring action did not select the real ordinary-app node')
        center(actual, size)
        return actual

    def click(record, identifier, label):
        actual = node(record, identifier, clickable=True)
        input_request(label + '.move', move_arguments(center(actual, size), size))
        input_request(label + '.down', button_arguments(True))
        input_request(label + '.up', button_arguments(False))

    cycles = actions.get('cycles')
    if not isinstance(cycles, list) or len(cycles) != 4:
        raise ValueError('four actual input cycles including abort boundary re-entry required')
    for cycle, (generation, mode) in zip(cycles, ((1, 'normal'), (2, 'abort'), (3, 'normal'), (4, 'cancel'))):
        if (cycle.get('generation') != generation or type(cycle['generation']) is not int or
                cycle.get('mode') != mode):
            raise ValueError('actual physical drag modes or generations changed')
        prefix = 'g' + str(generation)
        checkpoints = cycle.get('checkpoints')
        names = ['ready', 'begin'] + ([] if mode == 'cancel' else ['terminal']) + (
            ['held-quiet'] if mode == 'abort' else []) + ['released', 'quiet']
        if not isinstance(checkpoints, list) or [row.get('name') for row in checkpoints] != names:
            raise ValueError('actual held, released and quiet observations are incomplete')
        checkpoint_index = 0

        def checkpoint(name):
            nonlocal checkpoint_index, previous_checkpoint, previous_prefix
            row = checkpoints[checkpoint_index]
            checkpoint_index += 1
            if (row['name'] != name or type(row.get('host_ns')) is not int or
                    not previous_checkpoint < row['host_ns'] or
                    type(row.get('request_count')) is not int or row['request_count'] != cursor or
                    row['host_ns'] < requests[cursor - 1]['completed_ns'] or
                    (cursor < len(requests) and row['host_ns'] >= requests[cursor]['host_ns'])):
                raise ValueError('actual callback checkpoint does not follow the corresponding physical input')
            text = checked_path(row, 'results').read_text()
            if not text.endswith('\n') or not text.startswith(previous_prefix) or not raw_text.startswith(text):
                raise ValueError('actual spring callback prefixes were removed, replaced or reordered')
            all_rows = [json.loads(line) for line in text.splitlines()]
            rows = [value for value in all_rows if value['generation'] == generation]
            previous_checkpoint, previous_prefix = row['host_ns'], text
            return row, rows

        click(cycle['selection'], 'spring-mode-' + mode, prefix + '.mode')
        _, rows = checkpoint('ready')
        if len(rows) != 1 or rows[0]['name'] != 'ready.' + str({'normal': 1, 'abort': 2, 'cancel': 3}[mode]):
            raise ValueError('drag was active before its actual mode selection')
        geometry = cycle['geometry']
        layout = json.loads(checked_path(geometry, 'layout').read_text())
        nodes = {key: select_node(layout, BUNDLE, identifier='spring-' + key) for key in ('source', 'target')}
        if nodes != geometry.get('nodes'):
            raise ValueError('drag source/target differ from actual same-layout geometry')
        from PIL import Image
        with Image.open(checked_path(geometry, 'screenshot')) as image:
            image.load()
            if image.format != 'PNG' or list(image.size) != size:
                raise ValueError('actual compositor is rotated/scaled relative to QMP coordinates')
        start, finish = (center(nodes[key], size) for key in ('source', 'target'))
        if start == finish or (nodes['source']['rect'][1] + nodes['source']['rect'][3] >= nodes['target']['rect'][1]):
            raise ValueError('physical source and target boundaries must be distinct')
        input_request(prefix + '.drag.source', move_arguments(start, size))
        press = input_request(prefix + '.drag.press', button_arguments(True))
        for step in range(1, 9):
            point = [a + (b - a) * step // 8 for a, b in zip(start, finish)]
            moved = input_request(prefix + '.drag.step.' + str(step), move_arguments(point, size))
            if step == 1 and moved['host_ns'] - press['completed_ns'] < 1_000_000_000:
                raise ValueError('real source long press was not held before crossing the target boundary')
        _, rows = checkpoint('begin')
        callbacks = [row for row in rows if row['name'] == 'callback']
        if not callbacks or callbacks[0]['state'] != 0 or (mode == 'cancel' and len(callbacks) != 1):
            raise ValueError('real BEGIN was not observed while the pointer was held inside the target')
        if mode != 'cancel':
            terminal, rows = checkpoint('terminal')
            if not any(row['name'] == ('abort.called' if mode == 'abort' else 'callback') and
                       row['state'] == (0 if mode == 'abort' else 2) for row in rows):
                raise ValueError('real native abort/END missing before physical release')
        if mode == 'abort':
            for step, offset in enumerate((2, -2, 0), 1):
                point = [finish[0] + offset, finish[1]]
                left, top, width, height = nodes['target']['rect']
                if not left < point[0] < left + width or not top < point[1] < top + height:
                    raise ValueError('abort suppression nudge must remain inside the same real target')
                input_request(prefix + '.abort.nudge.' + str(step), move_arguments(point, size))
            held, rows = checkpoint('held-quiet')
            if (held['host_ns'] - terminal['host_ns'] < 1_500_000_000 or
                    len([row for row in rows if row['name'] == 'callback']) != 1 or
                    any(row['name'] in ('drop', 'drag.ended') for row in rows)):
                raise ValueError('abort resumed/notified while the same physical drag was held and nudged')
        input_request(prefix + '.drag.release', button_arguments(False))
        _, rows = checkpoint('released')
        if not any(row['name'] == 'drag.ended' for row in rows) or (
                mode == 'cancel' and not any(row['name'] == 'callback' and row['state'] == 3 for row in rows)):
            raise ValueError('actual physical release and native cancellation missing')
        click(cycle['quiet'], 'spring-quiet', prefix + '.quiet')
        _, rows = checkpoint('quiet')
        if not rows or rows[-1]['name'] != 'quiet.end':
            raise ValueError('real ordinary-app cleanup quiet observation missing')
    if cursor != len(requests) or previous_prefix != raw_text:
        raise ValueError('extra/unreleased pointer actions or unobserved late native callbacks')
    return dict(physical_drag_cycles=4, held_abort_nudges=3, absolute_pointer=True,
                source_long_press_ms=1000, abort_held_quiet_ms_at_least=1500, pointer_released=True)
