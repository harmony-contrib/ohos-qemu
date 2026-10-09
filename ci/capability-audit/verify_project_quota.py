"""Validate isolated kernel quota evidence; never close Storage app API gaps."""
import json
import re


def verify(text, nonce):
    if not re.fullmatch('[0-9a-f]{32}', nonce):
        raise ValueError('fresh 32-hex nonce required')
    rows = [json.loads(line.split('QEMU_PROJECT_QUOTA:', 1)[1])
            for line in text.splitlines() if 'QEMU_PROJECT_QUOTA:' in line]
    keys = {'nonce', 'scope', 'project', 'limitedBytes', 'recoveredBytes',
            'unprivilegedEdquot', 'cleanup'}
    if len(rows) != 1 or not isinstance(rows[0], dict) or set(rows[0]) != keys:
        raise ValueError('exactly one complete real quota observation required')
    row = rows[0]
    if (row['nonce'] != nonce or row['scope'] != 'disposable_guest_kernel_NOT_app_api' or
            row['unprivilegedEdquot'] is not True or row['cleanup'] is not True or
            any(type(row[key]) is not int for key in ('project', 'limitedBytes', 'recoveredBytes')) or
            not 0x60000000 <= row['project'] <= 0x6fffffff or
            not 0 < row['limitedBytes'] <= 2 * 1024 * 1024 or
            not 4 * 1024 * 1024 <= row['recoveredBytes'] <= 5 * 1024 * 1024):
        raise ValueError('actual isolated EDQUOT, recovery and cleanup evidence required')
    return {'scope': row['scope'], 'observation': row, 'closed': []}
