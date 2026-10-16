#!/usr/bin/env python3
"""Build reviewable exact-source components from fixed before/after fixtures."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'ci/capability-audit/fixtures/batch_media/wallpaper_settings'
GROUPS = {
    'applications/standard/settings': 'patches/common/applications/standard/settings/wallpaper_settings',
    'base/theme/wallpaper_mgr': 'patches/common/base/theme/wallpaper_mgr/qemu_renderer',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    provenance = json.loads((FIXTURE / 'provenance.json').read_text())
    before, after = FIXTURE / 'before', FIXTURE / 'after'
    for name, row in provenance['files'].items():
        if row['sha256'] is not None and sha((before / name).read_bytes()) != row['sha256']:
            raise ValueError('fixed wallpaper source fixture drift: ' + name)
    targets = {}
    for project, relative_component in GROUPS.items():
        component = ROOT / relative_component
        component.mkdir(parents=True, exist_ok=True)
        files, patch = [], []
        for path in sorted((after / project).rglob('*')):
            if not path.is_file():
                continue
            relative = path.relative_to(after).as_posix()
            original = before / relative
            old = original.read_bytes() if original.exists() else None
            new = path.read_bytes()
            if old == new:
                continue
            files.append((path.relative_to(after / project).as_posix(), sha(old) if old is not None else None, sha(new)))
            patch.append('diff --git a/' + relative + ' b/' + relative + '\n')
            if old is None:
                patch.append('new file mode 100644\n')
            for line in difflib.unified_diff((old or b'').decode().splitlines(keepends=True), new.decode().splitlines(keepends=True),
                    fromfile='a/' + relative if old is not None else '/dev/null', tofile='b/' + relative):
                patch.append(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n')
            targets[relative] = {'before_sha256': files[-1][1], 'after_sha256': files[-1][2]}
        if len(files) != (6 if project.startswith('applications/') else 2):
            raise ValueError('expected exactly the eight root-owned targets')
        (component / '0001-real-wallpaper-settings-and-renderer.patch').write_text(''.join(patch))
        (component / 'verify_source.py').write_text('''#!/usr/bin/env python3
"""Require the complete fixed-source wallpaper component; no runtime claim."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component
PROJECT = ''' + repr(project) + '\nREVISION = ' + repr(provenance['revisions'][project]) + '\nFILES = ' + repr(tuple(files)) + '''


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)
''')
        apply = component / 'apply.sh'
        apply.write_text('''#!/usr/bin/env bash
set -euo pipefail
component_dir="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$component_dir/../../../../../lib/apply_exact_component.py" --component-dir "$component_dir" "$@"
''')
        apply.chmod(0o755)
    (FIXTURE / 'targets.json').write_text(json.dumps(targets, indent=2) + '\n')
    print(json.dumps({'targets': len(targets), 'scope': 'source components only; no SDK/image/guest proof'}))


if __name__ == '__main__':
    main()
