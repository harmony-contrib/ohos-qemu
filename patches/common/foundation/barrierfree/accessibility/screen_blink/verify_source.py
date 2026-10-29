#!/usr/bin/env python3
"""Exact fixed-release screen-blink service/client/IPC/NAPI composition."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/barrierfree/accessibility'
REVISION = 'c593c7e1a6149a2c13e5931b2114d3c2d0bf20ea'
FILES = (
    ('common/interface/IAccessibleAbilityManagerService.idl',
     '49eee64cf6bc8846607f2ffee03dd378309f0b9b5427e1d0e9891dc22462aba4',
     '971b1eb2bb371c1b92b2534de6f15ccc0681644d7e0e3eeb505e14e39bf25bf4'),
    ('frameworks/acfwk/include/accessibility_config_impl.h',
     '608f9aef99a74524d1d3af3962e319dce6c34d2222e1fdd7e5b9d8feb53383d0',
     'b4d9547b45fb3dfd59ed7b34d988a486fbef3e91706339c46ca682390727ae83'),
    ('frameworks/acfwk/src/accessibility_config.cpp',
     '444a5ff7b768389be5bbd1389dc9943f5fcf1246629c9fc657fc19f7e151556d',
     'f0f55a4584990a1021986a3d5c0e7972b96daae5ff6187466a3cf010067b6a5d'),
    ('frameworks/acfwk/src/accessibility_config_impl.cpp',
     '7ab77943f17c76ec977756231123ca5f4720e103076ea005205d24f7b18c3a8f',
     '1967dc46f10bef039af87f1da6c11040f077e6b04647ed1214d3c9bfb191ba32'),
    ('interfaces/innerkits/acfwk/include/accessibility_config.h',
     '9e0c01e0a89ff300c1508dd2439fb1b7b47937c5c0352218dd03a9f61651c48b',
     '7700af0506666cf4f9e7d27db2b83b8730c33c2934b3c47e347c54ff3b952f7b'),
    ('interfaces/kits/napi/accessibility_config/src/napi_blink_control.h', None,
     'ceb18c9b68547ee10415bf437afda6066d058a77a5ea85c672f5d18e0130faa5'),
    ('interfaces/kits/napi/accessibility_config/src/native_module.cpp',
     'faa573b972a9ad98ae8316b669aa73cbf40c57bf740f354bd492589a6fa641e3',
     '9c4481936d1145c7e4796cf4a90faed44bf98b81e750e57418b8f3283867bcaa'),
    ('services/aams/BUILD.gn',
     'a1b5087a3115452f638bd837addd75c67964e837cff9c3160dc44239d8fcccee',
     'efc05ad39907cb8b73e6d81aab01df717eadb9fd80a25c3495e543952967d101'),
    ('services/aams/include/accessibility_blink_controller.h', None,
     '780cec804cb79a56eb4707bfde42d80b4228fe583de11ad62524b1f242b8c115'),
    ('services/aams/include/accessible_ability_manager_service.h',
     '4cab972b350339f25b472df4f41ebb03ba351e50b9e832120d51e084b0826175',
     '0eddd68b82ea427a72cedb30fcbd20656fcbf16bfd9a4b6dcd83e4e1fe3f73d2'),
    ('services/aams/src/accessibility_blink_controller.cpp', None,
     '39695151eead89a61d67c728eff9248cf10ebc0f7805ffe5c615a244212354af'),
    ('services/aams/src/accessible_ability_manager_service.cpp',
     '32e903a143c3f6eba43114e77059737cfb0eacb86dabce39390f3ce06aedbc4c',
     '2285457de48dc8a240a4f37c7937303ce5a0b0bc6afed340e262c2df33e7243a'),
)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
