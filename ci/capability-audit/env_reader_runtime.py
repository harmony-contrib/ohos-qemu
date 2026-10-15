"""Retain transient frames until the actual inherited or measured scene is stable."""
import json
from pathlib import Path
import time
from build_arkui_env_reader_probe import BUNDLE
from guest_ui import LayoutNotReady, NodeNotReady
from run_root_probe import digest
from verify_env_reader_results import pixels


def capture(ui, output, nonce, family, cycle, phase, density, timeout=60):
    output = Path(output)
    if output.exists(): raise ValueError('fresh environment/reader presentation required')
    report = dict(status='running',scope='environment_reader_compositor_only_NOT_archive_or_gate',
        run_id=nonce,family=family,cycle=cycle,phase=phase,density=density,
        first_artifact_behavior_gate_passed=False,samples=[])
    def save(): output.write_text(json.dumps(report,indent=2)+'\n')
    deadline = time.monotonic()+timeout; previous = None; stable = 0
    try:
        while time.monotonic()<deadline:
            sample = dict(sequence=len(report['samples'])); report['samples'].append(sample)
            try:
                label = 'env-reader-'+family+'-'+str(cycle)+'-'+phase
                layout,path = ui.layout(bundle=BUNDLE,label=label)
                screenshot = ui.screenshot(label=label)
                sample.update(layout=str(path),layout_sha256=digest(path),screenshot=str(screenshot),screenshot_sha256=digest(screenshot))
                metrics,fingerprint = pixels(screenshot,layout,nonce,family,cycle,phase,density)
            except (LayoutNotReady,NodeNotReady) as error:
                sample['not_ready']=str(error);previous=None;stable=0;save();time.sleep(.25);continue
            except ValueError as error:
                if str(error) not in ('removed environment/reader retained a visible scene',
                    'actual child row did not follow inherited direction',
                    'actual environment child color or text not presented',
                    'actual native reader geometry does not match its measured dimensions',
                    'actual environment/reader challenged text not painted'): raise
                sample['not_ready']=str(error);previous=None;stable=0;save();time.sleep(.25);continue
            stable = stable+1 if previous==fingerprint else 1;previous=fingerprint
            sample.update(metrics=metrics,consecutive_identical_presentations=stable);save()
            if stable==3:report['status']='pass_presentation_only';save();return report
            time.sleep(.25)
        raise ValueError('environment/reader never presented three stable challenged frames')
    except Exception as error:report.update(status='fail_presentation_only',error=str(error));save();raise
