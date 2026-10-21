"""Fixed global-clock AU DATA production on Root's existing held resources.

This does not install a caller, compile a helper, construct an Owner or waive
any original non-clock caller/helper/signature/source/cleanup admission.
"""
from pathlib import Path
import hashlib,json,re
import onset579_global_clock as clock
import onset579_global_tools as tools
from onset579_global_inventory import replay_inventory_proof
from onset579_global_bridge import admit,profile_from_config


def need(ok,message):
    if not ok:raise ValueError(message)


def fresh_json(path,value):
    path=Path(path);need(not path.exists() and not path.is_symlink(),'fresh fixed global AU DATA')
    with path.open('x') as stream:stream.write(json.dumps(value,indent=2)+'\n')
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def assemble_on_original_owner(owner,guest,*,domain,original_inventory_io,inventory_proof_ref,
        inventory_io_ref,original_six_inputs_ref,tools_proof,installed_dsos_ref,output,bindings):
    """Only replace two explicit descriptors after actual inventory IO is closed.

    Root must separately perform the original caller/signature/passive/token,
    source/lease/constructor admission. This result cannot certify those inputs.
    """
    clock.require_domain(domain);owner.held_binding(guest)
    need(original_inventory_io.owner is owner and original_inventory_io.guest is guest and
         original_inventory_io._closed and original_inventory_io.boot_id==domain.kernel.boot_id and
         original_inventory_io.archive_sha256==domain.kernel.archive_sha256 and
         tools.record(original_inventory_io.output/'io.json')['sha256']==inventory_io_ref['sha256'] and
         str(original_inventory_io.output/'io.json')==inventory_io_ref['path'],
         'same original retained closed IO, not another prelude or boot')
    archive={key:owner.config['archive'][key] for key in ('path','sha256')}
    need(archive['sha256']==domain.kernel.archive_sha256 and
         guest.report['archive_sha256']==archive['sha256'] and
         guest.report['test_environment']['boot_id']==domain.kernel.boot_id,'same original held archive/kernel boot')
    profile=profile_from_config(owner.config)
    inventory=replay_inventory_proof(inventory_proof_ref,domain=domain,original_io_ref=inventory_io_ref)
    value=bindings.load(bindings.checked(original_six_inputs_ref))
    need(type(value) is dict and set(value)=={'actors','helpers','signer_dist','signer_jar','control404','onset579'} and
         set(value['helpers'])=={'passive','token'},'unaltered finite original six inputs/non-clock helpers')
    onset=dict(schema='audio-onset-global579-input/v1',tools=tools_proof,installed_dsos=installed_dsos_ref)
    admit(onset,archive=archive,profile_ref=profile,domain=domain,bindings=bindings)
    out=Path(output);need(out.is_absolute() and out.resolve()==out and out.is_relative_to(owner.output) and
         not out.exists(),'fresh DATA below original Owner output');out.mkdir(mode=0o700)
    kernel_ref=dict(path=domain.kernel.original_kernel_admission_ref[0],sha256=domain.kernel.original_kernel_admission_ref[1])
    control=fresh_json(out/'control-global579.json',dict(schema='actual-arm32-global-CONTROL579/v1',tools=tools_proof,
        profile=profile,inventory=inventory,inventory_proof=inventory_proof_ref,kernel_admission=kernel_ref))
    final=dict(value,control404=control,onset579=onset)
    inputs=fresh_json(out/'inputs-global579.json',final)
    report=fresh_json(out/'assembly-global579.json',dict(schema='actual-arm32-global-AU-DATA579/v1',
        original_inputs=original_six_inputs_ref,inputs=inputs,inventory=inventory_proof_ref,original_io=inventory_io_ref,
        kernel_admission=kernel_ref,archive=archive,boot=domain.kernel.boot_id,
        changed_keys=['control404','onset579'],untouched_keys=['actors','helpers','signer_dist','signer_jar'],
        original_nonclock_admission_still_required=True,source_only_DATA_binding=True,
        runtime_pass=False,accepted=False,formally_closed=[],first_artifact_behavior_gate_passed=False))
    return dict(inputs=inputs,assembly=report,inventory_io=inventory_io_ref)


def production_argv(*,domain,profile_sha256,normal_link_target,original_build_sha256=None):
    """Finite argv for the already-owned native producer, never executed here.

    Caller must mount the reviewed kit/profile at these exact fixed paths in
    the existing original RO producer. Real normal target selection is checked
    again by Builder from actual Ninja bytes and the actual normal ELF/CRT.
    """
    clock.require_domain(domain)
    need(re.fullmatch('[a-f0-9]{64}',profile_sha256) is not None and
         type(normal_link_target) is str and re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_./+\-]*',normal_link_target) and
         not normal_link_target.startswith('/') and not any(v in ('','.','..') for v in normal_link_target.split('/')),
         'actual fixed normal executable target/profile identity')
    argv=['python3','-B','/arm32-onset579-kit/ci/capability-audit/onset579_global_native.py']
    if original_build_sha256 is None:
        argv+=['--mode','build','--normal-link-target',normal_link_target,
            '--runtime-profile-sha256',profile_sha256]
    else:
        need(re.fullmatch('[a-f0-9]{64}',original_build_sha256) is not None,'actual immutable original build SHA')
        argv+=['--mode','recheck','--previous-sha256',original_build_sha256]
    return argv
