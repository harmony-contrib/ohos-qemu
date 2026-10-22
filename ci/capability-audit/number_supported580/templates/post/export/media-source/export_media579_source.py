"""Read-only queries/copies inside the existing original Owner35 export CID.

Only fixed Ninja metadata tools are invoked. Compiler/linker commands printed by
Ninja are DATA and are never executed. No Owner/container/lease is created.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
from media579_source_request import (GFX,NINJA,TUS,GRAMMAR,AUDIO_PERMISSION,AUDIO_SOURCES,
    MIDI_HEADERS,IV_ROOT,IV_ENGINE_ROOT,SOURCE_TREES,PLUGINS,MEDIA_NAMES,IV_NAMES,PARTITIONS,USB_NAMES,USB_TREES,USB_SOURCES,CPU_PREBUILT_NAMES,CPU_ROOT,SPATIAL_ROOT,TELEPHONY_NATIVE_ROOT,CPU_SOURCE_AUDIO,CPU_IMAGE_ASSETS,NUMBER580_ROOTS,NUMBER580_SOURCES,NUMBER580_TUS,NUMBER580_DEPENDENCIES,NUMBER580_NAPI_SHA256,NUMBER580_PROJECT_REVISION)


def need(ok,message):
    if not ok:raise ValueError(message)


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def ref(path):return dict(path=str(path),sha256=sha(path),bytes=path.stat().st_size)


def load(path):
    def unique(pairs):
        result={}
        for key,value in pairs:
            need(key not in result,'duplicate actual media export key');result[key]=value
        return result
    return json.loads(path.read_text(),object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))


def argv(entry):
    words=entry.get('arguments') or shlex.split(entry['command'])
    need(type(words) is list and words and not any(w.startswith('@') for w in words),'complete expanded native compiler/linker DATA')
    return words


def cfi(words):
    selected=set()
    for word in words:
        if word.startswith('-fno-sanitize='):
            for item in word.split('=',1)[1].split(','):
                if item=='cfi':selected={x for x in selected if not x.startswith('cfi')}
                else:selected.discard(item)
        if word.startswith('-fsanitize='):selected.update(word.split('=',1)[1].split(','))
    return any(x.startswith('cfi') for x in selected) and '-fsanitize-cfi-cross-dso' in words


class Collector:
    def __init__(self):
        self.source=Path('/ohos');self.output=Path('/evidence/media-source-facts579')
        need(not self.output.exists(),'fresh fixed media export output only');self.output.mkdir()
        (self.output/'commands').mkdir();self.files={};self.commands=[];self.bytes=0;self.observations=[]
        self.primary=load(Path('/evidence/native-export/installed-runtime-export.json'))
        self.product=self.primary['product'];self.build=self.source/'out'/self.product
        need(self.primary['source_ro'] is self.primary['out_ro'] is True and self.primary['source_root']=='/ohos','actual original primary RO source/out')
        self.commit=self.primary['source_identity']['product_commit']
        self.before={};self.ninja_cache={};self.rule_files={};self.graph_inventory=[]

    def regular(self,path):
        path=Path(path);resolved=path.resolve()
        need(resolved.is_relative_to(self.source) and resolved.is_file() and
             os.statvfs(resolved).f_flag&os.ST_RDONLY,'actual regular selected RO source/out file')
        info=resolved.stat();need(stat.S_ISREG(info.st_mode) and info.st_size<=512*1024**2,'finite complete media source/out file')
        return resolved

    def copy(self,path):
        path=Path(path);real=self.regular(path);logical=str(path.relative_to(self.source))
        if logical in self.files:
            need(self.before[logical]['sha256']==sha(real),'actual source changed across uses');return self.files[logical]
        before=(real.stat().st_dev,real.stat().st_ino,real.stat().st_size,real.stat().st_mtime_ns,real.stat().st_ctime_ns)
        digest=sha(real);self.bytes+=real.stat().st_size
        need(len(self.before)<30000 and self.bytes<=3*1024**3,'complete export budget exceeded; do not truncate')
        target=self.output/'files'/logical;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(real,target)
        need(sha(target)==digest and before==(real.stat().st_dev,real.stat().st_ino,real.stat().st_size,real.stat().st_mtime_ns,real.stat().st_ctime_ns),'full stable actual RO file copy')
        self.before[logical]=dict(logical=str(path),resolved=str(real),sha256=digest,stat=list(before))
        row=ref(target);self.files[logical]=row
        if path.is_relative_to(self.build):self.files[str(path)]=row
        return row

    def command(self,words,label):
        need((words[0]==str(self.source/NINJA) and words[1:4]==['-C',str(self.build),'-t'] and
             words[4] in ('targets','query','compdb','deps')) or
             words[:3] in (['git','-C',str(self.source/GFX.rstrip('/'))],
                ['git','-C',str(self.source/'base/telephony/number_identity')],
                ['git','-C',str(self.source/'base/telephony/core_service')]) and words[3:]==['rev-parse','HEAD'],
             'fixed read-only Ninja/git query only; printed compiler commands never executable')
        index=len(self.commands);out=self.output/'commands'/(str(index).zfill(4)+'-'+label+'-stdout.bin')
        err=out.with_name(out.name.replace('-stdout.bin','-stderr.bin'))
        row=dict(argv=words,exit_code=None,timed_out=False,stream_mode='normal-query-separate-stdio579/v1');self.commands.append(row)
        with out.open('xb') as stdout,err.open('xb') as stderr:
            try:
                result=subprocess.run(words,cwd=self.source,stdout=stdout,stderr=stderr,timeout=240,env={**os.environ,'LC_ALL':'C','NINJA_STATUS':'[%f/%t] '})
                row['exit_code']=result.returncode
            except subprocess.TimeoutExpired:
                row['timed_out']=True;raise
            finally:
                row.update(stdout=ref(out),stderr=ref(err),log=str(out),sha256=sha(out));self.save('collecting')
        need(row['exit_code']==0 and not row['timed_out'] and err.read_bytes()==b'','actual successful complete split-stream read-only query')
        return row

    def tree(self,relative):
        root=self.source/relative;need(root.is_dir() and not root.is_symlink(),'actual complete fixed source tree')
        names=[];excluded=[]
        for folder,dirs,files in os.walk(root,followlinks=False):
            for name in dirs:
                p=Path(folder)/name
                if p.is_symlink():excluded.append(dict(path=str(p),link=os.readlink(p),kind='directory_link_not_followed'))
            dirs[:]=sorted(d for d in dirs if d not in ('.git','.repo','__pycache__') and not (Path(folder)/d).is_symlink())
            for name in sorted(files):
                p=Path(folder)/name
                if p.is_symlink():
                    self.copy(p);excluded.append(dict(path=str(p),link=os.readlink(p),kind='file_link_resolved_with_full_bytes'))
                else:self.copy(p)
                names.append(str(p.relative_to(self.source)))
        self.observations.append(dict(kind='complete_fixed_source_tree',root=str(root),members=names,link_observations=excluded,excluded_repository_metadata=['.git','.repo','__pycache__']))

    def graph(self):
        # GN emits literal include/subninja paths. Read every reachable original
        # graph file to identify all actual product cc/cxx and solink rules.
        pending=[self.build/'build.ninja'];seen=set()
        while pending:
            path=pending.pop().resolve()
            if path in seen:continue
            need(path.is_relative_to(self.build),'generated graph escapes actual product build')
            real=self.regular(path);seen.add(path);text=real.read_text();self.graph_inventory.append(dict(logical=str(path),sha256=sha(real),bytes=real.stat().st_size))
            found=False
            for match in re.finditer(r'^rule ([A-Za-z0-9_]+)\s*$',text,re.M):
                name=match[1]
                if re.fullmatch(r'(?:[A-Za-z0-9_]+_)?(?:cc|cxx|solink)',name):
                    need(name not in self.rule_files,'unique actual product generated rule');self.rule_files[name]=self.copy(path);found=True
            for match in re.finditer(r'^(?:include|subninja) ([^\n]+)$',text,re.M):
                token=match[1].strip();need(re.fullmatch(r'[A-Za-z0-9_./+\-]+',token) and '..' not in Path(token).parts,'literal GN graph inclusion')
                pending.append(self.build/token)
            need(len(seen)<=40000,'complete Ninja graph finite bound exceeded')
        rules=sorted(k for k in self.rule_files if re.fullmatch(r'(?:[A-Za-z0-9_]+_)?(?:cc|cxx)',k))
        need(any(re.search(r'(?:^|_)cc$',k) for k in rules) and any(re.search(r'(?:^|_)cxx$',k) for k in rules),'both actual whole product C and C++ rules')
        row=self.command([str(self.source/NINJA),'-C',str(self.build),'-t','compdb','-x',*rules],'whole-c-cxx-compdb')
        self.database=load(Path(row['stdout']['path']));need(type(self.database) is list and self.database,'complete actual product C/C++ compilation database')
        self.compile_query=row;self.compile_rules=rules
        self.ninja_log=self.copy(self.build/'.ninja_log');self.log=Path(self.ninja_log['path']).read_text().splitlines()
        self.targets_query=self.command([str(self.source/NINJA),'-C',str(self.build),'-t','targets','all'],'whole-graph-targets')
        self.targets=[]
        for line in Path(self.targets_query['stdout']['path']).read_text().splitlines():
            match=re.fullmatch(r'([A-Za-z0-9_./+\-]+): ([A-Za-z0-9_]+)',line)
            need(match is not None,'actual Ninja targets grammar')
            self.targets.append((match[1],match[2]))

    def entry(self,logical):
        entries=[e for e in self.database if (Path(e['directory'])/e['file']).resolve()==self.source/logical]
        need(len(entries)==1 and Path(entries[0]['directory'])==self.build,'one actual full product translation unit')
        return entries[0]

    def log_line(self,target):
        rows=[s for s in self.log if len(s.split('\t'))==5 and s.split('\t')[3]==target]
        need(rows,'actual completed full product Ninja target');return rows[-1]

    def unit(self,logical,entry=None):
        e=self.entry(logical) if entry is None else entry
        need(e in self.database and (Path(e['directory'])/e['file']).resolve()==self.source/logical,'one actual selected source/object command')
        words=argv(e);need('-c' in words and words.count('-o')==1,'actual full source compile DATA')
        target=Path(words[words.index('-o')+1]);target=target if target.is_absolute() else self.build/target
        need(target.is_relative_to(self.build),'actual object belongs to selected product')
        token=str(target.relative_to(self.build));obj=self.copy(target)
        dep=self.command([str(self.source/NINJA),'-C',str(self.build),'-t','deps',token],'actual-object-deps')
        text=Path(dep['stdout']['path']).read_text();lines=text.splitlines()
        head=re.fullmatch(re.escape(token)+r': #deps ([0-9]+), deps mtime [0-9]+ \(VALID\)',lines[0] if lines else '')
        need(head is not None and len(lines)>=int(head[1])+1,'actual valid full Ninja dependency record')
        deps=[s[4:] for s in lines[1:] if s.startswith('    ')];need(len(deps)==int(head[1]),'full actual dependency count')
        need(any((self.build/p).resolve()==self.source/logical for p in deps),'actual dependency record names the complete source TU')
        return dict(source=self.copy(self.source/logical),object=obj,command=words,effective_CFI=cfi(words),object_logical=str(target),
            compile_ninja_log_line=self.log_line(token),dependency_kind='original_ninja_deps/v1',dependency_file=dep['stdout'],dependency_query=dep,
            dependency_object=token,actual_depfile_present=target.with_suffix(target.suffix+'.d').is_file())

    def link(self,name,staged):
        candidates=[target for target,rule in self.targets if re.fullmatch(r'(?:[A-Za-z0-9_]+_)?solink',rule) and Path(target).name==name and not target.startswith(('lib.unstripped/','./lib.unstripped/')) and
            (self.build/target).is_file() and sha(self.build/target)==staged['sha256']]
        need(len(candidates)==1,'one real product solink output equals installed staged bytes: '+name);target=candidates[0]
        query=self.command([str(self.source/NINJA),'-C',str(self.build),'-t','query',target],'solink-query')
        lines=Path(query['stdout']['path']).read_text().splitlines();need(lines and lines[0]==target+':' and len(lines)>2,'actual exact solink graph edge')
        match=re.fullmatch(r'  input: ((?:[A-Za-z0-9_]+_)?solink)',lines[1]);need(match,'actual product solink rule');rule=match[1]
        if rule not in self.ninja_cache:self.ninja_cache[rule]=self.command([str(self.source/NINJA),'-C',str(self.build),'-t','compdb','-x',rule],'expanded-solink-compdb')
        expanded=self.ninja_cache[rule];entries=[e for e in load(Path(expanded['stdout']['path'])) if e.get('output')==target]
        need(len(entries)==1 and Path(entries[0]['directory'])==self.build,'one actual expanded original solink output')
        words=argv(entries[0]);need(words.count('--')==1,'actual original shared-library wrapper delimiter');driver=words[words.index('--')+1:]
        need(driver and Path(driver[0]).name in ('clang','clang++') and '-shared' in driver,'actual compiler driver is retained DATA only')
        return dict(linked_output=self.copy(self.build/target),linked_output_logical=str(self.build/target),ninja_target=target,
            link=dict(raw_query=query,expanded_compdb_query=expanded,ninja_binary=self.copy(self.source/NINJA),
                ninja_invoked_path=str(self.source/NINJA),ninja_resolved_path=str((self.source/NINJA).resolve()),
                grammar_sources={s:self.copy(self.source/s) for s in GRAMMAR},generated_rule=self.rule_files[rule],
                expanded_argv=driver,effective_CFI=cfi(driver),link_ninja_log_line=self.log_line(target)))

    def usb(self,libraries):
        units={}
        for name in sorted(USB_NAMES):
            need(name in libraries,'real normal MTP DSO must be present')
            driver=libraries[name]['link']['expanded_argv'];wanted={}
            for entry in self.database:
                words=argv(entry)
                if words.count('-o')!=1:continue
                obj=Path(words[words.index('-o')+1]);obj=obj if obj.is_absolute() else self.build/obj
                token=str(obj.relative_to(self.build))
                if token not in driver and str(obj) not in driver:continue
                source=(Path(entry['directory'])/entry['file']).resolve()
                need(source.is_relative_to(self.source),'actual product source root')
                logical=str(source.relative_to(self.source));wanted[logical]=self.unit(logical)
            direct={str((Path(v) if Path(v).is_absolute() else self.build/v).resolve()) for v in driver if v.endswith('.o')}
            need(wanted and {u['object_logical'] for u in wanted.values()}==direct,'all and only direct full compiler TUs consumed by original solink')
            units[name]=wanted
        variant={'arm64_virt':('arm64_virt','arm64','Image'),'armv7a_virt':('arm_virt','arm','zImage'),
                 'x86_64_virt':('x86_64_virt','x86_64','bzImage')}[self.product]
        object_dir,config_arch,kernel=variant
        k=dict(config=self.copy(self.source/'out/kernel/OBJ'/object_dir/'.config'),
            image=self.copy(self.build/'packages/phone/images'/kernel),
            source_defconfig=self.copy(self.source/('device/qemu/common/virt_full/kernel/'+config_arch+'_virt_defconfig')),
            normal_build_log=self.ninja_log)
        return dict(translation_units=units,kernel=k)

    def all_direct_units(self,item):
        driver=item['link']['expanded_argv'];wanted={}
        direct={str((Path(v) if Path(v).is_absolute() else self.build/v).resolve()) for v in driver if v.endswith('.o')}
        for entry in self.database:
            words=argv(entry)
            if words.count('-o')!=1:continue
            obj=(Path(entry['directory'])/words[words.index('-o')+1]).resolve()
            if str(obj) not in direct:continue
            source=(Path(entry['directory'])/entry['file']).resolve()
            need(source.is_relative_to(self.source),'all normal provider compiler TUs remain source-bound')
            logical=str(source.relative_to(self.source));wanted[logical]=self.unit(logical,entry=entry)
        need(wanted and {u['object_logical'] for u in wanted.values()}==direct,'all actual direct DSO compiler TUs and full deps')
        return wanted

    def providers(self):
        closure=set(self.primary['media579_dependency_closure']);original15=set(self.primary['media579_original15'])
        staged={}
        for row in self.primary['files']:
            if row['soname'] not in closure or row['symlink'] or '/module/arkts/' in row['path']:continue
            need(row['soname'] not in staged,'one installed complete provider dependency SONAME')
            staged[row['soname']]=row
        need(set(staged)==closure,'complete actual installed CPU dependency closure')
        compiled={};prebuilt={}
        abi={'arm64_virt':'arm64-v8a','armv7a_virt':'armeabi-v7a','x86_64_virt':'x86_64'}[self.product]
        for name in sorted(closure-original15):
            row=staged[name]
            if name in CPU_PREBUILT_NAMES:
                source=self.source/CPU_ROOT/'prebuilt'/abi/name
                need(sha(source)==row['sha256'],'actual normal prebuilt source bytes equal installed selected ABI')
                candidates=[t for t,r in self.targets if Path(t).name==name and not t.startswith('lib.unstripped/') and (self.build/t).is_file() and sha(self.build/t)==row['sha256']]
                need(candidates,'actual normal product copy target for original prebuilt')
                queries=[]
                for target in candidates:
                    queries.append(dict(target=target,query=self.command([str(self.source/NINJA),'-C',str(self.build),'-t','query',target],'cpu-prebuilt-copy-query'),log_line=self.log_line(target)))
                prebuilt[name]=dict(staged=row,source=self.copy(source),source_logical=str(source),copy_targets=queries,dependency_manifest=self.copy(self.source/CPU_ROOT/'DEPENDENCIES.json'),normal_source_prebuilt_not_source_compile=not (abi=='armeabi-v7a' and name=='libsherpa-onnx-c-api.so'))
            else:
                item=dict(staged=row,**self.link(name,row));item['translation_units']=self.all_direct_units(item);compiled[name]=item
        # Actual external CMake archive, every real full TU/object/dependency and
        # command remain distinct from the enclosing product GN solink receipt.
        targets=[t for t,r in self.targets if t.endswith('/openal/BUILD.json')]
        need(len(targets)==1,'one fixed normal OpenAL action build receipt')
        external=load(self.build/targets[0]);need(external['status']=='complete' and external['normal_product_build'] is True,'normal external HRTF product production completed')
        def retain(value):
            if type(value) is dict:
                if 'path' in value and 'sha256' in value and Path(value['path']).is_absolute() and Path(value['path']).is_relative_to(self.source):
                    copied=self.copy(Path(value['path']));need(copied['sha256']==value['sha256'],'full normal external source/out provenance bytes');return copied
                return {k:retain(v) for k,v in value.items()}
            if type(value) is list:return [retain(v) for v in value]
            return value
        external=retain(external)
        need(external['translation_units'] and all(u['effective_CFI'] for u in external['translation_units']),'every actual HRTF TU CFI')
        arm32=None
        if abi=='armeabi-v7a':
            arm32_original=self.source/CPU_ROOT/'prebuilt/armeabi-v7a/BUILD.json'
            arm32=retain(load(arm32_original));need(arm32['status']=='actual_normal_ARM32_compile_link_ONLY','real ARM32 source C API production required')
            arm32['original_build']=self.copy(arm32_original)
        cpu=dict(prebuilt=prebuilt,compiled=compiled,installed_dependency_closure=sorted(closure),original15=sorted(original15),
            source_audio={Path(n).name:self.copy(self.source/n) for n in CPU_SOURCE_AUDIO},openal_build=external,
            openal_build_original=self.copy(self.build/targets[0]),source_input=self.copy(self.source/CPU_ROOT/'assets/INPUTS.json'),arm32_source_build=arm32)
        name='libnetsys_native_manager.z.so';need(name in compiled,'separate normal phone native DSO source proof')
        return cpu,dict(translation_units={name:compiled[name]['translation_units']},libraries={name:compiled[name]},
            normal_source_root=TELEPHONY_NATIVE_ROOT,source_refs={n:self.copy(self.source/(TELEPHONY_NATIVE_ROOT+'/'+n)) for n in ('src/qemu_modem_tun.cpp','src/netsys_native_service.cpp','BUILD.gn','include/qemu_modem_tun.h')},runtime_pass=False)

    def number_permission(self):
        archive=self.primary['number580_archive']
        need(archive['source_commit']==self.commit and
             archive['actual_package_manifest_sha256']==self.primary['actual_package_manifest']['sha256'],
             'same original archive/commit/manifest for actual Number sources')
        result=dict(schema='number580-actual-source-compile-export/v1',source_commit=self.commit,
            archive_sha256=archive['archive']['sha256'],product=self.product,device=self.primary['device'],
            source_ro=True,out_ro=True,source_root=str(self.source),sources={},compile_units=[],libraries={},
            installed_dependency_closure=[],runtime_pass=False,first_artifact_behavior_gate_passed=False,
            image_report_attached=False,same_archive_image_binding_still_required=True)
        if self.primary['device']!='phone':
            need(self.primary['device']=='2in1','fixed Number phone/2in1 product context')
            need(not self.primary['number580_dependency_closure'] and not self.primary['number580_roots'],
                 'unselected Number profile cannot borrow phone source/compile receipts')
            result['profile_disposition']='not_applicable_to_original_phone_Number_subset'
            return result
        need(set(self.primary['number580_roots'])==NUMBER580_ROOTS,'all three normal Number image library roots')
        closure=set(self.primary['number580_dependency_closure'])
        edges=self.primary['number580_dependency_edges']
        need(NUMBER580_ROOTS<=closure and set(edges)==closure and
             all(set(values)<=closure for values in edges.values()),'complete actual Number DT_NEEDED closure')
        staged={};aliases={}
        for row in self.primary['files']:
            name=row['soname']
            if name not in closure or row['symlink'] or '/module/arkts/' in row['path']:continue
            if name in staged:
                need((staged[name]['sha256'],staged[name]['bytes'])==(row['sha256'],row['bytes']),
                     'ambiguous installed Number dependency bytes')
            else:staged[name]=row
            aliases.setdefault(name,[]).append(row)
        need(set(staged)==closure,'every actual installed Number dependency full file')
        result['sources']={role:self.copy(self.source/logical) for role,logical in NUMBER580_SOURCES.items()}
        need(result['sources']['number_napi']['sha256']==NUMBER580_NAPI_SHA256,
             'actual Number NAPI must be the complete public201 product postimage')
        heads={}
        for project in ('base/telephony/number_identity','base/telephony/core_service'):
            query=self.command(['git','-C',str(self.source/project),'rev-parse','HEAD'],'number-permission-project-head')
            value=Path(query['stdout']['path']).read_text().strip()
            need(re.fullmatch('[a-f0-9]{40}',value),'actual Number/Core project commit')
            if project=='base/telephony/number_identity':need(value==NUMBER580_PROJECT_REVISION,'fixed Number50e project')
            heads[project]=dict(commit=value,query=query)
        result['actual_project_heads']=heads
        wanted={NUMBER580_SOURCES[role]:role for role in NUMBER580_TUS}
        entries={}
        for entry in self.database:
            logical_source=(Path(entry['directory'])/entry['file']).resolve()
            if not logical_source.is_relative_to(self.source):continue
            logical=str(logical_source.relative_to(self.source))
            if logical not in wanted:continue
            words=argv(entry)
            need(words.count('-o')==1 and '-c' in words,'complete Number source compiler DATA')
            obj=Path(words[words.index('-o')+1]);obj=obj if obj.is_absolute() else self.build/obj
            obj=obj.resolve();need(obj.is_relative_to(self.build),'actual Number object remains in selected product')
            need(str(obj) not in entries,'one exact compiler entry per actual Number object')
            entries[str(obj)]=(logical,wanted[logical],entry)
        need({item[1] for item in entries.values()}==set(NUMBER580_TUS),'actual NAPI/mark/Core conversion TUs required')
        found=set()
        for name,row in sorted(staged.items()):
            candidates=[target for target,rule in self.targets if re.fullmatch(r'(?:[A-Za-z0-9_]+_)?solink',rule) and
                Path(target).name==name and not target.startswith(('lib.unstripped/','./lib.unstripped/')) and
                (self.build/target).is_file() and sha(self.build/target)==row['sha256']]
            if not candidates:continue
            item=dict(staged=row,staged_aliases=aliases[name],installed_file=self.copy(Path(row['path'])),**self.link(name,row))
            direct={str((Path(token) if Path(token).is_absolute() else self.build/token).resolve())
                    for token in item['link']['expanded_argv'] if token.endswith('.o')}
            owned=sorted(direct&set(entries))
            if not owned:continue
            item['permission_translation_units']=[]
            for obj in owned:
                logical,role,entry=entries[obj];unit=self.unit(logical,entry=entry)
                need(unit['effective_CFI'] and item['link']['effective_CFI'],
                     'original Number permission TU and owning link CFI required')
                dependency_text=Path(unit['dependency_file']['path']).read_text().splitlines()
                paths=[line[4:] for line in dependency_text[1:] if line.startswith('    ')]
                dependencies=[];by_logical={};bindings=[]
                for token in paths:
                    path=(self.build/token).resolve()
                    need(path.is_relative_to(self.source),'all actual Number compiler dependencies remain source/out bound')
                    logical_dependency=str(path.relative_to(self.source));copied=self.copy(self.source/logical_dependency)
                    dependencies.append(copied);by_logical[logical_dependency]=copied
                    bindings.append(dict(token=token,logical=logical_dependency,file=copied))
                for required_role in NUMBER580_DEPENDENCIES[role]:
                    required=NUMBER580_SOURCES[required_role]
                    need(by_logical.get(required)==result['sources'][required_role],
                         'actual Number TU dependency does not bind exact current source/header: '+required_role)
                record=dict(role=role,source_logical=logical,owning_soname=name,unit=unit,
                    compiler_dependencies=dependencies,dependency_sources=by_logical,dependency_bindings=bindings,
                    owning_staged_sha256=row['sha256'],scope='actual objects/valid Ninja deps/completed log and original command DATA; no fabricated compiler exit summary')
                item['permission_translation_units'].append(record)
                result['compile_units'].append(record);found.add((role,name))
            result['libraries'][name]=item
        need(('number_napi','libnumberidentity.z.so') in found and
             ('mark_ability','libnumber_identity.z.so') in found and any(role=='core_util' for role,name in found),
             'actual public NAPI, provider mark and linked Core conversion object owners required')
        result['installed_dependency_closure']=[dict(soname=name,needed=edges[name],staged=staged[name],
            staged_aliases=aliases[name],file=self.copy(Path(staged[name]['path']))) for name in sorted(closure)]
        result['complete_compile_commands']=self.compile_query['stdout']
        result['complete_compile_query']=self.compile_query
        result['complete_ninja_log']=self.ninja_log
        result['actual_graph_targets']=self.targets_query
        result['profile_disposition']='actual_original_phone_Number_source_compile_dependency_export'
        return result

    def save(self,status):
        value=dict(schema='media579-actual-product-RO-raw/v1',status=status,source_commit=self.commit,product=self.product,
            device=self.primary['device'],source_root=str(self.source),build_directory=str(self.build),source_ro=True,out_ro=True,
            original_primary=ref(Path('/evidence/native-export/installed-runtime-export.json')),files=self.files,commands=self.commands,
            original_source_observations=self.before,source_tree_inventories=self.observations,failures=getattr(self,'failures',[]),runtime_pass=False)
        value.update(getattr(self,'result',{}))
        (self.output/'RAW.json').write_text(json.dumps(value,indent=2)+'\n')

    def collect(self):
        for tree in (*SOURCE_TREES,*USB_TREES):self.tree(tree)
        for name in (*GRAMMAR,*AUDIO_SOURCES,*MIDI_HEADERS,*USB_SOURCES):self.copy(self.source/name)
        self.ninja_ref=self.copy(self.source/NINJA)
        revision=self.command(['git','-C',str(self.source/GFX.rstrip('/')),'rev-parse','HEAD'],'graphic-project-revision')
        self.graph();units={s:self.unit(s) for s in TUS}
        number_permission=self.number_permission()
        # Every actual permission object is exported for the same source-bound
        # HAP full-token check; do not infer eligibility from the root macro.
        permission=[]
        for entry in self.database:
            if (Path(entry['directory'])/entry['file']).resolve()!=self.source/AUDIO_PERMISSION:continue
            words=argv(entry);target=Path(words[words.index('-o')+1]);target=target if target.is_absolute() else self.build/target
            if target.is_file():
                self.log_line(str(target.relative_to(self.build)));permission.append(self.copy(target))
        need(permission,'actual selected-product permission objects required')
        registrations={}
        for symbol,parts in PLUGINS.items():
            uid,registration,translation,gn,name=parts
            registrations[symbol]=dict(uid_source=dict(logical=GFX+uid,file=self.copy(self.source/(GFX+uid))),
                registration_source=dict(logical=GFX+registration,file=self.copy(self.source/(GFX+registration))),
                translation_source=dict(logical=GFX+translation,file=self.copy(self.source/(GFX+translation))),
                build_gn=dict(logical=GFX+gn,file=self.copy(self.source/(GFX+gn))),soname=name)
        # A disabled optional PNG/JPEG source still exists. Only real compile
        # entries get object/deps; the pure assembler chooses the real closure.
        for symbol,node in registrations.items():
            matches=[e for e in self.database if (Path(e['directory'])/e['file']).resolve()==self.source/node['translation_source']['logical']]
            if matches:node['actual_unit']=self.unit(node['translation_source']['logical'])
        staged={}
        for row in self.primary['files']:
            name=row['soname']
            if name not in MEDIA_NAMES or row['symlink'] or '/module/arkts/' in row['path']:continue
            need(name not in staged,'one actual staged Media SONAME');staged[name]=row
        need('libohmidi.so' in staged and 'libAGPDLL.z.so' in staged and len({'libscene.so','libscene.z.so'}&staged.keys())==1,'real staged MIDI, Scene and core required')
        libraries={}
        for name,row in sorted(staged.items()):
            libraries[name]=dict(staged=row,**self.link(name,row))
        usb=self.usb(libraries)
        cpu_provider,telephony_native=self.providers()
        voice={};configs=[];inventory=[]
        for partition,member in [('vendor','/etc/init.virt.usb.cfg'),('system','/app/com.usb.right/usb_right_dialog.hap')]:
            p=self.build/'packages/phone'/partition/member.lstrip('/')
            configs.append(dict(partition=partition,image_member=member,staged=self.copy(p),staged_logical=str(p)))
        for partition in PARTITIONS:
            root=self.build/'packages/phone'/partition
            if not root.is_dir():continue
            entries=[];dso_entries=[];all_files=[];directory_links=[]
            for folder,dirs,files in os.walk(root,followlinks=False):
                for name in dirs:
                    p=Path(folder)/name
                    if p.is_symlink():directory_links.append(dict(member='/'+str(p.relative_to(root)),link=os.readlink(p)))
                dirs[:]=sorted(d for d in dirs if not (Path(folder)/d).is_symlink())
                for name in sorted(files):
                    p=Path(folder)/name;info=p.lstat();relative=str(p.relative_to(root))
                    all_files.append(dict(member='/'+relative,mode=stat.S_IMODE(info.st_mode),bytes=info.st_size,symlink=p.is_symlink(),
                        link=os.readlink(p) if p.is_symlink() else None))
                    if re.fullmatch(r'lib[A-Za-z0-9_.+\-]+\.so(?:\.[0-9]+)*',name):
                        dso_entries.append(dict(member='/'+relative,mode=stat.S_IMODE(info.st_mode),symlink=p.is_symlink(),bytes=info.st_size,
                            link=os.readlink(p) if p.is_symlink() else None,sha256=sha(p) if p.is_file() and not p.is_symlink() else None))
                    if any(token in name.lower() for token in ('audio_effect','spatial','intell_voice','voice_engine','wakeword','wakeup','enroll')):
                        entries.append(dict(member='/'+relative,mode=stat.S_IMODE(info.st_mode),symlink=p.is_symlink(),bytes=info.st_size,
                            link=os.readlink(p) if p.is_symlink() else None))
                        if p.is_file() and not p.is_symlink() and (p.suffix in ('.xml','.json','.cfg','.conf','.hcs','.bin') or name in IV_NAMES):
                            descriptor=self.copy(p);configs.append(dict(partition=partition,image_member='/'+relative,staged=descriptor,staged_logical=str(p)))
                            if name in IV_NAMES:
                                voice[name]=dict(staged=descriptor,partition=partition,image_member='/'+relative,**self.link(name,descriptor))
            inventory.append(dict(partition=partition,root=str(root),complete_walk=True,selected_name_grammar=['audio_effect','spatial','intell_voice','voice_engine','wakeword','wakeup','enroll'],entries=entries,
                complete_DSO_inventory=dso_entries,complete_file_inventory=all_files,directory_links=directory_links))
        need(set(voice)==IV_NAMES,'actual vendor IntelligentVoice engine full source/link required; absence is unresolved')
        for name,item in voice.items():
            driver=item['link']['expanded_argv'];actual_units={}
            for entry in self.database:
                physical=(Path(entry['directory'])/entry['file']).resolve()
                if not physical.is_relative_to(self.source/IV_ENGINE_ROOT):continue
                words=argv(entry);target=Path(words[words.index('-o')+1]);target=target if target.is_absolute() else self.build/target
                if str(target) in driver or str(target.relative_to(self.build)) in driver:
                    logical=str(physical.relative_to(self.source));actual_units[logical]=self.unit(logical)
            need(actual_units,'actual vendor engine full source compile objects consumed by real solink')
            item['translation_units']=actual_units
        for asset in CPU_IMAGE_ASSETS:
            p=self.build/'packages/phone/vendor/etc/intelligent_voice/cpu'/asset
            configs.append(dict(partition='vendor',image_member='/etc/intelligent_voice/cpu/'+asset,staged=self.copy(p),staged_logical=str(p)))
        for partition,member in [('system','/etc/init/netsysnative.cfg'),('system','/profile/netsysnative.json'),('system','/etc/audio/qemu_spatial/OPENAL-NOTICES.txt')]:
            p=self.build/'packages/phone'/partition/member.lstrip('/')
            configs.append(dict(partition=partition,image_member=member,staged=self.copy(p),staged_logical=str(p)))
        self.result=dict(complete_compile_commands=self.compile_query['stdout'],complete_compile_query=self.compile_query,
            complete_compile_rules=self.compile_rules,complete_ninja_log=self.ninja_log,graph_inventory=self.graph_inventory,
            actual_graph_targets=self.targets_query,translation_units=units,plugin_source_map=registrations,libraries=libraries,
            project_revision_query=revision,permission_objects=permission,cpu_provider=cpu_provider,telephony_native=telephony_native,voice_engine=voice,configuration_files=configs,provider_inventory=inventory,usb=usb,number_permission580=number_permission)
        self.failures=[];self.save('complete')
        # Source/out always remained RO. Check every retained input again.
        for logical,row in self.before.items():need(sha(self.regular(self.source/logical))==row['sha256'],'actual source/out changed during export')
        return ref(self.output/'RAW.json')


def append_media_facts():
    collector=Collector()
    try:return collector.collect()
    except BaseException as error:
        collector.failures=[dict(type=type(error).__name__,error=str(error))];collector.save('failed');raise
