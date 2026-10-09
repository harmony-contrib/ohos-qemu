"""Validate real display readback; never infer ordinary access or painted UI."""
import json


def verify(text):
    rows = [json.loads(line.split('QEMU_SCREEN_MODES:', 1)[1]) for line in text.splitlines()
            if 'QEMU_SCREEN_MODES:' in line]
    if len(rows) != 1 or rows[0].get('scope') != 'root_readonly_actual_display_service':
        raise ValueError('one actual read-only display service observation required')
    screens = rows[0].get('screens')
    if not isinstance(screens, list) or not screens:
        raise ValueError('actual screens required')
    ids = set()
    main = []
    for screen in screens:
        if not isinstance(screen, dict) or set(screen) != {'id', 'sourceMode', 'activeModeIndex', 'modes'}:
            raise ValueError('complete actual screen fields required')
        if (type(screen['id']) is not int or screen['id'] < 0 or screen['id'] in ids or
                type(screen['sourceMode']) is not int or screen['sourceMode'] not in range(5) or
                type(screen['activeModeIndex']) is not int or screen['activeModeIndex'] < 0):
            raise ValueError('valid distinct screen identity and active mode required')
        ids.add(screen['id'])
        modes = screen['modes']
        if not isinstance(modes, list) or not modes:
            raise ValueError('actual supported modes required')
        mode_ids = set()
        for mode in modes:
            if not isinstance(mode, dict) or set(mode) != {'id', 'width', 'height', 'refreshRate'}:
                raise ValueError('complete actual mode fields required')
            if (any(type(value) is not int for value in mode.values()) or mode['id'] < 0 or
                    min(mode['width'], mode['height'], mode['refreshRate']) <= 0 or mode['id'] in mode_ids):
                raise ValueError('valid distinct actual modes required')
            mode_ids.add(mode['id'])
        if screen['activeModeIndex'] >= len(modes):
            raise ValueError('active mode index is outside actual supported modes')
        if screen['sourceMode'] == 0:  # Actual pinned ScreenSourceMode::SCREEN_MAIN.
            main.append(screen)
    if len(main) != 1:
        raise ValueError('exactly one real main screen required')
    active = main[0]['modes'][main[0]['activeModeIndex']]
    return {'main_screen': main[0], 'active_mode': active, 'refresh_choices': [mode for mode in main[0]['modes']
            if (mode['width'], mode['height']) == (active['width'], active['height'])],
            'scope': 'root_readonly_modes_NOT_ordinary_permission_or_UI', 'closed': []}
