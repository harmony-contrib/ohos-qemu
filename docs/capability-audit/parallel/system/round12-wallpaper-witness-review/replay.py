#!/usr/bin/env python3
"""Pure reviewed-predicate replay; no compile, GN, Ninja, Docker or guest calls."""
import ast
import hashlib
import importlib
import json
from pathlib import Path
import re
import shlex
import sys

HERE = Path(__file__).resolve().parent
inputs = json.loads((HERE / 'inputs.json').read_text())
data = (HERE / 'reviewed-guard.txt').read_bytes()
assert hashlib.sha256(data).hexdigest() == inputs['reviewed_uncommitted_guard']['excerpt_sha256']
tree = ast.parse(data)
nodes = [n for n in tree.body if isinstance(n, ast.Assign) and
         any(isinstance(t, ast.Name) and t.id in ('BASE', 'UNITS', 'PRODUCTS') for t in n.targets) or
         isinstance(n, ast.FunctionDef) and n.name in ('compile_check', 'selected_args')]
namespace = {'Path': Path, 're': re, 'shlex': shlex}
exec(compile(ast.Module(body=nodes, type_ignores=[]), '<exact-reviewed-predicates>', 'exec'), namespace)
query = (HERE / 'actual-wallpaper-query.log').read_bytes()
assert hashlib.sha256(query).hexdigest() == inputs['actual_prior_compile_query']['sha256']
commands = [line for line in query.decode().splitlines() if 'clang++ ' in line and ' -c ' in line]
assert len(commands) == 1
command = commands[0]
macro_added_only_to_parser_input = '-DQEMU_WALLPAPER_RENDERER' not in command
if macro_added_only_to_parser_input: command = command.replace(' -c ', ' -DQEMU_WALLPAPER_RENDERER -c ', 1)


def replay(module):
    def accepted(fn, *args):
        try: fn(*args); return True
        except ValueError: return False
    return {'valid_command': accepted(module['compile_check'], command, namespace['UNITS'][0], 'arm64_virt'),
        'cancelled_protection_commands': {tail: accepted(module['compile_check'], command + ' ' + tail, namespace['UNITS'][0], 'arm64_virt')
            for tail in ('-fno-sanitize=cfi', '-fno-sanitize=all', '-fno-lto', '-fexceptions', '-frtti')},
        'unrelated_false_arg': accepted(module['selected_args'], 'theme_service\n Current value = true\nother_argument\n Current value = false\n'),
        'actual_selected_false': accepted(module['selected_args'], 'theme_service\n Current value = false\n')}


result = {'scope': 'pure reviewed parser/control-flow reproduction ONLY',
    'reviewed_guard_sha256_observed_before_root_fix': inputs['reviewed_uncommitted_guard']['sha256_observed_before_root_fix'],
    'reviewed_predicate_excerpt_sha256': inputs['reviewed_uncommitted_guard']['excerpt_sha256'],
    'actual_query_sha256': inputs['actual_prior_compile_query']['sha256'],
    'macro_added_only_to_parser_input_NOT_actual_GN_selection': macro_added_only_to_parser_input,
    'reviewed_behavior': replay(namespace), 'native_or_GN_or_guest_executed': False}
if len(sys.argv) == 2:
    root = Path(sys.argv[1]).resolve(); sys.path.insert(0, str(root / 'scripts'))
    before = (root / 'scripts/qemu_wallpaper_build_witness.py').read_bytes()
    current = importlib.import_module('qemu_wallpaper_build_witness')
    after = Path(current.__file__).read_bytes(); assert before == after, 'root changed during read-only import'
    result['current_root_guard_sha256'] = hashlib.sha256(after).hexdigest()
    result['current_root_behavior'] = replay(vars(current))
print(json.dumps(result, indent=2))
