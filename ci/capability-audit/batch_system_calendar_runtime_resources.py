"""Bounded Calendar RestoolV2 label resolution from actual HAP and guest locale.

This is the en-US/zh-CN subset proved by the retained native parser sources,
not a general locale fallback engine. Unsupported configurations remain gaps.
Transport callers must bind locale and BMS to their exact marked guest commands.
"""
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

from batch_system_calendar_runtime_project import checked, record, require
import batch_system_calendar_runtime_protocol as protocol

# Retained only to identify the historical failing parameter probe; never accepted as public locale evidence.
LOCALE_SCRIPT = 'param get persist.sys.locale'
PUBLIC_LOCALE_SOURCE = 'validated_public_Calendar_observer_capture/v1'
PROVIDER = 'com.ohos.calendardata'
SOURCE_PINS = {
    'frameworks/resmgr/include/res_desc.h': '357a84269aec1b713348f70d95f2e95069215a8485b26f83b232f61f6319d8f8',
    'interfaces/inner_api/include/res_common.h': 'b06162663b248974e0eb0f8669883fc2b39a07298d309b2e465d74f2a20bf9a0',
    'frameworks/resmgr/src/hap_parser_v2.cpp': '224af48e624c692bae8cd046c37546f5fdc8056fabf73d82ee9d19e3a13935a0',
    'frameworks/resmgr/src/hap_resource_v2.cpp': '9440c9e89c1588f06aa0363171766e4ecf2089d0332f31d502de4262bc5898dc',
    'frameworks/resmgr/src/res_desc.cpp': '4eca51a1737743821734178053d8291634677fb9c12583034f35a0428f0dd41b',
    'frameworks/resmgr/src/res_config_impl.cpp': '6dc953db2b1c9a074bfa58859915799744235c10040d0a0270929311e08285bd',
    'frameworks/resmgr/src/locale_matcher.cpp': '783279bc1b4a8bf814a82e37b0cd8f2b6e8b77ba5ac5a7e87eda05bae8a46fe3',
    'frameworks/resmgr/src/likely_subtags_key_data.cpp': '795174c251feb84ca4b71da030d74a2e4f2818c44f42cb86ffefe6e42b611389',
    'frameworks/resmgr/src/likely_subtags_value_data.cpp': '518622a0480dfda21785634bece0abc0a8893b4811a3d05136e70b34d470c267',
}


def public_locales_equivalent(system_locale, resource_locale):
    """Compare only the existing four tokens and finite resource separator aliases."""
    if type(system_locale) is not str or type(resource_locale) is not str:
        return False
    resource_tokens = {
        'en-US': 'en-US', 'en_US': 'en-US',
        'en-Latn-US': 'en-Latn-US', 'en_Latn_US': 'en-Latn-US',
        'zh-CN': 'zh-CN', 'zh_CN': 'zh-CN',
        'zh-Hans-CN': 'zh-Hans-CN', 'zh_Hans_CN': 'zh-Hans-CN',
    }
    return system_locale in ('en-US', 'en-Latn-US', 'zh-CN', 'zh-Hans-CN') and \
        resource_tokens.get(resource_locale) == system_locale


