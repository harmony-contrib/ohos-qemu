"""Fixed new-image Live Captions stage over the original held guest/OwnedIO.

All outcomes require raw public API, user UI, native journal and process evidence.
No resource owner, host ASR, injected PCM/transcript or provider test RPC exists.
"""
import json
from pathlib import Path
import re
import time

from capability578_owned_io import require, reference
from guest_ui import select_node, NodeNotReady, LayoutNotReady
from hap_identity_binding import strict_json
from livecaptions579_bindings import bind
from livecaptions579_provider_project import BUNDLE, ABILITY

IDENTIFIER = 'behavior:accessibility-caption-provider-missing'
SYSTEMUI = 'com.ohos.systemui'
LC = re.compile(r'\bLC uid=([0-9]+) pid=([0-9]+) session=([a-fA-F0-9-]{36}) event=([a-z_]+) sequence=([0-9]+) samples=([0-9]+) segments=([0-9]+) code=(-?[0-9]+)(?:\s|$)')
AP = re.compile(r'\bAP id=([a-fA-F0-9-]{36}) event=([a-z-]+) stream=([0-9]+) uid=([0-9]+) bundle=([A-Za-z0-9_.]+) code=(-?[0-9]+)(?:\s|$)')


def normal(text):
    return re.sub('[^a-z0-9]+', ' ', text.lower()).strip()


def records(raw):
    require('ExtensionRecords:' in raw, 'complete actual AMS extension dump required')
    result = []
    for block in re.split(r'(?=^\s*AbilityRecord ID #)', raw, flags=re.M):
        if '\n' not in block or 'main name [' + ABILITY + ']' not in block:
            continue
        match = re.search(r'^\s*AbilityRecord ID #([0-9]+)\s+state #([A-Z_]+)\s+start time \[([0-9]+)\]', block, re.M)
        require(match and 'bundle name [' + BUNDLE + ']' in block and 'ability type [SERVICE]' in block,
                'actual caption SERVICE record identity differs')
        result.append({'id': int(match[1]), 'state': match[2], 'start_time': int(match[3])})
    require(len(result) <= 1, 'one actual caption service instance required')
    return result


