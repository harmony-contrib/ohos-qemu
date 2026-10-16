"""Actual dump-format and notification selector mutation fixtures; no guest pass."""
import copy
import unittest

import audio_focus_observation as O

UID, PID, BUNDLE = 20010001, 345, O.BUNDLES[0]


def service_text():
    own = {'abilityName': 'EntryAbility', 'uid': str(UID), 'pid': str(PID), 'notificationId': '42',
           'continuousTaskId': '17', 'wantAgentBundleName': BUNDLE, 'wantAgentAbilityName': 'EntryAbility',
           'backgroundModes': '3,'}
    full = {**own, 'bundleName': BUNDLE, 'suspendState': 'false', 'notificationLabel': 'actual-bgt-label',
            'isCombinedTaskNotification': 'false'}
    notification = {'UserId': '100', 'CreatePid': '1001', 'OwnerBundleName': 'ohos.global.systemres',
                    'OwnerUid': str(UID), 'Id': '42', 'Label': 'actual-bgt-label'}
    render = lambda v: ''.join('\t\t' + k + ': ' + value + '\n' for k, value in v.items())
    return 'No.1' + render(own), 'No.1' + render(full), 'notification list:\nNo.1\n' + render(notification)


class AudioFocusObservation(unittest.TestCase):
    def test_two_services_join_by_owner_uid_id_label_and_unsuspended_actual_task(self):
        own, full, notification = service_text()
        result = O.active_task(own, full, notification, UID, PID, BUNDLE, 17, 42)
        self.assertEqual(result['identity_key'], [UID, 42, 'actual-bgt-label'])
        self.assertNotEqual(result['notification']['CreatePid'], str(PID))
        for mutation in ('other_owner', 'other_id', 'other_label', 'suspended', 'mode13', 'combined', 'wrong_pid', 'duplicate'):
            a, b, c = own, full, notification
            if mutation == 'other_owner': c = c.replace('OwnerUid: ' + str(UID), 'OwnerUid: ' + str(UID + 1))
            elif mutation == 'other_id': c = c.replace('Id: 42', 'Id: 43')
            elif mutation == 'other_label': c = c.replace('Label: actual-bgt-label', 'Label: other')
            elif mutation == 'suspended': b = b.replace('suspendState: false', 'suspendState: true')
            elif mutation == 'mode13': b = b.replace('backgroundModes: 3,', 'backgroundModes: 13,')
            elif mutation == 'combined': b = b.replace('isCombinedTaskNotification: false', 'isCombinedTaskNotification: true')
            elif mutation == 'wrong_pid': a = a.replace('pid: ' + str(PID), 'pid: 999')
            else: c += 'No.2\n' + notification.split('No.1\n')[1]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                O.active_task(a, b, c, UID, PID, BUNDLE, 17, 42)

    def test_empty_or_error_notification_dump_cannot_prove_an_active_notification(self):
        own, full, _ = service_text()
        for error in ('', 'no notification\n', 'permission denied\n', 'notification list:\n', 'param invaild\n'):
            with self.assertRaises(ValueError): O.active_task(own, full, error, UID, PID, BUNDLE, 17, 42)
        self.assertEqual(O.records('No running continuous task\n'), [])

    def test_notification_ui_requires_actual_title_trusted_bundle_and_unique_visible_button(self):
        def node(text, visible=True, button=False):
            return {'attributes': {'text': text, 'type': 'Button' if button else 'Text', 'bundleName': O.DIALOG,
                    'visible': str(visible).lower(), 'enabled': 'true', 'clickable': str(button).lower(),
                    'bounds': '[0,0][120,40]' if visible else '[0,40][120,80]'}, 'children': []}
        contract = {'dialog_bundle': O.DIALOG, 'sources_sha256': {'actual-source': 'a' * 64},
            'translations': {'base': {'group_label_notification': 'Allow %s to send you notifications?', 'ALLOW': 'Allow'}}}
        layout = {'attributes': {}, 'children': [node('Allow Capability audit to send you notifications?'),
                                               node('Allow', button=True), node('Allow', visible=False, button=True)]}
        self.assertEqual(O.notification_node(layout, contract)['attributes']['text'], 'Allow')
        for mutation in ('other_app', 'camera', 'missing_title', 'multiple'):
            broken = copy.deepcopy(layout)
            if mutation == 'other_app':
                for child in broken['children']: child['attributes']['bundleName'] = 'untrusted.app'
            elif mutation == 'camera': broken['children'][0]['attributes']['text'] = 'Allow Capability audit to use microphone?'
            elif mutation == 'missing_title': broken['children'].pop(0)
            else:
                duplicate = node('Allow', button=True);duplicate['attributes']['bounds'] = '[120,0][240,40]'
                broken['children'].append(duplicate)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): O.notification_node(broken, contract)


if __name__ == '__main__': unittest.main()
