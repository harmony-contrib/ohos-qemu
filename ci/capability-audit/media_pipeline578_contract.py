"""Typed public ArkTS caller binding; original ordinary builder/signing owns execution."""
import hashlib
import json
from pathlib import Path
import zipfile

from media_pipeline578 import source, sha, SCENARIOS
from audio_capture_contract import PERMISSIONS as MIC

PERMISSIONS = MIC + [{'name': 'ohos.permission.PRIVACY_WINDOW'}]
DECLARATIONS = ('@ohos.multimedia.media.d.ts', '@ohos.window.d.ts', '@ohos.systemDateTime.d.ts',
                '@ohos.file.fs.d.ts', '@ohos.process.d.ts', '@ohos.abilityAccessCtrl.d.ts', '@ohos.util.d.ts')


def code_assets(hap):
    with zipfile.ZipFile(hap) as archive:
        names = archive.namelist()
        assets = sorted(n for n in names if n.startswith('ets/') and n.endswith('.abc'))
        if not assets or len(assets) > 32 or len(names) != len(set(names)):
            raise ValueError('actual compiled ArkTS code assets required')
        return {n: hashlib.sha256(archive.read(n)).hexdigest() for n in assets}


def inputs(project, sdk, arch, run, scenario, unsigned_hap):
    project, sdk, unsigned_hap = Path(project).resolve(), Path(sdk).resolve(), Path(unsigned_hap).resolve()
    page = project / 'entry/src/main/ets/pages/Index.ets'
    module = project / 'entry/src/main/module.json5'
    config = json.loads(module.read_text())['module']
    if (arch not in ('arm64', 'armv7a', 'x86_64') or scenario not in SCENARIOS or page.read_text() != source(run, scenario) or
            config.get('requestPermissions') != PERMISSIONS or config['abilities'][0].get('backgroundModes', []) != [] or
            json.loads((project / 'AppScope/app.json5').read_text())['app']['bundleName'] != 'org.harmonycontrib.capabilityaudit'):
        raise ValueError('new ordinary media generated caller/permissions/bundle differs')
    info = json.loads((sdk / 'ets/oh-uni-package.json').read_text())
    if info.get('apiVersion') != '26' or info.get('releaseType') != 'Release' or info.get('platformVersion') != '26.0.0':
        raise ValueError('actual API26 Release declarations required; not a persona build pass')
    return {'schema_version': 1, 'kind': 'screen-transcode578', 'role': 'ordinary_app', 'run_id': run,
            'scenario': scenario, 'arch': arch, 'sdk': str(sdk), 'project': str(project),
            'generated_source': str(page), 'generated_source_sha256': sha(page), 'module_sha256': sha(module),
            'template_sha256': sha(Path(__file__).with_name('media_pipeline578_probe.ets')),
            'contract_sha256': sha(Path(__file__)), 'logic_sha256': sha(Path(__file__).with_name('media_pipeline578.py')),
            'request_permissions': PERMISSIONS, 'sdk_declarations': {n: sha(sdk/'ets/api'/n) for n in DECLARATIONS},
            'unsigned_hap': str(unsigned_hap), 'unsigned_hap_sha256': sha(unsigned_hap), 'code_assets': code_assets(unsigned_hap)}


def verify_inputs(value):
    if value != inputs(value['project'], value['sdk'], value['arch'], value['run_id'], value['scenario'], value['unsigned_hap']):
        raise ValueError('actual media build source/SDK/code asset inputs changed')


def verify_hap(hap, value):
    if code_assets(hap) != value['code_assets']:
        raise ValueError('signed ordinary HAP has different actual ArkTS code')
    with zipfile.ZipFile(hap) as archive:
        config = json.loads(archive.read('module.json'))['module']
        permissions = []
        for row in config.get('requestPermissions', []):
            row = dict(row)
            reason_id = row.pop('reasonId', None)
            if reason_id is not None and (type(reason_id) is not int or reason_id <= 0):
                raise ValueError('actual compiled permission reason invalid')
            permissions.append(row)
        if permissions != PERMISSIONS or config['abilities'][0].get('backgroundModes', []) != []:
            raise ValueError('actual signed media HAP permissions/background modes differ')
