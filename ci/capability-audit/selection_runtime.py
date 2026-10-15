"""Capture actual selection/menu frames until three challenged crops are stable."""
import json
from pathlib import Path
import time
from guest_ui import LayoutNotReady, NodeNotReady
from build_arkui_selection_probe import BUNDLE
from run_root_probe import digest
from verify_selection_results import pixels


def capture(ui, output, nonce, role, cycle, phase, timeout=60):
    output = Path(output)
    if output.exists(): raise ValueError('fresh selection presentation path required')
    report = dict(status='running', scope='selection_compositor_only_NOT_archive_or_gate',
                  run_id=nonce, role=role, cycle=cycle, phase=phase,
                  first_artifact_behavior_gate_passed=False, samples=[])
    def save(): output.write_text(json.dumps(report,indent=2)+'\n')
    previous = None; stable = 0; deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            sample = dict(sequence=len(report['samples'])); report['samples'].append(sample)
            try:
                label = 'selection-' + role + '-' + str(cycle) + '-' + phase
                layout, path = ui.layout(bundle=BUNDLE,label=label)
                screenshot = ui.screenshot(label=label)
                sample.update(layout=str(path),layout_sha256=digest(path),
                              screenshot=str(screenshot),screenshot_sha256=digest(screenshot))
                metrics, fingerprint = pixels(screenshot,layout,nonce,role,cycle,phase)
            except (LayoutNotReady,NodeNotReady) as error:
                sample['not_ready'] = str(error); previous = None; stable = 0
                save(); time.sleep(.25); continue
            except ValueError as error:
                if str(error) not in ('actual selection text pixels not presented',
                    'actual selected or cleared text background not presented',
                    'cleared selection retained its native menu',
                    'removed selection retained a visible child'): raise
                sample['not_ready'] = str(error); previous = None; stable = 0
                save(); time.sleep(.25); continue
            stable = stable + 1 if fingerprint == previous else 1; previous = fingerprint
            sample.update(metrics=metrics,consecutive_identical_presentations=stable); save()
            if stable == 3:
                report['status'] = 'pass_presentation_only'; save(); return report
            time.sleep(.25)
        raise ValueError('selection never presented three stable challenged frames')
    except Exception as error:
        report.update(status='fail_presentation_only',error=str(error)); save(); raise
