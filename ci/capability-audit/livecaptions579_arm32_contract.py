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
    path = Path(path)
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


def verify_build(value):
    build=load(value)
    require(build.get('schema')=='actual-livecaptions579-ohos32-build/v1' and
        build.get('status')=='compiled_linked_packaged_NOT_runtime_validated' and
        build.get('exit_code')==0 and build.get('runtime_validated') is False and
        build.get('first_artifact_behavior_gate_passed') is False, 'unfinished/failed ARM32 production cannot be admitted')
    here=Path(__file__).resolve().parent
    expected_sources={'livecaptions579_arm32_sources.py','livecaptions579_arm32_contract.py',
        'livecaptions579_arm32_production.py','livecaptions579_native.py','build_livecaptions579_arm32.py'}
    require(set(build['producer_sources'])==set(build['producer_source_origins'])==expected_sources,
        'complete finite production source set required')
    for name in ('livecaptions579_arm32_sources.py','livecaptions579_arm32_contract.py',
                 'livecaptions579_arm32_production.py','livecaptions579_native.py'):
        require(build['producer_sources'][name]['sha256']==sha((here/name).read_bytes()), 'fixed production source differs: '+name)
        require(build['producer_source_origins'][name]['sha256']==build['producer_sources'][name]['sha256'], 'production source export origin differs')
        raw(build['producer_sources'][name])
    script=here.parents[1]/'scripts/build_livecaptions579_arm32.py'
    require(build['producer_sources']['build_livecaptions579_arm32.py']['sha256']==sha(script.read_bytes()),
        'fixed actual worker entry differs')
    require(build['producer_source_origins']['build_livecaptions579_arm32.py']['sha256']==build['producer_sources']['build_livecaptions579_arm32.py']['sha256'],
        'actual worker source export differs')
    raw(build['producer_sources']['build_livecaptions579_arm32.py'])
    rows=commands(build['commands']); source=load(build['source_lock'])
    request=load(build['request']);out=Path(value['path']).parent
    require(Path(request['output'])==out and build['source_root']==str(out/'source') and
        request['source_lock']==build['source_lock'] and load(request['base_assets'])==build['base_assets'],
        'actual requested output/source/unchanged base descriptor differs')
    base=build['base_assets']
    require(base['assets']['har']['sha256']==BASE_HAR_SHA and base['assets']['notices']['sha256']==BASE_NOTICES_SHA,
        'exact existing R66 base input vector required')
    from livecaptions579_inputs import product_assets
    product_assets(base,'arm64-v8a')
    sdk=Path(build['sdk_root'])
    require(sdk.is_relative_to('/ohos/prebuilts/ohos-sdk/linux') and
        load(build['sdk_snapshot'])['root']==str(sdk), 'actual original resolved platform SDK root required')
    from livecaptions579_native import recipe, PREFIX, NAPI_SOURCES
    spec=recipe('armeabi-v7a',{'source':build['source_root'],'sdk_native':str(sdk),
        'ort':str(out/'ort/onnxruntime-ohos-armeabi-v7a-1.16.3'),'c_api_build':str(out/'c-api'),
        'install':str(out/'install'),'napi_build':str(out/'napi'),'node_addon':str(out/'node')})
    for label,key in (('c_api_configure','c_api_configure'),('c_api_build','c_api_build'),
        ('c_api_install','c_api_install'),('napi_configure','napi_configure_after_actual_c_api_copy'),('napi_build','napi_build')):
        require(rows[label]['argv']==spec['commands'][key], 'actual compiler argv differs from the fixed official-source recipe')
        require(all(rows[label]['environment'].get(k)==v for k,v in spec['environment'].items()), 'actual ORT environment differs')
    require(source['schema']=='actual-livecaptions579-source-cache/v1' and
        source['repositories']['sherpa']['commit']==SHERPA[1] and source['repositories']['node']['commit']==NODE[1] and
        set(source['archives'])==set(DEPENDENCIES), 'complete actual fixed native source cache required')
    for name,(_,url,checksum) in DEPENDENCIES.items():
        item=source['archives'][name]
        require(item['url']==url and item['file']['sha256']==checksum, 'native dependency source pin changed')
        raw(item['file'])
    ort_data=raw(source['ort'])
    require(source['ort']['sha256']==ORT_SHA and len(ort_data)==ORT_BYTES,'actual fixed ORT32 source archive missing')
    for role,commit in (('sherpa',SHERPA[1]),('node',NODE[1])):
        git_dir=source['repositories'][role]['git_dir']
        require(Path(git_dir).is_absolute() and
            Path(git_dir).parent==Path(build['source_lock']['path']).parent, 'fixed original source cache root required')
        git=['git','-c','safe.directory='+git_dir,'-C',git_dir]
        require(raw(rows[role+'_commit']['stdout']).decode().strip()==commit and
            rows[role+'_commit']['argv']==[*git,'rev-parse',commit+'^{commit}'] and
            rows[role+'_archive']['argv']==[*git,'archive','--format=tar',commit],
            'actual exact original-cache Git source/commit/archive argv differs')
    for key in ('source_before','source_after','sdk_snapshot','c_api_cache','napi_cache','c_api_compile_commands','napi_compile_commands'):
        raw(build[key])
    for role in ('c_api','napi'):
        cache_text=raw(build[role+'_cache']).decode();cache_values={}
        for line in cache_text.splitlines():
            if line.startswith(('#','//')) or '=' not in line or ':' not in line.split('=',1)[0]:continue
            key,val=line.split('=',1);cache_values[key.split(':',1)[0]]=val
        require(cache_values.get('OHOS_ARCH')=='armeabi-v7a' and
            cache_values.get('CMAKE_TOOLCHAIN_FILE')==str(sdk/'build/cmake/ohos.toolchain.cmake') and
            all(Path(cache_values[k]).is_relative_to(sdk/'llvm/bin') for k in ('CMAKE_C_COMPILER','CMAKE_CXX_COMPILER')),
            'actual OHOS SDK compiler/cache required')
        compile_rows=load(build[role+'_compile_commands']);require(compile_rows and len(compile_rows)<10000,'actual compile commands missing')
        for item in compile_rows:
            argv=item.get('arguments') or shlex.split(item['command'])
            require(argv and Path(argv[0]).is_relative_to(sdk/'llvm/bin') and '-mfloat-abi=hard' in argv and
                Path(item['file']).is_relative_to(out), 'actual native compile escaped target source/SDK')
        if role=='napi':
            require({str(Path(build['source_root'])/PREFIX/'src/main/cpp'/p) for p in NAPI_SOURCES} <=
                {r['file'] for r in compile_rows}, 'complete original NAPI source list was not compiled')
    for role in ('c_api','napi'):
        argv=rows[role+'_configure']['argv']
        require('-DOHOS_ARCH=armeabi-v7a' in argv and '-DCMAKE_C_FLAGS=-mfloat-abi=hard' in argv and
            '-DCMAKE_CXX_FLAGS=-mfloat-abi=hard' in argv and '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON' in argv,
            'real upstream OHOS32 toolchain configure argv required')
        require('-DFETCHCONTENT_UPDATES_DISCONNECTED=ON' in argv, 'native source updates cannot float')
    a=trace(build['c_api_trace'], build['source_root'], build['source_root'])
    b=trace(build['napi_trace'], build['source_root'], build['source_root'])
    require(set(a)==set(DEPENDENCIES) and set(b)=={'node_addon_api'}, 'actual native dependency closure differs')
    libraries=build['libraries']; require(set(libraries)==set(LIBS), 'four actual ARM32 DSOs required')
    for name,row in libraries.items():
        actual=elf32(raw(row['file'])); require(actual==row['elf'] and actual['soname']==name, 'actual ARM32 DSO differs')
        if name in ('libsherpa-onnx-c-api.so','libsherpa_onnx.so'):
            require(actual['hard_float'], 'new official-recipe outputs must expose their actual hard-float ABI')
            require(all(p=='$ORIGIN' for p in actual['rpaths']), 'new native library contains a foreign build-machine RPATH')
        label=name.replace('.','_').replace('+','p').replace('-','_')
        require(rows['strip_'+label]['argv']==[str(sdk/'llvm/bin/llvm-strip'),'--strip-unneeded',row['file']['path']] and
            rows['readelf_'+label]['argv']==[str(sdk/'llvm/bin/llvm-readelf'),'--file-header','--program-headers','--dynamic',
                '--dyn-symbols','--arch-specific',row['file']['path']], 'actual target strip/readelf argv differs')
        require('strip_'+name.replace('.','_').replace('+','p').replace('-','_') in rows and
            'readelf_'+name.replace('.','_').replace('+','p').replace('-','_') in rows, 'real strip/readelf raw evidence missing')
        if name=='libc++_shared.so':
            snapshot=load(build['sdk_snapshot'])
            require(snapshot['files'][row['input_origin']['sdk_relative']]['sha256']==row['input_sha256'],
                'actual matching SDK C++ runtime origin missing')
        else:require(sha(raw(row['input_origin']['file']))==row['input_sha256'], 'actual pre-strip native input differs')
        if name=='libonnxruntime.so':
            with zipfile.ZipFile(io.BytesIO(ort_data)) as z:
                require(sha(z.read('onnxruntime-ohos-armeabi-v7a-1.16.3/lib/libonnxruntime.so'))==row['input_sha256'],
                    'actual ORT32 library is not from the fixed source archive')
    api=set(libraries['libsherpa-onnx-c-api.so']['elf']['exports'])
    imported={s for s in libraries['libsherpa_onnx.so']['elf']['imports'] if s.startswith('SherpaOnnx')}
    require(imported and imported <= api and any('OfflineRecognizer' in n for n in imported) and
        any('VoiceActivityDetector' in n for n in imported), 'real complete NAPI imports/C API exports required')
    require('napi_module_register' in libraries['libsherpa_onnx.so']['elf']['imports'] and
        'OrtGetApiBase' in libraries['libonnxruntime.so']['elf']['exports'], 'actual native module/ORT exports absent')
    platform=build['platform_libraries']
    for name,row in libraries.items():
        for soname in row['elf']['needed']:
            require('/' not in soname and (soname in libraries or soname in platform), 'unresolved actual native dependency: '+soname)
    for name,row in platform.items():
        actual=elf32(raw(row['exported_file']))
        require(actual==row['elf'] and actual['soname']==name, 'actual SDK platform dependency proof differs')
        require(set(actual['needed']) <= set(platform)|set(libraries), 'platform dependency closure incomplete')
    # Full SDK snapshot and actual tool raw identify production provenance; this
    # does not claim that an SDK stub is the installed QEMU implementation.
    require(load(build['sdk_snapshot'])['toolchain_file_sha256']==build['toolchain']['sha256'], 'actual toolchain snapshot differs')
    for row in build['licenses']:
        require(raw(row['file']) in raw(build['notices']), 'actual native dependency notice omitted')
    before=load(build['source_before']);after=load(build['source_after'])
    # Original Git archive bytes plus actual source vectors rule out a patched
    # or stubbed compiler input hidden behind the expected commit's label.
    originals={}
    for role in ('sherpa','node'):
        data=raw(rows[role+'_archive']['stdout']);vector={};contents={}
        with tarfile.open(fileobj=io.BytesIO(data),mode='r:') as stream:
            for member in stream:
                p=PurePosixPath(member.name)
                require(not p.is_absolute() and '..' not in p.parts and '\\' not in member.name, 'unsafe fixed Git archive')
                if member.isfile():
                    content=stream.extractfile(member).read();contents[member.name]=content
                    vector[member.name]={'sha256':sha(content),'bytes':len(content)}
                elif member.issym():vector[member.name]={'symlink':member.linkname}
                else:require(member.isdir(), 'unsupported fixed Git archive member')
        stripped={p:{k:v for k,v in row.items() if k!='mode'} for p,row in before[role].items()}
        require(stripped==vector, 'pristine source vector differs from actual fixed Git archive')
        originals[role]=contents
    allowed={name for name,_,_ in DEPENDENCIES.values()}
    allowed.update(build['copied_native_inputs'])
    require(set(after['sherpa'])-set(before['sherpa'])==allowed and
        not set(before['sherpa'])-set(after['sherpa']), 'unexpected/lost native build source')
    # One known source delta, never an unchecked replacement source tree.
    require(set(build['source_adaptations'])=={'c_api_origin_rpath'}, 'only the reviewed CAPI RPATH delta required')
    adaptation=build['source_adaptations']['c_api_origin_rpath']
    require(set(adaptation)=={'patch','before_sha256','after_file'} and
        adaptation['before_sha256']==RPATH_SOURCE_SHA and raw(adaptation['patch'])==RPATH_PATCH.encode(),
        'exact upstream CAPI RPATH patch provenance required')
    cmake_original=originals['sherpa'][RPATH_SOURCE]
    require(sha(cmake_original)==RPATH_SOURCE_SHA and cmake_original.count(RPATH_BEFORE.encode())==1,
        'original Git CAPI RPATH preimage differs')
    cmake_patched=cmake_original.replace(RPATH_BEFORE.encode(),RPATH_AFTER.encode(),1)
    require(adaptation['after_file']['path']==str(Path(build['source_root'])/RPATH_SOURCE) and
        raw(adaptation['after_file'])==cmake_patched and
        after['sherpa'][RPATH_SOURCE]==dict(before['sherpa'][RPATH_SOURCE],
            sha256=sha(cmake_patched),bytes=len(cmake_patched)), 'complete CAPI RPATH postimage differs')
    patch_path=str(out/'c-api-origin-only.patch')
    require(adaptation['patch']['path']==patch_path and
        rows['rpath_patch_check']['argv']==['git','-C',build['source_root'],'apply','--check',patch_path] and
        rows['rpath_patch_apply']['argv']==['git','-C',build['source_root'],'apply',patch_path],
        'actual source-adaptation argv differs')
    for path,row in before['sherpa'].items():
        if path!=RPATH_SOURCE: require(after['sherpa'][path]==row, 'fixed sherpa source mutated: '+path)
    for name,(filename,_,checksum) in DEPENDENCIES.items():
        require(after['sherpa'][filename]['sha256']==checksum,'staged native archive changed')
    for path,item in build['copied_native_inputs'].items():
        require(raw(item['source'])==raw(item['copy']) and after['sherpa'][path]['sha256']==item['copy']['sha256'],
            'actual NAPI input copy differs')
    require(set(before['node'])==set(after['node']), 'node-addon source closure changed')
    for path,row in before['node'].items():
        if path!='napi-inl.h':require(after['node'][path]==row,'unrelated node-addon change')
    old=b'  napi_status status = napi_get_arraybuffer_info(_env, _value, &data, nullptr);'
    new=b'  size_t byte_length;\n  napi_status status = napi_get_arraybuffer_info(_env, _value, &data, &byte_length);'
    header=originals['node']['napi-inl.h']
    require(header.count(old)==1 and raw(build['node_header'])==header.replace(old,new,1) and
        after['node']['napi-inl.h']['sha256']==build['node_header']['sha256'], 'exact upstream node-addon patch required')
    har_proof(build['base_har'],build['har'],libraries,build['notices'])
    metadata=json.loads(tar_members(raw(build['har']))['package/ARM32_NATIVE_SOURCES.json'],object_pairs_hook=unique)
    require(metadata=={'source_lock':build['source_lock'],'commits':{'sherpa':SHERPA[1],'node_addon_api':NODE[1]},
        'source_adaptations':build['source_adaptations'],
        'toolchain':build['toolchain'],'libraries':libraries,'licenses':build['licenses'],
        'scope':'actual native production only; runtime pending'}, 'HAR native provenance differs from the actual build')
    return build


