#!/usr/bin/env python3
"""Compile the real API26 LazyDynamic and WaterFlow factories with the official UI transform."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from build_always_on_vpn_probe import prepare_application, module as base_module
from run_root_probe import digest

TEMPLATE = Path(__file__).with_name('arkui_lazy_layouts_probe.ets')
BUNDLE = 'org.harmonycontrib.capabilityaudit'
SCOPE = 'ordinary_API26_LazyDynamic_and_WaterFlow_typed_factories_native_layout_scroll_change_reset_remove_recreate'
DECLARATION = '@ohos.arkui.components.ArkLazyDynamicLayout.d.ts'
CONTRACTS = [*('arkts_export:@ohos.arkui.components.ArkLazyDynamicLayout:' + name for name in ('LazyDynamicLayoutAttribute','LazyDynamicLayoutInstance')),
             *('arkts_export:@ohos.arkui.components.ArkLazyWaterFlowLayout:' + name for name in ('LazyVWaterFlowLayoutAttribute','LazyVWaterFlowLayoutInstance','LazyWaterFlowLayoutAttribute'))]


def source(run_id):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('fresh real lazy-layout caller nonce required')
    return TEMPLATE.read_text().replace('__RUN__', run_id)


def module(role):
    if role != 'normal': raise ValueError('ordinary permission-free lazy-layout caller required')
    return base_module(role)


def inputs(project, sdk, arch, run_id, hvigor_home, node_home):
    project, sdk = Path(project).resolve(), Path(sdk).resolve()
    hvigor, node = Path(hvigor_home).resolve(), Path(node_home).resolve()
    if arch not in ('arm64', 'armv7a', 'x86_64'): raise ValueError('actual caller ABI required')
    paths = ['AppScope/app.json5', 'build-profile.json5', 'entry/build-profile.json5',
        'entry/src/main/module.json5', 'entry/src/main/ets/pages/Index.ets',
        'entry/src/main/ets/entryability/EntryAbility.ets', 'entry/src/main/resources/base/profile/main_pages.json',
        'hvigorfile.ts', 'entry/hvigorfile.ts', 'hvigor/hvigor-config.json5', 'local.properties']
    if any((project / name).is_symlink() for name in paths): raise ValueError('regular typed caller inputs required')
    if (project / paths[4]).read_text() != source(run_id): raise ValueError('real lazy-layout typed caller changed')
    app = json.loads((project / paths[0]).read_text())['app']
    profile = json.loads((project / paths[1]).read_text())
    entry = json.loads((project / paths[2]).read_text())
    actual_module = json.loads((project / paths[3]).read_text())['module']
    if (app['bundleName'] != BUNDLE or actual_module.get('requestPermissions') != [] or
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
    declarations = ['ets/api/' + DECLARATION, 'ets/api/@ohos.arkui.node.d.ts', 'ets/component/common.d.ts',
        'ets/kits/@kit.ArkUI.d.ts','ets/api/@ohos.arkui.components.ArkLazyWaterFlowLayout.d.ts',
        'ets/api/arkui/LazyLayoutAlgorithm.d.ts','ets/api/arkui/FrameNode.d.ts','ets/api/arkui/Graphics.d.ts']
    dynamic = (sdk / declarations[0]).read_text(); water = (sdk / declarations[4]).read_text()
    if any(value not in dynamic for value in (
        'export declare class LazyDynamicLayoutAttribute extends CommonMethod<LazyDynamicLayoutAttribute>',
        'export declare const LazyDynamicLayoutInstance: LazyDynamicLayoutAttribute;',
        'export declare function LazyDynamicLayout(algorithm: LazyLayoutAlgorithm): LazyDynamicLayoutAttribute;')):
        raise ValueError('real dynamic factory-returned SDK types required')
    if any(value not in water for value in (
        'export declare class LazyWaterFlowLayoutAttribute<T> extends CommonMethod<T>',
        'export declare class LazyVWaterFlowLayoutAttribute extends LazyWaterFlowLayoutAttribute<LazyVWaterFlowLayoutAttribute>',
        'export declare const LazyVWaterFlowLayoutInstance: LazyVWaterFlowLayoutAttribute;',
        '(): LazyVWaterFlowLayoutAttribute;')):
        raise ValueError('real inherited waterflow factory-returned SDK types required')
    tools = [hvigor / 'bin/hvigorw', hvigor / 'hvigor-ohos-plugin/package.json', node / 'bin/node']
    if json.loads(tools[1].read_text())['name'] != '@ohos/hvigor-ohos-plugin':
        raise ValueError('official OHOS Hvigor plugin required')
    return dict(schema_version=1, scope=SCOPE, arch=arch, run_id=run_id, project=str(project), sdk=str(sdk),
        hvigor_home=str(hvigor), node_home=str(node), generated_sha256={name:digest(project/name) for name in paths},
        sdk_declarations_sha256={name:digest(sdk/name) for name in declarations},
        compiler_sha256={str(path):digest(path) for path in tools}, template_sha256=digest(TEMPLATE),
        builder_sha256=digest(Path(__file__)), request_permissions=[],
        requires_real_UI_and_compositor=True, first_artifact_behavior_gate_passed=False)


def verify_inputs(value):
    if value != inputs(*(value[key] for key in ('project','sdk','arch','run_id','hvigor_home','node_home'))):
        raise ValueError('exact typed lazy-layout caller or official compiler/SDK inputs changed')


def build(args):
    hvigor, node = args.hvigor_home.resolve(), args.node_home.resolve()
    if not (hvigor/'bin/hvigorw').is_file() or not (node/'bin/node').is_file():
        raise ValueError('official Hvigor and Node required before creating caller project')
    root, sdk = prepare_application(args, source(args.run_id), TEMPLATE,
        'lazy-layouts-base-inputs.json', SCOPE, DECLARATION, module_factory=module)
    def write(name, value):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')
    write('build-profile.json5', dict(app=dict(products=[dict(name='default',compileSdkVersion='26.0.0',
        targetSdkVersion='26.0.0',compatibleSdkVersion='26.0.0',runtimeOS='OpenHarmony')],
        buildModeSet=[dict(name='debug'),dict(name='release')]), modules=[dict(name='entry',srcPath='./entry',
        targets=[dict(name='default',applyToProducts=['default'])])]))
    compiled_module=module('normal');compiled_module['module']['deviceTypes']=['default']
    write('entry/src/main/module.json5',compiled_module)
    for name,task in (('hvigorfile.ts','appTasks'),('entry/hvigorfile.ts','hapTasks')):
        write(name,"import { "+task+" } from '"+str(hvigor/'hvigor-ohos-plugin')+"';\nexport default { system: "+task+", plugins: [] };\n")
    write('hvigor/hvigor-config.json5',dict(modelVersion='6.0.0',dependencies={},execution=dict(daemon=False,parallel=False),logging=dict(level='info')))
    write('local.properties','sdk.dir='+str(sdk.parent)+'\n')
    write('arkui-lazy-layouts-probe-inputs.json',inputs(root,sdk,args.arch,args.run_id,hvigor,node))
    subprocess.run([str(hvigor/'bin/hvigorw'),'assembleHap','--no-daemon','-p','product=default','-p','buildMode=debug'],
        cwd=root,env=dict(os.environ,OHOS_SDK_HOME=str(sdk.parent),NODE_HOME=str(node)),check=True)
    verify_inputs(json.loads((root/'arkui-lazy-layouts-probe-inputs.json').read_text()))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('sdk','output','hvigor-home','node-home'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--arch',choices=('arm64','armv7a','x86_64'),required=True)
    parser.add_argument('--run-id',required=True)
    parser.set_defaults(role='normal')
    build(parser.parse_args())
