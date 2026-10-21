"""Finite source overlays for the root's original build/sign path; no tools."""
from pathlib import Path
import json
import re

ASSETS = Path(__file__).with_name('apps_providers579')
IDS = {
    'camera': ('behavior:camera-picker-entrypoint-missing-phone',),
    'photos': ('behavior:photo-provider-not-activated-2in1',),
    'photosform': ('behavior:photo-provider-not-activated-2in1',),
    'location': ('behavior:location-privacy-ui-providers-unavailable',),
    'cast': ('behavior:avcast-media-controller-provider-mismatch',),
    'volume': ('behavior:media-control-volume-provider-activation',),
    'input': ('behavior:phone-avinputcast-not-declared',),
    'dhardware': ('behavior:distributed-hardware-ui-preinstall-path-mismatch',),
    'vpn': ('behavior:vpn-dialog-provider-prefix-mismatch',),
    'wifi': ('behavior:wifi-system-ui-providers-not-activated',),
    'published': ('behavior:phone-published-capabilities-not-declared',),
    'exports': ('behavior:api26-runtime-export-mismatches-phone',),
    'imagegen': ('behavior:api26-runtime-export-mismatches-phone',),
    'ethernet': ('behavior:api26-runtime-export-mismatches-phone',),
    'sysvpn': ('behavior:api26-runtime-export-mismatches-phone',),
    'alwaysvpn': ('behavior:api26-runtime-export-mismatches-phone',)}
ROLES = {case: ('normal', 'grant', 'denied') for case in IDS}
ROLES.update(camera=('normal', 'foreign', 'janitor'), photos=('normal', 'foreign', 'janitor'),
             vpn=('allow', 'deny', 'cancel', 'foreign'), exports=('normal',))
DRIVERS = {'camera': 'Camera', 'photos': 'Photos', 'photosform': 'PhotoForm', 'location': 'Location',
    'cast': 'Cast', 'volume': 'Volume', 'input': 'Volume', 'dhardware': 'DHardware',
    'vpn': 'Vpn', 'wifi': 'Wifi', 'published': 'Published', 'exports': 'Matrix',
    'imagegen': 'ImageGeneration', 'ethernet': 'Ethernet', 'sysvpn': 'SysVpn', 'alwaysvpn': 'AlwaysVpn'}
ACTIONS = {
    'camera': ('identity', 'permissions', 'cleanup-owned', 'probe', 'photo', 'video', 'cancel-photo', 'cancel-video', 'read-ungranted', 'exit'),
    'photos': ('identity', 'permissions', 'cleanup-owned', 'recent-info', 'default-album', 'recent-component', 'hide-recent', 'create',
        'select', 'cancel-select', 'reload-owned-uri', 'read-denied', 'use-owned-fixture', 'delete', 'exit'),
    'photosform': ('identity', 'describe', 'boundaries', 'show', 'attach', 'publish', 'configure', 'observe', 'delete-form', 'exit'),
    'location': ('identity', 'snapshot', 'reset-own-fixture', 'enable', 'restore', 'exit'),
    'cast': ('identity', 'session-create', 'picker', 'picker-queue-off', 'picker-queue-off-on',
        'picker-off', 'picker-off-all', 'picker-off-on',
        'picker-on', 'picker-reselect', 'picker-release', 'discover', 'cast', 'stop-cast', 'cleanup', 'exit'),
    'volume': ('identity', 'observe', 'show-volume', 'hide-volume', 'volume-current', 'restore', 'exit'),
    'input': ('identity', 'permissions', 'observe', 'show-input', 'hide-input', 'capture-start', 'capture-stop', 'restore', 'exit'),
    'dhardware': ('identity', 'discover', 'authenticate', 'trusted', 'unbind', 'stop-discover', 'invalid-auth', 'exit'),
    'vpn': ('identity', 'authorize', 'stop-vpn', 'exit'),
    'wifi': ('identity', 'permissions', 'snapshot', 'sta-start', 'sta-state', 'sta-stop', 'networks', 'detect', 'ap-start', 'ap-state', 'ap-stop', 'restore', 'exit'),
    'published': ('identity', 'declarations', 'exit'), 'exports': ('identity', 'matrix-modern', 'matrix-legacy', 'exit'),
    'imagegen': ('identity', 'graph-open', 'graph-hide', 'graph-restore', 'graph-close',
        'dialog-open', 'dialog-hide', 'dialog-restore', 'dialog-close', 'boundaries', 'exit'),
    'ethernet': ('identity', 'snapshot', 'cycle', 'boundaries', 'restore', 'exit'),
    'sysvpn': ('identity', 'seed', 'verify-persisted', 'connected', 'boundaries', 'cleanup', 'exit'),
    'alwaysvpn': ('identity', 'seed', 'verify-persisted', 'boundaries', 'cleanup', 'exit')}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate(case, run_id, role=None, parameters=None):
    require(case in IDS and re.fullmatch('[a-f0-9]{32}', run_id or ''), 'fixed Apps579 case and fresh nonce required')
    require(role is None or role in ROLES[case], 'finite actual caller role required')
    if parameters is not None:
        require(type(parameters) is dict and parameters.get('profile') in ('phone', '2in1'), 'actual package profile required')


