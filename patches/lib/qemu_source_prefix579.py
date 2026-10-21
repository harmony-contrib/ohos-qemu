#!/usr/bin/env python3
"""Re-enter earlier source components from exact complete retained vectors."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from guarded_source_vector579 import apply, target
from calendar_lifecycle579 import rewind_if_final as rewind_calendar

PATCHES = Path(__file__).resolve().parents[1]
COMPONENTS = (
    ('common/build/sanitizers/qemu_thin_cfi', '0001-retain-cfi-with-bounded-thinlto.patch', 2),
    ('common/foundation/ability/ability_runtime/service_idle_startid',
     '0001-stop-only-the-current-service-request.patch', 18),
    ('common/applications/standard/settings_data/accessibility_notification_defaults',
     '0001-initialize-real-notification-preferences.patch', 2),
    ('common/foundation/multimedia/av_session/qemu_panel_lifecycle',
     '0001-connect-actual-panels-and-guard-session-events.patch', 4),
    ('common/applications/standard/settings/dnd_selection_ids',
     '0001-compose-product-provider-source.patch', 3),
)


def prepare(root):
    # The caller is the original serialized product build. These exact reverse
    # transactions precede the original guards, then the normal hooks reapply
    # the complete final vector before GN/compilation. Unknown/mixed bytes fail.
    rewind_calendar(root)
    for relative, patch, count in COMPONENTS:
        component = PATCHES / relative
        value = json.loads((component / 'source_states.json').read_text())
        if len(value['files']) != count or not value['projects']:
            raise ValueError('fixed complete product source vector required: ' + relative)
        if relative == 'common/foundation/multimedia/av_session/qemu_panel_lifecycle':
            # Complete before/previous/previous-owned/new four-source epochs.
            subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(root), '--rewind'], check=True)
            continue
        if relative == 'common/foundation/ability/ability_runtime/service_idle_startid':
            # The original prefix guard runs before the normal component hook.
            # Normalize only the exact complete known legacy final through that
            # same atomic component, then retain the original reverse transaction.
            legacy = value.get('legacy_final', {})
            previous = value.get('previous_napi_final', {})
            if (value.get('schema') != 'settings579-conditional-idle-stop-source-vector/v3' or
                    set(legacy) != set(value['files']) or set(previous) != set(value['files'])):
                raise ValueError('complete service-idle v3 whole72/previous-NAPI vectors required')
            observed = {name: hashlib.sha256(target(root, name).read_bytes()).hexdigest() for name in value['files']}
            if observed in (legacy, previous):
                subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(root)], check=True)
        reversed_value = dict(value, files={n: list(reversed(pair)) for n, pair in value['files'].items()})
        apply(root, component, reversed_value, reverse=True, patch_name=patch)
    print('Exact source prefixes prepared; behavior acceptance remains in new QEMU')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source_root.resolve())
