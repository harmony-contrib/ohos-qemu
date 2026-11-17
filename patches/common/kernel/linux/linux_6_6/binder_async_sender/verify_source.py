#!/usr/bin/env python3
"""Pinned private Binder sender reference; preserve asynchronous wire semantics."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'kernel/linux/linux-6.6'
REVISION = '14c77f1541a53e814d89ad6dea5f7f211f9895a6'
REPLACEMENTS = {
    'drivers/android/binder_internal.h': (
        ('\tkuid_t  sender_euid;\n',
         '\tkuid_t  sender_euid;\n#ifdef CONFIG_BINDER_SENDER_INFO\n'
         '\t/* Private reference for one-way sender info, not the wire PID. */\n'
         '\tstruct pid *async_sender_pid;\n#endif\n'),
    ),
    'drivers/android/binder.c': (
        ('\tt->sender_euid = task_euid(proc->tsk);\n',
         '#ifdef CONFIG_BINDER_SENDER_INFO\n'
         '\tif (!reply && (tr->flags & TF_ONE_WAY))\n'
         '\t\tt->async_sender_pid = get_task_pid(current, PIDTYPE_TGID);\n'
         '#endif\n\tt->sender_euid = task_euid(proc->tsk);\n'),
        ('\t\t\tthread->sender_pid_nr = 0;\n',
         '\t\t\tthread->sender_pid_nr = pid_nr(t->async_sender_pid);\n'),
        ('\tbinder_free_txn_fixups(t);\n\tkfree(t);\n',
         '\tbinder_free_txn_fixups(t);\n#ifdef CONFIG_BINDER_SENDER_INFO\n'
         '\tput_pid(t->async_sender_pid);\n#endif\n\tkfree(t);\n'),
        ('err_alloc_tcomplete_failed:\n\tif (trace_binder_txn_latency_free_enabled())\n'
         '\t\tbinder_txn_latency_free(t);\n\tkfree(t);\n',
         'err_alloc_tcomplete_failed:\n\tif (trace_binder_txn_latency_free_enabled())\n'
         '\t\tbinder_txn_latency_free(t);\n#ifdef CONFIG_BINDER_SENDER_INFO\n'
         '\tput_pid(t->async_sender_pid);\n#endif\n\tkfree(t);\n'),
        ('\t\tbinder_alloc_free_buf(&proc->alloc, buffer);\n\t\tkfree(t_outdated);\n',
         '\t\tbinder_alloc_free_buf(&proc->alloc, buffer);\n#ifdef CONFIG_BINDER_SENDER_INFO\n'
         '\t\tput_pid(t_outdated->async_sender_pid);\n#endif\n\t\tkfree(t_outdated);\n'),
    ),
}


def repaired_source(relative, original):
    value = original
    for old, new in REPLACEMENTS[relative]:
        if value.count(old) != 1:
            raise ValueError('unexpected pinned Binder source structure: ' + relative)
        value = value.replace(old, new)
    return value


FILES = (
    ('drivers/android/binder_internal.h', 'df2fa120113f718a7620ef3c581cca107c3e7449cae92ea447628036d9db9b4f', 'deea4d03ca9b0284fdf024963c93db2d32b8a6e81ef7901acd37fbdf35a7b2ea'),
    ('drivers/android/binder.c', '006fa69abbf50e76d69465b6150725d7427144fd6ad5b0dc37244f8ae04d07a8', 'e0d365c6c671b47f054f7d0af1162162a17e6b7d8b3a80a5d97eda8e5565a1cd'),
)


def validate(root, require_patched=False):
    if len(FILES) != 2:
        raise ValueError('incomplete Binder component baseline')
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('trusted async Binder sender patch present: ' + str(validate(args.source_root, args.require_patched)))


if __name__ == '__main__':
    main()
