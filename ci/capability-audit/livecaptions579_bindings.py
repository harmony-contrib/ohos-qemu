"""Concrete original-OwnedIO commands for the packaged English caption provider.

No Owner/Runner/VM/process constructor, mocked authorization or input-text path.
"""
from pathlib import Path
import json
import re
import secrets
import shlex
import time
import zipfile

from capability578_owned_io import require, reference
from settings_idle579_bindings import load_ref, receipt
from hap_identity_binding import strict_json, bms_application_identity
from guest_process_identity import starttime_shell, uids_shell
from batch_media_knowledge_suite import assert_bundles_absent
from batch_network_openvpn_runtime_collect import capture_snapshot
from guest_ui import select_node, NodeNotReady, LayoutNotReady
from livecaptions579_project import BUNDLES, source_files, asset_destinations, permissions
from livecaptions579_provider_project import BUNDLE, ABILITY, PERMISSIONS

ROW_KEYS = {'run','boot','operation','event','value','code','uid','pid','seq','uptimeMs','filesDir'}
ACTIONS = {'control': {'save','configure','restore','state'}, 'ordinary': {'forbidden-decision','forbidden-provider'},
           'media': {'play-a','play-b'}, 'private': {'play-a','play-b'}}


class Bindings:
    def __init__(self, io):
        require(re.fullmatch('[a-f0-9]{32}', io.run_id), 'actual original fresh run required')
        self.io, self.run = io, io.run_id
        self.roles, self.commands, self.reads = {}, [], []
        self.rows, self.prefixes, self.writers = {}, {}, {}
        self.install_intents, self.cleaned, self.ui_reads, self.scans = [], False, [], []
        self.saved, self.restored = None, False
        self.native_maps = []
        io.register_cleanup(self.cleanup)

    def shell(self, script, label, allow_failure=False, timeout=60):
        row = self.io.shell(script, 'captions579_' + label, timeout=timeout, allow_failure=True)
        self.commands.append(receipt(self.io, row, script))
        if not allow_failure: require(row['exit_code'] == 0, 'actual guest operation failed: ' + label)
        return row['stdout']

    def command(self, argv, label):
        row = self.io.command(argv, 'captions579_' + label, allow_failure=True)
        self.commands.append(receipt(self.io, row))
        require(row['exit_code'] == 0, 'actual HDC operation failed: ' + label)
        return row['stdout']

    def boot(self):
        require(self.shell('cat /proc/sys/kernel/random/boot_id', 'boot').strip() == self.io.boot_id,
                'actual one held guest boot changed')

    def prepare(self):
        self.boot()
        self.inputs = self.io.package_inputs['livecaptions579']
        require(self.inputs['archive_sha256'] == self.io.archive_sha256 and
            self.inputs['language'] == 'en' and self.inputs['model'] == 'whisper-tiny.en' and
            load_ref(self.inputs['admission']) and load_ref(self.inputs['provider_hap']),
            'original admitted packaged English-provider input receipts required')
        speakers = set()
        for key in ('a','b'):
            item = self.inputs['speech'][key]
            require(load_ref(item['audio']) and load_ref(item['license']) and load_ref(item['groundtruth']) and
                type(item['contains']) is list and item['contains'] and all(type(x) is str and len(x) >= 12 for x in item['contains']),
                'independently licensed/pinned real speech and groundtruth required')
            utterance = item['utterance_id']
            require(re.fullmatch(r'[0-9]+-[0-9]+-[0-9]+', utterance), 'original LibriSpeech utterance ID required')
            lines = [line[len(utterance)+1:] for line in load_ref(item['groundtruth']).decode('utf-8').splitlines()
                     if line.startswith(utterance+' ')]
            require(len(lines)==1 and all(re.sub(r'[^a-z0-9]+',' ',text.lower()).strip() in
                re.sub(r'[^a-z0-9]+',' ',lines[0].lower()).strip() for text in item['contains']),
                'oracle must come from the exact independently pinned original transcript line')
            speakers.add(utterance.split('-')[0])
        require(len(speakers)==2, 'two different original speakers required')
        require(self.inputs['speech']['a']['audio']['sha256'] != self.inputs['speech']['b']['audio']['sha256'],
                'two distinct real speech waveforms required')
        raw = self.shell('bm dump -n ' + BUNDLE, 'provider_bms')
        self.provider = bms_application_identity(raw, BUNDLE)
        doc = strict_json(raw[raw.index('{'):])
        require(doc['applicationInfo']['isSystemApp'] is True and doc['applicationInfo']['appPrivilegeLevel'] == 'system_basic' and
                set(doc['reqPermissions']) == set(PERMISSIONS), 'actual product provider privilege/permission vector differs')
        paths = [m['hapPath'] for m in doc['hapModuleInfos'] if m.get('hapPath')]
        require(len(paths) == 1 and paths[0].startswith('/system/app/'),
                'provider must be genuinely preinstalled in the selected new image')
        require(self.shell('sha256sum ' + shlex.quote(paths[0]), 'provider_hap_hash').strip() ==
            self.inputs['provider_hap']['sha256'] + '  ' + paths[0], 'actual packaged provider differs from built/signed input')
        self.provider['hap_path'] = paths[0]
        kernel = self.shell('uname -m', 'guest_arch').strip()
        self.abi = {'aarch64':'arm64-v8a','x86_64':'x86_64','armv7l':'armeabi-v7a'}[kernel]
        require(self.inputs['abi'] == self.abi, 'actual guest/HAP native ABI differs')
        with zipfile.ZipFile(self.inputs['provider_hap']['path']) as hap:
            require(hap.read('ets/modules.abc') and len(hap.namelist()) == len(set(hap.namelist())), 'actual signed product ABC required')
            for library, ref in self.inputs['libraries'].items():
                require(library in {'libsherpa_onnx.so','libsherpa-onnx-c-api.so','libonnxruntime.so','libc++_shared.so'} and
                    hap.read('libs/' + self.abi + '/' + library) == load_ref(ref), 'actual selected provider native bytes differ')
        require(set(self.inputs['libraries']) == {'libsherpa_onnx.so','libsherpa-onnx-c-api.so','libonnxruntime.so','libc++_shared.so'},
                'complete real native inference dependency closure required')
        prepared = self.io.prepare_callers('livecaptions579', 'end-to-end', self.run, tuple(BUNDLES), {})
        require(prepared['case'] == 'end-to-end' and prepared['run_id'] == self.run and prepared['boot_id'] == self.io.boot_id and
                set(prepared['callers']) == set(BUNDLES) and prepared['audio_fixtures'] ==
                {key:self.inputs['speech'][key]['audio'] for key in ('a','b')} and prepared['license_fixtures']==
                {key:self.inputs['speech'][key]['license'] for key in ('a','b')}, 'fixed actual caller/audio/license preparation differs')
        for role, row in prepared['callers'].items():
            require(row['bundle'] == BUNDLES[role] and row['build_commands'] and row['sign_commands'] and row['verify_commands'],
                    'original actual compile/sign/verification receipts required')
            for name in ('unsigned','signed','verified_profile','signing'): load_ref(row[name])
            for path, text in source_files('end-to-end', self.run, role, {}).items():
                require((Path(row['project']) / path).read_text() == text, 'actual fixture source differs')
            for key, path in asset_destinations('end-to-end', role).items():
                item=self.inputs['speech'][key.removeprefix('license_')]
                ref=item['license'] if key.startswith('license_') else item['audio']
                require((Path(row['project']) / path).read_bytes() == load_ref(ref),
                        'actual independent renderer audio/license asset differs')
            self.roles[role] = {'prepared':row}
        return prepared

    def install(self, role):
        bundle = BUNDLES[role]
        assert_bundles_absent(self.shell('bm dump -a','before_'+role), [bundle])
        self.install_intents.append(role)
        self.command([self.io.hdc,'-t',self.io.target,'install',self.roles[role]['prepared']['signed']['path']], 'install_'+role)
        raw = self.shell('bm dump -n '+bundle,'bms_'+role)
        identity = bms_application_identity(raw,bundle)
        doc = strict_json(raw[raw.index('{'):])
        require(set(doc.get('reqPermissions',[]))==set(permissions(role)) and
            doc['applicationInfo']['appPrivilegeLevel']==('system_basic' if role=='control' else 'normal') and
            doc['applicationInfo']['isSystemApp']==(role=='control'), 'actual distinct fixture permission/APL vector differs')
        require(identity['uid'] != self.provider['uid'] and all(r.get('identity',{}).get('uid') != identity['uid']
            for r in self.roles.values()), 'independent actual provider/caller UIDs required')
        self.roles[role].update(identity=identity,remote='/data/app/el2/100/base/'+bundle+'/haps/entry/files')
        return identity

    def request(self, role, action, stream_id=None):
        require(action in ACTIONS[role], 'fixed actual fixture action required')
        operation = secrets.token_hex(16)
        argv = ['aa','start','-b',BUNDLES[role],'-a','EntryAbility','--ps','run',self.run,'--ps','boot',self.io.boot_id,
                '--ps','operation',operation,'--ps','action',action]
        if stream_id is not None:
            require(role=='ordinary' and type(stream_id) is int and stream_id>0, 'genuine live target stream ID required')
            argv += ['--pi','streamId',str(stream_id)]
        self.shell(shlex.join(argv),'request_'+role+'_'+action.replace('-','_'))
        return operation

    def _writer(self, role, path, row):
        pid = row['pid']; key = (role, path)
        require(row['uid'] == self.roles[role]['identity']['uid'] and type(pid) is int and pid > 1 and
            re.fullmatch('live-captions579-' + self.run + '-' + str(pid) + r'-[a-f0-9]{32}\.jsonl', Path(path).name) and type(row['filesDir']) is str and
            row['filesDir'] in ('/data/storage/el2/base/haps/entry/files', self.roles[role]['remote']) and
            '..' not in Path(row['filesDir']).parts and str(Path(row['filesDir'])) == row['filesDir'],
            'actual per-PID UID/filesDir journal binding differs')
        if key in self.writers:
            require(row['filesDir'] == self.writers[key]['filesDir'], 'writer sandbox path changed')
            return
        sandbox = '/proc/' + str(pid) + '/root' + row['filesDir'] + '/' + Path(path).name
        raw = self.shell(starttime_shell(str(pid)), 'writer_start_' + role)
        require(re.fullmatch('[1-9][0-9]*\n?', raw), 'actual writer process start ticks absent')
        start = int(raw.strip())
        uids = self.shell(uids_shell(str(pid)), 'writer_uids_' + role)
        require(uids.split() == [str(row['uid'])] * 4, 'all four actual writer UIDs differ')
        meta = self.shell('test ! -L ' + shlex.quote(path) + ' && stat -c ' + shlex.quote('%d:%i:%u:%F') +
            ' ' + shlex.quote(path) + ' ' + shlex.quote(sandbox), 'writer_inode_' + role)
        lines = meta.splitlines()
        require(len(lines) == 2 and lines[0] == lines[1] and re.fullmatch(
            '[0-9]+:[1-9][0-9]*:' + str(row['uid']) + ':regular file', lines[0]),
                'actual sandbox/root journal inode ownership differs')
        maps = self.shell('cat /proc/' + str(pid) + '/maps', 'writer_maps_' + role)
        require(self.shell(starttime_shell(str(pid)), 'writer_start_after_' + role).strip() == str(start),
                'actual writer process generation changed')
        self.writers[key] = {'start_ticks': start, 'inode': lines[0], 'path': path,
                             'filesDir': row['filesDir'], 'commands_end': len(self.commands)}

    def collect(self, role):
        require(role in self.roles and 'remote' in self.roles[role], 'installed real journal role required')
        remote = self.roles[role]['remote']
        pattern = remote + '/live-captions579-' + self.run + '-*.jsonl'
        marker = '__CAPTIONS579_' + secrets.token_hex(16) + '__'
        script = ('for idle579_file in ' + pattern + '; do test -f "$idle579_file" || continue; '
            'test ! -L "$idle579_file" || exit 1; printf "' + marker + 'BEGIN:%s\\n" "$idle579_file"; '
            'cat "$idle579_file" || exit 1; printf "\\n' + marker + 'END\\n"; done')
        raw = self.shell(script, 'journal_' + role)
        self.reads.append({'role': role, 'command': len(self.commands)-1, 'marker': marker})
        pieces = raw.split(marker + 'BEGIN:')
        require(pieces[0] == '', 'unexpected journal capture prefix')
        for piece in pieces[1:]:
            path, rest = piece.split('\n', 1)
            require(re.fullmatch(re.escape(remote + '/live-captions579-' + self.run + '-') +
                r'[1-9][0-9]*-[a-f0-9]{32}\.jsonl', path) and rest.endswith('\n' + marker + 'END\n'),
                    'actual complete finite journal frame differs')
            body = rest[:-len('\n' + marker + 'END\n')]
            require(len(body.encode()) <= 16 * 1024 * 1024 and
                body.startswith(self.prefixes.get(path, '')), 'actual append-only journal prefix changed')
            if not body.endswith('\n'):
                continue  # Retain raw; wait for the writer's complete fsynced row.
            parsed = [strict_json(line) for line in body.splitlines()]
            require(parsed, 'empty file cannot prove an actual request')
            previous_time = -1
            for number, row in enumerate(parsed, 1):
                require(type(row) is dict and set(row) == ROW_KEYS and row['run'] == self.run and
                    row['boot'] == self.io.boot_id and re.fullmatch('[a-f0-9]{32}', row['operation']) and
                    type(row['seq']) is int and row['seq'] == number and type(row['uptimeMs']) is int and
                    row['uptimeMs'] >= previous_time and type(row['code']) is int and
                    type(row['event']) is str and type(row['value']) is str, 'actual raw typed journal differs')
                previous_time = row['uptimeMs']; self._writer(role, path, row)
            self.prefixes[path] = body; self.rows[path] = parsed
        return [r for path, values in self.rows.items() if '/' + BUNDLES[role] + '/' in path for r in values]

    def wait(self, role, operation, event, timeout=60, allow_error=False):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            rows = [r for r in self.collect(role) if r['operation']==operation]
            if not allow_error: require(not [r for r in rows if r['event']=='error'], 'actual typed fixture error')
            found = [r for r in rows if r['event']==event]
            if found:
                require(len(found)==1, 'one actual complete fixture event required')
                return found[0]
            time.sleep(.2)
        raise ValueError('actual fixture deadline: '+role+'/'+event)

    def state(self):
        op = self.request('control','state')
        return strict_json(self.wait('control',op,'state')['value'])

    def scan(self, identity, label):
        raw, parsed = capture_snapshot(lambda script, sub: self.shell(script,re.sub('[^A-Za-z0-9_-]','_',sub)),
            'caption579_'+label,self.io.boot_id,mode='uid',uid=identity['uid'],bundle=identity['bundle'])
        self.scans.append({'label':label,'identity':identity,'snapshot':parsed})
        return parsed

    def logs(self): return self.shell('hilog -x','logs')
    def snapshot(self): return self.shell('aa dump -a -u 100','ams')

    def layout(self, bundle, label):
        value,path = self.io.ui.layout(bundle=bundle,label='captions579_'+label)
        self.ui_reads.append({'kind':'layout','label':label,'bundle':bundle,'raw':reference(path)})
        return value

    def node(self, bundle, identifier, timeout=60):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            try: return select_node(self.layout(bundle,identifier),bundle,identifier=identifier)
            except (NodeNotReady,LayoutNotReady): time.sleep(.2)
        raise ValueError('actual visible node deadline: '+identifier)

    def click(self, bundle, identifier):
        self.node(bundle,identifier)
        result=self.io.ui.click(bundle,identifier=identifier,label='captions579_'+identifier)
        self.ui_reads.append({'kind':'click','identifier':identifier,'bundle':bundle,
            'raw':reference(result['layout']),'selected':result['selected_node']})
        return result

    def frame(self,label):
        result=self.io.frame('captions579_'+label)
        self.ui_reads.append({'kind':'frame','label':label,'result':result})
        return result

    def chord(self):
        down=[{'type':'key','data':{'down':True,'key':{'type':'qcode','data':key}}} for key in ('volumeup','volumedown')]
        up=[{'type':'key','data':{'down':False,'key':{'type':'qcode','data':key}}} for key in ('volumedown','volumeup')]
        try:
            actual=self.io.qmp('input-send-event',{'events':down})
            require(actual['completed'] is True, 'actual QMP key press failed')
            time.sleep(3.5)
        finally:
            actual=self.io.qmp('input-send-event',{'events':up})
            require(actual['completed'] is True, 'actual QMP key release failed')

    def native_identity(self, pid):
        require(type(pid) is int and pid>1, 'actual trace PID required')
        start=self.shell(starttime_shell(str(pid)), 'provider_start').strip()
        require(re.fullmatch('[1-9][0-9]*',start), 'actual provider start ticks absent')
        require(self.shell(uids_shell(str(pid)),'provider_uids').split()==[str(self.provider['uid'])]*4,
            'actual inference process four UIDs differ')
        maps=self.shell('cat /proc/'+str(pid)+'/maps','provider_maps')
        paths=set()
        for line in maps.splitlines():
            fields=line.split(None,5)
            require(len(fields)>=5, 'incomplete actual process map record')
            if len(fields)==6 and fields[5].startswith('/'): paths.add(fields[5])
        actual={}
        for library,ref in self.inputs['libraries'].items():
            matches=[path for path in paths if Path(path).name==library]
            require(len(matches)==1 and ' (deleted)' not in matches[0], 'one actual loaded native inference library required: '+library)
            path='/proc/'+str(pid)+'/root'+matches[0]
            got=self.shell('sha256sum '+shlex.quote(path),'mapped_'+re.sub('[^A-Za-z0-9_-]','_',library)).split()
            require(got==[ref['sha256'],path], 'actual inference mapping bytes differ from packaged ABI library')
            actual[library]={'mapping':matches[0],'sha256':got[0]}
        require(self.shell(starttime_shell(str(pid)),'provider_start_after').strip()==start,
            'actual inference process changed during native-byte inspection')
        row={'pid':pid,'uid':self.provider['uid'],'start_ticks':int(start),'libraries':actual,'commands_end':len(self.commands)}
        self.native_maps.append(row)
        return row

    def recover(self):
        self.shell('aa force-stop '+BUNDLE,'provider_force_stop',allow_failure=True)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if not self.scan(self.provider,'provider_force_stop_wait')['processes']: break
            time.sleep(.2)
        require(not self.scan(self.provider,'provider_force_stop_closed')['processes'], 'actual stopped provider UID remains')
        # Abrupt process death can leave the requested-state key true. Exercise
        # the actual AAMS shortcut: it delivers the genuine close Want to a fresh
        # service, whose own onCreate/onRequest clears state and conditionally
        # stops. No external write to the product key is permitted.
        if self.state()['captionRequested']=='true': self.chord()
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            state=self.state()
            if state['captionRequested']=='false' and not [r for r in state['capturers'] if r['clientUid']==self.provider['uid']] and not self.scan(self.provider,'provider_recover_wait')['processes']:
                return
            time.sleep(.2)
        raise ValueError('actual shortcut recovery failed after provider death')

    def cleanup(self):
        if self.cleaned: return
        failures=[]
        # Stop this product through the real AMS operation. Never kill SystemUI
        # or audio_server to manufacture an empty capture/authorization state.
        try:
            self.recover()
            for number in range(2):
                require(not self.scan(self.provider,'provider_cleanup_'+str(number))['processes'], 'caption provider UID still alive')
            if self.saved is not None and not self.restored and 'identity' in self.roles.get('control',{}):
                op=self.request('control','restore')
                require(strict_json(self.wait('control',op,'restored')['value'])==self.saved, 'actual original shortcut settings did not restore')
                self.restored=True
            if 'identity' in self.roles.get('control',{}):
                state=self.state()
                require(state['captionRequested']=='false' and not [r for r in state['capturers'] if r['clientUid']==self.provider['uid']],
                    'actual released provider capture/user state remains')
        except Exception as error: failures.append('provider: '+str(error))
        for role in reversed(self.install_intents):
            try:
                self.shell('aa force-stop '+BUNDLES[role],'stop_'+role,allow_failure=True)
                self.command([self.io.hdc,'-t',self.io.target,'uninstall',BUNDLES[role]],'uninstall_'+role)
                assert_bundles_absent(self.shell('bm dump -a','absent_'+role),[BUNDLES[role]])
                require('identity' in self.roles[role], 'actual BMS UID needed after a partial installation')
                for number in range(2):
                    require(not self.scan(self.roles[role]['identity'],'cleanup_'+role+'_'+str(number))['processes'],
                        'actual fixture UID remains after uninstall')
            except Exception as error: failures.append(role+': '+str(error))
        self.boot()
        require(not failures, 'actual caption cleanup failed: '+'; '.join(failures))
        self.cleaned=True


def bind(root_io): return Bindings(root_io)
