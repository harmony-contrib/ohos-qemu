"""Bounded presentation wait; preserve every actual failed capture attempt.

Native queue-present completion is not a compositor presentation fence. This
does not weaken pixel checks, synthesize frames or issue periodic wake input.
"""
import re
import time

from PIL import Image
from guest_ui import select_node
from verify_vulkan_window import PixelMismatch, verify_pixels


def presented_geometry(results, generation):
    if type(generation) is not int or generation not in (1, 2):
        raise ValueError('only the two actual surface generations are accepted')
    rows = results.splitlines()
    expected_events = ([('present', 0, 1)] if generation == 1 else
                       [('present', 0, 1), ('destroyed', 1, 1), ('present', 0, 2)])
    parsed = []
    pattern = re.compile(r'vulkan_window\.(present|destroyed)\|frames=5 width=(\d+) height=(\d+) '
                         r'cleaned=1 destroyed=(0|1) generation=(1|2)')
    for line in rows:
        match = pattern.fullmatch(line)
        if match is None:
            raise ValueError('actual Vulkan presentation stage contains a failure or malformed result')
        event, width, height, destroyed, actual_generation = match.groups()
        if min(int(width), int(height)) < 11:
            raise ValueError('actual native Vulkan surface is too small')
        parsed.append((event, int(destroyed), int(actual_generation), int(width), int(height)))
    if [(event, destroyed, actual_generation) for event, destroyed, actual_generation, _, _ in parsed] != expected_events:
        raise ValueError('Vulkan presentation generation/lifecycle is stale or incomplete')
    return {'width': parsed[-1][3], 'height': parsed[-1][4]}


def capture_presented_frame(ui, bundle, generation, results, attempts, checksum, *,
                            wait_seconds=60, clock=time.monotonic, sleep=time.sleep):
    if type(wait_seconds) is not int or not 1 <= wait_seconds <= 60:
        raise ValueError('presentation wait must be finite and at most 60 seconds')
    geometry = presented_geometry(results, generation)
    started = clock()
    deadline = started + wait_seconds
    while True:
        label = 'surface-' + str(generation) + '-attempt-' + str(len(attempts) + 1)
        layout, layout_path = ui.layout(bundle=bundle, label=label)
        surface = select_node(layout, bundle, identifier='qemu-vulkan-surface')
        if surface['rect'][2:] != [geometry['width'], geometry['height']]:
            raise ValueError('actual UITest and native Vulkan geometry differ')
        screenshot = ui.screenshot(label=label)
        row = {'generation': generation, 'layout': str(layout_path), 'layout_sha256': checksum(layout_path),
               'selected_node': surface, 'screenshot': str(screenshot), 'sha256': checksum(screenshot),
               'elapsed_seconds': clock() - started, 'status': 'fail'}
        attempts.append(row)
        with Image.open(screenshot) as picture:
            try:
                row['verified_rgba_pixels'] = verify_pixels(picture, tuple(surface['rect']), geometry)
            except PixelMismatch as error:
                row['failure'] = str(error)
            else:
                # Never accept a command which returned after the finite deadline.
                if clock() > deadline:
                    raise ValueError('actual compositor presentation exceeded its finite deadline')
                row['status'] = 'pass'
                return row
        remaining = deadline - clock()
        if remaining <= 0:
            raise ValueError('actual Vulkan compositor pixels did not match before the finite deadline')
        sleep(min(1, remaining))
