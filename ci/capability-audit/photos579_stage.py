"""Fixed Root seams, original Owner/Authority/OwnedIO only."""
from pathlib import Path
import json
import secrets

from capability578_owned_io import OwnedIO
from capability578_https import OwnedHTTPS
from capability578_stage import read_inputs, UnsettledCapability
import apps_providers579_knowledge as knowledge
from capability578_callers import prepare_callers as original_callers
from photos579_callers import prepare_callers
from photos579_runtime import run_on_held_io
from photos579_project import sources
from photos579_raw import need, ref, document

ROOT = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/ci/capability-audit')
_installed = False


def install_true2in1_preparation():
    """Call once in Root main before the original capability installer.

    The original command_with_knowledge_inputs still constructs/registers its
    one IO and keeps the exact CLI argv. This adds the real form role batch to
    the original manifest, on that existing IO. Phone is unchanged.
    """
    global _installed
    sources()
    original = knowledge.prepare_knowledge_manifest
    need(not _installed and Path(knowledge.__file__).resolve() == ROOT/'apps_providers579_knowledge.py' and
        Path(original.__code__.co_filename).resolve() == Path(knowledge.__file__),
        'one fixed wrapper over actual original manifest producer')
    def same_io_manifest(io, prepared, form_prepared=None):
        need(form_prepared is None, 'no external form batch substitution')
        environment = io.guest.report['test_environment']
        if environment['device_type'] == '2in1':
            form_prepared = original_callers(io, 'apps_providers579', 'photosform', io.run_id,
                ('normal','grant','denied'), {'profile':'2in1','udid':io.udid})
        manifest = original(io, prepared, form_prepared)
        if form_prepared is not None:
            from batch_media_knowledge_project import check_sdk
            value = document(manifest)
            receipts = io.output/'photos579-knowledge-production-receipts.json'
            receipts.write_text(json.dumps(dict(boot_id=io.boot_id,archive_sha256=io.archive_sha256,
                target=io.target,commands=io.receipts,qmp_records=io.qmp_receipts),indent=2)+'\n')
            value['photos579_production'] = dict(receipts=ref(receipts),sdk=check_sdk(io.owner.config['sdk'],'2in1'))
            Path(manifest['path']).write_text(json.dumps(value,indent=2)+'\n')
            manifest = ref(manifest['path'])
        return manifest
    knowledge.prepare_knowledge_manifest = same_io_manifest
    _installed = True


def run_after_knowledge(owner, resources, inputs_ref, **context):
    """Root fixed held-stage chain: original Knowledge22 first, then this.

    Root calls this after its existing Knowledge supplement. It neither
    replaces the canonical dispatcher nor clears any suite failure.
    """
    sources()
    guest = context['guest']
    owner.held_binding(guest)
    need(owner.vm is guest and type(resources) is list, 'same held original main scope')
    row = dict(schema='actual-photos579-whole-provider-stage/v1',
        archive_sha256=guest.report['archive_sha256'], boot_id=guest.report['test_environment']['boot_id'],
        profile=guest.report['test_environment']['device_type'], status='running',
        original_knowledge=None, restart=None, original_io=None, close_span=None,
        failures=[], formally_closed=[], runtime_pass=False, first_artifact_behavior_gate_passed=False)
    context['suite_report'].setdefault('supplemental_checks', {})['photos579'] = row
    context['save_suite']()
    if row['profile'] != '2in1':
        need(row['profile']=='phone', 'only original phone or true2in1 product')
        row.update(status='not_applicable_exact_2in1_whole_ID',
            original_id='behavior:photo-provider-not-activated-2in1')
        context['save_suite']()
        return row
    io = None
    try:
        context['same_guest']('before-photos579-provider-restart')
        old = context['suite_report']['checks']['knowledge-holiday']
        expected = Path(context['suite_work'])/'knowledge-holiday/evidence.json'
        need(Path(old['evidence'])==expected, 'original actual22 evidence location')
        row['original_knowledge'] = dict(path=str(expected),sha256=old['sha256'])
        prior = document(row['original_knowledge'])
        # A safely cleaned business failure remains in the original suite and
        # final replay; it does not prevent collecting a separate restart.
        need(prior['cleanup_complete'] is True and not prior['cleanup_errors'] and
            prior['archive_sha256']==row['archive_sha256'] and prior['boot_id']==row['boot_id'],
            'original22 cleanup and actual same boot required before restart')
        inputs = read_inputs(inputs_ref,owner)
        io = OwnedIO(owner,guest,owner.output/('photos579-restart-'+secrets.token_hex(8)),
            run_id=secrets.token_hex(16),package_inputs={name:inputs[name] for name in
                ('providers','native_helpers','native_addons')},
            prepare_callers=prepare_callers,https_factory=OwnedHTTPS)
        resources.append(io)  # Before any SDK, signing or guest operation.
        io.environment['permission_allow_text']=inputs['permission_allow_text']
        row['restart']=run_on_held_io(io)
        value=document(row['restart'])
        row['failures'].extend(value['failures'])
        row['status']='actual_restart_collected' if not row['failures'] else 'fail_business'
    except Exception as error:
        row['failures'].append(dict(type=type(error).__name__,message=str(error)))
        row['status']='fail'
    finally:
        if io is not None:
            at,qt=len(io.receipts),len(io.qmp_receipts)
            try:
                cleanup=io.close()
                span=dict(schema='actual-photos579-final-IO-close/v1',cleanup=cleanup,
                    commands=[io.ref_receipt(r) for r in io.receipts[at:]],qmp_records=io.qmp_receipts[qt:])
                destination=io.output/'photos579-close.json'
                destination.write_text(json.dumps(span,indent=2)+'\n')
                row.update(original_io=ref(io.output/'io.json'),close_span=ref(destination))
            except Exception as error:
                row['status']='fail_cleanup'
                context['save_suite']()
                raise UnsettledCapability('Photos579 original IO remains unsettled: '+str(error)) from error
        if row['failures']:
            context['suite_report']['failures'].append('photos579: '+repr(row['failures']))
        context['save_suite']()
    context['same_guest']('after-photos579-provider-restart')
    return row
