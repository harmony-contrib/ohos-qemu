"""Join a native AccessToken observation to an independently captured BMS identity.

BMS is the UID authority. Callers must bind its original guest command and raw
reply before passing its bundle, UID and accessTokenId here. The matching native
stdout must separately be bound to its exact command, arguments and exit frame.
HapTokenInfoParcel in the packaged native version does not transport UID.
"""
import json

IDENTITY_SCHEMA = 'hap-bms-access-token/v1'
HAP_IDENTITY_FIELDS = frozenset({
    'identity_schema', 'expected_uid', 'at_reported_uid', 'at_query_rc',
    'at_token_id', 'at_user_id', 'at_inst_index', 'at_bundle',
})


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate identity JSON key')
        result[key] = value
    return result


def strict_json(text):
    return json.loads(text, object_pairs_hook=unique_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite identity JSON')))


def bms_application_identity(text, bundle):
    """Read a single original ``bm dump -n BUNDLE`` body for account 100.

    The caller still binds this body to its exact successful guest command.
    Both BMS applicationInfo and the account-specific userInfo must agree.
    No application privilege or permission is inferred by this identity reader.
    """
    if type(text) is not str or type(bundle) is not str:
        raise ValueError('original BMS text and exact bundle required')
    begin = text.find('{')
    if begin < 0 or text[:begin].strip() != bundle + ':':
        raise ValueError('original BMS bundle header differs')
    decoder = json.JSONDecoder(object_pairs_hook=unique_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite BMS JSON')))
    document, end = decoder.raw_decode(text[begin:])
    if text[begin + end:].strip() or not isinstance(document, dict):
        raise ValueError('single complete BMS application record required')
    app = document.get('applicationInfo', {})
    if (not isinstance(app, dict) or document.get('name') != bundle or
            app.get('name') != bundle or app.get('bundleName') != bundle or
            type(document.get('appIndex')) is not int or document['appIndex'] != 0 or
            type(app.get('appIndex')) is not int or app['appIndex'] != 0):
        raise ValueError('exact original BMS bundle and instance required')
    uid, token_id = app.get('uid'), app.get('accessTokenId')
    if (type(uid) is not int or not 0 < uid < 2**31 or uid // 200000 != 100 or
            type(token_id) is not int or not 0 < token_id < 2**32):
        raise ValueError('original BMS UID/accessTokenId invalid')
    users = document.get('userInfo')
    if not isinstance(users, list) or any(not isinstance(row, dict) for row in users):
        raise ValueError('original BMS per-account identity missing')
    matches = [row for row in users if isinstance(row.get('bundleUserInfo'), dict) and
               type(row['bundleUserInfo'].get('userId')) is int and row['bundleUserInfo']['userId'] == 100]
    if (len(matches) != 1 or matches[0].get('bundleName') != bundle or
            type(matches[0].get('uid')) is not int or matches[0]['uid'] != uid or
            type(matches[0].get('accessTokenId')) is not int or matches[0]['accessTokenId'] != token_id):
        raise ValueError('BMS application and account-specific UID/token disagree')
    return dict(bundle=bundle, uid=uid, token_id=token_id, user_id=100, inst_index=0)


def verify_hap_token_identity(value, *, bundle, uid, token_id):
    """Validate the actual AT tuple against the original BMS application record.

    ``expected_uid`` is an argument echo, never an independently observed UID.
    ``at_reported_uid`` is preserved as a diagnostic, never used as UID authority.
    Lifecycle callers must also prove the original BMS identity stays unchanged
    after their operation; process UID checks remain separate and mandatory where
    required by the particular runtime protocol.
    """
    if (not isinstance(value, dict) or value.get('identity_schema') != IDENTITY_SCHEMA or
            not HAP_IDENTITY_FIELDS.issubset(value) or 'uid' in value):
        raise ValueError('explicit BMS/AccessToken identity schema required; legacy UID is ambiguous')
    if (type(bundle) is not str or not bundle or type(uid) is not int or
            not 0 < uid < 2**31 or uid // 200000 != 100 or
            type(token_id) is not int or not 0 < token_id < 2**32):
        raise ValueError('exact account-100 BMS bundle/UID/accessTokenId required')
    for key in ('expected_uid', 'at_reported_uid', 'at_query_rc', 'at_token_id',
                'at_user_id', 'at_inst_index', 'token_id'):
        if type(value.get(key)) is not int:
            raise ValueError('native token identity field is not an integer: ' + key)
    if not -(2**31) <= value['at_reported_uid'] < 2**31:
        raise ValueError('native HapTokenInfo UID diagnostic is outside int32')
    if (value.get('bundle') != bundle or value['expected_uid'] != uid or
            value['token_id'] != token_id or value['at_query_rc'] != 0 or
            value['at_token_id'] != token_id or value['at_user_id'] != 100 or
            value['at_inst_index'] != 0 or value['at_bundle'] != bundle):
        raise ValueError('actual AccessToken tuple does not match the original BMS identity')
