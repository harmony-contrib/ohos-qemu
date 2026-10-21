"""Finite normal OHOS32 production on the caller's original Owner35.

No Owner, lease, QEMU, socket or Popen is constructed. Root calls source cache
preparation and the one original owned Linux compiler worker when scheduled.
The worker's subprocess.run calls are normal compiler/tool invocations inside
that original owned container, not a host acceptance suite.
"""
from pathlib import Path, PurePosixPath
import copy
import gzip
import inspect
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import zipfile
from livecaptions579_arm32_contract import (elf32, har_proof, load, raw, ref, ref2,
    regular, require, sha, tar_members, unique, verify_build, owner_proof)
from livecaptions579_arm32_sources import (BASE_HAR_SHA, BASE_NOTICES_SHA, DEPENDENCIES, LIBS, NODE,
    ORT_BYTES, ORT_SHA, OWNER_SOURCE_SHA, SHERPA, RPATH_SOURCE, RPATH_SOURCE_SHA, RPATH_BEFORE, RPATH_AFTER, RPATH_PATCH)
from livecaptions579_native import PREFIX, recipe

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SOURCE_NAMES=('livecaptions579_arm32_sources.py','livecaptions579_arm32_contract.py',
              'livecaptions579_arm32_production.py','livecaptions579_native.py')


def write(path,value):
    path=Path(path); temporary=path.with_name(path.name+'.pending')
    with temporary.open('x') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def sources():
    return {name:ref(HERE/name) for name in SOURCE_NAMES} | {
        'build_livecaptions579_arm32.py':ref(ROOT/'scripts/build_livecaptions579_arm32.py')}


def original(owner):
    require(sha(Path(inspect.getfile(type(owner))).read_bytes())==OWNER_SOURCE_SHA and
        owner.phase=='work' and owner.lease is not None, 'live original Owner35 required')
    current=os.fstat(owner.lease.fileno());named=owner.lock_path.stat()
    require(stat.S_ISREG(current.st_mode) and current.st_nlink==1 and
        (current.st_dev,current.st_ino)==(named.st_dev,named.st_ino), 'original retained lease inode required')
    return {'owner_uuid':owner.owner,'lease_dev':current.st_dev,'lease_ino':current.st_ino,
        'owner_source':ref(Path(inspect.getfile(type(owner))).resolve())}


def prepare_on_original_owner(owner, *, cache, base_assets, ort, proxy=None):
    """Fetch exact source inputs only. All git/curl children use the given Owner.

    Root may reuse an existing immutable completed cache by its actual Ref; this
    function itself requires a fresh destination and never overwrites a cache.
    """
    identity=original(owner);cache=Path(cache)
    require(cache.is_absolute() and cache.is_relative_to(owner.output) and not cache.exists(), 'fresh original production output/cache required')
    require(proxy is None or re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}',proxy), 'explicit root loopback proxy only')
    base=load(base_assets)
    require(base['assets']['har']['sha256']==BASE_HAR_SHA and base['assets']['notices']['sha256']==BASE_NOTICES_SHA and
        ort['sha256']==ORT_SHA and len(raw(ort))==ORT_BYTES,
        'actual R66 base HAR and fixed OHOS32 ORT archive required')
    for value in (*base['assets'].values(),*base['licenses'].values()): raw(value)
    cache.mkdir();start=len(owner.commands);repositories={};archives={}
    for name,(url,commit,fetch_ref) in (('sherpa',SHERPA),('node',NODE)):
        target=cache/(name+'.git')
        owner.command(['git','init','--bare',str(target)],'asr32_'+name+'_init',check=True)
        argv=['git']
        if proxy: argv+=['-c','http.proxy='+proxy]
        owner.command([*argv,'-C',str(target),'fetch','--depth=1','--no-tags',url,fetch_ref],
            'asr32_'+name+'_fetch',timeout=1800,check=True)
        done=owner.command(['git','-C',str(target),'rev-parse','FETCH_HEAD^{commit}'],
            'asr32_'+name+'_commit',check=True)
        require(done.stdout.decode().strip()==commit, 'fixed upstream Git commit differs')
        repositories[name]={'url':url,'commit':commit,'git_dir':str(target),'fetch_ref':fetch_ref}
    for name,(filename,url,checksum) in DEPENDENCIES.items():
        part=cache/(filename+'.part');target=cache/filename
        argv=['curl','--fail','--location','--proto','=https','--tlsv1.2','--connect-timeout','30','--max-time','1800']
        if proxy: argv+=['--proxy',proxy]
        owner.command([*argv,'--output',str(part),url],'asr32_fetch_'+name.replace('-','_'),timeout=1830,check=True)
        require(ref(part)['sha256']==checksum, 'actual fixed source archive differs: '+name)
        part.rename(target);archives[name]={'url':url,'file':ref(target)}
    ort_path=cache/'onnxruntime-ohos-armeabi-v7a-1.16.3.zip';ort_path.write_bytes(raw(ort))
    result={'schema':'actual-livecaptions579-source-cache/v1','scope':'actual source/dependency preparation only; not native build or runtime',
        'repositories':repositories,'archives':archives,'ort':ref(ort_path),'base_assets':base_assets,
        'original_owner':identity,'commands':copy.deepcopy(owner.commands[start:]),'producer_sources':sources(),
        'runtime_validated':False,'first_artifact_behavior_gate_passed':False}
    path=cache/'source-lock.json';write(path,result);require(original(owner)==identity,'original lease changed')
    return ref(path)