def parse_label_index(data, resource_id, resource_name='app_name'):
    """Read actual V2 headers/IDs/configs, never scan for a plausible string.

    res_desc.h defines 140/12/16/12/12/12/8-byte structures. The native
    HapParserV2 methods and HapResourceV2::ParseLimitPaths join them by ID.
    Only language/region keys in the current Calendar resource set are covered.
    """
    require(isinstance(data, bytes) and 140 <= len(data) <= 16 * 1024 * 1024,
            'bounded actual compiled resource index required')
    require(type(resource_id) is int and 0 < resource_id < 2**32, 'actual integer resource ID required')
    version = b'RestoolV2 6.1.0.003'
    require(data[:128] == version + b'\0' * (128 - len(version)), 'unsupported resource index version/header')

    def ints(offset, count, limit=None):
        limit = len(data) if limit is None else limit
        require(type(offset) is int and 0 <= offset <= limit and count * 4 <= limit - offset,
                'resource structure offset outside actual bytes')
        return struct.unpack_from('<' + 'I' * count, data, offset)

    length, key_count, data_offset = ints(128, 3)
    require(length == len(data) and 1 <= key_count <= 32 and 140 < data_offset <= len(data) - 12,
            'resource header length/key count/data offset differs')
    offset = 140; configs = {}; qualifier_sets = set()
    for _ in range(key_count):
        require(data[offset:offset+4] == b'KEYS', 'resource KEYS tag missing')
        config_id, count = ints(offset+4, 2, data_offset); offset += 12
        require(config_id not in configs and 0 <= count <= 2, 'duplicate/unsupported resource configuration')
        qualifiers = {}
        for _ in range(count):
            kind, number = ints(offset, 2, data_offset); offset += 8
            require(kind in (0, 1) and kind not in qualifiers, 'unsupported/duplicate resource qualifier')
            # res_desc.cpp KeyParam::ConvertToStr reverses the four native
            # little-endian bytes and drops zero bytes for language/region.
            value = bytes(b for b in number.to_bytes(4, 'big') if b).decode('ascii')
            require(re.fullmatch('[a-z]{2}' if kind == 0 else '[A-Z]{2}', value), 'unsupported qualifier encoding')
            qualifiers[kind] = value
        canonical = tuple(sorted(qualifiers.items()))
        require(canonical in ((), ((0, 'en'), (1, 'US')), ((0, 'zh'), (1, 'CN'))) and canonical not in qualifier_sets,
                'unknown/ambiguous Calendar language configuration')
        qualifier_sets.add(canonical)
        configs[config_id] = {('language' if k == 0 else 'region'): v for k, v in qualifiers.items()}
    require(qualifier_sets == {(), ((0, 'en'), (1, 'US')), ((0, 'zh'), (1, 'CN'))},
            'current Calendar base/en_US/zh_CN configuration set required')
    ids_start = offset
    require(data[offset:offset+4] == b'IDSS', 'resource IDSS tag missing')
    ids_length, type_count, id_count = ints(offset+4, 3, data_offset); offset += 16
    require(ids_start + ids_length == data_offset and 1 <= type_count <= 32 and 1 <= id_count <= 10000,
            'resource IDSS length/count differs')
    items = {}; names = set(); types = set()
    for _ in range(type_count):
        start = offset; kind, type_length, count = ints(offset, 3, data_offset); offset += 12
        require(kind in (9, 14, 19, 20) and kind not in types and 1 <= count <= id_count,
                'unsupported/duplicate resource type')
        types.add(kind)
        for _ in range(count):
            item_id, item_offset, name_length = ints(offset, 3, data_offset); offset += 12
            require(1 <= name_length <= 256 and offset + name_length <= data_offset, 'resource name is outside IDSS')
            name = data[offset:offset+name_length].decode('utf-8'); offset += name_length
            require(re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,255}', name) and
                    item_id not in items and (kind, name) not in names, 'duplicate/invalid resource ID or type/name')
            items[item_id] = (kind, name, item_offset); names.add((kind, name))
        require(offset == start + type_length, 'resource type block length/count differs')
    require(offset == data_offset and len(items) == id_count, 'resource IDs do not exactly fill declared table')
    require(resource_id in items and items[resource_id][:2] == (9, resource_name), 'resource label ID is not STRING/app_name')
    require(data[data_offset:data_offset+4] == b'DATA', 'resource DATA tag missing')
    block_length, block_count = ints(data_offset+4, 2)
    pool = data_offset + block_length
    require(block_count == id_count and data_offset + 12 < pool <= len(data), 'resource DATA size/count differs')
    ranges = []; selected = None
    for item_id, (kind, name, pointer) in items.items():
        require(data_offset + 12 <= pointer < pool, 'resource record points outside DATA records')
        actual_id, record_length, count = ints(pointer, 3, pool)
        require(actual_id == item_id and 1 <= count <= key_count and record_length == 12 + 8 * count and
                pointer + record_length <= pool, 'resource value count/ID/length differs')
        ranges.append((pointer, pointer + record_length)); seen = set(); values = []
        for n in range(count):
            config_id, value_offset = ints(pointer + 12 + 8*n, 2, pool)
            require(config_id in configs and config_id not in seen and pool <= value_offset <= len(data) - 2,
                    'resource value config/offset missing, duplicate or outside string pool')
            seen.add(config_id)
            if item_id == resource_id:
                size = struct.unpack_from('<H', data, value_offset)[0]
                require(1 <= size <= 1024 and value_offset + 2 + size <= len(data), 'resource label string length outside pool')
                value = data[value_offset+2:value_offset+2+size].decode('utf-8')
                require(value.strip() == value and 0 < len(value) <= 256 and not value.startswith(('$', '@')) and
                        not any(ord(c) < 32 or ord(c) == 127 for c in value), 'resource label is empty/referenced/control text')
                values.append({'config_id': config_id, 'qualifiers': configs[config_id], 'value': value})
        if item_id == resource_id:
            require(seen == set(configs), 'label does not have all three actual locale configurations')
            selected = values
    cursor = data_offset + 12
    for begin, end in sorted(ranges):
        require(begin == cursor, 'overlapping/gapped resource value records')
        cursor = end
    require(cursor == pool, 'resource DATA contains unreferenced records')
    return {'resource_id': resource_id, 'type': 'STRING', 'name': resource_name,
            'configurations': sorted(selected, key=lambda x: x['config_id'])}


