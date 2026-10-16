#!/usr/bin/env python3
"""True vendor ABI, actual provider functions and Unix input; no packaged runtime closure."""
import argparse,base64,gzip,hashlib,json,os,platform,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
COMPONENT=ROOT/'patches/common/device/qemu/external_gnss'
CASES=['abi_boundaries','config','no_source','valid','optional','fragmented','wrong_nonce','wrong_version',
       'zero_sequence','repeated_sequence','repeated_utc','stale_utc','future_utc','latitude','longitude','nan',
       'zero_accuracy','speed','bearing','unknown_fields','partial','unauthorized','stop_replay','reconnect_replay',
       'callback_stop','callback_cleanup','backpressure_stop','file_protection','symlink_protection',
       'wrong_magic','reserved','altitude','infinity','vertical_accuracy']
def run(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    fixture=HERE/'fixtures/batch_system/external_gnss';meta=json.loads((fixture/'provenance.json').read_text())
    for row in meta['files']:
        data=gzip.decompress(base64.b64decode((fixture/row['fixture']).read_bytes()))
        assert hashlib.sha256(data).hexdigest()==row['sha256']
        (output/Path(row['path']).name).write_bytes(data)
    env=dict(os.environ,LC_ALL='C',LC_CTYPE='C',LANG='C',ASAN_OPTIONS=f'detect_leaks={int(platform.system()!="Darwin")}:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1')
    files=COMPONENT/'files'
    compiler=os.environ.get('CXX','c++')
    compiler_version=subprocess.check_output([compiler,'--version'],text=True)
    flags=[compiler,'-std=c++17','-Wall','-Wextra','-Werror','-g','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(files),'-I'+str(output)]
    commands=[]
    def compile(name,args):
        command=flags+args+['-o',str(output/name)];proc=subprocess.run(command,capture_output=True,text=True)
        (output/(name+'.compile.log')).write_text(proc.stdout+proc.stderr);commands.append(command)
        if proc.returncode:raise RuntimeError(name+' compilation failed')
    compile('gnss_harness',[str(files/'qemu_gnss_input.cpp'),str(HERE/'batch_system_gnss_harness.cpp')])
    rows=[]
    import tempfile
    with tempfile.TemporaryDirectory(prefix='qgn-',dir='/tmp') as temp:
        for i,case in enumerate(CASES):
            command=[str(output/'gnss_harness'),case,str(Path(temp)/(str(i)+'.sock'))]
            proc=subprocess.run(command,env=env,capture_output=True,text=True,timeout=15)
            (output/(case+'.log')).write_text(proc.stdout+proc.stderr)
            rows.append(dict(case=case,argv=command,exit_code=proc.returncode))
            if proc.returncode:raise RuntimeError(case+' failed')
    compile('vendorGnssAdapter.so',['-shared','-fPIC',str(files/'qemu_gnss_input.cpp'),str(files/'qemu_gnss_vendor.cpp')])
    compile('gnss_loader',[str(HERE/'batch_system_gnss_loader.cpp')]+([] if platform.system()=='Darwin' else ['-ldl']))
    command=[str(output/'gnss_loader'),str(output/'vendorGnssAdapter.so')]
    proc=subprocess.run(command,env=env,capture_output=True,text=True,timeout=15)
    (output/'loader.log').write_text(proc.stdout+proc.stderr)
    if proc.returncode:raise RuntimeError('actual DSO ABI load failed')
    rows.append(dict(case='true_dso_vendor_abi',argv=command,exit_code=proc.returncode))
    result=dict(status='pass_actual_host_gnss_provider',cases=rows,compile_commands=commands,fixture=meta,
      source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files.glob('*'))},
      compiler=compiler_version.splitlines()[0],platform=platform.platform(),
      host_test_peer_uid=os.geteuid(),exported_product_peer_uid=0,requirements_closed=0,runtime_tested=False,
      limitations='Actual full upstream vendor ABI header, provider functions, sockets and dlsym data symbol tested. Host Provider instance explicitly uses host UID/private path. Exported product device remains UID0/path fixed. Official GN/ARM64/CFI, HDI bridge, Location business/public API, SELinux and new package are not tested here.')
    (output/'evidence.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=run(args.output);print(json.dumps(dict(status=result['status'],cases=len(result['cases']))))
