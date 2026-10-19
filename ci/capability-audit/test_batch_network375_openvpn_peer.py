"""Actual adapter code with held-Popen doubles; no Docker or Linux peer."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import batch_network375_openvpn_peer as A
import batch_network375_peer_protocol as P
import batch_network375_root_entry as E
from batch_network375_peer_fixture import Frame267


class CommandDouble:
    pid = 62342
    returncode = None
    def communicate(self, timeout):
        self.returncode = 0
        return b'actual constructor unit stream', b''


class AdapterTests(unittest.TestCase):
    def setup_peer(self, root, *, reserve=None):
        frame = Frame267(evidence_root=str(root))
        source = Path(E.__file__).absolute()
        frame.binding['constructor_source'] = dict(path=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        environment = {'PATH': str(Path(P.CLI97['path']).parent) + ':/usr/bin:/bin'}
        (root / 'vm').mkdir()
        self.factory = Mock(return_value=CommandDouble())
        self.stop = Mock()
        owner = E.RootExecutor(root / 'vm/root-constructors', admit=lambda *a: None,
            register=lambda process, row: dict(pid=process.pid, pgid=process.pid, uid=os.geteuid()),
            stop_held=self.stop, python=P.PYTHON,
            trampoline=dict(P.TRAMPOLINE216, bytes=1), environment=environment,
            popen_factory=self.factory)
        actor = dict(kind='guardian', pid=os.getpid(), pgid=os.getpgrp(), uid=os.geteuid(),
                     source=frame.binding['constructor_source'])
        sequence = []
        def allocate(op):
            sequence.append(op); return len(sequence)
        peer = A.OpenVpnPeer(contract=frame.contract, anchor=frame.anchor,
            prefix_state_raw=frame.prefix_state_raw, binding=frame.binding, owner=owner,
            actor=actor, output=root / 'vm/peer-constructors',
            reserve_operation=reserve or allocate,
            resource_registry=lambda nonce, anchor: dict(build=frame.build_id, peer=frame.peer_id, network=frame.network_id))
        return frame, owner, peer, sequence

    def mock_trampoline(self, filename, *, executable=True):
        if str(filename) != P.TRAMPOLINE216['path']:
            raise AssertionError('unexpected executable observation')
        return dict(descriptor=dict(P.TRAMPOLINE216, bytes=1), stat={})

    def test_real_adapter_produces_independently_joined_constructor_from_held_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            frame, owner, peer, operations = self.setup_peer(Path(temporary))
            with patch.object(E, 'tool_identity', side_effect=self.mock_trampoline):
                with peer.operation(origin='witness', mode='inspect'):
                    result = peer.run(['docker', 'inspect', frame.peer_id], timeout=1)
            self.assertEqual(operations[0]['sequence'], None)  # reservation precedes returned sequence
            self.assertEqual(peer.operations[0]['sequence'], 1)
            raw = peer.ledger_path.read_bytes()
            snapshots = {str(peer.ledger_path):dict(descriptor=P.record_bytes(str(peer.ledger_path), raw), raw=raw)}
            row, actor = P.constructor_row(frame.contract, frame.anchor, frame.binding,
                                           peer.operations[0], snapshots)
            self.assertEqual(row['pid'], self.factory.return_value.pid)
            self.assertEqual(row['stdout_sha256'], hashlib.sha256(result.stdout).hexdigest())
            self.assertTrue(row['reaped'])
            self.assertEqual(actor['pid'], os.getpid())
            self.assertFalse(json.loads(owner.journal.read_text())['resource_cleanup_verified'])

    def test_readonly_actor_cannot_create_even_with_valid_original_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            frame, owner, peer, _ = self.setup_peer(Path(temporary))
            with peer.operation(origin='witness', mode='inspect'):
                with self.assertRaises(P.NotReady):
                    peer.run(frame.contract['plan']['peer_create'], timeout=1)
            self.factory.assert_not_called()

    def test_root_sequence_reuse_rejected_before_second_constructor(self):
        with tempfile.TemporaryDirectory() as temporary:
            frame, owner, peer, _ = self.setup_peer(Path(temporary), reserve=lambda op: 1)
            with patch.object(E, 'tool_identity', side_effect=self.mock_trampoline):
                with peer.operation(origin='witness', mode='inspect'):
                    peer.run(['docker', 'inspect', frame.peer_id], timeout=1)
                with peer.operation(origin='witness', mode='inspect'):
                    with self.assertRaises(P.NotReady):
                        peer.run(['docker', 'inspect', frame.peer_id], timeout=1)
            self.assertEqual(self.factory.call_count, 1)

    def test_original_prefix_raw_lexical_change_is_not_reencoded_into_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            frame, owner, peer, _ = self.setup_peer(Path(temporary))
            with self.assertRaises(P.NotReady):
                A.OpenVpnPeer(contract=frame.contract, anchor=frame.anchor,
                    prefix_state_raw=frame.prefix_state_raw+b' ', binding=frame.binding, owner=owner,
                    actor=peer.actor, output=Path(temporary)/'vm/never-created',
                    reserve_operation=lambda op:1, resource_registry=lambda *a:{})
            self.assertFalse((Path(temporary)/'vm/never-created').exists())


if __name__ == '__main__':
    unittest.main()
