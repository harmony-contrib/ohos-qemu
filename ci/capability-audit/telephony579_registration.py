"""Final Root actor's fixed L22 reader, after original Owner final settlement.

Returns no whole-ID registration until the original IMS/5A scope is resolved.
All finite positive results still require independent closed-IO replay. No
resource constructor, import target, callback or policy is supplied by DATA.
"""
from pathlib import Path
from types import SimpleNamespace
import re
import shlex
import sys

from final579_contract import (ROOT, KIT, KIT_SHA, COMMIT, ORIGINAL,
    checked, doc, ref, save, need, own_sources, fixed)

IDENTIFIER = 'behavior:telephony-no-modem-or-sim'
LEDGER_SHA = '54cac89929c14de4b3e384b1ab0316b9cc9d3aef19668ff4591f73fdadfff28c'
CANONICAL = ROOT / 'ci/capability-audit'


def modules():
    vector = doc(own_sources()); approved = {r['path']:r['sha256'] for r in vector['files']}
    need(approved.get(str(Path(__file__).resolve())) == ref(Path(__file__).resolve())['sha256'],
        'Root must admit this exact fixed L22 registration source')
    need(ref(KIT / 'manifest.json')['sha256'] == KIT_SHA,'actual normal current Kit manifest')
    manifest = doc(ref(KIT / 'manifest.json')); members = {r['path']:r for r in manifest['members']}
    metadata = {}
    for name in ('SOURCES377.json','SOURCE_REFRESH579.json'):
        row = members[name]; path = KIT / name
        need(row['kind'] == 'file' and ref(path)['sha256'] == row['sha256'] and path.stat().st_size == row['bytes'],
            'complete actual Kit source metadata differs')
        metadata[name] = doc(ref(path))
    sources,refresh = metadata['SOURCES377.json'],metadata['SOURCE_REFRESH579.json']
    need(len(sources['files']) == refresh['runtime_source_pin_count'] and
        len(sources['literal53']) == refresh['original_helper_identities'] == 53 and
        refresh['original_runtime_paths'] == 320,'original complete runtime/constructor source identities differ')
    for row in sources['files']:
        checked(row)
        need(row['path'] not in approved or approved[row['path']] == row['sha256'],
            'final source vector and actual Kit disagree')
        approved[row['path']] = row['sha256']
    siblings = {}
    for path,sha in approved.items():
        p = Path(path)
        if p.parent in (CANONICAL,ROOT / 'scripts') and p.suffix == '.py':
            need(p.stem not in siblings and ref(p)['sha256'] == sha,'ambiguous/changed original canonical import source')
            siblings[p.stem] = p
    for name,path in siblings.items():
        cached = sys.modules.get(name)
        need(cached is None or getattr(cached,'__file__',None) is not None and
            Path(cached.__file__).resolve() == path,'foreign canonical replay dependency already cached')
    result = {}
    for name in ('capability578_owned_io','guest_ui','telephony579_oracle'):
        path = CANONICAL / (name + '.py')
        need(approved.get(str(path)) == ref(path)['sha256'],'fixed current raw replay source absent')
        result[name] = fixed(name,CANONICAL)
        need(Path(result[name].__file__).resolve() == path and approved[str(path)] == ref(path)['sha256'],
            'fixed raw replay source changed during import')
    return result


