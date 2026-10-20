"""Independent replay of actual CA prompt, result, death and cleanup records."""
import hashlib
import re
from apps_ui578_contract import decode, journal, load_ref, require, returned
from guest_ui import NodeNotReady, select_node


def verify_ca(value, rows, records, plan):
    actual = rows['a']; item = value['certificate']
    if not item['supportsCA']:
        returned(actual, 'ca.uninstall.unsupported', 'unsupported-remove-ca', 29700004)
        return
    returned(actual, 'ca.invalid-uri', 'invalid-remove-ca', 401)
    consumed = returned(actual, 'ca.consume', 'read-ca')
    source = decode(load_ref(item['input']['input']))
    fingerprint = hashlib.sha256(bytes(consumed['bytes'])).hexdigest()
    require(fingerprint == source['der']['sha256'] and
            consumed['fingerprint'].replace(':', '').lower() == fingerprint,
            'actual certificate bytes and public fingerprint disagree')
    expected = {'ca.cancel': 'install-prompt', 'ca.install': 'install-prompt',
                'ca.remove.cancel': 'uninstall-prompt', 'ca.remove.death': 'uninstall-prompt',
                'ca.remove': 'uninstall-prompt'}
    observed = set()
    for entry in item['ca_visible']:
        operation, key = entry['operation'], entry['key']
        require((operation in expected and expected[operation] == key) or
                (operation == 'cleanup.ca' and key == 'uninstall-prompt'), 'unknown CA prompt dispatch')
        indexes = entry['commands']; require(len(indexes) >= 3, 'actual prompt/dump and immediate journal needed')
        dump, read = [records[i] for i in indexes[:2]]
        match = re.fullmatch(r'test ! -e (\S+) && uitest dumpLayout -p (\S+) -b com.ohos.certmanager', dump.get('script', ''))
        require(match and match[1] == match[2] and read.get('script') == 'cat ' + match[1],
                'actual CA hierarchy command differs')
        tree = decode(read['body']); selector = plan['actions'][key]
        require(len(selector) == 1 and tree == decode(load_ref(entry['layout'])) and
                select_node(tree, **selector[0]) == entry['node'], 'actual source CA prompt node differs')
        if key == 'uninstall-prompt':
            node = select_node(tree, 'com.ohos.certmanager', identifier='cert-uninstall-fingerprint')
            require(node['attributes']['text'].replace(':', '').lower() == fingerprint,
                    'the actual removal UI did not display this nonce certificate fingerprint')
        snapshots = [entry for entry in value['journal_reads'] if entry['role'] == 'a' and entry['command'] in indexes]
        require(snapshots and not any(row['operation'] == operation and row['event'].startswith('return.')
            for snapshot in snapshots for row in journal(records[snapshot['command']]['body'], value['run'], value['case'], 'a')),
            'actual callback settled before user decision')
        observed.add(operation)
    require(set(expected) <= observed, 'one actual CA lifecycle prompt was omitted')
    returned(actual, 'ca.remove.cancel', 'remove-ca', 29700002)
    require(returned(actual, 'ca.remove.cancel.read', 'read-ca') == consumed ==
            returned(actual, 'ca.after-death', 'read-ca'), 'cancel/death changed the actual trusted certificate')
    prior = [row for row in actual if row['operation'] == 'ca.remove.death' and row['event'] == 'call.remove-ca']
    after = [row for row in actual if row['operation'] == 'ca.after-death' and row['event'] == 'return.read-ca']
    require(len(prior) == len(after) == 1 and prior[0]['pid'] != after[0]['pid'] and
            not any(row['operation'] == 'ca.remove.death' and row['event'] == 'return.remove-ca' for row in actual),
            'actual pending CA removal caller generation boundary differs')
    require(len(item['ca_death_gone']) == 2, 'two actual full hierarchy teardown observations required')
    for entry in item['ca_death_gone']:
        require(len(entry['commands']) == 2, 'actual unfiltered teardown dump/read required')
        dump, read = [records[i] for i in entry['commands']]
        match = re.fullmatch(r'test ! -e (\S+) && uitest dumpLayout -p (\S+)', dump.get('script', ''))
        require(match and match[1] == match[2] and read.get('script') == 'cat ' + match[1],
                'filtered or failed hierarchy cannot prove actual CA teardown')
        tree = decode(read['body']); require(tree and tree == decode(load_ref(entry['layout'])), 'actual teardown raw differs')
        try:
            select_node(tree, 'com.ohos.certmanager', identifier='cert-uninstall-title')
        except NodeNotReady:
            pass
        else:
            raise ValueError('real CA removal modal survived caller death')
    require(returned(actual, 'ca.removed.read', 'read')['trusted'] == value['baseline']['trusted'],
            'real removal did not restore original trust inventory')
    recovered = returned(actual, 'cleanup.ca.recover', 'recover-ca')
    require(recovered == item['recovered_ca'] and set(recovered) == {'uri'}, 'finally nonce recovery is not the actual caller result')
    if recovered['uri']:
        require(recovered['uri'] == consumed['uri'] and 'cleanup.ca' in observed,
                'finally tried to remove a different certificate')
        returned(actual, 'cleanup.ca', 'remove-ca')
