"""Run actual product display HDI actions in isolated writable output."""
import hashlib
from pathlib import Path
import shlex
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(root, cwd, command, output, *, include_graphic_common=False):
    output.mkdir(exist_ok=False)
    targets = ['gen/drivers/interface/display/' + family + '/v1_0/display_' + family + '_type.h'
               for family in ('composer', 'buffer')]
    targets.append('gen/drivers/interface/display/buffer/v1_2/display_buffer_type.h')
    if include_graphic_common:
        targets += ['gen/drivers/interface/display/graphic/common/' + version + '/cm_color_space.h'
                    for version in ('v1_0', 'v2_0', 'v2_1', 'v2_2', 'v2_4')]
    result = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', *targets],
        capture_output=True, text=True, check=True)
    (output / 'query.stdout').write_text(result.stdout)
    (output / 'query.stderr').write_text(result.stderr)
    interface = root / 'drivers/interface'
    owned_inputs = output / 'idl-inputs'
    inputs = {}
    for source in interface.rglob('*.idl'):
        destination = owned_inputs / source.relative_to(interface)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        inputs[str(source)] = sha(source)
    records = []
    lines = result.stdout.strip().splitlines()
    if len(lines) != len(targets):
        raise ValueError('expected exactly ' + str(len(targets)) + ' real display HDI generation actions')
    for index, line in enumerate(lines):
        argv = shlex.split(line)
        while argv and argv[0] == '/usr/bin/env':
            argv.pop(0)
        # Earlier product graphs retain this exact source-volume alias.
        # Resolve the alias into the same RO inputs before checking the tool
        # and declarations; owned outputs are still redirected below.
        argv = [str(root / token.removeprefix('/openharmony/'))
                if token.startswith('/openharmony/') else
                'ohos.hdi:' + str(root / token.removeprefix('ohos.hdi:/openharmony/'))
                if token.startswith('ohos.hdi:/openharmony/') else token for token in argv]
        if (not argv or Path(argv[0]).name != 'idl' or argv.count('-d') != 1 or
                argv.count('-r') != 1 or '--gen-cpp' not in argv or
                argv[argv.index('--intf-type') + 1] != 'hdi'):
            raise ValueError('unexpected real HDI generator command')
        tool = Path(argv[0])
        if not tool.is_file():
            raise ValueError('the actual product HDI host generator is missing')
        mapping = argv[argv.index('-r') + 1]
        if not mapping.startswith('ohos.hdi:'):
            raise ValueError('unexpected HDI package mapping')
        original_interface = Path(mapping.removeprefix('ohos.hdi:'))
        if sha(original_interface / 'display/composer/v1_0/DisplayComposerType.idl') != inputs[
                str(interface / 'display/composer/v1_0/DisplayComposerType.idl')]:
            raise ValueError('GN action differs from pinned current display interface')
        revised = argv[:]
        generated = output / 'gen/drivers/interface'
        generated.mkdir(parents=True, exist_ok=True)
        revised[revised.index('-d') + 1] = str(generated)
        revised[revised.index('-r') + 1] = 'ohos.hdi:' + str(owned_inputs)
        for position, token in enumerate(argv):
            if token == '-c':
                source = Path(argv[position + 1])
                relative = source.relative_to(original_interface)
                if sha(source) != inputs[str(interface / relative)]:
                    raise ValueError('actual HDI declaration differs from pinned source')
                revised[position + 1] = str(owned_inputs / relative)
        log = output / ('generate-' + str(index) + '.log')
        with log.open('x') as stream:
            completed = subprocess.run(revised, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
        if completed.returncode:
            raise ValueError('actual isolated HDI generation failed')
        records.append(dict(actual_gn_command=line, owned_command=revised, tool_sha256=sha(tool),
                            log=str(log), log_sha256=sha(log), exit_code=completed.returncode))
    for target in targets:
        if not (output / target).is_file():
            raise ValueError('actual HDI generator did not produce required display header')
    if any(sha(Path(path)) != value for path, value in inputs.items()):
        raise ValueError('pinned IDL input changed')
    headers = {str(path): sha(path) for path in (output / 'gen').rglob('*.h')}
    rewritten = []
    for token in command:
        if token.startswith('-Igen/drivers/interface'):
            rewritten.append('-I' + str(output / token[2:]))
        rewritten.append(token)
    return rewritten, [dict(kind='actual_product_display_hdi', input_sha256=inputs,
                            generated_header_sha256=headers, actions=records)]
