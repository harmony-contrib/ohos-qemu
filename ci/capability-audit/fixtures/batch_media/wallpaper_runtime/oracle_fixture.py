"""Synthetic host oracle input ONLY. Never guest, package or SDK evidence."""
import copy
import json
import shlex
from pathlib import Path
import zipfile

from PIL import Image
import batch_media_wallpaper_runtime as runtime
import batch_media_verify_wallpaper_runtime as verify


def node(bundle, identifier='', *, kind='Button', rect=(0, 0, 360, 640), children=None):
    x, y, w, h = rect
    return {'attributes': {'bundleName': bundle, 'id': identifier, 'type': kind, 'visible': 'true',
                          'enabled': 'true', 'clickable': 'true', 'bounds': f'[{x},{y}][{x+w},{y+h}]'},
            'children': children or []}

def system_tree(bundle, identifier, width=360, height=640, top=0):
    full=f'[0,0][{width},{height}]'
    selected=node(bundle,identifier,kind='Flex',rect=(0,top,width,height-top))
    selected['attributes'].update(origBounds=full,displayId='0',hostWindowId='11')
    window=node(bundle,'session11',kind='WindowScene',rect=(0,top,width,height-top),children=[selected])
    window['attributes'].update(origBounds=full,displayId='0',hostWindowId='11')
    root=node('',rect=(0,0,width,height),children=[window])
    if top:
        bar=node('com.ohos.sceneboard','StatusBarBackground_Row_0',kind='Row',rect=(0,0,width,top))
        bar['attributes'].update(origBounds=f'[0,0][{width},{top}]',displayId='0',hostWindowId='20')
        owner=node('com.ohos.sceneboard','session20',kind='WindowScene',rect=(0,0,width,top),children=[bar])
        owner['attributes'].update(origBounds=f'[0,0][{width},{top}]',displayId='0',hostWindowId='20')
        root['children'].append(owner)
    return root


def ams(bundle):
    return '    AppRunningRecord ID #1\n      process name ['+bundle+']\n      pid #123  uid #20010001\n      state #FOREGROUND\n'


def provider(host):
    return ('    uri [/com.ohos.photos/entry/Picker10]\n      AbilityRecord ID #1\n      state #ACTIVE\n'
            'bundle name [com.ohos.photos]\nability type [UIEXTENSION]\nroot host bundle name ['+host+']\n')


