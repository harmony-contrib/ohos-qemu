"""Actual ARM32 C compile/recheck/ELF/image inputs; no tools are executed here.

Root must retain the real normal executable and actual installed DSOs along
with the fixed three-helper build. Missing artifacts never become readiness.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib,importlib.util,json,posixpath,re,shlex,stat,struct,sys,tarfile

CANONICAL=Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/ci/capability-audit')
BUILDER_SHA='9c4db163b28e934bb41c7e19806d71b25a9c230cd048ba1d7b6c1a31f1d94ead'
CONTEXT_SHA='779eaf2980765daaa14b9325dda1f39cc69451697b6f79cd2f33c7a8f4b1e943'
SOURCE_SHA={'audio_global579_af': '4a28bd721db126fb4f376731a95fae88c6f6fd66b7ff4571886ccc01df9bfa0d',
 'audio_global579_control': '7e7f4216eefbedfe4b362020e2ec9c1042c415b7580401c59f00ab5852600bf1',
 'audio_global579_status': 'cc62775b775d67a4928bc329c8f8f921b8ae78d31a5b59e68edeb30a253894fe'}
HEADER_SHA={'audio_onset580_wire.h': 'c5e500563cbfc36a66e027ff8f8ca234d8053cc61607778a660348a4d8bba1a4',
 'control_global579_core.h': '230cac9a9044a2c3a2b23dca77ab6612cb42c9dabb2ad03d2ed3ae39bb07a428',
 'media598_wire.h': '8d6957da5dbce30a31ed4aedb5224e4a51e0d25de73564bcbc70871e36899dc3',
 'onset579_clock_domain.h': 'd905aabdbbc46ed8e7fb16492626a52327126de7c8088f29867d6ac5cf05fe36',
 'onset579_kernel_clock_review.h': '122ac852dff2761b88c1bce8e18767572f7ca2eb3d9ce47f844bfe1ca749b739'}
NAMES=('audio_global579_control','audio_global579_status','audio_global579_af')
FIXTURES=dict(zip(NAMES,('control_global579.c','pcm_status_global579.c','audio_onset_global579.c')))
BUILD_ORIGIN=Path('/arm32-onset579-output/build')
RECHECK_ORIGIN=Path('/arm32-onset579-recheck/recheck')
VIRTUAL_KIT=Path('/arm32-onset579-kit')

def need(ok,message):
    if not ok:raise ValueError(message)

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def regular(path):
    p=Path(path)
    need(p.is_absolute() and p.resolve()==p and not any(n.is_symlink() for n in (p,*p.parents)),
         'one canonical actual artifact')
    st=p.stat();need(stat.S_ISREG(st.st_mode) and st.st_nlink==1,'single ordinary actual artifact')
    return p

def record(path):
    p=regular(path);return dict(path=str(p),sha256=digest(p),bytes=p.stat().st_size)

def checked(row):
    need(type(row) is dict and set(row) in ({'path','sha256'},{'path','sha256','bytes'}) and
         re.fullmatch('[a-f0-9]{64}',row.get('sha256','')) is not None,'actual Ref2/Ref3 required')
    p=regular(row['path']);need(digest(p)==row['sha256'] and ('bytes' not in row or
         type(row['bytes']) is int and row['bytes']==p.stat().st_size),'actual raw artifact bytes differ')
    return p

def decode(path):
    def unique(rows):
        out={}
        for k,v in rows:
            need(k not in out,'duplicate actual raw key');out[k]=v
        return out
    return json.loads(regular(path).read_text(),object_pairs_hook=unique,
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite raw value')))

def product_module():
    path=CANONICAL/'batch_system_build_runtime_helpers.py'
    need(type(BUILDER_SHA) is str and digest(regular(path))==BUILDER_SHA,
         'the reviewed generic-port plus finite global-C Builder must be adopted first')
    name='fixed_arm32_global579_product_builder'
    if name in sys.modules:
        value=sys.modules[name]
        need(Path(value.__file__)==path and digest(path)==BUILDER_SHA,'foreign cached global Builder')
        return value
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec)
    sys.modules[name]=value
    try:spec.loader.exec_module(value)
    except BaseException:sys.modules.pop(name,None);raise
    return value

def relocate(path,origin,directory):
    p=Path(path)
    need(p.is_absolute() and '..' not in p.parts,'canonical original artifact identity')
    relative=p.relative_to(origin);need(relative.parts,'actual private artifact below exact origin')
    return regular(Path(directory)/relative)

def command_table(report,origin,directory):
    need(type(report.get('commands')) is list and report['commands'],'actual raw command ledger')
    out={}
    for row in report['commands']:
        need(type(row['exit_code']) is int and row['exit_code']==0 and row.get('timed_out',False) is False and
             type(row['argv']) is list and row['argv'] and all(type(v) is str for v in row['argv']) and
             row['label'] not in out,'successful unique actual native build command')
        log=relocate(row['log'],origin,directory)
        need(digest(log)==row['sha256'],'actual native raw log changed')
        out[row['label']]=(row,log)
    return out

def needed_from_elf(path):
    return product_module().elf_needed(regular(path),product='armv7a_virt')


def artifact_context_module():
    product_module()
    path=CANONICAL/'native579_artifact_context.py'
    need(digest(regular(path))==CONTEXT_SHA,'fixed actual native context reader changed')
    name='fixed_global579_actual_native_context'
    if name in sys.modules:
        value=sys.modules[name];need(Path(value.__file__)==path,'foreign cached actual context reader');return value
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec)
    sys.modules[name]=value
    try:spec.loader.exec_module(value)
    except BaseException:sys.modules.pop(name,None);raise
    need(Path(value.product.__file__)==CANONICAL/'batch_system_build_runtime_helpers.py' and
         digest(value.product.__file__)==BUILDER_SHA,'actual normal parser uses the same admitted Builder')
    return value


def literal_link_inputs(text,build):
    """Original strict complete LLD -t grammar; no /ohos host file probes."""
    result=set()
    for line in re.sub(r'\x1b\[[0-9;]*m','',text).splitlines():
        word=line.strip()
        if not word:continue
        match=re.fullmatch(r'([A-Za-z0-9_./+:-]+)(?:\([^()\r\n]+\))?',word)
        need(match is not None,'unknown/malformed actual linker trace row')
        word=match[1]
        result.add(Path(posixpath.normpath(word if word.startswith('/') else posixpath.join(str(build),word))))
    need(result,'actual linker opened-input trace absent')
    return result

def image_witness(build,commands,directory,profile,product,profile_path):
    witness=build['installed_runtime_image_proof']
    need(set(witness)=={'archive_members','tools','dsos'},'complete original image re-extraction proof')
    originals={name:profile[name+'_image'] for name in ('system','vendor')}
    originals['manifest']=profile['package_manifest']
    expected={name:{key:row[key] for key in ('archive_member','sha256','bytes')} for name,row in originals.items()}
    need(witness['archive_members']==expected and set(witness['dsos'])==set(profile['dsos']),
         'complete exact profile-v2 archive images/manifest/installed inventory')
    archive=relocate(profile['archive']['path'],Path('/runtime-profile'),profile_path.parent);need(digest(archive)==profile['archive']['sha256'] and
        archive.stat().st_size==profile['archive']['bytes'],'actual original new archive bytes')
    wanted={row['archive_member']:row for row in originals.values()};seen=set()
    with tarfile.open(archive,'r:*') as stream:
        for member in stream:
            if member.name not in wanted:continue
            row=wanted[member.name];need(member.isfile() and member.name not in seen and member.size==row['bytes'],
                'one real regular archive image/manifest member');seen.add(member.name)
            source=stream.extractfile(member);need(source is not None,'actual archive member stream')
            h=hashlib.sha256();length=0;manifest=[]
            with source:
                for block in iter(lambda:source.read(1024*1024),b''):
                    h.update(block);length+=len(block)
                    if member.name==profile['package_manifest']['archive_member']:
                        need(length<=4*1024*1024,'bounded complete actual package manifest');manifest.append(block)
            need(h.hexdigest()==row['sha256'] and length==row['bytes'],'full actual archive image/manifest differs')
            if member.name==profile['package_manifest']['archive_member']:
                need(json.loads(b''.join(manifest))==profile['package_metadata'],'actual entire package manifest/metadata differs')
        need(seen==set(wanted),'actual new archive is missing required members')
    extraction=witness['tools'];need(set(extraction)=={'debugfs','extractor','selector'},'original finite extraction tools')
    for key,name in (('extractor','ext_image_entries.py'),('selector','verify_alsa_config_image.py')):
        path=CANONICAL.parents[1]/'scripts'/name;row=extraction[key]
        expected=dict(record(path),path=str(VIRTUAL_KIT/'scripts'/name))
        need(expected==row and build['inputs'].get(row['path'])==row,'original canonical image extractor source')
    need(build['inputs'].get(extraction['debugfs']['path'])==extraction['debugfs'],'actual image tool input hash')
    prefix=product.installed_prefix(profile)+'/'
    for soname,entry in profile['dsos'].items():
        row=witness['dsos'][soname];actual=relocate(row['path'],BUILD_ORIGIN,directory)
        staged=entry['staged'];need(staged['path'].startswith(prefix),'actual installed staging root')
        partition=staged['path'][len(prefix):].split('/',1)[0]
        need(partition in ('system','vendor') and row['partition']==partition and row['image_path']==entry['image_member'] and
             row['image_path_aliases']==[entry['image_member']] and type(row['image_inode']) is int and row['image_inode']>0 and
             digest(actual)==row['sha256']==staged['sha256'] and actual.stat().st_size==row['bytes']==staged['bytes'] and
             product.elf_soname(actual,product='armv7a_virt')==soname,'actual full installed image DSO/inode/ABI/SONAME')
        command,raw=commands['installed-runtime-stat-'+soname]
        need(type(row['stat_command']) is int and build['commands'][row['stat_command']]==command and
             command['argv']==[extraction['debugfs']['path'],'-R','stat '+entry['image_member'],profile[partition+'_image']['path']] and
             re.search(r'(?m)^Inode: '+str(row['image_inode'])+r'\s+Type: regular\s',raw.read_text()),
             'actual original image raw stat command/inode differs')

@dataclass(frozen=True)
class AdmittedGlobalTools579:
    control:Path
    status:Path
    af:Path
    profile:dict
    tools:dict
    af_tool:dict
    evidence:dict

def admit(proof,*,profile_descriptor,archive_sha256,domain):
    from onset579_global_clock import require_domain
    require_domain(domain)
    need(type(proof) is dict and set(proof)=={'schema','build','recheck','dsos','production','abi_reference'} and
         proof['schema']=='actual-arm32-global-clock-native579/v2','complete actual global native proof')
    need(domain.mode=='kernel_global_monotonic' and domain.kernel.product=='armv7a_virt' and
         domain.kernel.archive_sha256==archive_sha256,'original package kernel admission first')
    product=product_module()
    bp=checked(proof['build']);rp=checked(proof['recheck']);xp=checked(proof['dsos'])
    build=decode(bp);review=decode(rp);exports=decode(xp);production=decode(checked(proof['production']))
    profile=decode(checked(profile_descriptor));product.validate_installed_profile(profile,archive_sha256=archive_sha256)
    need(profile['schema_version']==2 and profile['product']=='armv7a_virt' and profile['device'] in ('phone','2in1'),
         'actual ARM32 profile-v2 package metadata, not a renamed ARM64 profile')
    for value in (build,review):
        need(value['status']=='pass_compile_link_ONLY' and value['plan_only'] is False and
             value['product']=='armv7a_virt' and value['source_root']=='/ohos' and
             value['build_directory']=='/ohos/out/armv7a_virt' and value['changed_inputs']==[] and
             value['builder_sha256']==BUILDER_SHA and set(value['helpers'])==set(NAMES) and
             value['requirements_closed']==0 and value['first_artifact_behavior_gate_passed'] is False,
             'actual finite compile/recheck scope and ABI gate')
    need(production['exit_code']==0 and production['cleanup_verified'] is True and
         production['archive_sha256']==archive_sha256 and production['build']==proof['build'] and
         production['recheck']==proof['recheck'] and production['dsos']==proof['dsos'],
         'same original Owner actual closed production receipt required')
    expected_profile=dict(path='/runtime-profile/runtime-profile.json',sha256=profile_descriptor['sha256'],
                          bytes=checked(profile_descriptor).stat().st_size)
    need(build['installed_runtime_profile']==dict(source=expected_profile,profile=profile),
         'exact original mounted profile-v2 source, not an unbound path derivation')
    need(review['verify_existing'] is True and review['original_report']['sha256']==proof['build']['sha256'] and
         review['original_report']['rewritten'] is False,'actual immutable original-artifact recheck')
    commands=command_table(build,BUILD_ORIGIN,bp.parent);rechecked=command_table(review,RECHECK_ORIGIN,rp.parent)
    image_witness(build,commands,bp.parent,profile,product,checked(profile_descriptor))
    recipe=CANONICAL/'onset579_global_native.py'
    recipe_expected=dict(record(recipe),path=str(VIRTUAL_KIT/'ci/capability-audit/onset579_global_native.py'))
    need(recipe_expected==build['global_clock579_native_recipe']==review['global_clock579_native_recipe'] and
         build['inputs'].get(recipe_expected['path'])==recipe_expected,
         'fixed finite recipe source must be retained in original input closure')
    from onset579_global_native import CLOCK_SOURCE_PINS,KERNEL_PROJECT,KERNEL_HEAD
    expected_sources={name:dict(path='/ohos/'+name,**row) for name,row in CLOCK_SOURCE_PINS.items()}
    implementation=dict(schema='actual-fixed-clock-implementation579/v1',project='/ohos/'+KERNEL_PROJECT,
        head=KERNEL_HEAD,sources=expected_sources,head_command='global-clock-kernel-HEAD',
        generated_config_admitted=False,package_kernel_admitted=False,held_boot_admitted=False)
    for report in (build,review):
        need(report.get('global_clock579_native_entry')==recipe_expected and
             report.get('clock_implementation579')==implementation and
             all(report['inputs'].get(row['path'])==row for row in expected_sources.values()),
             'complete actual fixed9 source/inner-entry proof; config/package/boot still independently required')
    head_argv=['git','-c','safe.directory=/ohos/'+KERNEL_PROJECT,
        '-C','/ohos/'+KERNEL_PROJECT,'rev-parse','HEAD']
    for table in (commands,rechecked):
        need('global-clock-kernel-HEAD' in table,'actual original reviewed kernel HEAD query absent')
        command,raw=table['global-clock-kernel-HEAD']
        need(command['argv']==head_argv and raw.read_text()==KERNEL_HEAD+'\n',
             'actual complete kernel HEAD raw differs from reviewed implementation')
    expected_commands={'installed-runtime-stat-'+name for name in profile['dsos']}
    expected_commands.update(('actual-normal-executable-link-command','global-clock-kernel-HEAD'))
    expected_commands.update(name+suffix for name in NAMES for suffix in ('-0-actual-GN-command','-compile','-link','-actual-ELF-ABI'))
    need(set(commands)==expected_commands and set(rechecked)=={name+'-actual-ELF-ABI' for name in NAMES}|{'global-clock-kernel-HEAD'} and
         all(row['cwd']=='/ohos/out/armv7a_virt' for table in (commands,rechecked) for row,_ in table.values()),
         'finite actual compiler/query/recheck command scope and original cwd')
    need(review['original_input_count']==len(build['inputs']) and len(review['original_commands'])==len(commands),
         'complete immutable original input/command replay')
    seen=set()
    for item in review['original_commands']:
        row=dict(item);verified=row.pop('verified_log');label=row['label']
        need(label not in seen and label in commands and row==commands[label][0] and verified['sha256']==row['sha256'],
             'actual original raw compiler command replay differs');seen.add(label)
    normal=build['normal_link_contract'];need(review['normal_link_contract']==normal,'same actual normal link/CRT contract')
    reference=checked(proof['abi_reference'])
    need(record(reference)['sha256']==normal['binary']['sha256'] and reference.stat().st_size==normal['binary']['bytes'] and
         product.elf_header(reference,executable=True,product='armv7a_virt',interpreter_path=normal['interpreter'])==normal['elf'] and
         product.machine_abi_flags(reference,'armv7a_virt')==normal['machine_abi_flags'],
         'actual normal executable class/loader/full ARM EABI flags')
    query=commands['actual-normal-executable-link-command']
    need(query[0]['argv']==['/ohos/prebuilts/build-tools/linux-x86/bin/ninja','-w','dupbuild=warn','-C',
         '/ohos/out/armv7a_virt','-t','commands','-s',normal['target']] and
         query[1].read_text().splitlines()==[normal['actual_command']],'actual printed normal link command')
    normal_words=shlex.split(normal['actual_command'])
    need(product.compiler_target(normal_words)==normal['compiler_target'] and
         product.abi_options(normal_words)==normal['abi_options'] and product.effective_cfi(normal_words),
         'normal target/float-call ABI/CFI cannot be guessed')
    need([Path(r['path']).name for r in normal['CRT']]==['Scrt1.o','crti.o','crtn.o'] and
         len({str(Path(r['path']).parent) for r in normal['CRT']})==1,'actual normal CRT directory/order')
    tools={};all_needed=set()
    for name in NAMES:
        old,new=build['helpers'][name],review['helpers'][name];origin=BUILD_ORIGIN/name
        binary=relocate(str(origin/name),BUILD_ORIGIN,bp.parent)
        source=relocate(str(origin/FIXTURES[name]),BUILD_ORIGIN,bp.parent)
        need(old['status']==new['status']=='pass_compile_link_ONLY' and old['language']==new['language']=='c' and
             old['actual_C_GN_flags_preserved'] is new['actual_C_GN_flags_preserved'] is True and
             old['runtime_validated'] is new['runtime_validated'] is False and
             digest(source)==old['source']['sha256']==old['private_source_sha256']==SOURCE_SHA[name],
             'actual fresh global C source/language/profile contract')
        expected_source=dict(record(source),path=str(VIRTUAL_KIT/'ci/capability-audit/fixtures/batch_media/audio_global_clock579'/FIXTURES[name]))
        need(old['source']==new['source']==expected_source and build['inputs'].get(expected_source['path'])==expected_source,
             'fixed actual original source input, not only a private copy')
        need(old['installed_runtime_profile']==build['installed_runtime_profile']==new['installed_runtime_profile'] and
             old['installed_runtime_profile']['profile']==profile,'same actual installed profile')
        compile_cmd=old['compile_command'];link=old['link_command']
        product.validate_c_flags(compile_cmd,product='armv7a_virt',actual_target=normal['compiler_target'])
        need(product.abi_options(compile_cmd)==normal['abi_options'] and
             old['CFI_preserved']==new['CFI_preserved']==product.effective_cfi(compile_cmd)==product.effective_cfi(link) and
             '-nostdlib' in link and all(link.count(r['path'])==1 for r in normal['CRT']),
             'actual unchanged C sysroot/LTO/CFI/CRT and float ABI')
        need(compile_cmd==new['compile_command'] and link==new['link_command'] and
             commands[name+'-compile'][0]['argv']==compile_cmd and commands[name+'-link'][0]['argv']==link,
             'actual original compiler/link argv, not report summaries')
        need(product.argument(compile_cmd,'-c')==str(origin/FIXTURES[name]) and
             product.argument(compile_cmd,'-o')==str(origin/(name+'.o')) and
             product.argument(compile_cmd,'-MF')==str(origin/'headers.d') and
             product.argument(link,'-o')==str(origin/name),'fixed actual source/object/dep/output argv')
        anchor,=old['anchors'];q=commands[name+'-0-actual-GN-command']
        need(anchor['object_target']=='obj/third_party/alsa-lib/src/libasound/async.o' and
             anchor['actual_command'] in q[1].read_text().splitlines() and
             product.compile_flags(anchor['actual_command'],Path(compile_cmd[0]),
                 Path('/ohos/third_party/alsa-lib/src/async.c'),Path('/ohos/out/armv7a_virt'))==anchor['flags'] and
             compile_cmd[1:1+len(anchor['flags'])]==anchor['flags'],'actual C GN flags/anchor query')
        need(compile_cmd[0]==link[0]=='/ohos/prebuilts/clang/ohos/linux-x86_64/llvm/bin/clang' and
             product.compiler_target(compile_cmd)==normal['compiler_target'] and
             product.effective_cfi(anchor['flags'])==old['CFI_preserved']==new['CFI_preserved'] and
             product.effective_cfi(anchor['ldflags'])==product.effective_cfi(link),
             'actual original C compiler/target/selected CFI unchanged')
        includes=anchor['include_dirs'];flags=list(anchor['flags'])+[word for word in includes if word not in anchor['flags']]
        expected_compile=[compile_cmd[0],*flags,'-fPIE','-MD','-MF',str(origin/'headers.d'),'-c',str(origin/FIXTURES[name]),'-o',str(origin/(name+'.o'))]
        need(compile_cmd==expected_compile,'exact original C flags/private source compile command')
        ld,removed=product.link_flags(anchor['ldflags'],origin)
        need(old['removed_component_DSO_only_export_maps']==removed and anchor['selected_shared_dependencies']==[] and
             old['linked_libraries']==[],'no added or hidden GN/component library dependency')
        crt=[row['path'] for row in normal['CRT']]
        expected_link=[compile_cmd[0],*ld,'-pie','-Wl,--export-dynamic','-Wl,--threads=2','-o',str(origin/name),
            *crt[:-1],'-Wl,-t','-Wl,--start-group',str(origin/(name+'.o')),
            *product.replace_runtime_libraries(anchor['libs'],profile),'-Wl,--end-group',crt[-1]]
        need(link==expected_link,'exact retained actual C GN/LTO/CFI/CRT/runtime link command')
        def actual_artifact(ref):
            need(type(ref) is dict and set(ref) in ({'path','sha256'},{'path','sha256','bytes'}),'actual retained normal/profile Ref')
            path=relocate(ref['path'],BUILD_ORIGIN,bp.parent)
            need(digest(path)==ref['sha256'] and ('bytes' not in ref or path.stat().st_size==ref['bytes']),'actual retained normal/profile bytes changed')
            return path
        context=artifact_context_module().binding_context(build,old,binary,actual_artifact)
        need(context['product']=='armv7a_virt' and context['normal']==normal,'same actual independently rebuilt normal target')
        guard=relocate(str(origin/'actual_system_abi.h'),BUILD_ORIGIN,bp.parent)
        need(guard.read_text()==product.C_ABI_GUARD and digest(guard)==old['abi_guard_sha256'],
             'actual C guard unchanged; no C++ ABI substitution')
        need(set(old['private_global_clock_headers'])==set(new['private_global_clock_headers'])==set(HEADER_SHA),
             'complete copied native header closure')
        for filename,digest_ in HEADER_SHA.items():
            header=relocate(str(origin/filename),BUILD_ORIGIN,bp.parent)
            header_input=old['private_global_clock_headers'][filename]
            need(header_input['path']==str(VIRTUAL_KIT/'ci/capability-audit/fixtures/batch_media/audio_global_clock579'/filename) and
                 build['inputs'].get(header_input['path'])==header_input,'fixed header input absent from original closure')
            need(digest(header)==old['private_global_clock_headers'][filename]['sha256']==digest_ and
                 old['private_global_clock_headers'][filename]==new['private_global_clock_headers'][filename],
                 'actual global header/review/wire bytes changed')
        dependencies=old['actual_compiler_dependencies']
        need(dependencies==new['actual_compiler_dependencies'] and dependencies and
             digest(relocate(str(origin/'headers.d'),BUILD_ORIGIN,bp.parent))==old['depfile_sha256'],
             'complete original compiler depfile/header replay')
        for dep in dependencies:
            path=Path(dep['path'])
            if str(path).startswith('/ohos/'):
                need(build['inputs'].get(str(path))==dep,'actual system header hash absent')
            else:
                need(path in {origin/FIXTURES[name],origin/'actual_system_abi.h',*(origin/h for h in HEADER_SHA)} and
                     digest(relocate(str(path),BUILD_ORIGIN,bp.parent))==dep['sha256'],'unknown private compiler dependency')
        for filename in (('socket.h','syscall.h','stat.h') if name!='audio_global579_status' else ('asound.h','syscall.h','ioctl.h')):
            entries=[row for row in dependencies if Path(row['path']).name==filename and row['path'].startswith('/ohos/')]
            need(entries and all(build['inputs'].get(row['path'])==row for row in entries),'actual C syscall/UAPI header '+filename)
        obj=relocate(str(origin/(name+'.o')),BUILD_ORIGIN,bp.parent);raw_obj=obj.read_bytes()
        need(raw_obj.startswith((b'BC\xc0\xde',b'\xde\xc0\x17\x0b')) or len(raw_obj)>=52 and
             raw_obj[:7]==b'\x7fELF\x01\x01\x01' and struct.unpack_from('<HH',raw_obj,16)==(1,40),
             'actual ARM32 relocatable or real LLVM LTO object')
        artifacts=new['reused_artifacts'];wanted=dict(source=source,abi_guard=guard,object_new_hash_capture=obj,binary=binary,
             depfile=relocate(str(origin/'headers.d'),BUILD_ORIGIN,bp.parent))
        need(set(artifacts)==set(wanted),'all actual immutable rechecked C artifacts required')
        for key,path in wanted.items():
            row=artifacts[key];need(digest(path)==row['sha256'] and path.stat().st_size==row['bytes'] and
                 relocate(row['path'],BUILD_ORIGIN,bp.parent)==path,'actual full C artifact recheck '+key)
        elf=product.elf_header(binary,executable=True,product='armv7a_virt',interpreter_path=normal['interpreter'])
        need(elf==old['elf']==new['elf'] and digest(binary)==old['binary_sha256']==new['binary_sha256'] and
             product.machine_abi_flags(binary,'armv7a_virt')==normal['machine_abi_flags'],'actual ARM32 ELF/EABI, no relabel')
        needed=needed_from_elf(binary);need('libc.so' in needed and needed==set(old['DT_NEEDED'])==set(new['DT_NEEDED']),
             'actual native dynamic dependencies')
        for table in (commands,rechecked):
            command,log=table[name+'-actual-ELF-ABI'];text=log.read_text()
            need(command['argv']==['/ohos/prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-readelf','-h','-l','-d','--dyn-syms','--wide','--demangle',str(origin/name)] and product.dynamic_needed(text)==needed and
                 product.defined_symbol(text,'main') and product.defined_symbol(text,'__cfi_check'),
                 'actual readelf main/CFI/DT_NEEDED raw replay')
        need(old['actual_link_inputs']==new['actual_link_inputs'] and old['actual_link_inputs'] and
             old['linked_libraries']==new['linked_libraries'] and
             old['actual_link_input_sonames']==new['actual_link_input_sonames'],
             'actual opened linker input closure')
        trace=literal_link_inputs(commands[name+'-link'][1].read_text(),Path('/ohos/out/armv7a_virt'))
        need(trace=={Path(r['path']) for r in old['actual_link_inputs']}|{origin/(name+'.o')},
             'raw actual full link trace and retained input inventory differ')
        for item in old['actual_link_inputs']:need(build['inputs'].get(item['path'])==item,'actual opened input hash')
        for soname in needed:product.runtime_link_records(old,soname)
        all_needed.update(needed);tools[name]=dict(binary=binary,helper=old,needed=tuple(sorted(needed)))
    need(exports['build']==proof['build'] and exports['profile']==profile_descriptor and set(exports['dsos'])==all_needed,
         'actual exact linked installed DSO export')
    for soname,row in exports['dsos'].items():
        actual=checked(row['file']);need(product.elf_soname(actual,product='armv7a_virt')==soname and
            product.machine_abi_flags(actual,'armv7a_virt')==normal['machine_abi_flags'],
            'actual target DSO SONAME and complete normal ARM ABI flags')
        for name in NAMES:
            if soname not in tools[name]['needed']:continue
            selected,=product.runtime_link_records(tools[name]['helper'],soname)
            need(digest(actual)==selected['sha256'] and actual.stat().st_size==selected['bytes'],
                 'actual installed linker-opened DSO bytes differ')
    pair={'audio_control404':tools[NAMES[0]],'audio_status377':tools[NAMES[1]]}
    return AdmittedGlobalTools579(tools[NAMES[0]]['binary'],tools[NAMES[1]]['binary'],tools[NAMES[2]]['binary'],
        profile,pair,tools[NAMES[2]],dict(proof=proof,profile=profile_descriptor,
        scope='actual compile/recheck/ELF/image source inputs only; no runtime/onset acceptance'))
