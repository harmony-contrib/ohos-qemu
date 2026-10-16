#!/usr/bin/env python3
"""Actual loader source + real provider DSO lifecycle. Only logging includes are host shims."""
import argparse,base64,gzip,hashlib,json,os,platform,select,socket,struct,subprocess,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
COMPONENT=ROOT/'patches/common/device/qemu/external_gnss'
FIXTURE=HERE/'fixtures/batch_system/external_gnss'
REL='drivers/peripheral/location/gnss/hdi_service'
CASES=['missing_symbol','bad_device','bad_table','callback_cleanup','external_cleanup','repeated_cleanup']
def prepare(root):
    meta=json.loads((FIXTURE/'provenance.json').read_text())
    for row in meta['files']:
        data=gzip.decompress(base64.b64decode((FIXTURE/row['fixture']).read_bytes()))
        assert hashlib.sha256(data).hexdigest()==row['sha256']
        p=root/row['path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    return meta

def feed(path,generation=1,previous=None):
    from batch_system_gnss_controller import read_exact,encode_sample
    records=[]
    def connect():
        stream=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        stream.settimeout(2);stream.connect(str(path));hello=read_exact(stream,32)
        magic,version,nonce,size,reserved=struct.unpack('<4sI16sII',hello)
        assert (magic,version,size,reserved)==(b'QGN1',1,88,0)
        return stream,hello,nonce
    if previous is not None:
        stream,hello,nonce=connect()
        with stream:
            assert nonce!=bytes.fromhex(previous['hello_hex'])[8:24]
            stream.sendall(bytes.fromhex(previous['frame_hex']))
            try:
                assert stream.recv(1)==b''
            except ConnectionResetError:
                pass
        records.append(dict(kind='old_generation_frame_rejected',hello_hex=hello.hex(),frame_hex=previous['frame_hex']))
    stream,hello,nonce=connect()
    with stream:
        # Controlled external test measurements enter the shipped native Provider; no mocked callback service.
        measurement=dict(at_ms=0,utc_ms=time.time_ns()//1000000,latitude=20.125+generation-1,
            longitude=-70.375-(generation-1),altitude=6.75,horizontal_accuracy=2.5,vertical_accuracy=3.5,
            speed=4.5,bearing=5.5)
        frame=encode_sample(nonce,1,measurement);stream.sendall(frame)
    record=dict(kind='valid_measurement',generation=generation,hello_hex=hello.hex(),frame_hex=frame.hex(),measurement=measurement)
    records.append(record)
    return record,records

def ready_line(proc):
    if not select.select([proc.stdout],[],[],10)[0]:
        raise TimeoutError('bounded GNSS harness readiness timeout')
    return proc.stdout.readline()

def run(output,same_process_reload=False):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    compiler=os.environ.get('CXX','c++')
    compiler_version=subprocess.check_output([compiler,'--version'],text=True)
    flags=[compiler,'-std=c++17','-Wall','-Wextra','-Werror','-g','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    env=dict(os.environ,LC_ALL='C',LC_CTYPE='C',LANG='C',ASAN_OPTIONS=f'detect_leaks={int(platform.system()!="Darwin")}:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1')
    # GNU-unique C++ bindings make glibc retain the host test DSO after dlclose.
    # Disable that binding for the host unload diagnostic; OHOS production uses Clang/libc++.
    # This enables the actual unload assertion instead of accepting a resident mapping.
    if platform.system()=='Linux' and 'clang' not in compiler_version.lower():
        flags+=['-fno-gnu-unique']
    commands=[];rows=[]
    def compile(name,args):
        command=flags+args+['-o',str(name)];proc=subprocess.run(command,capture_output=True,text=True)
        name.with_suffix(name.suffix+'.compile.log').write_text(proc.stdout+proc.stderr);commands.append(command)
        if proc.returncode:raise RuntimeError('compile failed: '+str(name))
    for state in ['before','after']:
        root=output/state;meta=prepare(root);inc=root/REL
        if state=='after':
            subprocess.run(['python3',str(COMPONENT/'apply.py'),'--source-root',str(root)],capture_output=True,check=True)
        (inc/'gnss_hdf_log.h').write_text('#pragma once\ntemplate<class... T> void HostLog(T...){ }\n#define HDF_LOGI(...) HostLog(__VA_ARGS__)\n#define HDF_LOGE(...) HostLog(__VA_ARGS__)\n')
        (inc/'gnss_interface_impl.h').write_text('#pragma once\n#include <string>\n')
        binary=root/'bridge_harness';includes=['-I'+str(inc),'-I'+str(COMPONENT/'files')]
        compile(binary,includes+[str(inc/'location_vendor_interface.cpp'),str(HERE/'batch_system_gnss_bridge_harness.cpp')]+([] if platform.system()=='Darwin' else ['-ldl']))
        source=(inc/'gnss_interface_impl.cpp').read_text()
        def function(name):
            start=source.index(name);brace=source.index('{',start);depth=1;end=brace+1
            while depth:
                depth+=(source[end]=='{')-(source[end]=='}');end+=1
            return source[start:end]+'\n'
        actual=''
        if 'LocationCallBackMap SnapshotLocationCallbacks()' in source:
            actual+=function('LocationCallBackMap SnapshotLocationCallbacks()')
        for name in ['void LocationUpdate(', 'void GetGnssBasicCallbackMethods(',
                     'bool GnssInterfaceImpl::IsGnssBasicConfigValid(', 'int32_t GnssInterfaceImpl::SetGnssConfigPara(']:
            actual+=function(name)
        (inc/'actual_bridge_functions.inc').write_text(actual)
        functions=root/'bridge_functions'
        compile(functions,includes+[str(HERE/'batch_system_gnss_bridge_functions_harness.cpp')])
        for case in ['callback_size','config_size','interval','cache','invalid_mode','callback_reentry']:
            command=[str(functions),case]
            try:
                proc=subprocess.run(command,env=env,capture_output=True,text=True,timeout=2)
                code=proc.returncode;log=proc.stdout+proc.stderr
            except subprocess.TimeoutExpired:
                code=124;log='actual original callback holds g_mutex while reentrant callback requests the same mutex; bounded 2s timeout\n'
            (root/('function-'+case+'.log')).write_text(log)
            rows.append(dict(state=state,case='actual_function_'+case,argv=command,exit_code=code))
            if state=='before' and code==0:raise RuntimeError('original bridge function defect not reproduced: '+case)
            if state=='after' and code:raise RuntimeError('repaired bridge function failed: '+case)
        # Keep the production UID0/path export unchanged in the repository. The test factory uses
        # the same shipped Provider class with an explicit host path/UID and the exact actual ABI.
        source=(COMPONENT/'files/qemu_gnss_vendor.cpp').read_text()
        assert source.count('GnssVendorDevice GnssVendorInterface = {')==1
        source=source.replace('GnssVendorDevice GnssVendorInterface = {','GnssVendorDevice HostUnusedProductDevice = {')
        test_source=root/'configured_provider.cpp';test_source.write_text(source+'\n'+(HERE/'batch_system_gnss_test_dso.inc').read_text())
        for case in CASES:
            directory=root/case;directory.mkdir();library=directory/'vendorGnssAdapter.so'
            if case.startswith('bad_') or case=='missing_symbol':
                kind={'missing_symbol':1,'bad_device':2,'bad_table':3}[case]
                compile(library,includes+['-shared','-fPIC','-DBAD_GNSS_KIND='+str(kind),str(HERE/'batch_system_gnss_bad_dso.cpp')])
            else:
                compile(library,includes+['-shared','-fPIC',str(COMPONENT/'files/qemu_gnss_input.cpp'),str(test_source)])
            with tempfile.TemporaryDirectory(prefix='qgb-',dir='/tmp') as temp:
                path=Path(temp)/'input';marker=Path(temp)/'unloaded'
                e=dict(env,GNSS_TEST_SOCKET=str(path),GNSS_TEST_UNLOADED=str(marker))
                e['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(directory)
                command=[str(binary),case]+(['reload'] if same_process_reload and case=='callback_cleanup' else [])
                proc=subprocess.Popen(command,env=e,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                first='';wire=[]
                try:
                    if case in ['callback_cleanup','external_cleanup']:
                        first=ready_line(proc)
                        if first.strip()=='READY':
                            previous,records=feed(path);wire.extend(records)
                            if same_process_reload and case=='callback_cleanup':
                                second=ready_line(proc);first+=second
                                if second.strip()=='READY2':
                                    _,records=feed(path,2,previous);wire.extend(records)
                                elif state=='after':
                                    raise RuntimeError('second GNSS generation did not become ready')
                    stdout,stderr=proc.communicate(timeout=10)
                except BaseException:
                    proc.kill();proc.communicate();raise
                log=first+stdout+stderr;(directory/'execution.log').write_text(log)
                (directory/'wire.json').write_text(json.dumps(wire,indent=2)+'\n')
                row=dict(state=state,case=case,argv=command,exit_code=proc.returncode,unload_marker=marker.read_text() if marker.exists() else '',wire=wire)
                rows.append(row)
                if state=='before':
                    if case in ['missing_symbol','bad_device','bad_table','callback_cleanup','external_cleanup']:
                        if proc.returncode==0:raise RuntimeError('original loader defect not reproduced: '+case)
                elif proc.returncode:raise RuntimeError('repaired loader boundary failed: '+case)
    result=dict(status='pass_actual_loader_dso_lifecycle',cases=rows,compile_commands=commands,fixture=meta,
                compiler=compiler_version.splitlines()[0],platform=platform.platform(),
                same_process_reload_requested=same_process_reload,
                same_process_reload_verified=bool(same_process_reload and any(row['state']=='after' and row['case']=='callback_cleanup' and row['unload_marker'].splitlines()==['unloaded','unloaded'] and len(row.get('wire',[]))==3 for row in rows)),
                requirements_closed=0,runtime_tested=False,
                limitations='Actual complete upstream loader source/header and true dlopen/dlsym/dlclose against actual shipped Provider class/socket transport. Test DSO factory explicitly configures host UID/path; production export remains pinned UID0. Only irrelevant HDF logging includes are shimmed. Full GNSS remote HDI TU/business/CFI/official ARM64/new package remain pending.')
    (output/'evidence.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--same-process-reload',action='store_true');a=p.parse_args();r=run(a.output,a.same_process_reload)
    print(json.dumps(dict(status=r['status'],cases=len(r['cases']))))
