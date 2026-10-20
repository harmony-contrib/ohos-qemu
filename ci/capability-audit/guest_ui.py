#!/usr/bin/env python3
"""Use the packaged UITest CLI; select actual nodes, never guess coordinates.

This is test orchestration, not an accessibility or capability implementation.
No system binary replacement, permission grants or periodic wakeup is used.
"""
import json
from pathlib import Path
import re
import secrets
import shlex


def command_exit(text, marker):
    """Decode one command-bound, complete terminal footer; keep body echoes.

    Raw command logs retain their original bytes. Only CRLF is normalized here
    for text parsing; an embedded printf/nonce in a hilog line is not a footer.
    This is not a journal EOF or process-snapshot framing parser.
    """
    if (type(text) is not str or type(marker) is not str or
            re.fullmatch(r'__[A-Z][A-Z0-9_]*_EXIT_[a-f0-9]{32}__=', marker) is None):
        raise ValueError('exact command exit marker required')
    text = text.replace('\r\n', '\n')
    records = list(re.finditer(r'^' + re.escape(marker) + r'([0-9]+)$', text, re.M))
    if len(records) != 1:
        raise ValueError('one complete command exit record required')
    record = records[0]; digits = record.group(1)
    if (len(digits) > 3 or int(digits) > 255 or record.start() == 0 or
            text[record.start()-1] != '\n' or record.end()+1 != len(text) or text[-1] != '\n'):
        raise ValueError('complete command exit must end the raw stream')
    return text[:record.start()-1], int(digits)


class GuestUiCommandError(ValueError):
    def __init__(self, label, exit_code, output):
        super().__init__('packaged UITest operation failed or lost its guest exit status: ' + label)
        self.exit_code = exit_code
        self.output = output


class LayoutNotReady(ValueError):
    """Exact packaged UITest window-enumeration failure; never a valid layout."""


class NodeNotReady(ValueError):
    """Well-formed hierarchy has no matching node yet; duplicates remain fatal."""


def bounds(value):
    match = re.fullmatch(r'\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]', value or '')
    if not match:
        raise ValueError('UITest node has malformed bounds')
    left, top, right, bottom = map(int, match.groups())
    if min(left, top) < 0 or right <= left or bottom <= top or max(right, bottom) > 100000:
        raise ValueError('UITest node is off-screen, empty or has unreasonable bounds')
    return left, top, right - left, bottom - top


def select_node(layout, bundle, *, identifier=None, text=None, clickable=False):
    if not bundle or ((identifier is None) == (text is None)):
        raise ValueError('select exactly one actual id or text in a specified bundle')
    roots = layout if isinstance(layout, list) else [layout]
    pending = [(root, '', 0) for root in roots]
    selected = []
    count = 0
    while pending:
        node, inherited_bundle, depth = pending.pop()
        count += 1
        if count > 100000 or depth > 256 or not isinstance(node, dict):
            raise ValueError('malformed or excessive UITest hierarchy')
        attributes = node.get('attributes')
        children = node.get('children', [])
        if not isinstance(attributes, dict) or not isinstance(children, list):
            raise ValueError('UITest hierarchy must contain attributes and child nodes')
        actual_bundle = attributes.get('bundleName') or inherited_bundle
        key, expected = ('id', identifier) if identifier is not None else ('text', text)
        if actual_bundle == bundle and attributes.get(key) == expected:
            if attributes.get('visible') != 'true':
                raise ValueError('selected UITest node is not actually visible')
            if clickable and (attributes.get('enabled') != 'true' or attributes.get('clickable') != 'true'):
                raise ValueError('selected UITest node is not an enabled clickable control')
            selected.append({'attributes': attributes, 'bundle': actual_bundle,
                             'rect': list(bounds(attributes.get('bounds')))})
        pending.extend((child, actual_bundle, depth + 1) for child in children)
    if not selected:
        raise NodeNotReady('require exactly one matching visible node in the actual target bundle')
    if len(selected) != 1:
        raise ValueError('require exactly one matching visible node in the actual target bundle')
    return selected[0]


