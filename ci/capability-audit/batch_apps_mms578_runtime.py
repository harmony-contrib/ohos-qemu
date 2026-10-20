"""Real MMS single-vCard draft/cancel slice on the original held suite guest.

No VM, signing, SDK or HDC launcher. Only the root's existing exact command
bridge dispatches. This slice does not certify legacy picker records, message
transport, deny/death on MMS, or native URI-grant release. They remain pending.
"""
import hashlib
import json
from pathlib import Path
import re
import shlex

import batch_apps_share578_project as project
import batch_apps_share578_project_verify as verify
from batch_apps_share578_collect import Collector, write_new
from guest_ui import NodeNotReady, select_node
from hap_identity_binding import bms_application_identity

BUNDLE = 'com.ohos.mms'
CACHE = '/data/app/el2/100/base/' + BUNDLE + '/cache'
LIST = 'if test -d ' + CACHE + '; then ls -1 ' + CACHE + '; else printf "%s\\n" __MMS578_NO_CACHE__; fi'

def require(ok, message):
    if not ok: raise ValueError(message)


def contents(req):
    return ('BEGIN:VCARD\r\nVERSION:3.0\r\nFN:MMS578/' + req['run_id'] + '/' + req['operation_id'] +
        '/mms-file-cancel/original\r\nEND:VCARD\r\n').encode()


def listing(raw):
    if raw == '__MMS578_NO_CACHE__\n': return []
    require(isinstance(raw, str) and raw.endswith('\n') and len(raw.encode()) <= 262144, 'complete cache enumeration required')
    values = raw.splitlines(); require(len(values) == len(set(values)), 'duplicate cache names')
    out = [x for x in values if x.startswith('senddata-import-')]
    require(all(re.fullmatch('senddata-import-[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', x) for x in out), 'unknown import directory preserved')
    return out


def provider(archive, callback):
    require(callable(callback), 'original root package/source/signer MMS verifier callback required; JSON pass flag refused')
    archive = project.regular(archive)
    value = callback(archive)  # Parent replays its ORIGINAL actual image guard.
    require(type(value) is dict and set(value) == {'archive_sha256','bundle','hap_sha256','permissions'} and
        value['archive_sha256'] == project.sha(archive) and value['bundle'] == BUNDLE and
        project.HEX.fullmatch(value['hap_sha256']) and type(value['permissions']) is list and
        all(type(x) is str for x in value['permissions']) and len(value['permissions']) == len(set(value['permissions'])),
        'exact actual same-archive MMS compiled HAP and unchanged permission surface required')
    return value


def mms_identity(raw, expected):
    identity = bms_application_identity(raw, BUNDLE)
    app = verify.decode(raw[raw.index('{'):])
    require(app['applicationInfo'].get('isSystemApp') is True and app['applicationInfo'].get('appPrivilegeLevel') == 'normal' and
        app.get('reqPermissions') == expected['permissions'], 'MMS original installed identity/permissions differ')
    paths = {x['hapPath'] for x in verify.walk_objects(app) if isinstance(x.get('hapPath'), str) and x['hapPath'].endswith('.hap')}
    require(len(paths) == 1, 'unique actual MMS installed HAP path required')
    path = paths.pop(); require(path.startswith(('/system/', '/data/app/')) and '//' not in path and
        all(x not in ('.','..','') for x in path.split('/')[1:]), 'canonical MMS installed path required')
    return dict(identity, hap_path=path)


