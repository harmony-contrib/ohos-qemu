"""Retain actual transient frames until the lazy layout is visibly stable."""
import json
from pathlib import Path
import time
from guest_ui import LayoutNotReady, NodeNotReady
from run_root_probe import digest
from verify_lazy_column_results import pixels


def capture(ui, output, nonce, cycle, phase, timeout=60):
    output=Path(output)
    if output.exists():raise ValueError('fresh lazy presentation path required')
    report=dict(status='running',scope='lazy_compositor_only_NOT_archive_or_gate',run_id=nonce,
        cycle=cycle,phase=phase,first_artifact_behavior_gate_passed=False,samples=[])
    deadline=time.monotonic()+timeout;previous=None;stable=0
    def save():output.write_text(json.dumps(report,indent=2)+'\n')
    try:
        while time.monotonic()<deadline:
            sample=dict(sequence=len(report['samples']));report['samples'].append(sample)
            try:
                from build_arkui_lazy_types_probe import BUNDLE
                layout,path=ui.layout(bundle=BUNDLE,label='lazy-'+str(cycle)+'-'+phase)
                screenshot=ui.screenshot(label='lazy-'+str(cycle)+'-'+phase)
                sample.update(layout=str(path),layout_sha256=digest(path),screenshot=str(screenshot),screenshot_sha256=digest(screenshot))
                metrics,fingerprint=pixels(screenshot,layout,nonce,cycle,phase)
            except (LayoutNotReady,NodeNotReady) as error:
                sample['not_ready']=str(error);stable=0;previous=None;save();time.sleep(.25);continue
            except ValueError as error:
                if str(error) not in ('actual lazy text pixels are not presented','actual lazy item color is not presented',
                                      'removed LazyColumn retained a visible child',
                                      'removed LazyColumn retained painted item pixels'):raise
                sample['not_ready']=str(error);stable=0;previous=None;save();time.sleep(.25);continue
            stable=stable+1 if fingerprint==previous else 1;previous=fingerprint
            sample.update(metrics=metrics,consecutive_identical_presentations=stable);save()
            if stable==3:report['status']='pass_presentation_only';save();return report
            time.sleep(.25)
        raise ValueError('lazy native scene never presented three stable challenged frames')
    except Exception as error:report.update(status='fail_presentation_only',error=str(error));save();raise
