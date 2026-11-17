"""Replay actual ARM32 production artifacts; no process or resource operations.

Compilation/HAR production is never a QEMU capability pass. An unfinished or
failed producer cannot yield an admissible product descriptor.
"""
from pathlib import Path, PurePosixPath
import hashlib
import io
import json
import re
import shlex
import struct
import tarfile
from livecaptions579_arm32_sources import BASE_HAR_SHA, BASE_NOTICES_SHA, DEPENDENCIES, LIBS, NODE, SHERPA, OWNER_SOURCE_SHA, ORT_SHA, ORT_BYTES, RPATH_SOURCE, RPATH_SOURCE_SHA, RPATH_BEFORE, RPATH_AFTER, RPATH_PATCH
import zipfile


def require(value, message):
    if not value: raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: '+key)
        result[key] = value
    return result


def sha(data): return hashlib.sha256(data).hexdigest()


def regular(path):
    from livecaptions579_inputs import _resolve_artifact_path
    path = _resolve_artifact_path(str(path))
    require(path.is_absolute() and '..' not in path.parts and path.is_file() and
        not any(p.is_symlink() for p in (path, *path.parents)), 'actual absolute regular unchanged artifact required')
    return path


def ref(path):
    path = regular(path); data = path.read_bytes()
    return {'path': str(path), 'sha256': sha(data), 'bytes': len(data)}


def raw(value):
    require(type(value) is dict and set(value) in ({'path','sha256'}, {'path','sha256','bytes'}) and
        re.fullmatch('[a-f0-9]{64}', value['sha256']), 'actual finite artifact Ref required')
    data = regular(value['path']).read_bytes()
    require(sha(data) == value['sha256'] and ('bytes' not in value or len(data) == value['bytes']), 'artifact bytes changed')
    return data


def load(value): return json.loads(raw(value), object_pairs_hook=unique)


def ref2(value): return {'path':value['path'], 'sha256':value['sha256']}


def tar_members(data):
    result = {}; total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as stream:
        for member in stream:
            p = PurePosixPath(member.name)
            require(not p.is_absolute() and '..' not in p.parts and '\\' not in member.name and
                member.name not in result and (member.isfile() or member.isdir()), 'finite safe HAR regular members required')
            total += member.size
            require(len(result) < 10000 and total <= 512*1024*1024, 'bounded HAR required')
            result[member.name] = stream.extractfile(member).read() if member.isfile() else None
    return result


