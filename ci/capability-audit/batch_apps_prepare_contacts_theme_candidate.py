#!/usr/bin/env python3
"""Regenerate packaging-only candidates from fixed read-only source fixtures."""
import base64
import difflib
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / 'ci/capability-audit/fixtures/batch_apps/contacts_theme'
META = json.loads((FIX / 'inspection.json').read_text())


def original(path):
    entry = META['files'].get(path)
    if entry is None:
        return None
    value = gzip.decompress(base64.b64decode(entry['gzip_base64']))
    assert hashlib.sha256(value).hexdigest() == entry['sha256'], path
    return value


def parse(raw):
    # Use the prepared tool's JSON5 parser; do not install any dependencies.
    parser = '/Volumes/PSSD/qemu/openharmony/prebuilts/tool/command-line-tools/6.x/hvigor/hvigor-ohos-plugin/node_modules/json5'
    script = 'const fs=require("fs"),j=require(process.argv[1]);process.stdout.write(JSON.stringify(j.parse(fs.readFileSync(0,"utf8"))))'
    return json.loads(subprocess.check_output(['node', '-e', script, parser], input=raw))


def document(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def app_target(name, profile, hap, bundle, module):
    return f'''ohos_app("{name}") {{
  deps = []
  certificate_profile = "signature/{profile}.p7b"
  hap_name = "{hap}"
  part_name = "prebuilt_hap"
  subsystem_name = "applications"
  module_install_dir = "app/{bundle}"
  sdk_home = "//prebuilts/ohos-sdk/linux"
  sdk_type_name = [ "sdk.dir" ]
  assemble_type = "assembleHap"
  build_level = "module"
  build_modules = [ "{module}" ]
  js_build_mode = "release"
}}
'''


def emit(project, after):
    component = ROOT / 'patches/common' / project / 'source_provider'
    component.mkdir(parents=True, exist_ok=True)
    patch = []
    files = []
    for relative, value in after.items():
        path = project + '/' + relative
        before = original(path)
        assert before != value, path
        files.append((relative, hashlib.sha256(before).hexdigest() if before is not None else None,
                      hashlib.sha256(value).hexdigest()))
        patch.append(f'diff --git a/{path} b/{path}\n'.encode())
        if before is None:
            patch.append(b'new file mode 100644\n')
        # Preserve exact LF/CRLF bytes from fixed source, including missing EOF newline.
        lines = difflib.unified_diff((before or b'').decode().splitlines(keepends=True),
                                    value.decode().splitlines(keepends=True),
                                    fromfile='a/' + path if before is not None else '/dev/null',
                                    tofile='b/' + path)
        for line in lines:
            patch.append(line.encode())
            if not line.endswith('\n'):
                patch.append(b'\n\\ No newline at end of file\n')
    (component / '0001-build-fixed-real-provider-sources.patch').write_bytes(b''.join(patch))
    verifier = '''#!/usr/bin/env python3
"""Exact source packaging metadata; not SDK, signature or guest acceptance."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

'''
    verifier += f'PROJECT = {project!r}\nREVISION = {META["projects"][project]!r}\nFILES = (\n'
    verifier += ''.join(f'    {entry!r},\n' for entry in files) + ')\n\n\n'
    verifier += 'def validate(root, require_patched=False):\n    return validate_component(root, PROJECT, REVISION, FILES, require_patched)\n'
    (component / 'verify_source.py').write_text(verifier)
    (component / 'apply.sh').write_text('''#!/usr/bin/env bash
set -euo pipefail
component_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec python3 "$component_dir/../../../../../lib/apply_exact_component.py" --component-dir "$component_dir" "$@"
''')
    return {project + '/' + relative: final for relative, _, final in files}


contacts = 'applications/standard/contacts'
theme = 'applications/standard/theme'
profile = parse(original(contacts + '/build-profile.json5'))
for product in profile['app']['products']:
    # Retain target/compatible 23 and all seven modules. GN performs OS signing.
    product.pop('signingConfig', None)
contacts_profile = original(contacts + '/build-profile.json5')
assert contacts_profile.count(b'        "signingConfig": "release",\n') == 1
contacts_profile = contacts_profile.replace(b'        "signingConfig": "release",\n', b'')
assert parse(contacts_profile) == profile
targets = emit(contacts, {
    'BUILD.gn': ('# Copyright (c) 2026 Harmony Contrib\n# SPDX-License-Identifier: Apache-2.0\n'
                 'import("//build/ohos.gni")\n\n'
                 '# The existing entry includes the real Contacts UIExtension and picker pages.\n'
                 + app_target('contacts_hap', 'contacts', 'Contacts', 'com.ohos.contacts', 'entry')).encode(),
    'build-profile.json5': contacts_profile,
})
profile = parse(original(theme + '/build-profile.json5'))
compatible = profile['app'].pop('compatibleSdkVersion')
old_compile = profile['app'].pop('compileSdkVersion')
for product in profile['app']['products']:
    product.pop('signingConfig', None)
    product.update(compileSdkVersion='26.0.0', compatibleSdkVersion=compatible,
                   targetSdkVersion=old_compile, runtimeOS='OpenHarmony')
targets.update(emit(theme, {
    'BUILD.gn': ('# Copyright (c) 2026 Harmony Contrib\n# SPDX-License-Identifier: Apache-2.0\n'
                 'import("//build/ohos.gni")\n\n'
                 '# Renderers only: neither target supplies a wallpaper selection/settings UI.\n'
                 '# The shared HAP graph must select one device module, never install both.\n'
                 + app_target('wallpaper_phone_hap', 'wallpaper', 'Wallpaper', 'com.ohos.wallpaper', 'phone-wallpaper')
                 + '\n' + app_target('wallpaper_pad_hap', 'wallpaper', 'Wallpaper', 'com.ohos.wallpaper', 'pad-wallpaper')).encode(),
    'build-profile.json5': document(profile),
    'oh-package.json5': document({'modelVersion': '6.0.0', 'name': 'wallpaper', 'version': '1.0.0',
                                 'dependencies': {}, 'devDependencies': {}}),
    'hvigor/hvigor-config.json5': document({'modelVersion': '6.0.0', 'dependencies': {},
                                          'execution': {'daemon': False, 'parallel': False}}),
    'product/phone/oh-package.json5': document({'name': 'wallpaper', 'version': '1.0.0', 'dependencies': {}}),
    'product/pad/oh-package.json5': document({'name': 'wallpaper', 'version': '1.0.0', 'dependencies': {}}),
}))
(FIX / 'candidate-hashes.json').write_text(json.dumps(targets, indent=2) + '\n')
print('generated exactly', len(targets), 'upstream packaging targets; no business or signing policy edits')
