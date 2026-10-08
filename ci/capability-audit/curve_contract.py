"""Dedicated ambient Curve proof; the general numeric enum resolver stays unchanged."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ci/capability-audit'))
from run_root_probe import digest

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / 'curve_probe.ets'
NATIVE = ROOT / 'ci/capability-audit/runtime_enum_hap_probe.cpp'
SCOPE = 'actual_ambient_Curve_typed_native_strings_and_factory_interpolation_NOT_animation_scheduling'
PRESETS = (
    ('Linear', 'linear', None),
    ('Ease', 'ease', (.25, .1, .25, 1)),
    ('EaseIn', 'ease-in', (.42, 0, 1, 1)),
    ('EaseOut', 'ease-out', (0, 0, .58, 1)),
    ('EaseInOut', 'ease-in-out', (.42, 0, .58, 1)),
    ('FastOutSlowIn', 'fast-out-slow-in', (.4, 0, .2, 1)),
    ('LinearOutSlowIn', 'linear-out-slow-in', (0, 0, .2, 1)),
    ('FastOutLinearIn', 'fast-out-linear-in', (.4, 0, 1, 1)),
    ('ExtremeDeceleration', 'extreme-deceleration', (0, 0, 0, 1)),
    ('Sharp', 'sharp', (.33, 0, .67, 1)),
    ('Rhythm', 'rhythm', (.7, 0, .2, 1)),
    ('Smooth', 'smooth', (.4, 0, .4, 1)),
    ('Friction', 'friction', (.2, 0, .2, 1)),
)
TIMES = (-1, 0, .125, .25, .5, .75, 1, 2)


def sdk_contract(sdk):
    sdk = Path(sdk)
    declaration = sdk / 'ets/api/@ohos.curves.d.ts'
    typescript = sdk / 'ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js'
    script = r"""
const fs=require('fs'),ts=require(process.argv[1]);
const source=ts.createSourceFile(process.argv[2],fs.readFileSync(process.argv[2],'utf8'),ts.ScriptTarget.Latest,true);
const declarations=[];
function walk(node) {
 if(ts.isEnumDeclaration(node)&&node.name.text==='Curve') declarations.push(node);
 ts.forEachChild(node,walk);
}
walk(source);
if(declarations.length!==1||declarations[0].members.some(member=>member.initializer))
 throw Error('actual SDK ambient Curve declaration changed');
process.stdout.write(JSON.stringify(declarations[0].members.map(member=>member.name.text)));
"""
    result = subprocess.run(['node', '-e', script, str(typescript), str(declaration)],
                            capture_output=True, text=True, check=True)
    if json.loads(result.stdout) != [row[0] for row in PRESETS]:
        raise ValueError('every actual SDK Curve member is required, in original order')
    return declaration, typescript


def inputs(project, sdk, arch, run_id):
    declaration, typescript = sdk_contract(sdk)
    page = Path(project) / 'entry/src/main/ets/pages/Index.ets'
    module = Path(project) / 'entry/src/main/module.json5'
    if json.loads(module.read_text())['module'].get('requestPermissions', []) != []:
        raise ValueError('actual Curve caller must be permission-free')
    return {'schema_version': 1, 'role': 'ordinary_app', 'scope': SCOPE,
        'request_permissions': [], 'run_id': run_id, 'arch': arch, 'sdk': str(Path(sdk).resolve()),
        'sdk_declaration': str(declaration), 'sdk_declaration_sha256': digest(declaration),
        'typescript_sha256': digest(typescript), 'template_sha256': digest(TEMPLATE),
        'generated_source': str(page), 'generated_source_sha256': digest(page),
        'module_sha256': digest(module),
        'native_source_sha256': digest(NATIVE), 'contract_sha256': digest(Path(__file__)),
        'presets': [[name, value, list(points) if points else None] for name, value, points in PRESETS],
        'times': list(TIMES), 'repeats': 32, 'generations': 2,
        'native_cubic_x_residual_bound': .001,
        'not_claimed': 'exact_mathematical_Cubic_endpoints_or_animation_frame_scheduling'}


def verify_inputs(value, run_id, arch):
    if (type(value.get('schema_version')) is not int or value['schema_version'] != 1 or
        type(value.get('generations')) is not int or type(value.get('repeats')) is not int):
        raise ValueError('exact integer Curve schema/counts required')
    page = Path(value['generated_source'])
    if page.is_symlink() or not page.is_file():
        raise ValueError('owned actual generated Curve caller required')
    # Page is entry/src/main/ets/pages/Index.ets.
    project = page.parents[5]
    expected = inputs(project, value['sdk'], arch, run_id)
    if (value != expected or page.read_text() != TEMPLATE.read_text().replace('__CURVE_RUN_ID__', run_id)):
        raise ValueError('Curve caller/SDK/native source/contract inputs changed')
