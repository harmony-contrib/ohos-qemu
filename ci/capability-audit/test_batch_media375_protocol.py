"""Synthetic protocol counterexamples; no SDK/native build, VM, PCM or permission changes."""
from argparse import Namespace
import copy
import json
import unittest

import batch_media375_protocol as p
import batch_media_audio_haptic_coordinator as c

RUN = 'a'*32
BOOT = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
BUNDLE = c.BUNDLES['owner']
UID, TOKEN = 20010000, 12345


def bms(uid=UID, token=TOKEN):
    return BUNDLE+':\n'+json.dumps(dict(name=BUNDLE, appIndex=0, uid=uid,
        applicationInfo=dict(name=BUNDLE, bundleName=BUNDLE, appIndex=0, uid=uid, accessTokenId=token,
            isSystemApp=False, appPrivilegeLevel='normal'),
        userInfo=[dict(bundleName=BUNDLE, uid=uid, accessTokenId=token, bundleUserInfo=dict(userId=100))]))


def native():
    return dict(protocol=p.PROTOCOL, kind='token', run_id=RUN, boot_id=BOOT, bundle=BUNDLE,
        token_id=TOKEN, permission='ohos.permission.VIBRATE', before=0, after=0, before_ns=10, after_ns=11,
        identity_schema='hap-bms-access-token/v1', expected_uid=UID, at_reported_uid=0,
        at_query_rc=0, at_token_id=TOKEN, at_user_id=100, at_inst_index=0, at_bundle=BUNDLE)


def time_rows():
    common = dict(protocol=p.PROTOCOL, run_id=RUN, boot_id=BOOT)
    rows = [dict(common, kind='begin', pid=320, uid=0, duration_ms=900000, period_ms=10,
        device_id=0, vibrator_id=0, before_ns=1, after_ns=2, result=0,
        time_delay=True, hd_haptic=False, preset_mapping=False)]
    for index, running in enumerate((False, True, False), 1):
        rows.append(dict(common, kind='sample', sequence=index, before_ns=index*10000000,
            after_ns=index*10000000+10, realtime_ns=1000000000+index*10000000+5,
            result=0, running=running))
    rows.append(dict(common, kind='complete', samples=3, owner_stop=True))
    return rows


def dump(rows):
    return ''.join(json.dumps(row)+'\n' for row in rows)


