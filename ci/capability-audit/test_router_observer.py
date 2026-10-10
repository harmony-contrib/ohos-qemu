"""Synthetic verifier unit cases, never packaged-device evidence."""
import copy
import json
import unittest

from router_observer_contract import sources
from verify_router_observer_results import verify

RUN = 'a' * 32
IDENTITY = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal', 'isSystemApp': False, 'uid': 20010001}})


def fixture():
    rows = []
    for generation in range(2):
        counts = [0, 0]
        for phase, start, end in ((0, 'registered', 'both-returned'),
                                  (1, 'first-removed', 'second-returned'),
                                  (2, 'all-removed', 'unsubscribed-returned')):
            def marker(name):
                rows.append(dict(runId=RUN, name=name, listener='', generation=generation,
                    phase=phase, index=0, pageName='', path='', state=0, pageId='',
                    contextMatches=True, counts=counts[:]))
            marker(start)
            if phase < 2:
                for state in (0, 2, 3, 1):
                    for listener, slot in ((('a', 0), ('b', 1)) if phase == 0 else (('b', 1),)):
                        counts[slot] += 1
                        rows.append(dict(runId=RUN, name='event', listener=listener, generation=generation,
                            phase=phase, index=2, pageName='ObserverDetail', path='pages/ObserverDetail',
                            state=state, pageId=str(10 + generation * 2 + phase), contextMatches=True,
                            counts=counts[:]))
            marker(end)
    rows.append(dict(runId=RUN, name='summary', listener='', generation=2, phase=2,
        index=0, pageName='', path='', state=0, pageId='', contextMatches=True, counts=counts[:]))
    return rows


def check(rows):
    return verify('\n'.join(map(json.dumps, rows)), RUN, IDENTITY)


class RouterObserverTests(unittest.TestCase):
    def test_complete_fixture_is_scoped_not_capability_closure(self):
        self.assertEqual(check(fixture())['closed'], [])
        self.assertEqual(check(fixture())['observed_child_instances'], 4)

    def test_missing_reordered_or_foreign_records_fail(self):
        for index in range(len(fixture())):
            rows = fixture()
            del rows[index]
            with self.assertRaises(ValueError):
                check(rows)
        rows = fixture()
        rows[1]['runId'] = 'b' * 32
        with self.assertRaises(ValueError):
            check(rows)

    def test_bad_context_stale_identity_and_missing_state_fail(self):
        for key, value in (('contextMatches', False), ('index', True), ('state', True),
                           ('path', 'invented'), ('pageId', ''), ('counts', [True, 0])):
            rows = fixture()
            rows[1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                check(rows)

    def test_callbacks_after_removal_fail(self):
        rows = fixture()
        index = next(i for i, row in enumerate(rows) if row['name'] == 'all-removed')
        extra = copy.deepcopy(rows[1])
        extra['phase'] = 2
        rows.insert(index + 1, extra)
        with self.assertRaises(ValueError):
            check(rows)
        rows = fixture()
        for row in rows:
            if row['name'] == 'event' and row['phase'] == 1:
                row['listener'] = 'a'
        with self.assertRaises(ValueError):
            check(rows)

    def test_real_templates_bind_nonce_and_public_routing(self):
        generated = sources(RUN)
        self.assertEqual(set(generated), {'Index', 'ObserverDetail'})
        self.assertIn("pushUrl({ url: 'pages/ObserverDetail' })", generated['Index'])
        self.assertIn('info: observer.RouterPageInfo', generated['Index'])
        self.assertNotIn('info.context === this.getUIContext()', generated['Index'])
        self.assertIn('context.getHostContext()', generated['Index'])
        self.assertIn('host.filesDir === ownHost.filesDir', generated['Index'])
        self.assertIn('Number(context.getRouter().getLength()) >= 1', generated['Index'])
        self.assertIn("observer.off('routerPageUpdate', context, first)", generated['Index'])
        self.assertIn('getRouter().back()', generated['ObserverDetail'])
        self.assertNotIn('__RUN__', ''.join(generated.values()))
        with self.assertRaises(ValueError):
            sources('stale')


if __name__ == '__main__':
    unittest.main()
