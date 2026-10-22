#!/usr/bin/env python3
"""Rewind only the complete known QEMU modem source vector before old hooks."""
import argparse
from pathlib import Path
import subprocess
from verify_source import validate,FILES,PROJECT,REVISION
from exact_source_states import validate_component

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    a=p.parse_args();root=a.source_root.resolve()
    try:
        final=validate(root)
    except ValueError as original_error:
        # A clean release checkout has not traversed the predecessor QEMU
        # control patch yet. Admit only its complete exact stock vector;
        # this does not authorize application before the normal prefix.
        stock=tuple((name,'76487f617bc760c021d974a69ec35a7d37f8241a4bd83a6485e55185ccbccab8'
            if name=='services/netmanagernative/BUILD.gn' else before,after)
            for name,before,after in FILES)
        try:
            if validate_component(root,PROJECT,REVISION,stock):
                raise ValueError('inconsistent complete modem state')
        except ValueError:
            raise original_error
        return
    if not final:return
    patch=Path(__file__).resolve().parent/'0001-create-fixed-virtual-modem-tun-in-netsysnative.patch'
    command=['git','-C',str(root),'apply','--reverse']
    subprocess.run(command+['--check',str(patch)],check=True)
    # One complete patch: git apply validates every hunk before any mutation.
    subprocess.run(command+[str(patch)],check=True)
    if validate(root):raise ValueError('modem source rewind did not restore its complete before vector')

if __name__=='__main__':main()
