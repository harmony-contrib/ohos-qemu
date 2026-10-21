"""One exact original ID, supported raw proposal; no cloud/whole-ID exemption."""
from pathlib import Path
from photos579_raw import need, checked, document, ref
from photos579_project import sources
from photos579_replay import replay_photos, ID

LEDGER_SHA='54cac89929c14de4b3e384b1ab0316b9cc9d3aef19668ff4591f73fdadfff28c'
LEDGER=Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu/docs/capability-audit/integration-20261019/remaining-requirements.json')


def original_row(original_ledger):
    need(checked(original_ledger)==LEDGER and original_ledger['sha256']==LEDGER_SHA,
        'the immutable original82 row alone defines this whole-ID scope')
    value=document(original_ledger)
    need(len(value['requirements'])==82 and len({row['id'] for row in value['requirements']})==82,
        'original82 immutable selector')
    rows=[row for row in value['requirements'] if row['id']==ID]
    need(len(rows)==1 and rows[0]['next_required']=='核对实际已启用提供者，补齐调用、界面、拒绝/取消/退出和服务重启证明',
        'one exact original Photos2in1 obligation')
    return rows[0]


def registration_candidate(*,original_ledger,archive,main_boot,main_suite,actor,output):
    sources();row=original_row(original_ledger)
    env=document(main_boot)['test_environment']
    need(document(main_boot)['archive_sha256']==archive['sha256'],'actual archive/boot association')
    checked(archive);checked(main_suite)
    proposal=dict(schema='photos579-one-original-ID-registration-candidate/v1',original_id=ID,
        original_ledger=original_ledger,original_requirement=row,archive=archive,boot=main_boot,
        raw_replay=None,registrations={},candidate_for_root_ledger_review=False,
        formally_closed=[],runtime_pass=False,first_artifact_behavior_gate_passed=False)
    if env['device_type']=='phone':
        proposal.update(profile_disposition='not_applicable_exact_2in1_whole_ID',
            local_phone_slices_still_required=True)
        return proposal
    need(env['device_type']=='2in1','true2in1 whole ID only')
    raw=replay_photos(archive=archive,main_boot=main_boot,main_suite=main_suite,actor=actor,output=output)
    proposal.update(profile_disposition='applicable_actual_2in1',raw_replay=raw,
        supported_local_complete=raw['supported_local_complete'],
        unresolved_subscopes=raw['unresolved_subscopes'])
    # The read complete selected Photos source has disabled account/token
    # code and only a named cloud client. No approved exact Photos-cloud
    # source disposition exists in release_scope. CloudSync's unrelated
    # exclusion cannot create this ID registration. A complete provider/raw
    # oracle or a separately reviewed precise source disposition requires a
    # new fixed successor, never a caller supplied JSON pass/ID list.
    need(raw['cloud_account_complete'] is False,'unreviewed cloud oracle cannot enter this fixed source')
    return proposal