def closed_view(path, owner, archive, inputs, run, imported):
    snapshot = ref(path); value = doc(snapshot); env = owner['test_environment']
    need(value['scope'] == 'actual_original_Owner_IO_only_NOT_acceptance' and value['closed'] is True and
        value['archive_sha256'] == archive['sha256'] and value['boot_id'] == env['boot_id'],
        'same-new-package original closed IO required')
    for row in value['commands']:
        for key in ('stdout_ref','stderr_ref','log'): checked(row[key])
        need(checked(row['stdout_ref']).read_text() == row['stdout'] and checked(row['stderr_ref']).read_text() == row['stderr'] and
            checked(row['log']).read_bytes() == (row['stdout'] + row['stderr']).encode() and
            row['boot_id'] == env['boot_id'] and row['timed_out'] is False,'original IO raw stdout/stderr/boot differs')
        if 'shell_exit_code' in row:
            need(row['argv'][1:4] == ['-t',env['target'],'shell'] and len(row['argv']) == 5,'original HDC shell target differs')
            match = re.fullmatch(r'(.*); cap578_rc=\$\?; printf "\\n(__CAP578_EXIT_[a-f0-9]{32}__=)%s\\n" "\$cap578_rc"',row['argv'][4],re.S)
            need(match is not None,'original actual CAP footer missing')
            words = shlex.split(match[1])
            need(len(words) == 3 and words[:2] == ['sh','-c'] and shlex.join(words) == match[1],
                'original fixed single shell program required')
            raw,code = imported['guest_ui'].command_exit(row['stdout'],match[2])
            need(raw == row['shell_stdout'] == checked(row['shell_stdout_ref']).read_text() and code == row['shell_exit_code'],
                'original guest/body/footer status differs')
    need(all(r['reaped'] is True and type(r['exit_code']) is int for r in value['held_transports'].values()),
        'original owned transport not actually reaped')
    hdc = {r['argv'][0] for r in value['commands'] if len(r['argv']) >= 4 and r['argv'][1:4] == ['-t',env['target'],'shell']}
    need(len(hdc) == 1,'one actual private HDC target required')
    view = SimpleNamespace(receipts=value['commands'],qmp_receipts=value['qmp'],
        ref_receipt=imported['capability578_owned_io'].OwnedIO.ref_receipt,
        run_id=run,boot_id=env['boot_id'],archive_sha256=archive['sha256'],hdc=next(iter(hdc)),
        target=env['target'],udid=env['udid'],output=path.parent,held_transports=value['held_transports'],
        telephony579_product=inputs['telephony579'], environment={'communications578_services':inputs['communications_services']})
    return view,snapshot