class Fixture:
    def __init__(self, root):
        self.root = Path(root); self.index = 0
        self.challenge_path = runtime.prepare(self.root/'challenge', 360, 640)
        self.challenge = json.loads(self.challenge_path.read_text()); self.run = self.challenge['run_id']
        self.boot = '11111111-1111-1111-1111-111111111111'
        self.seed_uid = 20012345; self.settings_uid = 20010001
        archive = self.put(b'host fixture, not an actual image')
        env = {'external_keepalive': False, 'guest_arch': 'arm64', 'device_type': '2in1', 'qemu_pid': 123,
               'qemu_command': 'qemu -qmp /tmp/host-fixture.sock', 'qmp_socket': '/tmp/host-fixture.sock',
               'target': '127.0.0.1:1234', 'boot_id': self.boot, 'udid': 'a'*64}
        boot = self.js({'status': 'pass', 'purpose': 'acceptance', 'scope': 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate',
                        'archive_sha256': archive['sha256'], 'test_environment': env})
        self.plan = {'settings_navigation': [], 'screens': {
            'desktop': {'bundle': 'com.ohos.sceneboard', 'identifier': 'SCBDesktop_Flex_Desktop'},
            'lock': {'bundle': 'com.ohos.sceneboard', 'identifier': 'ScreenLockRootComponent'}}}
        self.value = {'schema_version': 1, 'scope': runtime.SCOPE, 'status': 'collected', 'failures': [],
                      'first_artifact_behavior_gate_passed': False, 'run_id': self.run, 'boot_id': self.boot,
                      'archive': archive, 'boot': boot, 'challenge': runtime.record(self.challenge_path),
                      'plan': self.js(self.plan), 'runner': runtime.record(Path(runtime.__file__)),
                      'commands': [], 'ui_actions': [], 'actions': [], 'stages': []}
        self.bms_observations={}
        for key, bundle, ordinary, uid in [('seed_identity', runtime.SEED, True, self.seed_uid),
            ('settings_identity', runtime.SETTINGS, False, self.settings_uid),
            ('renderer_identity', 'com.ohos.wallpaper', False, 20010002), ('photos_identity', runtime.PHOTOS, False, 20010003)]:
            app={'applicationInfo':{'name':bundle,'uid':uid,'isSystemApp':not ordinary,
                'accessTokenId':10+len(self.bms_observations),'appPrivilegeLevel':'normal'if ordinary else'system_basic'}}
            label={'seed_identity':'seed','settings_identity':'settings','renderer_identity':'renderer',
                'photos_identity':'photos'}[key]+'-BMS'
            observed=self.observation('bm dump -n '+bundle,json.dumps(app),label)
            self.value[key]=observed['raw'];self.bms_observations[bundle]=observed
        self.default = {}
        for kind, case in [('desktop', 'cancel'), ('lock', 'desktop-1')]:
            image = Image.open(self.challenge['images'][case]['path'])
            path = self.root/('default-'+kind+'.jpeg'); image.save(path, quality=95)
            self.default[kind] = runtime.record(path)
        defaults = {kind: {'remote': '/system/etc/wallpaper'+('default' if kind == 'desktop' else 'lockdefault')+'.jpeg',
                           'manifest': None} for kind in ('desktop', 'lock')}
        self.value['defaults'] = {kind: self.transfer(defaults[kind]['remote'], Path(self.default[kind]['path']).read_bytes())
                                  for kind in defaults}
        elf = bytearray(64); elf[:4] = b'\x7fELF'; elf[18:20] = (183).to_bytes(2, 'little')
        binary = self.put(bytes(elf)); source = runtime.record(runtime.FIXTURE/'default_resolver.cpp')
        self.value['default_resolution'] = self.js({'run_id': self.run, 'boot_id': self.boot, **defaults,
            'query_binary': binary, 'query_source': source,
            'query_build_receipt': self.js({'status': 'pass', 'source_sha256': source['sha256'], 'binary_sha256': binary['sha256'], 'arch': 'arm64'}),
            'actual_GetCfgFiles_query': self.js({'run_id': self.run, 'boot_id': self.boot,
                'resource_path': 'resource/themes/theme/', 'paths': [], 'resolved': {k: v['remote'] for k, v in defaults.items()},
                'descriptions': {k: {'manifest_remote': '', 'manifest_state': 'fallback'} for k in defaults}})})
        self.uris = ['file://media/Photo/'+str(i+1)+'/IMG_'+str(i)+'.png' for i in range(5)]
        self.rows = []
        for case, uri in zip(runtime.CASES, self.uris):
            size = Path(self.challenge['images'][case]['path']).stat().st_size
            self.row('import.request', {'case': case, 'sourceUri': 'file://'+runtime.SEED+'/'+case+'.png', 'bytes': size})
            self.row('import.complete', {'case': case, 'uri': uri, 'bytes': size})
        self.value['seed_log'] = self.transfer('/data/app/el2/100/base/'+runtime.SEED+'/files/wallpaper-'+self.run+'.jsonl',
                                              self.lines(), uid=self.seed_uid)
        for kind in (0, 1):
            for operation in ('setWallpaper', 'reset', 'setImage', 'restore'):
                self.row('denied.request', {'type': kind, 'operation': operation})
                self.row('denied.error', {'type': kind, 'operation': operation, 'code': 201, 'message': 'Permission denied'})
        self.value['denied_log'] = self.transfer(self.value['seed_log']['remote'], self.lines(), uid=self.seed_uid)
        self.value['private_PNGs'] = {name: self.transfer('/data/app/el2/100/base/'+runtime.SEED+'/files/'+name+'.png',
            Path(self.challenge['images'][name]['path']).read_bytes(), uid=self.seed_uid) for name in runtime.CASES}
        module = {'app': {'bundleName': runtime.SEED}, 'module': {'requestPermissions': []}}
        unsigned = self.root/'unsigned.hap'; signed = self.root/'signed.hap'
        with zipfile.ZipFile(unsigned, 'w') as hap:
            hap.writestr('module.json', json.dumps(module)); hap.writestr('ets/modules.abc', b'HOST oracle fixture ABC')
            hap.writestr('resources.index', b'HOST oracle fixture resources')
        signed.write_bytes(unsigned.read_bytes())
        with zipfile.ZipFile(signed, 'a') as hap:
            hap.writestr('.pages.info', b'HOSTONLY')
        consent = []
        for case in runtime.CASES:
            from photos_dialog_contract import select_dialog
            tree = self.dialog(runtime.SEED, 'save')
            selected,contract=select_dialog(tree,runtime.SEED,'save',label='Wallpaper challenge',count=1)
            consent.append({'case': case, 'layout': self.js(tree), 'node': selected, 'dialog':contract,
                'selector':{'text':contract['allow']}, 'ui_bundle': runtime.SEED,
                'screenshot': self.challenge['images']['cancel'], 'provider_dump': self.put(provider(runtime.SEED))})
        self.value['import_observation'] = self.js({'run_id': self.run, 'boot_id': self.boot, 'uris': self.uris,
            'seed_uid': self.seed_uid, 'app_label':'Wallpaper challenge', 'compiled_module': self.js(module), 'compiled_page': self.challenge['generated_page'],
            'unsigned_hap': runtime.record(unsigned), 'signed_hap': runtime.record(signed), 'consent_actions': consent,
            'build_receipt': self.js({'status': 'pass', 'generated_page_sha256': self.challenge['generated_page']['sha256'],
                                      'unsigned_sha256': runtime.sha(unsigned)}),
            'signing_receipt': self.js({'status': 'pass', 'signed_sha256': runtime.sha(signed), 'unsigned_sha256': runtime.sha(unsigned),
                'verified_profile': {'bundle-info': {'bundle-name': runtime.SEED, 'apl': 'normal', 'app-feature': 'hos_normal_app'}}})})
        close = node(runtime.SETTINGS, 'close-button', children=[node(runtime.SETTINGS, 'Third_Select_PickerClose', kind='Image')])
        from photos_asset_ui import button_ancestor
        self.value['picker_cancel_observation'] = self.js({'run_id': self.run, 'boot_id': self.boot,
            'ui_bundle': runtime.SETTINGS, 'layout': self.js(close), 'node': button_ancestor(close, runtime.SETTINGS, 'Third_Select_PickerClose'),
            'provider_dump': self.put(provider(runtime.SETTINGS)), 'screenshot': self.challenge['images']['cancel']})
        self.value['denied_observation'] = self.js({'run_id': self.run, 'boot_id': self.boot,
            'token_query': self.token_observation(runtime.SEED,-1),
            'settings_token_query': self.token_observation(runtime.SETTINGS,0),
            'before_normal_token':self.token_observation(runtime.SEED,-1)})
        deletion=[]
        for _ in runtime.CASES:
            toolbar=node(runtime.PHOTOS,'ToolBarButtonDelete')
            deletion.append({'layout':self.js(toolbar),'selector':{'identifier':'ToolBarButtonDelete'},
                'node':verify.select_node(toolbar,runtime.PHOTOS,identifier='ToolBarButtonDelete',clickable=True),
                'screenshot':self.challenge['images']['cancel']})
            tree=self.dialog(runtime.PHOTOS,'delete');selected,contract=select_dialog(tree,runtime.PHOTOS,'delete')
            deletion.append({'layout':self.js(tree),'selector':{'text':contract['allow']},'dialog':contract,
                'node':selected,'screenshot':self.challenge['images']['cancel']})
        self.value['cleanup_observation'] = self.js({'run_id': self.run, 'boot_id': self.boot,
            'deleted_uris': self.uris, 'actual_asset_query': self.js({'queried_uris': self.uris, 'active_uris': []}),
            'ui_actions': deletion})
        self.value['private_cleanup'] = self.put('')
        self.value['back_return_layout'] = self.js(node(runtime.SETTINGS, 'settings_wallpaper_entry'))
        actions = ['verify-package-identities-and-permissions', 'resolve-service-default-resources',
                   'import-five-PNGs-via-real-Photos-consent']
        for case in runtime.CASES[:4]: actions += ['show-settings-main', 'show-real-'+case.split('-')[0]]
        actions += ['show-settings-main', 'cancel-real-Photos-picker', 'show-settings-main',
                    'ordinary-denied-set-and-restore', 'show-settings-main', 'show-real-desktop',
                    'show-settings-main', 'show-real-lock', 'delete-only-created-Photos-assets-via-real-UI', 'remove-owned-seed-private-inputs']
        for index, action in enumerate(actions):
            item = {'schema_version': 1, 'run_id': self.run, 'boot_id': self.boot, 'sequence': index+1,
                    'nonce': format(index+1, '032x'), 'action': action}
            self.value['actions'].append({'action': action, 'started_ns': 1000+index*10,
                'finished_ns': 1001+index*10, 'request': self.js({**item, 'details': {}}), 'ack': self.js(item)})
        files = {}
        self.stage('baseline', files)
        for case in runtime.CASES[:4]:
            kind = case.split('-')[0]
            files[verify.PATHS[kind]] = Path(self.challenge['images'][case]['path']).read_bytes()
            config = {'SystemResType': int('desktop' in case or verify.PATHS['desktop'] in files),
                      'LockScreenResType': int('lock' in case or verify.PATHS['lock'] in files)}
            files[verify.CFG] = json.dumps(config).encode()
            self.stage(case, files, screen=kind, picture=self.challenge['images'][case])
        for name in ('picker-cancel', 'preview-cancel', 'preview-back', 'permission-denied'): self.stage(name, files)
        for kind in ('desktop', 'lock'):
            files.pop(verify.PATHS[kind]); config = json.loads(files[verify.CFG])
            config['SystemResType' if kind == 'desktop' else 'LockScreenResType'] = 0
            files[verify.CFG] = json.dumps(config).encode()
            self.stage(kind+'-restore', files, screen=kind, picture=self.default[kind])
        for name in runtime.CASES[:4]:
            self.click('settings_wallpaper_entry'); self.picker(name)
            self.click('wallpaper_apply_home' if name.startswith('desktop') else 'wallpaper_apply_lock')
        self.click('settings_wallpaper_entry'); self.picker('cancel'); self.click('wallpaper_cancel')
        self.click('settings_wallpaper_entry'); self.picker('cancel')
        for kind in ('home', 'lock'): self.click('settings_wallpaper_entry'); self.click('wallpaper_restore_'+kind)
        self.path = self.root/'runtime.json'; self.save()
        marker = '__UITEST_EXIT_'+'a'*32+'__='
        self.value['commands'].append({'argv': ['hdc', '-t', '127.0.0.1:1234', 'shell',
            'for wallpaper_name in desktop-1 desktop-2 lock-1 lock-2 cancel; do test ! -e fixture; done; printf '+marker],
            'exit_code': 0, 'label': 'owned-private-inputs-absent', **self.put(marker+'0\n')})
        self.save()

    def dialog(self,owner,kind):
        from photos_dialog_contract import ZH
        spec=ZH[kind];title=spec['title']%('Wallpaper challenge',1) if kind=='save' else spec['title']
        children=[]
        for text,identifier in ((title,'title'),(spec['allow'],'advanced_dialog_button_0'),(spec['deny'],'advanced_dialog_button_7')):
            child=node(owner,identifier,kind='Text' if identifier=='title' else 'Button')
            child['attributes']['text']=text;children.append(child)
        return node(owner,'dialog',kind='Column',children=children)

    def put(self, content):
        self.index += 1; path = self.root/(str(self.index)+'.raw')
        path.write_bytes(content.encode() if isinstance(content, str) else content)
        return runtime.record(path)

    def js(self, value): return self.put(json.dumps(value))

    def observation(self,script,raw,label):
        index=len(self.value['commands']);marker='__UITEST_EXIT_'+format(index+1,'032x')+'__='
        log=self.put(raw+'\n\n'+marker+'0\n')
        command={'argv':['hdc','-t','127.0.0.1:1234','shell',
            script+'; task_ui_rc=$?; printf "\\n'+marker+'%s\\n" "$task_ui_rc"'],
            'label':label,'exit_code':0,**log}
        self.value['commands'].append(command)
        return {'raw':self.put(raw),'command_index':index,'command':command}

    def token_observation(self,bundle,grant):
        baseline=self.bms_observations[bundle];bms=json.loads(verify.checked(baseline['raw']).read_text())
        app=bms['applicationInfo'];uid,token=app['uid'],app['accessTokenId']
        before=self.observation('bm dump -n '+bundle,json.dumps(bms),'before-token-BMS')
        value={'run_id':self.run,'boot_id':self.boot,'bundle':bundle,'token_id':token,'user_id':100,
            'permission':'ohos.permission.SET_WALLPAPER','grant':grant,'before_ns':1000,'after_ns':1001,
            'identity_schema':'hap-bms-access-token/v1','expected_uid':uid,'at_reported_uid':0,
            'at_query_rc':0,'at_token_id':token,'at_user_id':100,'at_inst_index':0,'at_bundle':bundle}
        script='unset LD_LIBRARY_PATH LD_PRELOAD; '+shlex.join([
            '/data/local/tmp/wallpaper-coordinator-'+self.run+'/token',self.run,str(uid),bundle,value['permission']])
        observed=self.observation(script,json.dumps(value),'actual-token-query')
        after=self.observation('bm dump -n '+bundle,json.dumps(bms),'after-token-BMS')
        observed.update(schema_version=1,run_id=self.run,boot_id=self.boot,
            role='seed'if bundle==runtime.SEED else'settings',baseline=baseline,before=before,after=after,
            helper={'binary':self.put(b'HOST ORACLE ONLY NOT NATIVE BINARY'),
                'source':runtime.record(verify.HERE/'fixtures/batch_media/wallpaper_receipts/token_query.cpp'),
                'build_receipt':self.js({'scope':'HOST ORACLE ONLY NOT COMPILE EVIDENCE'})})
        return self.js(observed)
    def row(self, name, detail): self.rows.append({'runId': self.run, 'sequence': len(self.rows)+1,
        'name': name, 'detail': json.dumps(detail), 'timestampMs': 1000000+len(self.rows)})
    def lines(self): return '\n'.join(json.dumps(row) for row in self.rows)+'\n'

    def transfer(self, remote, content, uid=1000):
        file = self.put(content); stat = f'{uid} 1000 600 {Path(file["path"]).stat().st_size} 1000 1\n{file["sha256"]}  {remote}\n'
        return {'remote': remote, 'file': file, 'before': self.put(stat), 'after': self.put(stat)}

    def stage(self, name, files, screen=None, picture=None):
        i = len(self.value['stages']); stage = {'name': name, 'started_ns': i*100+1, 'finished_ns': i*100+2,
            'account': self.put('bootevent.account.ready=true\nID: 100\nisForeground: true\n'),
            'cfg_presence': self.put('present\n' if verify.CFG in files else 'absent\n'),
            'files': {p: self.transfer(p, b) for p, b in files.items()}, 'renderer_pids': self.put('444\n'),
            'ams': self.put(ams('com.ohos.sceneboard'))}
        for kind, directory in [('desktop', 'system'), ('lock', 'lockscreen')]:
            stage[kind+'_inventory'] = self.put(''.join(p+'\n' for p in files if p.startswith(verify.BASE+'/'+directory+'/')))
        if screen:
            chosen = self.plan['screens'][screen]
            image = Image.open(picture['path']); capture = self.root/(name+'-capture.png'); image.save(capture, format='PNG')
            stage.update(screen_kind=screen, screenshot=runtime.record(capture),
                layout=self.js(system_tree(chosen['bundle'],chosen['identifier'],image.width,image.height)))
        self.value['stages'].append(stage)
        marker = '__UITEST_EXIT_'+'a'*32+'__='
        log = self.put(marker+'0\n')
        self.value['commands'].append({'argv': ['hdc', '-t', '127.0.0.1:1234', 'shell', 'fixture; printf '+marker],
                                       'exit_code': 0, 'label': 'HOST oracle fixture only', **log})

    def click(self, identifier):
        tree = node(runtime.SETTINGS, identifier); record = self.js(tree)
        self.value['ui_actions'].append({'kind': 'click', 'bundle': runtime.SETTINGS, 'selector': {'identifier': identifier},
            'layout': record['path'], 'layout_sha256': record['sha256'], 'selected_node': verify.select_node(tree, runtime.SETTINGS,
                identifier=identifier, clickable=True), 'monotonic_ns': 1000})

    def picker(self, case):
        tree = node(runtime.SETTINGS, kind='Image'); layout = self.js(tree)
        selected, metrics = verify.thumbnail(tree, self.challenge['images'][case]['path'], self.challenge['images'][case]['path'])
        self.value['ui_actions'].append({'kind': 'challenge-thumbnail', 'case': case, 'layout': layout['path'],
            'layout_sha256': layout['sha256'], 'screenshot': self.challenge['images'][case], 'node': selected, 'metrics': metrics,
            'ui_bundle': runtime.SETTINGS, 'provider_dump': self.put(provider(runtime.SETTINGS)), 'monotonic_ns': 1000})

    def save(self): self.path.write_text(json.dumps(self.value))

    def clone(self): return copy.deepcopy(self.value)
