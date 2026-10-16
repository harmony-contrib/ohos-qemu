"""Strict guest clock samples and bounded elapsed differences, no sleep inference.

Root owns deployment, actual executable provenance, boot/phase binding and health
checks. This module obtains no host time and issues no guest command itself.
"""
import json
from pathlib import PurePosixPath
import re
import shlex

MAX_NS = (1 << 64) - 1
FIELDS = {'schema_version', 'nonce', 'monotonic_before_ns', 'boottime_ns', 'monotonic_after_ns'}


def _nonce(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{32}', value) is None:
        raise ValueError('one exact 32 lowercase hexadecimal challenge nonce required')
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('duplicate clock JSON field: ' + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError('non-finite clock JSON value: ' + value)


def _validated(value):
    if (type(value) is not dict or set(value) != FIELDS or
            type(value['schema_version']) is not int or value['schema_version'] != 1):
        raise ValueError('exact clock sample schema_version 1 and five fields required')
    _nonce(value['nonce'])
    for key in ('monotonic_before_ns', 'boottime_ns', 'monotonic_after_ns'):
        if type(value[key]) is not int or not 0 <= value[key] <= MAX_NS:
            raise ValueError('actual nonnegative uint64 integer nanoseconds required: ' + key)
    if value['monotonic_before_ns'] > value['monotonic_after_ns']:
        raise ValueError('MONOTONIC sample must enclose the BOOTTIME read in call order')
    # BOOTTIME contains accumulated suspend time. It need not lie numerically
    # between the two MONOTONIC readings; their width bounds sampling uncertainty.
    return dict(value)


def parse(raw, nonce):
    """Read one complete JSON line (with optional final LF), bound to its nonce."""
    nonce = _nonce(nonce)
    if not isinstance(raw, (str, bytes)) or not 1 <= len(raw) <= 1024:
        raise ValueError('one bounded actual clock output line required')
    text = raw.decode('ascii', errors='strict') if isinstance(raw, bytes) else raw
    if text.endswith('\n'): text = text[:-1]
    if not text or text != text.strip() or '\r' in text or '\n' in text or '\x00' in text:
        raise ValueError('one complete clock JSON line required; no log prefix/suffix')
    value = _validated(json.loads(text, object_pairs_hook=_unique, parse_constant=_constant))
    if value['nonce'] != nonce: raise ValueError('clock output belongs to another challenge nonce')
    return value


def compare(before, after):
    """Compare caller-bound same-boot samples; report intervals without clipping.

    At each BOOTTIME read, the simultaneous MONOTONIC value lies somewhere
    inside that sample's bracket. Subtracting the extreme pairs yields the
    interval, not a scheduler/preemption-sensitive point estimate. Negative
    edges are retained. Even an exact zero difference identifies no sleep state.
    """
    before, after = _validated(before), _validated(after)
    if after['monotonic_before_ns'] < before['monotonic_after_ns']:
        raise ValueError('later MONOTONIC bracket must follow the complete earlier bracket')
    if after['boottime_ns'] < before['boottime_ns']:
        raise ValueError('BOOTTIME moved backwards; do not compare another boot or reversed phase')
    boot_elapsed = after['boottime_ns'] - before['boottime_ns']
    mono_min = after['monotonic_before_ns'] - before['monotonic_after_ns']
    mono_max = after['monotonic_after_ns'] - before['monotonic_before_ns']
    return {'schema_version': 1, 'before_nonce': before['nonce'], 'after_nonce': after['nonce'],
        'boottime_elapsed_ns': boot_elapsed,
        'monotonic_elapsed_ns': {'minimum': mono_min, 'maximum': mono_max},
        'sleep_clock_difference_ns': {'minimum': boot_elapsed - mono_max, 'maximum': boot_elapsed - mono_min},
        'uncertainty_ns': mono_max - mono_min}


def capture_script(remote, nonce):
    """Generate only a foreground command; root still verifies ELF/hash/boot/exit."""
    nonce = _nonce(nonce)
    if (not isinstance(remote,str) or re.fullmatch('/[A-Za-z0-9_./-]{1,255}',remote) is None or remote.startswith('//') or
            '..' in PurePosixPath(remote).parts or PurePosixPath(remote).as_posix() != remote or remote.endswith('/')):
        raise ValueError('canonical absolute deployed clock probe path required')
    quoted = shlex.quote(remote)
    return ('unset LD_LIBRARY_PATH LD_PRELOAD; test -f '+quoted+' && test ! -L '+quoted+
            ' && test -x '+quoted+' && '+quoted+' '+nonce)
