"""Replay original held-guest wire/API/UI/process/URI observations, never a flag.

This module is called by the real QEMU stage and root aggregate. It creates no
resource and accepts no executable/source selector. A successful narrow replay
still closes neither original A03/A04 nor the complete first-artifact gate.
"""
from collections import Counter
from pathlib import Path
import json
import re
import shlex
import zipfile

from capability578_owned_io import reference, require
from capability578_callers import compiled_fields_match
from settings_idle579_bindings import load_ref
from guest_ui import command_exit, select_node, NodeNotReady
from guest_process_identity import starttime_shell, uids_shell
from hap_identity_binding import bms_application_identity, strict_json
from batch_network_openvpn_runtime_collect import parse_snapshot
from batch_media_knowledge_suite import assert_bundles_absent
from mms_share579_project import BUNDLES, ROLES, CASES, MIME, source_files, module_fields, configure_profile

MMS = 'com.ohos.mms'
CACHE = '/data/app/el2/100/base/' + MMS + '/cache'
LIST = 'if test -d ' + CACHE + '; then ls -1 ' + CACHE + '; else printf "__URI579_NO_CACHE__\\n"; fi'
ROW_KEYS = {'run','boot','archive','role','bundle','operation','object','caseId','action',
    'uid','pid','seq','activeMs','filesDir','event','value','code'}


def same_json(left, right):
    return strict_json(json.dumps(left)) == strict_json(json.dumps(right))


def val(row):
    return strict_json(row['value'])


def names(text):
    if text in ('', '__URI579_NO_CACHE__\n'):
        return []
    require(type(text) is str and text.endswith('\n') and len(text) < 1048576, 'complete actual MMS cache enumeration required')
    values = [v for v in text.splitlines() if v.startswith('senddata-import-')]
    require(len(values) == len(set(values)) and all(re.fullmatch('senddata-import-[a-f0-9-]{36}', v) for v in values),
        'unknown import directory preserved')
    return values


