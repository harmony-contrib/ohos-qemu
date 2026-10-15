#!/usr/bin/env python3
"""Compile the exact C/ArkTS disabled child profile caller with the official SDK."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import hashlib
from child_native_payload import processed_payload
from build_always_on_vpn_probe import prepare_application, module as base_module
from run_root_probe import digest

SOURCES = Path(__file__).with_name('child_profile_sources')
TEMPLATE = SOURCES / 'Index.ets'
BUNDLE = 'org.harmonycontrib.capabilityaudit'
SCOPE = 'ordinary_API26_disabled_child_profile_boundaries_NOT_supported_lifecycle'
DECLARATION = '@ohos.app.ability.childProcessManager.d.ts'
CONTRACTS = []
ABI = {'arm64': ('arm64-v8a', 'aarch64-linux-ohos'), 'armv7a': ('armeabi-v7a', 'arm-linux-ohos'), 'x86_64': ('x86_64', 'x86_64-linux-ohos')}


def source(run_id):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('fresh real Child profile caller nonce required')
    return TEMPLATE.read_text().replace('__RUN__', run_id)


def module(role):
    if role != 'normal': raise ValueError('ordinary permission-free Child profile caller required')
    return base_module(role)


def inputs(project, sdk, arch, run_id, hvigor_home, node_home):
    project, sdk = Path(project).resolve(), Path(sdk).resolve()
    hvigor, node = Path(hvigor_home).resolve(), Path(node_home).resolve()
    if arch not in ('arm64', 'armv7a', 'x86_64'): raise ValueError('actual caller ABI required')
    paths = ['AppScope/app.json5', 'build-profile.json5', 'entry/build-profile.json5',
        'entry/src/main/module.json5', 'entry/src/main/ets/pages/Index.ets',
        'entry/src/main/ets/entryability/EntryAbility.ets', 'entry/src/main/resources/base/profile/main_pages.json',
        'hvigorfile.ts', 'entry/hvigorfile.ts', 'hvigor/hvigor-config.json5', 'local.properties',
        'AppScope/resources/base/element/string.json', 'AppScope/resources/base/media/icon.svg',
        'entry/src/main/ets/child/Worker.ets', 'native_sources/profile.cpp',
        'entry/native-types/libprofile/index.d.ts', 'entry/native-types/libprofile/oh-package.json5',
        'entry/oh-package.json5']
    if any((project / name).is_symlink() for name in paths): raise ValueError('regular typed caller inputs required')
    if (project / paths[4]).read_text() != source(run_id): raise ValueError('real Child profile typed caller changed')
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
    declarations=['ets/api/'+DECLARATION, 'ets/api/@ohos.app.ability.ChildProcess.d.ts',
        'ets/api/@ohos.process.d.ts','ets/api/@ohos.file.fs.d.ts',
        'native/sysroot/usr/include/AbilityKit/native_child_process.h',
        'native/sysroot/usr/include/napi/native_api.h']
    for relative, name in (('entry/src/main/ets/child/Worker.ets','Worker.ets'),
                           ('native_sources/profile.cpp','profile.cpp'),
                           ('entry/native-types/libprofile/index.d.ts','profile.d.ts')):
        if (project/relative).read_text()!= (SOURCES/name).read_text().replace('__RUN__',run_id):
            raise ValueError('exact native/ArkTS child source required: '+name)
    native_path=project/'entry/libs'/ABI[arch][0]/'libprofile.so'
    runtime_path=project/'entry/libs'/ABI[arch][0]/'libc++_shared.so'
    for path in (native_path,runtime_path):
        if path.is_symlink() or not path.is_file():
            raise ValueError('actual regular compiled native child library required')
    for directory in ('ets','native'):
        metadata=json.loads((sdk/directory/'oh-uni-package.json').read_text())
        if any(metadata.get(key)!=value for key,value in
            (('apiVersion','26'),('releaseType','Release'),('platformVersion','26.0.0'))):
            raise ValueError('exact API26 Release child SDK required')
    strip=sdk/'native/llvm/bin/llvm-strip'
    tools = [hvigor / 'bin/hvigorw', hvigor / 'hvigor-ohos-plugin/package.json', node / 'bin/node',
             sdk/'native/llvm/bin/clang++', strip]
    if json.loads(tools[1].read_text())['name'] != '@ohos/hvigor-ohos-plugin':
        raise ValueError('official OHOS Hvigor plugin required')
    return dict(schema_version=1, scope=SCOPE, arch=arch, run_id=run_id, project=str(project), sdk=str(sdk),
        hvigor_home=str(hvigor), node_home=str(node), generated_sha256={name:digest(project/name) for name in paths},
        sdk_declarations_sha256={name:digest(sdk/name) for name in declarations},
        compiler_sha256={str(path):digest(path) for path in tools}, template_sha256=digest(TEMPLATE),
        builder_sha256=digest(Path(__file__)), request_permissions=[],
        source_sha256={p.name:digest(p) for p in sorted(SOURCES.iterdir()) if p.is_file()},
        native_compile_argv=native_command(project,sdk,arch),
        native_elf_sha256=digest(native_path), runtime_elf_sha256=digest(runtime_path),
        native_processing_helper_sha256=digest(Path(__file__).with_name('child_native_payload.py')),
        processed_native_elf_sha256=hashlib.sha256(processed_payload(native_path,strip,digest(native_path),digest(strip))).hexdigest(),
        processed_runtime_elf_sha256=hashlib.sha256(processed_payload(runtime_path,strip,digest(runtime_path),digest(strip))).hexdigest(),
        SDK_runtime_elf_sha256=digest(sdk/'native/llvm/lib'/ABI[arch][1]/'libc++_shared.so'),
        requires_real_native_C_API_and_ArkTS=True, first_artifact_behavior_gate_passed=False)


def native_command(project,sdk,arch):
    return list(map(str,[sdk/'native/llvm/bin/clang++','--target='+ABI[arch][1],
        '--sysroot='+str(sdk/'native/sysroot'),'-std=c++17','-shared','-fPIC','-O2',
        '-Wall','-Wextra','-Werror',project/'native_sources/profile.cpp','-lchild_process',
        '-lace_napi.z','-o',project/'entry/libs'/ABI[arch][0]/'libprofile.so']))


def verify_inputs(value):
    if value != inputs(*(value[key] for key in ('project','sdk','arch','run_id','hvigor_home','node_home'))):
        raise ValueError('exact typed Child profile caller or official compiler/SDK inputs changed')


def build(args):
    hvigor, node = args.hvigor_home.resolve(), args.node_home.resolve()
    if not (hvigor/'bin/hvigorw').is_file() or not (node/'bin/node').is_file():
        raise ValueError('official Hvigor and Node required before creating caller project')
    root, sdk = prepare_application(args, source(args.run_id), TEMPLATE,
        'child-default-profile-base-inputs.json', SCOPE, DECLARATION, module_factory=module)
    def write(name, value):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(value if isinstance(value,str) else json.dumps(value,indent=2)+'\n')
    write('AppScope/resources/base/element/string.json',
          {'string': [{'name': 'app_name', 'value': 'Child profile boundary audit'}]})
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
    write('entry/src/main/ets/child/Worker.ets',(SOURCES/'Worker.ets').read_text().replace('__RUN__',args.run_id))
    write('native_sources/profile.cpp',(SOURCES/'profile.cpp').read_text().replace('__RUN__',args.run_id))
    write('entry/native-types/libprofile/index.d.ts',(SOURCES/'profile.d.ts').read_text())
    write('entry/native-types/libprofile/oh-package.json5',dict(name='libprofile.so',version='1.0.0',types='./index.d.ts'))
    write('entry/oh-package.json5',dict(modelVersion='6.0.0',name='entry',version='1.0.0',dependencies={'libprofile.so':'file:./native-types/libprofile'}))
    libraries=root/'entry/libs'/ABI[args.arch][0];libraries.mkdir(parents=True)
    subprocess.run(native_command(root,sdk,args.arch),check=True)
    shutil.copyfile(sdk/'native/llvm/lib'/ABI[args.arch][1]/'libc++_shared.so',libraries/'libc++_shared.so')
    write('child-default-profile-probe-inputs.json',inputs(root,sdk,args.arch,args.run_id,hvigor,node))
    subprocess.run([str(hvigor/'bin/hvigorw'),'assembleHap','--no-daemon','-p','product=default','-p','buildMode=debug'],
        cwd=root,env=dict(os.environ,OHOS_SDK_HOME=str(sdk.parent),NODE_HOME=str(node)),check=True)
    verify_inputs(json.loads((root/'child-default-profile-probe-inputs.json').read_text()))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('sdk','output','hvigor-home','node-home'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--arch',choices=('arm64','armv7a','x86_64'),required=True)
    parser.add_argument('--run-id',required=True)
    parser.set_defaults(role='normal')
    build(parser.parse_args())
