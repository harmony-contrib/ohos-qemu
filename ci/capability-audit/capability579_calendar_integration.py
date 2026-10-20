"""Fixed Calendar business seams on the original main guest and real reboot.

Private source-kit phase callables are imported by the reviewed root entry;
data never selects executable code. Each actual operation remains under the
original Owner, Authority and lease, including cleanup after semantic failures.
"""
import json
from pathlib import Path
import secrets

from capability578_callers import prepare_callers
from capability578_https import OwnedHTTPS
from capability578_owned_io import OwnedIO, reference, require
from capability578_stage import data_file, read_inputs, UnsettledCapability


def run_held_phase1(owner, resources, inputs_ref, *, phase1, **context):
    guest = context['guest']
    owner.held_binding(guest)
    require(owner.vm is guest and type(resources) is list and callable(phase1),
            'actual original main guest and fixed Calendar phase1 required')
    inputs = read_inputs(inputs_ref, owner)
    context['same_guest']('before-calendar579-phase1')
    io = OwnedIO(owner, guest, owner.output / ('calendar579-phase1-' + secrets.token_hex(8)),
        run_id=secrets.token_hex(16), package_inputs={name: inputs[name] for name in
            ('providers', 'native_helpers', 'native_addons')},
        prepare_callers=prepare_callers, https_factory=OwnedHTTPS)
    resources.append(io)
    io.environment['permission_allow_text'] = inputs['permission_allow_text']
    row = {'status': 'running', 'archive_sha256': io.archive_sha256, 'boot_id': io.boot_id,
           'inputs': inputs_ref, 'first_artifact_behavior_gate_passed': False}
    context['suite_report'].setdefault('supplemental_checks', {})['calendar579-phase1'] = row
    context['save_suite']()
    try:
        phase1_ref = phase1(io)
        require(type(phase1_ref) is dict and set(phase1_ref) == {'path', 'sha256'} and
                Path(phase1_ref['path']).is_relative_to(io.output), 'actual Calendar phase1 report Ref required')
        data_file(phase1_ref)
        from capability579_calendar_owner import seal_phase1
        row['resource_binding'] = seal_phase1(io, phase1_ref)
        row.update(status='actual_phase1_sealed_pending_second_boot', evidence=phase1_ref)
    except Exception as error:
        row.update(status='fail', error=type(error).__name__ + ': ' + str(error))
        context['suite_report']['failures'].append('calendar579-phase1: ' + row['error'])
    finally:
        try:
            io.close()
        except Exception as error:
            row.update(status='fail_cleanup', cleanup_error=type(error).__name__ + ': ' + str(error))
            context['save_suite']()
            raise UnsettledCapability('Calendar phase1 cleanup unsettled: ' + str(error)) from error
        context['save_suite']()
    context['same_guest']('after-calendar579-phase1')
    return row


def run_after_main(owner, resources, inputs_ref, *, phase2):
    require(callable(phase2) and type(resources) is list, 'fixed Calendar phase2 and actual original table required')
    sealed = [io for io in resources if type(io) is OwnedIO and io.owner is owner and
              io.guest is owner.vm and hasattr(io, 'calendar579_phase1_binding')]
    if len(sealed) == 1:
        from capability579_calendar_owner import run_on_original_owner
        result = run_on_original_owner(owner, resources, inputs_ref,
            phase1_ref=sealed[0].calendar579_phase1_ref, phase2=phase2)
    else:
        require(not sealed, 'ambiguous Calendar first-boot ownership; preserve original resources')
        result = {'status': 'fail', 'failures': ['actual sealed Calendar phase1 is missing'],
                  'cleanup_complete': all(getattr(row, '_closed', False) for row in resources),
                  'runtime_pass': False, 'first_artifact_behavior_gate_passed': False}
        require(result['cleanup_complete'], 'unsettled original resource prevents further guests')
    path = owner.output / 'calendar579-after-main.json'
    with path.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return {'result': result, 'evidence': reference(path), 'first_artifact_behavior_gate_passed': False}
