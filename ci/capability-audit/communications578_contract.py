"""Fixed product boundary and finite cases; this file grants no capability pass."""
RTT_ON = ('onRttModifyInd', 'onRttErrCause', 'onReceiveRttMessage')
RTT_OFF = ('offRttModifyInd', 'offRttErrCause', 'offReceiveRttMessage')
RTT_OPS = ('startRtt', 'stopRtt', 'setRttCapability', 'sendRttMessage')
RTT = RTT_ON + RTT_OFF + RTT_OPS
OBSERVER = ('onCommunicationStateChange', 'offCommunicationStateChange')
IDS = tuple('arkts_export:@ohos.telephony.call:' + n for n in RTT) + tuple(
    'arkts_export:@ohos.telephony.observer:' + n for n in OBSERVER) + (
    'arkts_export:@ohos.bluetooth.connection:startPairOutOfBand',
    'behavior:bluetooth-state-transition-false-success', 'behavior:telephony-no-modem-or-sim')
BUNDLE = 'org.harmonycontrib.communications578'
PERMISSIONS = ('ohos.permission.GET_NETWORK_INFO', 'ohos.permission.GET_TELEPHONY_STATE',
    'ohos.permission.SET_TELEPHONY_STATE', 'ohos.permission.PLACE_CALL',
    'ohos.permission.SEND_MESSAGES', 'ohos.permission.SET_NETWORK_INFO',
    'ohos.permission.ACCESS_BLUETOOTH')
UNSUPPORTED_POSITIVE = {
    'RTT': 'No complete delivered modem/SIM/IMS peer or /dev/voice_proxy_rtt media protocol provider',
    'Bluetooth': 'No QEMU vendor ABI/controller and independent security OOB peer',
}
# These are independent wire bytes, never a public callback/registry call.
URC = {'one': b'\r\n+OHOS5A: 1\r\n', 'zero': b'\r\n+OHOS5A: 0\r\n',
       'invalid': b'\r\n+OHOS5A: 2\r\n\r\n+OHOS5A: 1x\r\n\r\n+OHOS5A: true\r\n'}
# OOB input addresses are syntactically valid negative-test DATA, never a discovered peer claim.
OOB_NEGATIVE_ADDRESS = '12:34:56:78:9A:BC'


def case(name, api='', form='callback', expect='return', **extra):
    return dict(case_id=name, action='invoke', api=api, form=form, expect=expect,
                slot=0, listener='a', call_id=2147483000, enabled=False,
                address=OOB_NEGATIVE_ADDRESS, wait_ms=2500, **extra)


def quiet(name, api='', stimulus=None):
    row = case(name, api); row.update(action='quiet', wait_ms=5000)
    if stimulus is not None: row['stimulus'] = stimulus
    return row


