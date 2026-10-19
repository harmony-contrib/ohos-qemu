"""Two-guest transport doubles: no VM, HDC, network sockets or real sessions."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

import batch_network_peer_lan as L
from batch_network375_root_entry import AdmissionError
from test_batch_network_peer_lan import fixture, prepare_unit, unit_owner


class GuestPairDouble:
    def __init__(self, plan, *, fault=None):
        self.plan, self.fault = plan, fault
        self.states = {role: dict(up=False, address=False) for role in L.ROLES}
        if fault == 'baseline-address-race':
            for state in self.states.values(): state['address'] = True
        self.commands = []

    def run(self, argv, *, timeout, label):
        self.commands.append((label, argv[-1]))
        role = next(role for role in L.ROLES if self.plan['instances'][role]['target'] == argv[2])
        inst, state = self.plan['instances'][role], self.states[role]
        body = argv[-1]
        marker = re.search(r'(__PEER_EXIT_[a-f0-9]{32}__=)', body).group(1)
        index = L.ROLES.index(role)
        text, code = '', 0
        if body.startswith('bm get --udid'):
            value = ('a' if index == 0 else 'b') * 64
            if self.fault == 'identity-swap' and 'cleanup-before' in label:
                value = 'c' * 64
            text = 'udid of current device is :\n' + value
        elif body.startswith('cat /proc/sys/kernel/random/boot_id'):
            text = ('1' if index == 0 else '2') * 8 + '-2222-4333-8444-555555555555'
        elif body.startswith('ip -o link show'):
            text = ('2: eth0: <UP> mtu 1500 link/ether ' + inst['management_mac'] + ' brd ff:ff:ff:ff:ff:ff\n'
                    '3: eth1: <' + ('UP' if state['up'] else 'BROADCAST') + '> mtu 1500 link/ether ' +
                    inst['peer_mac'] + ' brd ff:ff:ff:ff:ff:ff')
        elif body.startswith('ip -o -4 addr show'):
            text = '3: eth1 inet ' + inst['address'] + '/30 scope global eth1' if state['address'] else ''
            if self.fault == 'baseline-address-race' and 'cleanup-addresses-before' in label:
                state['foreign'] = True
            if state.get('foreign'):
                text += '\n3: eth1 inet 192.168.123.9/24 scope global eth1'
        elif 'ip addr add' in body:
            state.update(up=True, address=True)
            if self.fault == 'partial-config': code = 1
            if self.fault == 'permission':
                state.update(up=False, address=False); code = 201
        elif 'ip addr del' in body:
            state.update(up=False, address=False)
        elif 'ip link set dev eth1 down' in body:
            state['up'] = False
        elif body.startswith('ip -o route get'):
            if self.fault == 'nat-route':
                text = inst['peer_address'] + ' via 10.0.2.2 dev eth0 src 10.0.2.15'
            else:
                text = inst['peer_address'] + ' dev eth1 src ' + inst['address'] + ' uid 0'
        elif body.startswith('ping -I'):
            text = 'explicit unit packet-response double, not real traffic'
        elif body.startswith('ip neigh show'):
            other = self.plan['instances'][L.ROLES[1 - index]]
            text = inst['peer_address'] + ' dev eth1 lladdr ' + other['peer_mac'] + ' REACHABLE'
        else:
            raise AssertionError('unexpected guest double command: ' + body)
        return subprocess.CompletedProcess(argv, 0, (text + '\n' + marker + str(code) + '\n').encode(), b'')


class OwnedPairTests(unittest.TestCase):
    def staged(self, root):
        package, qemu = fixture(root)
        archive = root / 'candidate.tar.gz'
        import tarfile
        with tarfile.open(archive, 'w:gz') as target:
            target.add(package, arcname=package.name)
        args = SimpleNamespace(package=package, qemu=qemu, output=root / 'private', archive=archive,
            hdc_port=47580, vnc_display=4021, peer_port=47590, subnet='172.27.77.0/30')
        plan = prepare_unit(args)
        self.addCleanup(shutil.rmtree, plan['control_directory'])
        return args, plan, qemu

    def run_pair(self, root, fault=None, exercise=None):
        args, plan, qemu = self.staged(root)
        guests = GuestPairDouble(plan, fault=fault)
        owner = unit_owner(qemu); owner.run.side_effect = guests.run
        observe = SimpleNamespace(plan=args.output / 'peer-lan.json', output=root / 'observations',
                                  hdc=Path('/explicit-unit-HDC-never-executed'), configure=True)
        callback = (lambda **kw: exercise(guests, **kw)) if exercise is not None else None
        result = L.observe(observe, owner=owner, exercise=callback)
        return result, guests

    def test_without_root_admission_nothing_starts_or_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'never-created'
            with self.assertRaises(AdmissionError): L.prepare(SimpleNamespace(output=out))
            with self.assertRaises(AdmissionError): L.observe(SimpleNamespace(output=out))
            self.assertFalse(out.exists())

    def test_l2_double_success_restores_both_addresses_and_original_link_flags(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, guests = self.run_pair(Path(temporary))
            self.assertEqual(result['status'], 'kernel_l2_candidate_observed_not_service_acceptance', result)
            self.assertTrue(result['owned_ipv4_and_link_restored'])
            self.assertEqual(result['failures'], [])
            self.assertTrue(all(not s['up'] and not s['address'] for s in guests.states.values()))
            self.assertFalse(result['resource_cleanup_verified'])
            self.assertFalse(result['first_artifact_behavior_gate_passed'])

    def test_partial_configuration_failure_is_preserved_but_own_state_recovered(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, guests = self.run_pair(Path(temporary), 'partial-config')
            self.assertEqual(result['status'], 'fail')
            self.assertTrue(result['owned_ipv4_and_link_restored'], result)
            self.assertTrue(result['failures'])
            self.assertTrue(all(not s['up'] and not s['address'] for s in guests.states.values()))

    def test_management_nat_route_cannot_be_l2_success_and_is_restored(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, guests = self.run_pair(Path(temporary), 'nat-route')
            self.assertEqual(result['status'], 'fail')
            self.assertTrue(result['owned_ipv4_and_link_restored'])
            self.assertFalse(any('peer-ping' in label for label, _ in guests.commands))

    def test_permission_failure_is_not_retried_with_grant_or_reported_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, guests = self.run_pair(Path(temporary), 'permission')
            self.assertEqual(result['status'], 'fail')
            self.assertTrue(result['owned_ipv4_and_link_restored'])
            self.assertEqual(sum('configure-private-peer' in label for label, _ in guests.commands), 1)
            self.assertFalse(any('grant' in body or 'chmod' in body for _, body in guests.commands))

    def test_cleanup_identity_swap_preserves_unknown_guest_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, guests = self.run_pair(Path(temporary), 'identity-swap')
            self.assertEqual(result['status'], 'fail')
            self.assertFalse(result['owned_ipv4_and_link_restored'])
            self.assertTrue(any(s['address'] for s in guests.states.values()))
            self.assertFalse(any('restore-private-peer-ipv4' in label for label, _ in guests.commands))

    def test_root_service_exercise_uses_live_pair_and_binds_actual_receipt_before_restore(self):
        def exercise(guests, *, plan, identities, owner, output):
            self.assertTrue(all(s['up'] and s['address'] for s in guests.states.values()))
            self.assertNotEqual(identities['listener']['udid'], identities['connector']['udid'])
            output.mkdir()
            path = output / 'unit-service.json'
            body = json.dumps({'scope':'UNIT session double only, no real authenticated service'}).encode()
            path.write_bytes(body)
            return dict(path=str(path), sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
        with tempfile.TemporaryDirectory() as temporary:
            result, guests = self.run_pair(Path(temporary), exercise=exercise)
            self.assertTrue(result['root_service_receipt'], result)
            self.assertTrue(result['owned_ipv4_and_link_restored'])
            self.assertFalse(result['first_artifact_behavior_gate_passed'])

    def test_inner_session_failure_preserved_and_pair_network_restored(self):
        def failed(guests, **kwargs): raise RuntimeError('inner real-case boundary failed')
        with tempfile.TemporaryDirectory() as temporary:
            result, guests = self.run_pair(Path(temporary), exercise=failed)
            self.assertEqual(result['status'], 'fail')
            self.assertTrue(result['owned_ipv4_and_link_restored'])
            self.assertIsNone(result['root_service_receipt'])
            self.assertTrue(any('inner real-case boundary failed' in s for s in result['failures']))

    def test_service_success_boolean_is_not_a_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, guests = self.run_pair(Path(temporary), exercise=lambda *a, **kw: True)
            self.assertEqual(result['status'], 'fail')
            self.assertTrue(result['owned_ipv4_and_link_restored'])
            self.assertIsNone(result['root_service_receipt'])

    def test_new_unknown_address_prevents_restoring_preexisting_link_down(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, guests = self.run_pair(Path(temporary), 'baseline-address-race')
            self.assertEqual(result['status'], 'fail')
            self.assertFalse(result['owned_ipv4_and_link_restored'])
            self.assertTrue(all(s['up'] for s in guests.states.values()))
            self.assertFalse(any('restore-private-peer-link' in label for label, _ in guests.commands))


if __name__ == '__main__':
    unittest.main()
