"""Normal selected ARM32 production, explicitly after fresh representative gate.

No VM/container/SDK owner is created. Root invokes this inside its already held
normal compiler owner. CMake config/build/install run; target tests never run.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import zipfile


def ref(path):
    b=path.read_bytes();return dict(path=str(path.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source-root','sdk-native','cmake','build-dir','representative-gate'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--representative-gate-sha256',required=True);p.add_argument('--source-commit',required=True)
    p.add_argument('--normal-source',type=Path,required=True);p.add_argument('--normal-source-sha256',required=True)
    a=p.parse_args();here=Path(__file__).resolve().parent;root=a.source_root.resolve();sdk=a.sdk_native.resolve();out=a.build_dir.resolve()
    from produce_arm32 import normal_binding,gate_binding,preparation_binding
    normal_source={'path':str(a.normal_source),'sha256':a.normal_source_sha256}
    normal=normal_binding(normal_source)
    if normal['source_commit']!=a.source_commit:raise ValueError('same actual normal SOURCE commit required')
    representative=gate_binding({'path':str(a.representative_gate),'sha256':a.representative_gate_sha256},a.source_commit)
    preparation_binding(root)
    ninja=root/'prebuilts/build-tools/linux-x86/bin/ninja'
    if not ninja.is_file():raise ValueError('actual normal source Ninja required')
    toolchain=sdk/'build/cmake/ohos.toolchain.cmake'
    if not root.is_dir() or not toolchain.is_file() or not a.cmake.is_file() or out.exists() or not out.is_relative_to(root/'out'):raise ValueError('actual normal source/SDK/compiler owner output required')
    spec=json.loads((here/'INPUT-SOURCES.json').read_bytes())
    def asset(name):
        row=spec['arm32_sources'][name];path=here/row['relative']
        if ref(path)['sha256']!=row['sha256']:raise ValueError('fixed original public source changed')
        return path
    out.mkdir(parents=True);source=out/'source';source.mkdir();commands=[]
    with tarfile.open(asset('sherpa')) as t:
        for member in t.getmembers():
            rel=Path(*Path(member.name).parts[1:])
            if rel.is_absolute() or '..' in rel.parts:raise ValueError('unsafe upstream archive path')
            if member.isfile():
                dst=source/rel;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(t.extractfile(member).read())
            elif not member.isdir():raise ValueError('unreviewed upstream archive member')
    ort=out/'ort';ort.mkdir()
    with zipfile.ZipFile(asset('ort')) as z:
        for name in z.namelist():
            rel=Path(name)
            if rel.is_absolute() or '..' in rel.parts:raise ValueError('unsafe public ORT archive path')
            if not name.endswith('/'):
                dst=ort/rel;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(z.read(name))
    ort=ort/'onnxruntime-ohos-armeabi-v7a-1.16.3'
    build=out/'build';install=out/'install'
    env=dict(os.environ,SHERPA_ONNXRUNTIME_LIB_DIR=str(ort/'lib'),SHERPA_ONNXRUNTIME_INCLUDE_DIR=str(ort/'include'))
    flags='-mfloat-abi=softfp -flto=thin -fsanitize=cfi -fsanitize-cfi-cross-dso -fvisibility=hidden'
    configure=[str(a.cmake),'-S',str(source),'-B',str(build),'-G','Ninja','-DOHOS_ARCH=armeabi-v7a',
        '-DCMAKE_TOOLCHAIN_FILE='+str(toolchain),'-DCMAKE_MAKE_PROGRAM='+str(ninja),'-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY',
        '-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_FLAGS='+flags,'-DCMAKE_CXX_FLAGS='+flags,
        '-DCMAKE_SHARED_LINKER_FLAGS=-flto=thin -fsanitize=cfi -fsanitize-cfi-cross-dso',
        '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DCMAKE_INSTALL_PREFIX='+str(install),'-DBUILD_SHARED_LIBS=ON',
        '-DSHERPA_ONNX_ENABLE_C_API=ON','-DSHERPA_ONNX_ENABLE_BINARY=OFF','-DSHERPA_ONNX_ENABLE_TESTS=OFF',
        '-DSHERPA_ONNX_ENABLE_CHECK=OFF','-DSHERPA_ONNX_ENABLE_PYTHON=OFF','-DSHERPA_ONNX_ENABLE_PORTAUDIO=OFF',
        '-DSHERPA_ONNX_ENABLE_WEBSOCKET=OFF','-DSHERPA_ONNX_ENABLE_JNI=OFF','-DSHERPA_ONNX_ENABLE_TTS=OFF',
        '-DSHERPA_ONNX_ENABLE_SPEAKER_DIARIZATION=OFF']
    def run(argv,label):
        stdout=out/(label+'.stdout');stderr=out/(label+'.stderr')
        row=dict(argv=argv,exit_code=None,timed_out=False);commands.append(row)
        try:
            with stdout.open('xb') as so,stderr.open('xb') as se:done=subprocess.run(argv,env=env,stdout=so,stderr=se,timeout=7200)
            row['exit_code']=done.returncode
        except subprocess.TimeoutExpired:
            row['timed_out']=True;raise
        finally:
            row.update(stdout=ref(stdout),stderr=ref(stderr))
        if row['exit_code']:raise ValueError('actual normal ARM32 source build failed: '+label)
    report=dict(schema='normal-cpu-voice-arm32-source-production/v1',source_commit=a.source_commit,
        normal_source=normal_source,representative_gate=ref(a.representative_gate),representative_binding=representative,
        sdk_native=str(sdk),toolchain=ref(toolchain),cmake=ref(a.cmake),ninja=ref(ninja),sources=spec['arm32_sources'],commands=commands,
        source_only_compile_link_not_runtime=True,runtime_pass=False,first_artifact_behavior_gate_passed=False)
    try:
        run(configure,'configure');run([str(a.cmake),'--build',str(build),'--parallel','2','--verbose'],'compile-link');run([str(a.cmake),'--install',str(build)],'install')
        destinations=root/'drivers/peripheral/intelligent_voice/passthrough/cpu/prebuilt/armeabi-v7a';destinations.mkdir(parents=True,exist_ok=True)
        libraries={'libsherpa-onnx-c-api.so':install/'lib/libsherpa-onnx-c-api.so','libonnxruntime.so':ort/'lib/libonnxruntime.so'}
        candidates=[sdk/'sysroot/usr/lib/arm-linux-ohos/libc++_shared.so',sdk/'llvm/lib/arm-linux-ohos/libc++_shared.so']
        found=[p for p in candidates if p.is_file()]
        if not found or len({ref(p)['sha256'] for p in found})!=1:raise ValueError('one actual same SDK ARM32 C++ runtime required')
        libraries['libc++_shared.so']=found[0]
        report['libraries']={}
        for name,path in libraries.items():
            b=path.read_bytes()
            if b[:6]!=b'\x7fELF\x01\x01' or int.from_bytes(b[18:20],'little')!=40 or int.from_bytes(b[36:40],'little')&0x400:raise ValueError('actual ARM32 ELF production required')
            dst=destinations/name;shutil.copyfile(path,dst);report['libraries'][name]=dict(produced=ref(path),installed_source=ref(dst))
        database=json.loads((build/'compile_commands.json').read_bytes());units=[]
        for row in database:
            words=row.get('arguments') or shlex.split(row['command'])
            if '-c' not in words or words.count('-o')!=1:raise ValueError('whole actual ARM32 compiler TU command')
            obj=Path(row['directory'])/words[words.index('-o')+1]
            units.append(dict(source=ref(Path(row['directory'])/row['file']),object=ref(obj),command=words,
                effective_CFI='-fsanitize=cfi' in words and '-fsanitize-cfi-cross-dso' in words))
        if not units or not all(v['effective_CFI'] for v in units):raise ValueError('all actual new ARM32 source TUs retain CFI')
        report.update(status='actual_normal_ARM32_compile_link_ONLY',translation_units=units,compile_commands=ref(build/'compile_commands.json'),ninja_log=ref(build/'.ninja_log'))
    finally:
        (out/'BUILD.json').write_text(json.dumps(report,indent=2)+'\n')
    shutil.copyfile(out/'BUILD.json',destinations/'BUILD.json')
    return 0


if __name__=='__main__':raise SystemExit(main())
