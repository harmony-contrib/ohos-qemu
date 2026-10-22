"""Finite shared-device sources on Root's existing normal SOURCE context.

This is source admission only. It never admits a DATA-supplied executable,
constructs a resource Owner, or turns source facts into QEMU acceptance.
"""
from pathlib import Path
import sys
from audio579_common import checked, doc, ref, loads, save, need, source_guard, dependency

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OWN = ('usb579_contract.py', 'usb579_inputs.py', 'usb579_native.py', 'usb579_device_peer.c', 'usb579_project.py',
       'usb579_shared.py', 'usb579_retention.py', 'usb579/UsbAudit.ets', 'usb579/EntryAbility.ets', 'usb579/Index.ets')
GADGET = '/config/usb_gadget/qemu_shared'
BULK_MOUNT = '/dev/usb-ffs/usb579'
MTP_MOUNT = '/dev/usb-ffs/mtp'
FUNCTIONS = ('ffs.usb579', 'midi.usb579', 'ffs.mtp')


def guard(io=None):
    context = doc(source_guard())
    snapshot = doc(context['snapshot'])
    canonical = {row['path']: row['sha256'] for row in snapshot['files']}
    approved = {row['path']: row['sha256'] for row in context['files']}
    for name in OWN:
        path = HERE / name
        need(approved.get(str(path)) == ref(path)['sha256'] and
             canonical.get(str(path.relative_to(ROOT))) == ref(path)['sha256'],
             'new USB producer must be adopted into the actual normal canonical source')
        if name.endswith('.py'):
            module = sys.modules.get(path.stem)
            need(module is None or Path(module.__file__).resolve() == path, 'foreign cached USB module')
    if io is not None:
        need(type(io) is dependency('capability578_owned_io').OwnedIO and not io._closed and io.owner.vm is io.guest,
             'only the original live stage OwnedIO is admitted')
        io.owner.held_binding(io.guest)
        need(doc(ref(io.guest.directory / 'build-inputs.json'))['source_git_revision'] == context['source_commit'],
             'one newly packaged actual normal source')
    return context
