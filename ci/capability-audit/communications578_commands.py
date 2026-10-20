"""Finite command DATA for the original Owner's existing launch callback."""
import re
from communications578_contract import plan


def commands(profile, run, boot, operation_ids):
    rows = plan(profile)
    if (not re.fullmatch('[a-f0-9]{32}', run) or not re.fullmatch('[a-f0-9-]{36}', boot) or
            len(operation_ids) != len(rows) or len(set(operation_ids)) != len(rows) or
            any(type(n) is not str or not re.fullmatch('[a-f0-9]{32}', n) for n in operation_ids)):
        raise ValueError('Actual original Owner run/boot and fresh command nonces required')
    return [dict({k: v for k, v in row.items() if k not in ('expect', 'stimulus', 'restart_bluetooth')},
                 run_id=run, boot_id=boot, operation_id=nonce)
            for row, nonce in zip(rows, operation_ids)]