class Replay:
    def __init__(self, document, io):
        self.d, self.io = document, io
        require(document['schema'] == 'actual-mms-share579-boundaries/v1' and
            document['run'] == io.run_id and document['boot_id'] == io.boot_id and document['archive_sha256'] == io.archive_sha256,
            'actual same held guest/package/run required')
        originals = [io.ref_receipt(row) for row in io.receipts]
        require(document['original_io'] == originals[:len(document['original_io'])] and
            len(document['original_io']) <= len(originals), 'evidence is not a prefix of the original Owner IO')
        self.originals, self.body, self.positions = originals, [], []
        for observed in document['commands']:
            row = observed['receipt']
            matches = [i for i, actual in enumerate(originals) if row == actual]
            require(len(matches) == 1 and (not self.positions or matches[0] > self.positions[-1]) and
                row['boot_id'] == io.boot_id and row['timed_out'] is False and row['exit_code'] == 0,
                'raw command absent/reordered/ambiguous or HDC transport failed')
            self.positions.append(matches[0]); stderr = load_ref(row['stderr']).decode()
            require(not any(t in stderr for t in ('[Fail]','HDCFail','device not found','Connect server failed')), 'actual transport stderr failed')
            wire = load_ref(row['stdout']).decode()
            if 'script' in observed:
                prefix = shlex.join(['sh', '-c', observed['script']])
                suffix = row['argv'][4][len(prefix):] if len(row['argv']) == 5 else ''
                match = re.fullmatch(r'; cap578_rc=\$\?; printf "\\n(__CAP578_EXIT_[a-f0-9]{32}__=)%s\\n" "\$cap578_rc"', suffix)
                require(row['argv'][:4] == [io.hdc, '-t', io.target, 'shell'] and
                    row['argv'][4].startswith(prefix) and match, 'actual shell literal/footer differs')
                body, code = command_exit(wire, match[1])
                require(code == row['shell_exit_code'] and load_ref(row['shell_stdout']).decode() == body,
                    'guest status/body differs from the retained transport')
            else:
                body, code = wire, row['exit_code']
            require(load_ref(observed['body']).decode() == body, 'derived body differs from actual wire')
            self.body.append((body, code))
        self.events, self.journal_paths = {}, {}
        self.ui = [self.ui_action(action) for action in document['actions']]
        self.roles = self.identities()
        self.journals()
        self.scans = self.process_scans()

    def cmd(self, index, script=None, code=0):
        require(type(index) is int and 0 <= index < len(self.body), 'actual raw command index required')
        if script is not None:
            require(self.d['commands'][index].get('script') == script, 'actual source-defined command differs')
        body, actual_code = self.body[index]
        require(code is None or actual_code == code, 'actual guest operation failed')
        return body

    def cache(self, index):
        return names(self.cmd(index,LIST))

    def ui_wire(self, index):
        require(type(index) is int and 0 <= index < len(self.originals), 'actual original UITest command index required')
        row = self.originals[index]
        require(row['argv'][:4] == [self.io.hdc, '-t', self.io.target, 'shell'] and len(row['argv']) == 5 and
            row['exit_code'] == 0 and row['timed_out'] is False and row['boot_id'] == self.io.boot_id,
            'original actual UITest command required')
        match = re.fullmatch(r'(.+); task_ui_rc=\$\?; printf "\\n(__UITEST_EXIT_[a-f0-9]{32}__=)%s\\n" "\$task_ui_rc"', row['argv'][4])
        require(match, 'exact actual UITest wire/footer required')
        body, code = command_exit(load_ref(row['stdout']).decode(), match[2])
        require(code == 0 and '[Fail]' not in body and not load_ref(row['stderr']), 'actual UITest failed')
        return match[1], body

    def ui_action(self, action):
        indices = action['original_io_indices']
        require(len(indices) == (3 if 'identifier' in action else 2) and
            indices == list(range(indices[0], indices[0]+len(indices))), 'fresh dump/read/click sequence required')
        dump, _ = self.ui_wire(indices[0]); read, body = self.ui_wire(indices[1])
        require(re.fullmatch(r'cat /data/local/tmp/qemu-capability-ui-[a-f0-9]{32}-[0-9]+\.json', read), 'fresh actual layout path required')
        remote = read[4:]
        require(dump == 'test ! -e ' + remote + ' && uitest dumpLayout -p ' + remote +
            (' -b ' + action['bundle'] if action['bundle'] else ''), 'layout is not bound to its original dump')
        layout = strict_json(load_ref(action['layout']).decode())
        require(layout == strict_json(body), 'local layout differs from actual guest hierarchy')
        if 'identifier' in action:
            node = select_node(layout, action['bundle'], identifier=action['identifier'], clickable=True)
            require(node == action['selected_node'], 'selected node differs from actual visible UI')
            x,y,w,h = node['rect']; script, _ = self.ui_wire(indices[2])
            require(script == 'uitest uiInput click ' + str(x+w//2) + ' ' + str(y+h//2), 'click did not use actual node center')
        return layout

    def identities(self):
        result = {}
        require(set(self.d['roles']) == set(ROLES), 'exact three ordinary roles required')
        for role in ROLES:
            info = self.d['roles'][role]; prepared = info['prepared']
            require(prepared['bundle'] == BUNDLES[role], 'fixed bundle changed')
            for key in ('build_commands','sign_commands','verify_commands'):
                require(prepared[key] and all(row in self.originals and row['exit_code'] == 0 and row['boot_id'] == self.io.boot_id
                    for row in prepared[key]), 'compile/sign/verify not performed by original same-boot Owner')
            for path, text in source_files('boundaries', self.d['run'], role, {}).items():
                target = Path(prepared['project']) / path
                require(target.is_file() and not target.is_symlink() and target.read_text() == text, 'actual caller source overlay changed')
            for kind in ('unsigned','signed'):
                load_ref(prepared[kind])
                with zipfile.ZipFile(prepared[kind]['path']) as hap:
                    require(len(hap.namelist()) == len(set(hap.namelist())) and hap.read('ets/modules.abc'), 'complete real caller HAP required')
                    metadata = strict_json(hap.read('module.json').decode())
                    require(metadata['app']['bundleName'] == BUNDLES[role] and
                        compiled_fields_match(metadata['module'], module_fields('boundaries',role,{})), 'compiled fields/permission lists changed')
            profile = strict_json(load_ref(prepared['verified_profile']).decode())
            require(configure_profile('boundaries')(strict_json(json.dumps(profile)),role,self.io.udid,metadata) == profile,
                'actual ordinary signed profile/UDID/ACL differs')
            text = self.cmd(info['bms_command'], 'bm dump -n ' + BUNDLES[role])
            actual = bms_application_identity(text, BUNDLES[role]); doc = strict_json(text[text.index('{'):])
            require(actual == info['identity'] and doc['applicationInfo']['isSystemApp'] is False and
                doc['applicationInfo']['appPrivilegeLevel'] == 'normal' and doc['reqPermissions'] == [], 'actual ordinary BMS identity/permission surface differs')
            paths = doc['hapModuleInfos']; require(len(paths) == 1 and paths[0]['moduleName'] == 'entry', 'one actual role module required')
            require(self.cmd(info['hash_command'],'sha256sum '+shlex.quote(paths[0]['hapPath'])) ==
                prepared['signed']['sha256']+'  '+paths[0]['hapPath']+'\n', 'installed caller differs from signed real artifact')
            result[role] = actual
        require(len({v['uid'] for v in result.values()}) == 3 and len({v['token_id'] for v in result.values()}) == 3,
            'three independent installed UID/token pairs required')
        facts = strict_json(load_ref(self.d['mms_facts']).decode()); mms = self.d['mms']
        require(facts['schema'] == 'actual-owned-capability579-mms-facts/v1' and facts['boot_id'] == self.io.boot_id and
            facts['package']['archive']['sha256'] == self.io.archive_sha256, 'current package MMS facts missing')
        text = self.cmd(mms['bms_command'], 'bm dump -n '+MMS); doc = strict_json(text[text.index('{'):])
        actual = bms_application_identity(text,MMS)
        require(actual == facts['identity'] == mms['identity'] and doc['applicationInfo'] == facts['actual_applicationInfo'] and
            doc.get('signatureInfo') == facts['actual_signatureInfo'] and doc['reqPermissions'] == facts['actual_reqPermissions'] and
            actual['uid'] not in {v['uid'] for v in result.values()}, 'MMS actual package identity/permission surface differs')
        hap = facts['modules']['entry']['hap']; load_ref(hap)
        require(self.cmd(mms['hash_command'], 'sha256sum '+shlex.quote(mms['hap_path'])) == hap['sha256']+'  '+mms['hap_path']+'\n',
            'MMS installed bytes differ from selected system package export')
        result['mms'] = actual
        return result

    def journals(self):
        prefixes = {}; parsed = {}
        for read in self.d['journal_reads']:
            role, marker, index = read['role'], read['marker'], read['command']
            base = self.d['roles'][role]['remote']
            require(re.fullmatch('__URI579_[a-f0-9]{32}__',marker), 'actual journal framing nonce required')
            pattern = base+'/uri579-'+self.d['run']+'-*.jsonl'
            script = ('for uri579_file in '+pattern+'; do test -f "$uri579_file" || continue; '
                'test ! -L "$uri579_file" || exit 1; printf "'+marker+'BEGIN:%s\\n" "$uri579_file"; '
                'cat "$uri579_file" || exit 1; printf "\\n'+marker+'END\\n"; done')
            parts = self.cmd(index,script).split(marker+'BEGIN:'); require(parts[0] == '', 'unframed journal prefix')
            for part in parts[1:]:
                path, rest = part.split('\n',1)
                require(re.fullmatch(re.escape(base+'/uri579-'+self.d['run']+'-')+r'[1-9][0-9]*-[a-f0-9]{32}\.jsonl',path) and
                    rest.endswith('\n'+marker+'END\n'), 'complete finite journal frame required')
                text = rest[:-len('\n'+marker+'END\n')]
                require(len(text.encode()) <= 16*1024*1024 and text.startswith(prefixes.get(path,'')), 'raw journal was replaced or truncated')
                if not text.endswith('\n'):
                    continue
                rows = [strict_json(line) for line in text.splitlines()]; previous = -1
                for n,row in enumerate(rows,1):
                    require(set(row) == ROW_KEYS and row['run'] == self.d['run'] and row['boot'] == self.io.boot_id and
                        row['archive'] == self.io.archive_sha256 and row['role'] == role and row['bundle'] == BUNDLES[role] and
                        row['uid'] == self.roles[role]['uid'] and type(row['seq']) is int and row['seq'] == n and
                        type(row['activeMs']) is int and row['activeMs'] >= previous and type(row['code']) is int and
                        type(row['value']) is str and re.fullmatch('[a-f0-9]{32}',row['operation']) and row['caseId'] in CASES,
                        'actual nonce journal schema/identity/ordering differs')
                    previous = row['activeMs']; val(row)
                    require(row['event'] not in ('fixture.error','share.error','share.duplicate','mms.error'), 'actual API/fixture error cannot pass')
                parsed[path] = role,rows; prefixes[path] = text
        for writer in self.d['writers']:
            path,role,pid = writer['path'],writer['role'],str(writer['pid'])
            require(path in parsed and parsed[path][0] == role and parsed[path][1] and
                re.fullmatch('uri579-'+self.d['run']+'-'+pid+r'-[a-f0-9]{32}\.jsonl',Path(path).name) and
                all(row['pid'] == int(pid) and row['filesDir'] == writer['filesDir'] for row in parsed[path][1]) and
                writer['uid'] == self.roles[role]['uid'], 'actual writer/journal association differs')
            indices = writer['commands']; require(len(indices) == 4 and indices == list(range(indices[0],indices[0]+4)), 'complete actual writer birth/UID/inode query required')
            require(self.cmd(indices[0],starttime_shell(pid)).strip() == writer['start'] and
                self.cmd(indices[1],uids_shell(pid)).split() == [str(writer['uid'])]*4, 'writer PID birth/UID differs')
            sandbox = '/proc/'+pid+'/root'+writer['filesDir']+'/'+Path(path).name
            script = 'test ! -L '+shlex.quote(path)+' && stat -c '+shlex.quote('%d:%i:%u:%F')+' '+shlex.quote(path)+' '+shlex.quote(sandbox)
            require(self.cmd(indices[2],script).splitlines() == [writer['inode']]*2 and
                re.fullmatch('[0-9]+:[1-9][0-9]*:'+str(writer['uid'])+':regular file',writer['inode']) and
                self.cmd(indices[3],starttime_shell(pid)).strip() == writer['start'], 'actual sandbox file/inode/process generation differs')
            self.journal_paths[path] = writer
        require(set(self.journal_paths) == set(parsed), 'every actual journal must have a live writer binding')
        for path,(role,rows) in parsed.items():
            for row in rows:
                self.events.setdefault((role,row['operation']),[]).append(row)
        for issued in self.d['requests']:
            role,r,index = issued['role'],issued['request'],issued['command']
            argv = ['aa','start','-b',BUNDLES[role],'-a','EntryAbility','-m','entry','-u','100',
                '--ps','request',json.dumps(r,separators=(',',':'))]
            require('start ability successfully' in self.cmd(index,shlex.join(argv)).lower(), 'real AMS fixture dispatch failed')
            incoming = val(self.ev(role,r['operation'],'request'))
            require(strict_json(incoming['parameters']['request']) == r, 'actual received request differs from original launch argv')

    def ev(self, role, operation, event):
        selected = [r for r in self.events.get((role,operation),[]) if r['event'] == event]
        require(len(selected) == 1, 'one actual event required: '+role+'/'+operation+'/'+event)
        return selected[0]

    def process_scans(self):
        out = []
        for item in self.d['process_scans']:
            role = item['role']; index = item['commands_end']-1; body = self.cmd(index)
            head = body.splitlines()[0].split('|'); require(len(head) == 8 and head[:2] == ['BEGIN','PROCESS_V2'], 'complete original process capture required')
            identity = self.roles[role]
            actual = parse_snapshot(body,head[2],self.io.boot_id,mode='uid',uid=identity['uid'],bundle=identity['bundle'])
            require(same_json(actual,item['snapshot']), 'claimed UID/process snapshot differs from complete raw /proc scan')
            out.append(dict(item, snapshot=actual))
        return out

    def service(self, service):
        ids = service['commands']; pid = str(service['pid'])
        require(len(ids) == 5 and ids == list(range(ids[0],ids[0]+5)) and self.cmd(ids[0],'pidof foundation').strip() == pid and
            self.cmd(ids[1],starttime_shell(pid)).strip() == service['birth'] and
            self.cmd(ids[2],uids_shell(pid)).split() == service['uids'] == ['5523']*4 and
            re.search(r'/(?:[A-Za-z0-9_.-]+/)*libupms\.z\.so(?:\n|\s|$)',self.cmd(ids[3],'cat /proc/'+pid+'/maps')) and
            self.cmd(ids[4],starttime_shell(pid)).strip() == service['birth'], 'actual native URI service PID/birth/mapped library differs')

    def native(self, case, role):
        w = self.d['native_windows'][case['native_window']]
        require(w['role'] == role and w['token'] == self.roles[role]['token_id'] and
            case['command_start'] < w['before'] < w['after'] < case['command_end'], 'actual target token/window differs')
        self.service(w['service_before']); self.service(w['service_after'])
        require({k:w['service_before'][k] for k in ('pid','birth','uids')} ==
            {k:w['service_after'][k] for k in ('pid','birth','uids')}, 'URI server generation changed')
        before = self.cmd(w['before'],'hilog -x'); after = self.cmd(w['after'],'hilog -x')
        delta = Counter(after.splitlines())-Counter(before.splitlines())
        pattern = r'URI579_REVOKE token:'+str(w['token'])+r' sandbox:1 unset_result:0 erased:1 remaining:0 policy_cutoff_ns:([1-9][0-9]*)\b'
        matches = [line for line in delta.elements() if re.search(pattern,line)]
        require(matches == [w['line']], 'actual new successful native policy removal/erase record missing/ambiguous')
        stamp = re.match(r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+([1-9][0-9]*)\s+[1-9][0-9]*\s+I\b',matches[0])
        require(stamp and int(stamp[1]) == w['service_before']['pid'] and
            not any('URI579_REVOKE token:'+str(w['token'])+' ' in line and 'unset_result:0 ' not in line for line in delta.elements()),
            'native result belongs to another process or includes failed/unavailable revocation')
        return w

    def clicks(self, case, bundle, identifier):
        return [i for i in range(case['action_start'],case['action_end']) if
            self.d['actions'][i].get('bundle') == bundle and self.d['actions'][i].get('identifier') == identifier]

    def death(self, case, role, native=None):
        start,end = case['command_start'],case['command_end']
        stop = [i for i in range(start,end) if self.d['commands'][i].get('script') == 'aa force-stop '+self.roles[role]['bundle']]
        if native is not None:
            stop = [i for i in stop if native['before'] < i < native['after']]
        require(len(stop) == 1, 'one real source-defined target force-stop required in the cleanup window')
        empties = [s for s in self.scans if s['role'] == role and stop[0] < s['commands_end']-1 < end and
            s['label'].startswith('stopped_'+role+'_') and not s['snapshot']['processes']]
        require(len(empties) == 2, 'two complete actual target-UID absence captures required')
        return stop[0], max(s['commands_end']-1 for s in empties)

    def case(self, case):
        name,object_id = case['case'],case['object']
        require(re.fullmatch('[a-f0-9]{32}',object_id) and case['status'] == 'raw_observed_pending_replay', 'complete actual case required')
        for key,role in (('owner_death','owner'),('receiver_death','receiver'),('after_ui_close','receiver'),('mms_baseline','mms'),
                ('mms_after_attempt','mms'),('mms_death','mms'),('mms_recreated','mms')):
            if key in case:
                require(any(item['role'] == role and same_json(item['snapshot'],case[key]) for item in self.scans),
                    'case process summary is not an actual complete raw UID scan')
        ops = case['operations']; source = case['source']
        creates = [p for p in ops if p['role'] == 'owner' and p['request']['action'] == 'create']
        require(len(creates) == 1, 'one actual owner source creation required')
        created = self.ev('owner',creates[0]['request']['operation'],'owner.file')
        require(val(created) == source and source['run'] == self.d['run'] and source['boot'] == self.io.boot_id and
            source['archive'] == self.io.archive_sha256 and source['object'] == object_id and source['caseId'] == name and
            re.fullmatch('[1-9][0-9]*',source['inode']), 'actual original source owner/inode/nonce differs')
        suffix = '.vcf' if name.startswith('mms-') else '.txt'
        path = '/data/storage/el2/base/files/uri579-source-'+self.d['run']+'-'+object_id+suffix
        body = 'URI579/'+self.d['run']+'/'+object_id+'/'+name+'/original'
        if name.startswith('mms-'):
            body = 'BEGIN:VCARD\r\nVERSION:3.0\r\nFN:'+body+'\r\nEND:VCARD\r\n'
        require(source['path'] == path and source['uri'] == 'file://'+BUNDLES['owner']+path and source['content'] == body,
            'real bounded source bytes/URI differ')
        for issued in ops:
            role,r = issued['role'],issued['request']
            require(r['object'] == object_id and r['caseId'] == name and r['run'] == self.d['run'] and
                r['boot'] == self.io.boot_id and r['archive'] == self.io.archive_sha256, 'operation changed source/epoch')
            if r['action'] in ('owner-read','create'):
                require(val(self.ev(role,r['operation'],'owner.file')) == source, 'fresh owner read/inode changed before cleanup')
        for p in case['probes']:
            role,operation = p['role'],p['operation']
            r = next(v['request'] for v in ops if v['role'] == role and v['request']['operation'] == operation)
            incoming = val(self.ev(role,operation,'probe.incoming'))
            require(r['action'] == 'probe' and r['uri'] == source['uri'] and not incoming.get('uri') and
                incoming.get('flags',0) == 0 and 'ability.params.stream' not in incoming.get('parameters',{}),
                'probe must carry URI as text only and receive no grant')
            read,write = self.ev(role,operation,'file.read'),self.ev(role,operation,'file.write')
            if p['readable']:
                require(name == 'share-owner-death' and role == 'receiver' and read['code'] == 0 and
                    val(read) == {'uri':source['uri'],'content':body}, 'live target must retain its actual grant through grantor death')
            else:
                require(read['code'] == 13900012 and val(read).get('codeType') == 'number' and val(read).get('message'),
                    'actual permission denied required; absent source/generic error cannot pass')
            require(write['code'] == 13900012 and val(write).get('codeType') == 'number' and val(write).get('message'),
                'fresh WRITE permission must be denied')
        require(sum(p['role'] == 'foreign' and p['readable'] is False for p in case['probes']) >= 2,
            'independent never-selected ordinary UID required before and after')
        if name.startswith('share-'):
            self.share(case,source)
        else:
            self.mms(case,source)
        cleanup = [p for p in ops if p['role'] == 'owner' and p['request']['action'] == 'cleanup']
        require(len(cleanup) == 1, 'one original-owner deletion after all observations required')
        deleted = self.ev('owner',cleanup[0]['request']['operation'],'owner.deleted')
        require(val(deleted) == {'uri':source['uri'],'path':path,'exists':False}, 'actual owned source cleanup missing')
        request_index = next(v['command'] for v in self.d['requests'] if v['request'] == cleanup[0]['request'])
        require(request_index > max((self.d['native_windows'][case['native_window']]['after'],)
            if 'native_window' in case else (case['after_log'],)), 'source deletion preceded grant/rejection observation')
        reads = [p for p in ops if p['role'] == 'owner' and p['request']['action'] == 'owner-read']
        require(reads and reads[-1]['request']['operation'] != cleanup[0]['request']['operation'] and
            self.ev('owner',reads[-1]['request']['operation'],'owner.file')['pid'] == deleted['pid'] and
            self.ev('owner',reads[-1]['request']['operation'],'owner.file')['seq'] < deleted['seq'],
            'same-inode/content owner read must precede actual deletion')
        last_read_command = next(v['command'] for v in self.d['requests'] if v['request'] == reads[-1]['request'])
        observation_end = self.d['native_windows'][case['native_window']]['after'] if 'native_window' in case else case['after_log']
        require(observation_end < last_read_command < request_index,
            'actual original source must be re-opened with the same inode/content after release/rejection and before deletion')

    def share(self, case,source):
        name = case['case']; share = [o['request'] for o in case['operations'] if o['request']['action'] == 'share']
        require(len(share) == 1, 'one original caller Share API dispatch required'); r = share[0]
        call = val(self.ev('owner',r['operation'],'share.call'))
        require(call['type'] == 'share' and call['parameters']['uri'] == source['uri'] and
            call['parameters']['ability.params.stream'] == [source['uri']] and call['parameters']['type'] == MIME and
            call['parameters']['ability.want.params.uriPermissionFlag'] == (3 if name == 'share-write-close' else 1),
            'real public Share API payload/flags differ')
        self.ev('owner',r['operation'],'share.opened')
        delivery = dict(r,action='consume',operation=r['delivery'],uri=source['uri'])
        require(case['delivery'] == delivery and strict_json(call['parameters']['ability.subject']) == delivery,
            'actual receiver challenge must be forwarded through public Share')
        incoming = val(self.ev('receiver',r['delivery'],'receiver.incoming'))
        require(incoming['action'] == 'ohos.want.action.sendData' and incoming['type'] == MIME and incoming['flags'] == 1 and
            incoming['uri'] == source['uri'] and incoming['parameters']['ability.params.stream'] == [source['uri']] and
            strict_json(incoming['parameters']['ability.subject']) == delivery, 'actual selected target payload/READ grant differs')
        read,write = self.ev('receiver',r['delivery'],'file.read'),self.ev('receiver',r['delivery'],'file.write')
        require(read['code'] == 0 and val(read) == {'uri':source['uri'],'content':source['content']} and
            write['code'] == 13900012 and val(write)['message'], 'selected ordinary target must read complete bytes and deny WRITE')
        result = val(self.ev('owner',r['operation'],'share.result'))
        require(result['resultCode'] == 0 and result['want']['parameters'] == {'outcome':'launched',
            'selectedBundleName':BUNDLES['receiver'],'selectedModuleName':'entry','selectedAbilityName':'EntryAbility'},
            'actual modal callback/selected component differs')
        require(len(self.clicks(case,BUNDLES['owner'],'uri579-run')) == 1 and
            len(self.clicks(case,'com.ohos.settings','system-share-target-'+BUNDLES['receiver']+'/entry/EntryAbility')) == 1,
            'actual caller UI and target selection required')
        w = self.native(case,'receiver')
        if name in ('share-close','share-write-close'):
            closes = self.clicks(case,BUNDLES['receiver'],'uri579-close')
            require(len(closes) == 1 and self.positions[w['before']] <
                self.d['actions'][closes[0]]['original_io_indices'][-1] < self.positions[w['after']],
                'actual receiver public terminate UI must occur inside the native release window')
            self.ev('receiver',r['delivery'],'receiver.close'); self.ev('receiver',r['delivery'],'ability.destroyed')
            if case['after_ui_close']['processes']:
                self.death(case,'receiver',w)
        else:
            self.death(case,'receiver',w)
        if name == 'share-owner-death':
            owner_stop,owner_gone = self.death(case,'owner')
            require(sum(p['role'] == 'receiver' and p['readable'] is True for p in case['probes']) == 1,
                'live selected target read after grantor death is mandatory')
            still = next(p for p in case['probes'] if p['role'] == 'receiver' and p['readable'])
            issued = next(v['command'] for v in self.d['requests'] if v['request']['operation'] == still['operation'])
            receiver_stop,_ = self.death(case,'receiver',w)
            require(owner_gone < issued < receiver_stop, 'live target fresh read must occur after actual grantor death and before target exit')
        denied = [p for p in case['probes'] if p['role'] == 'receiver' and not p['readable']]
        require(len(denied) == 1, 'same installed selected UID must re-open without grant after target exit')
        at = next(q['command'] for q in self.d['requests'] if q['role'] == 'receiver' and q['request']['operation'] == denied[0]['operation'])
        require(w['after'] < at, 'no-grant receiver probe preceded actual native release')

    def mms(self, case,source):
        name = case['case']; role = 'foreign' if name == 'mms-forged-owner' else 'owner'
        operations = [o['request'] for o in case['operations'] if o['role'] == role and o['request']['action'] == 'mms']
        require(len(operations) == 1, 'one real ordinary MMS sendData invocation required'); r = operations[0]
        expected = {'action':'ohos.want.action.sendData','type':'text/vcard','flags':0 if name == 'mms-no-grant' else 1,
            'uri':source['uri'],'bundleName':MMS,'moduleName':'entry','abilityName':'com.ohos.mms.MainAbility',
            'parameters':{'ability.params.stream':[source['uri']]}}
        require(val(self.ev(role,r['operation'],'mms.call')) == expected, 'real MMS want differs')
        self.ev(role,r['operation'],'mms.opened')
        require(len(self.clicks(case,BUNDLES[role],'uri579-run')) == 1, 'actual ordinary caller UI invocation required')
        initial = [i for i in range(case['command_start'],case['before_log']) if self.d['commands'][i].get('script') == LIST]
        require(initial and not self.cache(initial[0]), 'preserve any preexisting MMS owned import instead of claiming/deleting it')
        if name in ('mms-no-grant','mms-forged-owner'):
            require(len(case['absent']) == 2 and all(not self.cache(i) for i in case['absent']), 'two actual no-import observations required')
            before,after = self.cmd(case['before_log'],'hilog -x'),self.cmd(case['after_log'],'hilog -x')
            fresh = list((Counter(after.splitlines())-Counter(before.splitlines())).elements())
            issued = next(v['command'] for v in self.d['requests'] if v['request'] == r)
            require(case['before_log'] < issued < min(case['absent']) <= max(case['absent']) < case['after_log'],
                'actual negative command/cache/log order differs')
            for i in case['absent']:
                layouts = [n for n in range(case['action_start'],case['action_end']) if self.d['actions'][n]['bundle'] == MMS and
                    self.d['actions'][n]['original_io_indices'][0] > self.positions[i]]
                require(layouts, 'actual current MMS hierarchy after cache absence required')
                tree = self.ui[layouts[0]]
                stack = [(node,'') for node in (tree if isinstance(tree,list) else [tree])]; visible = False
                while stack:
                    node,parent = stack.pop(); attrs = node['attributes']; bundle = attrs.get('bundleName') or parent
                    visible = visible or bundle == MMS and attrs.get('visible') == 'true'
                    stack.extend((child,bundle) for child in node.get('children',[]))
                require(visible, 'actual MMS window must be visible')
                try:
                    select_node(tree,MMS,identifier='mms-senddata-attachment')
                except NodeNotReady:
                    pass
                else:
                    raise ValueError('rejected URI produced an actual attachment UI')
            if name == 'mms-no-grant':
                candidates = [line for line in fresh if 'Cannot import shared file: Shared file requires caller URI READ authorization' in line]
                pids = {int(pid) for pid in case['mms_after_attempt']['processes']}
                require(len(candidates) == 1, 'actual MMS handler READ-authorization rejection missing')
                stamp = re.match(r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+([1-9][0-9]*)\s+[1-9][0-9]*\s+E\b',candidates[0])
                require(stamp and int(stamp[1]) in pids, 'rejection not emitted by actual MMS process')
            else:
                self.service(case['negative_service']); pid = case['negative_service']['pid']
                for fragment in ('erase uri param.','startIndex: 1, uriVec: 2, paramStreamUris: 0'):
                    candidates = [line for line in fresh if fragment in line]
                    require(len(candidates) == 1, 'actual AMS forged URI/stream erasure missing/ambiguous')
                    stamp = re.match(r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+([1-9][0-9]*)\s+[1-9][0-9]*\s+I\b',candidates[0])
                    require(stamp and int(stamp[1]) == pid, 'forged URI erasure not from actual foundation process')
            return
        imported = case['imported']; path = CACHE+'/'+imported['name']+'/source.vcf'
        require(self.cache(imported['cache_command']) == [imported['name']] and
            bytes.fromhex(self.cmd(imported['bytes_command'],'od -An -v -tx1 '+path)) == source['content'].encode(),
            'MMS must independently copy exact original nonce bytes')
        node = select_node(self.ui[imported['ui_action']],MMS,identifier='mms-senddata-attachment')
        require(node['attributes']['text'] == Path(source['path']).name+'\n'+str(len(source['content'].encode()))+' B',
            'actual MMS attachment UI name/size differs')
        w = self.native(case,'mms'); stopped,_ = self.death(case,'mms',w)
        require(imported['bytes_command'] < w['before'], 'native release must follow actual complete MMS copy')
        if name != 'mms-receiver-death':
            clicked = self.clicks(case,MMS,'mms-senddata-cancel')
            require(len(clicked) == 1 and self.positions[w['before']] < self.d['actions'][clicked[0]]['original_io_indices'][-1] <
                min(self.positions[i] for i in case['cancel_absent']) and len(case['cancel_absent']) == 2 and
                all(not self.cache(i) and i < stopped for i in case['cancel_absent']),
                'actual user cancel must remove MMS-owned staging before true recipient exit')
        if name == 'mms-owner-death':
            _,owner_gone = self.death(case,'owner')
            require(bytes.fromhex(self.cmd(case['copy_after_owner_death'],'od -An -v -tx1 '+path)) == source['content'].encode(),
                'actual MMS-owned copy must survive grantor death until user cancel')
            mms_stop,_ = self.death(case,'mms',w)
            require(owner_gone < case['copy_after_owner_death'] < mms_stop, 'MMS-owned nonce copy must be observed after grantor death while recipient lives')
        require(len(case['recreate_absent']) == 2 and all(not self.cache(i) for i in case['recreate_absent']),
            'actual new MMS process must recover its owned staging without receiving a new URI grant')
        require(w['after'] < min(case['recreate_absent']) <= max(case['recreate_absent']) < case['command_end'] and
            any(w['after'] < i < min(case['recreate_absent']) and item.get('script') ==
                'aa start -b com.ohos.mms -a com.ohos.mms.MainAbility -m entry -u 100'
                for i,item in enumerate(self.d['commands'])), 'actual public no-URI recipient recreation command missing/reordered')
        old,new = case['mms_death']['processes'],case['mms_recreated']['processes']
        require(old and new and all(str(pid) not in {str(p) for p in old} or
            all(str(p) != str(pid) or prior['start'] != row['start'] for p,prior in old.items()) for pid,row in new.items()),
            'actual MMS process generation did not change')

    def cleanup(self):
        require(self.d['cleanup_complete'] is True and self.d['failures'] == [], 'actual cleanup/case failure retained')
        last_case = max(case['command_end'] for case in self.d['cases'])
        mms = self.d['mms_cleanup']
        require(mms and len(mms['empty_commands']) == 2 and all(i >= last_case and not self.cache(i) for i in mms['empty_commands']) and
            mms['restored_running'] == bool(self.d['mms']['initial_processes']) and
            bool(mms['processes']) == mms['restored_running'] and
            any(s['role'] == 'mms' and s['label'] == 'mms_cleanup_restored' and same_json(s['snapshot']['processes'],mms['processes'])
                for s in self.scans), 'actual MMS owned-cache cleanup/prior running-state restoration missing')
        for role in ROLES:
            prepared = self.d['roles'][role]['prepared']
            uninstall = [i for i,item in enumerate(self.d['commands']) if item['receipt']['argv'] ==
                [self.io.hdc,'-t',self.io.target,'uninstall',BUNDLES[role]]]
            require(len(uninstall) == 1 and uninstall[0] >= last_case, 'uninstall must follow every source-present grant check')
            absent = [s for s in self.scans if s['role'] == role and s['label'].startswith('cleanup_'+role+'_') and
                s['commands_end']-1 > uninstall[0] and not s['snapshot']['processes']]
            require(len(absent) == 2, 'two complete post-uninstall UID absence scans required')
            bms = [self.cmd(i) for i,item in enumerate(self.d['commands']) if i > uninstall[0] and item.get('script') == 'bm dump -a']
            require(bms, 'actual BMS removal observation missing'); assert_bundles_absent(bms[0],[BUNDLES[role]])
        require(self.cmd(len(self.body)-1,'cat /proc/sys/kernel/random/boot_id').strip() == self.io.boot_id,
            'actual final held boot changed')


def verify_observations(document, original_io):
    replay = Replay(document,original_io)
    require([case['case'] for case in document['cases']] == list(CASES), 'all fixed boundaries in source order required')
    require(len(document['native_windows']) == 7 and {case['native_window'] for case in document['cases'] if 'native_window' in case} == set(range(7)),
        'each target-exit case needs its own distinct actual native revocation window')
    for case in document['cases']:
        replay.case(case)
    replay.cleanup()
    require(document['whole_id_closure'] is False and document['formally_closed'] == [] and
        document['first_artifact_behavior_gate_passed'] is False and document['runtime_pass'] is False,
        'narrow observations must not replace whole original-ID or first-artifact acceptance')
    return {'schema':'actual-mms-share579-raw-replay/v1','archive_sha256':original_io.archive_sha256,
        'boot_id':original_io.boot_id,'run':original_io.run_id,'actual_raw_observations_matched':True,
        'cases':list(CASES),'scope':'MMS single-vCard handler and target-scoped Share URI boundaries only',
        'not_covered':['cellular message transport','legacy picker records','BYOD policy and cross-profile flow',
            'all other original MMS/Share business branches'],
        'whole_id_closure':False,'formally_closed':[],'first_artifact_behavior_gate_passed':False,'runtime_pass':False}
