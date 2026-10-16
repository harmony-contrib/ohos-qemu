#!/usr/bin/env python3
"""Reproduce the narrow read-only snapshot; this never runs build/native tools."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


QUERY = r'''
from pathlib import Path
import hashlib, json, time
r = Path('/ohos')
out = r / 'out/arm64_virt'
project = 'applications/standard/contacts_data/contacts'
obj = out / ('obj/' + project)
def descriptor(path):
    if not path.exists():
        return {'path':str(path),'exists':False}
    data = path.read_bytes(); s=path.stat()
    return {'path':str(path),'exists':True,'sha256':hashlib.sha256(data).hexdigest(),
            'size':len(data),'mtime_ns':s.st_mtime_ns,'container_filesystem_inode':s.st_ino}
def excerpt(path, start, end):
    lines=path.read_text().splitlines()
    return {'path':str(path),'lines':[{'line':i+1,'text':lines[i]} for i in range(start-1,min(end,len(lines)))]}
sources = [project+'/BUILD.gn',project+'/src/contact.js',project+'/src/native_module.cpp',
           'build/scripts/generate_js_bytecode.py','build/scripts/run_objcopy.py','build/ohos/ace/ace.gni',
           'build/config/components/ets_frontend/es2abc_config.gni','build/hb/modules/ohos_build_module.py',
           'build/hb/containers/arg.py','build/hb/resources/args/default/buildargs.json',
           'arkcompiler/runtime_core/libpandafile/file.h','arkcompiler/runtime_core/libpandafile/file.cpp']
artifacts = {'source_js':r/(project+'/src/contact.js'),'abc':obj/'contact.abc',
             'js_object':obj/'contact.o','abc_object':obj/'contact_abc.o',
             'unstripped':out/'lib.unstripped/applications/contacts_data/libcontact.z.so',
             'linked':out/'applications/contacts_data/libcontact.z.so',
             'staged':out/'packages/phone/system/lib64/module/libcontact.z.so'}
data={key:path.read_bytes() for key,path in artifacts.items()}
elf={key:Elf(data[key],'arm64','object' if key.endswith('_object') else 'dso')
     for key in ('js_object','abc_object','unstripped','linked','staged')}
bindings={}
for key,prefix,object_key in [('source_js',PREFIXES[0],'js_object'),('abc',PREFIXES[1],'abc_object')]:
    blob,location=elf['unstripped'].blob(prefix,dso=True)
    object_blob,_=elf[object_key].blob(prefix)
    bindings[key]={'unstripped_symbol_range':location,'object_bytes_match_input':object_blob==data[key],
                   'unstripped_bytes_match_input':blob==data[key],
                   'linked_bytes_match_input':elf['linked'].mapped(location['address'],location['size'])==data[key],
                   'staged_bytes_match_input':elf['staged'].mapped(location['address'],location['size'])==data[key]}
toolchain=out/'toolchain.ninja';selected=[]
markers=('rule __applications_standard_contacts_data_contacts_gen_contact_abc_',
         'rule __applications_standard_contacts_data_contacts_gen_js_obj_contact_')
lines=toolchain.read_text().splitlines()
for i,line in enumerate(lines):
    if line.startswith(markers):
        selected.extend({'line':j+1,'text':lines[j]} for j in range(i,min(i+4,len(lines))))
    elif line.startswith('build obj/'+project+'/') and any(x in line for x in (
            '/contact.abc:', '/contact_abc.o:', '/contact.o:', '/gen_contact_abc.stamp:',
            '/gen_js_obj_contact_abc.stamp:', '/gen_js_obj_contact_js.stamp:')):
        selected.append({'line':i+1,'text':line})
ninja=obj/'contact.ninja';link_lines=[]
for i,line in enumerate(ninja.read_text().splitlines()):
    if line.startswith(('build applications/contacts_data/libcontact.z.so','build obj/'+project+'/src/contact/')):
        link_lines.append({'line':i+1,'text':line})
log=[]
targets={str((obj/name).relative_to(out)) for name in (
    'contact.abc','contact_abc.o','contact.o','gen_contact_abc.stamp',
    'gen_js_obj_contact_abc.stamp','gen_js_obj_contact_js.stamp')}
for line in (out/'.ninja_log').open():
    fields=line.rstrip('\n').split('\t')
    if len(fields)>=4 and fields[3] in targets:log.append(line.rstrip('\n'))
current_args=r/'out/hb_args/buildargs.json'
value={'schema_version':1,'scope':'READ_ONLY_existing_source_graph_and_old_output_NOT_new_build_evidence',
       'observed_unix_ns':time.time_ns(),'source_descriptors':[descriptor(r/name) for name in sources],
       'artifacts':{key:descriptor(path) for key,path in artifacts.items()},'old_payload_identity':bindings,
       'old_ABC_header':abc_header(data['abc']),'old_NAPI_exports':elf['linked'].exports(),
       'linked_equals_staged':data['linked']==data['staged'],
       'old_toolchain':{'descriptor':descriptor(toolchain),'selected_lines':selected},
       'old_link_graph':{'descriptor':descriptor(ninja),'selected_lines':link_lines},
       'old_install_module':json.loads((obj/'contact_module_info.json').read_text()),
       'old_ninja_log_exact_blob_targets':log,'persisted_hb_args':descriptor(current_args),
       'source_excerpts':[excerpt(r/(project+'/BUILD.gn'),1,150),
                          excerpt(r/(project+'/src/native_module.cpp'),20,130),
                          excerpt(r/'build/ohos/ace/ace.gni',24,68),
                          excerpt(r/'build/hb/modules/ohos_build_module.py',80,130),
                          excerpt(r/'build/hb/containers/arg.py',352,396),
                          excerpt(r/'arkcompiler/runtime_core/libpandafile/file.h',59,79)],
       'first_artifact_behavior_gate_passed':False,'ledger_closed':False,
       'image_extracted_or_verified':False,'actual_fresh_es2abc_execution_observed':False,
       'module_record_and_literal_binding_verified':False}
if current_args.exists():
    current=json.loads(current_args.read_text());value['persisted_hb_values']={k:current.get(k) for k in ('fast_rebuild','build_only_load')}
print(json.dumps(value,indent=2))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', default='ohos-qemu-parallel-source-20261016-02')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[5]
    helper = repo / 'ci/capability-audit/batch_apps_contact_payload.py'
    helper_data = helper.read_bytes()
    # A non-main namespace loads only the pure Python data reader; the source is
    # passed through stdin and never copied into or written inside the container.
    query = "__name__='readonly_contact_payload_inspection'\n" + helper_data.decode() + '\n' + QUERY
    command = ['docker', 'exec', '-i', args.container, 'python3', '-']
    completed = subprocess.run(command, input=query, text=True, capture_output=True, check=False, timeout=30)
    if completed.returncode:
        raise RuntimeError('read-only query failed: ' + completed.stderr)
    value = json.loads(completed.stdout)
    value['inspection'] = {'argv': command, 'exit_code': completed.returncode,
                           'query_sha256': hashlib.sha256(query.encode()).hexdigest(),
                           'payload_reader_sha256': hashlib.sha256(helper_data).hexdigest(),
                           'container_writes': False, 'native_or_build_tools_executed': False}
    runner = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/scripts/build_standard_qemu_in_docker.sh')
    runner_data = runner.read_bytes()
    value['parent_runner_readonly'] = {'path': str(runner), 'sha256': hashlib.sha256(runner_data).hexdigest(),
        'selected_lines': [{'line': i+1, 'text': line} for i, line in enumerate(runner_data.decode().splitlines())
                           if 'fast-rebuild' in line or 1570 <= i+1 <= 1582 or 1618 <= i+1 <= 1634]}
    with args.output.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
