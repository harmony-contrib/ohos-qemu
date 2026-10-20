"""Actual CA dialog cycle, using the original held guest and public caller."""
import hashlib
import time
from apps_ui578_contract import decode, json_ref, load_ref, require, returned
from guest_ui import LayoutNotReady, NodeNotReady, select_node


def observe(session, operation, uninstall=False):
    key = 'uninstall-prompt' if uninstall else 'install-prompt'
    selectors = session.plan['actions'][key]
    require(len(selectors) == 1, 'one source-backed actual certificate prompt anchor required')
    deadline = time.monotonic() + 25
    while True:
        try:
            start = len(session.value['commands'])
            tree, path = session.ui.layout(bundle='com.ohos.certmanager', label='actual_ca_prompt')
            node = select_node(tree, **selectors[0])
            if uninstall:
                displayed = select_node(tree, 'com.ohos.certmanager', identifier='cert-uninstall-fingerprint')
                fingerprint = displayed['attributes'].get('text', '').replace(':', '').lower()
                if not fingerprint: raise NodeNotReady('actual CA metadata is still loading')
                expected = decode(load_ref(session.value['certificate']['input']['input']))['der']['sha256']
                require(fingerprint == expected, 'actual removal prompt names a different certificate')
            current = session.rows('a')
            require(not any(row['operation'] == operation and row['event'].startswith('return.') for row in current),
                    'CA callback completed before the real user decision')
            session.value['certificate'].setdefault('ca_visible', []).append({
                'operation': operation, 'key': key, 'layout': json_ref(path), 'node': node,
                'commands': list(range(start, len(session.value['commands'])))})
            return
        except (LayoutNotReady, NodeNotReady):
            if time.monotonic() >= deadline: raise
            time.sleep(.15)


def result(session, operation, action, code=0):
    rows = session.wait('a', lambda items: any(row['operation'] == operation and
        row['event'] == 'return.' + action for row in items), 'actual_ca_result', seconds=45)
    return returned(rows, operation, action, code)


def gone(session):
    observations = []
    deadline = time.monotonic() + 25
    while len(observations) < 2:
        start = len(session.value['commands'])
        tree, path = session.ui.layout(label='actual_ca_modal_gone')
        try:
            select_node(tree, 'com.ohos.certmanager', identifier='cert-uninstall-title')
            observations = []
            require(time.monotonic() < deadline, 'actual uninstall modal survived its caller death')
        except NodeNotReady:
            observations.append({'layout': json_ref(path), 'commands': list(range(start, len(session.value['commands'])))})
        time.sleep(.15)
    session.value['certificate']['ca_death_gone'] = observations


def ca_cycle(session, baseline):
    if not baseline['supportsCA']:
        session.api('a', 'ca.unsupported', 'install-ca', 29700004)
        session.api('a', 'ca.uninstall.unsupported', 'unsupported-remove-ca', 29700004)
        return
    session.api('a', 'ca.invalid-uri', 'invalid-remove-ca', 401)
    session.invoke('a', 'ca.cancel', 'install-ca', wait=False)
    observe(session, 'ca.cancel'); session.system('cancel-install')
    result(session, 'ca.cancel', 'install-ca', 29700002)
    require(session.api('a', 'ca.after-cancel', 'read')['trusted'] == baseline['trusted'],
            'cancelled CA installation changed the original trusted inventory')
    session.invoke('a', 'ca.install', 'install-ca', wait=False)
    observe(session, 'ca.install'); session.system('confirm-install')
    uri = result(session, 'ca.install', 'install-ca')
    session.value['certificate']['ca_installed'] = True
    actual = session.api('a', 'ca.consume', 'read-ca')
    source = decode(load_ref(session.value['certificate']['input']['input']))
    require(uri == actual['uri'] and hashlib.sha256(bytes(actual['bytes'])).hexdigest() == source['der']['sha256'],
            'independent CA consumer did not read this exact nonce DER')
    session.invoke('a', 'ca.remove.cancel', 'remove-ca', wait=False)
    observe(session, 'ca.remove.cancel', True); session.system('cancel-uninstall')
    result(session, 'ca.remove.cancel', 'remove-ca', 29700002)
    require(session.api('a', 'ca.remove.cancel.read', 'read-ca') == actual,
            'cancelled CA removal changed the actual certificate')
    session.invoke('a', 'ca.remove.death', 'remove-ca', wait=False)
    observe(session, 'ca.remove.death', True)
    previous = session.stop('a'); gone(session)
    require(session.api('a', 'ca.after-death', 'read-ca') == actual and any(
        row['operation'] == 'ca.after-death' and row['pid'] != previous for row in session.rows('a')),
        'CA removal caller death/recreation changed or cached the actual certificate')
    session.invoke('a', 'ca.remove', 'remove-ca', wait=False)
    observe(session, 'ca.remove', True); session.system('confirm-uninstall')
    result(session, 'ca.remove', 'remove-ca')
    session.value['certificate']['ca_installed'] = False
    require(session.api('a', 'ca.removed.read', 'read')['trusted'] == baseline['trusted'],
            'real CA dialog did not restore exactly the original trusted inventory')


def cleanup_ca(session):
    item = session.value['certificate']
    if item.get('supportsCA') is not True or 'input' not in item:
        return
    # Close any actual pending user dialog first. This also handles the install
    # success page whose original Back handler returns its committed URI.
    session.system('cancel')
    recovered = session.api('a', 'cleanup.ca.recover', 'recover-ca')
    require(set(recovered) == {'uri'} and isinstance(recovered['uri'], str),
            'actual current inventory/nonce DER recovery required')
    item['recovered_ca'] = recovered
    if recovered['uri']:
        session.invoke('a', 'cleanup.ca', 'remove-ca', wait=False)
        observe(session, 'cleanup.ca', True); session.system('confirm-uninstall')
        result(session, 'cleanup.ca', 'remove-ca')
    item['ca_installed'] = False
