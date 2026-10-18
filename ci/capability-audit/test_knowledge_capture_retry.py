"""Root-run350 successor file/fake regressions; author executed/imported none."""
import copy
import itertools
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

TEST_ROOT = Path(__file__).resolve().parent
F = TEST_ROOT if (TEST_ROOT/'batch_media_knowledge_project.py').is_file() else Path(
    '/Users/ranger/.codex/worktrees/capability-batched-repair-f/ohos-qemu/ci/capability-audit')
sys.path.append(str(F))
import batch_media_knowledge_suite as S
if Path(S.__file__).resolve().parent != Path(__file__).resolve().parent:
    raise RuntimeError('test must load the isolated314 candidate, not a cached original')
from guest_ui import GuestUiCommandError


class Frame:
    """Synthetic original-shaped raw commands/observations; never guest evidence."""
    def __init__(self, root, *, ready_missing=False, ready_transition=False):
        self.ready_missing=ready_missing;self.ready_transition=ready_transition
        self.root=root;self.hdc='/hdc';self.target='127.0.0.1:47001';self.run='a'*32;self.boot='b'*8+'-0000-0000-0000-'+'b'*12
        self.bundle=S.project.ROLES['query'][0];self.namespace='c'*32;self.sequence=0
        self.value=dict(run_id=self.run,boot_id=self.boot,hdc=self.hdc,commands=[],ui_actions=[],phases=[],observations=[])
        self.observations={};self.data=dict(run_id=self.run);self.env=dict(target=self.target,boot_id=self.boot)
        self.request=self.file('request.json',json.dumps(dict(run_id=self.run,boot_id=self.boot,phase='cleanup',role='query',action='query',operation_id='d'*32)))
        self.value['phases']=[dict(phase='cleanup',role='query',request=self.request,complete=True)]
        self.picture=root/'synthetic.png'
        from PIL import Image
        Image.new('RGB',(100,100)).save(self.picture)
        self.start_phase()

    def file(self,name,text):
        p=self.root/name;p.write_text(text);return S.record(p)

    def command(self,script,body='',code=0,*,label='synthetic',host=0,timeout=False,before_dispatch=None):
        i=len(self.value['commands']);marker='__UITEST_EXIT_'+format(i+1,'032x')+'__='
        row=dict(argv=[self.hdc,'-t',self.target,'shell',script+'; task_ui_rc=$?; printf "\\n'+marker+'%s\\n" "$task_ui_rc"'],
                 label=label,exit_code=host,timed_out=timeout,
                 raw=self.file(str(i)+'.log',body+'\n'+marker+str(code)+'\n'))
        if before_dispatch is not None:before_dispatch(row)
        self.value['commands'].append(row);return i

    def observe(self,script,body,label='synthetic-observation'):
        body=body.rstrip('\n')  # Match original GuestUi.shell normalized observation bytes.
        i=self.command(script,body,label=label);r=self.file('obs-'+str(i)+'.txt',body)
        entry=dict(command=i,script=script,raw=r);self.observations[(r['path'],r['sha256'])]=entry
        self.value['observations'].append(entry);return r

    def observed(self,row,script=None):
        entry=self.observations[(row['path'],row['sha256'])]
        if script is not None:S.require(entry['script']==script,'synthetic observation script changed')
        return S.checked(row).read_text()

    def rewrite_observation(self,row,body):
        """Coherently change synthetic raw+normalized bytes to test later checks."""
        old=(row['path'],row['sha256']);entry=self.observations.pop(old)
        cmd=self.value['commands'][entry['command']];p=S.checked(cmd['raw']);text=p.read_text()
        footer=text[text.rfind('\n__UITEST_EXIT_'):]
        p.write_text(body+footer);cmd['raw']=S.record(p)
        p=Path(row['path']);p.write_text(body);row.clear();row.update(S.record(p))
        self.observations[(row['path'],row['sha256'])]=entry

    def reorder(self,order):
        """Coherently remap a synthetic journal; raw bytes are not normalized."""
        old=self.value['commands'];assert sorted(order)==list(range(len(old)))
        indexes={old_index:new_index for new_index,old_index in enumerate(order)}
        self.value['commands']=[old[i]for i in order]
        for row in self.observations.values():row['command']=indexes[row['command']]
        for row in self.value['staged']:row['command']=indexes[row['command']]
        for row in self.value['ui_actions']:
            for key in ('command','layout_command','screenshot_command'):row[key]=indexes[row[key]]
        for phase in self.value['phases']:
            for diagnostic in phase.get('diagnostics',[]):
                for key in ('layout_command','screenshot_command'):
                    if key in diagnostic:diagnostic[key]=indexes[diagnostic[key]]
        for guard in self.value.get('capture_retries',[]):
            guard['click_command']=indexes[guard['click_command']]
            for attempt in guard['attempts']:
                for key in ('layout_command','capture_command','screenshot_command'):
                    if key in attempt:attempt[key]=indexes[attempt[key]]

    def insert_at(self,index,script):
        added=self.command(script);order=list(range(added));order.insert(index,added);self.reorder(order)

    def remote(self,suffix):
        self.sequence+=1
        return '/data/local/tmp/qemu-capability-ui-'+self.namespace+'-'+str(self.sequence)+suffix

    def layout(self,window='31'):
        tree=dict(attributes=dict(id='knowledge_run',bundleName=self.bundle,visible='true',enabled='true',clickable='true',
                  bounds='[0,0][20,20]',hostWindowId=window,displayId='0'),children=[])
        remote=self.remote('.json');self.command('test ! -e '+remote+' && uitest dumpLayout -p '+remote)
        li=self.command('cat '+remote,json.dumps(tree));desc=self.file('layout-'+str(li)+'.json',json.dumps(tree))
        node=S.select_node(tree,self.bundle,identifier='knowledge_run',clickable=True)
        return tree,Path(desc['path']),node,li

    def ams_text(self,ability='159'):
        return 'User ID #100\n  current mission lists:{\n    Mission ID #31  mission name #[synthetic]\n      AbilityRecord ID #'+ability+'\n        app name ['+self.bundle+']\n        main name [EntryAbility]\n        bundle name ['+self.bundle+']\n        ability type [PAGE]\n        state #FOREGROUND\n }\n  ExtensionRecords:\n  AppRunningRecords:\n'

    def start_phase(self):
        """Actual-shaped single original request publication, still synthetic."""
        self.value['staged']=[];self.value['journals']=[]
        bms=dict(applicationInfo=dict(name=self.bundle,uid=20010043,accessTokenId=123,isSystemApp=True,
                 appPrivilegeLevel=S.project.ROLES['query'][1]),moduleInfos=[{'hapPath':'/data/app/query/entry.hap'}])
        raw=self.observe('bm dump -n '+self.bundle,json.dumps(bms))
        self.value['capture']=dict(roles={'query':{'bms':raw}})
        phase=self.value['phases'][0];phase['begin_boot']=self.observe('cat /proc/sys/kernel/random/boot_id',self.boot)
        self.command('aa start -b '+self.bundle+' -a EntryAbility')
        if self.ready_transition:
            path=self.remote('.json');index=self.command('test ! -e '+path+' && uitest dumpLayout -p '+path,
                'DumpLayout failed:Get window nodes failed\n',1)
            self.value['commands'][index]['layout_transition']=True
        if self.ready_missing:
            path=self.remote('.json');self.command('test ! -e '+path+' && uitest dumpLayout -p '+path)
            self.command('cat '+path,json.dumps(dict(attributes=dict(id='not-ready',bundleName=self.bundle),children=[])))
        self.layout()  # Actual original ready dump/read, before any stage.
        dest='/data/app/el2/100/base/'+self.bundle+'/files/knowledge-request.json';temp=dest+'.'+'f'*16+'.tmp'
        self.command('test ! -e '+temp+' && test ! -L '+temp)
        send=len(self.value['commands']);self.value['commands'].append(dict(argv=[self.hdc,'-t',self.target,'file','send',self.request['path'],temp],
              label='synthetic-request-send',exit_code=0,timed_out=False,raw=self.file(str(send)+'.log','FileTransfer finish\n')))
        self.command('chown 20010043:20010043 '+temp+' && chmod 600 '+temp)
        self.command('test ! -L '+dest+' && mv '+temp+' '+dest)
        hashed=self.observe('sha256sum '+dest,self.request['sha256']+'  '+dest)
        self.value['staged'].append(dict(local=self.request,remote=dest,sent_remote=temp,uid=20010043,mode='600',command=send,guest_hash=hashed))
        phase['curator_pid_before']=self.observe('pidof '+S.project.ROLES['curator'][0],'7466')

    def journal_poll(self,text,name='cleanup-journal'):
        raw=self.file(name+'-'+str(len(self.value['journals']))+'.jsonl',text)
        marker='__KNOWLEDGE_EOF_'+format(len(self.value['journals'])+1,'032x')+'__'
        remote='/data/app/el2/100/base/'+self.bundle+'/files/knowledge-'+self.run+'.jsonl'
        script='if test -f '+remote+'; then cat '+remote+' || exit 1; fi && printf '+S.shlex.quote('\n'+marker+'\n')
        observation=self.observe(script,text+'\n'+marker)
        self.value['journals'].append(dict(role='query',raw=raw,observation=observation,sentinel=marker,remote=remote))
        return raw

    def diagnostic(self,prefix=6):
        """Source-shaped readonly prefix; synthetic bytes are never actual guest evidence."""
        row=dict(reason='waiting for actual journal',diagnostic_only=True,journal_absence_proves_no_side_effect=False)
        self.value['phases'][0].setdefault('diagnostics',[]).append(row)
        if prefix<6:row['capture_error']='synthetic caught diagnostic failure'
        if not prefix:return row
        tree=dict(attributes=dict(id='knowledge_status',bundleName=self.bundle,visible='true',enabled='true',
                  clickable='false',bounds='[0,0][20,20]',text='Actual import/cleanup operation finished'),children=[])
        path=self.remote('.json');self.command('test ! -e '+path+' && uitest dumpLayout -p '+path)
        if prefix<2:return row
        li=self.command('cat '+path,json.dumps(tree));desc=self.file('diagnostic-'+str(li)+'.json',json.dumps(tree))
        row.update(layout=desc,layout_command=li,status=S.ready_node(tree,self.bundle,identifier='knowledge_status'))
        if prefix<3:return row
        path=self.remote('.png');self.command('test ! -e '+path+' && uitest screenCap -p '+path,'ScreenCap saved to '+path+'\n')
        if prefix<4:return row
        local=self.root/'ui'/(str(self.sequence).zfill(3)+'-cleanup-diagnostic.png');local.parent.mkdir(exist_ok=True)
        local.write_bytes(self.picture.read_bytes());receive=len(self.value['commands'])
        self.value['commands'].append(dict(argv=[self.hdc,'-t',self.target,'file','recv',path,str(local)],
             label='cleanup-diagnostic-receive-compositor-capture',exit_code=0,timed_out=False,raw=self.file(str(receive)+'.log','FileTransfer finish\n')))
        if prefix<5:return row
        row.update(screenshot=S.record(local),screenshot_command=receive,
                   screenshot_guest_hash=self.observe('sha256sum '+path,S.sha(local)+'  '+path))
        if prefix<6:return row
        row['ams']=self.observe('aa dump -a -u 100',self.ams_text());return row

    def finish_phase(self,*,waiting=False,diagnostic_prefix=6):
        if 'journal' in self.value['phases'][0]:return
        request=json.loads(S.checked(self.request).read_text());records=[]
        for n,event in enumerate(('begin','complete')):
            records.append(dict(schema_version=1,run_id=self.run,boot_id=self.boot,operation_id=request['operation_id'],role='query',phase='cleanup',
                 sequence=n+1,timestamp_ms=n+1,uid=20010043,token_id=123,event=event,api='request',value_json=json.dumps(request if n==0 else {}),error_code=0,error_message=''))
        if waiting:
            self.journal_poll(json.dumps(records[0])+'\n','preliminary')
            self.diagnostic(diagnostic_prefix)
        text=''.join(json.dumps(r)+'\n'for r in records);raw=self.journal_poll(text)
        self.value['phases'][0].update(journal=raw,end_boot=self.observe('cat /proc/sys/kernel/random/boot_id',self.boot))

    def capture(self,unavailable=False,forced_remote=None):
        remote=forced_remote or self.remote('.png');script='test ! -e '+remote+' && uitest screenCap -p '+remote
        ci=self.command(script,(S.PIXELMAP_UNAVAILABLE if unavailable else 'ScreenCap saved to '+remote)+'\n',
                        1 if unavailable else 0,label='cleanup-run-compositor-capture')
        if unavailable:return ci,remote,None
        i=len(self.value['commands']);self.value['commands'].append(dict(argv=[self.hdc,'-t',self.target,'file','recv',remote,str(self.picture)],
             label='cleanup-run-receive-compositor-capture',exit_code=0,timed_out=False,raw=self.file(str(i)+'.log','FileTransfer finish\n')))
        return ci,remote,i

    def complete(self,failures=1,*,window_change=False,boot_change=False,intruder=False,reuse_capture_path=False,waiting=False,diagnostic_prefix=6):
        attempts=[];first_capture=None
        for n in range(failures+1):
            a=dict(index=n,started_monotonic=float(n*2+1),boot_before=self.observe('cat /proc/sys/kernel/random/boot_id',self.boot))
            tree,path,node,li=self.layout('32'if window_change and n else'31')
            ams=self.observe('aa dump -a -u 100',self.ams_text())
            a.update(layout=S.record(path),layout_command=li,selected_node=node,ams=ams,window=S.capture_window(node,self.observed(ams),self.bundle))
            ci,remote,transfer=self.capture(n<failures,first_capture if reuse_capture_path else None);a['capture_command']=ci
            if first_capture is None:first_capture=remote
            if n<failures:
                a['outcome']='pixelmap_unavailable';self.value['commands'][ci]['capture_transition']={'retry':0,'attempt':n}
            else:
                digest=self.observe('sha256sum '+remote,S.sha(self.picture)+'  '+remote)
                a.update(outcome='success',screenshot=S.record(self.picture),screenshot_command=transfer,screenshot_guest_hash=digest)
            if intruder and n==0:self.command('uitest uiInput click 10 10')
            a['boot_after']=self.observe('cat /proc/sys/kernel/random/boot_id','changed-boot'if boot_change and n else self.boot)
            a['finished_monotonic']=float(n*2+2);attempts.append(a)
        click=self.command('uitest uiInput click 10 10');last=attempts[-1]
        action=dict(phase='cleanup',kind='run',bundle=self.bundle,selector={'identifier':'knowledge_run'},title=None,command=click,capture_retry=0,
                    **{k:last[k]for k in ('layout','layout_command','selected_node','ams','screenshot','screenshot_command','screenshot_guest_hash')})
        self.value['ui_actions']=[action]
        accepted=attempts[-1]['finished_monotonic']+.1;dispatch=accepted+.1
        self.value['capture_retries']=[dict(schema=S.CAPTURE_RETRY_SCHEMA,run_id=self.run,boot_id=self.boot,request=self.request,phase='cleanup',kind='run',
             bundle=self.bundle,action_index=0,attempts=attempts,outcome='complete',click_command=click,started_monotonic=0.0,
             deadline_monotonic=45.0,accepted_monotonic=accepted,dispatch_monotonic=dispatch)]
        self.value['commands'][click]['capture_dispatch']=dict(retry=0,accepted_monotonic=accepted,dispatch_monotonic=dispatch,deadline_monotonic=45.0)
        self.finish_phase(waiting=waiting,diagnostic_prefix=diagnostic_prefix)
        return self

    def verify(self):
        accepted=S.capture_retry_indices(self.value)
        S.verify_commands(self.value['commands'],self.hdc,self.target,capture_transitions=accepted)
        S.verify_capture_retries(self.value,self.env,self.data,self.observed,self.observations)
        S.verify_click(self.value['ui_actions'][0],self.value['commands'],self.hdc,self.target,self.observed)

    def collector(self,errors):
        c=S.Collector.__new__(S.Collector);c.value=self.value;c.data=self.data;c.env=self.env
        c.args=SimpleNamespace(hdc=Path(self.hdc));c.guest=SimpleNamespace(target=self.target)
        c.persist=mock.Mock();c.calls=[]
        def wait(*args,**kwargs):
            tree,path,node,_=self.layout();return tree,path,node
        c.wait_control=wait
        def observe(script,label):
            if script=='cat /proc/sys/kernel/random/boot_id':body=self.boot
            elif script=='aa dump -a -u 100':body=self.ams_text()
            elif script.startswith('sha256sum '):body=S.sha(self.picture)+'  '+script.split(' ',1)[1]
            else:raise AssertionError('unexpected synthetic observer')
            return self.observe(script,body,label)
        c.observe=observe
        pending=iter(errors)
        def screenshot(**kwargs):
            kind=next(pending,None);c.calls.append('capture')
            if kind:
                self.capture(kind!='png')
                if kind=='pixelmap':raise GuestUiCommandError('cleanup-run-compositor-capture',1,S.PIXELMAP_UNAVAILABLE)
                if kind=='other':raise GuestUiCommandError('cleanup-run-compositor-capture',1,'another guest error')
                if kind=='nonce':raise GuestUiCommandError('cleanup-run-compositor-capture',None,'missing footer')
                raise ValueError('actual PNG verification failed')
            self.capture(False);return self.picture
        def shell(script,label):
            self.command(script,label=label,before_dispatch=lambda row:c.capture_dispatch326(row['argv'],label,row))
            c.calls.append('click');return ''
        c.ui=SimpleNamespace(screenshot=screenshot,shell=shell)
        return c


class CaptureRetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='capture314-file-fake-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.f=Frame(self.root)

    def failed_row(self):
        self.f.complete();return self.f.value['commands'][self.f.value['capture_retries'][0]['attempts'][0]['capture_command']]

    def test_exact_pixelmap_guest1_has_known_real_footer(self):
        row=self.failed_row();self.assertTrue(S.capture_unavailable(row,self.f.hdc,self.f.target).endswith('.png'))

    def test_normal_single_attempt_and_png_verify(self):self.f.complete(0).verify()
    def test_one_transient_then_success_keeps_raw_and_one_click(self):
        self.f.complete().verify();self.assertEqual(sum('uiInput click'in r['argv'][-1]for r in self.f.value['commands']),1)
        self.assertEqual(len(S.capture_retry_indices(self.f.value)),1)

    def test_two_transients_are_bounded_and_raw_preserved(self):self.f.complete(2).verify()
    def test_host_failure_cannot_retry(self):
        r=self.failed_row();r['exit_code']=1
        with self.assertRaises(ValueError):S.capture_unavailable(r,self.f.hdc,self.f.target)
    def test_transport_timeout_cannot_retry(self):
        r=self.failed_row();r['timed_out']=True
        with self.assertRaises(ValueError):S.capture_unavailable(r,self.f.hdc,self.f.target)
    def test_wrong_target_or_label_refused(self):
        r=self.failed_row()
        for field,value in [('label','unrelated'),('argv',['/hdc','-t','foreign','shell',r['argv'][4]])]:
            changed=copy.deepcopy(r);changed[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):S.capture_unavailable(changed,self.f.hdc,self.f.target)
    def test_another_guest1_body_refused(self):
        r=self.failed_row();p=S.checked(r['raw']);p.write_bytes(p.read_bytes().replace(S.PIXELMAP_UNAVAILABLE.encode(),b'another failure'));r['raw']=S.record(p)
        with self.assertRaises(ValueError):S.capture_unavailable(r,self.f.hdc,self.f.target)
    def test_wrong_missing_duplicate_or_nonterminal_footer_refused(self):
        r=self.failed_row();original=S.checked(r['raw']).read_text()
        variants=[original.replace('__UITEST_EXIT_','__WRONG_EXIT_'),original.split('__UITEST_EXIT_')[0],original+original,original+'later output\n']
        for i,text in enumerate(variants):
            changed=copy.deepcopy(r);changed['raw']=self.f.file('bad-'+str(i)+'.log',text)
            with self.subTest(i=i),self.assertRaises(ValueError):S.capture_unavailable(changed,self.f.hdc,self.f.target)
    def test_stale_actual_raw_hash_refused(self):
        r=self.failed_row();S.checked(r['raw']).write_text('changed')
        with self.assertRaises(ValueError):S.capture_unavailable(r,self.f.hdc,self.f.target)
    def test_guest1_or_annotation_alone_does_not_pass_commands(self):
        self.f.complete()
        with self.assertRaises(ValueError):S.verify_commands(self.f.value['commands'],self.f.hdc,self.f.target)
    def test_unbound_annotation_without_receipt_refused(self):
        self.f.complete();del self.f.value['capture_retries'];self.f.value['ui_actions'][0].pop('capture_retry')
        with self.assertRaises(ValueError):S.capture_retry_indices(self.f.value)
    def test_boolean_annotation_fields_are_not_operation_indexes(self):
        self.f.complete();ci=self.f.value['capture_retries'][0]['attempts'][0]['capture_command']
        self.f.value['commands'][ci]['capture_transition']['retry']=False
        with self.assertRaises(ValueError):S.capture_retry_indices(self.f.value)
    def test_wrong_run_boot_request_phase_or_role_refused(self):
        self.f.complete();guard=self.f.value['capture_retries'][0]
        for field in ('run_id','boot_id','phase','bundle'):
            old=guard[field];guard[field]='foreign'
            with self.subTest(field=field),self.assertRaises(ValueError):S.capture_retry_indices(self.f.value)
            guard[field]=old
    def test_actual_kernel_boot_change_refused(self):
        self.f.complete(boot_change=True)
        with self.assertRaises(ValueError):self.f.verify()
    def test_actual_window_change_refused(self):
        self.f.complete(window_change=True)
        with self.assertRaises(ValueError):self.f.verify()
    def test_reused_failed_png_destination_refused(self):
        self.f.complete(reuse_capture_path=True)
        with self.assertRaises(ValueError):self.f.verify()
    def test_forged_window_metadata_refused(self):
        self.f.complete();self.f.value['capture_retries'][0]['attempts'][0]['window']['host_window_id']='999'
        with self.assertRaises(ValueError):self.f.verify()
    def test_duplicate_foreground_page_refused(self):
        tree,path,node,li=self.f.layout()
        with self.assertRaises(ValueError):S.capture_window(node,self.f.ams_text()+self.f.ams_text('160'),self.f.bundle)
    def test_public_action_inside_retry_span_refused(self):
        self.f.complete(intruder=True)
        with self.assertRaises(ValueError):self.f.verify()
    def test_over_budget_or_nonfinite_time_refused(self):
        self.f.complete();a=self.f.value['capture_retries'][0]['attempts']
        for value in (True,float('inf'),float('nan'),99.0):
            old=a[-1]['finished_monotonic'];a[-1]['finished_monotonic']=value
            with self.subTest(value=value),self.assertRaises(ValueError):S.capture_retry_indices(self.f.value)
            a[-1]['finished_monotonic']=old
    def test_four_attempts_refused(self):
        self.f.complete(3)
        with self.assertRaises(ValueError):S.capture_retry_indices(self.f.value)
    def test_attempt_omission_or_extra_field_refused(self):
        self.f.complete();a=self.f.value['capture_retries'][0]['attempts'][0];a['invented']=True
        with self.assertRaises(ValueError):S.capture_retry_indices(self.f.value)
    def test_prepared_or_failed_receipt_is_not_completed_action(self):
        self.f.complete();guard=self.f.value['capture_retries'][0]
        for state in ('prepared','failed'):
            guard['outcome']=state
            with self.subTest(state=state),self.assertRaises(ValueError):S.capture_retry_indices(self.f.value)
    def test_final_action_cannot_substitute_layout_or_capture(self):
        self.f.complete();self.f.value['ui_actions'][0]['layout_command']=0
        with self.assertRaises(ValueError):S.capture_retry_indices(self.f.value)
    def test_actual_success_png_is_still_mandatory(self):
        self.f.complete();self.f.picture.write_bytes(b'not png');record=S.record(self.f.picture)
        self.f.value['ui_actions'][0]['screenshot']=record;self.f.value['capture_retries'][0]['attempts'][-1]['screenshot']=record
        at=self.f.value['capture_retries'][0]['attempts'][-1]
        remote=self.f.value['commands'][at['screenshot_command']]['argv'][-2]
        self.f.rewrite_observation(at['screenshot_guest_hash'],record['sha256']+'  '+remote)
        with self.assertRaises(Exception):self.f.verify()
    def test_collector_retries_only_readonly_capture_and_clicks_once(self):
        c=self.f.collector(['pixelmap',None]);clock=itertools.count(0,.1)
        with mock.patch.object(S.time,'monotonic',side_effect=lambda:next(clock)),mock.patch.object(S.time,'sleep'):
            c.click(self.f.bundle,{'identifier':'knowledge_run'},'run','cleanup',request=self.f.request)
        self.assertEqual(c.calls,['capture','capture','click']);self.assertEqual(len(c.value['capture_retries'][0]['attempts']),2)
        self.f.finish_phase()
        self.f.verify()
    def test_collector_other_error_nonce_or_png_error_is_not_retried(self):
        for error in ('other','nonce','png'):
            with self.subTest(error=error):
                root=self.root/error;root.mkdir();f=Frame(root);c=f.collector([error])
                with self.assertRaises(ValueError):c.click(f.bundle,{'identifier':'knowledge_run'},'run','cleanup',request=f.request)
                self.assertEqual(c.calls,['capture']);self.assertEqual(c.value['capture_retries'][0]['outcome'],'failed')
    def test_collector_exhaustion_keeps_three_actual_failures_and_no_click(self):
        c=self.f.collector(['pixelmap']*3);clock=itertools.count(0,.1)
        with mock.patch.object(S.time,'monotonic',side_effect=lambda:next(clock)),mock.patch.object(S.time,'sleep'),self.assertRaises(GuestUiCommandError):
            c.click(self.f.bundle,{'identifier':'knowledge_run'},'run','cleanup',request=self.f.request)
        self.assertEqual(c.calls,['capture']*3);self.assertEqual(len(c.value['capture_retries'][0]['attempts']),3)
        self.assertEqual(c.value['ui_actions'],[])
    def test_success_after_time_budget_never_clicks(self):
        c=self.f.collector([None]);times=iter([0.0,0.0,0.0,46.0,46.0])
        with mock.patch.object(S.time,'monotonic',side_effect=lambda:next(times)),self.assertRaises(ValueError):
            c.click(self.f.bundle,{'identifier':'knowledge_run'},'run','cleanup',request=self.f.request)
        self.assertEqual(c.calls,['capture']);self.assertEqual(c.value['ui_actions'],[])
    def test_another_phase_still_fails_pixelmap_without_retry(self):
        c=self.f.collector(['pixelmap'])
        with self.assertRaises(GuestUiCommandError):c.click(self.f.bundle,{'identifier':'knowledge_run'},'run','baseline')
        self.assertEqual(c.calls,['capture']);self.assertNotIn('capture_retries',c.value)