def plan(profile):
    rows = [dict(case_id='exports', action='exports', api='', expect='exports')]
    if profile == 'rtt':
        for api in RTT_ON:
            short = api.lower()
            for form in ('missing', 'null', 'nonfunction', 'extra'):
                rows.append(case(short + '-' + form, api, form, 401))
            rows.extend((case(short + '-a', api), case(short + '-duplicate', api),
                         dict(case(short + '-b', api), listener='b')))
        rows.append(quiet('registered-no-session'))
        for api in RTT_OFF:
            for form in ('null', 'nonfunction', 'extra'):
                rows.append(case(api.lower() + '-' + form, api, form, 401))
            for form in ('callback', 'callback', 'undefined', 'missing'):
                rows.append(case(api.lower() + '-' + form + '-' + str(len(rows)), api, form))
        for api in RTT_OPS:
            rows.append(case(api.lower() + '-wrong-type', api, 'wrong-type', 401))
            rows.append(case(api.lower() + '-no-session', api, expect='capability-local' if api == 'setRttCapability' else 'telephony-failure'))
        rows.append(dict(case('capability-restore-off', 'setRttCapability', expect='capability-local'), enabled=False))
        rows.insert(-1, dict(case('capability-local-on', 'setRttCapability', expect='capability-local'), enabled=True))
        rows.append(quiet('unregistered-no-session'))
    elif profile in ('rtt-denied', 'rtt-ordinary'):
        for api in RTT_OPS:
            rows.append(case(api.lower() + '-role', api, expect=201 if profile == 'rtt-denied' else 202))
        if profile == 'rtt-denied':
            for api in RTT_ON + RTT_OFF: rows.append(case(api.lower() + '-role', api, expect=201))
    elif profile == 'observer':
        for api in OBSERVER:
            for form in ('missing', 'undefined', 'null', 'nonfunction', 'extra', 'fraction-slot', 'negative-slot', 'large-slot'):
                rows.append(case(api.lower() + '-' + form, api, form, 401))
        rows += [case('on-a', OBSERVER[0], 'default-slot'), case('on-a-duplicate', OBSERVER[0], 'undefined-options'),
                 dict(case('on-b', OBSERVER[0]), listener='b'), dict(case('on-slot-one', OBSERVER[0]), listener='slot-one', slot=1),
                 quiet('invalid-urc', stimulus='invalid'), quiet('one-urc', stimulus='one'), quiet('zero-urc', stimulus='zero'),
                 case('off-a', OBSERVER[1]), quiet('one-after-off-a', stimulus='one'),
                 case('off-a-repeat', OBSERVER[1]), dict(case('off-b', OBSERVER[1]), listener='b'),
                 quiet('zero-after-off-all', stimulus='zero'),
                 dict(case('on-a-next-generation', OBSERVER[0]), listener='a2'), quiet('next-generation-cached-zero'),
                 quiet('one-next-generation', stimulus='one'),
                 dict(case('off-a-next-generation', OBSERVER[1]), listener='a2'),
                 dict(case('off-slot-one', OBSERVER[1]), listener='slot-one', slot=1), quiet('final-zero', stimulus='zero')]
    elif profile == 'observer-denied':
        rows += [case('on-denied', OBSERVER[0], expect=201), case('off-denied', OBSERVER[1], expect=201)]
    elif profile == 'bluetooth':
        rows.append(dict(case('bluetooth-consent'), action='consent'))
        rows += [case('disable-baseline', 'disableBluetooth', expect='bt-disable'), quiet('off-baseline', 'bluetooth-state')]
        for form in ('bad-address', 'bad-transport', 'missing-oob', 'short-confirmation', 'short-randomizer', 'extra-oob-arg'):
            rows.append(case('oob-' + form, 'startPairOutOfBand', form, 401))
        rows += [case('oob-p192-off', 'startPairOutOfBand', 'p192', 2900003),
                 case('oob-p256-off', 'startPairOutOfBand', 'p256', 2900003)]
        for i in range(2):
            enable = case('enable-' + str(i), 'enableBluetooth', expect='bt-enable')
            if i == 1: enable['restart_bluetooth'] = True
            rows += [enable, quiet('failed-enable-' + str(i), 'bluetooth-state'),
                     case('disable-' + str(i), 'disableBluetooth', expect='bt-disable'), quiet('final-off-' + str(i), 'bluetooth-state')]
    elif profile in ('bluetooth-denied', 'bluetooth-ordinary'):
        if profile == 'bluetooth-ordinary': rows.append(dict(case('bluetooth-consent'), action='consent'))
        rows += [case('oob-role', 'startPairOutOfBand', 'p256', 201 if profile == 'bluetooth-denied' else 202)]
    elif profile == 'no-modem':
        rows += [dict(case('no-modem-before'), action='identity'),
                 case('call-no-modem', 'dialCall', expect='telephony-failure'),
                 case('sms-no-modem', 'sendShortMessage', expect='sms-result'),
                 dict(quiet('sms-result-window'), wait_ms=30000),
                 case('data-policy-on', 'enableCellularData', expect='capability-local'),
                 dict(case('no-modem-policy-on'), action='identity'),
                 case('data-policy-off', 'disableCellularData', expect='capability-local'),
                 case('rtt-send-no-modem', 'sendRttMessage', expect='telephony-failure'),
                 case('rtt-start-no-modem', 'startRtt', expect='telephony-failure'),
                 dict(case('no-modem-after'), action='identity')]
    else:
        raise ValueError('Unknown fixed communications profile')
    rows += [dict(case('cleanup'), action='cleanup'), quiet('exit-quiet')]
    return rows

PROFILES = ('rtt', 'rtt-denied', 'rtt-ordinary', 'observer', 'observer-denied',
            'bluetooth', 'bluetooth-denied', 'bluetooth-ordinary', 'no-modem')
