"""Freeze actual SDK factory/class signatures and the ordinary typed caller."""
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(1, str(ROOT / 'ci/capability-audit'))
from run_root_probe import digest

TEMPLATE = Path(__file__).with_name('binding_probe.ets')
SCOPE = 'actual_UIUtils_factory_returned_Binding_MutableBinding_getter_setter_NOT_constructors_or_persistence'


def sdk_contract(sdk):
    sdk = Path(sdk)
    declaration = sdk / 'ets/api/@ohos.arkui.StateManagement.d.ts'
    typescript = sdk / 'ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js'
    script = r"""
const fs=require('fs'),ts=require(process.argv[1]);
const source=ts.createSourceFile(process.argv[2],fs.readFileSync(process.argv[2],'utf8'),ts.ScriptTarget.Latest,true);
const declarations={};
function walk(node) {
 if(ts.isClassDeclaration(node)&&node.name&&['Binding','MutableBinding','UIUtils'].includes(node.name.text)) {
  if(declarations[node.name.text]) throw Error('duplicate actual SDK binding class');
  declarations[node.name.text]=node;
 }
 ts.forEachChild(node,walk);
}
walk(source);
const wanted={Binding:['GetAccessor'],MutableBinding:['GetAccessor','SetAccessor']};
for(const name of Object.keys(wanted)) {
 const node=declarations[name];
 if(!node||node.members.length!==wanted[name].length||node.members.some((m,i)=>
  ts.SyntaxKind[m.kind]!==wanted[name][i]||m.name.text!=='value')) throw Error('actual SDK class contract changed');
}
const factories=declarations.UIUtils.members.filter(m=>m.name&&m.name.text==='makeBinding');
if(factories.length!==2||factories[0].parameters.length!==1||factories[1].parameters.length!==2||
 factories[0].type.getText(source)!=='Binding<T>'||factories[1].type.getText(source)!=='MutableBinding<T>')
 throw Error('real public SDK binding factory overloads changed');
process.stdout.write(JSON.stringify(['Binding','MutableBinding']));
"""
    result = subprocess.run(['node', '-e', script, str(typescript), str(declaration)],
        check=True, capture_output=True, text=True)
    if json.loads(result.stdout) != ['Binding', 'MutableBinding']:
        raise ValueError('actual public SDK factory-returned class signatures required')
    return declaration, typescript


def inputs(project, sdk, arch, run_id):
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh binding-factory challenge required')
    declaration, typescript = sdk_contract(sdk)
    project = Path(project)
    page = project / 'entry/src/main/ets/pages/Index.ets'
    module = project / 'entry/src/main/module.json5'
    if json.loads(module.read_text())['module'].get('requestPermissions', []) != []:
        raise ValueError('ordinary data-binding caller must be permission-free')
    return {'schema_version': 1, 'role': 'ordinary_app', 'scope': SCOPE,
        'request_permissions': [], 'run_id': run_id, 'arch': arch,
        'sdk': str(Path(sdk).resolve()), 'sdk_declaration_sha256': digest(declaration),
        'typescript_sha256': digest(typescript), 'template_sha256': digest(TEMPLATE),
        'generated_source': str(page), 'generated_source_sha256': digest(page),
        'module_sha256': digest(module), 'contract_sha256': digest(Path(__file__)),
        'generations': 2, 'repeated_writes': 33,
        'not_claimed': 'SDK_constructor_exports_ConnectOptions_PersistenceV2_or_UI_redraw'}


def verify_inputs(value, run_id, arch):
    page = Path(value['generated_source'])
    if (page.is_symlink() or not page.is_file() or type(value.get('schema_version')) is not int or
            value != inputs(page.parents[5], value['sdk'], arch, run_id) or
            page.read_text() != TEMPLATE.read_text().replace('__BINDING_RUN_ID__', run_id)):
        raise ValueError('original compiled public factory caller and SDK contract changed')
