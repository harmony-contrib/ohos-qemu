"""Host fixtures for strict network evidence; never actual guest acceptance."""
import copy
import ast
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from network_accounting_contract import endpoint_port, generate
from network_accounting_endpoint import Endpoint, payload
from run_normal_hap_probe import PERSONAS, verifier_arguments
from run_root_probe import digest
from verify_network_accounting_results import verify

RUN = '0123456789abcdef' * 2
UID = 20010000
URL = 'http://10.0.2.2:23456/' + RUN
IDENTITY = json.dumps(dict(applicationInfo=dict(appPrivilegeLevel='normal', isSystemApp=False, uid=UID)))


def observations():
    rows = []
    def row(name, values):
        rows.append(dict(runId=RUN, name=name, values=values, error=''))
    row('identity', [UID, UID])
    row('warmup', [32])
    before = [400, 600]
    for generation in (1, 2):
        row('before.' + str(generation), before.copy())
        length = len(payload(RUN, generation))
        row('payload.' + str(generation), [length])
        before = [value + length + 1000 for value in before]
        row('after.' + str(generation), before.copy())
    row('other-uid-denial', [201, 201])
    row('summary', [1])
    return rows


def peer():
    return dict(scope='owned_loopback_HTTP_peer_NOT_guest_or_statistics_acceptance', run_id=RUN,
        endpoint=URL, bind_address='127.0.0.1', listener_closed=True, errors=[],
        requests=[dict(generation=i, length=len(payload(RUN, i)),
                       sha256=hashlib.sha256(payload(RUN, i)).hexdigest()) for i in range(3)],
        implementation_sha256=digest(Path(__file__).with_name('network_accounting_endpoint.py')))


def encoded(rows):
    return '\n'.join(json.dumps(row) for row in rows)


class NetworkAccountingTests(unittest.TestCase):
    def test_validated_endpoint_cannot_inject_ArkTS_or_target_external_hosts(self):
        self.assertEqual(endpoint_port(URL, RUN), 23456)
        for url in ('https://example.com/' + RUN, URL + "';", URL + '/0', URL.replace(':23456', ':80'),
                    URL.replace(':23456', ':65536'), URL.replace(RUN, 'a' * 32)):
            with self.subTest(url=url), self.assertRaises(ValueError):
                generate(RUN, url)
        source = generate(RUN, URL)
        self.assertIn(URL, source)
        self.assertNotIn('__NETWORK_ACCOUNTING_', source)

    def test_complete_fixture_not_full_gap_closure(self):
        value = verify(encoded(observations()), RUN, IDENTITY, peer(), URL)
        self.assertEqual(value['closed'], [])
        self.assertEqual(value['uid'], UID)
        self.assertEqual(value['rx_tx_payload_bytes'], [131072, 262144])

    def test_no_traffic_wrong_UID_denial_missing_or_reordered_rows_are_rejected(self):
        good = observations()
        variants = [good[:-1], [good[1], good[0], *good[2:]]]
        for index, values in ((0, [0, 0]), (4, good[2]['values']), (3, [0]), (8, [0, 201]), (9, [0])):
            changed = copy.deepcopy(good)
            changed[index]['values'] = values
            variants.append(changed)
        changed = copy.deepcopy(good)
        changed[4]['values'][0] = True
        variants.append(changed)
        changed = copy.deepcopy(good)
        changed[4]['values'][0] += 1000000
        variants.append(changed)
        changed = copy.deepcopy(good)
        changed[2]['runId'] = 'a' * 32
        variants.append(changed)
        for changed in variants:
            with self.subTest(rows=changed), self.assertRaises(ValueError):
                verify(encoded(changed), RUN, IDENTITY, peer(), URL)
        with self.assertRaises(ValueError):
            verify(encoded(good), RUN, IDENTITY.replace('normal', 'system_basic'), peer(), URL)

    def test_peer_mismatch_and_incomplete_shutdown_are_not_accepted(self):
        for key, value in (('run_id', 'a' * 32), ('requests', []), ('errors', ['timeout']),
                           ('listener_closed', False), ('bind_address', '0.0.0.0'),
                           ('implementation_sha256', '0' * 64)):
            document = peer()
            document[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify(encoded(observations()), RUN, IDENTITY, document, URL)
        document = peer()
        document['requests'][1]['generation'] = True
        with self.assertRaises(ValueError):
            verify(encoded(observations()), RUN, IDENTITY, document, URL)

    def test_actual_loopback_peer_reads_and_echoes_three_nonce_payloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            endpoint = Endpoint(RUN)
            try:
                for generation in range(3):
                    connection = http.client.HTTPConnection('127.0.0.1', endpoint.port, timeout=10)
                    try:
                        body = payload(RUN, generation)
                        connection.request('POST', '/' + RUN + '/' + str(generation), body)
                        response = connection.getresponse()
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.read(), body)
                    finally:
                        connection.close()
            finally:
                actual = endpoint.finish(Path(temporary) / 'peer.json')
            self.assertEqual(actual['requests'], peer()['requests'])
            self.assertEqual(actual['errors'], [])
            self.assertTrue(actual['listener_closed'])

    def test_peer_rejects_wrong_payload_and_stops(self):
        with tempfile.TemporaryDirectory() as temporary:
            endpoint = Endpoint(RUN)
            try:
                connection = http.client.HTTPConnection('127.0.0.1', endpoint.port, timeout=10)
                try:
                    connection.request('POST', '/' + RUN + '/0', b'x' * 32)
                    response = connection.getresponse()
                    self.assertEqual(response.status, 400)
                    response.read()
                finally:
                    connection.close()
            finally:
                actual = endpoint.finish(Path(temporary) / 'peer.json')
            self.assertEqual(actual['requests'], [])
            self.assertEqual(len(actual['errors']), 1)

    def test_runner_uses_normal_identity_and_bound_inputs(self):
        self.assertEqual(PERSONAS['network-accounting'][0], '--network-accounting-only')
        args = verifier_arguments('network-accounting', 'archive', 'results', 'identity', RUN, 'arm64', 'output')
        self.assertIn('--arch', args)
        self.assertIn('--application-identity', args)
        runner = Path(__file__).with_name('run_normal_hap_probe.py').read_text()
        self.assertIn("['--network-accounting-endpoint', network_peer.endpoint]", runner)
        self.assertIn("['--http-peer', str(peer_path)]", runner)

    def test_actual_builder_grants_only_INTERNET_to_accounting_caller(self):
        tree = ast.parse(Path(__file__).with_name('build_hap_probe.py').read_text())
        expressions = [value for node in ast.walk(tree) if isinstance(node, ast.Dict)
                       for key, value in zip(node.keys, node.values)
                       if isinstance(key, ast.Constant) and key.value == 'requestPermissions'
                       and isinstance(value, ast.IfExp)]
        self.assertEqual(len(expressions), 1)
        args = SimpleNamespace(camera_only=False, wifi_scan_only=False, network_accounting_only=True)
        expression = compile(ast.Expression(expressions[0]), 'actual-builder-permissions', 'eval')
        self.assertEqual(eval(expression, {'args': args}), [{'name': 'ohos.permission.INTERNET'}])


if __name__ == '__main__':
    unittest.main()
