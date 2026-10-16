#!/usr/bin/env python3
"""Observe the real e51 MMS policy comparator; do not sign/build/mock a HAP."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repository', type=Path, required=True)
    args = parser.parse_args()
    revision = 'e51e3fed3cabcaf605db46f46eb31962fa4a1150'
    sys.dont_write_bytecode = True
    sources = {}
    for name in ['calendar_provider', 'mms_provider']:
        raw = subprocess.check_output(['git', '-C', str(args.repository), 'show',
                                       revision + ':patches/lib/' + name + '.py'])
        module = types.ModuleType(name)
        module.__file__ = str(args.repository / 'patches/lib' / (name + '.py'))
        sys.modules[name] = module
        exec(compile(raw, module.__file__, 'exec'), module.__dict__)
        sources[name] = hashlib.sha256(raw).hexdigest()
    module = sys.modules['mms_provider']
    cases = []
    for name, expected in [('capability', module.CAPABILITY), ('grants', module.GRANTS)]:
        numeric = json.loads(json.dumps(expected))
        if name == 'capability':
            numeric['singleton'] = 1
            numeric['keepAlive'] = 0
        else:
            numeric['permissions'][0]['userCancellable'] = 1
            numeric['permissions'][1]['userCancellable'] = 0
        returned = json.loads(module.policy(json.dumps([numeric]).encode(), expected))
        assert returned[0]['app_signature'] == [module.SIGNATURE]
        if name == 'capability':
            assert type(returned[0]['singleton']) is int and type(returned[0]['keepAlive']) is int
        else:
            assert type(returned[0]['permissions'][0]['userCancellable']) is int
        cases.append({'kind': name, 'input': numeric, 'actual_accepted_output': returned})

    raw = subprocess.check_output(['git', '-C', str(args.repository), 'show',
                                   revision + ':patches/lib/mms_provider.py'])
    tree = ast.parse(raw)
    verify = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'verify')
    condition = next(n.test for n in verify.body if isinstance(n, ast.If) and
                     any(isinstance(x, ast.Constant) and x.value == 'unique original MMS preinstall directory required'
                         for x in ast.walk(n)))
    numeric = {'install_list': [{'app_dir': '/system/app/com.ohos.mms', 'removable': 0}]}
    rejects = eval(compile(ast.Expression(condition), '<actual-e51-install-list-predicate>', 'eval'),
                   {'installs': numeric['install_list']})
    assert rejects is False
    result = {'status': 'confirmed_e51_guard_type_gap', 'review_commit': revision,
              'actual_source_sha256': sources, 'actual_policy_calls': cases,
              'actual_source_install_list_predicate': {'input': numeric, 'rejects': rejects,
                  'scope': 'exact predicate extracted from real verify(); no full source/image/signature success claimed'},
              'root_followup': 'Root reports strict recursive same_json plus int-for-bool negative tests added; root owns their execution.',
              'products_built': 0, 'haps_signed': 0, 'images_tested': 0,
              'first_artifact_behavior_gate_passed': False}
    target = Path(__file__).with_name('boolean-boundary-results.json')
    target.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'policy_cases': len(cases), 'install_predicate_rejects_numeric_zero': rejects}))


if __name__ == '__main__':
    main()