def elf32(data):
    require(len(data) >= 52 and data[:7] == b'\x7fELF\x01\x01\x01', 'actual little-endian ELF32 required')
    h = struct.unpack_from('<HHIIIIIHHHHHH', data, 16)
    etype, machine, version, _, phoff, shoff, flags, _, phsize, phnum, shsize, shnum, _ = h
    require((etype,machine,version) == (3,40,1) and flags & 0xff000000 == 0x05000000,
        'real ARM EABI5 DSO required')
    require(phsize == 32 and shsize == 40 and 0 < phnum < 1024 and 0 < shnum < 65536 and
        phoff+phsize*phnum <= len(data) and shoff+shsize*shnum <= len(data), 'complete ARM ELF tables required')
    ph = [struct.unpack_from('<IIIIIIII',data,phoff+i*phsize) for i in range(phnum)]
    sections = [struct.unpack_from('<IIIIIIIIII',data,shoff+i*shsize) for i in range(shnum)]
    def area(offset, size):
        require(0 <= offset <= len(data) and 0 <= size <= len(data)-offset, 'ELF range outside artifact')
        return data[offset:offset+size]
    def text(table, offset):
        require(0 <= offset < len(table), 'ELF string offset invalid')
        end = table.find(b'\0',offset); require(end >= offset, 'ELF string not terminated')
        return table[offset:end].decode('utf-8','strict')
    dynamic = [p for p in ph if p[0] == 2]; require(len(dynamic)==1, 'one actual dynamic table required')
    p = dynamic[0]; entries=[]
    for off in range(p[1],p[1]+p[4],8):
        tag,value=struct.unpack('<II',area(off,8))
        if tag==0: break
        entries.append((tag,value))
    table_address=[v for t,v in entries if t==5]; size=[v for t,v in entries if t==10]
    require(len(table_address)==len(size)==1, 'one dynamic string table required')
    loads=[p for p in ph if p[0]==1 and p[2] <= table_address[0] and table_address[0]+size[0] <= p[2]+p[4]]
    require(len(loads)==1, 'dynamic strings must be backed by actual file load')
    table=area(loads[0][1]+table_address[0]-loads[0][2],size[0])
    needed=[text(table,v) for t,v in entries if t==1]
    sonames=[text(table,v) for t,v in entries if t==14]
    require(len(needed)==len(set(needed)) and len(sonames)==1, 'unique DT_NEEDED and SONAME required')
    exports=[]; imports=[]
    for s in sections:
        if s[1] != 11: continue
        require(s[9]==16 and s[6]<len(sections), 'real dynsym required')
        strings=sections[s[6]]; st=area(strings[4],strings[5])
        for offset in range(s[4],s[4]+s[5],16):
            name,_,_,info,other,index=struct.unpack('<IIIBBH',area(offset,16))
            if not name: continue
            value=text(st,name)
            if index==0: imports.append(value)
            elif info>>4 in (1,2) and other&3 in (0,3): exports.append(value)
    require(exports or imports, 'actual dynamic symbols required')
    return {'class':32,'machine':40,'eabi':5,'flags':flags,'hard_float':bool(flags & 0x400),
        'soname':sonames[0],'needed':needed,'rpaths':[text(table,v) for t,v in entries if t in (15,29)],
        'exports':sorted(set(exports)),'imports':sorted(set(imports))}


def commands(rows):
    require(type(rows) is list and 15 <= len(rows) < 100, 'actual finite native command chain required')
    labels=[]; last=None
    for row in rows:
        require(type(row['argv']) is list and row['argv'] and all(type(a) is str for a in row['argv']) and
            re.fullmatch('[A-Za-z0-9_-]+',row['label']) and row['label'] not in labels and
            row['exit_code']==0 and row['timed_out'] is False and
            row['finished_monotonic'] >= row['started_monotonic'] and
            (last is None or row['started_monotonic'] >= last), 'actual ordered successful argv/raw chain required')
        raw(row['stdout']); raw(row['stderr']); labels.append(row['label']); last=row['finished_monotonic']
    mandatory=('sherpa_commit','sherpa_archive','node_commit','node_archive','rpath_patch_check','rpath_patch_apply','node_patch_check','node_patch_apply',
        'c_api_configure','c_api_build','c_api_install','napi_configure','napi_build')
    require(all(n in labels for n in mandatory) and [labels.index(n) for n in mandatory] == sorted(labels.index(n) for n in mandatory),
        'real source/patch/C API/NAPI sequence missing')
    return {r['label']:r for r in rows}


def trace(value, source_root, dependency_cache):
    observed={}
    for line in raw(value).decode().splitlines():
        row=json.loads(line,object_pairs_hook=unique)
        if row.get('cmd','').lower()!='fetchcontent_declare': continue
        args=row['args']; require(args, 'empty FetchContent declaration')
        name=args[0].lower(); require(name in DEPENDENCIES or name=='node_addon_api', 'unknown native fetch: '+name)
        if name=='node_addon_api':
            require(NODE[0] in args and NODE[1] in args, 'actual fixed node-addon source declaration required')
        else:
            filename,_,checksum=DEPENDENCIES[name]
            require(str(Path(dependency_cache)/filename) in args and 'SHA256='+checksum in args,
                'native source must use the SHA-pinned local cache: '+name)
        require(Path(row['file']).is_relative_to(source_root), 'native CMake declaration came from unknown source')
        observed[name]=row['file']
    return observed


