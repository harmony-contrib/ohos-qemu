#!/usr/bin/env python3
"""Reproduce every HAP native member with the original read-only SDK39 strip.

Root executes recheck under its build lease. verify reads retained evidence only;
neither ELF similarity nor a self-reported hash permits a changed HAP member.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import time
import zipfile

STATUS = 'pass_exact_SDK_NativeStrip_ONLY'
SCOPE = 'exact_original_SDK39_NativeStrip_NOT_signing_or_guest_acceptance'
SDK_STRIP_SHA256 = '78bee3733d321304ee24d068840878a4413cc4ac814c6beab5705da14e65a7af'
ABIS = {'arm64-v8a':(2,183), 'armeabi-v7a':(1,40), 'x86_64':(2,62)}


def require(value, reason):
    if not value: raise ValueError(reason)


def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024), b''): value.update(block)
    return value.hexdigest()


def regular(path):
    path=Path(path)
    require(path.is_absolute() and path.is_file() and not any(p.is_symlink() for p in (path,*path.parents)),
            'actual non-aliased regular evidence required: '+str(path))
    require(0 < path.stat().st_size <= 128*1024**2, 'bounded nonempty input required')
    return path


def descriptor(path):
    path=regular(path)
    return {'path':str(path),'sha256':digest(path)}


def checked(value):
    require(isinstance(value,dict) and set(value)=={'path','sha256'}, 'exact file descriptor required')
    path=regular(value['path']);require(digest(path)==value['sha256'], 'actual input changed: '+str(path));return path


def load(path):
    def unique(pairs):
        value={}
        for key,item in pairs:
            require(key not in value,'duplicate receipt/SDK key');value[key]=item
        return value
    return json.loads(Path(path).read_text(),object_pairs_hook=unique)


def retained(root,value):
    relative=PurePosixPath(value['path'])
    require(not relative.is_absolute() and '..' not in relative.parts and relative.as_posix()==value['path'] and
            '\\' not in value['path'], 'unsafe retained evidence path')
    path=regular(root/relative);require(digest(path)==value['sha256'],'retained evidence changed');return path


def keep(root,source,relative):
    path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream: stream.write(Path(source).read_bytes())
    return {'path':relative,'sha256':digest(path)}


def metadata(value):
    require(isinstance(value,dict) and value.get('path')=='native' and value.get('apiVersion')=='26' and
            value.get('platformVersion')=='26.0.0' and value.get('version')=='26.0.0.39' and
            value.get('releaseType')=='Release', 'actual Native SDK 26.0.0.39 required; no host SDK substitution')
    return value


def members(path,member):
    require(re.fullmatch(r'libs/(arm64-v8a|armeabi-v7a|x86_64)/[A-Za-z0-9_+.-]+\.so',member or '') is not None,
            'one exact ABI native HAP member required')
    prefix=member.rsplit('/',1)[0]+'/'
    with zipfile.ZipFile(path) as archive:
        infos=archive.infolist();names=[v.filename for v in infos]
        require(len(infos)<=10000 and len(names)==len(set(names)), 'unsafe duplicated/excessive HAP entries')
        require(sum(v.file_size for v in infos)<=256*1024**2, 'bounded HAP contents required')
        result={}
        for item in infos:
            parsed=PurePosixPath(item.filename)
            require(not parsed.is_absolute() and '..' not in parsed.parts and '\\' not in item.filename and
                    parsed.as_posix()==item.filename.rstrip('/') and not item.flag_bits&1 and
                    ((item.external_attr>>16)&0o170000)!=0o120000, 'unsafe HAP entry')
            if item.filename.startswith('libs/') and item.filename.endswith('.so'):
                require(item.filename.startswith(prefix) and '/' not in item.filename[len(prefix):] and
                        0<item.file_size<=128*1024**2, 'uncovered ABI or nested native HAP member')
                result[item.filename]=archive.read(item)
        require(member in result, 'actual requested HAP native member missing')
        return result


def elf_layout(data):
    """Read ELF headers/sections in Python for diagnostics, never identity proof."""
    require(len(data)>=64 and data[:4]==b'\x7fELF' and data[4] in (1,2) and data[5:7]==b'\x01\x01', 'actual little-endian ELF required')
    cls=data[4];kind,machine=struct.unpack_from('<HH',data,16)
    phoff,shoff=struct.unpack_from('<QQ' if cls==2 else '<II',data,32 if cls==2 else 28)
    phsize,phcount,shsize,shcount,shindex=struct.unpack_from('<HHHHH',data,54 if cls==2 else 42)
    phfmt='<IIQQQQQQ' if cls==2 else '<IIIIIIII';shfmt='<IIQQQQIIQQ' if cls==2 else '<IIIIIIIIII'
    require(kind==3 and phcount>0 and phsize==struct.calcsize(phfmt) and phoff+phsize*phcount<=len(data) and
            shcount>0 and shsize==struct.calcsize(shfmt) and shindex<shcount and shoff+shsize*shcount<=len(data),
            'complete DSO program/section tables required')
    headers=[list(struct.unpack_from(phfmt,data,phoff+i*phsize))for i in range(phcount)]
    sections=[struct.unpack_from(shfmt,data,shoff+i*shsize)for i in range(shcount)]
    names=sections[shindex];require(names[1]==3 and names[4]+names[5]<=len(data),'ELF section names truncated')
    strings=data[names[4]:names[4]+names[5]];result={}
    for section in sections[1:]:
        require(section[0]<len(strings) and b'\0' in strings[section[0]:], 'ELF section name truncated')
        name=strings[section[0]:].split(b'\0',1)[0].decode('ascii')
        require(name and name not in result and (section[1]==8 or section[4]+section[5]<=len(data)), 'ELF section duplicated/truncated')
        result[name]={'type':section[1],'flags':section[2],'address':section[3],'offset':section[4],'bytes':section[5],
            'sha256':None if section[1]==8 else hashlib.sha256(data[section[4]:section[4]+section[5]]).hexdigest()}
    return {'class':cls,'machine':machine,'type':kind,'program_headers':headers,'sections':result}


def abi(data,member):
    value=elf_layout(data);require((value['class'],value['machine'])==ABIS[member.split('/')[1]], 'DSO/HAP ABI mismatch');return value


def originals(evidence,native,hap,member):
    value=load(evidence)
    builds=[b for b in value.get('native_builds',[]) if b.get('binary',{}).get('sha256')==digest(native)]
    require(len(builds)==1, 'one original native_builds artifact required');build=builds[0];project=build['project']
    require(Path(build['binary']['path'])==native and checked(build['binary'])==native, 'CLI original native path/report mismatch')
    haps=[h for h in value.get('haps',[]) if h.get('project')==project and h.get('sha256')==digest(hap)]
    require(len(haps)==1 and haps[0].get('bytes')==hap.stat().st_size, 'actual original SDK HAP/report binding missing')
    rows=[r for r in value.get('commands',[]) if r.get('project')==project]
    require(rows and all(type(r.get('exit_code'))is int and r['exit_code']==0 for r in rows), 'selected original SDK commands failed/incomplete')
    native_rows=[r for r in rows if r.get('label')==build['command_label']]
    compile_rows=[r for r in rows if 'assembleHap' in r.get('argv',[])]
    require(len(native_rows)==len(compile_rows)==1 and native_rows[0]['argv'][0]==build['compiler']['path'], 'original native/Hvigor command absent')
    for row in rows:
        log=Path(row['log']);require(log.is_file() and not log.is_symlink() and digest(log)==row['sha256'],'original SDK command log changed')
    log=Path(compile_rows[0]['log']).read_text(errors='replace');plain=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',log)
    require('BUILD SUCCESSFUL' in plain and re.search(r'Finished[^\n]*@DoNativeStrip',plain), 'actual completed Hvigor NativeStrip task required')
    checked(build['source']);require(value.get('source_files') and type(value.get('exit_code'))is int, 'original SDK source/report identity absent')
    result={member:descriptor(native)}
    for runtime in build.get('runtime_libraries',[]):
        path=regular(runtime['path']);name=member.rsplit('/',1)[0]+'/'+path.name
        require(name not in result and digest(path)==runtime['sha256'], 'duplicate/changed original native runtime library')
        result[name]=descriptor(path)
    require(set(members(hap,member))==set(result), 'all HAP runtime native libraries must be covered')
    return value,build,rows,result


def run_command(argv,label,output):
    start=time.monotonic();result=subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,timeout=120,
        env=dict(os.environ,LC_ALL='C',LC_CTYPE='C',LANG='C',LD_LIBRARY_PATH='',LD_PRELOAD=''))
    row={'argv':list(map(str,argv)),'exit_code':result.returncode,'seconds':time.monotonic()-start}
    for name,data in (('stdout',result.stdout),('stderr',result.stderr)):
        path=output/'logs'/(label+'.'+name);path.parent.mkdir(exist_ok=True)
        with path.open('xb') as stream:stream.write(data)
        row[name]={'path':str(path.relative_to(output)),'sha256':digest(path)}
    return row


def read_log(root,value):
    # Successful strip commands and the original compiler may emit empty logs.
    relative=PurePosixPath(value['path']);require(not relative.is_absolute() and '..' not in relative.parts and
        relative.as_posix()==value['path'] and '\\' not in value['path'], 'unsafe command log path')
    path=root/relative;require(path.is_file() and not any(p.is_symlink()for p in (path,*path.parents)) and
        path.stat().st_size<=16*1024**2 and digest(path)==value['sha256'],'retained command log changed');return path


def recheck(sdk,native,hap,member,evidence,output):
    sdk,native,hap,evidence,output=(Path(p).absolute()for p in (sdk,native,hap,evidence,output))
    require(not output.exists() and not output.is_symlink() and not output.resolve().is_relative_to(sdk.resolve()),'fresh scratch output outside SDK required')
    output.mkdir(parents=True,mode=0o700)
    report={'schema_version':1,'status':'fail','scope':SCOPE,'failures':[],'execution_output':str(output),
        'first_artifact_behavior_gate_passed':False,'runtime_validated':False,'libraries':{},'commands':[]}
    try:
        native,hap,evidence=map(regular,(native,hap,evidence))
        original,build,rows,inputs=originals(evidence,native,hap,member)
        require(os.statvfs(sdk).f_flag & os.ST_RDONLY,'actual original SDK mount must be read-only')
        tool=sdk/'llvm/bin/llvm-strip';meta=sdk/'oh-uni-package.json'
        require(all(p.resolve().is_relative_to(sdk.resolve()) and p.is_file()for p in (tool,meta)), 'original SDK tool/metadata missing or outside SDK')
        require(digest(tool)==SDK_STRIP_SHA256 and str(sdk/'llvm/bin/clang++')==build['compiler']['path'] and
            digest(meta)==build['sdk_native_metadata_sha256'], 'original SDK39 tool/compiler root/metadata differs')
        report.update(script_sha256=digest(Path(__file__)),script=keep(output,Path(__file__),'inputs/verifier.py'),
            sdk=str(sdk),canonical_sdk_root=str(sdk.resolve()),sdk_read_only=True,sdk_metadata=metadata(load(meta)),
            original_sdk_evidence=descriptor(evidence),frozen_sdk_evidence=keep(output,evidence,'inputs/original-sdk-evidence.json'),
            native_build=build,member=member,HAP=descriptor(hap),original_native=descriptor(native),
            sdk_inputs={'strip':{'path':str(tool),'canonical_path':str(tool.resolve()),'sha256':digest(tool)},
                        'metadata':{'path':str(meta),'canonical_path':str(meta.resolve()),'sha256':digest(meta)}},
            frozen_tool=keep(output,tool,'inputs/llvm-strip'),frozen_metadata=keep(output,meta,'inputs/oh-uni-package.json'))
        report['original_commands']=[]
        for index,row in enumerate(rows):
            saved=keep(output,Path(row['log']),'inputs/original-command-'+str(index)+'.log')
            report['original_commands'].append({'original':row,'log':saved})
        version=run_command([str(tool),'--version'],'strip-version',output);report['commands'].append(version)
        require(version['exit_code']==0 and 'LLVM' in read_log(output,version['stdout']).read_text(), 'actual SDK strip version command failed')
        packed=members(hap,member)
        for index,(name,source) in enumerate(sorted(inputs.items())):
            frozen=keep(output,checked(source),'inputs/native-'+str(index)+'.so')
            scratch=keep(output,checked(source),'work/native-'+str(index)+'.so')
            destination=output/'stripped'/('native-'+str(index)+'.so');destination.parent.mkdir(exist_ok=True)
            argv=[str(tool),str(output/scratch['path']),'-o'+str(destination)]
            command=run_command(argv,'strip-'+str(index),output);report['commands'].append(command)
            row={'original':source,'frozen_original':frozen,'scratch_input':scratch,'command':command,
                 'HAP_member_sha256':hashlib.sha256(packed[name]).hexdigest(),'HAP_member_bytes':len(packed[name])}
            report['libraries'][name]=row;require(command['exit_code']==0,'actual SDK NativeStrip failed: '+name)
            row['stripped']={'path':str(destination.relative_to(output)),'sha256':digest(regular(destination))}
            require(destination.read_bytes()==packed[name], 'actual SDK NativeStrip did not reproduce exact HAP member: '+name)
            row['original_ELF']=abi(checked(source).read_bytes(),name);row['stripped_ELF']=abi(destination.read_bytes(),name)
        report['sdk_inputs_after']={key:{**value,'sha256':digest(Path(value['path']))}for key,value in report['sdk_inputs'].items()}
        require(report['sdk_inputs_after']==report['sdk_inputs'],'SDK tool/metadata changed during recheck')
        for source in inputs.values(): checked(source)
        require(descriptor(native)==report['original_native'] and descriptor(hap)==report['HAP'] and
            descriptor(evidence)==report['original_sdk_evidence'] and digest(Path(__file__))==report['script_sha256'], 'read-only input/script changed')
        report['status']=STATUS
    except (OSError,ValueError,KeyError,TypeError,struct.error,subprocess.SubprocessError,zipfile.BadZipFile) as error:
        report['failures'].append(type(error).__name__+': '+str(error))
    with (output/'receipt.json').open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    return report


def verify(caller_spec,native_build,original_binary):
    """No subprocess/strip/SDK invocation. Re-read exact retained and current bytes."""
    receipt=checked(caller_spec['native_strip_receipt']);root=receipt.parent;value=load(receipt)
    require(value.get('schema_version')==1 and type(value['schema_version'])is int and value.get('status')==STATUS and
        value.get('scope')==SCOPE and value.get('failures')==[] and value.get('runtime_validated')is False and
        value.get('first_artifact_behavior_gate_passed')is False and value.get('sdk_read_only')is True,
        'complete successful exact SDK NativeStrip receipt required')
    require(value['script_sha256']==digest(Path(__file__))==digest(retained(root,value['script'])), 'actual recheck verifier source changed')
    evidence=checked(caller_spec['sdk_evidence']);native=regular(Path(original_binary).absolute());hap=checked(caller_spec['unsigned_hap'])
    require(digest(evidence)==value['original_sdk_evidence']['sha256']==digest(retained(root,value['frozen_sdk_evidence'])) and
        digest(hap)==value['HAP']['sha256'] and digest(native)==value['original_native']['sha256']==native_build['binary']['sha256'] and
        native_build==value['native_build'] and native_build['project']==caller_spec['sdk_project'], 'current original SDK/native/HAP binding differs')
    original=load(evidence);builds=[b for b in original.get('native_builds',[])if b==native_build]
    require(len(builds)==1,'selected native build not present in unchanged original SDK report')
    haps=[h for h in original.get('haps',[])if h.get('project')==caller_spec['sdk_project'] and h.get('sha256')==digest(hap)]
    require(len(haps)==1 and haps[0].get('bytes')==hap.stat().st_size,'current HAP differs from unchanged original SDK report')
    meta=retained(root,value['frozen_metadata']);tool=retained(root,value['frozen_tool'])
    require(set(value['sdk_inputs'])=={'strip','metadata'} and
        value['frozen_tool']['path']=='inputs/llvm-strip' and value['frozen_metadata']['path']=='inputs/oh-uni-package.json' and
        value['script']['path']=='inputs/verifier.py' and value['frozen_sdk_evidence']['path']=='inputs/original-sdk-evidence.json' and
        metadata(load(meta))==value['sdk_metadata'] and digest(meta)==native_build['sdk_native_metadata_sha256'] and
        digest(tool)==SDK_STRIP_SHA256 and value['sdk_inputs']==value['sdk_inputs_after'] and
        value['sdk_inputs']['strip']['sha256']==SDK_STRIP_SHA256 and value['sdk_inputs']['metadata']['sha256']==digest(meta),
        'retained actual SDK39 metadata/tool read hashes differ')
    sdk=Path(value['sdk']);require(sdk.is_absolute() and value['sdk_inputs']['strip']['path']==str(sdk/'llvm/bin/llvm-strip') and
        value['sdk_inputs']['metadata']['path']==str(sdk/'oh-uni-package.json') and
        native_build['compiler']['path']==str(sdk/'llvm/bin/clang++'),'recheck tools do not belong to original compiler SDK')
    canonical=Path(value['canonical_sdk_root'])
    require(canonical.is_absolute() and all(Path(v['canonical_path']).is_absolute() and
        Path(v['canonical_path']).is_relative_to(canonical)for v in value['sdk_inputs'].values()), 'recorded SDK tool/metadata canonical origin differs')
    selected=[r for r in original['commands']if r.get('project')==caller_spec['sdk_project']]
    require([r['original']for r in value['original_commands']]==selected and selected and
        all(type(r.get('exit_code'))is int and r['exit_code']==0 for r in selected), 'unchanged successful original SDK command set required')
    for row in value['original_commands']:
        require(digest(read_log(root,row['log']))==row['original']['sha256'],'original SDK raw command log differs')
    compile_rows=[r for r in value['original_commands']if 'assembleHap'in r['original']['argv']]
    require(len(compile_rows)==1,'original Hvigor assembleHap command required')
    plain=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',read_log(root,compile_rows[0]['log']).read_text(errors='replace'))
    require('BUILD SUCCESSFUL'in plain and re.search(r'Finished[^\n]*@DoNativeStrip',plain),'original successful NativeStrip task missing')
    packed=members(hap,value['member']);expected={value['member']:descriptor(native)}
    for item in native_build.get('runtime_libraries',[]):
        name=value['member'].rsplit('/',1)[0]+'/'+Path(item['path']).name;path=regular(native.parent/Path(item['path']).name)
        require(name not in expected and digest(path)==item['sha256'],'original runtime native library changed or duplicated');expected[name]=descriptor(path)
    require(set(packed)==set(value['libraries'])==set(expected),'exact complete native/runtime member coverage required')
    commands=value['commands'];require(len(commands)==1+len(expected),'actual strip/version commands incomplete')
    require(commands[0]['argv']==[str(sdk/'llvm/bin/llvm-strip'),'--version'] and commands[0]['exit_code']==0 and
        'LLVM'in read_log(root,commands[0]['stdout']).read_text(),'actual pinned strip version log missing')
    for row in commands:
        require(type(row.get('exit_code'))is int and row['exit_code']==0 and type(row.get('seconds'))in (int,float) and row['seconds']>=0,
            'actual SDK strip/version command failed')
        read_log(root,row['stdout']);read_log(root,row['stderr'])
    execution=Path(value['execution_output']);require(execution.is_absolute(),'original execution output path missing')
    result={}
    for index,name in enumerate(sorted(expected)):
        row=value['libraries'][name];current=checked(expected[name]);frozen=retained(root,row['frozen_original'])
        scratch=retained(root,row['scratch_input']);stripped=retained(root,row['stripped'])
        require(row['frozen_original']['path']=='inputs/native-'+str(index)+'.so' and
            row['scratch_input']['path']=='work/native-'+str(index)+'.so' and
            row['stripped']['path']=='stripped/native-'+str(index)+'.so','exact retained original/work/output roles required')
        require(digest(current)==row['original']['sha256']==digest(frozen)==digest(scratch), 'original/scratch native DSO differs')
        command=commands[index+1]
        require(row['command']==command and command['argv']==[str(sdk/'llvm/bin/llvm-strip'),
            str(execution/row['scratch_input']['path']),'-o'+str(execution/row['stripped']['path'])], 'not exact original SDK NativeStrip argv')
        require(stripped.read_bytes()==packed[name] and row['HAP_member_sha256']==hashlib.sha256(packed[name]).hexdigest() and
            row['HAP_member_bytes']==len(packed[name]), 'stripped bytes differ from current HAP member')
        require(abi(current.read_bytes(),name)==row['original_ELF'] and abi(stripped.read_bytes(),name)==row['stripped_ELF'],'retained native ELF diagnostics changed')
        result[name]={'original_sha256':digest(current),'HAP_member_sha256':digest(stripped),'HAP_member_bytes':len(packed[name])}
    return {'status':STATUS,'scope':SCOPE,'receipt':descriptor(receipt),'sdk_metadata_sha256':digest(meta),
        'sdk_version':value['sdk_metadata']['version'],'strip_tool_sha256':digest(tool),'native_binary_sha256':digest(native),
        'HAP_sha256':digest(hap),'libraries':result,'runtime_validated':False,'first_artifact_behavior_gate_passed':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);modes=parser.add_subparsers(dest='mode',required=True)
    command=modes.add_parser('recheck')
    for name in ('sdk','native','hap','sdk-evidence','output'):command.add_argument('--'+name,type=Path,required=True)
    command.add_argument('--member',required=True);args=parser.parse_args()
    value=recheck(args.sdk,args.native,args.hap,args.member,args.sdk_evidence,args.output)
    print(json.dumps({'status':value['status'],'failures':value['failures']}));return int(value['status']!=STATUS)


if __name__=='__main__':raise SystemExit(main())
