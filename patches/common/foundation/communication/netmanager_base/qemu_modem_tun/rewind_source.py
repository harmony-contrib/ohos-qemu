#!/usr/bin/env python3
"""Rewind only the complete known QEMU modem source vector before old hooks."""
import argparse
import hashlib
from pathlib import Path
import subprocess
from verify_source import validate,FILES,PROJECT,REVISION
from exact_source_states import validate_component

# Complete installed C28 epoch, accepted only for prefix reversal.
PREVIOUS_FILES = (
    ('services/netmanagernative/BUILD.gn', '7358e7778ead53edeab9834f9288e5b9b873dddf01fd44ce3730d3ed7c744531', 'ca34a5f72e51f2b7f297ffd1924a8e5b21993f89ea913b42491ab32591250ec9'),
    ('services/netmanagernative/src/netsys_native_service.cpp', '58ae14b0a01f9147e4b1c2ad27891faf706ef779209e71c620c0c6a335f6a384', 'cba1bf384b844a3ca3bd97d4b4d34a27fab2d35308978567ecde7f4598f020f2'),
    ('services/netmanagernative/src/qemu_modem_tun.cpp', None, '02ceb1c09861ed5fdee3944e6022439a9d1d0fd0134fb8869c8218dbb3b6e0fd'),
    ('services/netmanagernative/include/qemu_modem_tun.h', None, '6507372cf9854bfadfc3fb067b33adfa268a7797abacf3b3ba9929ecd4058887'),
)
CURRENT_PATCH_SHA256 = 'caecd4b55413124ea745767860f11880c97118cde2fe944c71bf20506664c74a'
PREVIOUS_PATCH_SHA256 = '0f504a53be783744c2ee7a52dcdd01c48d1adb7dc495e16e9f35442d8692292f'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    a=p.parse_args();root=a.source_root.resolve()
    previous=False
    try:
        final=validate(root)
    except ValueError as original_error:
        try:
            final=validate_component(root,PROJECT,REVISION,PREVIOUS_FILES,True)
        except ValueError:
            # A clean release checkout has not traversed the predecessor QEMU
            # control patch yet. Preserve only the original complete stock vector.
            stock=tuple((name,'76487f617bc760c021d974a69ec35a7d37f8241a4bd83a6485e55185ccbccab8'
                if name=='services/netmanagernative/BUILD.gn' else before,after)
                for name,before,after in FILES)
            try:
                if validate_component(root,PROJECT,REVISION,stock):
                    raise ValueError('inconsistent complete modem state')
            except ValueError:
                raise original_error
            return
        previous=True
    if not final:return
    component=Path(__file__).resolve().parent
    patch=component/('legacy/previous-c28-product-source.patch' if previous else
        '0001-create-fixed-virtual-modem-tun-in-netsysnative.patch')
    expected=PREVIOUS_PATCH_SHA256 if previous else CURRENT_PATCH_SHA256
    if (patch.is_symlink() or patch.parent.is_symlink() or not patch.is_file() or
        hashlib.sha256(patch.read_bytes()).hexdigest()!=expected):
        raise ValueError('fixed complete modem epoch patch differs')
    command=['git','-C',str(root),'apply','--reverse']
    subprocess.run(command+['--check',str(patch)],check=True)
    # One complete patch: git apply validates every hunk before any mutation.
    subprocess.run(command+[str(patch)],check=True)
    if validate(root):raise ValueError('modem source rewind did not restore its complete before vector')

if __name__=='__main__':main()
