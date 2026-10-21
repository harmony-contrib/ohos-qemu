"""Actual Photos provider stop/rebuild on the same original held2in1 IO."""
import json
import secrets
import time
from photos579_bindings import bind
from photos579_project import ROLES, bundle
from photos579_raw import need, checked, ref, processes, extensions, title_hash


def run_on_held_io(io):
    env=io.guest.report['test_environment']
    need(env['device_type']=='2in1' and env['external_keepalive'] is False and io.owner.vm is io.guest,
        'one original actual2in1 acceptance guest')
    cb,cuts=bind(io)
    report=dict(schema='actual-photos579-provider-restart/v1',run=io.run_id,
        archive_sha256=io.archive_sha256,boot_id=io.boot_id,udid=io.udid,target=io.target,
        prepared=None,installs={},operations=[],snapshots={},nonces={},assets={},failures=[],cleanup=None,
        runtime_pass=False,first_artifact_behavior_gate_passed=False)
    serial=0
    def keep(kind,value):
        report['operations'].append(dict(kind=kind,value=value)); return value
    def start(role,action,payload=None):
        nonlocal serial
        serial+=1
        request=dict(run_id=io.run_id,request_id='restart_%04d_%s'%(serial,action),action=action,payload=payload or {})
        keep('request',dict(role=role,request=request)); keep('start',cb['start'](role,action,request))
        return request['request_id']
    def collect(role,request_id, *, errors=False):
        value=keep('collect',cb['collect'](role,request_id))
        all_rows=[json.loads(line) for line in checked(value['journal']).read_text().splitlines() if line]
        rows=[row for row in all_rows if row['request_id']==request_id]
        need(rows and any(row['event']=='request' for row in rows),'actual caller request journal absent')
        if not errors:
            need(any(row['event']=='done' for row in rows) and not any(row['event'] in
                ('error','request-error','page-error') for row in rows),'actual public caller request failed')
        return rows,value
    def call(role,action,payload=None,**options):
        return collect(role,start(role,action,payload),**options)
    def one(rows,event):
        selected=[row for row in rows if row['event']==event]
        need(len(selected)==1,'one actual public event: '+event)
        return json.loads(selected[0]['value'])
    def touch(action,payload=None):
        return keep('input',dict(action=action,result=cb['input'](action,payload or {})))
    def snapshot(name):
        value=keep('network',dict(action='provider-snapshot',result=cb['network']('provider-snapshot',{})))['result']
        report['snapshots'][name]=value
        return value,processes(checked(value['processes']).read_text(),io.boot_id)
    def create(name):
        nonce=secrets.token_hex(16)
        while any(title_hash('photos579-'+io.run_id+'-'+nonce)==title_hash('photos579-'+io.run_id+'-'+n) for n in report['nonces'].values()):
            nonce=secrets.token_hex(16)
        report['nonces'][name]=nonce
        request_id=start('normal','create',{'nonce':nonce})
        touch('photos-consent',{'kind':'save'})
        rows,collected=collect('normal',request_id)
        asset=one(rows,'asset-created')
        need(asset['nonce']==nonce and asset['title']=='photos579-'+io.run_id+'-'+nonce and asset['uri'].startswith('file://media/Photo/') and
            len(collected['binaries'])==1,'actual freshly consented nonce JPEG required')
        report['assets'][name]=dict(request_id=request_id,asset=asset,binary=collected['binaries'][0]['raw'])
        rows,_=call('normal','recent-info')
        info=one(rows,'recent-info')
        need(info['defaults']==info['explicit'] and info['defaults']['identifier']==title_hash(asset['title']) and
            info['defaults']['dateTaken']>0,'actual Photos info does not identify fresh public nonce asset')
        rows,_=call('normal','default-album'); need(one(rows,'default-album'),'actual localized album absent')
        request_id=start('normal','recent-component')
        deadline=time.monotonic()+30
        while True:
            rows,_=collect('normal',request_id)
            exists=[json.loads(row['value']) for row in rows if row['event']=='recent-component-exists']
            if True in exists: break
            need(time.monotonic()<deadline,'real recent component did not recover its public positive callback')
            time.sleep(.25)
        touch('snapshot',{'label':'restart_'+name})
        touch('recent-nonce-pixels',{'binary':collected['binaries'][0]['raw'],'nonce':nonce})
        observed,native=snapshot(name)
        need(native,'actual Photos provider process missing')
        report['assets'][name]['info']=info
        report['assets'][name]['extension_record']=extensions(checked(observed['ams']).read_text(),bundle('photos','normal'))
        return asset
    try:
        report['prepared']=keep('prepared',cb['prepare_callers']('photos',io.run_id,ROLES['photos']))
        need(report['prepared']['profile']=='2in1','actual compiled2in1 roles only')
        for role in ROLES['photos']:
            report['installs'][role]=keep('install',dict(role=role,result=cb['install'](role)))['result']
        request_id=start('janitor','permissions'); touch('media-permission'); permissions,_=collect('janitor',request_id)
        need(one(permissions,'permission-result')['authResults']==[0,0],'actual READ/WRITE grant required for cleanup')
        before=create('before')
        # The source-defined native identity is recorded while the UIExtension
        # is actually connected; caller death is not substituted for this stop.
        call('normal','hide-recent')
        keep('network',dict(action='provider-stop',result=cb['network']('provider-stop',{})))
        old={(row['pid'],row['starttime']) for row in processes(
            checked(report['snapshots']['before']['processes']).read_text(),io.boot_id)}
        deadline=time.monotonic()+30
        while True:
            observed,native=snapshot('stopped')
            if not old & {(row['pid'],row['starttime']) for row in native}: break
            need(time.monotonic()<deadline,'actual original Photos PID births survived provider stop')
            time.sleep(.25)
        after=create('after')
        need(before['uri']!=after['uri'] and report['assets']['before']['binary']['sha256']!=report['assets']['after']['binary']['sha256'] and
            report['assets']['before']['extension_record']!=report['assets']['after']['extension_record'],
            'new process/extension/nonce content must be independently observed')
        current=processes(checked(report['snapshots']['after']['processes']).read_text(),io.boot_id)
        need(not old & {(row['pid'],row['starttime']) for row in current},'new actual provider instance was not established')
        denied,_=call('foreign','read-denied',{'uri':after['uri']},errors=True)
        need(len([row for row in denied if row['event']=='error' and row['code'] in (201,202,13900001,13900012)])==1 and
            not any(row['event'] in ('done','media-bytes','ungranted-uri-read-returned') for row in denied),
            'foreign UID gained fresh restart asset access')
        call('normal','hide-recent')
        cancel=start('normal','cancel-select'); touch('snapshot',{'label':'restart_cancel'}); touch('back')
        cancelled,_=collect('normal',cancel)
        need(one(cancelled,'select-result')['photoUris']==[],'actual cancel returned a grant')
        exited,_=call('normal','exit',errors=True)
        need(len([row for row in exited if row['event']=='exit-request'])==1 and
            not any(row['event'] in ('error','request-error','page-error') for row in exited), 'actual caller exit request failed')
        call('normal','identity')
        # terminateSelf ends the UIAbility; AMS may retain its cached process.
        # Original Knowledge's real force-stop/reentry is the PID-death case.
        call('normal','recent-info')
    except Exception as error:
        report['failures'].append(dict(type=type(error).__name__,message=str(error)))
    finally:
        try:
            report['cleanup']=keep('cleanup',cb['cleanup']())
            need(report['cleanup']['restored'] is True and report['cleanup']['failures']==[], 'actual owned caller/media cleanup failed')
        except Exception as error:
            report['failures'].append(dict(stage='cleanup',type=type(error).__name__,message=str(error)))
        report['callback_cuts']=list(cuts)
        path=io.output/'restart-business.json'
        with path.open('x') as stream:
            json.dump(report,stream,indent=2);stream.write('\n')
    return ref(path)