def bundle(case, role):
    require(case in ROLES and role in ROLES[case], 'fixed compiled caller required')
    return 'org.ohos.qemu.apps579.' + case + '.' + role


def permissions(case, role):
    if role == 'janitor':
        return ['ohos.permission.READ_IMAGEVIDEO', 'ohos.permission.WRITE_IMAGEVIDEO']
    if case == 'vpn':
        return ['ohos.permission.INTERNET']
    if role != 'grant':
        return []
    return {'photosform': ['ohos.permission.REQUIRE_FORM', 'ohos.permission.GET_BUNDLE_INFO_PRIVILEGED',
                           'ohos.permission.OBSERVE_FORM_RUNNING'],
        'location': ['ohos.permission.MANAGE_SECURE_SETTINGS'],
        'cast': ['ohos.permission.MANAGE_MEDIA_RESOURCES'],
        'volume': ['ohos.permission.MODIFY_AUDIO_SETTINGS'],
        'input': ['ohos.permission.MODIFY_AUDIO_SETTINGS', 'ohos.permission.MICROPHONE'],
        'dhardware': ['ohos.permission.DISTRIBUTED_DATASYNC'],
        'ethernet': ['ohos.permission.CONNECTIVITY_INTERNAL', 'ohos.permission.GET_NETWORK_INFO'],
        'sysvpn': ['ohos.permission.MANAGE_VPN'], 'alwaysvpn': ['ohos.permission.MANAGE_VPN'],
        'wifi': ['ohos.permission.INTERNET', 'ohos.permission.GET_NETWORK_INFO', 'ohos.permission.GET_WIFI_INFO', 'ohos.permission.SET_WIFI_INFO', 'ohos.permission.SET_WIFI_CONFIG',
                 'ohos.permission.GET_WIFI_CONFIG', 'ohos.permission.MANAGE_WIFI_CONNECTION',
                 'ohos.permission.MANAGE_WIFI_HOTSPOT', 'ohos.permission.LOCATION', 'ohos.permission.APPROXIMATELY_LOCATION']}.get(case, [])


