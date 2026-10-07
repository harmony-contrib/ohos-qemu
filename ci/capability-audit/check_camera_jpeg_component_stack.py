#!/usr/bin/env python3
"""Check actual pinned JPEG application and repeated predecessor compatibility.

Only an owned scratch copy is writable. This does not regenerate GN, build,
install, boot, capture pictures or pass the first-artifact gate.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/drivers/peripheral/camera/jpeg_capture'
USB = ROOT / 'patches/common/drivers/peripheral/camera/usb_backend'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    source, work = args.source_root.resolve(), args.work.absolute()
    if not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise ValueError('production source must be mounted read-only')
    if work.parent != Path('/tmp').resolve() or not work.name.startswith('camera-jpeg-component-'):
        raise ValueError('fresh exclusive /tmp/camera-jpeg-component-* required')
    work.mkdir(exist_ok=False)
    modules = []
    for name, path in (('jpeg', COMPONENT / 'verify_source.py'), ('usb', USB / 'check.py')):
        spec = importlib.util.spec_from_file_location('actual_camera_component_' + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    jpeg, usb = modules
    if jpeg.validate(source):
        raise ValueError('isolated fresh application needs the exact pre-JPEG component state')
    project = source / jpeg.PROJECT
    head = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
    if head != jpeg.REVISION:
        raise ValueError('wrong actual peripheral revision')
    names = sorted({entry[0] for entry in jpeg.FILES} | {usb.FILE, usb.CONFIG, usb.PIPELINE, usb.ADAPTER})
    originals = {name: sha(project / name) for name in names}
    recipes = [Path(__file__).resolve(), ROOT / 'patches/lib/apply_exact_component.py',
               ROOT / 'patches/lib/exact_source_states.py', ROOT / 'patches/lib/apply_patch.sh',
               ROOT / 'patches/lib/apply_component_dir.sh']
    recipes += [path for component in (COMPONENT, USB) for path in component.iterdir()
                if path.is_file() and path.suffix in ('.sh', '.py', '.patch')]
    recipe_shas = {str(path): sha(path) for path in sorted(recipes)}
    staged = work / 'source'
    destination = staged / jpeg.PROJECT
    destination.parent.mkdir(parents=True)
    commands = []

    def command(argv, label):
        log = work / (label + '.log')
        with log.open('x') as stream:
            result = subprocess.run(list(map(str, argv)), stdout=stream, stderr=subprocess.STDOUT)
        commands.append({'argv': list(map(str, argv)), 'exit_code': result.returncode,
                         'log': str(log), 'sha256': sha(log)})
        if result.returncode:
            raise ValueError('actual component validation failed: ' + label)

    command(['git', 'clone', '--no-checkout', '--shared', project, destination], 'owned-pinned-git-copy')
    for name in names:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project / name, target)
    for attempt in (1, 2):
        command(['bash', COMPONENT / 'apply.sh', '--source-root', staged], 'jpeg-apply-' + str(attempt))
    jpeg.validate(staged, require_patched=True)
    # In a repeated aggregate plan the earlier USB component runs first.
    command(['bash', USB / 'apply.sh', '--source-root', staged], 'repeat-predecessor-usb-component')
    command(['bash', COMPONENT / 'apply.sh', '--source-root', staged], 'jpeg-after-predecessor-repeat')
    jpeg.validate(staged, require_patched=True)
    if ({name: sha(project / name) for name in names} != originals or
            {str(path): sha(path) for path in sorted(recipes)} != recipe_shas):
        raise ValueError('read-only production or recipe input changed during validation')
    report = {'status': 'pass', 'scope': 'actual_pinned_JPEG_source_apply_repeat_and_USB_predecessor_only',
              'source_revision': head, 'source_readonly': True, 'commands': commands,
              'originals_sha256': originals, 'recipe_sha256': recipe_shas,
              'finals_sha256': {name: sha(destination / name) for name in names},
              'GN_compile_link_or_guest_verified': False, 'first_artifact_behavior_gate_passed': False}
    (work / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print('actual pinned JPEG component and repeated USB predecessor checked; not GN or guest acceptance')


if __name__ == '__main__':
    main()
