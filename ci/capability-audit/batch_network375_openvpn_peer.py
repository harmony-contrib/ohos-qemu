"""Produce the original peer protocol's ledger from actual root-owned commands.

The root supplies the original verified_built_case anchor, an actual actor and
global durable operation reservation/resource registry callbacks. This module
never creates credentials, acquires a lease, starts a VM, or relaxes the original
TLS/TUN/public-API verifier. It is a callable adapter, not a standalone runner.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess

import batch_network375_peer_protocol as P
from batch_network375_root_entry import require_owner


class OpenVpnPeer:
    def __init__(self, *, contract, anchor, prefix_state_raw, binding, owner, actor, output,
                 reserve_operation, resource_registry):
        self.owner = require_owner(owner)
        P.checked_anchor(contract, anchor, prefix_state_raw)
        P.root_binding(contract, anchor, binding)
        filename = Path(type(self.owner).run.__code__.co_filename).absolute()
        P.require(binding['constructor_source'] == dict(path=str(filename),
                  sha256=hashlib.sha256(filename.read_bytes()).hexdigest()),
                  'actual current root constructor source descriptor required')
        P.require(self.owner.python == P.PYTHON and
                  {k: self.owner.trampoline[k] for k in ('path', 'sha256')} == P.TRAMPOLINE216 and
                  {k: self.owner.environment.get(k) for k in P.DOCKER_KEYS} == binding['docker_environment'] and
                  self.owner.environment.get('PATH', '').split(':')[0] == str(Path(P.CLI97['path']).parent),
                  'actual constructor Python/trampoline/private Docker endpoint environment differs')
        P.require(callable(reserve_operation) and callable(resource_registry),
                  'root durable operation/actual created-resource registry callbacks required')
        P.require(actor['pid'] == os.getpid() and actor['pgid'] == os.getpgrp() and
                  actor['uid'] == os.geteuid(), 'actual calling actor required')
        self.contract, self.anchor, self.binding = contract, anchor, binding
        self.actor = copy.deepcopy(actor)
        self.reserve_operation = reserve_operation
        self.resource_registry = resource_registry
        self.output = Path(output).absolute()
        P.require(self.output.is_relative_to(Path(binding['output'])), 'peer ledger outside root output')
        self.owner.authorize('peer-ledger-output', dict(path=str(self.output), binding=binding))
        self.output.mkdir(mode=0o700, exist_ok=False)
        self.ledger_path = self.output / 'peer-constructors375.json'
        self.operations, self.errors, self.contexts = [], [], []
        self.ledger = dict(schema='peer-owner-constructors375/v1',
            source=copy.deepcopy(binding['constructor_source']), nonce=binding['nonce'],
            anchor_id=anchor['anchor_id'], actor=copy.deepcopy(actor), spawns=[])
        self._write()

    def _write(self):
        # The mutable rows are referenced by path+index before construction;
        # their final raw snapshot hash is only computed after real settlement.
        for filename, value in (('peer-constructors375.json', self.ledger),
                                ('peer-operations375.json', self.operations),
                                ('peer-errors375.json', self.errors)):
            path = self.output / filename
            temporary = self.output / ('.' + filename + '.next')
            with temporary.open('xb') as stream:
                stream.write(P.encoded(value) + b'\n'); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)

    @contextlib.contextmanager
    def operation(self, *, origin, mode, journal_index=None):
        P._actor(self.contract, self.anchor, self.actor, origin, mode, self.binding)
        self.contexts.append(dict(origin=origin, mode=mode, journal_index=journal_index))
        try:
            yield self
        finally:
            self.contexts.pop()

    def run(self, argv, *, timeout):
        P.require(len(self.contexts) == 1, 'one actual original operation scope required')
        context = self.contexts[0]
        ids = self.resource_registry(self.binding['nonce'], self.anchor['anchor_id'])
        if context['origin'] == 'process-cut':
            P.require(argv == P.PS_ARGV, 'exact current census argv required')
        else:
            classification = P.admit_argv(self.contract, argv, phase='runtime',
                                         observed_ids=ids, context=self.anchor['docker_context'])
            if context['origin'] != 'controller':
                allowed = ('witness-inspect',) if context['origin'] == 'witness' else ('inspect-name', 'inspect-id')
                P.require(classification['action'] in allowed, 'read-only actor attempted resource mutation')
            elif classification['action'] in ('create', 'start'):
                P.require(context['mode'] == 'start', 'creation outside original start phase')
            elif classification['action'] in ('stop', 'remove', 'logs'):
                P.require(context['mode'] == 'stop', 'disposal outside original stop phase')
        index = len(self.ledger['spawns'])
        op = dict(id=os.urandom(16).hex(), sequence=None, **context, argv=list(argv),
                  constructor=dict(ledger_path=str(self.ledger_path), index=index))
        row = dict(operation_id=op['id'], original_argv=list(argv), final_exec_argv=list(argv),
            actual_spawn_argv=None, previous_signal_mask=None, effective_environment=None,
            state='intent', pid=None, pgid=None, uid=None, exit_code=None, reaped=False,
            start_new_session=context['origin'] != 'controller', stdout_sha256=None,
            stderr_sha256=None, query_tools_before=None, query_tools_after=None)
        self.ledger['spawns'].append(row); self._write()
        # Root must reserve/persist this exact whole operation before returning
        # its global sequence; never infer the order after subprocess success.
        sequence = self.reserve_operation(copy.deepcopy(op))
        P.require(type(sequence) is int and sequence > 0, 'actual durable global sequence required')
        P.require(not self.operations or sequence > self.operations[-1]['sequence'],
                  'root reused/reordered durable global operation sequence')
        op['sequence'] = sequence
        self.operations.append(op); self._write()
        root_index = len(self.owner.records)
        try:
            result = self.owner.run(list(argv), timeout=timeout, label=op['id'],
                                    start_new_session=row['start_new_session'])
            return result
        except BaseException as error:
            self.errors.append(dict(operation_id=op['id'], error=type(error).__name__ + ': ' + str(error)))
            raise
        finally:
            if len(self.owner.records) == root_index + 1:
                actual = self.owner.records[root_index]
                P.require(actual['original_argv'] == argv and actual['label'] == op['id'],
                          'actual root constructor is not this registered operation')
                for key in ('actual_spawn_argv', 'previous_signal_mask', 'state', 'pid', 'pgid',
                            'uid', 'exit_code', 'reaped', 'start_new_session'):
                    if key in actual:
                        row[key] = copy.deepcopy(actual[key])
                if 'effective_environment' in actual:
                    env = actual['effective_environment']
                    row['effective_environment'] = {k: env.get(k) for k in P.DOCKER_KEYS | {'PATH'}}
                for name in ('stdout', 'stderr'):
                    if name in actual:
                        row[name + '_sha256'] = actual[name]['sha256']
                row['query_tools_before'] = actual.get('tool_identities_before')
                row['query_tools_after'] = actual.get('tool_identities_after')
            else:
                self.errors.append(dict(operation_id=op['id'], error='constructor not uniquely assigned'))
                self.owner.quarantined = True
            self._write()

    def subprocess_proxy(self):
        peer = self

        class Proxy:
            DEVNULL = subprocess.DEVNULL
            TimeoutExpired = subprocess.TimeoutExpired

            @staticmethod
            def run(argv, *, capture_output, timeout, stdin=None, text=False, check=False):
                P.require(capture_output is True and stdin in (None, subprocess.DEVNULL) and
                          type(text) is bool and check is False, 'original complete subprocess.run contract required')
                result = peer.run(list(argv), timeout=timeout)
                if text:
                    def decoded(raw):
                        # Match subprocess.run(text=True)'s universal newlines;
                        # the root constructor still preserves original bytes.
                        return raw.decode('utf-8', 'strict').replace('\r\n', '\n').replace('\r', '\n')
                    return subprocess.CompletedProcess(result.args, result.returncode,
                        decoded(result.stdout), decoded(result.stderr))
                return result
        return Proxy()

    @contextlib.contextmanager
    def _intercept(self, cls):
        """Intercept only source-pinned private module globals, never stdlib."""
        dictionaries = []
        for base in cls.__mro__:
            for name in ('command', 'absent'):
                function = base.__dict__.get(name)
                if function is None or not hasattr(function, '__globals__'):
                    continue
                namespace = function.__globals__
                if 'subprocess' not in namespace or any(namespace is old for old, _ in dictionaries):
                    continue
                filename = Path(namespace['__file__']).resolve()
                relative = filename.relative_to(Path(P.HERE)).as_posix()
                P.require(relative in P.SOURCE_SHA and
                          hashlib.sha256(filename.read_bytes()).hexdigest() == P.SOURCE_SHA[relative],
                          'unknown original Controller function source')
                P.require(namespace['subprocess'] is subprocess, 'foreign cached subprocess replacement')
                dictionaries.append((namespace, namespace['subprocess']))
        P.require(dictionaries, 'source-pinned original Controller subprocess boundary missing')
        proxy = self.subprocess_proxy()
        try:
            for namespace, _ in dictionaries:
                namespace['subprocess'] = proxy
            yield
        finally:
            for namespace, original in dictionaries:
                namespace['subprocess'] = original

    def controller_class(self, original, *, mode):
        """Keep the original command/absence writers and stop35 transformation."""
        peer = self

        class OwnedController(original):
            def command(self, *args, **kwargs):
                with peer.operation(origin='controller', mode=mode,
                                    journal_index=len(self.state['commands'])):
                    with peer._intercept(original):
                        return super().command(*args, **kwargs)

            def absent(self, *args, **kwargs):
                with peer.operation(origin='controller', mode=mode,
                                    journal_index=len(self.state['commands'])):
                    with peer._intercept(original):
                        return super().absent(*args, **kwargs)
        return OwnedController