ACTUAL296_AMS = 'User ID #100\n  current mission lists:{\n    Mission ID #29  mission name #[#org.harmonycontrib.knowledgeimporter:entry:EntryAbility]  lockedState #0  mission affinity #[]\n      AbilityRecord ID #157\n        app name [org.harmonycontrib.knowledgeimporter]\n        main name [EntryAbility]\n        bundle name [org.harmonycontrib.knowledgeimporter]\n        ability type [PAGE]\n        state #BACKGROUND  start time [116634]\n        app state #BACKGROUND\n        ready #1  window attached #0  launcher #0\n        callee connections: \n        isKeepAlive: false\n    Mission ID #30  mission name #[#org.harmonycontrib.knowledgedenied:entry:EntryAbility]  lockedState #0  mission affinity #[]\n      AbilityRecord ID #158\n        app name [org.harmonycontrib.knowledgedenied]\n        main name [EntryAbility]\n        bundle name [org.harmonycontrib.knowledgedenied]\n        ability type [PAGE]\n        state #BACKGROUND  start time [186202]\n        app state #BACKGROUND\n        ready #1  window attached #0  launcher #0\n        callee connections: \n        isKeepAlive: false\n    Mission ID #31  mission name #[#org.harmonycontrib.knowledgequery:entry:EntryAbility]  lockedState #0  mission affinity #[]\n      AbilityRecord ID #159\n        app name [org.harmonycontrib.knowledgequery]\n        main name [EntryAbility]\n        bundle name [org.harmonycontrib.knowledgequery]\n        ability type [PAGE]\n        state #FOREGROUND  start time [197521]\n        app state #FOREGROUND\n        ready #1  window attached #0  launcher #0\n        callee connections: \n        isKeepAlive: false\n    Mission ID #33  mission name #[#org.harmonycontrib.knowledgecurator:entry:EntryAbility]  lockedState #0  mission affinity #[]\n      AbilityRecord ID #161\n        app name [org.harmonycontrib.knowledgecurator]\n        main name [EntryAbility]\n        bundle name [org.harmonycontrib.knowledgecurator]\n        ability type [PAGE]\n        state #BACKGROUND  start time [225844]\n        app state #BACKGROUND\n        ready #1  window attached #0  launcher #0\n        callee connections: \n        isKeepAlive: false\n }\n  ExtensionRecords:\n    uri [/com.example.kikakeyboard/entry/ServiceExtAbility]\n      AbilityRecord ID #10   state #ACTIVE   start time [8399]\n      main name [ServiceExtAbility]\n      bundle name [com.example.kikakeyboard]\n      ability type [SERVICE]\n      app state #BEGIN\n        isKeepAlive: false\n      Connections: 1\n       > com.example.kikakeyboard/ServiceExtAbility   connectionState #CONNECTED\n    uri [/com.ohos.medialibrary.medialibrarydata/entry/DataShareExtAbility]\n      AbilityRecord ID #2   state #ACTIVE   start time [7612]\n      main name [DataShareExtAbility]\n      bundle name [com.ohos.medialibrary.medialibrarydata]\n      ability type [SERVICE]\n      app state #BEGIN\n        isKeepAlive: false\n      Connections: 4\n       > com.ohos.medialibrary.medialibrarydata/DataShareExtAbility   connectionState #CONNECTED\n       > com.ohos.medialibrary.medialibrarydata/DataShareExtAbility   connectionState #CONNECTED\n       > com.ohos.medialibrary.medialibrarydata/DataShareExtAbility   connectionState #CONNECTED\n       > com.ohos.medialibrary.medialibrarydata/DataShareExtAbility   connectionState #CONNECTED\n    uri [/com.ohos.sceneboard/phone_sceneboard/com.ohos.sceneboard.MainAbility]\n      AbilityRecord ID #1   state #ACTIVE   start time [7571]\n      main name [com.ohos.sceneboard.MainAbility]\n      bundle name [com.ohos.sceneboard]\n      ability type [SERVICE]\n      app state #FOREGROUND\n        isKeepAlive: true\n      Connections: 0\n    uri [/com.ohos.sceneboard/themeservice_core/ThemeServiceAbility]\n      AbilityRecord ID #7   state #ACTIVE   start time [8094]\n      main name [ThemeServiceAbility]\n      bundle name [com.ohos.sceneboard]\n      ability type [SERVICE]\n      app state #FOREGROUND\n        isKeepAlive: false\n      Connections: 0\n    PendingWantRecords:\n        PendWantRecord ID #1  type #4\n        bundle name []\n        result who []\n        request code #0  flags #134217728\n        resolved type []\n        Wants:\n          uri [///]\n          resolved types []\n  AppRunningRecords:\n    AppRunningRecord ID #0\n      process name [com.ohos.sceneboard]\n      pid #1612  uid #20010010\n      state #FOREGROUND\n    AppRunningRecord ID #1\n      process name [com.ohos.medialibrary.medialibrarydata]\n      pid #1655  uid #20010014\n      state #READY\n    AppRunningRecord ID #2\n      process name [com.example.kikakeyboard:inputMethod]\n      pid #1846  uid #20010036\n      state #READY\n    AppRunningRecord ID #3\n      process name [org.harmonycontrib.knowledgeimporter]\n      pid #6137  uid #20010041\n      state #BACKGROUND\n    AppRunningRecord ID #4\n      process name [org.harmonycontrib.knowledgedenied]\n      pid #6459  uid #20010042\n      state #BACKGROUND\n    AppRunningRecord ID #5\n      process name [org.harmonycontrib.knowledgequery]\n      pid #7076  uid #20010043\n      state #FOREGROUND\n    AppRunningRecord ID #6\n      process name [org.harmonycontrib.knowledgecurator]\n      pid #7466  uid #20010044\n      state #BACKGROUND'
BACKGROUND_QUERY_AMS = 'User ID #100\n  current mission lists:{\n    Mission ID #31  mission name #[#org.harmonycontrib.knowledgequery:entry:EntryAbility]  lockedState #0  mission affinity #[]\n      AbilityRecord ID #159\n        app name [org.harmonycontrib.knowledgequery]\n        main name [EntryAbility]\n        bundle name [org.harmonycontrib.knowledgequery]\n        ability type [PAGE]\n        state #BACKGROUND  start time [197521]\n        app state #BACKGROUND\n        ready #1  window attached #0  launcher #0\n        callee connections:\n        isKeepAlive: false\n }\n  ExtensionRecords:\n    uri [/com.ohos.sceneboard/phone_sceneboard/com.ohos.sceneboard.MainAbility]\n      AbilityRecord ID #1   state #ACTIVE   start time [7571]\n      main name [com.ohos.sceneboard.MainAbility]\n      bundle name [com.ohos.sceneboard]\n      ability type [SERVICE]\n      app state #FOREGROUND\n        isKeepAlive: true\n      Connections: 0\n  AppRunningRecords:\n    AppRunningRecord ID #0\n      process name [com.ohos.sceneboard]\n      pid #1612  uid #20010010\n      state #FOREGROUND\n'