class Media375ProtocolTests(unittest.TestCase):
    def test_independent_BMS_uid_and_AT_tuple(self):
        identity = p.bms_identity(bms(), BUNDLE)
        value = p.actual_token(json.dumps(native()), run=RUN, boot=BOOT, bundle=BUNDLE,
            identity=identity, permission='ohos.permission.VIBRATE', expected=0)
        self.assertEqual(value['at_reported_uid'], 0)

    def test_legacy_uid_echo_cannot_be_authority(self):
        for key, wrong in [('uid', UID), ('expected_uid', UID+1), ('at_query_rc', -1),
            ('at_token_id', TOKEN+1), ('at_user_id', 101), ('at_inst_index', 1), ('boot_id', 'c'*36),
            ('before', False), ('after_ns', 9), ('at_reported_uid', False)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.actual_token(json.dumps(dict(native(), **{key:wrong})), run=RUN, boot=BOOT,
                    bundle=BUNDLE, identity=p.bms_identity(bms(), BUNDLE), permission='ohos.permission.VIBRATE', expected=0)

    def test_actual_BMS_command_order_and_reinstall_are_checked(self):
        refs = {key:dict(path=key, sha256=key) for key in ('before', 'token', 'after')}
        data = dict(before=bms(), token=json.dumps(native()), after=bms())
        scripts = dict(before='bm dump -n '+BUNDLE, after='bm dump -n '+BUNDLE,
            token=p.token_script('/data/local/tmp/audio-haptic-'+RUN, RUN, BOOT, BUNDLE, UID, 'ohos.permission.VIBRATE'))
        indexes = dict(before=1, token=2, after=3)
        item = dict(role='owner', permission='ohos.permission.VIBRATE', bms_before=refs['before'],
            raw=refs['token'], bms_after=refs['after'], value=native())
        def observed(ref, script):
            self.assertEqual(script, scripts[ref['path']]); return data[ref['path']]
        def check():
            return p.verify_token_binding(item, run=RUN, boot=BOOT, role='owner', bundle=BUNDLE,
                identity=p.bms_identity(bms(), BUNDLE), permission='ohos.permission.VIBRATE', expected=0,
                observed=observed, command_index=lambda ref:indexes[ref['path']])
        check()
        data['after'] = bms(token=TOKEN+1)
        with self.assertRaisesRegex(ValueError, 'BMS identity changed'): check()
        data['after'] = bms(); indexes['after'] = 1
        with self.assertRaisesRegex(ValueError, 'bracket'): check()

    def test_mismatched_BMS_account_token_and_privileged_apps_fail(self):
        for mutation in (lambda d:d['userInfo'][0].update(accessTokenId=TOKEN+1),
            lambda d:d['applicationInfo'].update(isSystemApp=True),
            lambda d:d['applicationInfo'].update(appPrivilegeLevel='system_basic'),
            lambda d:d['applicationInfo'].update(appIndex=1)):
            data = json.loads(bms().split('\n', 1)[1]); mutation(data)
            with self.assertRaises(ValueError): p.bms_identity(BUNDLE+':\n'+json.dumps(data), BUNDLE)

    def test_TIME_owner_stop_and_real_dual_clocks(self):
        samples = p.parse_time(dump(time_rows()), RUN, BOOT, 0)
        self.assertEqual([row['running'] for row in samples], [False, True, False])

    def test_TIME_old_schema_or_clock_identity_cannot_mix(self):
        for index, key, wrong in [(0, 'protocol', 'old'), (1, 'boot_id', 'c'*36), (2, 'sequence', 1),
            (2, 'running', 1), (2, 'result', -1), (2, 'before_ns', 1),
            (2, 'realtime_ns', 1), (2, 'realtime_ns', 10**18), (-1, 'owner_stop', False),
            (-1, 'samples', 4), (0, 'time_delay', False), (0, 'uid', False)]:
            data = time_rows(); data[index][key] = wrong
            with self.subTest(key=key, wrong=wrong), self.assertRaises(ValueError):
                p.parse_time(dump(data), RUN, BOOT, 0)
        with self.assertRaises(ValueError): p.parse_time(dump(time_rows()), RUN, BOOT, 1)

    def test_TIME_duplicate_or_truncated_records_fail(self):
        with self.assertRaises(ValueError): p.parse_time(dump(time_rows())[:-1], RUN, BOOT, 0)
        raw = dump(time_rows()).replace('"owner_stop": true', '"owner_stop": true, "owner_stop": true')
        with self.assertRaises(ValueError): p.parse_time(raw, RUN, BOOT, 0)

    def test_native_failure_cannot_hide_behind_HDC_zero_exit(self):
        marker = '__HAPTIC375_EXIT_'+'c'*32+'__='
        p.parse_time_transport(dump(time_rows())+'\n'+marker+'0\n', RUN, BOOT, 0, marker)
        for status in ('1', '-1', 'false'):
            with self.subTest(status=status), self.assertRaises(ValueError):
                p.parse_time_transport(dump(time_rows())+'\n'+marker+status+'\n', RUN, BOOT, 0, marker)
        with self.assertRaises(ValueError):
            p.parse_time_transport(dump(time_rows()), RUN, BOOT, 0, marker)

    def test_root_admission_has_no_boolean_or_missing_lease_fallback(self):
        with self.assertRaisesRegex(ValueError, 'explicit same-parent live root lease'):
            c.root_admission(Namespace(root_lease=None, root_lease_nonce=None, root_config=None,
                root_output=None, authorized=True))

    def test_native_observers_have_no_mutations_and_no_uid_assertion(self):
        self.assertNotIn('info.uid!=', p.TOKEN_SOURCE)
        self.assertIn('info.uid,queried', p.TOKEN_SOURCE)
        self.assertIn('CLOCK_REALTIME', p.PASSIVE_SOURCE)
        self.assertIn('sampler-stop', p.PASSIVE_SOURCE)
        for forbidden in ('GrantPermission', 'RevokePermission', 'StartVibrator', 'StopVibrator', 'clock_settime'):
            self.assertNotIn(forbidden, p.TOKEN_SOURCE+p.PASSIVE_SOURCE)

    def test_token_script_rejects_cross_run_and_shell_injection(self):
        for bundle in (BUNDLE+';id', 'com.ohos.settings'):
            with self.assertRaises(ValueError):
                p.token_script('/data/local/tmp/audio-haptic-'+RUN, RUN, BOOT, bundle, UID, 'ohos.permission.VIBRATE')
        with self.assertRaises(ValueError):
            p.token_script('/data/local/tmp/audio-haptic-'+'b'*32, RUN, BOOT, BUNDLE, UID, 'ohos.permission.VIBRATE')

    def test_passive_command_binds_boot_stop_path_and_native_exit(self):
        remote = '/data/local/tmp/audio-haptic-'+RUN
        marker = '__HAPTIC375_EXIT_'+'c'*32+'__='
        command = p.observer_script(remote, RUN, BOOT, marker)
        self.assertIn(remote+'/passive '+RUN+' '+BOOT+' 900000 10 '+remote+'/sampler-stop', command)
        self.assertIn('task_haptic_rc=$?', command)
        self.assertIn(marker, command)
        for wrong in ('/data/local/tmp/shared', remote+';id'):
            with self.assertRaises(ValueError): p.observer_script(wrong, RUN, BOOT, marker)


if __name__ == '__main__':
    unittest.main()
