"""Generate a typed SDK caller for all baseline const-enum members.

This tests the compiler/inlined numeric or string contracts only, not any
associated service, class export, system capability or permission grant.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / 'docs/capability-audit/native-arkts11-gap-ledger.json'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected_contracts(sdk, device='phone'):
    sdk = Path(sdk).resolve()
    typescript = sdk / 'ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js'
    command = ['node', str(Path(__file__).with_name('extract_const_enum_contracts.cjs')),
               '--typescript', str(typescript), '--api-dir', str(sdk / 'ets/api'),
               '--ledger', str(LEDGER), '--device', device]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def generate(contracts, run_id):
    if not re.fullmatch('[0-9a-f]{32}', run_id):
        raise ValueError('fresh const-enum challenge required')
    imports, checks = [], []
    ids = set()
    count = 0
    for index, contract in enumerate(contracts):
        identifier = contract['module'] + ':' + contract['name']
        if identifier in ids:
            raise ValueError('duplicate enum contract')
        ids.add(identifier)
        alias = 'Contract' + str(index)
        if contract['import_kind'] == 'named':
            imports.append("import { " + contract['name'] + ' as ' + alias + " } from '" + contract['module'] + "';")
            expression = alias
        elif contract['import_kind'] == 'default_namespace':
            imports.append('import ' + alias + " from '" + contract['module'] + "';")
            expression = alias + '.' + contract['name']
        else:
            raise ValueError('unknown enum import kind')
        for member in contract['members']:
            if re.fullmatch('[A-Za-z_$][A-Za-z0-9_$]*', member['name']) is None:
                raise ValueError('invalid enum member name')
            key = 'const_enum:' + identifier + ':' + member['name']
            checks.append('    this.record(' + json.dumps(key) + ', ' + expression + '.' + member['name'] + ');')
            count += 1
    if not ids or not count:
        raise ValueError('empty enum contract cannot pass')
    source = '\n'.join(imports) + "\nimport fs from '@ohos.file.fs';\n" + '''
interface Result { name: string; value: number | string; runId: string; }
@Entry
@Component
struct Index {
  @State private note: string = 'Executing compiled SDK constant contracts';
  private readonly runId: string = '__RUN__';
  private readonly path: string = '/data/storage/el2/base/files/const-enum-__RUN__-results.log';
  private record(name: string, value: number | string): void {
    const result: Result = { name: name, value: value, runId: this.runId };
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, JSON.stringify(result) + '\\n');
    fs.closeSync(file);
  }
  aboutToAppear(): void {
    const file = fs.openSync(this.path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    fs.closeSync(file);
__CHECKS__
    this.record('summary', __COUNT__);
    this.note = 'Compiled constant contracts completed';
  }
  build() { Column() { Text(this.note) }.width('100%').height('100%') }
}
'''
    return source.replace('__RUN__', run_id).replace('__CHECKS__', '\n'.join(checks)).replace('__COUNT__', str(count))


def validate_inputs(inputs, sdk=None):
    if (inputs.get('role') != 'ordinary_app' or inputs.get('scope') != 'compiled_const_enum_contracts_only'
            or inputs.get('audit_baseline_sha256') != sha256(LEDGER)):
        raise ValueError('const-enum inputs must match complete current baseline')
    expected = [(row['module'], contract['name']) for row in json.loads(LEDGER.read_text())['devices']['phone']
                ['arkts11_compiled_constant_enum_contracts'] for contract in row['contracts']]
    contracts = inputs.get('contracts', [])
    if [(row['module'], row['name']) for row in contracts] != expected:
        raise ValueError('missing/reordered/broadened enum contracts')
    for row in contracts:
        if sha256(row['sdk_declaration']) != row['sdk_declaration_sha256']:
            raise ValueError('actual SDK declaration changed')
    sdk = sdk or inputs['sdk']
    if sha256(Path(sdk) / 'ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js') != inputs['typescript_sha256']:
        raise ValueError('actual SDK constant resolver changed')
    if contracts != expected_contracts(sdk):
        raise ValueError('member expectations differ from actual compiler-resolved SDK declarations')
    page = Path(inputs['generated_source'])
    if (sha256(page) != inputs['generated_source_sha256'] or
            page.read_text() != generate(contracts, inputs['run_id'])):
        raise ValueError('typed caller differs from all actual SDK members')
    return contracts
