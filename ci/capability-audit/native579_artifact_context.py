"""Pure actual-product native context; no subprocess, SDK or resource action.

Every original per-kind oracle still owns its source/commands/semantics. This
module only joins the actual target/profile and retained normal-link bytes so
those oracles never reinterpret ELF32 as ELF64 or silently accept another ABI.
"""
from pathlib import Path
import json

import batch_system_build_runtime_helpers as product


def need(value, message):
    if not value:
        raise ValueError(message)


def checked(row):
    need(type(row) is dict and set(row) in ({'path', 'sha256'}, {'path', 'sha256', 'bytes'}),
         'actual immutable native Ref2/3 required')
    path = Path(row['path'])
    need(path.is_absolute() and path.resolve() == path and path.is_file() and
         not any(p.is_symlink() for p in (path, *path.parents)), 'actual regular native artifact required')
    need(product.sha(path) == row['sha256'] and
         ('bytes' not in row or type(row['bytes']) is int and path.stat().st_size == row['bytes']),
         'actual native artifact changed')
    return path


def replay_normal_link(report, artifact):
    """Reinvoke the original strict normal-link parser using retained raw bytes.

    artifact(ref) is the owning original decoder's existing finite private-prefix
    mapping. It must check SHA itself; this function checks returned bytes again.
    No path from DATA selects code or a program, and nothing is executed.
    """
    selected = report['product']; product.target_spec(selected)
    normal = report.get('normal_link_contract')
    if normal is None:
        need(selected == product.PRODUCT, 'nondefault actual normal-link raw chain missing')
        return None
    copies = report.get('normal_link_artifacts')
    expected = {'binary': normal['binary'], **{str(i): row for i, row in enumerate(normal['CRT'])}}
    need(len(normal['CRT']) == 3, 'original exact normal-link CRT grammar required')
    wrapper = normal.get('wrapper')
    if wrapper is not None:
        need(type(wrapper) is dict and wrapper.get('schema') == 'actual-normal-gcc-link-wrapper579/v1' and
             len(wrapper.get('grammar_sources', [])) == len(product.NORMAL_LINK_GRAMMAR579),
             'fixed official wrapper grammar-source vector required')
        expected.update({'grammar' + str(i): row for i, row in enumerate(wrapper['grammar_sources'])})
    need(type(copies) is dict and set(copies) == set(expected),
         'actual retained normal executable/three CRTs/selected grammar sources required')
    source_paths = {}
    for key, source in expected.items():
        row = copies[key]
        need(type(row) is dict and set(row) == {'source', 'retained'} and row['source'] == source and
             report['inputs'].get(source['path']) == source,
             'actual source/normal retained-byte identity differs')
        path = Path(artifact(row['retained']))
        need(product.sha(path) == source['sha256'] == row['retained']['sha256'] and
             path.stat().st_size == source['bytes'] == row['retained']['bytes'],
             'actual normal executable/CRT raw changed')
        need(source['path'] not in source_paths, 'normal executable/CRT alias')
        source_paths[source['path']] = (source, path)
    commands = [row for row in report['commands'] if row['label'] == 'actual-normal-executable-link-command']
    need(len(commands) == 1, 'one original actual normal executable Ninja query required')
    command = commands[0]; argv = command['argv']
    need(type(command.get('exit_code')) is int and command['exit_code'] == 0 and
         not command.get('timed_out') and command['cwd'] == report['build_directory'] and
         len(argv) == 9 and Path(argv[0]).name == 'ninja' and
         argv[1:] == ['-w', 'dupbuild=warn', '-C', report['build_directory'], '-t', 'commands', '-s', normal['target']],
         'actual normal executable query argv/status differs')
    # The query actually has nine argv entries including its literal driver.
    # Do not infer it from a success summary: the complete log is replayed.
    stdout_ref, stderr_ref = product.normal_query_streams579(command)
    retained_streams = []
    for raw in (stdout_ref, stderr_ref):
        path = Path(artifact(raw))
        need(product.sha(path) == raw['sha256'] and path.stat().st_size == raw['bytes'],
             'actual complete normal stdout/stderr stream changed')
        retained_streams.append(path)
    query = retained_streams[0]
    need(report['build_directory'] == str(Path(report['source_root']) / 'out' / selected),
         'normal source/out product differs')
    edge_text = None; rule_observation = None
    if wrapper is not None:
        edge_rows = [row for row in report['commands'] if row['label'] == 'actual-normal-executable-input-edge']
        need(len(edge_rows) == 1, 'one original actual normal input-edge query required')
        edge_row = edge_rows[0]
        need(type(edge_row.get('exit_code')) is int and edge_row['exit_code'] == 0 and
             not edge_row.get('timed_out') and edge_row['cwd'] == report['build_directory'] and
             edge_row['argv'] == [argv[0], '-w', 'dupbuild=warn', '-C', report['build_directory'],
                                  '-t', 'query', normal['target']],
             'actual normal input-edge query argv/status differs')
        edge_stdout, edge_stderr = product.normal_query_streams579(edge_row)
        retained_edge_streams = []
        for raw in (edge_stdout, edge_stderr):
            path = Path(artifact(raw))
            need(product.sha(path) == raw['sha256'] and path.stat().st_size == raw['bytes'],
                 'actual complete normal edge stdout/stderr stream changed')
            retained_edge_streams.append(path)
        edge_text = retained_edge_streams[0].read_text()
        rule_artifact = report.get('normal_link_rule_artifact')
        need(type(rule_artifact) is dict and set(rule_artifact) == {'source', 'retained'} and
             rule_artifact['source'] == wrapper['generated_rule'], 'generated rule cut identity differs')
        meta = rule_artifact['source']; source = meta['source']
        need(report['inputs'].get(source['path']) == source and
             source['path'] == str(Path(report['build_directory']) / 'toolchain.ninja') and
             source['path'] not in source_paths, 'actual full toolchain input identity differs')
        rule_raw = Path(artifact(rule_artifact['retained']))
        need(product.sha(rule_raw) == meta['sha256'] == rule_artifact['retained']['sha256'] and
             rule_raw.stat().st_size == meta['bytes'] == rule_artifact['retained']['bytes'],
             'retained bounded generated rule cut changed')
        source_paths[source['path']] = (source, None)
        rule_observation = {'source': source, 'first_line': meta['first_line'],
            'last_line': meta['last_line'], 'text': rule_raw.read_text()}
    tools = report['normal_link_tools']
    need(set(tools) == {'compiler', 'c_compiler', 'ninja'}, 'actual normal query tool identities missing')
    for name, tool in tools.items():
        need(type(tool) is dict and set(tool) == {'literal', 'file'} and
             report['inputs'].get(tool['file']['path']) == tool['file'] and
             Path(tool['literal']).is_absolute() and
             Path(tool['literal']).name == {'compiler':'clang++', 'c_compiler':'clang', 'ninja':'ninja'}[name],
             'actual normal source tool literal/hash binding differs')
    need(argv[0] == tools['ninja']['literal'], 'actual Ninja literal differs')

    class Readback:
        def __init__(self):
            self.product = selected
            self.root = Path(report['source_root'])
            self.build = Path(report['build_directory'])
            self.compiler = Path(tools['compiler']['literal'])
            self.c_compiler = Path(tools['c_compiler']['literal'])
            self.installed_runtime = report['installed_runtime_profile']
            self.normal_link_edge_text = edge_text
            self.normal_link_rule_observation = rule_observation

        def remember(self, path):
            key = str(Path(path))
            need(key in source_paths, 'normal parser requested an unretained source input')
            return source_paths[key][0]

        def read_normal_file(self, path):
            key = str(Path(path))
            need(key in source_paths and source_paths[key][1] is not None,
                 'normal parser requested unretained executable bytes')
            return source_paths[key][1]

    rebuilt = product.Builder.normal_link_contract(Readback(), normal['target'], query.read_text())
    need(rebuilt == normal, 'normal target/CRT/ABI/interpreter raw replay differs')
    return rebuilt


