"""Bounded additional apps578 contracts. No Owner, subprocess or test entry point."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ASSETS = HERE / 'apps_ui578'
ROLES = ('normal', 'system-denied', 'a', 'b', 'account')
CASES = ('blink', 'notification-settings', 'notification-subscription', 'intelligent-scene',
         'certificate-dialog', 'accessibility-input', 'accessibility-settings',
         'network-policy', 'apn', 'shortkey', 'enterprise')
IDS = {
    'blink': ('arkts_export:@ohos.accessibility.config:startBlinking',
              'arkts_export:@ohos.accessibility.config:stopBlinking'),
    'notification-settings': ('behavior:notification-manager-settings-provider-missing-phone',),
    'notification-subscription': ('behavior:notification-extension-settings-entrypoint-missing',),
    'intelligent-scene': ('behavior:intelligent-scene-notification-query-fails',),
    'certificate-dialog': ('behavior:certificate-dialog-device-result',),
    'accessibility-input': ('behavior:accessibility-qemu-input-e2e',),
    'accessibility-settings': ('behavior:accessibility-settings-entrypoints-unavailable',),
    'network-policy': ('behavior:network-policy-settings-providers-missing',),
    'apn': ('behavior:telephony-apn-settings-provider-missing',),
    'shortkey': ('behavior:shortkey-empty-launch-config',),
    'enterprise': ('behavior:enterprise-provisioning-provider-missing',),
}
PERMISSIONS = {
    'blink': ('WRITE_ACCESSIBILITY_CONFIG', 'MANAGE_SECURE_SETTINGS'),
    'notification-settings': (), 'notification-subscription': ('SUBSCRIBE_NOTIFICATION',),
    'intelligent-scene': ('GET_DONOTDISTURB_STATE','ACCESS_SYSTEM_SETTINGS'),
    'certificate-dialog': ('ACCESS_CERT_MANAGER',),
    'accessibility-input': (),
    'accessibility-settings': ('READ_ACCESSIBILITY_CONFIG', 'WRITE_ACCESSIBILITY_CONFIG', 'MANAGE_SECURE_SETTINGS'),
    'network-policy': ('MANAGE_NET_STRATEGY',), 'apn': ('MANAGE_APN_SETTING',), 'shortkey': (),
    'enterprise': ('MANAGE_ENTERPRISE_DEVICE_ADMIN','START_PROVISIONING_MESSAGE'),
}
# UI-only aggregate protocols needing further implementation are never closed
# merely because this public API slice ran successfully.
SLICE_ONLY = {'accessibility-input', 'accessibility-settings', 'network-policy', 'apn', 'enterprise'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    p = Path(path)
    require(p.is_absolute() and p.is_file() and not p.is_symlink(), 'absolute regular raw input required')
    return hashlib.sha256(p.read_bytes()).hexdigest()


def decode(text):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            require(k not in out, 'duplicate apps578 JSON key')
            out[k] = v
        return out
    return json.loads(text, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite apps578 JSON')))


def nonce(value):
    require(isinstance(value, str) and re.fullmatch('[a-f0-9]{32}', value), 'fresh actual apps578 nonce required')
    return value


def bundle(role):
    require(role in ROLES, 'fixed apps578 caller role required')
    return 'org.harmonycontrib.appsui578.' + role.replace('-', '')


def permissions(kind, role):
    require(kind in CASES and role in ROLES, 'fixed case and role required')
    names = list(PERMISSIONS[kind]) if role in ('a', 'b', 'account') else []
    if role == 'account':
        require(kind == 'blink', 'account operator only belongs to the blink boundary')
        names += ['MANAGE_LOCAL_ACCOUNTS', 'INTERACT_ACROSS_LOCAL_ACCOUNTS_EXTENSION']
    return sorted('ohos.permission.' + x for x in names)


def json_ref(path):
    p = Path(path).resolve()
    return {'path': str(p), 'sha256': sha(p)}


def load_ref(ref):
    require(type(ref) is dict and set(ref) == {'path', 'sha256'} and sha(ref['path']) == ref['sha256'],
            'actual immutable descriptor changed')
    return Path(ref['path']).read_text()




def action_node(layout, selector):
    """Resolve one real source-related action; no guessed coordinate fallback."""
    from guest_ui import bounds, select_node
    if 'within_mode' in selector:
        from apps_ui578_followup_verify import mode_button
        return mode_button(layout, selector)
    plain={k:v for k,v in selector.items() if k in ('bundle','identifier','text')}
    anchor={'bundle':plain['bundle'],'text':selector['within_card']} if 'within_card' in selector else plain
    matched=select_node(layout,**anchor)
    if not selector.get('ancestor') and not selector.get('card_title') and 'within_card' not in selector and 'sibling_type' not in selector:
        return select_node(layout,**plain,clickable=True),matched
    roots=layout if isinstance(layout,list) else [layout]
    pending=[(root,'',[]) for root in roots];found=[];count=0
    key,expected=('id',anchor['identifier']) if 'identifier' in anchor else ('text',anchor['text'])
    while pending:
        node,inherited,parents=pending.pop();count+=1
        require(count<=100000 and len(parents)<=256 and isinstance(node,dict), 'bounded actual action hierarchy required')
        attrs=node.get('attributes');children=node.get('children',[])
        require(isinstance(attrs,dict) and isinstance(children,list), 'actual action node shape differs')
        owner=attrs.get('bundleName') or inherited
        if owner==plain['bundle'] and attrs.get(key)==expected and attrs.get('visible')=='true':
            found.append((node,owner,parents))
        pending.extend((child,owner,parents+[(node,owner)]) for child in children)
    require(len(found)==1,'one actual related action anchor required')
    node,owner,parents=found[0]
    if selector.get('card_title') or 'within_card' in selector:
        candidates=[]
        for parent,parent_owner in reversed(parents[-8:]):
            if parent_owner!=plain['bundle']:break
            titles=[(child,child['attributes'].get('bundleName') or parent_owner) for child in parent['children']
                if child['attributes'].get('type')=='Flex' and child['attributes'].get('visible')=='true' and
                child['attributes'].get('enabled')=='true' and child['attributes'].get('clickable')=='true']
            if len(titles)==1:
                if 'within_card' in selector:
                    queue=[(child,parent_owner) for child in parent['children']];candidates=[];visited=0
                    while queue:
                        child,owner=queue.pop();visited+=1
                        require(visited<=10000,'actual source notification card is excessive')
                        attrs=child['attributes'];owner=attrs.get('bundleName') or owner
                        if (owner==plain['bundle'] and attrs.get('text')==plain['text'] and
                            attrs.get('visible')=='true' and attrs.get('enabled')=='true' and attrs.get('clickable')=='true'):
                            candidates.append((child,owner))
                        queue.extend((item,owner) for item in child.get('children',[]))
                else:candidates=titles
                break
    elif selector.get('ancestor'):
        candidates=[]
        for parent,parent_owner in reversed(parents[-8:]):
            if parent_owner!=plain['bundle']:break
            attrs=parent['attributes']
            if attrs.get('visible')=='true' and attrs.get('enabled')=='true' and attrs.get('clickable')=='true':
                candidates=[(parent,parent_owner)];break
    else:
        require(parents,'actual sibling action requires a real source Row parent')
        parent,parent_owner=parents[-1]
        candidates=[(child,child['attributes'].get('bundleName') or parent_owner) for child in parent['children']
            if child['attributes'].get('type')==selector['sibling_type'] and
            child['attributes'].get('visible')=='true' and child['attributes'].get('enabled')=='true' and
            child['attributes'].get('clickable')=='true']
    require(len(candidates)==1 and candidates[0][1]==plain['bundle'], 'one enabled actual source-related action required')
    actual,owner=candidates[0];attrs=actual['attributes']
    return {'attributes':attrs,'bundle':owner,'rect':list(bounds(attrs.get('bounds')))},matched


def qmp_wire(row):
    """Replay complete original QemuGuest.qmp JSONL, including its handshake.

    The enclosing Owner must independently bind both Ref values to its real
    same-boot qmp_receipts. This parser never replaces those wire records with
    the convenience reply value or drops interleaved asynchronous events.
    """
    require(isinstance(row, dict) and
        {'execute', 'arguments', 'reply', 'request', 'response', 'boot_id'} <= set(row) and
        isinstance(row['execute'], str) and row['execute'] != 'qmp_capabilities' and
        isinstance(row['arguments'], dict), 'actual QMP observation framing differs')
    streams = []
    for key in ('request', 'response'):
        text = load_ref(row[key])
        require(text.endswith('\n') and len(text.encode()) <= 2**21,
            'bounded complete original QMP JSONL required')
        lines = text.splitlines()
        require(0 < len(lines) <= 10000 and all(lines), 'empty or unbounded QMP JSONL record')
        records = [decode(line) for line in lines]
        require(all(isinstance(item, dict) for item in records), 'QMP wire record must be an object')
        streams.append(records)
    sent, received = streams
    require(len(sent) == 2 and sent[0].get('id') == 'capabilities' and
        sent[0].get('execute') == 'qmp_capabilities' and sent[0].get('arguments', {}) == {} and
        set(sent[0]) <= {'id', 'execute', 'arguments'} and
        sent[1].get('id') == 'request' and sent[1].get('execute') == row['execute'] and
        sent[1].get('arguments', {}) == row['arguments'] and
        set(sent[1]) <= {'id', 'execute', 'arguments'},
        'original QMP capability/actual request sequence differs')
    require(len(received) >= 3 and set(received[0]) == {'QMP'} and
        isinstance(received[0]['QMP'], dict) and
        isinstance(received[0]['QMP'].get('version'), dict) and
        isinstance(received[0]['QMP'].get('capabilities'), list), 'actual QMP greeting missing')
    replies = []
    for response in received[1:]:
        if 'event' in response:
            require(isinstance(response['event'], str) and bool(response['event']) and
                not ({'id', 'return', 'error', 'QMP'} & set(response)),
                'malformed or response-shaped asynchronous QMP event')
            continue
        expected = 'capabilities' if len(replies) == 0 else 'request'
        require(len(replies) < 2 and response.get('id') == expected and
            'return' in response and 'error' not in response and 'QMP' not in response,
            'actual QMP capability/request failed, duplicated or out of order')
        replies.append(response)
    require(len(replies) == 2 and received[-1] is replies[-1] and
        replies[0]['return'] == {} and replies[1]['return'] == row['reply'],
        'actual QMP raw final reply differs from the observed request result')
    return {'requests': sent, 'responses': received}


def journal(text, run, kind, role):
    nonce(run)
    require(kind in CASES and role in ROLES and len(text.encode()) <= 2**20 and text.endswith('\n'),
            'bounded complete actual caller journal required')
    rows = [decode(s) for s in text.splitlines()]
    require(rows and len(rows) < 10000, 'nonempty bounded caller journal required')
    identity = None
    last = -1
    for i, row in enumerate(rows):
        require(set(row) == {'run','kind','role','bundle','uid','pid','seq','activeMs','operation','event','code','value'} and
            row['run'] == run and row['kind'] == kind and row['role'] == role and row['bundle'] == bundle(role) and
            type(row['uid']) is int and row['uid']//200000 == 100 and row['uid']%200000 >= 10000 and
            type(row['pid']) is int and row['pid'] > 1 and type(row['seq']) is int and row['seq'] == i and
            type(row['activeMs']) in (int, float) and row['activeMs'] >= last and
            isinstance(row['operation'], str) and re.fullmatch('[a-z][a-z0-9.-]{0,63}',row['operation']) and
            type(row['code']) is int and isinstance(row['event'],str) and len(row['event']) <= 128 and
            isinstance(row['value'],str) and len(row['value'].encode()) <= 262144,
            'actual caller nonce/identity/sequence/result framing differs')
        current = row['uid'], row['pid']
        require(identity is None or current == identity, 'PID generation changed within one raw journal')
        identity, last = current, row['activeMs']
        decode(row['value'])
    require(rows[0]['event'] == 'process.created' and rows[0]['operation'] == 'lifecycle',
            'real process creation observation missing')
    return rows


def returned(rows, operation, action, code=0):
    found = [r for r in rows if r['operation'] == operation and r['event'] == 'return.'+action]
    require(len(found) == 1 and found[0]['code'] == code, 'one exact real API return required: '+operation)
    calls = [r for r in rows if r['operation'] == operation and r['event'] == 'call.'+action]
    require(len(calls) == 1 and calls[0]['seq'] < found[0]['seq'], 'actual public call/return order differs')
    return decode(found[0]['value'])


def provider_boundary_classification(kind, proof, terminal_api):
    """Classify actual bounded provider declarations, never overall support.

    Nonzero `bm`/transport output alone is inconclusive. Only a complete actual
    installed bundle document can prove a missing literal extension here. The
    two known reusable-product gaps must never enter the unsupported bucket.
    """
    targets={'notification-subscription':('com.ohos.sceneboard','NotificationAccessGrantUIExtensionAbility',500),
        'network-policy':('com.huawei.hmos.communicationsetting','NetAccessPolicySettingUIExtension',500),
        'apn':('com.huawei.hmos.callsetting','GeneralCallSettingDialogAbility',301),
        'intelligent-scene':('com.ohos.intelligentscene','IntelligentSceneUIExtSettingAbility',500)}
    require(kind in targets and proof['schema']=='actual-apps578-provider-boundary/v1', 'fixed real provider boundary required')
    bundle_name,ability,extension_type=targets[kind]
    require(proof['bundle']==bundle_name and proof['ability']==ability, 'actual probe target differs from the original API')
    bms=proof['bms'];text=load_ref(bms['stdout_ref']);load_ref(bms['stderr_ref']);load_ref(bms['log'])
    require(isinstance(terminal_api,list) and terminal_api, 'actual public caller terminal observations required')
    result={'classification':'provider_probe_inconclusive','literal_target':{'bundle':bundle_name,'ability':ability,'type':extension_type},
        'formally_closed':[],'runtime_pass':False,'unsupported':False}
    if kind in ('network-policy','apn'):
        result['classification']='known_product_protocol_gap_observed'
        result['reason']='official applications_call business source exists; public target/Want/declaration adaptation remains required'
        return result
    if bms['exit_code']!=0 or bms['timed_out'] is not False or '{' not in text:
        result['reason']='bm/transport failure is not proof that the bundle is absent'
        return result
    try:
        doc=decode(text[text.index('{'):])
        require(isinstance(doc,dict) and {'applicationInfo','hapModuleInfos','extensionAbilityInfo'}<=set(doc) and
            doc['applicationInfo']['bundleName']==bundle_name and doc['applicationInfo']['isSystemApp'] is True and
            isinstance(doc['hapModuleInfos'],list) and doc['hapModuleInfos'] and
            isinstance(doc['extensionAbilityInfo'],list), 'complete actual installed provider declarations required')
        modules={m['moduleName'] for m in doc['hapModuleInfos']}
        require(all(isinstance(x,dict) and isinstance(x.get('name'),str) and type(x.get('type')) is int and
            type(x.get('visible')) is bool and x.get('moduleName') in modules for x in doc['extensionAbilityInfo']),
            'actual installed extension declarations are incomplete')
        matches=[x for x in doc['extensionAbilityInfo'] if x['name']==ability and x['type']==extension_type and x['visible']]
        if matches:
            result['classification']='provider_present_protocol_unverified'
            result['reason']='actual literal provider exists; a complete real UI business case must be supplied'
        else:
            actual=[x for x in terminal_api if x.get('role')=='a' and x.get('action') in ('invoke','read') and
                type(x.get('code')) is int]
            require(actual,'actual privileged public API terminal raw result missing')
            result['classification']='bounded_provider_absence_observed'
            result['reason']='complete actual installed bundle lacks the precise fixed-source public extension declaration; source scope still needs parent support adjudication'
    except (ValueError,KeyError,TypeError) as error:
        result['reason']='actual BMS declaration cannot prove absence: '+str(error)
    return result
