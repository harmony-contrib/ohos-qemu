"""Source installer for the existing build_hap_probe SDK process; no executor/Owner."""
from pathlib import Path
import json
import re

def install(root: Path, nonce: str) -> None:
    if not re.fullmatch(r'[0-9a-f]{32}', nonce):
        raise ValueError('Fresh original Owner nonce required')
    fixtures = Path(__file__).with_name('location_eight')
    for name, relative in [('EntryAbility.ets', 'entry/src/main/ets/entryability/EntryAbility.ets'),
                           ('Index.ets', 'entry/src/main/ets/pages/Index.ets')]:
        content = (fixtures / name).read_text()
        if name == 'EntryAbility.ets' and content.count('__LOCATION_EIGHT_RUN__') != 1:
            raise ValueError('Caller nonce marker drift')
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content.replace('__LOCATION_EIGHT_RUN__', nonce))
    path = root / 'entry/src/main/module.json5'
    module = json.loads(path.read_text())
    module['module']['requestPermissions'] = [
        {'name': p, 'reason': '$string:permission_reason',
         'usedScene': {'abilities': ['EntryAbility'], 'when': 'inuse'}}
        for p in ['ohos.permission.APPROXIMATELY_LOCATION', 'ohos.permission.LOCATION']]
    # Standard launch-mode state is necessary for onNewWant to reach the same native registrations.
    abilities = module['module']['abilities']
    if len(abilities) != 1 or abilities[0]['name'] != 'EntryAbility':
        raise ValueError('Original minimal app ability changed')
    abilities[0]['launchType'] = 'singleton'
    path.write_text(json.dumps(module, ensure_ascii=False, indent=2) + '\n')
    (root / 'location-eight-inputs.json').write_text(json.dumps({
        'schema': 1, 'run_id': nonce, 'source_only': True,
        'actual_sdk': None, 'actual_package': None, 'actual_guest': None,
        'raw_path': 'files/location-eight-' + nonce + '.jsonl'}, indent=2) + '\n')
