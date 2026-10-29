"""Exact QEMU modem TUN sources; a source state is never runtime acceptance."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5]/'lib'))
from exact_source_states import validate_component
PROJECT = 'foundation/communication/netmanager_base'
REVISION = '9831989d54f490d046a632ab13d309580d2fa710'
FILES = (('services/netmanagernative/BUILD.gn', '7358e7778ead53edeab9834f9288e5b9b873dddf01fd44ce3730d3ed7c744531', 'ca34a5f72e51f2b7f297ffd1924a8e5b21993f89ea913b42491ab32591250ec9'), ('services/netmanagernative/src/netsys_native_service.cpp', '58ae14b0a01f9147e4b1c2ad27891faf706ef779209e71c620c0c6a335f6a384', 'cba1bf384b844a3ca3bd97d4b4d34a27fab2d35308978567ecde7f4598f020f2'), ('services/netmanagernative/src/qemu_modem_tun.cpp', None, '49450e5e2f13fe2a20acae0eff2d10b6bda8846a52b04395667dc95e03e1f143'), ('services/netmanagernative/include/qemu_modem_tun.h', None, '6507372cf9854bfadfc3fb067b33adfa268a7797abacf3b3ba9929ecd4058887'))

def validate(root,require_patched=False):
    return validate_component(root,PROJECT,REVISION,FILES,require_patched)

def preceding_files(root,files):
    if not validate(root):return files
    # Only after all four whole sources and the real project HEAD match may
    # the preceding control guard use the exact final GN successor hash.
    name,_,after=FILES[0]
    return tuple((p,b,after if p==name else a) for p,b,a in files)