class Review320BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='capture326-boundary-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.f=Frame(self.root)

    def oi(self,row):return self.f.observations[(row['path'],row['sha256'])]['command']

    def test_all_retry_shell_kinds_reject_post_footer_operation(self):
        self.f.complete();g=self.f.value['capture_retries'][0];a=g['attempts'][-1]
        indexes=[self.oi(a['boot_before']),self.oi(a['ams']),a['layout_command']-1,a['layout_command'],a['capture_command'],self.oi(a['screenshot_guest_hash'])]
        for index in indexes:
            row=self.f.value['commands'][index];original=row['argv'][4]
            row['argv'][4]+='; uitest uiInput click 10 10 >/dev/null 2>&1'
            with self.subTest(index=index),self.assertRaises(ValueError):self.f.verify()
            row['argv'][4]=original

    def test_retry_wrapper_rejects_substitution_redirection_and_alternate_suffix(self):
        self.f.complete();a=self.f.value['capture_retries'][0]['attempts'][0];index=self.oi(a['ams'])
        row=self.f.value['commands'][index];original=row['argv'][4]
        variants=[original.replace('"$task_ui_rc"','"$(uitest uiInput click 10 10 >/dev/null; printf 0)"'),
                  original+' >/dev/null',original.replace('printf "\\n','printf "\\nextra')]
        for variant in variants:
            row['argv'][4]=variant
            with self.subTest(variant=variant),self.assertRaises(ValueError):self.f.verify()
        row['argv'][4]=original

    def test_actual296_full_AMS_own_PAGE_is_foreground(self):
        tree,path,node,li=self.f.layout()
        self.assertEqual(S.capture_window(node,ACTUAL296_AMS,self.f.bundle),dict(host_window_id='31',display_id='0',ability_record_id='159'))

    def test_last_background_PAGE_cannot_borrow_AppRunning_foreground(self):
        tree,path,node,li=self.f.layout()
        with self.assertRaises(ValueError):S.capture_window(node,BACKGROUND_QUERY_AMS,self.f.bundle)

    def test_wrong_or_duplicate_AMS_user_heading_refused(self):
        tree,path,node,li=self.f.layout()
        for text in [self.f.ams_text().replace('User ID #100','User ID #0'),self.f.ams_text()+'User ID #100\n']:
            with self.subTest(text=text[:40]),self.assertRaises(ValueError):S.capture_window(node,text,self.f.bundle)

    def test_own_PAGE_missing_duplicate_conflicting_or_inline_fields_refused(self):
        tree,path,node,li=self.f.layout();base=self.f.ams_text()
        variants=[base.replace('        state #FOREGROUND\n',''),
                  base.replace('        state #FOREGROUND','        state #BACKGROUND\n        state #FOREGROUND'),
                  base.replace('        bundle name ['+self.f.bundle+']','        bundle name [foreign]\n        bundle name ['+self.f.bundle+']'),
                  base.replace('      AbilityRecord ID #159','      AbilityRecord ID #159   state #FOREGROUND'),
                  base.replace('        main name [EntryAbility]','        main name [OtherAbility]')]
        for number,text in enumerate(variants):
            with self.subTest(number=number),self.assertRaises(ValueError):S.capture_window(node,text,self.f.bundle)

    def test_foreground_in_next_mission_or_extension_cannot_be_borrowed(self):
        tree,path,node,li=self.f.layout();base=self.f.ams_text().replace('        state #FOREGROUND','        state #BACKGROUND')
        extra='    Mission ID #44  mission name #[foreign]\n      AbilityRecord ID #200\n        app name [foreign]\n        main name [EntryAbility]\n        bundle name [foreign]\n        ability type [PAGE]\n        state #FOREGROUND\n'
        for text in (base.replace(' }\n',extra+' }\n'),BACKGROUND_QUERY_AMS):
            with self.assertRaises(ValueError):S.capture_window(node,text,self.f.bundle)

    def test_two_own_foreground_PAGE_records_are_ambiguous(self):
        tree,path,node,li=self.f.layout();base=self.f.ams_text();own=base.split('    Mission ID #31',1)[1].split(' }',1)[0]
        extra='    Mission ID #32'+own.replace('#159','#160')
        with self.assertRaises(ValueError):S.capture_window(node,base.replace(' }\n',extra+' }\n'),self.f.bundle)

    def test_actual_shaped_publication_precedes_retry_and_complete_journal(self):
        self.f.complete().verify();g=self.f.value['capture_retries'][0];s=self.f.value['staged'][0]
        self.assertLess(self.oi(s['guest_hash']),self.oi(g['attempts'][0]['boot_before']))
        phase=self.f.value['phases'][0];j=self.f.value['journals'][0]
        self.assertLess(g['click_command'],self.oi(j['observation']));self.assertLess(self.oi(j['observation']),self.oi(phase['end_boot']))

    def test_whole_request_publication_after_click_is_rejected(self):
        self.f.complete();g=self.f.value['capture_retries'][0];s=self.f.value['staged'][0]
        block=list(range(s['command']-1,s['command']+4));order=[i for i in range(len(self.f.value['commands']))if i not in block]
        insert=order.index(g['click_command'])+1;order[insert:insert]=block;self.f.reorder(order)
        with self.assertRaises(ValueError):self.f.verify()

    def test_sent_early_but_hash_late_is_rejected(self):
        self.f.complete();g=self.f.value['capture_retries'][0];hashed=self.oi(self.f.value['staged'][0]['guest_hash'])
        order=[i for i in range(len(self.f.value['commands']))if i!=hashed];order.insert(order.index(g['click_command'])+1,hashed);self.f.reorder(order)
        with self.assertRaises(ValueError):self.f.verify()

    def test_publication_after_first_boot_is_rejected(self):
        self.f.complete();g=self.f.value['capture_retries'][0];s=self.f.value['staged'][0];first=self.oi(g['attempts'][0]['boot_before'])
        block=list(range(s['command']-1,s['command']+4));order=[i for i in range(len(self.f.value['commands']))if i not in block]
        at=order.index(first)+1;order[at:at]=block;self.f.reorder(order)
        with self.assertRaises(ValueError):self.f.verify()

    def test_untracked_request_supersession_before_retry_is_rejected(self):
        self.f.complete();g=self.f.value['capture_retries'][0];first=self.oi(g['attempts'][0]['boot_before']);dest=self.f.value['staged'][0]['remote']
        self.f.insert_at(first,'test ! -L '+dest+' && mv '+dest+'.untracked.tmp '+dest)
        with self.assertRaises(ValueError):self.f.verify()

    def test_second_send_inside_request_interval_is_rejected(self):
        self.f.complete();first=self.oi(self.f.value['capture_retries'][0]['attempts'][0]['boot_before']);stage=self.f.value['staged'][0]
        added=self.f.command('true');self.f.value['commands'][added]['argv']=[self.f.hdc,'-t',self.f.target,'file','send',self.f.request['path'],stage['remote']+'.extra.tmp']
        order=list(range(added));order.insert(first,added);self.f.reorder(order)
        with self.assertRaises(ValueError):self.f.verify()

    def test_extra_Run_before_retry_or_after_sole_click_is_rejected(self):
        for position in ('before','after'):
            root=self.root/position;root.mkdir();f=Frame(root).complete();g=f.value['capture_retries'][0]
            index=f.observations[(g['attempts'][0]['boot_before']['path'],g['attempts'][0]['boot_before']['sha256'])]['command']if position=='before'else g['click_command']+1
            f.insert_at(index,'uitest uiInput click 10 10')
            with self.subTest(position=position),self.assertRaises(ValueError):f.verify()

    def test_phase_end_before_click_or_journal_before_click_is_rejected(self):
        self.f.complete();phase=self.f.value['phases'][0];phase['end_boot']=self.f.value['capture_retries'][0]['attempts'][-1]['boot_after']
        with self.assertRaises(ValueError):self.f.verify()
        root=self.root/'journal';root.mkdir();f=Frame(root).complete();g=f.value['capture_retries'][0]
        ji=f.observations[(f.value['journals'][0]['observation']['path'],f.value['journals'][0]['observation']['sha256'])]['command']
        first=f.observations[(g['attempts'][0]['boot_before']['path'],g['attempts'][0]['boot_before']['sha256'])]['command']
        order=[i for i in range(len(f.value['commands']))if i!=ji];order.insert(order.index(first),ji);f.reorder(order)
        with self.assertRaises(ValueError):f.verify()

    def test_request_operation_nonce_must_join_complete_raw_journal(self):
        self.f.complete();phase=self.f.value['phases'][0];journal=self.f.value['journals'][0]
        p=S.checked(phase['journal']);rows=[json.loads(line)for line in p.read_text().splitlines()];rows[0]['operation_id']='f'*32
        text=''.join(json.dumps(row)+'\n'for row in rows);p.write_text(text);phase['journal'].clear();phase['journal'].update(S.record(p))
        self.f.rewrite_observation(journal['observation'],text+'\n'+journal['sentinel'])
        with self.assertRaises(ValueError):self.f.verify()

    def test_post_persist_budget_expiry_never_dispatches_click(self):
        c=self.f.collector([None]);clock={'now':0.0}
        def persist():
            if c.value.get('capture_retries')and c.value['capture_retries'][0]['outcome']=='prepared':clock['now']=45.2
        c.persist=mock.Mock(side_effect=persist)
        with mock.patch.object(S.time,'monotonic',side_effect=lambda:clock['now']),self.assertRaises(ValueError):
            c.click(self.f.bundle,{'identifier':'knowledge_run'},'run','cleanup',request=self.f.request)
        self.assertEqual(c.calls,['capture']);self.assertEqual(c.value['ui_actions'],[])
        self.assertIsNone(c.value['capture_retries'][0]['dispatch_monotonic'])

    def test_actual_command_health_delay_rechecks_deadline_before_Popen(self):
        self.f.complete();c=self.f.collector([None]);g=c.value['capture_retries'][0];g.update(outcome='prepared',accepted_monotonic=44.8,dispatch_monotonic=None)
        c.args.output=self.root;c.pending_capture_dispatch326=dict(retry=0,script='uitest uiInput click 10 10');clock={'now':44.9}
        c.guest.healthy=lambda:clock.update(now=45.2);argv=list(c.value['commands'][g['click_command']]['argv'])
        with mock.patch.object(S.time,'monotonic',side_effect=lambda:clock['now']),mock.patch.object(S.subprocess,'Popen')as popen,self.assertRaises(ValueError):
            c.command(argv,'cleanup-run-click')
        popen.assert_not_called();self.assertIsNone(g['dispatch_monotonic'])

    def test_actual_command_below_deadline_stamps_same_constructor_row(self):
        self.f.complete();c=self.f.collector([None]);g=c.value['capture_retries'][0];g.update(outcome='prepared',accepted_monotonic=44.8,dispatch_monotonic=None)
        c.args.output=self.root;c.pending_capture_dispatch326=dict(retry=0,script='uitest uiInput click 10 10');c.guest.healthy=lambda:None
        argv=list(c.value['commands'][g['click_command']]['argv']);process=SimpleNamespace(wait=lambda timeout:None,returncode=0)
        with mock.patch.object(S.time,'monotonic',return_value=44.9),mock.patch.object(S.subprocess,'Popen',return_value=process)as popen:
            c.command(argv,'cleanup-run-click')
        self.assertEqual(popen.call_count,1);self.assertEqual(g['dispatch_monotonic'],44.9)
        self.assertEqual(c.value['commands'][-1]['capture_dispatch']['dispatch_monotonic'],44.9)

    def test_dispatch_receipt_missing_forged_or_over_budget_is_rejected(self):
        self.f.complete();g=self.f.value['capture_retries'][0];row=self.f.value['commands'][g['click_command']]
        original=copy.deepcopy(row['capture_dispatch']);row.pop('capture_dispatch')
        with self.assertRaises(ValueError):self.f.verify()
        row['capture_dispatch']=original
        for field,value in [('accepted_monotonic',46.0),('dispatch_monotonic',46.0),('started_monotonic',True),('deadline_monotonic',99.0)]:
            old=g[field];g[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.f.verify()
            g[field]=old
        root=self.root/'stripped';root.mkdir();f=Frame(root).complete(0);guard=f.value.pop('capture_retries')[0]
        f.value['ui_actions'][0].pop('capture_retry');f.value['commands'][guard['click_command']].pop('capture_dispatch')
        with self.assertRaises(ValueError):f.verify()

    def test_callback_without_actual_dispatch_gate_cannot_complete_receipt(self):
        c=self.f.collector([None]);c.ui.shell=lambda script,label:''
        with self.assertRaises(ValueError):c.click(self.f.bundle,{'identifier':'knowledge_run'},'run','cleanup',request=self.f.request)
        self.assertEqual(c.value['ui_actions'],[]);self.assertEqual(c.value['capture_retries'][0]['outcome'],'failed')


class Review352IntervalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='capture350-file-fake-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.f=Frame(self.root)

    def oi(self,row):return self.f.observations[(row['path'],row['sha256'])]['command']
    def first(self):return self.oi(self.f.value['capture_retries'][0]['attempts'][0]['boot_before'])
    def script(self,index,value):
        row=self.f.value['commands'][index];suffix=row['argv'][4].split('; task_ui_rc=$?; printf ',1)[1]
        row['argv'][4]=value+'; task_ui_rc=$?; printf '+suffix
    def reject_insert(self,script,at=None):
        self.f.complete();self.f.insert_at(self.first() if at is None else at,script)
        with self.assertRaises(ValueError):self.f.verify()

    def test_tab_public_action_before_first_boot_rejected(self):self.reject_insert('uitest\tuiInput click 10 10')
    def test_multiple_space_public_action_before_first_boot_rejected(self):self.reject_insert('uitest  uiInput click 10 10')
    def test_variable_expanded_request_replacement_rejected(self):
        self.reject_insert('p=/data/app/el2/100/base/'+self.f.bundle+'/files;mv "$p/knowledge-request.json.untracked.tmp" "$p/knowledge-request.json"')
    def test_indirect_public_action_rejected(self):self.reject_insert('u=uitest; "$u" uiInput click 10 10')
    def test_indirect_shell_dispatch_rejected(self):self.reject_insert('sh -c "uitest uiInput click 10 10"')
    def test_arbitrary_readonly_command_without_typed_owner_rejected(self):self.reject_insert('cat /proc/uptime')
    def test_unbound_exact_boot_query_is_not_harmless_gap(self):self.reject_insert('cat /proc/sys/kernel/random/boot_id')
    def test_unbound_exact_AMS_query_is_not_harmless_gap(self):self.reject_insert('aa dump -a -u 100')

    def test_every_phase_boundary_refuses_unbound_canonical_shell(self):
        self.f.complete(waiting=True);phase=self.f.value['phases'][0]
        for index in range(self.oi(phase['begin_boot'])+1,self.oi(phase['end_boot'])+1):
            root=self.root/('boundary-'+str(index));root.mkdir();f=Frame(root).complete(waiting=True)
            f.insert_at(index,'true')
            with self.subTest(index=index),self.assertRaises(ValueError):f.verify()

    def test_actual_source_ready_and_curator_PID_gap_accepted(self):
        # Actual296: ready651/652; stage653..657; typed singletonPID658.
        self.f.complete().verify();phase=self.f.value['phases'][0];stage=self.f.value['staged'][0]
        self.assertEqual(self.oi(phase['curator_pid_before']),self.oi(stage['guest_hash'])+1)
        self.assertEqual(self.first(),self.oi(phase['curator_pid_before'])+1)
        self.assertEqual(self.f.observed(phase['curator_pid_before']),'7466')
    def test_actual_ready_NodeNotReady_poll_can_precede_selected_Run(self):
        root=self.root/'node-poll';root.mkdir();Frame(root,ready_missing=True).complete().verify()
    def test_typed_exact_layout_transition_can_precede_actual_ready_read(self):
        root=self.root/'layout-poll';root.mkdir();Frame(root,ready_transition=True).complete().verify()
    def test_missing_typed_curator_PID_refused(self):
        self.f.complete();del self.f.value['phases'][0]['curator_pid_before']
        with self.assertRaises(ValueError):self.f.verify()
    def test_foreign_pid_command_cannot_own_curator_observation(self):
        self.f.complete();self.script(self.oi(self.f.value['phases'][0]['curator_pid_before']),'pidof '+self.f.bundle)
        with self.assertRaises(ValueError):self.f.verify()
    def test_non_singleton_curator_PID_refused(self):
        self.f.complete();self.f.rewrite_observation(self.f.value['phases'][0]['curator_pid_before'],'7466 7467')
        with self.assertRaises(ValueError):self.f.verify()
    def test_extra_command_in_pre_stage_ready_region_rejected(self):
        self.f.complete();self.f.insert_at(self.f.value['staged'][0]['command']-1,'uitest\tuiInput click 10 10')
        with self.assertRaises(ValueError):self.f.verify()
    def test_ready_pair_may_not_read_another_UI_path(self):
        self.f.complete();begin=self.oi(self.f.value['phases'][0]['begin_boot']);self.script(begin+3,'cat '+self.f.remote('.json'))
        with self.assertRaises(ValueError):self.f.verify()
    def test_ready_namespace_may_not_differ_from_retry_namespace(self):
        self.f.complete();begin=self.oi(self.f.value['phases'][0]['begin_boot'])
        for i in (begin+2,begin+3):
            row=self.f.value['commands'][i];row['argv'][4]=row['argv'][4].replace(self.f.namespace,'9'*32)
        with self.assertRaises(ValueError):self.f.verify()

    def test_actual_import_style_poll_diagnostic_poll_order_accepted(self):
        # Actual296 import: poll363, dump364/read365/capture366/recv367/SHA368/AMS369, poll370/end371.
        self.f.complete(waiting=True).verify();phase=self.f.value['phases'][0];d=phase['diagnostics'][0]
        self.assertEqual(d['screenshot_command'],d['layout_command']+2)
        self.assertEqual(self.oi(d['ams']),d['layout_command']+4)
        self.assertEqual(len(self.f.value['journals']),2)
    def test_each_caught_diagnostic_prefix_remains_readonly_and_preserved(self):
        for prefix in range(6):
            root=self.root/str(prefix);root.mkdir();f=Frame(root).complete(waiting=True,diagnostic_prefix=prefix)
            with self.subTest(prefix=prefix):
                f.verify();self.assertIn('capture_error',f.value['phases'][0]['diagnostics'][0])
    def test_diagnostic_commands_without_phase_record_rejected(self):
        self.f.complete(waiting=True);del self.f.value['phases'][0]['diagnostics']
        with self.assertRaises(ValueError):self.f.verify()
    def test_diagnostic_extra_command_between_capture_and_receive_rejected(self):
        self.f.complete(waiting=True);d=self.f.value['phases'][0]['diagnostics'][0]
        self.f.insert_at(d['screenshot_command'],'uitest  uiInput click 10 10')
        with self.assertRaises(ValueError):self.f.verify()
    def test_diagnostic_metadata_does_not_admit_extra_commands(self):
        self.f.complete(waiting=True);d=self.f.value['phases'][0]['diagnostics'][0]
        self.f.insert_at(self.oi(d['ams'])+1,'p=/data; mv "$p/a" "$p/b"')
        with self.assertRaises(ValueError):self.f.verify()
    def test_diagnostic_changed_AMS_or_SHA_script_rejected(self):
        for key in ('ams','screenshot_guest_hash'):
            root=self.root/key;root.mkdir();f=Frame(root).complete(waiting=True);d=f.value['phases'][0]['diagnostics'][0]
            index=f.observations[(d[key]['path'],d[key]['sha256'])]['command'];row=f.value['commands'][index]
            row['argv'][4]='true; task_ui_rc=$?; printf '+row['argv'][4].split('; task_ui_rc=$?; printf ',1)[1]
            with self.subTest(key=key),self.assertRaises(ValueError):f.verify()
    def test_diagnostic_foreign_local_receive_refused(self):
        self.f.complete(waiting=True);d=self.f.value['phases'][0]['diagnostics'][0]
        self.f.value['commands'][d['screenshot_command']]['argv'][-1]=str(self.root/'foreign.png')
        with self.assertRaises(ValueError):self.f.verify()
    def test_extra_diagnostic_record_cannot_reuse_actual_commands(self):
        self.f.complete(waiting=True);phase=self.f.value['phases'][0];phase['diagnostics'].append(copy.deepcopy(phase['diagnostics'][0]))
        with self.assertRaises(ValueError):self.f.verify()
    def test_preliminary_journal_poll_must_have_original_transport_record(self):
        self.f.complete(waiting=True);self.f.value['journals'].pop(0)
        with self.assertRaises(ValueError):self.f.verify()
    def test_duplicate_journal_poll_record_rejected(self):
        self.f.complete(waiting=True);self.f.value['journals'].append(copy.deepcopy(self.f.value['journals'][0]))
        with self.assertRaises(ValueError):self.f.verify()
    def test_foreign_role_journal_cannot_consume_query_interval(self):
        self.f.complete(waiting=True);self.f.value['journals'][0]['role']='curator'
        with self.assertRaises(ValueError):self.f.verify()
    def test_extra_command_after_complete_journal_before_end_rejected(self):
        self.f.complete();self.f.insert_at(self.oi(self.f.value['phases'][0]['end_boot']),'uitest\tuiInput click 10 10')
        with self.assertRaises(ValueError):self.f.verify()
    def test_failed_diagnostic_metadata_cannot_admit_indirect_operation(self):
        self.f.complete(waiting=True,diagnostic_prefix=1);poll=self.f.value['journals'][0]
        self.script(self.oi(poll['observation'])+1,'x=uitest; "$x" uiInput click 10 10')
        with self.assertRaises(ValueError):self.f.verify()


if __name__=='__main__':unittest.main()