def _mount(path,writable=False): return {'Type':'bind','Source':str(path),'RW':writable}


def run_on_original_owner(owner, *, cache_ref, base_assets, output, image, source_commit,
                          sdk_native, sdk_library_dir, sdk_libcxx, sdk_mount):
    """One ordinary original-Owner compiler container, network=none.

    sdk_mount is Root's existing read-only /ohos source volume mount descriptor;
    this function does not choose a volume, image, SDK revision or new Owner.
    Same absolute output/cache/source file paths are used inside and outside.
    """
    identity=original(owner);cache=load(cache_ref);base=load(base_assets);out=Path(output)
    require(cache['base_assets']==base_assets and re.fullmatch('[a-f0-9]{40}',source_commit), 'same source cache/base identity required')
    current=owner.command(['git','-C',str(ROOT),'rev-parse','HEAD'],'asr32_production_source_head',check=True)
    require(current.stdout.decode().strip()==source_commit,'normal production must use the actual adopted canonical commit')
    tracked=[*('ci/capability-audit/'+name for name in SOURCE_NAMES),
        'ci/capability-audit/livecaptions579_inputs.py','patches/lib/livecaptions_provider.py',
        'scripts/build_livecaptions579_arm32.py','scripts/run_device_type_matrix_build_docker.sh']
    for index,relative in enumerate(tracked):
        actual=owner.command(['git','-C',str(ROOT),'show',source_commit+':'+relative],
            'asr32_production_source_'+str(index),check=True)
        require(actual.stdout==(ROOT/relative).read_bytes(),'normal producer input differs from the adopted commit: '+relative)
    require(out.is_absolute() and out.is_relative_to(owner.output) and not out.exists(), 'fresh original output required')
    require(Path(sdk_native).is_relative_to('/ohos/prebuilts/ohos-sdk/linux') and
        Path(sdk_library_dir).is_relative_to(sdk_native) and Path(sdk_libcxx).is_relative_to(sdk_native), 'actual original platform SDK paths required')
    require(sdk_mount.get('Type')=='volume' and sdk_mount.get('RW') is False and
        set(sdk_mount)=={'Type','Name','RW'}, 'existing actual readonly source volume mount required')
    for name in ('sherpa','node'): require(Path(cache['repositories'][name]['git_dir']).parent==Path(cache_ref['path']).parent, 'fixed cache git root required')
    out.mkdir();request=out/'request.json'
    value={'schema':'livecaptions579-ohos32-production-request/v1','source_lock':cache_ref,'base_assets':base_assets,
        'output':str(out/'worker'),'sdk_native':str(sdk_native),'sdk_library_dir':str(sdk_library_dir),
        'sdk_libcxx':str(sdk_libcxx),'source_commit':source_commit,'original_owner':identity}
    write(request,value)
    script=ROOT/'scripts/build_livecaptions579_arm32.py'
    argv=['python3',str(script),'--request',str(request),'--request-sha256',ref(request)['sha256']]
    mounts={'/ohos':dict(sdk_mount),str(ROOT):_mount(ROOT),str(out):_mount(out,True),
        str(Path(cache_ref['path']).parent):_mount(Path(cache_ref['path']).parent)}
    refs=[base_assets,identity['owner_source'],*base['assets'].values(),*base['licenses'].values()]
    if 'source_production_receipt' in base: refs.append(base['source_production_receipt'])
    for value in refs:
        p=regular(value['path'])
        if not any(p.is_relative_to(Path(destination)) for destination in mounts):mounts[str(p)]=_mount(p)
    options=['--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
        '--tmpfs','/tmp:rw,nosuid,nodev,size=1g','--cpus','2','--memory','6g','--pids-limit','512']
    for destination,item in mounts.items():
        spec='type='+item['Type']+',src='+item.get('Name',item.get('Source',''))+',dst='+destination
        if item['RW'] is False:spec+=',readonly'
        options+=['--mount',spec]
    entry=owner.plan(name='ohos-asr32-'+owner.owner,commit=source_commit,image=image,mounts=mounts,command=argv)
    owner.create(entry,options);owner.start(entry,timeout=14400,combined=True)
    build_ref=ref(out/'worker/build.json');build=verify_build(build_ref)
    require(build['original_owner']==identity and build['invocation_argv']==argv and original(owner)==identity,
        'actual native producer/source/lease differs')
    # Root still owns every resource. Root calls its normal finish once all
    # production work is done, then invokes seal_after_owner_finished below.
    return {'build':build_ref,'container_id':entry['id'],'request':ref(request),'original_owner':identity}


