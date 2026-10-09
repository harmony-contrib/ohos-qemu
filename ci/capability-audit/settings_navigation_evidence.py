"""Bind embedded Settings UI to the real AMS provider and host process records."""
import re

from guest_ui import bounds

SETTINGS = 'com.ohos.settings'
CALLER = 'org.harmonycontrib.capabilityaudit'
ABILITY = 'ExternalCommonUIExtensionAbility'


def provider_binding(dump, settings_uid, caller_uid):
    if (type(settings_uid) is not int or type(caller_uid) is not int or
            settings_uid == caller_uid or settings_uid // 200000 != 100 or caller_uid // 200000 != 100):
        raise ValueError('distinct actual account-100 provider and ordinary caller identities required')
    records = re.split(r'(?=^    uri \[)', dump, flags=re.M)
    candidates = []
    for record in records:
        if re.match(r'    uri \[/com\.ohos\.settings/phone/ExternalCommonUIExtensionAbility[0-9]+\]', record):
            record = re.split(r'^ {2,4}(?:PendingWantRecords|AppRunningRecords):', record, flags=re.M)[0]
            if (f'main name [{ABILITY}]' in record and f'bundle name [{SETTINGS}]' in record and
                    'ability type [UIEXTENSION]' in record and
                    f'root host bundle name [{CALLER}]' in record and
                    'root host module name [entry]' in record and 'root host ability name [EntryAbility]' in record and
                    re.search(r'AbilityRecord ID #\d+\s+state #(FOREGROUND|ACTIVE)\b', record) and
                    'app state #FOREGROUND' in record):
                match = re.search(r'^      pid: ([1-9][0-9]*)$', record, re.M)
                if match:
                    candidates.append(int(match.group(1)))
    if len(candidates) != 1:
        raise ValueError('one live foreground Settings extension for the actual caller required')
    provider_pid = candidates[0]
    apps = re.split(r'(?=^    AppRunningRecord ID #)', dump, flags=re.M)
    providers, hosts = [], []
    for app in apps:
        identity = re.search(r'^      pid #([1-9][0-9]*)  uid #([1-9][0-9]*)$', app, re.M)
        if not identity:
            continue
        pid, uid = map(int, identity.groups())
        if (pid == provider_pid and uid == settings_uid and 'state #FOREGROUND' in app and
                re.search(r'^      process name \[com\.ohos\.settings:ExternalCommonUIExtensionAbility:[0-9]+\]$', app, re.M)):
            providers.append(app)
        if (uid == caller_uid and f'process name [{CALLER}]' in app and 'state #FOREGROUND' in app and
                re.search(r'uiextension provider #\d+\s+pid #' + str(provider_pid) + r'\b', app)):
            hosts.append(pid)
    if len(providers) != 1 or len(hosts) != 1 or not re.search(
            r'root caller #\d+\s+pid #' + str(hosts[0]) + r'\b', providers[0]):
        raise ValueError('reciprocal AMS provider/host PID and UID binding required')
    return {'provider_pid': provider_pid, 'provider_uid': settings_uid,
            'host_pid': hosts[0], 'host_uid': caller_uid, 'provider_bundle': SETTINGS, 'host_bundle': CALLER}


def embedded_title(layout, text):
    pending = [(layout, '', False)]
    selected = []
    count = 0
    while pending:
        node, inherited_bundle, in_extension = pending.pop()
        count += 1
        if count > 100000 or not isinstance(node, dict):
            raise ValueError('invalid or excessive UI tree')
        attributes, children = node.get('attributes'), node.get('children', [])
        if not isinstance(attributes, dict) or not isinstance(children, list):
            raise ValueError('invalid UI node')
        bundle = attributes.get('bundleName') or inherited_bundle
        in_extension = in_extension or (bundle == CALLER and attributes.get('type') == 'UIExtensionComponent'
                                       and attributes.get('visible') == 'true')
        if (bundle == CALLER and in_extension and attributes.get('type') == 'TitleBar' and
                attributes.get('text') == text and attributes.get('visible') == 'true'):
            selected.append({'attributes': attributes, 'host_bundle': bundle,
                             'rect': list(bounds(attributes.get('bounds')))})
        pending.extend((child, bundle, in_extension) for child in children)
    if len(selected) != 1:
        raise ValueError('one visible Settings title inside the host UIExtension subtree required')
    return selected[0]
