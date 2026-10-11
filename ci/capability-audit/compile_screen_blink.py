"""Read-only real NAPI/client/service/generated IPC compile, not runtime proof."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from compile_always_on_vpn import query
from compile_taskpool_thread_info import PRODUCTS, digest
from compile_render_connection_reply import prepare_missing_idl

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--source-root', type=Path, required=True)
parser.add_argument('--product', choices=PRODUCTS, action='append')
args = parser.parse_args()
source = args.source_root.resolve()
project = Path('foundation/barrierfree/accessibility')
idl = project / 'common/interface'
args.output.mkdir(parents=True, exist_ok=False)
assert all(os.statvfs(path).f_flag & os.ST_RDONLY for path in (source, source / 'out'))
root = Path(__file__).resolve().parents[2]
component = root / 'patches/common/foundation/barrierfree/accessibility/screen_blink'
spec = importlib.util.spec_from_file_location('blink_baseline', component / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
assert baseline.validate(source) is False, 'requires exact prior enum stack'
stage_root = args.output / 'source'
stage = stage_root / project
original_hashes = {}
for relative, old, new in baseline.FILES:
    source_path = source / project / relative
    destination = stage / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    original_hashes[relative] = digest(source_path) if source_path.exists() else None
    if source_path.exists():
        shutil.copy2(source_path, destination)
for attempt in (1, 2):
    with (args.output / f'apply-{attempt}.log').open('x') as log:
        subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(stage_root)],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
baseline.validate(stage_root, require_patched=True)
files = sorted(p for p in stage.rglob('*') if p.is_file())
before = {str(p.relative_to(stage)): digest(p) for p in files}
report = dict(status='fail', scope='actual_product_TUs_and_generated_IPC_NOT_link_or_guest',
              candidate_sha256=before, first_artifact_behavior_gate_passed=False, commands=[], generations=[])
targets = [
    'obj/' + str(project) + '/interfaces/kits/napi/accessibility_config/src/config_napi/native_module.o',
    'obj/' + str(project) + '/frameworks/acfwk/src/accessibilityconfig/accessibility_config.o',
    'obj/' + str(project) + '/frameworks/acfwk/src/accessibilityconfig/accessibility_config_impl.o',
    'obj/' + str(project) + '/services/aams/src/accessibleabilityms/accessible_ability_manager_service.o',
    'obj/out/{product}/gen/' + str(idl) + '/accessibility_interface/accessible_ability_manager_service_proxy.o',
    'obj/out/{product}/gen/' + str(idl) + '/accessibility_interface/accessible_ability_manager_service_stub.o',
]
try:
    for product in args.product or PRODUCTS:
        cwd = source / 'out' / product
        out = args.output / product
        out.mkdir()
        original = query(source, cwd, str(Path('gen') / idl / 'iaccessible_ability_manager_service.h'), out / 'idl-query.log')
        command = [','.join(str(source / part.removeprefix('/openharmony/')) if part.startswith('/openharmony/')
                           else part for part in token.split(',')) for token in original]
        assert command[:2] == ['/usr/bin/env', '../../build/config/components/idl_tool/idl.py']
        assert all(command.count(flag) == 1 for flag in ('--src-idl', '--dst-path', '--dst-file', '--idl-tool-path'))
        inputs, generated = out / 'idl-inputs', out / 'generated'
        inputs.mkdir()
        for path in (source / idl).glob('*.idl'):
            replacement = stage / 'common/interface' / path.name
            shutil.copy2(replacement if replacement.exists() else path, inputs / path.name)
        destination = cwd / 'gen' / idl
        assert Path(command[command.index('--dst-path') + 1]) == destination
        srcs = command[command.index('--src-idl') + 1].split(',')
        dsts = command[command.index('--dst-file') + 1].split(',')
        assert all(Path(p).parent == source / idl for p in srcs)
        assert all(Path(p).parent == destination for p in dsts)
        command[command.index('--src-idl') + 1] = ','.join(str(inputs / Path(p).name) for p in srcs)
        command[command.index('--dst-file') + 1] = ','.join(str(generated / Path(p).name) for p in dsts)
        command[command.index('--dst-path') + 1] = str(generated)
        with (out / 'idl-generate.log').open('x') as log:
            subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True)
        assert 'ControlBlinking' in (generated / 'iaccessible_ability_manager_service.h').read_text()
        generated_files = sorted(p for p in generated.iterdir() if p.suffix in ('.h', '.cpp'))
        report['generations'].append(dict(product=product, original_argv=original, argv=command,
            input_sha256={p.name: digest(p) for p in inputs.iterdir()},
            output_sha256={p.name: digest(p) for p in generated_files}))
        entries = [{'type': 'file', 'name': str(source / project / p.relative_to(stage)),
                    'external-contents': str(p)} for p in files]
        entries += [{'type': 'file', 'name': str(destination / p.name), 'external-contents': str(p)} for p in generated_files]
        overlay = out / 'vfs.json'
        overlay.write_text(json.dumps(dict(version=0, roots=entries), indent=2) + '\n')
        candidates = {entry['name']: entry['external-contents'] for entry in entries}
        for index, target in enumerate(targets):
            prefix = str(index)
            original = query(source, cwd, target.format(product=product), out / (prefix + '-query.log'))
            argv = original[:]
            if Path(argv[0]).name == 'ccache':
                argv.pop(0)
            assert Path(argv[0]).name == 'clang++' and '--target=' + PRODUCTS[product] in argv
            assert all(argv.count(flag) == 1 for flag in ('-c', '-o', '-MF'))
            unit = (cwd / argv[argv.index('-c') + 1]).resolve()
            assert str(unit) in candidates
            argv[argv.index('-c') + 1] = candidates[str(unit)]
            argv[1:1] = ['-ivfsoverlay', str(overlay)]
            obj, deps = out / (prefix + '.o'), out / (prefix + '.d')
            argv[argv.index('-o') + 1] = str(obj)
            argv[argv.index('-MF') + 1] = str(deps)
            dependency_output = out / ('dependencies-' + prefix)
            dependency_output.mkdir()
            argv, dependency_generation = prepare_missing_idl(source, cwd, argv, dependency_output,
                                                               copy_readonly_inputs=True)
            argv[1:1] = ['-I' + str(generated)]
            log = out / (prefix + '-compile.log')
            with log.open('x') as stream:
                result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                        env=dict(os.environ, CCACHE_DISABLE='1'))
            row = dict(product=product, index=index, original_argv=original, argv=argv,
                       exit_code=result.returncode, log_sha256=digest(log),
                       dependency_idl=dependency_generation)
            report['commands'].append(row)
            assert result.returncode == 0, f'actual TU failed: {product}/{index}'
            assert candidates[str(unit)] in deps.read_text()
            row.update(object_sha256=digest(obj), dependencies_sha256=digest(deps))
    assert before == {str(p.relative_to(stage)): digest(p) for p in files}
    assert original_hashes == {relative: digest(source / project / relative)
                              if (source / project / relative).exists() else None
                              for relative in original_hashes}
    report['original_sha256'] = original_hashes
    report['status'] = 'pass'
except Exception as error:
    report['error'] = type(error).__name__ + ': ' + str(error)
(args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
raise SystemExit(report['status'] != 'pass')
