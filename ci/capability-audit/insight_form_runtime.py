"""Wait for actual ordinary-widget presentation, preserving every transient frame."""
import json
from pathlib import Path
import time
from guest_ui import LayoutNotReady, NodeNotReady
from run_root_probe import digest
from verify_insight_form_host_results import phase_pixels, verify_layout
from build_insight_form_host_probe import BUNDLE


def capture_phase(ui, output, target_nonce, identifier, state, label, timeout=60):
    output = Path(output)
    if output.exists():
        raise ValueError('fresh widget presentation evidence path required')
    report = dict(status='running', scope='compositor_presentation_only_NOT_archive_or_gate',
        first_artifact_behavior_gate_passed=False, target_nonce=target_nonce,
        form_id=identifier, state=state, samples=[])
    deadline = time.monotonic() + timeout
    stable = 0
    previous = None
    def save():
        output.write_text(json.dumps(report, indent=2) + '\n')
    try:
        while time.monotonic() < deadline:
            sample = dict(sequence=len(report['samples']), elapsed_remaining=deadline - time.monotonic())
            report['samples'].append(sample)
            try:
                layout, path = ui.layout(bundle=BUNDLE, label=label + '-view')
                nodes = verify_layout(layout, target_nonce, identifier, state)
            except (LayoutNotReady, NodeNotReady):
                sample['not_ready'] = 'packaged UITest view not attached'; stable = 0; save(); time.sleep(.25); continue
            sample.update(layout=str(path), layout_sha256=digest(path), nodes=nodes)
            screenshot = ui.screenshot(label=label + '-pixels')
            sample.update(screenshot=str(screenshot), screenshot_sha256=digest(screenshot))
            try:
                metrics, text = phase_pixels(screenshot, layout, target_nonce, identifier, state)
            except ValueError as error:
                if str(error) != 'widget rendered neither its expected card surface nor real data text':
                    raise
                sample['not_ready'] = str(error); stable = 0; save(); time.sleep(.25); continue
            marker = (nodes['frame']['rect'], nodes['marker']['rect'], text.tobytes())
            stable = stable + 1 if marker == previous else 1
            previous = marker
            sample.update(metrics=metrics, consecutive_identical_presentations=stable)
            save()
            if stable == 3:
                report.update(status='pass_presentation_only', layout=str(path), screenshot=str(screenshot))
                save(); return report
            time.sleep(.25)
        raise ValueError('ordinary widget never presented three stable actual card/text frames')
    except Exception as error:
        report.update(status='fail_presentation_only', error=str(error)); save(); raise
