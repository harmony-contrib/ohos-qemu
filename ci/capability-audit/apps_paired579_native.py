"""Fixed read-only native observer for the original platform helper builder.

Root alone adds the finite helper name to its shared builder and compiles in the
same actual fixture batch. No query, compiler, process or resource runs here.
"""
from pathlib import Path
from communications578_native import RIL_C

HERE=Path(__file__).resolve().parent


def helper_recipes():
    return {'apps_paired579_net':{
        'fixture':'../apps_paired579/paired_net.c',
        'source_file':str(HERE/'apps_paired579/paired_net.c'),
        'language':'c','anchors':[dict(RIL_C)],'libraries':[],
        'headers':[],'extra_includes':[]}}


def gn_contract():
    return {'diagnostic_target':'apps_paired579_net',
        'diagnostic_build':str(HERE/'apps_paired579/paired_net.gn'),
        'source_file':str(HERE/'apps_paired579/paired_net.c'),
        'actual_anchor':dict(RIL_C),
        'actual_anchor_GN_target':'//base/telephony/ril_adapter/services/vendor:ril_vendor',
        'required_helper_DT_NEEDED':['libc.so'],
        'extra_libraries':[],
        'scope':'actual guest read-only eth0/eth1 ioctl observer; no daemon, mutation, packet injection or ip-tool assumption'}