class Stage:
    def __init__(self, io):
        self.io, self.b = io, bind(io)
        self.lc, self.ap, self.seen_lc, self.seen_ap = [], [], set(), set()
        self.cases, self.failures, self.sessions = [], [], []
        self.baseline = None
        self.native_stops = []

    def traces(self):
        raw = self.b.logs()
        command = len(self.b.commands)-1
        for line in raw.splitlines():
            native=re.search(r'conditional stop accepted, startId=([0-9]+) record=([0-9]+)(?:\s|$)',line)
            if native and line not in {r['raw'] for r in self.native_stops}:
                self.native_stops.append({'start_id':int(native[1]),'record_id':int(native[2]),'command':command,'raw':line})
            match = LC.search(line)
            if match and line not in self.seen_lc:
                self.seen_lc.add(line)
                uid, pid, session, event, sequence, samples, segments, code = match.groups()
                if int(uid) == self.b.provider['uid']:
                    self.lc.append({'uid':int(uid),'pid':int(pid),'session':session,'event':event,
                        'sequence':int(sequence),'samples':int(samples),'segments':int(segments),
                        'code':int(code),'command':command,'raw':line})
            match = AP.search(line)
            if match and line not in self.seen_ap:
                self.seen_ap.add(line)
                ident, event, stream, uid, bundle, code = match.groups()
                if int(uid) == self.b.provider['uid']:
                    require(bundle == BUNDLE, 'actual consent UID/bundle identity differs')
                    self.ap.append({'id':ident,'event':event,'stream':int(stream),'uid':int(uid),
                        'bundle':bundle,'code':int(code),'command':command,'raw':line})
        return self.lc

    def events(self, session, event):
        return [row for row in self.lc if row['session']==session['id'] and row['event']==event]

    def wait_event(self, session, event, timeout=60):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.traces()
            rows = self.events(session,event)
            if rows: return rows[-1]
            time.sleep(.5)
        raise ValueError('actual provider event deadline: '+event)

    def state(self, session, wanted):
        state=self.b.state()
        matching=[r for r in state['capturers'] if r['clientUid']==self.b.provider['uid']]
        require(state['captionRequested']=='true' and len(matching)==1 and
            matching[0]['streamId']==session['stream'] and matching[0]['capturerInfo']['source']==2 and
            matching[0]['capturerState']==wanted, 'actual native capture UID/SID/source/state differs')
        return state

    def pending(self):
        self.b.recover()
        self.traces()
        prior={row['session'] for row in self.lc}
        self.b.chord()
        deadline=time.monotonic()+220
        confirm_clicked=False
        while time.monotonic()<deadline:
            self.traces()
            created=[row for row in self.lc if row['event']=='capture_created' and row['session'] not in prior]
            if created:
                require(len(created)==1 and created[0]['code']>0, 'one real fresh capture stream required')
                row=created[0]
                session={'id':row['session'],'pid':row['pid'],'stream':row['code']}
                self.sessions.append(session)
                self.wait_event(session,'authority_requested',timeout=10)
                require(self.events(session,'window_visible') and self.events(session,'model_ready'),
                    'actual window/model/authorization chain incomplete')
                node=self.b.node(SYSTEMUI,'playback-consent-app',timeout=30)
                require(node['attributes'].get('text')==BUNDLE, 'user consent displays another requesting bundle')
                self.traces()
                shown=[r for r in self.ap if r['stream']==session['stream'] and r['event']=='shown']
                require(len(shown)==1, 'one real pending consent session required')
                session['consent_id']=shown[0]['id']
                live=self.b.scan(self.b.provider,'pending_identity')['processes']
                require(session['pid'] in live and live[session['pid']]['uid']==self.b.provider['uid'],
                    'actual pending provider process/UID absent')
                session['native']={'pid':session['pid'],'uid':self.b.provider['uid'],'start_ticks':live[session['pid']]['start']}
                session['prepared']=self.state(session,1)
                active=records(self.b.snapshot())
                require(len(active)==1, 'actual framework SERVICE record missing')
                session['record']=active[0]
                self.b.frame('pending_'+str(len(self.sessions)))
                return session
            # First-use confirmation can belong to Settings or SceneBoard. Never mutate its
            # first-use database flag to avoid the dialog.
            for bundle in ('com.ohos.settings', 'com.ohos.sceneboard'):
                try:
                    layout=self.b.layout(bundle,'shortcut_confirm')
                    select_node(layout,bundle,identifier='accessibility-shortcut-confirm-enable')
                except (NodeNotReady,LayoutNotReady):
                    continue
                require(not confirm_clicked, 'unexpected repeated shortcut confirmation')
                self.b.click(bundle,'accessibility-shortcut-confirm-enable')
                confirm_clicked=True
                break
            time.sleep(1)
        raise ValueError('actual AAMS shortcut/model/consent chain deadline')

    def closed(self, session, graceful=True, timeout=60):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.traces()
            state=self.b.state()
            active=records(self.b.snapshot())
            scan=self.b.scan(self.b.provider,'closed_wait')
            if state['captionRequested']=='false' and not active and not scan['processes'] and not [
                r for r in state['capturers'] if r['clientUid']==self.b.provider['uid']]:
                break
            time.sleep(.5)
        else: raise ValueError('actual provider/capture/AMS/UID closure deadline')
        if graceful:
            require(self.events(session,'capture_released') and self.events(session,'window_destroyed') and
                self.events(session,'resources_released') and
                [r for r in self.events(session,'worker_exit') if r['code']==0] and
                not self.events(session,'cleanup_error'), 'actual graceful native/worker/window release incomplete')
            stops=[r for r in self.native_stops if r['record_id']==session['record']['id']]
            require(len(stops)==1 and stops[0]['start_id']>0, 'actual AMS conditional SERVICE idle-stop decision missing')
            session['native_stop']=stops[0]
        for number in range(2):
            require(not self.b.scan(self.b.provider,'closed_'+str(number))['processes'], 'provider UID reappeared after closure')
            require(not records(self.b.snapshot()), 'caption SERVICE record reappeared after closure')
        # A complete real hierarchy, not window-enumeration failure, proves both
        # the caption overlay and this provider's consent control disappeared.
        layout=self.b.layout(None,'closed_windows')
        for bundle, identifier in ((BUNDLE,'live-captions-close'),(SYSTEMUI,'playback-consent-app')):
            try: select_node(layout,bundle,identifier=identifier)
            except NodeNotReady: pass
            else: raise ValueError('actual owned caption/consent UI remains after closure')
        session['closed']={'state':state,'record_absent':True,'commands_end':len(self.b.commands),'graceful':graceful}

    def allow(self, session):
        self.b.click(SYSTEMUI,'playback-consent-allow')
        actual=self.wait_event(session,'capture_running')
        require(actual['code']==2 and [r for r in self.events(session,'authority_callback') if r['code']==0],
            'actual native successful callback/running state missing')
        self.state(session,2)
        mapped=self.b.native_identity(session['pid'])
        require(mapped['start_ticks']==session['native']['start_ticks'], 'provider generation changed before native library inspection')
        session['native']=mapped
        self.traces()
        accepted=[r for r in self.ap if r['id']==session['consent_id'] and r['event']=='allow-button' and r['code']==0]
        require(len(accepted)==1, 'actual bound user Allow decision did not succeed')
        self.b.node(BUNDLE,'live-captions-status')
        self.b.frame('authorized_'+str(len(self.sessions)))

    def play(self, role, which):
        op=self.b.request(role,'play-'+which)
        started=strict_json(self.b.wait(role,op,'renderer.start')['value'])
        drained=strict_json(self.b.wait(role,op,'renderer.drained',timeout=90)['value'])
        released=self.b.wait(role,op,'renderer.released')
        self.b.wait(role,op,'done')
        require(started['state']==2 and started['privacy']==(1 if role=='private' else 0) and
            started['streamId']>0 and started['waveformBytes']>=32000 and
            drained['streamId']==started['streamId'] and drained['state']==2 and
            drained['written']==started['waveformBytes']+64000 and drained['audioTime']>0 and
            released['value']=='4', 'actual independent renderer/drain/release facts differ')
        return {'role':role,'operation':op,'started':started,'drained':drained,'released':released}

    def transcript(self, session, which):
        deadline=time.monotonic()+90
        expected=self.b.inputs['speech'][which]['contains']
        while time.monotonic()<deadline:
            self.traces()
            require(not self.events(session,'session_error') and not self.events(session,'cleanup_error'), 'actual recognition session failed')
            node=self.b.node(BUNDLE,'live-captions-text',timeout=3)
            text=node['attributes'].get('text','')
            if all(normal(part) in normal(text) for part in expected):
                rendered=self.events(session,'caption_rendered')
                ack=self.events(session,'pcm_ack')
                require(rendered and ack and rendered[-1]['segments']>0 and rendered[-1]['samples']>=16000 and
                    ack[-1]['sequence']>=rendered[-1]['sequence'] and
                    all(r['pid']==session['pid'] for r in self.lc if r['session']==session['id']),
                    'actual native PCM/result/UI session chain incomplete')
                self.state(session,2)
                self.b.frame('recognized_'+which)
                return {'text':text,'expected':expected,'groundtruth':self.b.inputs['speech'][which]['groundtruth'],
                        'last_result':rendered[-1],'last_ack':ack[-1],'ui_end':len(self.b.ui_reads)}
            time.sleep(.5)
        raise ValueError('actual visible transcript does not contain independent original groundtruth')

    def stop(self, session):
        self.b.click(BUNDLE,'live-captions-close')
        self.closed(session)

    def deny_permission(self):
        op=self.b.request('ordinary','forbidden-provider')
        error=self.b.wait('ordinary',op,'error',allow_error=True)
        require(error['code']==201 and not [r for r in self.b.collect('ordinary') if
            r['operation']==op and r['event']=='forbidden.provider.return'], 'actual provider start permission denial missing')
        return {'operation':op,'error':error}

    def deny(self):
        session=self.pending()
        op=self.b.request('ordinary','forbidden-decision',session['stream'])
        error=self.b.wait('ordinary',op,'error',allow_error=True)
        require(error['code']==201 and not [r for r in self.b.collect('ordinary') if
            r['operation']==op and r['event']=='forbidden.return'], 'valid real native report must reject missing MANAGE_AUDIO_CONFIG')
        session['unprivileged']={'operation':op,'error':error,'state':self.state(session,1)}
        self.b.click(SYSTEMUI,'playback-consent-deny')
        callback=self.wait_event(session,'authority_callback')
        require(callback['code']==2 and not self.events(session,'capture_running'), 'real user denial must not start capture')
        self.closed(session)
        return session

    def cancel_pending(self):
        session=self.pending()
        self.b.chord()  # AAMS reads requested=true and dispatches the true close Want.
        self.closed(session)
        require(not [r for r in self.events(session,'authority_callback') if r['code']==0] and
            not self.events(session,'capture_running'), 'cancelled pending session accepted late authorization')
        return session

    def back(self):
        session=self.pending()
        self.b.shell('uitest uiInput keyEvent Back','real_back')
        callback=self.wait_event(session,'authority_callback')
        require(callback['code']==2 and not self.events(session,'capture_running'), 'real Back must deny capture')
        self.closed(session)
        return session

    def timeout(self):
        session=self.pending()
        callback=self.wait_event(session,'authority_callback',timeout=75)
        require(callback['code']==2 and not self.events(session,'capture_running'), 'expired UI must not grant capture')
        self.traces()
        require([r for r in self.ap if r['id']==session['consent_id'] and r['event']=='deny-timeout' and r['code']==0],
            'actual consent expiry report missing')
        self.closed(session)
        return session

    def speech_and_private(self):
        session=self.pending(); self.allow(session)
        session['public']=self.play('media','a')
        session['recognized']=self.transcript(session,'a')
        time.sleep(2); self.traces()
        before=self.events(session,'caption_rendered')[-1]
        old_ack=self.events(session,'pcm_ack')[-1]
        old_text=self.b.node(BUNDLE,'live-captions-text')['attributes'].get('text','')
        session['private']=self.play('private','b')
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            self.traces()
            require(self.b.node(BUNDLE,'live-captions-text')['attributes'].get('text','')==old_text and
                self.events(session,'caption_rendered')[-1]==before and not self.events(session,'session_error'),
                'private renderer audio entered the visible caption transcript')
            self.state(session,2)
            time.sleep(.5)
        ack=self.events(session,'pcm_ack')[-1]
        require(ack['sequence']>old_ack['sequence'] and ack['samples']>old_ack['samples'] and
            ack['segments']==before['segments'], 'private exclusion must retain a live capture/worker without decoding private speech')
        session['private_exclusion']={'before_result':before,'before_ack':old_ack,'after_ack':ack,'visible':old_text}
        self.stop(session)
        return session

    def death_and_restart(self):
        prior=self.pending()
        self.b.recover()
        self.closed(prior,graceful=False)
        current=self.pending()
        require(current['id']!=prior['id'] and current['stream']!=prior['stream'] and
            current['record']['id']!=prior['record']['id'] and
            (current['pid'],current['native']['start_ticks'])!=(prior['pid'],prior['native']['start_ticks']),
            'real process/service/stream/session generations must differ after abrupt death')
        self.allow(current)
        current['public']=self.play('media','b')
        current['recognized']=self.transcript(current,'b')
        require(all(r['pid']==current['pid'] for r in self.lc if r['session']==current['id']),
            'old instance callback entered the rebuilt caption session')
        self.stop(current)
        return {'terminated':prior,'rebuilt':current}

    def case(self, name, function):
        row={'name':name,'commands_begin':len(self.b.commands),'ui_begin':len(self.b.ui_reads)}
        self.cases.append(row)
        try:
            row['actual']=function(); row['passed']=True
        except Exception as error:
            row.update(passed=False,error=type(error).__name__+': '+str(error))
            self.failures.append(name+': '+str(error))
            # Preserve this failure, then use the actual owned cleanup path so
            # independently executable later boundaries still collect evidence.
            try: self.b.recover()
            except Exception as recovery: row['recovery_error']=str(recovery)
        finally:
            row['commands_end']=len(self.b.commands); row['ui_end']=len(self.b.ui_reads)
            self.save()

    def save(self):
        path=Path(self.io.output)/'evidence.json'
        value={'schema':'actual-livecaptions579-runtime/v1','id':IDENTIFIER,'archive_sha256':self.io.archive_sha256,
            'boot_id':self.io.boot_id,'run':self.b.run,'language':'en','model':'whisper-tiny.en',
            'package_inputs':getattr(self.b,'inputs',None),'baseline':self.baseline,'roles':self.b.roles,
            'provider':getattr(self.b,'provider',None),'commands':self.b.commands,'journal_reads':self.b.reads,
            'journal_writers':list(self.b.writers.values()),'journals':self.b.rows,'ui':self.b.ui_reads,
            'process_scans':self.b.scans,'native_maps':self.b.native_maps,'lc':self.lc,'consent':self.ap,
            'cases':self.cases,'sessions':self.sessions,'native_stops':self.native_stops,'failures':self.failures,
            'cleanup_complete':self.b.cleaned,'runtime_validated':not self.failures and self.b.cleaned and len(self.cases)==7}
        path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
        return reference(path)

    def execute(self):
        try:
            self.b.prepare()
            for role in ('control','media','private','ordinary'): self.b.install(role)
            original=self.b.state()
            require(original['captionRequested']=='false' and not [r for r in original['capturers'] if
                r['clientUid']==self.b.provider['uid']] and not self.b.scan(self.b.provider,'initial')['processes'],
                'new artifact must begin with inactive real caption provider')
            op=self.b.request('control','save')
            self.b.saved=strict_json(self.b.wait('control',op,'saved')['value'])
            self.baseline={'state':original,'settings':self.b.saved,'operation':op}
            op=self.b.request('control','configure')
            configured=strict_json(self.b.wait('control',op,'configured')['value'])
            require(configured=={'enabled':True,'targets':['CAPTIONS_ASSISTANT']}, 'real shortcut configuration did not apply')
            self.case('provider-permission',self.deny_permission)
            self.case('native-permission-and-user-deny',self.deny)
            self.case('cancel-pending',self.cancel_pending)
            self.case('user-back-denies',self.back)
            self.case('user-consent-expires',self.timeout)
            self.case('real-speech-and-private-exclusion',self.speech_and_private)
            self.case('abrupt-death-and-rebuilt-speech',self.death_and_restart)
        except Exception as error:
            self.failures.append('preparation: '+type(error).__name__+': '+str(error))
        finally:
            try: self.b.cleanup()
            except Exception as error: self.failures.append('cleanup: '+str(error))
            artifact=self.save()
        require(not self.failures, 'actual caption stage failed; all independent evidence retained: '+'; '.join(self.failures))
        require(self.b.cleaned and len(self.cases)==7 and all(row['passed'] for row in self.cases),
                'complete real caption boundary/runtime gate did not pass')
        return artifact


def run(root_io):
    return Stage(root_io).execute()
