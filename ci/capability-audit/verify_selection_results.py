"""Verify real copy contents, permission boundaries, recreation and painted selection."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from PIL import Image
from build_arkui_selection_probe import BUNDLE, CONTRACTS, PERMISSION, ROLES
from guest_ui import select_node, NodeNotReady
from selection_menu_runtime import menu_button

PHASES = ('initial', 'veto-selected', 'veto-copied', 'veto-deferred', 'veto-cleared',
          'allowed-selected', 'allowed-copied', 'allowed-deferred', 'allowed-cleared',
          'direct-selected', 'direct-copied', 'direct-deferred', 'direct-cleared', 'removed')


def clipboard(value):
    data = json.loads(value)
    if (set(data) != {'text', 'html', 'mimeTypes', 'records', 'textPresent', 'htmlPresent', 'mimeTypesPresent'} or
            type(data['text']) is not str or type(data['html']) is not str or
            type(data['records']) is not int or data['records'] < 0 or
            any(type(data[key]) is not bool for key in ('textPresent', 'htmlPresent', 'mimeTypesPresent')) or
            not isinstance(data['mimeTypes'], list) or any(type(item) is not str for item in data['mimeTypes'])):
        raise ValueError('malformed actual clipboard contents')
    return data


def rows(text, nonce, uid):
    if re.fullmatch('[0-9a-f]{32}', nonce or '') is None or type(uid) is not int or uid // 200000 != 100:
        raise ValueError('actual ordinary selection caller required')
    result = [json.loads(line) for line in text.splitlines() if line]
    allowed = {'permission.result', 'permission.state', 'identity', 'seed.completed', 'create.request',
               'modifier.selection', 'willCopy', 'copied', 'pasteboard.read', 'pasteboard.read.reject',
               'pasteboard.deferred.read', 'pasteboard.deferred.reject', 'clear.request',
               'pasteboard.sync.read', 'pasteboard.sync.reject', 'pasteboard.callback.read', 'pasteboard.callback.reject',
               'allow.request', 'join.request', 'remove.request'}
    for row in result:
        if (set(row) != {'runId', 'cycle', 'phase', 'name', 'values', 'data'} or row['runId'] != nonce or
                type(row['cycle']) is not int or row['cycle'] not in (0, 1) or
                type(row['phase']) is not int or row['phase'] not in (0, 1, 2) or row['name'] not in allowed or
                not isinstance(row['values'], list) or any(type(v) is not int for v in row['values']) or
                type(row['data']) is not str):
            raise ValueError('failed, foreign or malformed actual selection journal')
        values, name = row['values'], row['name']
        if name == 'identity':
            if len(values) != 3 or values[:2] != [uid, uid] or values[2] <= 0 or row['data'] != '':
                raise ValueError('selection process differs from its installed ordinary caller')
        elif name == 'modifier.selection':
            if values != [1, 1] or row['data'] != '':
                raise ValueError('selection typed reset or chain failed')
        elif name == 'willCopy':
            if values not in ([0], [1]): raise ValueError('selection copy veto malformed')
        elif name == 'permission.state':
            if values not in ([2], [0]) or row['data'] != '': raise ValueError('unexpected actual clipboard grant state')
        elif name == 'permission.result':
            if values != [0] or json.loads(row['data']) != [PERMISSION]: raise ValueError('actual user consent failed')
        elif name.endswith('.reject'):
            if values != [201] or not row['data']: raise ValueError('clipboard failed outside its permission boundary')
        elif values != [1]: raise ValueError('actual selection UI action failed')
        if name in ('seed.completed', 'pasteboard.read', 'pasteboard.deferred.read',
                    'pasteboard.sync.read', 'pasteboard.callback.read'): clipboard(row['data'])
    return result


class HtmlText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.paragraphs = 0
    def handle_data(self, value):
        if value: self.parts.append(value)
    def handle_starttag(self, tag, attrs):
        if tag == 'p': self.paragraphs += 1


def verify(text, nonce, uid, role):
    if role not in ROLES: raise ValueError('exact selection role required')
    observed = rows(text, nonce, uid)
    if not observed or [r['cycle'] for r in observed] != sorted(r['cycle'] for r in observed):
        raise ValueError('two ordered selection creation cycles required')
    consent = [r for r in observed if r['name'] == 'permission.result']
    if (role == 'reader' and (len(consent) != 1 or observed[0] != consent[0])) or (role != 'reader' and consent):
        raise ValueError('only the declared reader may obtain actual user consent')
    pids = []
    for cycle in (0, 1):
        events = [r for r in observed if r['cycle'] == cycle and r['name'] != 'permission.result']
        def one(name, phase=None):
            found = [(i, r) for i, r in enumerate(events) if r['name'] == name and (phase is None or r['phase'] == phase)]
            if len(found) != 1: raise ValueError('one actual selection event required: ' + name)
            return found[0]
        identity_index, ident = one('identity'); pids.append(ident['values'][2])
        permission_index, permission = one('permission.state')
        create_index, _ = one('create.request'); remove_index, _ = one('remove.request')
        if not (identity_index == 0 < permission_index < create_index < remove_index == len(events) - 1):
            raise ValueError('selection creation/removal ordering or late callbacks failed')
        if permission['values'] != ([0] if role == 'reader' else [2]):
            raise ValueError('actual selection permission boundary differs')
        seeds = [r for r in events if r['name'] == 'seed.completed']
        seed_text = nonce + ' seed:' + str(cycle)
        if role == 'reader':
            seed_index, seed = one('seed.completed')
            data = clipboard(seed['data'])
            if not (permission_index < seed_index < create_index and data['text'] == seed_text and
                    data['records'] == 1 and data['textPresent'] and data['mimeTypes'] == ['text/plain']):
                raise ValueError('real challenged seed clipboard not written/read before selection')
        elif seeds: raise ValueError('undeclared reader used the seeded privileged read flow')
        for phase in (0, 1, 2):
            first = create_index if phase == 0 else one('allow.request' if phase == 1 else 'join.request')[0]
            veto_index, veto = one('willCopy', phase)
            clear_index, _ = one('clear.request', phase)
            expected = nonce + ' alpha' + ('\n' if phase < 2 else '') + nonce + ' beta'
            if not first < veto_index < clear_index < remove_index or veto['values'] != ([0] if phase == 0 else [1]) or veto['data'] != expected:
                raise ValueError('actual veto or selected join-style contents differ')
            copied = [(i, r) for i, r in enumerate(events) if r['name'] == 'copied' and r['phase'] == phase]
            immediate = [(i, r) for i, r in enumerate(events) if r['name'] in ('pasteboard.read', 'pasteboard.read.reject') and r['phase'] == phase]
            if phase == 0:
                if copied or immediate: raise ValueError('vetoed selection still delivered a copy callback')
            elif len(copied) != 1 or copied[0][1]['data'] != expected or not veto_index < copied[0][0] < clear_index or len(immediate) != 1:
                raise ValueError('allowed selection copy callback or immediate read missing')
            deferred = [(i, r) for i, r in enumerate(events) if r['name'] in ('pasteboard.deferred.read', 'pasteboard.deferred.reject') and r['phase'] == phase]
            if len(deferred) != 1 or not veto_index < deferred[0][0] < clear_index:
                raise ValueError('deferred actual clipboard read missing')
            if role!='reader' and not deferred[0][1]['name'].endswith('.reject'):
                raise ValueError('undeclared clipboard reader did not reject with SDK error 201')
            forms = list(deferred)
            for form in ('sync','callback'):
                found = [(i,r) for i,r in enumerate(events) if r['name'] in (
                    'pasteboard.'+form+'.read','pasteboard.'+form+'.reject') and r['phase']==phase]
                if len(found)!=1 or not veto_index<found[0][0]<clear_index:
                    raise ValueError('actual '+form+' clipboard getter boundary missing')
                forms.extend(found)
            if role == 'reader':
                for _,result in forms:
                    if result['name'].endswith('.reject'): raise ValueError('authorized clipboard getter rejected')
                    data = clipboard(result['data'])
                    if data['text'] != (seed_text if phase == 0 else expected) or data['records'] != 1 or not data['textPresent']:
                        raise ValueError('veto changed the seed or copy did not reach the actual clipboard')
                    if phase:
                        parser = HtmlText(); parser.feed(data['html'])
                        if (set(data['mimeTypes']) != {'openharmony.styled-string', 'text/plain', 'text/html'} or
                                not data['htmlPresent'] or not data['mimeTypesPresent'] or
                                parser.parts != [nonce + ' alpha', nonce + ' beta'] or parser.paragraphs != (2 if phase == 1 else 1)):
                            raise ValueError('native styled-string, HTML or joined text clipboard records differ')
            else:
                for _, read in forms + immediate:
                    if not read['name'].endswith('.reject'):
                        raise ValueError('undeclared clipboard reader did not reject with SDK error 201')
        modifiers = [r for r in events if r['name'] == 'modifier.selection']
        if not modifiers or not any(r['phase'] == 0 for r in modifiers):
            raise ValueError('real imported factory modifier not executed on recreation')
    if pids[0] != pids[1]: raise ValueError('selection recreation changed caller process')
    return list(CONTRACTS)


def pixels(screenshot, layout, nonce, role, cycle, phase):
    with Image.open(screenshot) as source:
        if source.format != 'PNG': raise ValueError('real selection compositor PNG required')
        image = source.convert('RGB')
    nodes = [select_node(layout, BUNDLE, identifier='selection-ready'),
             select_node(layout, BUNDLE, identifier='selection-role'),
             select_node(layout, BUNDLE, identifier='selection-state')]
    if nodes[0]['attributes']['text'] != nonce or nodes[1]['attributes']['text'] != role or nodes[2]['attributes']['text'] != (
            ('removed ' if phase == 'removed' else 'active ') + nonce + ':' + str(cycle)):
        raise NodeNotReady('actual challenged selection state not presented')
    selected = phase not in ('initial', 'removed') and not phase.endswith('-cleared')
    if phase == 'removed':
        for name in ('selection-factory', 'selection-alpha', 'selection-beta', 'selection-read', 'selection-remove'):
            try: select_node(layout, BUNDLE, identifier=name)
            except NodeNotReady: continue
            raise ValueError('removed selection retained a visible child')
    else:
        select_node(layout, BUNDLE, identifier='selection-factory')
        for suffix in ('alpha', 'beta'):
            node = select_node(layout, BUNDLE, identifier='selection-' + suffix)
            if node['attributes']['text'] != nonce + ' ' + suffix: raise ValueError('foreign selection text')
            nodes.append(node)
    if phase.endswith('-selected'):
        menu_button(layout, BUNDLE, ('复制', 'Copy'))
    else:
        try: menu_button(layout, BUNDLE, ('复制', 'Copy'))
        except NodeNotReady: pass
        else: raise ValueError('cleared selection retained its native menu')
    fingerprint = []; metrics = []
    for index, node in enumerate(nodes):
        x, y, w, h = node['rect']
        if x + w > image.width or y + h > image.height: raise ValueError('selection compositor text off-screen')
        crop = image.crop((x, y, x + w, y + h)); colors = list(crop.get_flattened_data())
        dark = sum(max(c) < 110 for c in colors)
        highlight = sum(c == (255, 252, 211) for c in colors)
        if dark < 20: raise ValueError('actual selection text pixels not presented')
        if index >= 3 and ((selected and highlight < 100) or (not selected and highlight > 5)):
            raise ValueError('actual selected or cleared text background not presented')
        fingerprint.extend([str(node['rect']).encode(), crop.tobytes()])
        metrics.append(dict(rect=node['rect'],dark_pixels=dark,highlight_pixels=highlight))
    return metrics, b''.join(fingerprint)


def verify_presentations(phases, nonce, role):
    if set(phases) != {str(cycle) + ':' + phase for cycle in (0, 1) for phase in PHASES}:
        raise ValueError('all selection boundaries and both creations must be presented')
    for key, record in phases.items():
        cycle, phase = key.split(':'); presentation = record['presentation']; samples = presentation['samples']
        if presentation['status'] != 'pass_presentation_only' or len(samples) < 3:
            raise ValueError('three actual stable selection frames missing')
        fingerprints = []
        for sample in samples[-3:]:
            actual, fingerprint = pixels(sample['screenshot'],json.loads(Path(sample['layout']).read_text()),
                                         nonce,role,int(cycle),phase)
            if actual != sample['metrics']: raise ValueError('selection compositor metrics changed')
            fingerprints.append(fingerprint)
        if len(set(fingerprints)) != 1: raise ValueError('three consecutive identical selection presentations required')
    return True
