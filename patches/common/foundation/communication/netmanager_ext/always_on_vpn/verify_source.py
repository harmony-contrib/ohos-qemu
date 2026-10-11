#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = "foundation/communication/netmanager_ext"
REVISION = "8c41289750820fb2ddb347b1205cee9a7b527388"
FILES = [
    ("interfaces/innerkits/netvpnclient/INetworkVpnService.idl", "2698c2a86c0cf3f59840766de207beb2e35ef73ed2c375274dc64ffec0a9a09d", "d2a41cae4f25ff8808b9287986a6f1785a3a9778eaf65e05f9f35945f3a8c1fc"),
    ("interfaces/innerkits/netvpnclient/include/networkvpn_client.h", "d1408260b75362c1531a2ae6cb61418bd55a76f19a8dfe2a2e0673e497ba4801", "216228f506b663d8d9006ce63505eaee183ab1e247a00828bccb9adbf925d701"),
    ("frameworks/native/netvpnclient/src/networkvpn_client.cpp", "60fa7ea9d4d21fd4bacbd83622713814d01fda50cd27c542b221b157a57160a6", "2f2494677bfa42fa5fcd2bf3f605054c67f4341ead9282b1fddccbfb406fa513"),
    ("services/vpnmanager/include/networkvpn_service.h", "b8ccc016b57e985f39c970b97f425c36bdba683857b5b001c3758ce56235602f", "296316894a3db878e4951456b8b021d9ead4c9eb15392a7f5c660b00fb8c8674"),
    ("services/vpnmanager/src/networkvpn_service.cpp", "344e07d629fc5445f8edf069959780f8364eb5b5f040befc6b72d3396d8cc7b4", "1be84d577d02d7f02ac18e880ef904fd7683cc8747cc34c7f41949db7c09bc89"),
    ("frameworks/js/napi/vpnext/include/vpn_always_on_napi.h", None, "916d6db2e88b830febe5033bb8d32466d4c18ee2c72f4c379728e7955aa99d72"),
    ("frameworks/js/napi/vpnext/src/vpn_module_ext.cpp", "c66bca2e972ce84e7360402b189d5a7d8fb5f35602f57c2a923d2bb14318a21f", "f083d0b75922f1ca4bb3a6efbedca38fafd9ae3e0b7cbdb168c796dd44ecb5c5"),
]

def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    validate(args.source_root, args.require_patched)
