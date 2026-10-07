#!/usr/bin/env python3
"""Isolated diagnostic wrapper, never used for an acceptance boot."""
import json
import os
import sys


def adjust(arguments, mode):
    if mode not in ('verbose', 'idle-tick', 'power-trace'):
        raise ValueError('unsupported isolated kernel diagnostic')
    result = list(arguments)
    if '-append' in result:
        index = result.index('-append') + 1
        if index >= len(result):
            raise ValueError('missing actual launcher kernel command line')
        result[index] += ' loglevel=8'
        if mode == 'idle-tick':
            result[index] += ' nohz=off cpuidle.off=1'
        if mode == 'power-trace':
            result[index] += ' no_console_suspend trace_event=power:suspend_resume tp_printk'
    return result


def main():
    binary = os.environ['QEMU_DIAGNOSTIC_BINARY']
    if not os.path.isabs(binary) or not os.path.isfile(binary):
        raise ValueError('an actual absolute QEMU binary is required')
    arguments = adjust(sys.argv[1:], os.environ['QEMU_KERNEL_DIAGNOSTIC'])
    if '-append' in arguments:
        print('Isolated kernel diagnostic argv: ' + json.dumps([binary, *arguments]), file=sys.stderr, flush=True)
    os.execv(binary, [binary, *arguments])


if __name__ == '__main__':
    main()
