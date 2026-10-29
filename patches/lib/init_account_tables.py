"""Exact seven-field account repair; never grant or alias an identity."""
import re

CLOUD_ORIGINAL = b'cloud_disk_service:x:6161:6161::/bin/false'
CLOUD_REPAIRED = b'cloud_disk_service:x:6161:6161:::/bin/false'


def repair_cloud(original):
    rows = original.splitlines()
    if rows.count(CLOUD_ORIGINAL) != 1 or CLOUD_REPAIRED in rows:
        raise ValueError('unknown or duplicate fixed cloud account record')
    result = original.replace(CLOUD_ORIGINAL, CLOUD_REPAIRED)
    validate(result, 'passwd')
    return result


def validate(data, kind):
    width = {'passwd': 7, 'group': 4}[kind]
    names = set()
    for line in data.decode('utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        row = line.split(':')
        if (len(row) != width or re.fullmatch(r'[a-zA-Z0-9_-]+', row[0]) is None or
                row[0] in names or re.fullmatch(r'0|[1-9][0-9]*', row[2]) is None or
                (kind == 'passwd' and re.fullmatch(r'0|[1-9][0-9]*', row[3]) is None)):
            raise ValueError('malformed or duplicate packaged account record')
        names.add(row[0])
    # Other platform accounts can intentionally share IDs; this dedicated
    # service may not. Preserve all original users and memberships verbatim.
    rows = [line.split(':') for line in data.decode().splitlines() if line and not line.startswith('#')]
    owned = [row for row in rows if row[0] == 'cloud_disk_service']
    aliases = [row for row in rows if row[2] == '6161']
    if len(owned) != 1 or aliases != owned or owned[0][2] != '6161':
        raise ValueError('cloud service identity is missing, duplicated or aliased')
    if kind == 'passwd' and owned[0] != CLOUD_REPAIRED.decode().split(':'):
        raise ValueError('cloud service primary group, home or non-login shell changed')
    if kind == 'group' and owned[0] != ['cloud_disk_service', 'x', '6161', '']:
        raise ValueError('cloud service group authority changed')
