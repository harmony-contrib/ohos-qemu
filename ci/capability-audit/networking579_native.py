"""One explicitly selected C observer; original default helper set is unchanged.

Intended canonical destinations: ci/capability-audit/networking579_native.py
and ci/capability-audit/networking579_bpf_snapshot.c. The original Builder
rejects private source_file paths outside HERE; no path bypass is proposed.
"""
from pathlib import Path
from communications578_native import RIL_C

HERE = Path(__file__).resolve().parent
NAME = 'networking579_bpf_snapshot'


def helper_recipes():
    return {NAME: {'fixture': '../networking579_bpf_snapshot.c',
        'source_file': str(HERE / 'networking579_bpf_snapshot.c'), 'language': 'c',
        'anchors': [dict(RIL_C)], 'libraries': [],
        'headers': ['kernel/linux/linux-6.6/include/uapi/linux/bpf.h',
            'foundation/communication/netmanager_base/services/netmanagernative/bpf/include/bpf_def.h',
            'foundation/communication/netmanager_base/services/netmanagernative/bpf/include/bpf_path.h',
            'foundation/communication/netmanager_base/services/netmanagernative/bpf/src/netsys.c',
            'foundation/communication/netmanager_base/services/netmanagernative/bpf/src/bpf_loader.cpp',
            'foundation/communication/netmanager_base/services/netmanagernative/bpf/BUILD.gn'],
        'extra_includes': []}}


def contract():
    return {'actual_anchor': dict(RIL_C),
        'actual_anchor_GN_target': '//base/telephony/ril_adapter/services/vendor:ril_vendor',
        'required_DT_NEEDED': ['libc.so'], 'normal_product_link_required': True,
        'C_flags_CRT_CFI_LTO_preserved': True,
        'header_boundary': 'Use the actual selected OHOS sysroot linux/bpf.h; retain exact source header and compile dependency receipt. No generated substitute UAPI.',
        'actual_binary': None, 'runtime_pass': False, 'first_artifact_behavior_gate_passed': False}


def prepared_input(build_ref, *, archive, product):
    """Pure normal-production receipt projection, never a build or acceptance.

    Root calls only after its original Owner35 has run the existing Builder
    explicitly for NAME. Original extra7 exact-set consumers stay unchanged;
    this may consume a separate actual selected-helper build in the SAME Owner35
    dispatch, never a synthetic eighth row or a second resource Owner.
    """
    import hashlib
    import json
    from batch_system_build_runtime_helpers import _runtime_profile, target_spec
    from native579_artifact_context import binding_context
    def document(value):
        path = Path(value['path'])
        if not path.is_absolute() or path.resolve() != path or path.is_symlink() or not path.is_file():
            raise ValueError('actual ordinary normal-production artifact required')
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != value['sha256'] or ('bytes' in value and len(body) != value['bytes']):
            raise ValueError('actual normal-production artifact changed')
        return body
    report = json.loads(document(build_ref))
    row = report['helpers'][NAME]
    if (report['product'] != product or report['arch'] != target_spec(product)['arch'] or
            report['changed_inputs'] != [] or report['builder_sha256'] != hashlib.sha256(
                (HERE / 'batch_system_build_runtime_helpers.py').read_bytes()).hexdigest() or
            row['status'] != 'pass_compile_link_ONLY'):
        raise ValueError('actual selected original normal Builder/source result required')
    binary = {'path': row['binary'], 'sha256': row['binary_sha256']}
    source = row['source']
    document(binary)
    if document(source) != (HERE / 'networking579_bpf_snapshot.c').read_bytes():
        raise ValueError('normal compiled native fixture differs')
    def artifact(value):
        document(value)
        return Path(value['path'])
    context = binding_context(report, row, Path(binary['path']), artifact)
    profile = _runtime_profile(row)
    if context['product'] != product or profile['archive']['sha256'] != archive['sha256']:
        raise ValueError('native normal-link/installed DSO profile not bound to this new archive')
    for argv in (row['compile_command'], row['link_command']):
        commands = [r for r in report['commands'] if r['argv'] == argv]
        if len(commands) != 1 or commands[0]['exit_code'] != 0 or commands[0].get('timed_out'):
            raise ValueError('actual complete normal compile/link command receipt required')
        document({'path': commands[0]['log'], 'sha256': commands[0]['sha256']})
    return {'binary': binary, 'build': build_ref, 'source': source, 'abi': report['arch']}