def _extract(data,destination):
    require(not destination.exists(), 'fresh source extraction only');destination.mkdir()
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:*') as stream:
        rows=stream.getmembers();require(len(rows)<100000 and sum(r.size for r in rows)<512*1024*1024,'bounded source archive required')
        stream.extractall(destination,filter='data')


def _inventory(root):
    result={}
    for p in sorted(root.rglob('*')):
        relative=p.relative_to(root).as_posix()
        if p.is_symlink():
            require(p.resolve().is_relative_to(root.resolve()),'source/SDK symlink escapes original root')
            result[relative]={'symlink':os.readlink(p)}
        elif p.is_file():result[relative]={'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size,'mode':stat.S_IMODE(p.stat().st_mode)}
    return result


def _license_files(roots,output):
    output.mkdir();rows=[]
    for name,root in roots.items():
        found=[]
        for p in sorted(root.rglob('*')):
            if p.is_file() and not p.is_symlink() and re.match(r'^(LICENSE|LICENCE|COPYING|NOTICE|COPYRIGHT)([._-].*)?$',p.name,re.I):
                require(p.stat().st_size<=2*1024*1024,'bounded full notice required')
                target=output/name/p.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
                found.append({'source':p.relative_to(root).as_posix(),'file':ref(target)})
        require(found,'original dependency license/notice missing: '+name)
        rows.extend({'dependency':name,**r} for r in found)
    require(sum(r['file']['bytes'] for r in rows)<=8*1024*1024,'finite complete native notices required')
    return rows


def worker(request_ref):
    request=load(request_ref)
    require(set(request)=={'schema','source_lock','base_assets','output','sdk_native','sdk_library_dir','sdk_libcxx','source_commit','original_owner'} and
        request['schema']=='livecaptions579-ohos32-production-request/v1','finite fixed production request required')
    out=Path(request['output']);require(out.is_absolute() and not out.exists(),'fresh normal worker output required');out.mkdir()
    logs=out/'commands';logs.mkdir();source_origins=sources();exports=out/'producer-source';exports.mkdir()
    exported_sources={}
    for name,value in source_origins.items():
        p=exports/name;p.write_bytes(raw(value));exported_sources[name]=ref(p)
    owner_copy=exports/'original-owned_resource35.py';owner_copy.write_bytes(raw(request['original_owner']['owner_source']))
    report={'schema':'actual-livecaptions579-ohos32-build/v1','status':'pending',
        'exit_code':1,'runtime_validated':False,'first_artifact_behavior_gate_passed':False,'commands':[],
        'request':request_ref,'producer_sources':exported_sources,'producer_source_origins':source_origins,
        'owner_source_export':ref(owner_copy),'original_owner':request['original_owner'],
        'source_commit':request['source_commit'],'source_lock':request['source_lock']}
    report['invocation_argv']=[v.decode() for v in Path('/proc/self/cmdline').read_bytes().split(b'\0') if v]
    destination=out/'build.json'
    def save():write(destination,report)
    sdk=Path(request['sdk_native']).resolve();library_dir=Path(request['sdk_library_dir']).resolve()
    report['sdk_root']=str(sdk)
    require(library_dir.is_relative_to(sdk),'actual SDK library directory required')
    environment={'PATH':str(sdk/'build-tools/cmake/bin')+':'+str(sdk/'llvm/bin')+':/usr/bin:/bin',
        'LC_ALL':'C','LANG':'C','SHERPA_ONNXRUNTIME_LIB_DIR':'','SHERPA_ONNXRUNTIME_INCLUDE_DIR':''}
    def command(argv,label,timeout=3600):
        row={'argv':list(map(str,argv)),'label':label,'environment':dict(environment),
            'started_monotonic':time.monotonic(),'exit_code':None,'timed_out':False}
        report['commands'].append(row);save()
        try:
            done=subprocess.run(row['argv'],stdin=subprocess.DEVNULL,capture_output=True,env=environment,timeout=timeout)
            stdout,stderr=done.stdout,done.stderr;row['exit_code']=done.returncode
        except subprocess.TimeoutExpired as error:
            stdout,stderr=error.stdout or b'',error.stderr or b'';row['timed_out']=True
        row['finished_monotonic']=time.monotonic()
        for name,data in (('stdout',stdout),('stderr',stderr)):
            p=logs/(str(len(report['commands'])).zfill(3)+'-'+label+'-'+name+'.bin');p.write_bytes(data);row[name]=ref(p)
        save();require(row['exit_code']==0 and row['timed_out'] is False,'actual native tool failed: '+label)
        return stdout
    try:
        cache=load(request['source_lock']);base=load(request['base_assets']);report['base_assets']=base
        require(cache['base_assets']==request['base_assets'] and base['assets']['har']['sha256']==BASE_HAR_SHA,
            'same immutable source cache/R66 product data required')
        code=out/'source';node=out/'node';report['source_root']=str(code)
        for name,definition,path in (('sherpa',SHERPA,code),('node',NODE,node)):
            repo=cache['repositories'][name];require(repo['commit']==definition[1] and repo['url']==definition[0], 'fixed actual Git input required')
            # Bare cache belongs to the original host Owner UID. Trust only
            # that exact validated cache path inside the root compiler worker;
            # never set safe.directory=* or change global Git configuration.
            git=['git','-c','safe.directory='+repo['git_dir'],'-C',repo['git_dir']]
            data=command([*git,'rev-parse',definition[1]+'^{commit}'],name+'_commit',60)
            require(data.decode().strip()==definition[1], 'actual Git source commit differs')
            archive=command([*git,'archive','--format=tar',definition[1]],name+'_archive',300)
            _extract(archive,path)
        before=out/'source-before.json';write(before,{'sherpa':_inventory(code),'node':_inventory(node)});report['source_before']=ref(before)
        # Keep the complete original Git vector above. Apply only the reviewed
        # root CMake RPATH delta, using real git argv/exit/raw and postimage.
        capi_cmake=code/RPATH_SOURCE;pristine_cmake=capi_cmake.read_bytes()
        require(sha(pristine_cmake)==RPATH_SOURCE_SHA and
            pristine_cmake.count(RPATH_BEFORE.encode())==1, 'exact upstream CAPI RPATH source required')
        origin_patch=out/'c-api-origin-only.patch';origin_patch.write_text(RPATH_PATCH)
        command(['git','-C',str(code),'apply','--check',str(origin_patch)],'rpath_patch_check',60)
        command(['git','-C',str(code),'apply',str(origin_patch)],'rpath_patch_apply',60)
        require(capi_cmake.read_bytes()==pristine_cmake.replace(RPATH_BEFORE.encode(),RPATH_AFTER.encode(),1),
            'only the exact CAPI RPATH source postimage is permitted')
        report['source_adaptations']={'c_api_origin_rpath':{'patch':ref(origin_patch),
            'before_sha256':RPATH_SOURCE_SHA,'after_file':ref(capi_cmake)}}
        license_roots={'sherpa':code,'node_addon_api':node}
        for name,(filename,url,checksum) in DEPENDENCIES.items():
            item=cache['archives'][name];require(item['url']==url and item['file']['sha256']==checksum,'fixed native dependency differs')
            (code/filename).write_bytes(raw(item['file']))
            extracted=out/'dependency-licenses'/name;extracted.parent.mkdir(exist_ok=True)
            if filename.endswith('.zip'):
                extracted.mkdir()
                with zipfile.ZipFile(io.BytesIO(raw(item['file']))) as z:
                    require(len(z.infolist())<100000 and sum(r.file_size for r in z.infolist())<512*1024*1024,'bounded native zip source required')
                    for r in z.infolist():
                        p=PurePosixPath(r.filename);require(not p.is_absolute() and '..' not in p.parts and '\\' not in r.filename and
                            (r.external_attr>>16)&0o170000!=0o120000,'safe native source archive required')
                    z.extractall(extracted)
            else:_extract(raw(item['file']),extracted)
            license_roots[name]=extracted
        ort_archive=raw(cache['ort']);require(cache['ort']['sha256']==ORT_SHA and len(ort_archive)==ORT_BYTES,'actual fixed ORT32 archive required')
        ort=out/'ort';ort.mkdir()
        with zipfile.ZipFile(io.BytesIO(ort_archive)) as z:
            for r in z.infolist():
                p=PurePosixPath(r.filename);require(not p.is_absolute() and '..' not in p.parts and '\\' not in r.filename and
                    (r.external_attr>>16)&0o170000!=0o120000,'safe actual ORT32 archive required')
            z.extractall(ort)
        ort_root=ort/'onnxruntime-ohos-armeabi-v7a-1.16.3'
        require((ort_root/'include/onnxruntime_cxx_api.h').is_file() and (ort_root/'lib/libonnxruntime.so').is_file(),'exact upstream ORT layout required')
        patch=code/PREFIX/'src/main/cpp/my-patch.diff'
        command(['git','-C',str(node),'apply','--check',str(patch)],'node_patch_check',60)
        command(['git','-C',str(node),'apply',str(patch)],'node_patch_apply',60)
        report['node_header']=ref(node/'napi-inl.h')
        snapshot=out/'sdk-snapshot.json';toolchain=sdk/'build/cmake/ohos.toolchain.cmake'
        require((sdk/'llvm/bin/clang').exists() and (sdk/'llvm/bin/clang++').exists() and toolchain.is_file(),
            'actual original OHOS SDK clang/toolchain required; target is proved by compile/ELF evidence')
        write(snapshot,{'root':str(sdk),'files':_inventory(sdk),'toolchain_file_sha256':sha(toolchain.read_bytes())})
        report['sdk_snapshot']=ref(snapshot);report['toolchain']={'path':str(toolchain),'sha256':sha(toolchain.read_bytes())}
        paths={'source':str(code),'sdk_native':str(sdk),'ort':str(ort_root),'c_api_build':str(out/'c-api'),
            'install':str(out/'install'),'napi_build':str(out/'napi'),'node_addon':str(node)}
        spec=recipe('armeabi-v7a',paths);environment.update(spec['environment'])
        for role in ('c_api_configure','c_api_build','c_api_install'):
            command(spec['commands'][role],role.replace('c_api_','c_api_'))
        report['copied_native_inputs']={}
        for target,source in spec['copy_before_napi'].items():
            target=Path(target);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(Path(source).resolve(),target)
            report['copied_native_inputs'][target.relative_to(code).as_posix()]={
                'source':ref(Path(source).resolve()),'copy':ref(target)}
        command(spec['commands']['napi_configure_after_actual_c_api_copy'],'napi_configure')
        command(spec['commands']['napi_build'],'napi_build')
        report.update(c_api_cache=ref(out/'c-api/CMakeCache.txt'),napi_cache=ref(out/'napi/CMakeCache.txt'),
            c_api_trace=ref(out/'c-api-trace.jsonl'),napi_trace=ref(out/'napi-trace.jsonl'),
            c_api_compile_commands=ref(out/'c-api/compile_commands.json'),napi_compile_commands=ref(out/'napi/compile_commands.json'))
        after=out/'source-after.json';write(after,{'sherpa':_inventory(code),'node':_inventory(node)});report['source_after']=ref(after)
        libraries={};libdir=out/'native';libdir.mkdir();strip=sdk/'llvm/bin/llvm-strip';readelf=sdk/'llvm/bin/llvm-readelf'
        require(Path(request['sdk_libcxx']).resolve().is_relative_to(sdk),'actual matching SDK libc++_shared required')
        inputs={'libsherpa_onnx.so':out/'napi/libsherpa_onnx.so',
            'libsherpa-onnx-c-api.so':out/'install/lib/libsherpa-onnx-c-api.so',
            'libonnxruntime.so':ort_root/'lib/libonnxruntime.so','libc++_shared.so':Path(request['sdk_libcxx'])}
        for name,path in inputs.items():
            target=libdir/name;shutil.copyfile(path.resolve(),target);before_strip=ref(target)
            label=name.replace('.','_').replace('+','p').replace('-','_')
            command([str(strip),'--strip-unneeded',str(target)],'strip_'+label,120)
            command([str(readelf),'--file-header','--program-headers','--dynamic','--dyn-symbols','--arch-specific',str(target)],'readelf_'+label,120)
            origin={'sdk_relative':path.resolve().relative_to(sdk).as_posix()} if name=='libc++_shared.so' else {'file':ref(path.resolve())}
            libraries[name]={'file':ref(target),'elf':elf32(target.read_bytes()),'input_sha256':before_strip['sha256'],
                'source_path':str(path),'input_origin':origin}
        report['libraries']=libraries;platform={};pending={n for r in libraries.values() for n in r['elf']['needed']} - set(libraries)
        exported=out/'sdk-platform';exported.mkdir()
        while pending:
            name=sorted(pending)[0];pending.remove(name)
            require(re.fullmatch(r'[A-Za-z0-9_+.-]+\.so(?:\.[0-9]+)*',name),'finite SDK native dependency name required')
            original_path=(library_dir/name).resolve();require(original_path.is_relative_to(sdk),'SDK dependency escaped original SDK')
            target=exported/name;shutil.copyfile(original_path,target);actual=elf32(target.read_bytes())
            platform[name]={'source_path':str(original_path),'exported_file':ref(target),'elf':actual}
            pending.update(set(actual['needed'])-set(libraries)-set(platform))
            require(len(platform)<64,'bounded complete native dependency closure required')
        report['platform_libraries']=platform
        license_rows=_license_files(license_roots,out/'licenses');report['licenses']=license_rows
        notices=out/'LIVE_CAPTIONS_NOTICES.arm32.txt';notice_data=bytearray(raw(base['assets']['notices']))
        for row in license_rows:
            notice_data.extend(('\n\n--- ARM32 native source '+row['dependency']+'/'+row['source']+' ---\n').encode());notice_data.extend(raw(row['file']))
        notices.write_bytes(notice_data);report['notices']=ref(notices)
        base_har=base['assets']['har'];original_members=tar_members(raw(base_har));profile='package/build-profile.json5'
        anchor=b'"arm64-v8a",';require(original_members[profile].count(anchor)==1,'fixed official HAR profile edit required')
        original_members[profile]=original_members[profile].replace(anchor,b'"armeabi-v7a",\n        '+anchor,1)
        original_members['package/libs/armeabi-v7a']=None
        for name,row in libraries.items():original_members['package/libs/armeabi-v7a/'+name]=raw(row['file'])
        original_members['package/NOTICE.arm32.txt']=bytes(notice_data)
        original_members['package/ARM32_NATIVE_SOURCES.json']=(json.dumps({'source_lock':request['source_lock'],
            'commits':{'sherpa':SHERPA[1],'node_addon_api':NODE[1]},'source_adaptations':report['source_adaptations'],
            'toolchain':report['toolchain'],
            'libraries':libraries,'licenses':license_rows,'scope':'actual native production only; runtime pending'},indent=2)+'\n').encode()
        har=out/'sherpa_onnx-1.11.2-three-abi.har'
        with har.open('xb') as physical:
            with gzip.GzipFile(fileobj=physical,mode='wb',mtime=0,filename='') as compressed:
                with tarfile.open(fileobj=compressed,mode='w') as stream:
                    for name,data in original_members.items():
                        row=tarfile.TarInfo(name);row.mtime=0;row.uid=row.gid=0;row.mode=0o755 if data is None else 0o644
                        if data is None:row.type=tarfile.DIRTYPE;stream.addfile(row)
                        else:row.size=len(data);stream.addfile(row,io.BytesIO(data))
        report.update(base_har=base_har,har=ref(har),status='compiled_linked_packaged_NOT_runtime_validated',exit_code=0)
        save();verify_build(ref(destination))
        require(report['producer_source_origins']==sources(),'producer source changed during actual build')
    except BaseException as error:
        report.update(exit_code=1,status='failed_pending',error=type(error).__name__+': '+str(error));save();raise
    return ref(destination)


def seal_after_owner_finished(*, build_ref, owner_receipt, output):
    """Called after Root's normal finish_report. No resource operations occur."""
    build=verify_build(build_ref);build['receipt_identity']=build_ref
    out=Path(output);require(out.is_absolute() and not out.exists(),'fresh post-Owner seal output required');out.mkdir()
    value={'schema':'actual-livecaptions579-ohos32-seal/v1','build':build_ref,'owner_receipt':owner_receipt,
        'runtime_validated':False,'first_artifact_behavior_gate_passed':False}
    sealed=out/'seal.json';write(sealed,value);owner_proof(ref(sealed),build)
    descriptor=copy.deepcopy(build['base_assets']);descriptor['assets']['har']=ref2(build['har'])
    descriptor['assets']['notices']=ref2(build['notices']);descriptor['ohos32_source_build']=ref2(ref(sealed))
    path=out/'product-assets-arm32.json';write(path,descriptor)
    # Pure replay reopens all actual outputs and the final original Owner ledger.
    from livecaptions579_arm32_contract import admit
    admit(descriptor)
    return {'descriptor':ref(path),'seal':ref(sealed),'runtime_validated':False,
        'first_artifact_behavior_gate_passed':False}