def har_proof(base_ref, har_ref, libraries, notices):
    require(base_ref['sha256']==BASE_HAR_SHA, 'unchanged official two-ABI HAR required')
    old=tar_members(raw(base_ref)); new=tar_members(raw(har_ref))
    profile='package/build-profile.json5'
    require(profile in old and profile in new, 'actual HAR build profile missing')
    # This exact source-local edit does not rewrite ETS, either 64-bit DSO or metadata.
    anchor=b'"arm64-v8a",'
    require(old[profile].count(anchor)==1 and new[profile]==old[profile].replace(anchor,b'"armeabi-v7a",\n        '+anchor,1),
        'only the explicit new ABI filter may change')
    extra={'package/libs/armeabi-v7a', 'package/ARM32_NATIVE_SOURCES.json','package/NOTICE.arm32.txt'}
    extra.update('package/libs/armeabi-v7a/'+name for name in LIBS)
    # tar directory member spelling is normalized only by the producer, never by DATA.
    require(set(new)-set(old)==extra and set(old)-set(new)==set(), 'unexpected/lost merged HAR member')
    for name,data in old.items():
        if name!=profile: require(new[name]==data, 'existing HAR member changed: '+name)
    for name,value in libraries.items():
        require(new['package/libs/armeabi-v7a/'+name]==raw(value['file']), 'HAR does not contain actual native output')
    require(new['package/NOTICE.arm32.txt']==raw(notices), 'full actual ARM32 notices missing from HAR')
    return {'preserved_original_members':len(old)-1,'new_abi':'armeabi-v7a','native_members':list(LIBS)}


def admit(inputs):
    require(inputs.get('ohos32_direct_build'), 'direct ARM32 native production descriptor required')
    build=load(inputs['ohos32_direct_build'])
    require(build.get('schema')=='direct-livecaptions579-ohos32-build/v1' and
        build.get('status')=='compiled_linked_packaged_NOT_runtime_validated' and
        build.get('exit_code')==0 and build.get('runtime_validated') is False and
        build.get('first_artifact_behavior_gate_passed') is False,
        'completed direct ARM32 native production required')
    libraries=build['libraries']
    require(set(libraries)==set(LIBS), 'four actual ARM32 DSOs required')
    for name,row in libraries.items():
        actual=elf32(raw(row['file']))
        require(actual==row['elf'] and actual['soname']==name, 'actual direct ARM32 DSO differs')
        require(all(p=='$ORIGIN' for p in actual['rpaths']), 'foreign direct native RPATH')
        # Vendored ORT and SDK libc++ retain their supplied ABI flags.
        if name in ('libsherpa-onnx-c-api.so','libsherpa_onnx.so'):
            require(actual['hard_float'] and actual['rpaths'],
                'direct compiled sherpa outputs require hard-float ABI and origin-relative RPATH')
    api=set(libraries['libsherpa-onnx-c-api.so']['elf']['exports'])
    imported={s for s in libraries['libsherpa_onnx.so']['elf']['imports'] if s.startswith('SherpaOnnx')}
    require(imported and imported <= api and any('OfflineRecognizer' in n for n in imported) and
        any('VoiceActivityDetector' in n for n in imported), 'complete direct NAPI imports/C API exports required')
    require('napi_module_register' in libraries['libsherpa_onnx.so']['elf']['imports'] and
        'OrtGetApiBase' in libraries['libsherpa-onnx-c-api.so']['elf']['imports'] and
        'OrtGetApiBase' in libraries['libonnxruntime.so']['elf']['exports'],
        'actual direct native module/ORT symbols absent')
    har_proof(build['base_har'],build['har'],libraries,build['notices'])
    require(inputs['assets']['har']==ref2(build['har']) and inputs['assets']['notices']==ref2(build['notices']),
        'descriptor does not select actual direct HAR/full notices')
    base=build['base_assets']
    require(all(inputs['assets'][name]==base['assets'][name] for name in ('encoder','decoder','tokens','vad')) and
        inputs['licenses']==base['licenses'], 'only direct native ABI/HAR/notices may vary')
    for row in build['licenses']:
        require(raw(row['file']) in raw(build['notices']), 'direct native dependency notice omitted')
    return build
