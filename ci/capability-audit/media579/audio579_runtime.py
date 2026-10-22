"""Additional Audio10 business cases on the original stage's existing OwnedIO.

No Owner, process, HDC, VM, peer, socket or SDK substitute is created here. The
normal existing caller builder compiles/signs four real roles. MIDI peer and
voice algorithm positives remain unresolved unless their genuine raw exists.
"""
from pathlib import Path
import json
import re
import secrets
import shlex
import time
from audio579_common import HERE, need, checked, doc, ref, loads, save, dependency, source_guard, communication_napi
from audio579_project import ROLES, bundle, permissions

CASE = 'original-audio10'


def run(io, *, shared_midi=None):
    context = doc(source_guard()); commit = context['source_commit']
    need(type(io) is dependency('capability578_owned_io').OwnedIO and io.owner.vm is io.guest and
         not io._closed, 'only the original live main stage IO')
    io.owner.held_binding(io.guest)
    need(doc(ref(io.guest.directory / 'build-inputs.json'))['source_git_revision'] == commit,
         'actual packaged source and independently produced normal source context differ')
    report = dict(schema='media579-original-audio10-runtime/v1', source_commit=commit,
        run=io.run_id, archive_sha256=io.archive_sha256, boot_id=io.boot_id,
        output=str(io.output), hdc=io.hdc, target=io.target, roles={}, requests=[], observations=[], failures=[], cleanup_errors=[],
        cleanup=None, runtime_pass=False, closed_ids=[], first_artifact_behavior_gate_passed=False)
    output = io.output / 'evidence.json'
    prepared = None
    installed = []
    communication_source = communication_napi(io.package_inputs['media579_audio'])
    report['communication_source'] = communication_source
    stimulus_roots = []
    from audio579_provider_runtime import Session, PHRASES
    provider = None

    def persist():
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n')

    def shell(script, label, allow_failure=False):
        row = io.shell(script, 'audio579_' + label, allow_failure=allow_failure)
        report['observations'].append(dict(label=label, script=script, receipt=io.ref_receipt(row)))
        persist()
        return row['stdout']

    def process(role, label):
        name = bundle(CASE, role)
        bms = shell('bm dump -n ' + name, label + '_BMS')
        identity = dependency('hap_identity_binding').bms_application_identity(bms, name)
        value = loads(bms[bms.index('{'):])
        need(value['applicationInfo']['isSystemApp'] is (role != 'ordinary') and
             value['applicationInfo']['appPrivilegeLevel'] == ('normal' if role == 'ordinary' else 'system_core') and
             set(value.get('reqPermissions', [])) == set(permissions(role)), 'real caller permission/APL identity')
        raw = shell(dependency('guest_process_identity').identity_shell(name), label + '_process')
        need(re.fullmatch('[1-9][0-9]*(?: [0-9]+){5}\n?', raw), 'actual PID/birth/all-four-UID source')
        pid, birth, *uids = map(int, raw.split())
        need(birth > 0 and uids == [identity['uid']] * 4, 'native actual process UID/generation')
        identity.update(pid=pid, birth_ticks=birth)
        paths = {entry['hapPath'] for entry in value['hapModuleInfos'] if entry.get('hapPath')}
        need(len(paths) == 1, 'one installed real caller HAP')
        path = paths.pop()
        need(shell('sha256sum ' + shlex.quote(path), label + '_HAP').split() ==
             [prepared['callers'][role]['signed']['sha256'], path], 'installed source must be exactly signed caller')
        report['roles'][role].setdefault('generations', []).append(identity)
        return identity

    def launch(role, action, *, consent=False, expected_boundary=False, phrase=None):
        request = dict(run=io.run_id, boot=io.boot_id, operation=secrets.token_hex(16), action=action)
        if phrase is not None:
            need(role == 'system' and action == 'voice' and phrase in [p[0] for p in PHRASES], 'fixed independent real phrase configuration')
            request['phrase'] = phrase
        row = dict(role=role, request=request, journal=None, identity=None, UI=None, error=None)
        report['requests'].append(row); persist()
        name = bundle(CASE, role)
        remote = '/data/app/el2/100/base/' + name + '/haps/entry/files/audio579-' + io.run_id + '.jsonl'
        try:
            reply = shell(shlex.join(['aa', 'start', '-b', name, '-a', 'EntryAbility', '--ps', 'request',
                json.dumps(request, separators=(',', ':'))]), role + '_' + action)
            need('start ability successfully' in reply, 'actual single-instance public caller launch')
            if consent:
                selected = io.ui.click('com.ohos.permissionmanager', text=io.environment['permission_allow_text'],
                    label='audio579_MIC_user_consent_' + role)
                row['consent'] = selected
            deadline = time.monotonic() + 90
            while True:
                body = shell('if test -f ' + shlex.quote(remote) + ' && test ! -L ' + shlex.quote(remote) +
                    '; then cat ' + shlex.quote(remote) + '; else echo MISSING; fi', role + '_read')
                if body != 'MISSING\n':
                    rows = [loads(line) for line in body.splitlines()]
                    if provider is not None: provider.poll(request, rows)
                    terminal = [item for item in rows if item['operation'] == request['operation'] and item['event'] == 'end']
                    if terminal: break
                need(time.monotonic() < deadline, 'actual caller never completed: ' + action)
                time.sleep(.2)
            identity = process(role, role + '_' + action + '_after')
            selected_rows = [item for item in rows if item['operation'] == request['operation']]
            need(selected_rows and len({item['filesDir'] for item in selected_rows}) == 1, 'one actual process sandbox per operation')
            files_dir = selected_rows[0]['filesDir']
            need(files_dir == '/data/storage/el2/base/haps/entry/files', 'actual module UIAbility sandbox')
            sandbox = '/proc/' + str(identity['pid']) + '/root' + files_dir + '/audio579-' + io.run_id + '.jsonl'
            stat_script = 'test ! -L ' + shlex.quote(remote) + ' && test ! -L ' + shlex.quote(sandbox) + ' && stat -c ' + shlex.quote('%d:%i:%u:%F') + ' ' + shlex.quote(remote) + ' ' + shlex.quote(sandbox)
            linked = shell(stat_script, role + '_' + action + '_live_writer_inode').splitlines()
            need(len(linked) == 2 and linked[0] == linked[1] and
                 re.fullmatch('[0-9]+:[1-9][0-9]*:' + str(identity['uid']) + ':regular file', linked[0]), 'real journal belongs to actual live UID/sandbox inode')
            need(shell(dependency('guest_process_identity').starttime_shell(str(identity['pid'])), role + '_' + action + '_writer_generation').strip() ==
                 str(identity['birth_ticks']), 'same actual PID generation after raw journal identity')

            path = io.output / (role + '-' + request['operation'] + '.jsonl')
            io.receive(remote, path, 'audio579_' + role + '_journal')
            row.update(journal=ref(path), identity=identity)
            tree, layout = io.ui.layout(bundle=name, label='audio579_' + role + '_visible')
            node = dependency('guest_ui').select_node(tree, name, identifier='audio579-visible-caller')
            row['UI'] = dict(layout=ref(layout), selected=node, capture=io.frame('audio579_' + role + '_frame'))
            # Keep every raw terminal; full semantic replay happens later.
            own = [item for item in rows if item['operation'] == request['operation']]
            need(all(item['uid'] == identity['uid'] and item['pid'] == identity['pid'] for item in own), 'raw caller UID/PID')
            thrown = [item for item in own if item['event'] == 'throw']
            if expected_boundary:
                codes = (communication_source['ordinary_system_app_denial'],) if role == 'ordinary' and action == 'communication' else (201, 202)
                native = [item for item in own if item['event'] in ('throw', 'recorder-error') and item['code'] in codes]
                need(len(native) == 1, 'real privilege boundary, not missing API/provider')
            else:
                need(not thrown, 'actual public API failed: ' + repr(thrown))
            row['observed'] = True
        except Exception as error:
            row['error'] = type(error).__name__ + ': ' + str(error)
            report['failures'].append(dict(role=role, action=action, error=row['error']))
        persist()
        return row

    def cleanup():
        if report['cleanup'] is not None: return
        errors, raw = [], []
        for role in reversed(installed):
            name = bundle(CASE, role)
            try:
                raw.append(shell('aa force-stop ' + name, 'cleanup_stop_' + role, allow_failure=True))
                stopped = shell('if pidof ' + name + '; then exit 1; else echo ABSENT; fi', 'cleanup_pid_' + role)
                need(stopped.strip() == 'ABSENT', 'caller kernel process still present')
                row = io.command([io.hdc, '-t', io.target, 'uninstall', name], 'audio579_uninstall_' + role)
                need('uninstall bundle successfully' in row['stdout'].lower(), 'actual caller uninstall did not acknowledge')
                listing = shell('bm dump -a', 'cleanup_BMS_' + role)
                need('com.ohos.' in listing and not re.search(r'(?<![A-Za-z0-9_.])' + re.escape(name) + r'(?![A-Za-z0-9_.])', listing),
                     'full real BMS listing does not prove caller absent')
            except Exception as error:
                errors.append(dict(role=role, error=type(error).__name__ + ': ' + str(error)))
        for remote in stimulus_roots:
            try:
                # The original transport finalizer still owns every live
                # producer. Only finished nonce directories are removed here.
                closed = [item for item in report.get('communication_stimuli', []) + (provider.feeds if provider is not None else []) if item['remote'] == remote]
                need(len(closed) == 1 and closed[0].get('completion', {}).get('exit_code') == 0,
                     'actual ALSA source must finish before its owned files are removed')
                shell('rm -f ' + remote + '/alsa_inject ' + remote + '/challenge.pcm ' + remote +
                    '/producer.pid ' + remote + '/producer.start && rmdir ' + remote,
                    'cleanup_stimulus_' + remote.rsplit('-', 1)[-1])
            except Exception as error:
                errors.append(dict(stimulus=remote, error=type(error).__name__ + ': ' + str(error)))
        if provider is not None:
            try: provider.restore()
            except Exception as error: errors.append(dict(provider='actual-frame-session',error=type(error).__name__+': '+str(error)))
        report['cleanup_errors'].extend(errors)
        report['cleanup'] = dict(installed_roles=installed, errors=errors, original_Owner_finish_still_required=True)
        persist()
        need(not errors, 'Audio10 cleanup uncertain; original owner must stop guest reuse')

    io.register_cleanup(cleanup)
    persist()
    try:
        prepared = io.prepare_callers('audio579', CASE, io.run_id, ROLES, {})
        need(set(prepared['callers']) == set(ROLES), 'all four actual SDK-built/signed roles')
        report['prepared'] = prepared
        for role in ROLES:
            name = bundle(CASE, role)
            report['roles'][role] = dict(prepared=prepared['callers'][role])
            installed.append(role)  # Record intent before actual install.
            row = io.command([io.hdc, '-t', io.target, 'install', prepared['callers'][role]['signed']['path']],
                             'audio579_install_' + role)
            need('success' in row['stdout'].lower(), 'actual four-role HAP installation')
            launch(role, 'identity')
        provider = Session(io, report, shell, process, stimulus_roots); provider.start()
        launch('system', 'permission', consent=True)
        launch('ordinary', 'permission', consent=True)
        baseline = launch('system', 'state'); report['baseline_state_operation'] = baseline['request']['operation']
        report['permission_windows'] = []
        for role in ('ordinary', 'denied'):
            for action in ('communication', 'tone', 'spatial', 'voice'):
                boundary = role == 'ordinary' or action != 'tone'
                before = launch('system', 'state') if boundary else None
                attempted = launch(role, action, expected_boundary=boundary)
                if boundary:
                    after = launch('system', 'state')
                    report['permission_windows'].append(dict(role=role, action=action,
                        before=before['request']['operation'], attempt=attempted['request']['operation'], after=after['request']['operation']))
        before = launch('system', 'state'); attempted = launch('denied', 'recorder', expected_boundary=True); after = launch('system', 'state')
        report['permission_windows'].append(dict(role='denied', action='recorder', before=before['request']['operation'],
            attempt=attempted['request']['operation'], after=after['request']['operation']))
        # The observer is a different actual UID. It receives real OS playback
        # PCM, never a producer-returned data blob or expected-value buffer.
        for cycle in (1, 2):
            for action, producer in (('tone', 'system'), ('player', 'ordinary'), ('soundpool', 'ordinary')):
                begin = launch('observer', 'capture-start')
                produced = launch(producer, action)
                ended = launch('observer', 'capture-stop')
                report.setdefault('PCM_windows', []).append(dict(action=action, cycle=cycle, begin=begin['request']['operation'],
                    producer=produced['request']['operation'], end=ended['request']['operation']))
            # Independent root-only entropy -> actual ALSA loopback hardware.
            # The HAP never receives the source file/seed. This reuses the
            # already built original helper and existing Owner spawn callback.
            source_run = secrets.token_hex(16)
            challenge = io.output / ('communication-source-' + source_run)
            dependency('batch_media_recorder_challenge').pcm.generate(challenge, source_run)
            helper = io.package_inputs['media579_audio']['alsa_inject']
            build = doc(helper['build']); native = build['helpers']['alsa_inject']
            need(build['status'] == 'pass_compile_link_ONLY' and build['installed_runtime_profile']['profile']['archive']['sha256'] == io.archive_sha256 and
                 ref(checked(helper['binary']))['sha256'] == native['binary_sha256'], 'same genuine product C ALSA helper')
            remote = '/data/local/tmp/qemu-mic-' + source_run; stimulus_roots.append(remote)
            shell('test ! -e ' + remote + ' && mkdir -m 0700 ' + remote, 'create_independent_ALSA_source')
            for local, name, mode in ((checked(helper['binary']), 'alsa_inject', '0700'),
                                      (challenge / 'challenge.pcm', 'challenge.pcm', '0600')):
                io.send(local, remote + '/' + name, 'audio579_root_only_' + name.replace('.', '_'))
                need(shell('chmod ' + mode + ' ' + remote + '/' + name + ' && sha256sum ' + remote + '/' + name,
                    'source_file_identity').split() == [ref(local)['sha256'], remote + '/' + name], 'actual independent ALSA source bytes')
            marker = '__PCM_CHILD_EXIT_' + secrets.token_hex(16) + '__='
            script = dependency('guest_process_identity').producer_shell(remote, marker)
            key = io.spawn_guest(script, 'audio579_real_ALSA_communication_source')
            stimulus = dict(run=source_run, remote=remote, manifest=ref(challenge / 'challenge.json'),
                PCM=ref(challenge / 'challenge.pcm'), helper=helper, command=script, transport_key=key)
            report.setdefault('communication_stimuli', []).append(stimulus); persist()
            # Observe the real native feeding row before dispatch; elapsed time
            # or an app-ready flag cannot substitute for this hardware edge.
            deadline = time.monotonic() + 10
            while '"event":"feeding"' not in io._long[key]['err'].read_text():
                need(time.monotonic() < deadline, 'actual ALSA hardware feeding never began')
                time.sleep(.1)
            performed = launch('system', 'communication'); stimulus['operation'] = performed['request']['operation']
            recorded = launch('ordinary', 'recorder'); stimulus['recorder_operation'] = recorded['request']['operation']
            completed = io.wait(key, timeout=40)
            stimulus['completion'] = dict(io.ref_receipt(completed), **{'exit_code': completed['exit_code']})
            need(completed['exit_code'] == 0 and completed['transport_exit_code'] == 0, 'actual independent ALSA source finished')
        launch('system', 'spatial')
        for cycle, (phrase, positive, negative) in enumerate(PHRASES):
            if cycle: launch('system', 'permission', consent=True)
            performed = launch('system', 'voice', phrase=phrase)
            provider.complete_operation(performed)
        launch('system', 'permission', consent=True)
        provider.collect()
        midi = launch('ordinary', 'midi')
        op = midi['request']['operation']
        remote = '/data/app/el2/100/base/' + bundle(CASE, 'ordinary') + '/haps/entry/files/audio579-midi-' + io.run_id + '-' + op + '.jsonl'
        if shared_midi is not None:
            from usb579_shared import SharedDevice
            need(type(shared_midi) is SharedDevice, 'fixed original two-IO USB/MIDI session')
            report['midi_usb_shared'] = shared_midi.collect(io, midi['request'], remote)
            persist()
        deadline = time.monotonic() + 60
        while True:
            text = shell('if test -f ' + shlex.quote(remote) + '; then tail -n 1 ' + shlex.quote(remote) + '; else echo MISSING; fi', 'midi_end')
            if text.startswith('{') and loads(text).get('event') == 'end': break
            need(time.monotonic() < deadline, 'actual public MIDI native command incomplete')
            time.sleep(.2)
        actual_stat = shell('test ! -L ' + shlex.quote(remote) + ' && stat -c "%u %s %i" ' + shlex.quote(remote), 'midi_native_owner_inode')
        midi_uid, midi_size, midi_inode = map(int, actual_stat.split())
        need(midi['identity'] is not None and midi_uid == midi['identity']['uid'] and
             0 < midi_size <= 2 * 1024 * 1024 and midi_inode > 0, 'actual MIDI journal private UID/size/inode')
        live = process('ordinary', 'midi_native_finished')
        need(live == midi['identity'], 'native MIDI must finish in the original live app process generation')
        midi_maps = shell('cat /proc/' + str(live['pid']) + '/maps', 'midi_native_live_mappings')
        need('libaudio579midi.so' in midi_maps and 'libohmidi.so' in midi_maps, 'actual app loaded the original MIDI C addon and product library')
        midi_raw = shell('cat ' + shlex.quote(remote), 'midi_complete_native_journal')
        local = io.output / 'midi-native.jsonl'
        midi_sha = shell('sha256sum ' + shlex.quote(remote), 'midi_native_sha_before')
        io.receive(remote, local, 'audio579_midi_native')
        need(midi_raw == local.read_text() and midi_sha.split() == [ref(local)['sha256'], remote] and
             shell('sha256sum ' + shlex.quote(remote), 'midi_native_sha_after') == midi_sha, 'complete actual native MIDI read and immutable transferred bytes')
        need(local.stat().st_size == midi_size, 'complete actual MIDI native transfer')
        report['midi_native'] = ref(local)
        report['midi_native_identity'] = dict(operation=op, process=live, remote=remote,
            uid=midi_uid, bytes=midi_size, inode=midi_inode, actual_stat=actual_stat, mappings=midi_maps)
        # These are decoders of real new-QEMU AudioRecorder files, not host
        # capability checks. The exact fixed tools are owned by this same IO.
        for item in report['requests']:
            if item['request']['action'] != 'recorder' or item['role'] != 'ordinary' or item['journal'] is None or item['error'] is not None: continue
            rows = [loads(line) for line in checked(item['journal']).read_text().splitlines()
                    if loads(line)['operation'] == item['request']['operation']]
            files = [loads(row['value']) for row in rows if row['event'] == 'recorder-file-finished']
            need(len(files) == 1 and 1024 <= files[0]['bytes'] <= 16 * 1024 * 1024, 'actual AudioRecorder output file')
            name = Path(files[0]['path']).name
            need(name == 'audio579-recorder-' + io.run_id + '-' + item['request']['operation'] + '.m4a', 'nonce-owned actual recording')
            remote = '/data/app/el2/100/base/' + bundle(CASE, item['role']) + '/haps/entry/files/' + name
            need(shell('stat -c "%u %s" ' + shlex.quote(remote), 'recorder_actual_file_owner').split() ==
                 [str(item['identity']['uid']), str(files[0]['bytes'])], 'real private recording owner/size')
            local = io.output / name; recorded_sha = shell('sha256sum ' + shlex.quote(remote), 'recorder_sha_before')
            io.receive(remote, local, 'audio579_real_recorder_file')
            need(recorded_sha.split() == [ref(local)['sha256'], remote] and shell('sha256sum ' + shlex.quote(remote), 'recorder_sha_after') == recorded_sha, 'actual guest finalized AudioRecorder bytes')
            decoder_tools = {name: ref(Path('/opt/homebrew/bin/' + name).resolve()) for name in ('ffprobe', 'ffmpeg')}
            probe_argv = ['/usr/bin/nice', '-n', '10', '/opt/homebrew/bin/ffprobe', '-v', 'error',
                          '-show_streams', '-show_packets', '-of', 'json', str(local)]
            probe = io.command(probe_argv, 'audio579_consume_actual_recording_metadata', timeout=60)
            decoded = io.output / (name + '.pcm')
            decode_argv = ['/usr/bin/nice', '-n', '10', '/opt/homebrew/bin/ffmpeg', '-v', 'error', '-nostdin',
                           '-threads', '1', '-i', str(local), '-map', '0:a:0', '-t', '5', '-ac', '2', '-ar', '48000',
                           '-c:a', 'pcm_s16le', '-f', 's16le', '-n', str(decoded)]
            consumed = io.command(decode_argv, 'audio579_consume_actual_recording_PCM', timeout=60)
            report.setdefault('recorded_audio', []).append(dict(operation=item['request']['operation'],
                file=ref(local), metadata=probe['stdout_ref'], decoded=ref(decoded),
                metadata_command=io.ref_receipt(probe), decode_command=io.ref_receipt(consumed),
                decoder_tools=decoder_tools, decoder_invocations={name: '/opt/homebrew/bin/' + name for name in ('ffprobe', 'ffmpeg')}))
            need(all(Path('/opt/homebrew/bin/' + name).resolve() == checked(row) for name, row in decoder_tools.items()), 'actual invoked decoder targets unchanged')
        abandoned = launch('observer', 'capture-start')
        old = abandoned['identity']
        shell('aa force-stop ' + bundle(CASE, 'observer'), 'abrupt_observer_death')
        need(shell('if pidof ' + bundle(CASE, 'observer') + '; then exit 1; else echo ABSENT; fi', 'abrupt_observer_absent').strip() == 'ABSENT',
             'actual observer process death required')
        state = launch('system', 'state')
        rebuilt = launch('observer', 'identity')
        need(old is not None and rebuilt['identity'] is not None and
             (old['pid'], old['birth_ticks']) != (rebuilt['identity']['pid'], rebuilt['identity']['birth_ticks']),
             'actual process rebuild, not a relabeled same process')
        report['observer_death_rebuild'] = dict(abandoned_operation=abandoned['request']['operation'], old=old,
            absence_state_operation=state['request']['operation'], rebuilt=rebuilt['identity'])
        # Preserve each independently captured PCM using the caller-observed
        # sandbox and native UID/inode before any caller can be uninstalled.
        for item in report['requests']:
            if item['journal'] is None: continue
            for row in [loads(line) for line in checked(item['journal']).read_text().splitlines()]:
                if row['operation'] != item['request']['operation'] or row['event'] != 'capture-started' or \
                   row['operation'] == report['observer_death_rebuild']['abandoned_operation']: continue
                value = loads(row['value']); name = Path(value['path']).name
                need(re.fullmatch('audio579-' + io.run_id + '-[a-f0-9]{32}\\.pcm', name), 'nonce capture path')
                remote = '/data/app/el2/100/base/' + bundle(CASE, item['role']) + '/haps/entry/files/' + name
                metadata = shell('test ! -L ' + shlex.quote(remote) + ' && stat -c "%u %s %i" ' + shlex.quote(remote), 'PCM_owner')
                uid, size, inode = map(int, metadata.split())
                need(uid == item['identity']['uid'] and 0 < size <= 16 * 1024 * 1024 and inode > 0,
                     'actual capture owner, inode and bounded nonempty bytes')
                local = io.output / name; pcm_sha = shell('sha256sum ' + shlex.quote(remote), 'PCM_sha_before')
                io.receive(remote, local, 'audio579_PCM')
                need(pcm_sha.split() == [ref(local)['sha256'], remote] and shell('sha256sum ' + shlex.quote(remote), 'PCM_sha_after') == pcm_sha, 'actual complete immutable captured PCM transfer')
                need(local.stat().st_size == size, 'real PCM transfer incomplete')
                report.setdefault('PCM', []).append(dict(role=item['role'], operation=row['operation'], file=ref(local),
                    bytes=size, uid=uid, inode=inode, remote=remote, metadata=metadata))
        for role in ROLES: launch(role, 'cleanup')
        final = launch('system', 'state'); report['final_state_operation'] = final['request']['operation']
    except Exception as error:
        report['failures'].append(dict(stage='original-audio10', error=type(error).__name__ + ': ' + str(error)))
    finally:
        cleanup()
        before_close = io.output / 'io-before-original-close.json'
        with before_close.open('xb') as stream: stream.write((io.output / 'io.json').read_bytes())
        report['io_snapshot_before_original_close'] = ref(before_close)
        persist()
    return ref(output)
