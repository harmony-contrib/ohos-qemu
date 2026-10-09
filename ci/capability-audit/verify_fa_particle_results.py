"""Validate FA observations; still requires independent same-archive Stage tests."""
import json
from pathlib import Path
import re
import zipfile

from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest

BUNDLE = 'org.harmonycontrib.qemu.fa.particle'
NAMES = ('particle.invalid_parameter', 'actual.fa.context', 'particle.context',
         'particle.ability_name', 'complete')


def verify_evidence(document, archive_sha, boot_id, arch):
    """Recompute the narrow FA result, never infer Stage or whole-gap closure."""
    from run_fa_particle_probe import verify_page, verify_process
    if (document.get('status') != 'pass' or document.get('persona') != 'fa-particle' or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('failures') != [] or
            document.get('closed') != [] or document.get('first_artifact_behavior_gate_passed') is not False or
            document.get('cleanup') != 'force stop process successfully.'):
        raise ValueError('successful FA test on this exact package/boot/architecture required')

    def checked(key):
        path = Path(document.get(key, ''))
        if (not path.is_absolute() or not path.is_file() or path.is_symlink() or
                digest(path) != document.get(key + '_sha256')):
            raise ValueError('actual FA evidence changed: ' + key)
        return path

    identity = checked('identity').read_text()
    uid = require_normal_identity(identity, BUNDLE)
    raw = checked('results').read_text()
    inputs_path = checked('caller_inputs')
    inputs = json.loads(inputs_path.read_text())
    project = inputs_path.parent
    if (inputs.get('nonce') != document.get('nonce') or inputs.get('bundle') != BUNDLE or
            inputs.get('build_status') != 'pass' or inputs.get('model') != 'FA' or
            inputs.get('ability_kind') != 'service' or inputs.get('request_permissions') != [] or
            inputs.get('builder_sha256') != digest(Path(__file__).with_name('build_fa_particle_probe.py'))):
        raise ValueError('fresh compiled FA caller contract required')
    for relative, key in (
            ('entry/src/main/js/ParticleService/service.js', 'source_sha256'),
            ('entry/src/main/js/MainAbility/pages/index/index.js', 'page_source_sha256')):
        path = project / relative
        if path.is_symlink() or digest(path) != inputs.get(key):
            raise ValueError('compiled FA source changed')
    unsigned = Path(inputs.get('unsigned_hap', ''))
    if (not unsigned.is_absolute() or not unsigned.resolve().is_relative_to(project.resolve()) or
            unsigned.is_symlink() or digest(unsigned) != inputs.get('unsigned_hap_sha256')):
        raise ValueError('compiled FA HAP changed')
    signed = inputs_path.parent.parent / 'ordinary-fa.hap'
    if signed.is_symlink() or digest(signed) != document.get('signed_hap_sha256'):
        raise ValueError('actual installed signed FA HAP changed')
    with zipfile.ZipFile(unsigned) as hap:
        config = json.loads(hap.read('config.json'))
        if ('module.json' in hap.namelist() or config['app']['bundleName'] != BUNDLE or
                config['module'].get('reqPermissions', [])):
            raise ValueError('FA model with no extra permissions required')
        for member in ('assets/js/ParticleService/service.abc', 'assets/js/MainAbility/pages/index/index.abc'):
            if not hap.read(member):
                raise ValueError('actual FA compiled page and service required')
    processes = document.get('processes')
    if not isinstance(processes, list) or not processes or len(processes) > 8:
        raise ValueError('actual ordinary FA page/service process evidence required')
    pids = set()
    for process in processes:
        pid = process.get('pid')
        if type(pid) is not int or pid <= 0 or pid in pids or process.get('uid') != uid:
            raise ValueError('invalid actual FA process identity')
        pids.add(pid)
        verify_process(process['status'], uid)
    commands = document.get('commands')
    if not isinstance(commands, list) or not commands:
        raise ValueError('actual FA build/install/run commands required')
    for command in commands:
        path = Path(command.get('log', ''))
        if (command.get('exit_code') != 0 or command.get('timed_out') or not command.get('argv') or
                not path.is_absolute() or path.is_symlink() or not path.is_file() or
                digest(path) != command.get('sha256')):
            raise ValueError('actual FA command evidence changed or failed')
    verify_page(raw, document['nonce'])
    result = verify(raw, document['nonce'], identity)
    if result != document.get('result'):
        raise ValueError('FA summary differs from its actual caller observations')
    return result


def verify(text, nonce, identity):
    require_normal_identity(identity, BUNDLE)
    package = json.loads(identity.removeprefix(BUNDLE + ':\n'))
    if package['applicationInfo'].get('bundleName') != BUNDLE:
        raise ValueError('actual ordinary identity must belong to the FA caller')
    if not isinstance(nonce, str) or re.fullmatch('[0-9a-f]{32}', nonce) is None:
        raise ValueError('fresh FA caller nonce required')
    rows = []
    for line in text.splitlines():
        if 'QEMU_FA_PARTICLE:' in line:
            rows.append(json.loads(line.split('QEMU_FA_PARTICLE:', 1)[1]))
    if len(rows) != len(NAMES):
        raise ValueError('one complete actual FA invocation required')
    for row, name in zip(rows, NAMES):
        if (not isinstance(row, dict) or set(row) != {'nonce', 'name', 'status', 'value'} or
                row['nonce'] != nonce or row['name'] != name or row['status'] != 'pass'):
            raise ValueError('failed, stale, reordered or malformed FA observation')
    constant = rows[0]['value']
    if (not isinstance(constant, dict) or set(constant) != {'INVALID_PARAMETER'} or
            type(constant['INVALID_PARAMETER']) is not int or constant['INVALID_PARAMETER'] != -1):
        raise ValueError('exact SDK particle ErrorCode member required')
    info = rows[1]['value']
    if (not isinstance(info, dict) or info.get('bundleName') != BUNDLE or
            info.get('type') != 2 or type(info.get('type')) is not int or info.get('contextPresent') is not True or
            not isinstance(info.get('name'), str) or info['name'] != BUNDLE + '.ParticleService'):
        raise ValueError('actual FA context must identify this caller')
    second = rows[2]['value']
    if (not isinstance(second, dict) or second.get('bundleName') != BUNDLE or
            second.get('name') != info['name'] or type(second.get('type')) is not int or second['type'] != 2 or
            rows[3]['value'] != info['name'] or
            rows[4]['value'] != 'FA'):
        raise ValueError('FA context and existing particle call disagree')
    return {'status': 'pass', 'observations': len(rows), 'scope': 'FA_particle_constant_and_context_only',
            'closed': [], 'requires': ['same-archive Stage regression', 'fresh package binding']}