def module_fields(case, role, parameters=None):
    request = []
    for permission in permissions(case, role):
        entry = {'name': permission}
        if permission in ('ohos.permission.READ_IMAGEVIDEO', 'ohos.permission.WRITE_IMAGEVIDEO', 'ohos.permission.MICROPHONE', 'ohos.permission.LOCATION', 'ohos.permission.APPROXIMATELY_LOCATION',
                          'ohos.permission.DISTRIBUTED_DATASYNC'):
            entry.update(reason='$string:apps579_permission', usedScene={'abilities': ['EntryAbility'], 'when': 'inuse'})
        request.append(entry)
    fields = {'requestPermissions': request}
    if parameters is not None:
        require(parameters.get('profile') in ('phone', '2in1'), 'actual package profile required')
        fields['deviceTypes'] = ['2in1'] if parameters['profile'] == '2in1' else ['default']
    if case == 'vpn':
        fields['extensionAbilities'] = [{'name': 'OwnedVpnExtension', 'srcEntry': './ets/common/VpnExtension.ets',
            'type': 'vpn', 'exported': False}]
    if case == 'alwaysvpn':
        fields['extensionAbilities'] = [{'name': 'OwnedPolicyVpnExtension', 'srcEntry': './ets/common/PolicyVpnExtension.ets',
            'type': 'vpn', 'exported': False}]
    return fields


def source_files(case, run_id, role, parameters=None):
    validate(case, run_id, role)
    if case == 'photosform':
        require(parameters is not None and parameters.get('profile') == '2in1', 'FormHost requires actual SDK 2in1 caller profile')
    replacements = {'__APPS579_RUN__': run_id, '__APPS579_CASE__': case,
        '__APPS579_ROLE__': role, '__APPS579_BUNDLE__': bundle(case, role)}
    names = {'Journal.ets': 'entry/src/main/ets/common/Journal.ets',
        'EntryAbility.ets': 'entry/src/main/ets/entryability/EntryAbility.ets',
        ('JanitorDriver.ets' if role == 'janitor' else DRIVERS[case] + 'Driver.ets'): 'entry/src/main/ets/common/Driver.ets',
        ('PhotoFormPage.ets' if case == 'photosform' else 'PhotosPage.ets' if case == 'photos' and role != 'janitor' else 'VolumePage.ets' if case in ('volume', 'input') else 'PlainPage.ets'):
            'entry/src/main/ets/pages/Index.ets'}
    if case in ('camera', 'photos'):
        names['MediaBytes.ets'] = 'entry/src/main/ets/common/MediaBytes.ets'
    if case == 'vpn':
        names['VpnExtension.ets'] = 'entry/src/main/ets/common/VpnExtension.ets'
    if case == 'sysvpn':
        names['SysVpnConfig.ets'] = 'entry/src/main/ets/common/SysVpnConfig.ets'
    if case == 'alwaysvpn':
        names['PolicyVpnExtension.ets'] = 'entry/src/main/ets/common/PolicyVpnExtension.ets'
    output = {}
    for name, destination in names.items():
        text = (ASSETS / name).read_text()
        for old, new in replacements.items():
            text = text.replace(old, new)
        output[destination] = text
    output['entry/src/main/resources/base/element/apps579.json'] = ('{"string":[{"name":"apps579_permission",'
        '"value":"Exercise the owned QEMU provider test and restore its state"}]}\n')
    output['AppScope/resources/base/element/string.json'] = json.dumps({'string': [{'name': 'app_name',
        'value': 'Apps579 ' + case + ' ' + role + ' ' + run_id[:8]}]}) + '\n'
    return output


def configure_profile(case):
    require(case in IDS, 'fixed case required')
    def configure(profile, role, udid, compiled):
        require(re.fullmatch('[a-fA-F0-9]{64}', udid or '') and role in ROLES[case], 'actual held guest UDID/role required')
        require(compiled['app']['bundleName'] == bundle(case, role), 'compiled exact bundle required')
        system = role in ('grant', 'denied', 'janitor')
        profile['bundle-info'].update({'bundle-name': bundle(case, role), 'apl': 'system_core' if system else 'normal',
                                      'app-feature': 'hos_system_app' if system else 'hos_normal_app'})
        profile['debug-info']['device-ids'] = [udid]
        profile['acls']['allowed-acls'] = permissions(case, role)
        profile['permissions']['restricted-permissions'] = permissions(case, role)
        return profile
    return configure
