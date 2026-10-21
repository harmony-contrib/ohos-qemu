#!/usr/bin/env python3
"""Capture real ordinary callbacks on an existing new-package acceptance guest.

Never boots/restarts services, changes permissions/IDs, signs a HAP, synthesizes
measurements, or calls the provider ABI directly. SDK/signing belongs to root.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import socket
import struct
import subprocess
import time

from batch_system_live_inputs import (BUNDLE, SOCKETS, SCOPE, digest, verify_signed_payload,
    load_rows, nonce, read_json, trace, verify_project, write_json, JournalSchemaError,
    require_no_api_errors, switch_observations, LOCATION_SWITCH_API, LOCATION_SWITCH_CONTROL)
from batch_system_gnss_controller import encode_sample, read_exact
from guest_ui import GuestUi
from hdc_transport import failed as hdc_failed
from run_normal_hap_probe import require_normal_identity
import batch_system_live_mappings as live_mappings


class JournalNotReady(ValueError):
    """Only an explicitly absent/initially empty journal may be polled again."""


class Capture:
    def __init__(self, args):
        self.a = args; self.output = args.output.resolve(); self.output.mkdir(parents=True, exist_ok=False)
        self.report = {'schema_version': 1, 'scope': SCOPE, 'status': 'fail', 'failures': [],
            'commands': [], 'sessions': [], 'ui_actions': [], 'first_artifact_behavior_gate_passed': False}
        self.streams = []; self.forwards = []
        self.remote = '/data/app/el2/100/base/' + BUNDLE + '/files/live-' + nonce(args.run_id) + '.jsonl'
        self.report.update(run_id=args.run_id, archive=str(args.archive.resolve()), archive_sha256=digest(args.archive),
            enclosing_boot=str(args.boot.resolve()), enclosing_boot_sha256=digest(args.boot),
            project=str(args.project.resolve()), sdk=str(args.sdk.resolve()), arch=args.arch,
            signed_hap=str(args.signed_hap.resolve()), signed_hap_sha256=digest(args.signed_hap),
            runner_sha256=digest(Path(__file__)), signer_jar=str(args.signer_jar.resolve()), signer_jar_sha256=digest(args.signer_jar))
        self.ui = GuestUi(self.command, args.hdc, args.target, self.output / 'ui')

    def command(self, argv, label, timeout=60, accepted_failure=False):
        argv = list(map(str, argv)); path = self.output / (f'{len(self.report["commands"]):04d}-{label}.log')
        record = {'argv': argv, 'label': label}; self.report['commands'].append(record)
        try:
            p = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
            path.write_bytes(p.stdout + p.stderr)
            record.update(exit_code=p.returncode, log=str(path), sha256=digest(path))
            stdout, stderr = p.stdout.decode('utf-8'), p.stderr.decode('utf-8')
            if not accepted_failure and (p.returncode or hdc_failed(stdout, stderr)):
                raise ValueError('actual operation failed: ' + label)
            return stdout.replace('\r', '')
        except subprocess.TimeoutExpired as e:
            path.write_bytes((e.stdout or b'') + (e.stderr or b'')); record.update(timed_out=True, log=str(path), sha256=digest(path))
            raise ValueError('bounded operation timeout: ' + label) from e

    def shell(self, script, label, accepted_failure=False):
        marker = '__LIVE_GUEST_EXIT_' + secrets.token_hex(16) + '__='
        output = self.command([self.a.hdc, '-t', self.a.target, 'shell',
            '(' + script + '); task_live_rc=$?; printf "\\n' + marker + '%s\\n" "$task_live_rc"'],
            label, accepted_failure=accepted_failure)
        match = re.search(r'\n' + marker + r'([0-9]+)\s*$', output)
        if not match or (match.group(1) != '0' and not accepted_failure):
            raise ValueError('missing/nonzero actual guest exit: ' + label)
        return output[:match.start()].rstrip('\n')

    def rows(self):
        absent = '__LIVE_JOURNAL_NOT_CREATED__'
        script = 'if test -f ' + shlex.quote(self.remote) + '; then cat ' + shlex.quote(self.remote)
        script += '; else printf "' + absent + '\\n"; fi'
        raw = self.shell(script, 'read-own-raw-callbacks')
        path = self.output / 'raw-results.jsonl'
        path.write_text(('' if raw == absent else raw) + '\n')
        if raw in ('', absent):
            if getattr(self, '_journal_seen', False):
                raise JournalSchemaError('actual journal disappeared/truncated after valid rows')
            raise JournalNotReady('actual ordinary journal not created/written yet')
        rows = load_rows(path, self.a.run_id)
        self._journal_seen = True
        return rows

    def wait(self, kind, generation=None, seconds=30):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                rows = self.rows()
            except JournalNotReady:
                time.sleep(.25)
                continue
            # Never replace a schema/transport/API failure with a timeout, even
            # when the requested marker is already present later in the journal.
            require_no_api_errors(rows, 'waiting for ' + kind)
            candidates = [r for r in rows if r['kind'] == kind and (generation is None or r['generation'] == generation)]
            if candidates:
                return candidates[-1]
            time.sleep(.25)
        raise ValueError('ordinary callback/control did not arrive: ' + kind)

    def read_location_switch_state(self, label, seconds=30):
        """Repeatable read-only public observation, usable during restoration.

        Prior API errors are returned verbatim in the observation, never erased
        or converted into acceptance. Errors from this query fail immediately.
        This method does not change the switch, request permission or touch HDI.
        """
        if re.fullmatch('[A-Za-z0-9_-]+', label) is None or not 0 < seconds <= 90:
            raise ValueError('bounded explicit public switch query label/deadline required')
        before = self.rows()
        before_seq = before[-1]['seq']
        old_queries = [r for r in before if r['kind'] == 'location_switch_query']
        request_id = len(old_queries) + 1
        self.click(LOCATION_SWITCH_CONTROL)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            rows = self.rows()
            recent = [r for r in rows if r['seq'] > before_seq]
            require_no_api_errors(recent, 'reading actual public switch state: ' + label)
            observations = [r for r in switch_observations(rows) if r['request_id'] == request_id and r['before_seq'] > before_seq]
            if observations:
                if len(observations) != 1:
                    raise JournalSchemaError('public switch query produced duplicate states')
                observation = dict(observations[0], label=label,
                    prior_api_errors=[r for r in before if r['kind'] == 'error'],
                    scope='ordinary_public_switch_state_observation_ONLY_NOT_acceptance')
                self.report.setdefault('public_location_switch_observations', []).append(observation)
                return observation
            time.sleep(.25)
        raise ValueError('actual public ' + LOCATION_SWITCH_API + ' result missing: ' + label)

    def click(self, identifier):
        action = self.ui.click(BUNDLE, identifier=identifier, label=identifier)
        action.update(identifier=identifier, layout_sha256=digest(action['layout']))
        self.report['ui_actions'].append(action)
        return action

    def mark(self):
        before = len([r for r in self.rows() if r['kind'] == 'quiet_marker'])
        self.click('live-quiet'); end = time.monotonic() + 10
        while time.monotonic() < end:
            marks = [r for r in self.rows() if r['kind'] == 'quiet_marker']
            if len(marks) == before + 1: return marks[-1]['seq']
            time.sleep(.2)
        raise ValueError('actual app clock marker missing')

    def connect(self, kind, label):
        stream = socket.socket(); stream.settimeout(3)
        stream.connect(('127.0.0.1', self.ports[kind])); self.streams.append(stream)
        hello = read_exact(stream, 32)
        magic, version, challenge, field, reserved = struct.unpack('<4sI16sII', hello)
        expected = (b'QGN1', 88) if kind == 'gnss' else (b'QSN1', 1)
        if (magic, version, field, reserved) != (expected[0], 1, expected[1], 0):
            raise ValueError('actual provider handshake invalid')
        row = {'kind': kind, 'label': label, 'hello_hex': hello.hex(), 'frames': [],
               'connected_monotonic_ns': time.monotonic_ns(), 'generation': self.generation}
        self.report['sessions'].append(row)
        return stream, challenge, row

    @staticmethod
    def frame(kind, challenge, seq, sample):
        if kind == 'gnss': return encode_sample(challenge, seq, sample)
        return struct.pack('<4sI16sQfff', b'QSF1', 1, challenge, seq, sample['x'], sample['y'], sample['z'])

    @staticmethod
    def eof(stream):
        stream.settimeout(3)
        try:
            if stream.recv(1) != b'': raise ValueError('provider returned unexpected data instead of closing')
        except ConnectionResetError:
            return 'ECONNRESET'
        return 'EOF'

    def bad_cases(self, kind, sample, old_nonce=None):
        cases = ['wrong_nonce', 'zero_sequence', 'wrong_version', 'nonfinite']
        if old_nonce is not None: cases.append('old_generation_nonce')
        for name in cases:
            stream, challenge, record = self.connect(kind, name)
            packet = bytearray(self.frame(kind, challenge, 1, sample))
            if name == 'wrong_nonce': packet[8] ^= 128
            elif name == 'old_generation_nonce': packet[8:24] = old_nonce
            elif name == 'zero_sequence': packet[24:32] = bytes(8)
            elif name == 'wrong_version': packet[4:8] = struct.pack('<I', 0xffffffff)
            elif kind == 'gnss': packet[40:48] = struct.pack('<d', float('nan'))
            if name == 'nonfinite' and kind == 'sensor': packet[32:36] = struct.pack('<f', float('nan'))
            # Fixed raw bytes, not a requested/expected rejection boolean.
            stream.sendall(packet); record['frames'].append({'hex': bytes(packet).hex(), 'host_monotonic_ns': time.monotonic_ns()})
            record.update(disconnect=self.eof(stream), eof_monotonic_ns=time.monotonic_ns())
            stream.close()

    def supplied(self, generation):
        ready = self.output / ('ready-' + str(generation) + '.json')
        write_json(ready, {'run_id': self.a.run_id, 'generation': generation, 'host_utc_ms': int(time.time() * 1000),
            'request': 'root must now publish generationN.json and actual fresh explicit GNSS/sensor trace files; UTC will not be rewritten'})
        manifest = self.a.input_directory / ('generation' + str(generation) + '.json')
        end = time.monotonic() + self.a.input_wait
        while not manifest.is_file() and time.monotonic() < end: time.sleep(.25)
        value = read_json(manifest)
        if (value.get('run_id') != self.a.run_id or value.get('generation') != generation or
                not isinstance(value.get('source'), str) or not value['source'].strip()):
            raise ValueError('external measurement/replay provenance and actual run/generation required')
        dest = self.output / ('input-' + str(generation)); dest.mkdir()
        shutil.copyfile(manifest, dest / 'manifest.json')
        result = {}
        for kind in SOCKETS:
            name = value[kind + '_file']
            if not isinstance(name, str) or Path(name).name != name: raise ValueError('input must be a simple private filename')
            source = self.a.input_directory / name
            if source.is_symlink() or not source.is_file(): raise ValueError('actual supplied trace missing')
            before = digest(source); shutil.copyfile(source, dest / (kind + '.json'))
            if before != digest(source) or before != digest(dest / (kind + '.json')): raise ValueError('source changed during capture')
            result[kind] = trace(dest / (kind + '.json'), kind)
        return result

    def mapping_snapshot(self, name, *, pid=None, libraries=()):
        """Retain one complete raw attempt; its gaps never become absence.

        Root's GNSS driver uses exact-PID cuts before/after its actual Dump and
        live_mappings.bind_trace_process with same-image contract descriptors.
        A single-PID positive cut cannot replace a complete all-PID absence scan.
        No readiness retry or successful last printf hides a query failure.
        """
        if re.fullmatch('[A-Za-z0-9_-]{1,96}', name) is None:
            raise ValueError('safe unique actual maps capture label required')
        boot_id = self.report.get('boot_id')
        scan_nonce = secrets.token_hex(16)
        script = live_mappings.snapshot_script(scan_nonce, boot_id, pid=pid, libraries=libraries)
        prefix = self.output / (name + '-proc-maps')
        script_path = prefix.with_suffix('.sh')
        with script_path.open('x') as stream: stream.write(script)
        entry = dict(nonce=scan_nonce, boot_id=boot_id, pid=pid, libraries=list(libraries),
                     script=dict(path=str(script_path), sha256=digest(script_path)),
                     parser=dict(path=str(Path(live_mappings.__file__).resolve()), sha256=digest(live_mappings.__file__)),
                     command_index=len(self.report['commands']), status='raw_not_yet_parsed')
        self.report.setdefault('mapping_snapshots', []).append(entry)
        # shell() preserves command stdout/stderr and its HDC/guest result even
        # when it raises. A passing shell result still needs every framed rc.
        raw = self.shell(script, name)
        path = prefix.with_suffix('.raw.txt')
        with path.open('x') as stream: stream.write(raw + '\n')
        entry['raw'] = dict(path=str(path), sha256=digest(path))
        snapshot = live_mappings.parse_snapshot(path.read_text(), scan_nonce, boot_id, pid=pid, libraries=libraries)
        parsed = prefix.with_suffix('.json')
        with parsed.open('x') as stream:
            json.dump({k: v for k, v in snapshot.items() if k != 'raw'}, stream, indent=2, allow_nan=False); stream.write('\n')
        entry.update(parsed=dict(path=str(parsed), sha256=digest(parsed)),
                     status='complete_observation_ONLY' if snapshot['complete'] else 'gap_raw_evidence_preserved',
                     complete=snapshot['complete'], global_absence_eligible=snapshot['global_absence_eligible'])
        live_mappings.verify_evidence(entry, self.report['commands'][entry['command_index']], target=self.a.target)
        return dict(snapshot=snapshot, evidence=entry)

    def mappings(self, name):
        observation = self.mapping_snapshot(name)
        value = live_mappings.legacy_text(observation['snapshot'])
        path = self.output / (name + '.txt')
        with path.open('x') as stream: stream.write(value)
        observation['evidence']['legacy_view'] = dict(path=str(path), sha256=digest(path))
        return str(path)

    def run(self):
        a = self.a; r = self.report
        try:
            boot = read_json(a.boot); env = boot['test_environment']
            if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or env.get('external_keepalive') is not False or
                    boot['archive_sha256'] != r['archive_sha256'] or env['target'] != a.target or
                    env['guest_arch'] != a.arch or env['device_type'] not in ('phone','2in1') or
                    {'arm64':'arm64_virt','armv7a':'armv7a_virt','x86_64':'x86_64_virt'}.get(a.arch) != env['product']):
                raise ValueError('requires same newly packaged actual product/profile acceptance boot')
            r['boot_id'] = env['boot_id']
            if self.shell('cat /proc/sys/kernel/random/boot_id', 'boot-before') != r['boot_id']:
                raise ValueError('connected guest does not match enclosing acceptance boot')
            contract = verify_project(a.project, a.sdk, a.run_id, a.arch)
            build = read_json(a.project / 'live-inputs-build.json')
            if build.get('status') != 'pass' or digest(build['unsigned_hap']) != build['unsigned_hap_sha256']:
                raise ValueError('actual SDK-built caller evidence required')
            verify_signed_payload(build['unsigned_hap'], a.signed_hap)
            r['contract_sha256'] = digest(a.project / 'live-inputs-contract.json')
            r['build_sha256'] = digest(a.project / 'live-inputs-build.json')
            # Verify the actual installed HAP signature with the real tool; no profile shim.
            profile = self.output / 'verified-profile.p7b'; chain = self.output / 'verified-chain.cer'
            log = self.command(['java', '-jar', a.signer_jar, 'verify-app', '-inFile', a.signed_hap,
                '-outCertChain', chain, '-outProfile', profile], 'actual-hap-signature', timeout=120)
            if any(v not in log for v in ['verify codesign success', 'Digest verify result: true', 'verify-app success', 'verify permission sign success']):
                raise ValueError('actual normal HAP code/profile/digest signature verification incomplete')
            data = self.command(['openssl', 'cms', '-verify', '-inform', 'DER', '-in', profile, '-noverify'], 'actual-signed-profile-json')
            # OpenSSL appends diagnostic text on stderr, not to stdout (command returns stdout only).
            profile_json = json.loads(data)
            info = profile_json['bundle-info']
            if (info['bundle-name'] != BUNDLE or info['apl'] != 'normal' or info['app-feature'] != 'hos_normal_app' or
                    profile_json['acls']['allowed-acls'] or profile_json['permissions']['restricted-permissions']):
                raise ValueError('profile must remain ordinary, no ACL/restricted grants')
            self.shell('aa force-stop ' + BUNDLE, 'stop-own-old-app', accepted_failure=True)
            self.command([a.hdc, '-t', a.target, 'uninstall', BUNDLE], 'uninstall-own-old-app', accepted_failure=True)
            self.command([a.hdc, '-t', a.target, 'install', a.signed_hap], 'install-own-normal-app')
            identity = self.shell('bm dump -n ' + BUNDLE, 'ordinary-identity')
            r['ordinary_uid'] = require_normal_identity(identity, BUNDLE)
            (self.output / 'application-identity.json').write_text(identity)
            if self.shell('if test -e ' + shlex.quote(self.remote) + '; then echo STALE; else echo ABSENT; fi', 'result-absent') != 'ABSENT':
                raise ValueError('stale nonce result before launch')
            self.shell('power-shell wakeup', 'single-test-wakeup')
            launched = self.shell('aa start -a EntryAbility -b ' + BUNDLE, 'launch-own-app')
            if 'start ability successfully' not in launched: raise ValueError('actual HAP launch failed')
            self.wait('ready')
            self.click('live-permissions')
            # Root/operator handles only the real ordinary consent dialog, never bm grants.
            # --permission-allow-text is an explicit actual visible label, not guessed coordinates.
            if a.permission_allow_text:
                end = time.monotonic() + 30
                while time.monotonic() < end:
                    try:
                        action = self.ui.click('com.ohos.permissionmanager', text=a.permission_allow_text,
                                               label='actual-location-consent')
                        action.update(identifier='real-location-consent', layout_sha256=digest(action['layout']))
                        r['ui_actions'].append(action); break
                    except ValueError: time.sleep(.5)
                else: raise ValueError('actual trusted permission dialog not confirmed')
            self.wait('permissions', seconds=90)
            self.ports = {}
            for kind in SOCKETS:
                with socket.socket() as probe: probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
                local, remote = 'tcp:' + str(port), 'localfilesystem:' + SOCKETS[kind]
                # Register this private endpoint before a command that may fail
                # after creation, so the finally path still attempts removal.
                self.forwards.append((local, remote))
                self.command([a.hdc, '-t', a.target, 'fport', local, remote], 'own-forward-' + kind)
                self.ports[kind] = port
            old = {}
            for generation in (1, 2):
                self.generation = generation
                self.read_location_switch_state('before-start-' + str(generation))
                self.click('live-start'); self.wait('start_complete', generation)
                self.click('live-denials')
                r['mappings_' + str(generation)] = self.mappings('actual-mappings-' + str(generation))
                self.shell('ls -ldnZ /dev/unix/socket/qemu_gnss /dev/unix/socket/qemu_gnss/input '
                    '/dev/unix/socket/qemu_sensor /dev/unix/socket/qemu_sensor/input', 'actual-socket-identity-' + str(generation))
                paths = ['/vendor/lib64/vendorGnssAdapter.so', '/vendor/lib64/libgnss_interface_service_2.0.z.so',
                    '/system/lib64/liblbsservice_gnss.z.so', '/vendor/lib64/libhdi_sensor_impl.z.so', '/system/lib64/libdevicestatus_algo.z.so',
                    '/system/lib64/libdevicestatus_service.z.so']
                paths = [path.replace('/lib64/', '/lib/' if a.arch == 'armv7a' else '/lib64/') for path in paths]
                self.shell('sha256sum ' + ' '.join(paths), 'actual-image-libraries-' + str(generation))
                inputs = self.supplied(generation)
                begin = self.mark()
                for kind in SOCKETS: self.bad_cases(kind, inputs[kind][0], old.get(kind))
                end = self.mark(); r['attack_window_' + str(generation)] = [begin, end]
                active = {}
                def send(kind):
                    stream, challenge, record = self.connect(kind, 'valid-generation-' + str(generation))
                    active[kind] = stream; old[kind] = challenge; base_ns = time.monotonic_ns()
                    record['trace_start_monotonic_ns'] = base_ns
                    base = base_ns / 1e9
                    for i, sample in enumerate(inputs[kind], 1):
                        pause = base + sample['at_ms'] / 1000 - time.monotonic()
                        if pause > 0: time.sleep(pause)
                        packet = self.frame(kind, challenge, i, sample); stream.sendall(packet)
                        record['frames'].append({'hex': packet.hex(), 'host_monotonic_ns': time.monotonic_ns()})
                    return record
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(send, kind) for kind in SOCKETS]
                    for future in futures: future.result(timeout=55)
                time.sleep(2)  # bounded normal NAPI/latency drain, not fabricated results
                self.click('live-stop'); self.wait('stopped', generation)
                for kind, stream in active.items():
                    record = next(v for v in reversed(r['sessions']) if v['kind'] == kind and v['label'] == 'valid-generation-' + str(generation))
                    try: record.update(stop_disconnect=self.eof(stream))
                    except (TimeoutError, OSError, ValueError) as e: record['stop_disconnect_error'] = str(e)
                    stream.close()
                time.sleep(4)  # queued deliveries before this are preserved, not hidden
                begin = self.mark(); time.sleep(4); end = self.mark()
                r['quiet_window_' + str(generation)] = [begin, end]
            self.click('live-finish'); self.wait('finished')
            if self.shell('cat /proc/sys/kernel/random/boot_id', 'boot-after') != r['boot_id']:
                raise ValueError('kernel boot changed during actual test')
            self.rows(); r.update(capture_complete=True, status='captured_NOT_verified')
        except Exception as error:
            r['failures'].append(type(error).__name__ + ': ' + str(error))
        finally:
            for stream in self.streams: stream.close()
            for local, remote in self.forwards:
                try: self.command([a.hdc, '-t', a.target, 'fport', 'rm', local, remote], 'remove-own-forward', accepted_failure=True)
                except Exception as e: r['failures'].append('own-forward-cleanup: ' + str(e))
            # Preserve raw failures, including ordinary public still being unsupported.
            try: self.rows()
            except Exception as e: r['failures'].append('raw-result-capture: ' + str(e))
            r['files_sha256'] = {str(p.relative_to(self.output)): digest(p) for p in self.output.rglob('*') if p.is_file()}
            write_json(self.output / 'capture.json', r)
        return r


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['archive', 'boot', 'project', 'sdk', 'signed-hap', 'signer-jar', 'input-directory', 'output']:
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--hdc', required=True); p.add_argument('--target', required=True); p.add_argument('--run-id', required=True)
    p.add_argument('--arch', choices=['arm64','armv7a','x86_64'], default='arm64'); p.add_argument('--input-wait', type=int, default=120)
    p.add_argument('--permission-allow-text', help='Explicit actual trusted consent label, otherwise an operator handles the real dialog')
    a = p.parse_args()
    if not 1 <= a.input_wait <= 120: p.error('bounded external trace wait1..120seconds required')
    for g in (1, 2):
        if (a.input_directory / ('generation' + str(g) + '.json')).exists(): p.error('publish each fresh manifest only after ready-N.json')
    report = Capture(a).run()
    print(json.dumps({'capture_complete': report.get('capture_complete', False), 'failures': report['failures'],
                      'note': 'Capture is not acceptance. Run the independent verifier.'}))
    return 0 if report.get('capture_complete') and not report['failures'] else 1


if __name__ == '__main__': raise SystemExit(main())