def resolve_provider_label(installed_hap, bms_text, locale_text):
    """Resolve only exact proven locales; callers separately bind raw transport."""
    import batch_apps_contact_picker_coordinator as signatures
    module, _ = signatures.hap_contents(installed_hap)
    bundle, app, remote = protocol.bms(bms_text, PROVIDER)
    require(app.get('isSystemApp') is True and app.get('appPrivilegeLevel') == 'system_core' and
            module['app'].get('bundleName') == PROVIDER, 'actual source Calendar identity required')
    label_id = app.get('labelId')
    require(app.get('label') == module['app'].get('label') == '$string:app_name' and
            type(label_id) is int and module['app'].get('labelId') == label_id,
            'BMS and actual installed module label resource differ')
    modules = [m for m in bundle.get('hapModuleInfos', []) if m.get('name') == 'entry' and m.get('hapPath') == remote]
    require(len(modules) == 1 and modules[0].get('labelId') == label_id and modules[0].get('label') == '$string:app_name',
            'unique BMS entry module label missing')
    abilities = [a for a in modules[0].get('abilityInfos', []) if a.get('name') == 'MainAbility']
    compiled = [a for a in module['module'].get('abilities', []) if a.get('name') == 'MainAbility']
    require(len(abilities) == len(compiled) == 1 and abilities[0].get('labelId') == compiled[0].get('labelId') == label_id and
            abilities[0].get('label') == compiled[0].get('label') == '$string:app_name', 'actual MainAbility label differs')
    require(isinstance(locale_text, str) and re.fullmatch(r'(en-US|en-Latn-US|zh-CN|zh-Hans-CN)\n?', locale_text),
            'unknown/ambiguous/unproven actual guest locale; preserve label gap')
    actual_locale = locale_text.removesuffix('\n')
    language, region = ('en', 'US') if actual_locale.startswith('en-') else ('zh', 'CN')
    # Native LocaleMatcher::Match permits base, excludes the other language;
    # IsMoreSuitable/CompareRegionWhenLangIsNotEqual prefers the matching
    # language+region here. likely_subtags arrays entries321/1385 establish
    # en-Latn-US / zh-Hans-CN when the raw locale omits its default script.
    with zipfile.ZipFile(installed_hap) as archive:
        index = archive.read('resources.index')
    parsed = parse_label_index(index, label_id)
    matched = [v for v in parsed['configurations'] if v['qualifiers'] == {'language': language, 'region': region}]
    require(len(matched) == 1, 'actual locale does not select one proven Calendar label')
    return {'identity': {'bundle': PROVIDER, 'uid': app['uid'], 'token_id': app['accessTokenId'], 'module': 'entry',
                        'ability': 'MainAbility', 'BMS_label': app['label'], 'label_id': label_id, 'installed_remote': remote},
            'resource_index': {'member': 'resources.index', 'sha256': hashlib.sha256(index).hexdigest(), 'bytes': len(index)},
            'resource': parsed, 'actual_locale': actual_locale, 'selected': matched[0]}