def binding_context(report, row, binary, artifact):
    """Target portion only; original complete per-kind oracle remains required."""
    profile = row['installed_runtime_profile']['profile']
    product.validate_installed_profile(profile)
    selected = profile['product']; target = product.target_spec(selected)
    need(report['product'] == selected and report['installed_runtime_profile'] == row['installed_runtime_profile'],
         'native row/profile/report target differs')
    profile_raw = report['profile_raw']
    profile_file = artifact(profile_raw)
    expected_profile = row['installed_runtime_profile']['source']
    need(product.sha(profile_file) == profile_raw['sha256'] == expected_profile['sha256'] and
         Path(profile_file).stat().st_size == profile_raw['bytes'] == expected_profile['bytes'] and
         json.loads(Path(profile_file).read_text()) == profile, 'actual complete native profile changed')
    normal = replay_normal_link(report, artifact)
    actual_target = None if normal is None else normal['compiler_target']
    compile_argv, link_argv = row['compile_command'], row['link_command']
    if row.get('language') == 'c':
        product.validate_c_flags(compile_argv, product=selected, actual_target=actual_target)
    else:
        product.validate_flags(compile_argv, product=selected, actual_target=actual_target)
    need(any(flag == '-flto' or flag.startswith('-flto=') for flag in link_argv),
         'actual original link LTO must remain enabled')
    if row.get('language') == 'c':
        need(row['CFI_preserved'] == product.effective_cfi(compile_argv) == product.effective_cfi(link_argv),
             'actual C GN CFI selection must be preserved, never fabricated')
    else:
        need(product.effective_cfi(link_argv) and row['CFI_preserved'] is True,
             'actual original C++ link CFI must remain enabled')
    if normal is not None:
        need(row.get('normal_link_contract') == normal and
             product.compiler_target(link_argv) == actual_target and
             product.abi_options(link_argv) == normal['abi_options'],
             'actual helper/normal target/float-call ABI differs')
        need(product.machine_abi_flags(binary, selected) == normal['machine_abi_flags'],
             'actual helper machine ABI differs from retained normal executable')
    interpreter = None if normal is None else normal['interpreter']
    elf = product.elf_header(binary, executable=row.get('elf_kind') != 'shared_napi',
        shared=row.get('elf_kind') == 'shared_napi', product=selected, interpreter_path=interpreter)
    need(elf == row['elf'], 'actual helper class/machine/bytes differ')
    return {'product': selected, 'arch': target['arch'], 'target': target,
            'compiler_target': actual_target, 'interpreter': interpreter, 'normal': normal}
