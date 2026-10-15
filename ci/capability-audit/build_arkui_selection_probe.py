#!/usr/bin/env python3
"""Compile the real API26 SelectionContainer factory with the official UI transform."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
from build_always_on_vpn_probe import prepare_application, module as base_module
from run_root_probe import digest

TEMPLATE = Path(__file__).with_name('arkui_selection_probe.ets')
BUNDLE = 'org.harmonycontrib.capabilityaudit'
SCOPE = 'ordinary_API26_SelectionContainer_typed_modifier_native_menu_copy_veto_join_controller_clear'
DECLARATION = '@ohos.arkui.components.SelectionContainer.d.ts'
ROLES = ('normal', 'reader-denied', 'reader')
PERMISSION = 'ohos.permission.READ_PASTEBOARD'
CONTRACTS = ['arkts_export:@ohos.arkui.components.SelectionContainer:' + name
             for name in ('SelectionContainerAttribute','SelectionContainerInstance')]


def source(run_id, role='normal'):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None or role not in ROLES:
        raise ValueError('fresh real SelectionContainer caller nonce required')
    return TEMPLATE.read_text().replace('__RUN__', run_id).replace('__ROLE__', role)


def module(role):
    if role not in ROLES: raise ValueError('exact selection caller role required')
    value=base_module('normal')
    value['module']['requestPermissions']=[{'name':PERMISSION,'reason':'$string:selection_read_reason',
        'usedScene':{'abilities':['EntryAbility'],'when':'inuse'}}] if role=='reader' else []
    return value


def inputs(project, sdk, arch, run_id, hvigor_home, node_home, role='normal'):
    project, sdk = Path(project).resolve(), Path(sdk).resolve()
    hvigor, node = Path(hvigor_home).resolve(), Path(node_home).resolve()
    if arch not in ('arm64', 'armv7a', 'x86_64'): raise ValueError('actual caller ABI required')
    paths = ['AppScope/app.json5', 'build-profile.json5', 'entry/build-profile.json5',
        'entry/src/main/module.json5', 'entry/src/main/ets/pages/Index.ets',
        'entry/src/main/ets/entryability/EntryAbility.ets', 'entry/src/main/resources/base/profile/main_pages.json',
        'hvigorfile.ts', 'entry/hvigorfile.ts', 'hvigor/hvigor-config.json5', 'local.properties',
        'entry/src/main/resources/base/element/string.json', 'AppScope/resources/base/element/string.json']
    if any((project / name).is_symlink() for name in paths): raise ValueError('regular typed caller inputs required')
    if (project / paths[4]).read_text() != source(run_id,role): raise ValueError('real SelectionContainer typed caller changed')
    app = json.loads((project / paths[0]).read_text())['app']
    profile = json.loads((project / paths[1]).read_text())
    entry = json.loads((project / paths[2]).read_text())
    actual_module = json.loads((project / paths[3]).read_text())['module']
    if (json.loads((project/paths[-2]).read_text()) != reason_resource() or
            json.loads((project/paths[-1]).read_text()) != app_name_resource()):
        raise ValueError('exact selection label and user-grant reason resource required')
    if (app['bundleName'] != BUNDLE or actual_module.get('requestPermissions') != module(role)['module']['requestPermissions'] or
        actual_module.get('deviceTypes') != ['default'] or
        profile['app']['products'] != [dict(name='default', compileSdkVersion='26.0.0',
            targetSdkVersion='26.0.0', compatibleSdkVersion='26.0.0', runtimeOS='OpenHarmony')] or
        entry != dict(apiType='stageMode', buildOption=dict(externalNativeOptions=dict(
            abiFilters=[{'arm64':'arm64-v8a','armv7a':'armeabi-v7a','x86_64':'x86_64'}[arch]])),
            targets=[dict(name='default')])):
        raise ValueError('exact ordinary API26 OpenHarmony caller profile required')
    for path, task in (('hvigorfile.ts', 'appTasks'), ('entry/hvigorfile.ts', 'hapTasks')):
        if (project / path).read_text() != "import { " + task + " } from '" + str(hvigor / 'hvigor-ohos-plugin') + "';\nexport default { system: " + task + ", plugins: [] };\n":
            raise ValueError('official UI transform without compiler override required')
    config = dict(modelVersion='6.0.0', dependencies={}, execution=dict(daemon=False, parallel=False), logging=dict(level='info'))
    if (json.loads((project / 'hvigor/hvigor-config.json5').read_text()) != config or
        (project / 'local.properties').read_text() != 'sdk.dir=' + str(sdk.parent) + '\n'):
        raise ValueError('official SDK path and checking cannot be overridden')
    declarations=['ets/api/'+DECLARATION,'ets/api/@ohos.pasteboard.d.ts',
        'ets/component/common.d.ts','ets/component/enums.d.ts','ets/kits/@kit.ArkUI.d.ts',
        'ets/api/@ohos.abilityAccessCtrl.d.ts','ets/api/@ohos.app.ability.common.d.ts']
    text=(sdk/declarations[0]).read_text()
    if any(value not in text for value in ('export declare class SelectionContainerAttribute extends CommonMethod<SelectionContainerAttribute>',
        'export declare const SelectionContainerInstance: SelectionContainerAttribute;',
        'export declare class SelectionContainerController')):
        raise ValueError('real SelectionContainer factory-returned SDK types required')
    tools = [hvigor / 'bin/hvigorw', hvigor / 'hvigor-ohos-plugin/package.json', node / 'bin/node']
    if json.loads(tools[1].read_text())['name'] != '@ohos/hvigor-ohos-plugin':
        raise ValueError('official OHOS Hvigor plugin required')
    return dict(schema_version=1, scope=SCOPE, arch=arch, run_id=run_id, role=role, project=str(project), sdk=str(sdk),
        hvigor_home=str(hvigor), node_home=str(node), generated_sha256={name:digest(project/name) for name in paths},
        sdk_declarations_sha256={name:digest(sdk/name) for name in declarations},
        compiler_sha256={str(path):digest(path) for path in tools}, template_sha256=digest(TEMPLATE),
        builder_sha256=digest(Path(__file__)), request_permissions=[PERMISSION] if role=='reader' else [],
        requires_real_UI_and_compositor=True, first_artifact_behavior_gate_passed=False)


def verify_inputs(value):
    if value != inputs(*(value[key] for key in ('project','sdk','arch','run_id','hvigor_home','node_home','role'))):
        raise ValueError('exact typed SelectionContainer caller or official compiler/SDK inputs changed')


def reason_resource():
    return {'string':[{'name':'selection_read_reason',
        'value':'Verify the text copied by this QEMU selection regression.'}]}


def app_name_resource():
    return {'string':[{'name':'app_name','value':'QEMU selection regression'}]}


def build(args):
    hvigor, node = args.hvigor_home.resolve(), args.node_home.resolve()
    if not (hvigor/'bin/hvigorw').is_file() or not (node/'bin/node').is_file():
        raise ValueError('official Hvigor and Node required before creating caller project')
    if args.role not in ROLES:raise ValueError('exact selection role required')
    # The common preparer retains its established VPN role vocabulary; the
    # selected module and final receipt bind the actual selection role.
    prepared=SimpleNamespace(**vars(args));prepared.role='normal'
    def preparation_module(_):
        value=module(args.role)
        value['module']['requestPermissions']=[{'name':row['name']} for row in value['module']['requestPermissions']]
        return value
    root, sdk = prepare_application(prepared, source(args.run_id,args.role), TEMPLATE,
        'selection-base-inputs.json', SCOPE, DECLARATION, module_factory=preparation_module)
    def write(name, value):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')
    write('build-profile.json5', dict(app=dict(products=[dict(name='default',compileSdkVersion='26.0.0',
        targetSdkVersion='26.0.0',compatibleSdkVersion='26.0.0',runtimeOS='OpenHarmony')],
        buildModeSet=[dict(name='debug'),dict(name='release')]), modules=[dict(name='entry',srcPath='./entry',
        targets=[dict(name='default',applyToProducts=['default'])])]))
    compiled_module=module(args.role);compiled_module['module']['deviceTypes']=['default']
    write('entry/src/main/module.json5',compiled_module)
    write('entry/src/main/resources/base/element/string.json',reason_resource())
    write('AppScope/resources/base/element/string.json',app_name_resource())
    for name,task in (('hvigorfile.ts','appTasks'),('entry/hvigorfile.ts','hapTasks')):
        write(name,"import { "+task+" } from '"+str(hvigor/'hvigor-ohos-plugin')+"';\nexport default { system: "+task+", plugins: [] };\n")
    write('hvigor/hvigor-config.json5',dict(modelVersion='6.0.0',dependencies={},execution=dict(daemon=False,parallel=False),logging=dict(level='info')))
    write('local.properties','sdk.dir='+str(sdk.parent)+'\n')
    write('arkui-selection-probe-inputs.json',inputs(root,sdk,args.arch,args.run_id,hvigor,node,args.role))
    subprocess.run([str(hvigor/'bin/hvigorw'),'assembleHap','--no-daemon','-p','product=default','-p','buildMode=debug'],
        cwd=root,env=dict(os.environ,OHOS_SDK_HOME=str(sdk.parent),NODE_HOME=str(node)),check=True)
    verify_inputs(json.loads((root/'arkui-selection-probe-inputs.json').read_text()))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('sdk','output','hvigor-home','node-home'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--arch',choices=('arm64','armv7a','x86_64'),required=True)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--role',choices=ROLES,default='normal')
    build(parser.parse_args())