def public_locale_from_capture(locale, *, archive_sha256, boot_id, run_id):
    """Independently replay real public API output; never interpret a parameter error as a locale."""
    from batch_system_calendar_runtime_project import ROLES, load_challenge
    from batch_system_calendar_runtime_verify import validate_capture, operation
    capture = protocol.decode(checked(locale).read_text())
    require(capture.get('archive', {}).get('sha256') == archive_sha256 and
            capture.get('boot_id') == boot_id and capture.get('run_id') == run_id and
            capture.get('stage') == 'public-operation' and
            capture.get('request', {}).get('role') == 'observer' and
            capture['request'].get('action') == 'locale', 'actual same-run/boot/archive public observer locale capture required')
    verified = validate_capture(checked(locale), load_challenge(checked(capture['challenge'])), capture['archive'])
    rows = operation(verified)
    require([(r['event'], r['api']) for r in rows] == [
        ('begin', 'request'), ('system-locale', 'i18n.System.getSystemLocale'),
        ('resource-locale', 'ResourceManager.getConfiguration'), ('complete', 'request')] and
        all(r['error_code'] == 0 and r['error_message'] == '' for r in rows),
        'locale observation must contain only both public reads and complete; no permission or Calendar calls')
    values = [protocol.decode(r['value_json']) for r in rows[1:3]]
    require(all(isinstance(v, dict) and set(v) == {'locale'} and isinstance(v['locale'], str) for v in values),
            'both original public locale strings required')
    system_locale, resource_locale = [v['locale'] for v in values]
    require(public_locales_equivalent(system_locale, resource_locale),
            'unknown, conflicting or unsupported public system/resource locale; preserve label gap')
    return {'source': PUBLIC_LOCALE_SOURCE, 'observer_bundle': ROLES['observer']['bundle'], 'challenge': capture['challenge'],
            'uid': rows[0]['uid'], 'token_id': rows[0]['token_id'], 'operation_id': capture['request']['operation_id'],
            'system_api': rows[1]['api'], 'resource_api': rows[2]['api'], 'system_locale': system_locale,
            'resource_locale': resource_locale, 'timestamp_ms': rows[-1]['timestamp_ms']}


def require_fresh_public_locale(proof, realtime_ns):
    observed = proof['public_locale']['timestamp_ms']
    require(type(realtime_ns) is int and type(observed) is int and
            0 <= realtime_ns // 1_000_000 - observed <= 120000,
            'public locale observation is not fresh within two minutes; preserve dialog and refresh before launching provider')


def make_provider_label_proof(*, installed_hap, bms, locale, archive_sha256, boot_id, run_id):
    require(isinstance(archive_sha256, str) and re.fullmatch('[a-f0-9]{64}', archive_sha256) and
            isinstance(boot_id, str) and re.fullmatch('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', boot_id) and
            isinstance(run_id, str) and re.fullmatch('[a-f0-9]{32}', run_id), 'actual archive/boot/run label context required')
    checked(locale)
    public_locale = public_locale_from_capture(locale, archive_sha256=archive_sha256, boot_id=boot_id, run_id=run_id)
    value = resolve_provider_label(checked(installed_hap), checked(bms).read_text(), public_locale['system_locale'])
    return {'schema_version': 2, 'source': 'resource_index+public_i18n_and_resource_configuration', 'archive_sha256': archive_sha256,
            'boot_id': boot_id, 'run_id': run_id, 'installed_hap': installed_hap, 'bms': bms, 'locale': locale,
            'public_locale': public_locale, 'resolved': value, 'parser': record(Path(__file__)), 'native_source_pins': SOURCE_PINS,
            'transport_verified_by_caller': False, 'UI_requester_reviewed': False}


def verify_provider_label_proof(proof, *, installed_hap, bms, locale, archive_sha256, boot_id, run_id):
    expected = make_provider_label_proof(installed_hap=installed_hap, bms=bms, locale=locale,
                                       archive_sha256=archive_sha256, boot_id=boot_id, run_id=run_id)
    require(isinstance(proof, dict) and json.dumps(proof, sort_keys=True, ensure_ascii=False) ==
            json.dumps(expected, sort_keys=True, ensure_ascii=False), 'provider label resource/identity/locale/boot proof changed')
    return expected['resolved']['selected']['value']
