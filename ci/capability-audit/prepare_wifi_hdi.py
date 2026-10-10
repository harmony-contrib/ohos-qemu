"""Generate the actual product's WPA/hostapd C HDI into private scratch."""
from pathlib import Path
import shlex
import shutil
import subprocess

from prepare_display_hdi import sha


def prepare(root, cwd, command, output):
    output.mkdir(exist_ok=False)
    targets = ['gen/drivers/interface/wlan/hostapd/v1_0/ihostapd_interface.h',
               'gen/drivers/interface/wlan/wpa/v2_0/iwpa_interface.h']
    result = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', *targets],
        capture_output=True, text=True, check=True)
    (output / 'query.stdout').write_text(result.stdout)
    (output / 'query.stderr').write_text(result.stderr)
    interface = root / 'drivers/interface'
    owned_inputs = output / 'idl-inputs'
    inputs = {}
    for source in (interface / 'wlan').rglob('*.idl'):
        destination = owned_inputs / source.relative_to(interface)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        inputs[str(source)] = sha(source)
    lines = result.stdout.strip().splitlines()
    if len(lines) != 2:
        raise ValueError('expected two actual WPA/hostapd HDI actions')
    records = []
    generated = output / 'gen/drivers/interface'
    generated.mkdir(parents=True)
    for index, line in enumerate(lines):
        argv = shlex.split(line)
        while argv and argv[0] == '/usr/bin/env':
            argv.pop(0)
        if (not argv or Path(argv[0]).name != 'idl' or argv.count('-d') != 1 or
                argv.count('-r') != 1 or '--gen-c' not in argv or
                argv[argv.index('--intf-type') + 1] != 'hdi'):
            raise ValueError('unexpected Wi-Fi HDI generator command')
        mapping = argv[argv.index('-r') + 1]
        if not mapping.startswith('ohos.hdi:'):
            raise ValueError('unexpected HDI package mapping')
        original_interface = Path(mapping.removeprefix('ohos.hdi:'))
        original_root = original_interface.parent.parent
        if original_root not in (root, Path('/openharmony')) or original_interface != original_root / 'drivers/interface':
            raise ValueError('unrecognized product build-root relocation')
        relative_tool = Path('out') / cwd.name / 'clang_x64/ability/idl_tool/idl'
        if Path(argv[0]) != original_root / relative_tool:
            raise ValueError('HDI generator must belong to the selected actual product')
        tool = root / relative_tool
        if not tool.is_file():
            raise ValueError('actual product HDI host generator missing')
        revised = argv[:]
        revised[0] = str(tool)
        revised[revised.index('-d') + 1] = str(generated)
        revised[revised.index('-r') + 1] = 'ohos.hdi:' + str(owned_inputs)
        for position, token in enumerate(argv):
            if token == '-c':
                source = Path(argv[position + 1])
                relative = source.relative_to(original_interface)
                relocated_source = interface / relative
                if sha(relocated_source) != inputs[str(relocated_source)]:
                    raise ValueError('actual HDI action differs from pinned Wi-Fi declarations')
                revised[position + 1] = str(owned_inputs / relative)
        log = output / ('generate-' + str(index) + '.log')
        with log.open('x') as stream:
            subprocess.run(revised, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=True)
        records.append(dict(actual_gn_command=line, owned_command=revised,
                            tool_sha256=sha(tool), log=str(log), log_sha256=sha(log),
                            source_root_relocation=dict(original=str(original_root), actual=str(root))))
    for target in targets:
        if not (output / target).is_file():
            raise ValueError('actual HDI generator did not produce required Wi-Fi header')
    if any(sha(Path(path)) != value for path, value in inputs.items()):
        raise ValueError('pinned Wi-Fi IDL input changed')
    headers = {str(path): sha(path) for path in generated.rglob('*.h')}
    rewritten = []
    for token in command:
        if token.startswith('-Igen/drivers/interface'):
            rewritten.append('-I' + str(output / token[2:]))
        rewritten.append(token)
    return rewritten, [dict(kind='actual_product_wifi_hdi', input_sha256=inputs,
                            generated_header_sha256=headers, actions=records)]
