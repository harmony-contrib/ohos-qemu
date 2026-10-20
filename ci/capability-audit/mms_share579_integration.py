"""Fixed hook immediately after the original Share8/MMS1 stage returns.

The actual original suite calls its Select hook at run_packaged_qemu_suite.py
280, before finally/guest.close at 985/1000. Owner.stage runs Select then the
unchanged Share integration, which runs/replays Share8 and MMS1 and performs its
original cleanup before returning. No work is scheduled after canonical().
"""
import json
import secrets

from capability578_owned_io import OwnedIO, reference, require
from capability578_callers import prepare_callers
from capability578_https import OwnedHTTPS
from settings_idle579_bindings import load_ref
from mms_share579_runtime import run


def run_after_original_share(owner, resources, original_result, *, mms_facts, context):
    guest = context['guest']
    owner.held_binding(guest)
    require(owner.vm is guest and type(resources) is list and set(original_result) == {'select375','share578'},
        'same original held Owner and completed original Select/Share return required')
    prior = original_result['share578']
    actual_path = context['suite_work'] / 'share578/integration-report.json'
    require(actual_path.is_file() and not actual_path.is_symlink() and json.loads(actual_path.read_text()) == prior and
        prior['status'] == 'pass_share578_additional_raw_API_slice_ONLY' and prior['cleanup_complete'] is True and
        prior['failures'] == [] and prior['cleanup_errors'] == [] and
        prior['archive_sha256'] == guest.report['archive_sha256'] and
        prior['boot_id'] == guest.report['test_environment']['boot_id'] and
        prior['MMS_draft_cancel']['scope'] == 'pass_narrow_MMS_draft_cancel_ONLY',
        'all original Share8/MMS1 assertions/cleanup must actually finish first')
    original_mms = json.loads(load_ref(prior['MMS_draft_cancel']['evidence']))
    original_share = json.loads(load_ref(prior['collector_report']))
    require(original_mms['status'] == 'pass_narrow_MMS_draft_cancel_ONLY' and
        len(original_mms['cases']) == 1 and original_mms['cases'][0]['case_id'] == 'mms-file-cancel' and
        [case['case_id'] for case in original_share['cases']] ==
            ['read-a','read-b','write-a','text-a','no-grant-a','cancel','death','recovery-a'],
        'the original eight plus one cases must remain present and unchanged')
    # mms_facts comes from the root's actual source-pinned deferred producer,
    # never JSON-selected code, the old Docker guard, or a source/out HAP.
    load_ref(mms_facts)
    context['same_guest']('before-owned-mms-share579-boundaries')
    io = OwnedIO(owner, guest, owner.output / ('mms-share579-' + secrets.token_hex(8)),
        run_id=secrets.token_hex(16), package_inputs={}, prepare_callers=prepare_callers, https_factory=OwnedHTTPS)
    resources.append(io)  # before prepare, install, command or cleanup creation
    row = {'status':'running','archive_sha256':io.archive_sha256,'boot_id':io.boot_id,
        'original_share':reference(actual_path),'mms_facts':mms_facts,'whole_id_closure':False,
        'formally_closed':[],'first_artifact_behavior_gate_passed':False}
    context['suite_report'].setdefault('supplemental_checks',{})['mms-share579-boundaries'] = row
    context['save_suite']()
    try:
        row['result'] = run(io,mms_facts=mms_facts)
        row['status'] = 'actual_raw_boundary_observations_ONLY'
    except Exception as error:
        row.update(status='fail',error=type(error).__name__+': '+str(error))
        evidence = io.output / 'mms-share579/evidence.json'
        if evidence.is_file() and not evidence.is_symlink():
            row['partial_evidence'] = reference(evidence)
        context['suite_report']['failures'].append('mms-share579-boundaries: '+row['error'])
        # Safely cleaned semantic failures remain failures and the original
        # suite continues collecting its other independent QEMU observations.
    finally:
        try:
            io.close()
        except Exception as error:
            from capability578_stage import UnsettledCapability
            row.update(status='fail_cleanup',cleanup_error=type(error).__name__+': '+str(error))
            context['save_suite']()
            raise UnsettledCapability('original MMS/Share resources unsettled: '+str(error)) from error
        context['save_suite']()
    context['same_guest']('after-owned-mms-share579-boundaries')
    return row
