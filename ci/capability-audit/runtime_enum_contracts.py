"""Typed and independent NAPI reads of all original regular-enum findings.

SDK constant values are expectations only, never the native probe's results.
The ambient Curve declaration has no compiler-resolved values and remains an
explicit unresolved requirement; this collector cannot attest its behavior.
"""
import json
from pathlib import Path
import re
import subprocess

from const_enum_contracts import LEDGER, sha256

HERE = Path(__file__).resolve().parent
NATIVE = HERE / 'runtime_enum_hap_probe.cpp'
SCOPE = 'complete_original_regular_enum_member_collection_NOT_backend_behavior'
UNRESOLVED = ('@ohos.curves', 'Curve')


def requested(device):
    if device not in ('phone', '2in1'):
        raise ValueError('unknown enum device profile')
    return [{'module': row['module'], 'contracts': [{'name': item['name']} for item in row['missing']
             if item['kind'] == 'enum']} for row in json.loads(LEDGER.read_text())['devices'][device]
            ['arkts11_runtime_export_gaps'] if any(item['kind'] == 'enum' for item in row['missing'])]


def expected(sdk, device):
    sdk = Path(sdk).resolve()
    script = '''
const m=require(process.argv[1]);const ts=require(process.argv[2]);
const requests=JSON.parse(process.argv[4]);let contracts=[],unresolved=[];
for(const r of requests) for(const c of r.contracts) {
  try {
    const extracted=m.extract(ts,process.argv[3],[{module:r.module,contracts:[c]}],false);
    if(r.module==='@ohos.ability.particleAbility'&&c.name==='ErrorCode') {
      const fs=require('fs');const file=extracted[0].sdk_declaration;
      const source=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true);
      const namespace=source.statements.find(ts.isModuleDeclaration);
      if(!namespace||!ts.getJSDocTags(namespace).some(tag=>tag.tagName.text==='famodelonly'))
        throw Error('SDK FA-only contract changed');
      unresolved.push({module:r.module,name:c.name,reason:'actual SDK requires FA model; this caller is Stage',
        sdk_declaration:file,sdk_declaration_sha256:extracted[0].sdk_declaration_sha256});
    } else contracts.push(...extracted);
  }
  catch(error) {
    if(r.module!=='@ohos.curves'||c.name!=='Curve'||
       error.message!=='not a compiler-resolved enum constant: Linear') throw error;
    unresolved.push({module:r.module,name:c.name,reason:error.message});
  }
}
process.stdout.write(JSON.stringify({contracts,unresolved}));
'''
    result = subprocess.run(['node', '-e', script, str(HERE / 'extract_const_enum_contracts.cjs'),
        str(sdk / 'ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js'),
        str(sdk / 'ets/api'), json.dumps(requested(device))], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def generate(contracts, run_id):
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh regular-enum challenge required')
    imports, reads, seen = [], [], set()
    for index, contract in enumerate(contracts):
        module, name = contract['module'], contract['name']
        if (module, name) in seen or not re.fullmatch(r'@ohos\.[A-Za-z0-9_.]+', module):
            raise ValueError('duplicate or invalid SDK enum')
        seen.add((module, name))
        if not re.fullmatch('[A-Za-z_$][A-Za-z0-9_$]*', name):
            raise ValueError('invalid SDK enum identifier')
        alias = 'EnumModule' + str(index)
        if contract['import_kind'] == 'named':
            imports.append('import { ' + name + ' as ' + alias + " } from '" + module + "';")
            expression = alias
        elif contract['import_kind'] == 'default_namespace':
            imports.append('import ' + alias + " from '" + module + "';")
            expression = alias + '.' + name
        else:
            raise ValueError('unsupported SDK enum import')
        members = [item['name'] for item in contract['members']]
        if not members or len(set(members)) != len(members) or any(
                re.fullmatch('[A-Za-z_$][A-Za-z0-9_$]*', item) is None for item in members):
            raise ValueError('invalid or empty SDK enum members')
        reads += ['    {', '      let values: (number | string)[] = [];', '      let typedException: boolean = false;',
            '      try { values = [' + ', '.join(expression + '.' + item for item in members) + ']; }',
            '      catch (_) { typedException = true; }',
            '      this.record({ runId: this.runId, module: ' + json.dumps(module) + ', name: ' + json.dumps(name) + ',',
            '        values: values, typedException: typedException, native: probe.inspect(' + json.dumps(module) +
            ', ' + json.dumps(name) + ', ' + json.dumps(members) + ') });', '    }']
    if not seen:
        raise ValueError('empty original enum collection cannot pass')
    return '\n'.join(imports) + "\nimport fs from '@ohos.file.fs';\nimport probe from 'libruntimeenumprobe.so';\n" + '''
interface NativeEnum { values: (number | string)[]; statuses: number[]; types: number[]; own: boolean[]; exception: boolean; }
interface Observation { runId: string; module: string; name: string; values: (number | string)[];
  typedException: boolean; native: NativeEnum; }
@Entry
@Component
struct Index {
  @State private note: string = 'Reading actual public enum members';
  private readonly runId: string = '__RUN__';
  private readonly path: string = '/data/storage/el2/base/files/runtime-enum-__RUN__-results.log';
  private record(value: Observation): void {
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(value) + '\\n');
    fs.closeSync(file);
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file);
__READS__
    const done = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.APPEND);
    fs.writeSync(done.fd, JSON.stringify({ runId: this.runId, summary: __COUNT__ }) + '\\n');
    fs.closeSync(done);
    this.note = 'Actual public enum collection completed';
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
'''.replace('__RUN__', run_id).replace('__READS__', '\n'.join(reads)).replace('__COUNT__', str(len(contracts)))


def inputs(project, sdk, arch, device, run_id):
    sdk = Path(sdk).resolve()
    page = Path(project) / 'entry/src/main/ets/pages/Index.ets'
    return {'schema_version': 1, 'role': 'ordinary_app', 'scope': SCOPE, 'run_id': run_id,
        'arch': arch, 'device': device, 'request_permissions': [], 'sdk': str(sdk),
        **expected(sdk, device), 'audit_baseline_sha256': sha256(LEDGER), 'generated_source': str(page),
        'generated_source_sha256': sha256(page), 'native_source_sha256': sha256(NATIVE),
        'generator_sha256': sha256(Path(__file__)), 'resolver_sha256': sha256(HERE / 'extract_const_enum_contracts.cjs'),
        'typescript_sha256': sha256(sdk / 'ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js')}


def verify_inputs(value, run_id, arch):
    sdk, page = Path(value['sdk']), Path(value['generated_source'])
    actual = expected(sdk, value['device'])
    if (type(value.get('schema_version')) is not int or value['schema_version'] != 1 or
            value.get('role') != 'ordinary_app' or value.get('scope') != SCOPE or
            value.get('run_id') != run_id or value.get('arch') != arch or
            value.get('request_permissions') != [] or value.get('audit_baseline_sha256') != sha256(LEDGER) or
            page.is_symlink() or sha256(page) != value.get('generated_source_sha256') or
            page.read_text() != generate(actual['contracts'], run_id) or
            any(value.get(key) != actual[key] for key in ('contracts', 'unresolved')) or
            sha256(NATIVE) != value.get('native_source_sha256') or
            sha256(Path(__file__)) != value.get('generator_sha256') or
            sha256(HERE / 'extract_const_enum_contracts.cjs') != value.get('resolver_sha256') or
            sha256(sdk / 'ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js') !=
            value.get('typescript_sha256')):
        raise ValueError('enum caller/compiler/SDK must match all unchanged original findings')
    return actual['contracts']