def verify_runtime(spec, challenge, request, hdc, endpoint, archive, provider_verifier):
    require(set(spec) == {'schema_version','api','launch','actions','mms','cache'} and spec['schema_version'] == 1, 'complete MMS raw case envelope required')
    expected = provider(archive, provider_verifier)
    req,snaps,identities = verify.bind_runtime(spec['api'], challenge, request, hdc, endpoint, expected['archive_sha256'])
    require(req['case_id'] == 'mms-file-cancel' and set(spec['actions']) == {'caller','recipient','cancel','cleanup'} and
        len(spec['mms']) == 2 and set(spec['cache']) == {'before','during','bytes','absent'}, 'exact narrow MMS file/cancel case required')
    delta = verify.additions(req, snaps['before'], snaps['after'], identities); caller = delta['caller']
    require(not delta['target_a'] and not delta['target_b'] and [r['event'] for r in caller] ==
        ['begin','incoming','owned','owner_before','mms_call','mms_opened','cleanup_ready','cleanup_confirmed','owner_after','deleted','complete'], 'actual ordinary MMS caller trace incomplete or foreign receiver invoked')
    require(all(r['kind'] == 'caller' and r['phase'] == 'run' for r in caller) and
        verify.success(caller[0],'begin','request') == req and
        verify.decode(verify.success(caller[1],'incoming','UIAbility.Want').get('parameters',{}).get('request','')) == req, 'MMS request/ordinary caller differs')
    name = 'mms578-' + req['run_id'] + '-' + req['operation_id'] + '.vcf'
    uri = 'file://' + project.ROLES['caller']['bundle'] + '/data/storage/el2/base/files/' + name
    require(verify.success(caller[2],'owned','fileUri.getUriFromPath') == uri and
        verify.success(caller[3],'owner_before','fileIo.openSync/readSync').encode() == contents(req), 'actual sender vCard bytes/URI differ')
    want = {'action':'ohos.want.action.sendData','type':'text/vcard','flags':1,'uri':uri,'bundleName':BUNDLE,'moduleName':'entry',
        'abilityName':'com.ohos.mms.MainAbility','parameters':{'ability.params.stream':[uri]}}
    require(verify.success(caller[4],'mms_call','UIAbilityContext.startAbility') == want and
        verify.success(caller[5],'mms_opened','UIAbilityContext.startAbility') is None and
        verify.success(caller[6],'cleanup_ready','') is None, 'MMS must be started by ordinary public caller with real READ URI')
    launch = shlex.join(['aa','start','-b',project.ROLES['caller']['bundle'],'-a','EntryAbility','--ps','request',json.dumps(req,separators=(',',':'))])
    verify.command(spec['launch'],launch,req,hdc,endpoint)
    verify.verify_click(spec['actions']['caller'],req,hdc,endpoint,'caller')
    mms = None
    for row in spec['mms']:
        require(set(row) == {'bms','hash'}, 'exact actual MMS BMS/hash observation required')
        identity = mms_identity(verify.command(row['bms'],'bm dump -n '+BUNDLE,req,hdc,endpoint),expected)
        require(mms is None or mms == identity, 'MMS installed owner changed'); mms = identity
        require(verify.command(row['hash'],'sha256sum '+shlex.quote(identity['hap_path']),req,hdc,endpoint) == expected['hap_sha256']+'  '+identity['hap_path']+'\n', 'guest MMS bytes differ from original current-archive image guard')
    require(mms['uid'] not in {r['uid'] for r in identities.values()}, 'MMS cannot borrow an ordinary audit UID')
    cache = spec['cache']
    require(not listing(verify.command(cache['before'],LIST,req,hdc,endpoint)), 'fresh guest already has an attachment staging owner')
    names = listing(verify.command(cache['during'],LIST,req,hdc,endpoint));require(len(names) == 1, 'exactly one real imported file required')
    path = CACHE + '/' + names[0] + '/source.vcf'
    raw = verify.command(cache['bytes'],'od -An -v -tx1 '+path,req,hdc,endpoint)
    require(re.fullmatch('[0-9a-fA-F \n]+',raw) and len(raw) <= 1048576 and bytes.fromhex(raw) == contents(req), 'MMS must really read/copy full original nonce bytes, not return empty draft/success')
    recipient = verify.ui_tree(spec['actions']['recipient'],hdc,endpoint,BUNDLE)
    node = select_node(recipient,BUNDLE,identifier='mms-senddata-attachment')
    require(node['attributes'].get('text') == name+'\n'+str(len(contents(req)))+' B', 'actual recipient UI attachment name/size differs')
    cancel = spec['actions']['cancel'];require(set(cancel) == {'hierarchy','click'}, 'real user cancel proof required')
    layout = verify.ui_tree(cancel['hierarchy'],hdc,endpoint,BUNDLE)
    button = select_node(layout,BUNDLE,identifier='mms-senddata-cancel',clickable=True)
    left,top,width,height = button['rect'];script,_ = verify.ui_command(cancel['click'],hdc,endpoint)
    require(script == 'uitest uiInput click '+str(left+width//2)+' '+str(top+height//2), 'cancel must use actual current recipient UI node')
    require(len(cache['absent']) == 2, 'two actual post-cancel staged-file absence observations required')
    last = cancel['click']['finished_ns']
    for row in cache['absent']:
        require(last <= row['started_ns'] and not listing(verify.command(row,LIST,req,hdc,endpoint)), 'attachment stage remains/reappears or cleanup observation reordered')
        last = row['finished_ns']
    verify.verify_click(spec['actions']['cleanup'],req,hdc,endpoint,'cleanup')
    require(last <= spec['actions']['cleanup']['hierarchy']['dump']['started_ns'] and
        verify.success(caller[7],'cleanup_confirmed','UI.onClick') is None and
        verify.success(caller[8],'owner_after','fileIo.openSync/readSync').encode() == contents(req) and
        verify.success(caller[9],'deleted','fileIo.unlinkSync/accessSync') == {'path':'/data/storage/el2/base/files/'+name,'exists_after':False} and
        verify.success(caller[10],'complete','') is None, 'caller cleanup preceded real receiver cancel or file changed')
    # Host monotonic ordering joins all independent raw guest commands.
    require(spec['api']['commands'][9]['finished_ns'] <= cache['before']['started_ns'] <= cache['before']['finished_ns'] <= spec['launch']['started_ns'] <= spec['launch']['finished_ns'] <=
        spec['actions']['caller']['hierarchy']['dump']['started_ns'] <= spec['actions']['caller']['click']['finished_ns'] <=
        cache['during']['started_ns'] <= cache['bytes']['finished_ns'] <= spec['actions']['recipient']['dump']['started_ns'] <=
        cancel['hierarchy']['dump']['started_ns'] <= cancel['click']['finished_ns'] <= last <=
        spec['actions']['cleanup']['click']['finished_ns'] <= spec['api']['commands'][10]['started_ns'], 'MMS raw/UI/cancel/cleanup window differs')
    return {'scope':'actual_single_vCard_MMS_URI_import_recipient_UI_cancel_cleanup_ONLY', 'case_id':req['case_id'],
        'source_commit':project.load_challenge(challenge)['source_commit'],'boot_id':req['boot_id'],'archive_sha256':expected['archive_sha256'],
        'native_message_send_or_absence_verified':False,'MMS_deny_death_verified':False,'native_URI_grant_release_verified':False,
        'ledger_closed':False,'first_artifact_behavior_gate_passed':False}


class MmsCollector(Collector):
    def caller_nodes(self, layout, req):
        ready = select_node(layout,project.ROLES['caller']['bundle'],identifier='share578-ready')
        actual = ready['attributes'].get('text')
        if actual in self.known_prior_readies: raise NodeNotReady('previous independently verified modal request still visible')
        return super().caller_nodes(layout,req)

    def run_mms(self, archive, provider_verifier):
        expected = provider(archive, provider_verifier); require(expected['archive_sha256'] == self.archive,'MMS package differs from original owned guest')
        self.preflight_inputs()
        req = project.request(self.challenge_path,self.boot,self.archive,'mms-file-cancel')
        path = self.output/'request-mms-file-cancel.json';request = write_new(path,req)
        before,old = self.snapshot(req,'mms-before');require(not any(old.values()),'fresh independent MMS journals required')
        _,cache_before = self.shell(LIST,req,'mms-cache-before');require(not listing(verify.command(cache_before,LIST,req,self.hdc,self.endpoint)),'preserve pre-existing import')
        def installed(label):
            body,bms = self.shell('bm dump -n '+BUNDLE,req,label+'-bms');identity = mms_identity(body,expected)
            body,sha = self.shell('sha256sum '+shlex.quote(identity['hap_path']),req,label+'-hash')
            require(body == expected['hap_sha256']+'  '+identity['hap_path']+'\n','current-archive MMS HAP mismatch')
            return {'bms':bms,'hash':sha}
        installed_before = installed('mms-before')
        launch = shlex.join(['aa','start','-b',project.ROLES['caller']['bundle'],'-a','EntryAbility','--ps','request',json.dumps(req,separators=(',',':'))])
        _,launched = self.shell(launch,req,'mms-publish-caller')
        actions = {'caller':self.click(req,project.ROLES['caller']['bundle'],'mms-caller',lambda tree:self.caller_nodes(tree,req))}
        self.wait_cleanup_ready(req)
        def received():
            layout,proof = self.hierarchy(req,BUNDLE,'mms-recipient')
            select_node(layout,BUNDLE,identifier='mms-senddata-attachment')
            return proof
        def imported():
            _,row = self.shell(LIST,req,'mms-cache-during');found = listing(verify.command(row,LIST,req,self.hdc,self.endpoint))
            if not found: raise NodeNotReady('real MMS import not yet staged')
            require(len(found) == 1,'one actual MMS import required');return row,found
        during,names = self.bounded(imported)
        _,copied = self.shell('od -An -v -tx1 '+CACHE+'/'+names[0]+'/source.vcf',req,'mms-real-copied-bytes')
        actions['recipient'] = self.bounded(received)
        def cancel(tree): return {'button':select_node(tree,BUNDLE,identifier='mms-senddata-cancel',clickable=True)}
        actions['cancel'] = self.click(req,BUNDLE,'mms-cancel',cancel)
        absent = []
        for i in range(2):
            def gone():
                _,row = self.shell(LIST,req,'mms-cache-absent-'+str(i))
                if listing(verify.command(row,LIST,req,self.hdc,self.endpoint)): raise NodeNotReady('MMS staging cache not removed')
                return row
            absent.append(self.bounded(gone))
        self.shell(launch,req,'mms-reveal-same-caller-cleanup')
        def cleanup(tree):
            nodes = self.caller_nodes(tree,req);nodes['button'] = select_node(tree,project.ROLES['caller']['bundle'],identifier='share578-cleanup',clickable=True);return nodes
        actions['cleanup'] = self.click(req,project.ROLES['caller']['bundle'],'mms-caller-cleanup',cleanup)
        self.wait_complete(req);after,new = self.snapshot(req,'mms-after')
        spec = {'schema_version':1,'api':{'schema_version':1,'request':request,'applications':self.apps,'commands':before+after},'launch':launched,
            'actions':actions,'mms':[installed_before,installed('mms-after')],'cache':{'before':cache_before,'during':during,'bytes':copied,'absent':absent}}
        evidence = write_new(self.output/'evidence-mms-file-cancel.json',spec)
        result = verify_runtime(spec,self.challenge_path,path,self.hdc,self.endpoint,archive,provider_verifier)
        write_new(self.output/'verification-mms-file-cancel.json',result)
        self.report['cases'] = [{'case_id':req['case_id'],'request':request,'evidence':evidence,'status':'pass_narrow_MMS_draft_cancel_ONLY'}]
        self.report['status'] = 'pass_narrow_MMS_draft_cancel_ONLY';self.save();return self.report


def collect(*, archive, provider_verifier, previous_share_report, **kwargs):
    # Fail before constructing a collector/output or dispatching any command if
    # the existing parent package verifier seam has not actually been supplied.
    provider(archive,provider_verifier)
    prior = verify.decode(project.checked(previous_share_report).read_text())
    require(prior.get('applications') == kwargs['applications'] and prior.get('boot_id') == kwargs['boot_id'] and
        prior.get('archive_sha256') == kwargs['archive_sha256'] and len(prior.get('cases',[])) == len(project.CONTRACT['cases']), 'exact preceding same-guest modal report required')
    readies = set()
    for item,case in zip(prior['cases'],project.CONTRACT['cases']):
        require(item['case_id'] == case,'preceding modal order differs')
        request = project.checked(item['request']);spec = verify.decode(project.checked(item['evidence']).read_text())
        verify.verify_case(spec,kwargs['challenge'],request,kwargs['hdc'],kwargs['endpoint'],kwargs['archive_sha256'])
        req = verify.decode(request.read_text());readies.add('/'.join([req['run_id'],req['operation_id'],req['case_id'],'run']))
    collector = MmsCollector(**kwargs);collector.known_prior_readies = readies
    collector.report['previous_modal_report'] = previous_share_report;collector.save()
    try:
        return collector.run_mms(archive,provider_verifier)
    except Exception as error:
        collector.report['status'] = 'fail'
        collector.report['failures'].append(type(error).__name__ + ': ' + str(error))
        collector.save()
        raise
    finally:
        collector.save()
