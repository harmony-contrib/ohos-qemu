"""Data/source installation into the parent's existing SDK builder only."""
from pathlib import Path
import hashlib
import json
import re
from graphics3d_asset import asset, invalid_asset, descriptors, specification

ACTIONS = ['load', 'frame', 'translate', 'frame', 'destroy', 'frame', 'invalid',
           'load', 'frame', 'translate', 'frame', 'destroy', 'frame', 'cleanup', 'quiet']

def commands(run, boot, operation_ids):
    specification(run)
    if not isinstance(boot, str) or not re.fullmatch('[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', boot):
        raise ValueError('Actual original Owner boot ID required')
    if (len(operation_ids) != len(ACTIONS) or len(set(operation_ids)) != len(ACTIONS) or
            any(not isinstance(op, str) or not re.fullmatch('[a-f0-9]{32}', op) for op in operation_ids)):
        raise ValueError('One original Owner fresh operation nonce per command required')
    return [dict(run_id=run, boot_id=boot, operation_id=op, action=action,
                 translate_x=specification(run)['translate_x'], wait_ms=1500)
            for action, op in zip(ACTIONS, operation_ids)]

def install(root: Path, run: str):
    specification(run)
    here = Path(__file__).with_name('graphics3d')
    targets = [('EntryAbility.ets', 'ets/entryability/EntryAbility.ets'),
               ('Index.ets', 'ets/pages/Index.ets'),
               ('GraphicsController.ets', 'ets/graphics3d/GraphicsController.ets')]
    sources = {}
    for source, destination in targets:
        text = (here / source).read_text()
        if source == 'GraphicsController.ets' and text.count('__GRAPHICS3D_RUN__') != 1:
            raise ValueError('Actual caller nonce marker drift')
        target = root / 'entry/src/main' / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text.replace('__GRAPHICS3D_RUN__', run))
        sources[destination] = hashlib.sha256(target.read_bytes()).hexdigest()
    raw = root / 'entry/src/main/resources/rawfile'
    raw.mkdir(parents=True, exist_ok=True)
    (raw / 'graphics3d-audit.glb').write_bytes(asset(run))
    (raw / 'graphics3d-invalid.glb').write_bytes(invalid_asset())
    path = root / 'entry/src/main/module.json5'
    module = json.loads(path.read_text())
    abilities = module['module']['abilities']
    if len(abilities) != 1 or abilities[0]['name'] != 'EntryAbility':
        raise ValueError('Existing minimal ability shape changed')
    abilities[0]['launchType'] = 'singleton'
    module['module']['requestPermissions'] = []
    path.write_text(json.dumps(module, indent=2) + '\n')
    (root / 'graphics3d-inputs.json').write_text(json.dumps({
        'schema': 1, 'run_id': run, 'source_only': True, 'sources': sources,
        'assets': descriptors(run), 'geometry': specification(run),
        'raw_path': 'files/graphics3d-' + run + '.jsonl',
        'actual_sdk': None, 'actual_package': None, 'actual_guest': None,
        'closed_ids': [], 'full_graphics3d_verified': False}, indent=2) + '\n')
