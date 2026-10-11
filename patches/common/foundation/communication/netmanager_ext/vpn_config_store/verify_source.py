"""Exact complete network-store candidate; no package acceptance claim."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/netmanager_ext'
REVISION = '8c41289750820fb2ddb347b1205cee9a7b527388'
FILES = (
    ('frameworks/js/napi/vpn/src/vpn_exec.cpp',
     'e053b07dda9e84c70f070bdc4c17c8078d457a4c114f0807f8853e0053d64085',
     '7762983bb0e95ad1b5bd3bd1f63f482b3803b1b5c39fe2276c677c397fe8dacc'),
    ('frameworks/native/netvpnclient/src/vpn_data_bean.cpp',
     'cd88f49e024b904fefd934af5f86dced4f4e28060bf67d82afd5f62b44107f16',
     '9803f79ba3c19a7133255a95ac0e72857e37360ba72311c7cb959497edd34ae3'),
    ('interfaces/innerkits/netvpnclient/include/vpn_data_bean.h',
     '37db373428fa33efdaf07a845ba3d1081d94ab77887ff6dec38f5d9c8f56e6e8',
     'aaadee914460afe983a7199651ea884d2cc098ca71d554af6eab350f51b5584f'),
    ('interfaces/innerkits/netvpnclient/include/vpn_network_config.h', None,
     '2fd70b4bce1885d5259efe297eb383418a209470a904e00968a3165e9935b09e'),
    ('services/vpnmanager/include/vpn_database_defines.h',
     '8896acba872cd9cb339cb6458e67a28a5fd92413a6bd2cee61c65a58a8b8c5be',
     '2490bc4ff08d131ea921b30579cce2a473874bbfa9bb0e888a6390d3eca0a75f'),
    ('services/vpnmanager/src/vpn_database_helper.cpp',
     '611f815db2dbd515edb062efc2896843fa843573183860068c6cd6419b74760e',
     '91a225974252a719c56c967519ac0d9fa1eaa27280f54678df66abf6a323c257'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
