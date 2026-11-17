#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/wifi'
REVISION = '367605c52dfaf5f09bd690f16d9ee9a301cfc98a'
PREFIX = 'wifi/services/wifi_standard/wifi_framework/wifi_manage/wifi_scan/'
FILES = [
    (PREFIX + 'scan_monitor.h',
     '0203b1ca0c2208a13c31a0293b5b6de9e835c460d8d3f2fe8055c3f3f2bc9fdf',
     '97d7e1be24896e4aaac23781501e9085b468a5bca2bf87e45fe4583cfe207f98'),
    (PREFIX + 'scan_monitor.cpp',
     '4f47f2d6a7335116448640c714e63c4ada296a3054cc6605481339121e145cca',
     '035c6c2554ed7f6a996decd9d0272b7b4c7435bd82fb9e9b5641bb082b4933bc'),
    (PREFIX + 'scan_service.cpp',
     '8b48fac85e47b6177ce9c7dd7e79403e9e81a49aa922c9eed7d300315ada8a22',
     '4e02cf7b495894bd1c3f43690db68e5b397ab462dee59d8a7b81facb7dcdb475'),
]


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
