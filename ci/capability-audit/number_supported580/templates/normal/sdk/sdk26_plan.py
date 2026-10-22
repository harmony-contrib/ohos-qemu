"""Inert argv construction. No SDK/Git/Docker/file-input reads at import."""
from pathlib import Path

import sdk26_common as C

HOST_ROLES = {
    'apps15': ['contacts-caller', 'contacts-seed', 'wallpaper-seed', 'wallpaper-query'],
    'audio-calendar26': ['audio/normal', 'audio/denied', 'calendar/producer', 'calendar/observer', 'calendar/denied'],
    'knowledge26': ['importer', 'denied', 'query', 'curator'],
}
POST_PACKAGE_ROLES = ['peer15/owner', 'peer15/internet']
NUMBER580_ROLES = ['system-granted', 'system-readonly', 'ordinary']


def stages(commit, output, *, phase='prepackage', width=1280, height=800, product='arm64_virt', device='phone', wallpaper_ui_plan=None, wallpaper_ui_plan_sha256=None, number_inputs=None, number_inputs_sha256=None, sdk_declaration_receipt=None, sdk_declaration_receipt_sha256=None):
    C.target_context(product, device)
    C.commit_shape(commit)
    output = Path(output).absolute()
    rows = [
        dict(label='apps15', roles=HOST_ROLES['apps15'], output=str(output / 'apps15'),
            receipt=str(output / 'apps15/evidence.json'), timeout=16000,
            argv=[C.PY, '-B', str(C.HERE / 'prepare_apps_callers375.py'), '--execute', '--commit', commit,
                '--output', str(output / 'apps15'), '--width', str(width), '--height', str(height)]),
        dict(label='audio-calendar26', roles=HOST_ROLES['audio-calendar26'], output=str(output / 'audio-calendar26'),
            receipt=str(output / 'audio-calendar26/evidence.json'), timeout=14000,
            argv=[C.PY, '-B', str(C.HERE / 'run_dedicated_sdk26.py'), '--execute', '--commit', commit,
                '--output', str(output / 'audio-calendar26')]),
        dict(label='knowledge26', roles=HOST_ROLES['knowledge26'], output=str(output / 'knowledge26'),
            receipt=str(output / 'knowledge26/evidence.json'), timeout=16000,
            argv=[C.PY, '-B', str(C.HERE / 'run_knowledge_sdk26.py'), '--execute', '--commit', commit,
                '--output', str(output / 'knowledge26')]),
    ]
    if phase == 'prepackage':
        rows += [
            dict(label='live-sdk39-26', roles=['live-inputs'], output=str(output / 'live-sdk39-26'),
                receipt=str(output / 'live-sdk39-26/evidence.json'), timeout=6500,
                argv=[C.PY, '-B', str(C.HERE / 'run_live_sdk39_26.py'), '--execute', '--commit', commit,
                    '--output', str(output / 'live-sdk39-26')]),
        ]
    if phase == 'prepackage':
        number_argv = [C.PY, '-B', str(C.HERE.parent / 'number/produce580.py'), '--execute',
            '--commit', commit, '--output', str(output / 'number-local580')]
        if device == 'phone':
            C.require(number_inputs is not None and number_inputs_sha256 is not None and
                sdk_declaration_receipt is not None and sdk_declaration_receipt_sha256 is not None,
                'actual same-archive Number SDK and normal declaration inputs required')
            number_argv += ['--inputs',str(number_inputs),'--inputs-sha256',number_inputs_sha256,
                '--sdk-declaration-receipt',str(sdk_declaration_receipt),
                '--sdk-declaration-receipt-sha256',sdk_declaration_receipt_sha256]
        else:
            C.require(number_inputs is None and number_inputs_sha256 is None,
                '2in1 Number is explicit profile N/A; no phone artifact data')
        rows.append(dict(label='number-local580', roles=NUMBER580_ROLES if device == 'phone' else [],
            output=str(output / 'number-local580'),receipt=str(output / 'number-local580/evidence.json'),
            timeout=16000,argv=number_argv,independent_account_role='account' if device == 'phone' else None))
    if device == '2in1':
        C.require(wallpaper_ui_plan is not None and wallpaper_ui_plan_sha256 is not None,
            'actual source-bound 2in1 Wallpaper UI plan input remains required')
        rows[0]['argv'] += ['--wallpaper-ui-plan',str(wallpaper_ui_plan),
            '--wallpaper-ui-plan-sha256',wallpaper_ui_plan_sha256]
    else:
        C.require(wallpaper_ui_plan is None and wallpaper_ui_plan_sha256 is None,
            'phone retains its original fixed selector plan')
    for row in rows:
        row['argv'] += ['--product', product, '--device', device]
        row['target'] = C.target_context(product, device)
    return rows


def plan(commit, output, **options):
    rows = stages(commit, output, **options)
    return dict(schema='F-SDK-root-batch26-plan/v1', status='source_draft_NOT_executed',
        source_commit=commit, worktree=str(C.REPO), main_commit=C.MAIN_COMMIT,
        python_invocation=C.PY, python_argv0_must_not_resolve=True,
        sdk105=str(C.SDK), node=str(C.NODE), java_home=str(C.JAVA),
        serial=True, max_sdk_jobs=1, root_dispatcher_holds_no_outer_flock=True,
        per_stage_root_lock=str(C.LOCK), stages=rows,
        requested_prepackage_role_count=sum(len(row['roles']) for row in rows),
        deferred_postpackage=dict(roles=POST_PACKAGE_ROLES,
            reason='Unchanged peer15 execution_inputs and challenge require the actual NEW F package/profile/helper.',
            config_schema='openvpn-owned-peer15/v1',
            root_wrapper=str(C.HERE / 'run_peer_postpackage26.py'),
            fresh_credentials_required=True, old_E_HAP_credentials_or_ready_config_allowed=False),
        provider_product_SDK_lineage='Contacts/Theme/Calendar/Settings/PrivacyCenter source+image SDK lineage remains root product acceptance, not these caller HAPs.',
        runtime_input_assembly_successor_required=True,
        number_local580=dict(scope='phone_only_unsigned_roles_plus_independent_account',
            applicable=options.get('device','phone') == 'phone',
            profile_not_applicable=options.get('device','phone') == '2in1',
            native_observer='separate original normal Builder/admission; no SDK ELF reuse',
            signing='original normal signer with actual fresh boot UDID; never this batch'),
        signed=False, guest_executed=False, capabilities_closed=0, first_artifact_behavior_gate_passed=False)
