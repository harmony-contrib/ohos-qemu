"""Fixed guest-only Wi-Fi peer recipe for the existing platform helper build."""
from pathlib import Path
from communications578_native import RIL_C

HERE = Path(__file__).resolve().parent


def helper_recipes():
    return {'apps579_wifi_peer': {
        'fixture': '../apps_providers579/wifi_peer.c',
        'source_file': str(HERE / 'apps_providers579/wifi_peer.c'),
        'language': 'c', 'anchors': [dict(RIL_C)], 'libraries': [],
        'headers': [], 'extra_includes': []}}
