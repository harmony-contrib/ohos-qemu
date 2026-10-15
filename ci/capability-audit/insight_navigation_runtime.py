"""Capture three stable actual Page/Link text frames, retaining all transients."""
import json
from pathlib import Path
import time
from build_insight_driver_probe import TARGET_BUNDLE
from guest_ui import LayoutNotReady, NodeNotReady, select_node
from run_root_probe import digest
from verify_insight_navigation_results import marker_text, phase_pixels


def capture_phase(ui, output, kind, cycle, target_nonce, caller_nonce, timeout=60):
    output = Path(output)
    if output.exists(): raise ValueError('fresh navigation presentation evidence path required')
    report = dict(status='running', scope='navigation_compositor_only_NOT_archive_or_gate',
        first_artifact_behavior_gate_passed=False, kind=kind, cycle=cycle,
        target_nonce=target_nonce, caller_nonce=caller_nonce, samples=[])
    label = 'navigation-' + kind + '-' + str(cycle)
    expected = marker_text(kind, cycle, target_nonce, caller_nonce)
    deadline = time.monotonic() + timeout; stable = 0; previous = None
    def save(): output.write_text(json.dumps(report, indent=2) + '\n')
    try:
        while time.monotonic() < deadline:
            sample = dict(sequence=len(report['samples'])); report['samples'].append(sample)
            try:
                layout, path = ui.layout(bundle=TARGET_BUNDLE, label=label + '-view')
                node = select_node(layout, TARGET_BUNDLE, text=expected)
            except (LayoutNotReady, NodeNotReady):
                sample['not_ready'] = 'actual challenged view not attached'; stable = 0; save(); time.sleep(.25); continue
            sample.update(layout=str(path), layout_sha256=digest(path), selected_node=node)
            screenshot = ui.screenshot(label=label + '-pixels')
            sample.update(screenshot=str(screenshot), screenshot_sha256=digest(screenshot))
            try: pixels, text = phase_pixels(screenshot, node)
            except ValueError as error:
                if str(error) != 'metadata success reused a blank or earlier shorter compositor view': raise
                sample['not_ready'] = str(error); stable = 0; save(); time.sleep(.25); continue
            current = node['rect'], text.tobytes()
            stable = stable + 1 if current == previous else 1; previous = current
            sample.update(metrics=pixels, consecutive_identical_presentations=stable); save()
            if stable == 3:
                report.update(status='pass_presentation_only', layout=str(path), selected_node=node,
                    layout_sha256=digest(path), screenshot=str(screenshot), screenshot_sha256=digest(screenshot))
                save(); return report
            time.sleep(.25)
        raise ValueError('navigation never presented three stable actual challenged text frames')
    except Exception as error:
        report.update(status='fail_presentation_only', error=str(error)); save(); raise
