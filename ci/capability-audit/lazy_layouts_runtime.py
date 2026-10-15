"""Capture stable native lazy factory geometry and compositor frames."""
import json
from pathlib import Path
import time
from guest_ui import LayoutNotReady, NodeNotReady
from build_arkui_lazy_layouts_probe import BUNDLE
from run_root_probe import digest
from verify_lazy_layouts_results import pixels


def capture(ui,output,nonce,kind,cycle,phase,timeout=60):
    output=Path(output)
    if output.exists():raise ValueError('fresh actual lazy presentation required')
    report=dict(status='running',scope='lazy_layout_compositor_only_NOT_archive_or_gate',run_id=nonce,
        kind=kind,cycle=cycle,phase=phase,first_artifact_behavior_gate_passed=False,samples=[])
    deadline=time.monotonic()+timeout;previous=None;stable=0
    def save():output.write_text(json.dumps(report,indent=2)+'\n')
    try:
        while time.monotonic()<deadline:
            sample=dict(sequence=len(report['samples']));report['samples'].append(sample)
            try:
                label='lazy-'+kind+'-'+str(cycle)+'-'+phase
                layout,path=ui.layout(bundle=BUNDLE,label=label);screenshot=ui.screenshot(label=label)
                sample.update(layout=str(path),layout_sha256=digest(path),screenshot=str(screenshot),screenshot_sha256=digest(screenshot))
                metrics,fingerprint=pixels(screenshot,layout,nonce,kind,cycle,phase)
            except (LayoutNotReady,NodeNotReady,ValueError) as error:
                allowed=('actual lazy challenged text pixels not presented','actual lazy child color not presented',
                    'removed lazy factory retained visible children','removed lazy factory retained painted children',
                    'native waterfall did not change to three columns','native initial waterfall did not use two columns')
                if isinstance(error,ValueError) and not isinstance(error,(LayoutNotReady,NodeNotReady)) and str(error) not in allowed:raise
                sample['not_ready']=str(error);stable=0;previous=None;save();time.sleep(.25);continue
            stable=stable+1 if fingerprint==previous else 1;previous=fingerprint
            sample.update(metrics=metrics,consecutive_identical_presentations=stable);save()
            if stable==3:report['status']='pass_presentation_only';save();return report
            time.sleep(.25)
        raise ValueError('actual lazy scene never presented three stable challenged frames')
    except Exception as error:report.update(status='fail_presentation_only',error=str(error));save();raise
