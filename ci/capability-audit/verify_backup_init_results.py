#!/usr/bin/env python3
"""Verify that a newly booted package actually started its backup SA.

This closes only the old invalid-capability init rejection, not Backup API
data transfer, restore, cloud integration, or authorization behavior.
"""
import re


def verify(serial: str) -> dict:
    started = re.findall(r'ServiceStart started info backup_sa\(pid (\d+) uid (\d+)\)', serial)
    executed = set(re.findall(r'\[pid=(\d+)\]\[Init\]\[INFO\].*ServiceExec backup_sa\b', serial))
    scheduled = re.findall(r'SAMGR: Start dynamic proc:backup_sa,5203,0_\d+ms', serial)
    if len(started) != 1 or len(scheduled) != 1:
        raise ValueError('backup SA was not started exactly once by init and SAMGR')
    pid, uid = started[0]
    if int(pid) <= 1 or int(uid) != 1089 or pid not in executed:
        raise ValueError('backup SA start/exec identity differs or is incomplete')
    return {'pid': int(pid), 'uid': int(uid), 'service': 'backup_sa', 'sa_id': 5203}
