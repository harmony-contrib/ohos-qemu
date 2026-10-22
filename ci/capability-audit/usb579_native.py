"""Exactly one explicitly selected ordinary C helper; no compilation here."""
from pathlib import Path
from communications578_native import RIL_C

HERE = Path(__file__).resolve().parent
NAME = 'usb579_device_peer'


def helper_recipes():
    return {NAME: dict(fixture='../usb579_device_peer.c', source_file=str(HERE / 'usb579_device_peer.c'),
        language='c', anchors=[dict(RIL_C)], libraries=[],
        headers=['kernel/linux/linux-6.6/include/uapi/linux/usb/functionfs.h',
            'kernel/linux/linux-6.6/include/uapi/linux/usb/ch9.h',
            'kernel/linux/linux-6.6/drivers/usb/gadget/function/f_midi.c',
            'kernel/linux/linux-6.6/drivers/usb/gadget/udc/dummy_hcd.c'], extra_includes=[])}


def prepared_input(build_ref, *, archive, product):
    """Project the real original selected-helper production, never create it."""
    import hashlib
    import json
    from batch_system_build_runtime_helpers import _runtime_profile, target_spec
    from native579_artifact_context import binding_context
    def artifact(value):
        path = Path(value['path'])
        if not path.is_absolute() or path.resolve() != path or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('actual normal production file, never private source substitution')
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != value['sha256'] or ('bytes' in value and len(body) != value['bytes']):
            raise ValueError('actual original production bytes changed')
        return path
    report = json.loads(artifact(build_ref).read_bytes())
    row = report['helpers'][NAME]
    if (report['product'] != product or report['arch'] != target_spec(product)['arch'] or report['changed_inputs'] != [] or
        report['builder_sha256'] != hashlib.sha256((HERE / 'batch_system_build_runtime_helpers.py').read_bytes()).hexdigest() or
        row['status'] != 'pass_compile_link_ONLY'):
        raise ValueError('original actual selected normal helper build required')
    binary = dict(path=row['binary'], sha256=row['binary_sha256'])
    if artifact(row['source']).read_bytes() != (HERE / 'usb579_device_peer.c').read_bytes():
        raise ValueError('one actual admitted canonical peer C source')
    context = binding_context(report, row, artifact(binary), artifact)
    if context['product'] != product or _runtime_profile(row)['archive']['sha256'] != archive['sha256']:
        raise ValueError('real helper compile/link and installed runtime belong to another package')
    for argv in (row['compile_command'], row['link_command']):
        commands = [item for item in report['commands'] if item['argv'] == argv]
        if len(commands) != 1 or commands[0]['exit_code'] != 0 or commands[0].get('timed_out'):
            raise ValueError('complete original normal compile/link command missing')
        artifact(dict(path=commands[0]['log'], sha256=commands[0]['sha256']))
    return dict(binary=binary, build=build_ref, source=row['source'], abi=report['arch'])
