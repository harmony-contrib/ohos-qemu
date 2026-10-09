#!/usr/bin/env python3
"""Apply/reapply the full Photos stack in scratch and run the actual ABC rule."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from build_rs_object_probe import PRODUCTS, sha

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT/'patches/common/foundation/multimedia/media_library/photos_recent_info'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--arch',choices=PRODUCTS,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    output = args.output.resolve()
    if output.parent != Path('/tmp').resolve() or not output.name.startswith('photo-recent-wrapper-'):
        raise ValueError('fresh owned /tmp/photo-recent-wrapper-* required')
    if not os.statvfs(root).f_flag & os.ST_RDONLY or not os.statvfs(root/'out').f_flag & os.ST_RDONLY:
        raise ValueError('production source and out must be mounted read-only')
    output.mkdir(exist_ok=False)
    report = {'status':'fail','scope':'actual_product_Photos_ABC_compile_NOT_guest',
              'first_artifact_behavior_gate_passed':False,'commands':[]}
    def command(argv,label,cwd=None):
        argv=list(map(str,argv))
        result=subprocess.run(argv,cwd=cwd,capture_output=True,text=True,timeout=180)
        log=output/(label+'.log')
        log.write_text(result.stdout+result.stderr)
        report['commands'].append({'argv':argv,'cwd':str(cwd) if cwd else None,
                                  'exit_code':result.returncode,'log_sha256':sha(log)})
        if result.returncode:
            raise ValueError('actual source/product command failed: '+label)
        return result.stdout
    try:
        spec=importlib.util.spec_from_file_location('recent_baseline',COMPONENT/'verify_source.py')
        baseline=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        baseline.validate(root)
        head=command(['git','-C',root/baseline.PROJECT,'rev-parse','HEAD'],'source-head').strip()
        if head!=baseline.REVISION:
            raise ValueError('fixed Release MediaLibrary revision required')
        staged=output/'source'
        original={}
        for relative,_,_ in baseline.FILES:
            path=root/baseline.PROJECT/relative
            original[relative]=sha(path)
            destination=staged/baseline.PROJECT/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,destination)
        for attempt in (1,2):
            command(['bash',COMPONENT/'apply.sh','--source-root',staged],'apply-'+str(attempt))
        for name in ('fusion_asset_type','api26_photo_enums','api26_photo_search_enums'):
            command(['bash',COMPONENT.parent/name/'apply.sh','--source-root',staged],'repeat-'+name)
        baseline.validate(staged,require_patched=True)
        cwd=root/'out'/PRODUCTS[args.arch]
        target='multimedia/media_library/photoaccesshelper.abc'
        query=command([root/'prebuilts/build-tools/linux-x86/bin/ninja','-w','dupbuild=warn',
                       '-C',cwd,'-t','commands','-s',target],'query',cwd)
        argv=shlex.split(query.splitlines()[-1])
        if (len(argv)!=8 or argv[0]!='/usr/bin/env' or
            (cwd/argv[1]).resolve()!=root/'build/scripts/ohos_abc.py' or
            argv[2]!='--outputs' or Path(argv[3]).resolve()!=cwd/target or
            argv[4]!='--es2abc' or argv[6]!='--sources' or
            (cwd/argv[7]).resolve()!=root/baseline.PROJECT/baseline.FILES[0][0]):
            raise ValueError('unexpected actual ABC rule')
        candidate=staged/baseline.PROJECT/baseline.FILES[0][0]
        compiled=output/'photoaccesshelper.abc'
        report['compiler_sha256']=sha(Path(argv[5])/'es2abc')
        argv[3],argv[7]=str(compiled),str(candidate)
        command(argv,'actual-ABC-compile',cwd)
        if not compiled.read_bytes().startswith(b'PANDA\x00\x00\x00'):
            raise ValueError('actual compiler did not produce Ark bytecode')
        if original!={relative:sha(root/baseline.PROJECT/relative) for relative in original}:
            raise ValueError('production input changed during read-only validation')
        report.update(status='pass',source_revision=head,original_source_sha256=original,
                      candidate_sha256=sha(candidate),abc_sha256=sha(compiled))
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        report['error']=str(error)
    (output/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'error':report.get('error')}))
    return 0 if report['status']=='pass' else 1

if __name__=='__main__':
    raise SystemExit(main())
