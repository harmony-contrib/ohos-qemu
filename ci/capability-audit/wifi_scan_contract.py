"""Bind a normal-permission Wi-Fi callback diagnostic, not full WLAN closure."""
import json
from pathlib import Path
import re
from run_root_probe import digest

TEMPLATE = Path(__file__).with_name('wifi_scan_probe.ets')
SCOPE = 'ordinary_ArkTS_real_wifi_scan_callbacks_NOT_association_AP_P2P_or_SSID_proof'
PERMISSIONS = ['ohos.permission.GET_WIFI_INFO', 'ohos.permission.SET_WIFI_INFO']


def inputs(project, sdk, arch, run_id):
    if re.fullmatch('[0-9a-f]{32}', run_id) is None or arch not in ('arm64', 'armv7a', 'x86_64'):
        raise ValueError('fresh Wi-Fi scan nonce and supported ABI required')
    project, sdk = Path(project), Path(sdk).resolve()
    page = project / 'entry/src/main/ets/pages/Index.ets'
    module = project / 'entry/src/main/module.json5'
    declaration = sdk / 'ets/api/@ohos.wifiManager.d.ts'
    if json.loads(module.read_text())['module'].get('requestPermissions') != [{'name': name} for name in PERMISSIONS]:
        raise ValueError('Wi-Fi scan caller must request only normal scan/read permissions')
    text = declaration.read_text()
    for name in ('isWifiActive', 'scan', 'startScan', 'getScanInfoList', 'on', 'off'):
        if 'function ' + name + '(' not in text:
            raise ValueError('actual SDK Wi-Fi contract changed: ' + name)
    return {'schema_version': 1, 'scope': SCOPE, 'role': 'ordinary_app', 'request_permissions': PERMISSIONS,
        'sdk': str(sdk), 'arch': arch, 'run_id': run_id,
        'sdk_declaration_sha256': digest(declaration), 'template_sha256': digest(TEMPLATE),
        'contract_sha256': digest(Path(__file__)), 'module_sha256': digest(module),
        'generated_source': str(page), 'generated_source_sha256': digest(page)}


def verify_inputs(value, run_id, arch):
    page = Path(value['generated_source'])
    if (page.is_symlink() or not page.is_file() or
            value != inputs(page.parents[5], value['sdk'], arch, run_id) or
            page.read_text() != TEMPLATE.read_text().replace('__WIFI_SCAN_RUN_ID__', run_id)):
        raise ValueError('actual compiled Wi-Fi caller changed')