def collect(packet, output, actor):
    need(actor.STATE is not None,'original admitted final Root actor only')
    original = doc(ref(ORIGINAL))
    need(ref(ORIGINAL)['sha256'] == LEDGER_SHA and len(original['requirements']) == 82,'full unchanged original82 ledger required')
    requirements = {r['id']:r for r in original['requirements']}
    need(IDENTIFIER in requirements,'exact unchanged original L22 ID absent')
    imported = modules(); owner = doc(packet['main_boot']); env = owner['test_environment']
    need(owner['archive_sha256'] == packet['archive']['sha256'] and owner['purpose'] == 'acceptance' and
        owner['scope'] == 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate' and env['external_keepalive'] is False and
        not any(owner.get(k) for k in ('candidate_kernel','kernel_command_line_diagnostic','diagnostic_assistance',
            'diagnostic_power_button')),'actual normal new-package QEMU main boot required')
    seal = fixed('final579_seal',Path(sys.modules['final579_contract'].__file__).resolve().parent)
    settled = seal.settlement(packet['main_settlement']['held'],packet['main_settlement']['constructors'])
    root = Path(settled['root'])
    need(checked(packet['main_suite']).is_relative_to(root) and checked(packet['main_boot']).is_relative_to(root),
        'actual main artifacts must belong to settled original Owner')
    suite = doc(packet['main_suite']); stage_ref = suite['capability578']; stage = doc(stage_ref); stage_path = checked(stage_ref)
    need(stage_path.name == 'evidence.json' and stage_path.parent.name == 'capability578' and stage_path.is_relative_to(root) and
        stage['schema'] == 'actual-owned-qemu-capability578/v1' and stage['archive_sha256'] == packet['archive']['sha256'] and
        stage['boot_id'] == env['boot_id'] and stage['cleanup_complete'] is True and stage['closed_ids'] == [],
        'actual original whole capability stage/cleanup required')
    inputs = doc(stage['inputs'])
    need(inputs['schema'] == 'actual-qemu-capability578-inputs/v1' and inputs['source_commit'] == COMMIT and
        {k:inputs['archive'][k] for k in ('path','sha256')} == {k:packet['archive'][k] for k in ('path','sha256')},
        'normal actual source context and archive differ')
    raw = None; failure = None; full = None
    try:
        entries = [r for r in stage['cases'] if r['group'] == 'apps' and r['case'] == 'apn']
        need(len(entries) == 1,'one original fixed APN stage attempt required')
        entry = entries[0]; io_root = stage_path.parent / 'apps-apn'
        need(checked(entry['result']) == io_root / 'stage-result.json','actual original APN result path differs')
        apn = doc(entry['result']); modem_ref = ref(io_root / 'apn579-owned/evidence.json'); modem = doc(modem_ref)
        need(checked(modem['apps']) == io_root / 'runtime/evidence.json' and doc(modem['apps']) == apn,
            'original APN UI result and owned modem do not name the same complete actual result')
        view,io_ref = closed_view(io_root / 'io.json',owner,packet['archive'],inputs,modem['run'],imported)
        cleanup = doc(entry['cleanup'])
        need(checked(entry['cleanup']).parent == io_root and cleanup['boot_id'] == env['boot_id'] and
            cleanup['cleanup_complete'] is True and cleanup['errors'] == [],'original IO.close failed')
        evidence = ref(io_root / 'telephony579-whole/evidence.json')
        raw = imported['telephony579_oracle'].verify(view,evidence,modem_ref)
        need(raw['formally_closed'] == [] and raw['whole_id_closure'] is False and raw['runtime_pass'] is False,
            'finite transactions cannot be a whole-ID or global gate')
        full = fixed('telephony579_full_replay',CANONICAL).collect(packet,inputs,output)
        proof = save(output / 'telephony579-transactions.json',dict(schema='actual-L22-normal-transaction-raw-candidate/v1',
            original_requirement=requirements[IDENTIFIER],archive=packet['archive'],boot=packet['main_boot'],
            stage=stage_ref,original_apn_result=entry['result'],closed_io=io_ref,close_receipt=entry['cleanup'],
            evidence=evidence,actual_raw_replay=raw,remaining_obligations=raw['remaining_obligations'],
            full_supported_obligations=full,finite_obligations_resolved_by_full_fixed_join=True,
            formally_closed=[],runtime_pass=False,first_artifact_behavior_gate_passed=False,
            original_owner_finish_still_required=True))
    except Exception as error:
        failure = {'id':IDENTIFIER,'type':type(error).__name__,'error':str(error)}
        proof = save(output / 'telephony579-unresolved.json',dict(original_requirement=requirements[IDENTIFIER],
            actual_stage=stage_ref,unresolved_failure=failure,formally_closed=[],runtime_pass=False,
            original_owner_finish_still_required=True))
    complete = failure is None and raw is not None and full is not None
    registrations = {IDENTIFIER:dict(source='full original finite modem/SIM/CS/SMS/PDP plus complete RTT10/explicit5A raw replay',
        archive_sha256=packet['archive']['sha256'],boot_id=env['boot_id'],proof=proof,
        full_supported_obligations=full,supported_scope_complete=True,carrier_IMS_positive_claimed=False,
        source_qualified_partial_provider_scope='QemuCarrierIMSTransport579')} if complete else {}
    return dict(registrations=registrations,failures=[] if complete else [failure or dict(id=IDENTIFIER,error='full supported replay incomplete')],
        proof=proof,unresolved={} if complete else {IDENTIFIER:dict(proof=proof)},
        required_obligations_complete=complete,finite_transactions_replayed=raw is not None,
        actual_full_RTT10_and_explicit5A=full,original_owner_finish_still_required=True)
