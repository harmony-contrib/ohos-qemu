#!/usr/bin/env python3
"""Explicit native gate: full real B4/candidate CPPs + actual headers, controlled external dependencies."""
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',type=Path,required=True)
    parser.add_argument('--work-root',type=Path,required=True)
    parser.add_argument('--source-root',type=Path,help='optional exact incarnation source tree instead of candidate fixture')
    parser.add_argument('--sanitize',choices=('address,undefined','thread','none'),default='address,undefined')
    args=parser.parse_args()
    fixture=Path(__file__).parent/'fixtures/batch_media/audio_haptic_generation'
    states=json.loads((fixture/'source_states.json').read_text())
    result={'schema':1,'scope':'host real class-header/full-CPP controlled dependency regression',
            'native_executed':False,'guest_passed':False,'pcm_hdi_verified':False,'capability_closed':False,
            'compiler':str(args.compiler),'steps':[],'source_sha256':{}}
    args.work_root.mkdir(parents=True,exist_ok=True)
    directory=Path(tempfile.mkdtemp(prefix='audio-haptic-native-',dir=args.work_root))
    result['directory']=str(directory)
    try:
        for state in ('b4','incarnation'):
            source=directory/state;source.mkdir()
            result['source_sha256'][state]={}
            for name,entry in states['states'][state].items():
                if entry['gzip_base64'] is None:continue
                data=(args.source_root/states['project']/name).read_bytes() if args.source_root and state=='incarnation' else gzip.decompress(base64.b64decode(entry['gzip_base64']))
                if hashlib.sha256(data).hexdigest()!=entry['sha256']:
                    raise ValueError('native source must match exact complete '+state+' state: '+name)
                (source/Path(name).name).write_bytes(data)
                result['source_sha256'][state][name]=entry['sha256']
            command=[str(args.compiler),'-std=c++17','-pthread','-fno-rtti','-Wall','-Wextra','-Werror',
                     '-Wno-unused-parameter','-Wno-unused-const-variable','-include',str(fixture/'stubs/host_prelude.h'),
                     '-I'+str(source),'-I'+str(fixture/'include'),'-I'+str(fixture/'stubs')]
            if state=='b4':command.append('-DAUDIO_HAPTIC_BASELINE')
            if args.sanitize!='none':command+=['-fsanitize='+args.sanitize,'-fno-omit-frame-pointer']
            executable=directory/('generation-host-'+state)
            command += [str(source/'audio_haptic_sound_normal_impl.cpp'),str(source/'audio_haptic_player_impl.cpp'),
                        str(fixture/'native_harness.cpp'),'-o',str(executable)]
            result['steps'].append({'state':state,'kind':'compile','argv':command})
            build=subprocess.run(command,capture_output=True,text=True,timeout=120)
            (directory/(state+'-compile.stdout')).write_text(build.stdout);(directory/(state+'-compile.stderr')).write_text(build.stderr)
            result['steps'][-1]['exit_code']=build.returncode
            if build.returncode:raise RuntimeError(state+' native compile failed; inspect compile.stderr')
            runtime=[str(executable),str(directory)]
            result['steps'].append({'state':state,'kind':'execute','argv':runtime})
            run=subprocess.run(runtime,capture_output=True,text=True,timeout=60,
                               env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0' if os.uname().sysname!='Linux' else 'detect_leaks=1'))
            result['native_executed']=True
            result['steps'][-1]['exit_code']=run.returncode
            (directory/(state+'-run.stdout')).write_text(run.stdout);(directory/(state+'-run.stderr')).write_text(run.stderr)
            if run.returncode:raise RuntimeError(state+' native regression failed; inspect run.stderr')
        result['host_native_passed']=True
    except BaseException as exc:
        result['host_native_passed']=False
        result['error']=str(exc)
        raise
    finally:
        (directory/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'result':str(directory/'result.json'),'host_native_passed':result.get('host_native_passed',False),
                          'guest_passed':False}))


if __name__=='__main__':main()
