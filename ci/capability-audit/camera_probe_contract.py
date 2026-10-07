#!/usr/bin/env python3
"""Bind the real Camera test sources and trusted permission-dialog labels."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
PERMISSION_BUNDLE = 'com.ohos.permissionmanager'
SCOPE = 'ordinary_public_Camera_preview_photo_recreation_only'


def sha(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Camera contract needs a regular file: ' + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(project, sdk, arch, run):
    if arch not in ('arm64', 'armv7a', 'x86_64') or re.fullmatch('[0-9a-f]{32}', run or '') is None:
        raise ValueError('actual Camera architecture and fresh nonce required')
    project, sdk = Path(project), Path(sdk)
    names = ('camera_probe.ets', 'camera_hap_probe.cpp', 'probes/camera_public.cpp')
    headers = sorted((sdk / 'native/sysroot/usr/include/ohcamera').glob('*.h'))
    if len(headers) < 5:
        raise ValueError('actual public Camera NDK header set missing')
    declaration = sdk / 'ets/api/@ohos.multimedia.camera.d.ts'
    page = project / 'entry/src/main/ets/pages/Index.ets'
    if page.read_text() != (ROOT / names[0]).read_text().replace('__CAMERA_RUN_ID__', run):
        raise ValueError('Camera page differs from the current nonce-bearing source')
    return {'schema_version': 1, 'scope': SCOPE, 'role': 'ordinary_app', 'run_id': run, 'arch': arch,
            'request_permissions': ['ohos.permission.CAMERA'],
            'source_sha256': {name: sha(ROOT / name) for name in names},
            'page_sha256': sha(page),
            'sdk_files_sha256': {str(path.resolve()): sha(path) for path in [declaration, *headers]}}


def verify_inputs(document, project, run, arch):
    if (document.get('scope') != SCOPE or document.get('role') != 'ordinary_app' or
            document.get('run_id') != run or document.get('arch') != arch or
            document.get('request_permissions') != ['ohos.permission.CAMERA']):
        raise ValueError('Camera compiled contract role/nonce/ABI/permissions differ')
    names = ('camera_probe.ets', 'camera_hap_probe.cpp', 'probes/camera_public.cpp')
    if document.get('source_sha256') != {name: sha(ROOT / name) for name in names}:
        raise ValueError('Camera compiled sources differ from the current tests')
    page = Path(project) / 'entry/src/main/ets/pages/Index.ets'
    if (sha(page) != document.get('page_sha256') or
            page.read_text() != (ROOT / names[0]).read_text().replace('__CAMERA_RUN_ID__', run)):
        raise ValueError('Camera generated page changed or used another nonce')
    sdk_files = document.get('sdk_files_sha256', {})
    if (not isinstance(sdk_files, dict) or len(sdk_files) < 6 or
            sum(Path(name).name == '@ohos.multimedia.camera.d.ts' for name in sdk_files) != 1 or
            any(sha(Path(name)) != value for name, value in sdk_files.items())):
        raise ValueError('Camera actual SDK declarations/headers missing or changed')
    for name in sdk_files:
        path = Path(name)
        if (not path.is_absolute() or not (path.name == '@ohos.multimedia.camera.d.ts' or
                (path.parent.name == 'ohcamera' and path.suffix == '.h'))):
            raise ValueError('unexpected Camera SDK contract file')


def permission_labels(source_root):
    base = Path(source_root) / 'applications/standard/permission_manager'
    main = base / 'permissionmanager/src/main'
    model = main / 'ets/common/model/permissionGroup.ets'
    dialog = main / 'ets/pages/dialogPlus.ets'
    strategy = main / 'ets/common/permissionGroupManager/CameraStrategy.ets'
    base_strategy = main / 'ets/common/base/BasePermissionStrategy.ets'
    if ("$r('app.string.group_label_camera', appName)" not in strategy.read_text() or
            'getButtonList(' in strategy.read_text() or
            not re.search(r'getButtonList\(\): ButtonStatus\[\]\s*\{\s*return '
                          r'\[ButtonStatus\.DENY, ButtonStatus\.ALLOW\];\s*\}', base_strategy.read_text())):
        raise ValueError('actual Camera user-grant title/default-button strategy changed')
    model_text = model.read_text()
    if ("[ButtonStatus.ALLOW, $r('app.string.allow')]" not in model_text or
            not re.search(r'new GroupInfo\(PermissionGroup\.CAMERA,.*?\[ButtonStatus\.DENY, ButtonStatus\.ALLOW\]',
                          model_text)):
        raise ValueError('actual Camera permission button protocol changed')
    dialog_text = dialog.read_text()
    if 'Button(buttonResource.get(' not in dialog_text or 'this.processClick(' not in dialog_text:
        raise ValueError('actual trusted grant-dialog implementation changed')
    resources = sorted((main / 'resources').glob('*/element/string.json'))
    labels, hashes = set(), {str(path.relative_to(base)): sha(path)
                            for path in (model, dialog, strategy, base_strategy)}
    for resource in resources:
        values = json.loads(resource.read_text())['string']
        matches = [row['value'] for row in values if row['name'] == 'allow']
        if not matches and resource != main / 'resources/base/element/string.json':
            hashes[str(resource.relative_to(base))] = sha(resource)
            continue  # Partial locale resources use the real base fallback.
        if len(matches) != 1 or not isinstance(matches[0], str) or not matches[0]:
            raise ValueError('actual trusted allow resource missing/ambiguous')
        labels.add(matches[0])
        hashes[str(resource.relative_to(base))] = sha(resource)
    if not labels:
        raise ValueError('actual permission-manager localized labels missing')
    return {'schema_version': 1, 'scope': 'actual_trusted_Camera_ALLOW_button_resources_only',
            'bundle': PERMISSION_BUNDLE, 'allow_labels': sorted(labels), 'files_sha256': hashes}


def select_permission(layout, labels):
    from guest_ui import select_node
    if (labels.get('bundle') != PERMISSION_BUNDLE or
            labels.get('scope') != 'actual_trusted_Camera_ALLOW_button_resources_only' or
            not labels.get('files_sha256') or not labels.get('allow_labels')):
        raise ValueError('actual trusted permission-manager label provenance required')
    pending = [(root, '', 0) for root in (layout if isinstance(layout, list) else [layout])]
    texts, count = [], 0
    while pending:
        node, inherited, depth = pending.pop()
        count += 1
        if count > 100000 or depth > 256 or not isinstance(node, dict):
            raise ValueError('malformed permission dialog hierarchy')
        attrs, children = node.get('attributes'), node.get('children', [])
        if not isinstance(attrs, dict) or not isinstance(children, list):
            raise ValueError('malformed permission dialog node')
        bundle = attrs.get('bundleName') or inherited
        if bundle == PERMISSION_BUNDLE and attrs.get('visible') == 'true':
            texts.append(attrs.get('text', ''))
        pending.extend((child, bundle, depth + 1) for child in children)
    if not any(isinstance(text, str) and 'Capability audit' in text for text in texts):
        raise ValueError('trusted permission dialog is not for the dedicated Camera audit app')
    candidates = []
    for text in labels['allow_labels']:
        if text in texts:
            candidates.append(select_node(layout, PERMISSION_BUNDLE, text=text, clickable=True))
    if len(candidates) != 1:
        raise ValueError('require one actual trusted Camera Allow control')
    return candidates[0]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(permission_labels(args.source_root), ensure_ascii=False))
