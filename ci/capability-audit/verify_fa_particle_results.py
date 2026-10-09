"""Validate FA observations; still requires independent same-archive Stage tests."""
import json
import re

from run_normal_hap_probe import require_normal_identity

BUNDLE = 'org.harmonycontrib.qemu.fa.particle'
NAMES = ('particle.invalid_parameter', 'actual.fa.context', 'particle.context',
         'particle.ability_name', 'complete')


def verify(text, nonce, identity):
    require_normal_identity(identity, BUNDLE)
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
