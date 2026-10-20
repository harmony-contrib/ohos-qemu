"""Thin share578 orchestration on a root-owned guest; no resource/process owner.

Only root-injected callables dispatch commands. CLI execution is deliberately
absent. Installed/signature descriptors come from root's actual SDK/signing/
installation stage. The original read-only verifier remains the API oracle.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import shlex
import time

import batch_apps_share578_project as project
import batch_apps_share578_project_verify as verify
from guest_ui import GuestUi, LayoutNotReady, NodeNotReady, select_node
from hdc_transport import failed as transport_failed


BOOT_SCRIPT = 'cat /proc/sys/kernel/random/boot_id'
SETTINGS = 'com.ohos.settings'
PRIVATE_CASES = ()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def write_new(path, value):
    path = Path(path)
    require(not path.exists() and not path.is_symlink(), 'fresh output member required')
    with path.open('x', encoding='utf-8') as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return project.record(path)


def source_pins(path):
    pins = verify.decode(project.regular(path).read_text())
    require(pins.get('schema_version') == 1 and pins.get('files') == project.source_tools(), 'frozen source pins required')
    for name, wanted in pins['files'].items():
        actual = project.regular(project.HERE / name)
        require(project.sha(actual) == wanted, 'frozen runtime dependency changed: ' + name)
    return pins


def root_record_bridge(root_command, command_records):
    """Adapt an actual root command(argv,label,timeout,allow_failure) runner.

    command_records is a callable returning the actual root runner's mutable
    command list, not a JSON ownership claim. Exactly one newly appended argv/
    host-exit/log record must result. Timings are measured around that actual
    callback; log bytes are read from its original file, not its normalized
    return string. This function never dispatches a subprocess itself.
    """
    require(callable(root_command) and callable(command_records), 'actual root callbacks required')

    def execute(argv, *, label, timeout):
        before = len(command_records())
        started = time.monotonic_ns()
        root_command(argv, label, timeout=timeout, allow_failure=True)
        finished = time.monotonic_ns()
        rows = command_records()
        require(len(rows) == before + 1, 'one new actual root command record required')
        row = rows[-1]
        require(row.get('argv') == argv and type(row.get('exit_code')) is int and not row.get('timed_out', False),
                'actual root argv/host exit absent or timed out')
        log = project.regular(row.get('log', row.get('path', '')))
        require(row.get('sha256') == project.sha(log), 'root original log descriptor changed')
        return dict(argv=list(argv), host_exit_code=row['exit_code'], raw=project.record(log),
                    started_ns=started, finished_ns=finished)
    return execute


class Collector:
    def __init__(self, *, challenge, applications, boot_id, archive_sha256, guest_udid, hdc, endpoint,
                 output, command, healthy, pins, timeout=90, poll_interval=0.25):
        # A dictionary, execute flag, or JSON root_owned value cannot dispatch.
        require(callable(command) and callable(healthy), 'actual owned command and health callbacks required')
        require(type(timeout) in (int, float) and 1 <= timeout <= 300 and
                type(poll_interval) in (int, float) and 0.05 <= poll_interval <= 2,
                'bounded real runtime waits required')
        self.pins_path = project.regular(pins)
        self.pins = source_pins(self.pins_path)
        self.challenge_path = project.regular(challenge)
        self.challenge = project.load_challenge(self.challenge_path)
        require(project.BOOT.fullmatch(boot_id) and project.HEX.fullmatch(archive_sha256), 'actual boot/archive required')
        self.hdc = str(project.regular(hdc)); self.endpoint = endpoint
        require(type(endpoint) is str and re.fullmatch('[A-Za-z0-9_.:-]{1,128}', endpoint), 'trusted endpoint required')
        require(isinstance(applications, dict) and set(applications) == set(project.ROLES), 'three actual installed applications required')
        self.apps = copy.deepcopy(applications)
        require(type(guest_udid) is str and re.fullmatch('[a-fA-F0-9]{64}', guest_udid) and
                all(x.get('actual_guest_udid') == guest_udid for x in self.apps.values()),
                'actual root guest UDID must bind every normal signed profile')
        self.boot, self.archive = boot_id, archive_sha256
        self.command_callback, self.healthy = command, healthy
        self.timeout, self.interval = float(timeout), float(poll_interval)
        self.output = Path(output)
        require(self.output.is_absolute() and self.output.parent.resolve() == self.output.parent and
                not self.output.exists() and not self.output.is_symlink(), 'fresh canonical private runtime output required')
        self.output.mkdir()
        self.report = dict(schema_version=1, scope='root_owned_share578_fresh_UI_and_original_raw_verifier_ONLY',
            status='running', challenge=project.record(self.challenge_path), source_pins=project.record(self.pins_path),
            collector=project.record(Path(__file__).resolve()), boot_id=self.boot, archive_sha256=self.archive, guest_udid=guest_udid,
            hdc=project.record(Path(self.hdc)), endpoint=endpoint, applications=self.apps,
            commands=[], cases=[], failures=[], first_artifact_behavior_gate_passed=False,
            ledger_closed=False, native_owner_release_verified_here=False,
            signature_cryptography_verified_here=False, app_uninstall_cleanup_verified_here=False)
        self.ui = GuestUi(self.text_command, self.hdc, endpoint, self.output / 'ui')
        self.last_finished = 0
        self.prior_journals = {role: '' for role in project.ROLES}
        self.identities = None
        self.save()

    def save(self):
        # Only this new collector report is updated; raw command files are never edited.
        path = self.output / 'collector-report.json'
        path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + '\n')

    def dispatch(self, argv, label, timeout=30):
        argv = [str(x) for x in argv]
        require(re.fullmatch('[a-zA-Z0-9_-]{1,160}', label), 'bounded command label required')
        require(argv[:3] == [self.hdc, '-t', self.endpoint] and argv[3:4] in (['shell'], ['file']),
                'only actual owned endpoint HDC operations permitted')
        if argv[3] == 'file':
            require(len(argv) == 7 and argv[4] == 'recv' and
                    re.fullmatch('/data/local/tmp/qemu-capability-ui-[a-f0-9]{32}-[0-9]+[.]png', argv[5]) and
                    Path(argv[6]).parent == self.ui.output and Path(argv[6]).suffix == '.png' and
                    not Path(argv[6]).exists(), 'only fresh compositor PNG receive into owned output permitted')
        self.healthy(); source_pins(self.pins_path)
        item = dict(argv=argv, label=label, actual_observation_received=False)
        self.report['commands'].append(item); self.save()
        row = self.command_callback(argv, label=label, timeout=timeout)
        require(type(row) is dict and set(row) == {'argv', 'host_exit_code', 'raw', 'started_ns', 'finished_ns'} and
                row['argv'] == argv and type(row['host_exit_code']) is int and
                type(row['started_ns']) is int and type(row['finished_ns']) is int and
                0 < row['started_ns'] <= row['finished_ns'] and row['started_ns'] >= self.last_finished,
                'exact serial actual command observation required')
        raw = project.checked(row['raw']).read_text()
        item.update(actual_observation_received=True, observation=row); self.save()
        self.last_finished = row['finished_ns']
        require(row['host_exit_code'] == 0 and not transport_failed(raw) and
                not any(x in raw for x in ('HDCFail', 'Connect server failed', 'device not found')),
                'actual HDC host/transport failure: ' + label)
        self.healthy(); source_pins(self.pins_path)
        return row, raw

    def text_command(self, argv, label):
        return self.dispatch(argv, label)[1]

    def shell(self, script, req, label):
        shell, _ = verify.wrapped(script, req['operation_id'])
        row, _ = self.dispatch([self.hdc, '-t', self.endpoint, 'shell', shell], label)
        return verify.command(row, script, req, self.hdc, self.endpoint), row

    def same_boot(self, req, label):
        body, row = self.shell(BOOT_SCRIPT, req, label)
        require(body == self.boot + '\n', 'actual guest boot changed')
        return row

    def snapshot(self, req, label):
        rows = [self.same_boot(req, label + '-boot')]
        journals, identities = {}, {}
        for role in project.ROLES:
            body, row = self.shell('bm dump -n ' + project.ROLES[role]['bundle'], req, label + '-' + role + '-bms')
            rows.append(row); identities[role] = verify.identity(body, role)
            script, absent = verify.journal_script(req, role)
            body, row = self.shell(script, req, label + '-' + role + '-journal')
            rows.append(row); journals[role] = '' if body == absent + '\n' else body
            path = identities[role]['hap_path']
            body, row = self.shell('sha256sum ' + shlex.quote(path), req, label + '-' + role + '-hap')
            rows.append(row)
            require(body == project.sha(project.checked(self.apps[role]['signed_hap'])) + '  ' + path + '\n',
                    'actual installed role HAP hash differs')
        require(len({x['uid'] for x in identities.values()}) == 3 and len({x['token_id'] for x in identities.values()}) == 3,
                'three distinct actual UID/token roles required')
        if self.identities is not None:
            require(self.identities == identities, 'installed roles changed between operations')
        self.identities = identities
        return rows, journals

    def current_caller(self, req, label, *, partial=False):
        script, absent = verify.journal_script(req, 'caller')
        body, row = self.shell(script, req, label)
        if body == absent + '\n':
            body = ''
        if partial and body and not body.endswith('\n'):
            # A polled append may have one incomplete last line. Preserve that raw
            # observation and wait; it is never used as the final verifier snapshot.
            require(len(body.encode()) <= 4194304, 'bounded complete journal prefix required')
            body = body[:body.rfind('\n') + 1] if '\n' in body else ''
        rows = verify.parse(body, req, 'caller', self.identities['caller'])
        prior = verify.parse(self.prior_journals['caller'], req, 'caller', self.identities['caller'])
        require(rows[:len(prior)] == prior, 'journal prior prefix was changed')
        added = rows[len(prior):]
        require(all(x['operation_id'] == req['operation_id'] and x['case_id'] == req['case_id'] and
                    x['kind'] == 'caller' and x['phase'] == 'run' for x in added), 'foreign/replaced caller operation')
        require(not any(x['event'] in ('error', 'failed', 'private_resolve') for x in added),
                'real caller API error or direct private start resolved')
        return added, row

    def bounded(self, action):
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                return action()
            except (LayoutNotReady, NodeNotReady):
                if time.monotonic() >= deadline:
                    raise TimeoutError('bounded actual UI/journal readiness expired')
                time.sleep(self.interval)

    def caller_nodes(self, layout, req):
        bundle = project.ROLES['caller']['bundle']
        ready = select_node(layout, bundle, identifier='share578-ready')
        expected = '/'.join([req['run_id'], req['operation_id'], req['case_id'], 'run'])
        actual = ready['attributes'].get('text')
        if actual != expected:
            prior_ready = set()
            for item in self.report['cases']:
                if item.get('status') == 'pass_raw_modal_share578_slice_ONLY':
                    old = verify.decode(project.checked(item['request']).read_text())
                    prior_ready.add('/'.join([old['run_id'], old['operation_id'], old['case_id'], 'run']))
            if actual == '' or actual in prior_ready:
                raise NodeNotReady('cold/onNewWant caller has not published the current owned request')
            raise ValueError('actual caller ready text belongs to another request')
        button = select_node(layout, bundle, identifier='share578-run', clickable=True)
        return dict(ready=ready, button=button)

    def wait_complete(self, req):
        def read():
            rows, row = self.current_caller(req, req['case_id'] + '-completion-poll', partial=True)
            if not rows or rows[-1]['event'] != 'complete':
                raise NodeNotReady('actual caller journal not complete')
            return row
        return self.bounded(read)

    def preflight_inputs(self):
        # Reuse the original verifier's same file-only prelude before any guest
        # action. Signature cryptography stays root's separate real signer gate.
        from batch_apps_contact_picker_coordinator import verify_signed_payload, ordinary_hap, verify_profile
        for role in project.ROLES:
            app = self.apps[role]
            unsigned = verify.sdk_binding(app, role, self.challenge_path)
            signed = project.checked(app['signed_hap'])
            verify_signed_payload(unsigned, signed)
            ordinary_hap(signed, project.ROLES[role]['bundle'], [])
            verify_profile(verify.decode(project.checked(app['decoded_profile']).read_text()),
                           project.ROLES[role]['bundle'], [], app['actual_guest_udid'])
            require(project.sha(project.checked(app['installed_hap'])) == project.sha(signed),
                    'root pulled installed HAP differs before operation')

    def hierarchy(self, req, bundle, label):
        self.same_boot(req,label+'-boot')
        layout,path=self.ui.layout(bundle=bundle,label=label)
        proof={'tree':project.record(path.resolve()),'dump':self.report['commands'][-2]['observation'],
            'read':self.report['commands'][-1]['observation']}
        # Original raw UI evidence is replayed immediately, never trusted as a
        # parsed dictionary or a collector success flag.
        verify.ui_tree(proof,self.hdc,self.endpoint,bundle)
        return layout,proof

    def click(self, req, bundle, label, check):
        def dispatch():
            layout,proof=self.hierarchy(req,bundle,label)
            nodes=check(layout);node=nodes['button'];left,top,width,height=node['rect']
            script='uitest uiInput click '+str(left+width//2)+' '+str(top+height//2)
            self.ui.shell(script,label+'-actual-node-center')
            click=self.report['commands'][-1]['observation']
            png=self.ui.screenshot(label=label)
            self.report.setdefault('compositor_screenshots',[]).append(project.record(png.resolve()));self.save()
            return {'hierarchy':proof,'click':click}
        return self.bounded(dispatch)

    def pending_select(self, req):
        rows,row=self.current_caller(req,req['case_id']+'-pending-share',partial=True)
        require(not any(x['event'] in ('share_result','share_callback_error','cleanup_ready','complete') for x in rows),'share returned before an actual chooser action')
        calls=[x for x in rows if x['event']=='share_call']
        if len(calls)!=1 or not rows or rows[-1]['event'] not in ('share_call','share_opened'):
            raise NodeNotReady('ordinary caller has not reached pending real modal share')
        uri,_=verify.owned(req,rows);verify.shared_call(req,calls[0],uri)
        return row

    def chooser_nodes(self, layout, req):
        return verify.chooser_nodes(layout,req)

    def wait_cleanup_ready(self, req):
        def read():
            rows,row=self.current_caller(req,req['case_id']+'-cleanup-ready',partial=True)
            if not rows or rows[-1]['event']!='cleanup_ready': raise NodeNotReady('awaiting actual callback before cleanup')
            return row
        return self.bounded(read)

    def wait_receiver(self, req):
        role=project.CONTRACT['cases'][req['case_id']]['target']
        if not role: return
        def read():
            script,absent=verify.journal_script(req,role);body,_=self.shell(script,req,req['case_id']+'-receiver-completion')
            if body==absent+'\n' or not body.endswith('\n'): raise NodeNotReady('real receiver not complete')
            rows=verify.parse(body,req,role,self.identities[role]);old=verify.parse(self.prior_journals[role],req,role,self.identities[role])
            require(rows[:len(old)]==old,'receiver prior journal changed');new=rows[len(old):]
            if not new or new[-1]['event']!='complete': raise NodeNotReady('real receiver IO/exit not complete')
            caller,_=self.current_caller(req,req['case_id']+'-receiver-owned-uri',partial=True)
            uri,_=verify.owned(req,caller);verify.target(new,req,role,'select','choose',uri)
        self.bounded(read)

    def process_scan(self,req,label):
        import secrets
        from batch_network_openvpn_runtime_collect import snapshot_script
        nonce=secrets.token_hex(16);identity=self.identities['caller']
        script=snapshot_script(nonce,self.boot,mode='uid',uid=identity['uid'],bundle=project.ROLES['caller']['bundle'])
        _,row=self.shell(script,req,label);proof={'nonce':nonce,'command':row}
        return proof,verify.process_proof(proof,req,self.hdc,self.endpoint,identity)

    def death(self,req,item):
        def pending():
            self.pending_select(req)
            layout,proof=self.hierarchy(req,SETTINGS,'death-pending-modal')
            self.chooser_nodes(layout,req)
            rows,_=self.current_caller(req,'death-pending-opened',partial=True)
            if not rows or rows[-1]['event']!='share_opened': raise NodeNotReady('wait actual startAbilityByType promise')
            return proof
        item['actions']['pending_chooser']=self.bounded(pending)
        before,scan=self.process_scan(req,'death-caller-kernel-birth')
        rows,_=self.current_caller(req,'death-current-pid',partial=True)
        require(rows[-1]['pid'] in scan['processes'],'current ordinary caller birth missing')
        _,stop=self.shell('aa force-stop '+project.ROLES['caller']['bundle'],req,'death-force-stop-only-owned-audit-caller')
        result={'before':before,'stop':stop,'absent':[],'gone_chooser':[]}
        for i in range(2):
            def gone():
                proof,current=self.process_scan(req,'death-uid-absent-'+str(i))
                if current['processes']: raise NodeNotReady('actual owned caller UID still alive')
                return proof
            result['absent'].append(self.bounded(gone))
            def modal_gone():
                layout,proof=self.hierarchy(req,None,'death-modal-absent-'+str(i))
                try: select_node(layout,SETTINGS,identifier='system-share-title')
                except NodeNotReady: return proof
                raise NodeNotReady('actual modal still attached after caller death')
            result['gone_chooser'].append(self.bounded(modal_gone))
        return result

    def run(self):
        death_evidence=None
        try:
            self.preflight_inputs()
            for case in project.CONTRACT['cases']:
                req=project.request(self.challenge_path,self.boot,self.archive,case)
                path=self.output/('request-'+case+'.json');request_record=write_new(path,req)
                item={'case_id':case,'request':request_record,'status':'running','actions':{}}
                self.report['cases'].append(item);self.save()
                before,old=self.snapshot(req,case+'-before')
                require(old==self.prior_journals,'serial original journal prefix changed')
                for role in project.ROLES: verify.parse(old[role],req,role,self.identities[role])
                launch=shlex.join(['aa','start','-b',project.ROLES['caller']['bundle'],'-a','EntryAbility','--ps','request',json.dumps(req,separators=(',',':'))])
                _,launch_row=self.shell(launch,req,case+'-publish-ordinary-caller')
                item['actions']['caller']=self.click(req,project.ROLES['caller']['bundle'],case+'-caller',lambda tree:self.caller_nodes(tree,req))
                lifetime=None;recovery=None
                if case=='death': lifetime=self.death(req,item)
                else:
                    if case!='no-grant-a':
                        self.bounded(lambda:self.pending_select(req))
                        def chooser(tree):
                            self.pending_select(req);return self.chooser_nodes(tree,req)
                        item['actions']['chooser']=self.click(req,SETTINGS,case+'-chooser',chooser)
                    self.wait_cleanup_ready(req);self.wait_receiver(req)
                    # Reveal the SAME busy singleton without executing a second
                    # operation. The cleanup node still carries this nonce.
                    self.shell(launch,req,case+'-reveal-same-caller-for-cleanup')
                    def cleanup(tree):
                        nodes=self.caller_nodes(tree,req)
                        nodes['button']=select_node(tree,project.ROLES['caller']['bundle'],identifier='share578-cleanup',clickable=True)
                        return nodes
                    item['actions']['cleanup']=self.click(req,project.ROLES['caller']['bundle'],case+'-cleanup',cleanup)
                    self.wait_complete(req)
                    if case=='recovery-a':
                        proof,_=self.process_scan(req,'recovery-new-caller-kernel-birth')
                        require(death_evidence is not None,'recovery requires exact preceding death evidence')
                        recovery={'process':proof,'death':death_evidence}
                after,new=self.snapshot(req,case+'-after')
                api={'schema_version':1,'request':request_record,'applications':self.apps,'commands':before+after}
                evidence={'schema_version':1,'api':api,'actions':item['actions'],'launch':launch_row,'death':lifetime,'recovery':recovery}
                item['evidence']=write_new(self.output/('evidence-'+case+'.json'),evidence)
                result=verify.verify_case(evidence,self.challenge_path,path,self.hdc,self.endpoint,self.archive)
                item['verification']=write_new(self.output/('verification-'+case+'.json'),result)
                item['status']='pass_raw_modal_share578_slice_ONLY';self.prior_journals=new
                if case=='death': death_evidence=item['evidence']
                self.save()
            self.report['status']='pass_eight_modal_share_raw_slices_ONLY'
        except Exception as error:
            self.report['status']='fail';self.report['failures'].append(type(error).__name__+': '+str(error));self.save();raise
        finally: self.save()
        return self.report


def collect(**kwargs):
    return Collector(**kwargs).run()