def swipe_down_points(start, end):
    """Actual left-half status-bar start and visible application destination."""
    sx, sy, sw, sh = start['rect']; ex, ey, ew, eh = end['rect']
    left, right = max(sx, ex), min(sx+sw//2, ex+ew)
    if right-left < 4 or ey+eh//2 <= sy+sh//2+max(sh, 18):
        raise ValueError('actual status-bar/Canvas geometry cannot open the notification drawer')
    x = left+(right-left)//2
    return [x, sy+sh//2, x, ey+eh//2]


class GuestUi:
    """Caller owns the VM and command evidence; each snapshot is nonce-scoped."""
    def __init__(self, command, hdc, target, output):
        self.command = command
        self.hdc = str(hdc)
        self.target = target
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.challenge = secrets.token_hex(16)
        self.sequence = 0

    def shell(self, script, label):
        marker = '__UITEST_EXIT_' + secrets.token_hex(16) + '__='
        result = self.command([self.hdc, '-t', self.target, 'shell',
            script + '; task_ui_rc=$?; printf "\\n' + marker + '%s\\n" "$task_ui_rc"'], label)
        try:
            body, code = command_exit(result, marker)
        except ValueError as error:
            raise GuestUiCommandError(label, None, result) from error
        if code != 0 or '[Fail]' in result:
            raise GuestUiCommandError(label, code, body.strip())
        return body.rstrip('\n')

    def remote(self, suffix):
        self.sequence += 1
        return '/data/local/tmp/qemu-capability-ui-' + self.challenge + '-' + str(self.sequence) + suffix

    def layout(self, *, bundle=None, label='layout'):
        remote = self.remote('.json')
        script = 'test ! -e ' + shlex.quote(remote) + ' && uitest dumpLayout -p ' + shlex.quote(remote)
        if bundle:
            script += ' -b ' + shlex.quote(bundle)
        try:
            self.shell(script, label + '-dump')
        except GuestUiCommandError as error:
            if error.exit_code == 1 and error.output == 'DumpLayout failed:Get window nodes failed':
                raise LayoutNotReady(error.output) from error
            raise
        text = self.shell('cat ' + shlex.quote(remote), label + '-read')
        layout = json.loads(text)
        local = self.output / (str(self.sequence).zfill(3) + '-' + label + '.json')
        local.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n')
        return layout, local

    def click(self, bundle, *, identifier=None, text=None, label='click'):
        layout, path = self.layout(bundle=bundle, label=label)
        node = select_node(layout, bundle, identifier=identifier, text=text, clickable=True)
        left, top, width, height = node['rect']
        self.shell('uitest uiInput click ' + str(left + width // 2) + ' ' + str(top + height // 2),
                   label + '-actual-node-center')
        return {'layout': str(path), 'selected_node': node}

    def swipe_down(self, bundle, *, identifier, swipe_to, label='swipe-down'):
        # A single unfiltered actual dump contains both windows. The end point
        # comes from the caller's visible Canvas, never a fixed screen size.
        layout, path = self.layout(label=label)
        node = select_node(layout, bundle, identifier=identifier)
        destination = select_node(layout, **swipe_to)
        points = swipe_down_points(node, destination)
        self.shell('uitest uiInput swipe ' + ' '.join(map(str, points)), label+'-actual-node-swipe')
        return {'layout': str(path), 'selected_node': node, 'destination_node': destination,
                'swipe_points': points}

    def screenshot(self, *, label='screen'):

        remote = self.remote('.png')
        self.shell('test ! -e ' + shlex.quote(remote) + ' && uitest screenCap -p ' + shlex.quote(remote),
                   label + '-compositor-capture')
        local = self.output / (str(self.sequence).zfill(3) + '-' + label + '.png')
        text = self.command([self.hdc, '-t', self.target, 'file', 'recv', remote, str(local)],
                            label + '-receive-compositor-capture')
        if '[Fail]' in text or not local.is_file():
            raise ValueError('actual compositor screenshot transfer failed')
        from PIL import Image
        with Image.open(local) as image:
            image.verify()
            if image.format != 'PNG' or min(image.size) < 100:
                raise ValueError('actual compositor screenshot is not a usable PNG')
        return local
