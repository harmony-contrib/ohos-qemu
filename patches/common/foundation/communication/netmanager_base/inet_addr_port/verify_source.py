"""Exact network port storage/codec/parser repair; not runtime acceptance."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/netmanager_base'
REVISION = '9831989d54f490d046a632ab13d309580d2fa710'
FILES = (
    ('frameworks/js/napi/connection/async_context/src/addnetworkroute_context.cpp',
     '9b85077af2a915c6052f66e265d5787c3dae6cb3eb564cfd4f3e7ef5eabaae81',
     '5d47bc6143b58b16bf665bdbb58fcc6653670f97524f2c000d1502f775b92496'),
    ('frameworks/js/napi/connection/async_context/src/addvlanip_context.cpp',
     '7f55967ce344eef16f782ddafe1cfc0b90a76e9d3fc6df97123bfab20e16d0d3',
     '18dca15d0149a09680906eb0955f677c12f47117804f4c15100ee81b203b19af'),
    ('frameworks/js/napi/connection/async_context/src/deletevlanip_context.cpp',
     '42ad08625c81466f63c3e2016b266c7306e911b8c24d54718264f1cd565c9016',
     'bbd71149aa251f7556c41c84de0fed3ad5b92a2b62c3362e5cee1e1560d0ebc1'),
    ('frameworks/native/netconnclient/src/inet_addr.cpp',
     '1b9c5a4b53ceff160bbafe2a52fe1d1b03fadb7f2e3065a9fb496a4ac6e4675c',
     '16c19928463e66ef2da0319f37e9eccdd56a221a60763975c423fa9b5177b815'),
    ('interfaces/innerkits/include/inet_addr.h',
     'dac353ba935bc188620ff9eced4311bc85cf36577229da72013ca3857c6d2363',
     '6870dcb0032b9d9bb67c98fff311caff991fbba4970b431789394e74e86eb328'),
    ('utils/napi_utils/include/napi_utils.h',
     '28459ca9c41ddb496017cd60f276ca85dcddb239971c1d8e30a1f366fcb3eba0',
     'd323cba6262430aac12cbfc7e83abf698b87f3a2a025e053012a93d02a2d9cf9'),
    ('utils/napi_utils/src/napi_utils.cpp',
     'b426016a306fc4f3f50aead9f3c7dd0b2a903f641907e1d6b293cce265cc0ed7',
     '87303a4effdab3c274ed231b4a0eba77ab9d6980c4b811a857b32bde5a1d673e'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
