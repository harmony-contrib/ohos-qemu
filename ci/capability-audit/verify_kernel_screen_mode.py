"""Read actual DRM CRTC state; a display-service cached mode alone is insufficient."""
import re


def verify(text, expected):
    blocks = list(re.finditer(r'(?m)^(crtc|connector)\[(\d+)\]: ([^\n]+)\n((?:[ \t][^\n]*\n?)*)',
                             text.replace('\r', '')))
    active = []
    for block in blocks:
        if block[1] != 'crtc':
            continue
        lines = [line.strip() for line in block[4].splitlines()]
        if lines.count('enable=1') == 1 and lines.count('active=1') == 1:
            active.append((block, lines))
    if len(active) != 1:
        raise ValueError('exactly one enabled active QEMU DRM CRTC required')
    block, lines = active[0]
    modes = [line for line in lines if line.startswith('mode:')]
    pattern = r'mode: "([^"\n]+)":' + r'\s+(\d+)' * 10 + r'\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)'
    mode = re.fullmatch(pattern, modes[0]) if len(modes) == 1 else None
    if mode is None:
        raise ValueError('complete actual DRM timing record required')
    rate, clock, width, hstart, hend, htotal, height, vstart, vend, vtotal = map(int, mode.groups()[1:11])
    if (rate <= 0 or clock <= 0 or not 0 < width <= hstart <= hend <= htotal or
            not 0 < height <= vstart <= vend <= vtotal or
            (width, height, rate) != (expected['width'], expected['height'], expected['refreshRate'])):
        raise ValueError('kernel DRM mode differs from actual display service selection')
    attached = [connector for connector in blocks if connector[1] == 'connector' and
                ('crtc=' + block[3]) in [line.strip() for line in connector[4].splitlines()]]
    if len(attached) != 1:
        raise ValueError('one actual connector bound to the selected QEMU CRTC required')
    return dict(crtc_id=int(block[2]), crtc_name=block[3], connector_id=int(attached[0][2]),
                mode_name=mode[1], width=width, height=height, refreshRate=rate, pixel_clock_khz=clock,
                scope='kernel_DRM_readback_NOT_ordinary_permission_or_UI', closed=[])
