"""Record actual two already-closed original IO objects; no executor."""
from pathlib import Path
from usb579_contract import guard, need, doc, ref, dependency


def retain_completed(owner, resources, *, suite_work, archive, main_boot):
    guard();owner.held_binding(owner.vm)
    need(owner.vm is not None and not owner.cleanup_complete and archive==ref(owner.archive) and
        owner.vm.report['archive_sha256']==archive['sha256'], 'one original held main Owner/new archive')
    work=Path(suite_work)
    need(work.is_absolute() and work.resolve()==work and work.is_relative_to(owner.output), 'original suite output only')
    types=dependency('capability578_owned_io')
    actual={}
    for role,folder in [('usb','usb579-shared-device'),('audio','media579-audio10')]:
        matches=[io for io in resources if type(io) is types.OwnedIO and io.owner is owner and
            io.guest is owner.vm and io.output==work/'capability578'/folder]
        need(len(matches)==1 and matches[0]._closed and all(v['child'].reaped and
            type(v['child'].returncode) is int for v in matches[0]._long.values()), 'actual original closed '+role+' IO')
        io=matches[0];closed=doc(ref(io.output/'io.json'))
        need(closed['closed'] is True and closed['commands']==io.receipts and closed['qmp']==io.qmp_receipts,
             'actual original object/stream/QMP retention')
        actual[role]=dict(io=ref(io.output/'io.json'),run=io.run_id,output=str(io.output),
            package_inputs=io.package_inputs,archive_sha256=io.archive_sha256,boot_id=io.boot_id)
    need(actual['usb']['archive_sha256']==actual['audio']['archive_sha256']==archive['sha256'] and
        actual['usb']['boot_id']==actual['audio']['boot_id']==owner.vm.report['test_environment']['boot_id'], 'same actual two IO package/boot')
    report=ref(Path(actual['usb']['output'])/'usb579-shared-device.json')
    audio=ref(Path(actual['audio']['output'])/'evidence.json')
    value=doc(report);need(value['audio_evidence']==audio and value['run']==actual['usb']['run'] and
        value['audio_run']==actual['audio']['run'], 'real shared USB/Audio nonce association')
    result=dict(schema='usb579-actual-closed-two-IO-retention/v1',archive=archive,main_boot=main_boot,
        source_commit=value['source_commit'],boot_id=value['boot_id'],report=report,audio_report=audio,actual=actual,
        original_object_only=True,original_whole_Owner_finish_still_required=True,
        runtime_pass=False,first_artifact_behavior_gate_passed=False)
    path=owner.output/'usb579-retention.json'
    from audio579_common import save
    return save(path,result)
