#!/usr/bin/env python3
"""Verify two narrow boot-profile repairs against image metadata and init output."""
import re


MODULE_PATH = '/system/bin/check_module_update_init'
USAGE_PATHS = ('/system/etc/init/device_usage_statistics_service.cfg',
               '/etc/init/device_usage_statistics_service.cfg')


def verify(module_stat: str, usage_stats: list[str], serial: str) -> dict:
    if re.search(r'(?m)^Inode: \d+\s+Type: regular\s+Mode:\s+0?755\b', module_stat) is None:
        raise ValueError('module-update initializer is not an executable regular image file')
    if (len(usage_stats) != len(USAGE_PATHS) or
            any('File not found by ext2_lookup' not in entry or 'Inode:' in entry
                for entry in usage_stats)):
        raise ValueError('invalid usage-statistics init definition remains packaged')
    events = ('check_module_update start.', 'HandleModuleUpdate, exec chekc_module_update.',
              'boot completed, uninstall module_update_init.')
    positions = [serial.find(event) for event in events]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise ValueError('module-update init did not run through its complete boot lifecycle')
    if re.search(r'(?i)module_update_init.*exec error|exec error.*check_module_update', serial):
        raise ValueError('module-update initializer exec failed')
    if ('Start OnStart-SA:1907 finished' not in serial or
            'Publish SA:1907 result:0' not in serial):
        raise ValueError('replacement UsageStatistics SA did not start and publish')
    return {'module_update_init_executable': True, 'module_update_boot_lifecycle': True,
            'invalid_usage_init_absent': True, 'usage_statistics_sa_1907_published': True}
