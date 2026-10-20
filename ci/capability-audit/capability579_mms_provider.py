"""Bind MMS to actual system HAPs observed inside the original fresh QEMU.

No separate image parser, Docker verification, compiler or resource owner is
used. The original MMS business stage still checks URI bytes, UI and cleanup.
"""
from pathlib import Path
import json
import secrets
import shlex

from capability578_owned_io import OwnedIO, reference, require
from capability578_callers import prepare_callers
from capability578_https import OwnedHTTPS
from assemble_capability579_inputs import checked_ref, json_ref
from export_capability579_from_guest import bms_body, SYSTEM_HAP_PREFIXES


def actual_provider(owner, archive, exports):
    guest = owner.vm
    owner.held_binding(guest)
    require(Path(archive) == owner.archive == guest.args.archive and
            guest.args.purpose == 'acceptance' and not guest.report.get('candidate_kernel') and
            type(exports) is dict and set(exports) == {
                'package_export', 'services_export', 'mms_facts', 'raw_export'},
            'MMS requires the actual original guest export on this new archive')
    require(reference(archive) == {key: owner.config['archive'][key] for key in ('path', 'sha256')} and
            guest.report['archive_sha256'] == owner.config['archive']['sha256'],
            'MMS archive changed from the held fresh boot')
    fact = json_ref(exports['mms_facts'])
    raw = json_ref(exports['raw_export'])
    boot = guest.report['test_environment']['boot_id']
    common = fact['package']
    require(fact['schema'] == 'actual-owned-capability579-mms-facts/v1' and
            raw['schema'] == 'actual-owned-capability579-guest-export/v1' and
            fact['boot_id'] == raw['boot_id'] == boot and raw['complete'] is True and
            raw['package'] == common and raw['target'] == guest.target and raw['udid'] == guest.udid and
            checked_ref(common['archive']) == reference(archive) and
            checked_ref(common['package_receipt']) == {
                key: owner.config['package_receipt'][key] for key in ('path', 'sha256')} and
            raw['mms_facts'] == exports['mms_facts'],
            'MMS export facts belong to another package, boot or resource context')
    require((guest.directory / 'build-inputs.json').read_bytes() ==
            Path(checked_ref(common['build_inputs'])['path']).read_bytes() and
            json_ref(common['build_inputs'])['source_git_revision'] == common['source_commit'],
            'MMS actual extracted package source identity changed')
    expected_raw = Path(checked_ref(fact['bms_query'])['path']).read_text()
    before, identity, modules = bms_body(expected_raw, 'com.ohos.mms')
    require(identity == fact['identity'] and modules == fact['actual_module_paths'] and len(modules) == 1 and
            before['applicationInfo'] == fact['actual_applicationInfo'] and
            before['applicationInfo'].get('isSystemApp') is True and
            before['applicationInfo'].get('appPrivilegeLevel') == 'normal' and
            before.get('signatureInfo') == fact['actual_signatureInfo'] and
            before['reqPermissions'] == fact['actual_reqPermissions'],
            'actual original system MMS identity or permission inventory differs')
    permissions = fact['actual_reqPermissions']
    require(type(permissions) is list and all(type(item) is str for item in permissions) and
            len(permissions) == len(set(permissions)), 'complete actual MMS permission list required')
    # Bind the export records back to actual original Guest command receipts.
    # A hand-written exported fact JSON cannot supply an executable or a pass.
    for item in raw['commands']:
        observation = item['original_receipt']
        matches = [row for row in guest.report['commands'] if
            row['argv'] == observation['argv'] and row.get('log') == item['log']['path'] and
            row.get('sha256') == item['log']['sha256'] and row.get('exit_code') == 0]
        require(len(matches) == 1 and observation['boot_id'] == boot,
                'MMS export command is not from the actual retained Guest')
        for key in ('body', 'stderr', 'log'):
            checked_ref(item[key])
    module, remote = next(iter(modules.items()))
    require(remote.startswith(SYSTEM_HAP_PREFIXES) and remote.endswith('.hap') and
            set(fact['modules']) == {module}, 'MMS must originate in this image system app partition')
    hap = checked_ref(fact['modules'][module]['hap'])
    files = [row for row in raw['files'] if row['kind'] == 'hap' and row['guest_path'] == remote and
             row['received'] == hap]
    require(len(files) == 1 and files[0]['sha256_before'] == files[0]['sha256_after'] == hap['sha256'] and
            files[0]['stat_before'] == files[0]['stat_after'],
            'actual installed MMS bytes lack the original pre/post guest transfer binding')
    output = owner.output / ('mms-guest-provider579-' + secrets.token_hex(8))
    io = OwnedIO(owner, guest, output, run_id=secrets.token_hex(16), package_inputs={},
                 prepare_callers=prepare_callers, https_factory=OwnedHTTPS)
    try:
        actual = io.shell('bm dump -n com.ohos.mms', 'mms_bms_again')
        current, current_identity, current_modules = bms_body(actual['stdout'], 'com.ohos.mms')
        require(current_identity == identity and current_modules == modules and
                current['applicationInfo'] == before['applicationInfo'] and
                current.get('signatureInfo') == before.get('signatureInfo') and
                current['reqPermissions'] == permissions,
                'MMS BMS identity, system origin or permissions changed during the business case')
        hashed = io.shell('sha256sum ' + shlex.quote(remote), 'mms_system_hap_again')
        require(hashed['stdout'] == hap['sha256'] + '  ' + remote + '\n',
                'actual QEMU MMS HAP changed after its original export')
        proof = dict(scope='actual_same_QEMU_MMS_BMS_system_HAP_identity_ONLY',
            archive=reference(archive), boot_id=boot, original_exports=exports,
            system_hap=hap, guest_path=remote, bms=actual['stdout_ref'], hash=hashed['stdout_ref'],
            business_runtime_pass=False, first_artifact_behavior_gate_passed=False)
        (output / 'provider-facts.json').write_text(json.dumps(proof, indent=2) + '\n')
    finally:
        io.close()
    owner.held_binding(guest)
    return dict(archive_sha256=owner.config['archive']['sha256'], bundle='com.ohos.mms',
                hap_sha256=hap['sha256'], permissions=permissions)