def owner_proof(value, build):
    seal=load(value)
    require(seal['schema']=='actual-livecaptions579-ohos32-seal/v1' and seal['runtime_validated'] is False and
        seal['first_artifact_behavior_gate_passed'] is False, 'real post-Owner seal required')
    report=load(seal['owner_receipt']); ledger=load(report['resource_ledger'])
    require(report['exit_code']==0 and report['cleanup_verified'] is True and report['owned_container_absent'] is True and
        ledger['schema']=='owned-resource35/v1' and ledger['phase']=='closed' and ledger['cleanup_verified'] is True and
        ledger['failed'] is False, 'original Owner35 must actually close before product admission')
    entries=[r for r in ledger['containers'] if r['command']==build['invocation_argv']]
    require(len(entries)==1 and entries[0]['owner']==ledger['owner_uuid'] and entries[0]['absent'] is True and
        re.fullmatch('[a-f0-9]{64}',entries[0]['id']), 'exact original owned native producer container required')
    entry=entries[0]; cs=ledger['commands']
    require(build['original_owner']['owner_uuid']==ledger['owner_uuid'] and entry['commit']==build['source_commit'],
        'native build belongs to another original Owner/source commit')
    require(build['original_owner']['owner_source']['sha256']==OWNER_SOURCE_SHA and
        build['owner_source_export']['sha256']==OWNER_SOURCE_SHA, 'original Owner source pin differs')
    raw(build['owner_source_export'])
    require(build['invocation_argv'][1]==build['producer_source_origins']['build_livecaptions579_arm32.py']['path'],
        'original worker command does not name its real source origin')
    source_root=Path(build['producer_source_origins']['build_livecaptions579_arm32.py']['path']).parents[1]
    for name,exported in build['producer_sources'].items():
        relative=('scripts/' if name=='build_livecaptions579_arm32.py' else 'ci/capability-audit/')+name
        git_rows=[r for r in cs if r['argv']==['git','-C',str(source_root),'show',build['source_commit']+':'+relative]]
        require(len(git_rows)==1 and git_rows[0]['exit_code']==0 and git_rows[0]['timed_out'] is False and
            sha(raw(git_rows[0]['stdout_record']))==exported['sha256'], 'actual tracked producer source/commit proof missing')
    created=[r for r in cs if r['argv'][:2]==['docker','create'] and entry['name'] in r['argv']]
    started=[r for r in cs if r['argv']==['docker','start','-a',entry['id']]]
    require(len(created)==len(started)==1 and all(r['exit_code']==0 and r['timed_out'] is False for r in (*created,*started)),
        'actual original create/start argv/exit/raw required')
    argv=created[0]['argv']; require(any(argv[i:i+2]==['--network','none'] for i in range(len(argv)-1)),
        'normal native compile worker must have network disabled; missing dependencies fail')
    for row in (*created,*started):
        raw(row['stdout_record'])
        if row.get('stderr_record'): raw(row['stderr_record'])
    inspected=[]
    for row in cs:
        if row['argv'][:2]!=['docker','inspect'] or row['exit_code']!=0: continue
        values=json.loads(raw(row['stdout_record']),object_pairs_hook=unique)
        for item in values:
            if item.get('Id')==entry['id']: inspected.append(item)
    require(inspected and all(r['HostConfig']['NetworkMode']=='none' and r['HostConfig']['ReadonlyRootfs'] is True and
        r['Config']['Cmd']==build['invocation_argv'] and r['Image']==entry['image'] and
        r['Config']['Labels']['ohos-qemu.root-run']==ledger['owner_uuid'] and
        r['Config']['Labels']['ohos-qemu.source-commit']==entry['commit'] for r in inspected),
        'actual same owned no-network worker inspection missing')
    require(all(any(m['Destination']=='/ohos' and m['RW'] is False for m in r['Mounts']) for r in inspected),
        'actual original SDK/source volume was not readonly')
    require(seal['build']==build['receipt_identity'], 'seal references another native build')
    return seal


def admit(inputs):
    if inputs.get('ohos32_direct_build'):
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
    seal=load(inputs['ohos32_source_build']); build=verify_build(seal['build'])
    build['receipt_identity']=seal['build']; owner_proof(inputs['ohos32_source_build'],build)
    require(inputs['assets']['har']==ref2(build['har']) and inputs['assets']['notices']==ref2(build['notices']),
        'descriptor does not select actual built HAR/full notices')
    require(inputs['assets']['encoder']==build['base_assets']['assets']['encoder'] and
        inputs['assets']['decoder']==build['base_assets']['assets']['decoder'] and
        inputs['assets']['tokens']==build['base_assets']['assets']['tokens'] and
        inputs['assets']['vad']==build['base_assets']['assets']['vad'] and
        inputs['licenses']==build['base_assets']['licenses'], 'only native ABI/HAR/notices may vary')
    return build
