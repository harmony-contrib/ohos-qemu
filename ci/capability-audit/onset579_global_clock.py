"""Pure actual ARM32 global clock records; never legacy TimeNS normalization.

Admission requires the actual fixed9 implementation review and per-package kernel proof.
No caller-selected mode/skip flag, missing-proc fallback or synthetic inode.
"""
import re
import onset579_clock_admission as fixed_review
from onset579_clock_admission import (AdmittedKernelIdentity, ClockDomain,
    ClockDomainPending, admit_clock_domain)

ROLES=frozenset(('af_producer','alsa_holder','af_client','status_sampler',
                'control_client','renderer_receiver'))

def need(ok,message):
    if not ok:raise ValueError(message)

def integer(row,key,low=0,high=(1<<64)-1):
    value=row.get(key)
    need(type(value) is int and low<=value<=high,'actual clock integer '+key)
    return value

def admit_global(*,kernel,config_raw,actual_sources):
    domain=admit_clock_domain(kernel=kernel,config_raw=config_raw,actual_sources=actual_sources)
    need(type(domain) is ClockDomain and domain.mode=='kernel_global_monotonic' and
         domain.kernel.product=='armv7a_virt','explicit reviewed ARM32 kernel-global variant required')
    return domain

def require_domain(domain):
    if fixed_review.ACTUAL_CLOCK_SOURCE_REVIEW is None:
        raise ClockDomainPending('actual four kernel clock files and immutable source/config review are pending')
    need(type(domain) is ClockDomain and domain.mode=='kernel_global_monotonic' and
         domain.kernel.product=='armv7a_virt','original actual ARM32 kernel/global admission required')
    return domain

def actual_stat(row):
    need(type(row) is dict and set(row)=={'dev','ino','mode'},'actual proc stat identity')
    integer(row,'dev');integer(row,'ino',1);integer(row,'mode',1)
    return row

def observation(row,*,domain,run,role,expected):
    """expected=(pid,birth,observer_pid,original held pidfd), from original raw.

    The caller must replay the native open/pidfd/credential/close protocol first.
    A numeric fd by itself is not an authority. This performs only clock checks.
    """
    require_domain(domain)
    need(re.fullmatch('[a-f0-9]{32}',run) is not None and
         role in ROLES|{'inventory_observer'},'fixed actual clock run/role')
    need(type(row) is dict and set(row)=={'schema','kind','run','role','mode','pid','expected_birth',
         'observer_pid','held_pidfd','error','before','after'},'complete typed native clock observation')
    need(row['schema']=='onset579-clock-domain/v1' and row['kind']=='clock_domain579' and
         row['run']==run and row['role']==role and row['mode']=='kernel_global_monotonic' and
         type(row['error']) is int and row['error']==0,'native clock failure/schema/mode is not admissible')
    identity=(integer(row,'pid',2),integer(row,'expected_birth',1),integer(row,'observer_pid',2),row['held_pidfd'])
    need(type(expected) is tuple and len(expected)==4 and identity==expected and
         type(row['held_pidfd']) is int,'native clock incarnation/original pidfd differs')
    need(row['held_pidfd']==-1 if row['pid']==row['observer_pid'] else row['held_pidfd']>=0,
         'self/foreign original pidfd contract')
    cuts=[]
    for cut in (row['before'],row['after']):
        need(type(cut) is dict and set(cut)=={'birth','before_ns','after_ns','boot','pidfd_poll_rc',
             'pidfd_revents','directory','pid_namespace','time','time_for_children'},'exact two-cut native clock record')
        need(integer(cut,'birth',1)==identity[1] and cut['boot']==domain.kernel.boot_id and
             type(cut['pidfd_poll_rc']) is int and cut['pidfd_poll_rc']==0 and
             type(cut['pidfd_revents']) is int and cut['pidfd_revents']==0,'same live actual boot/birth/pidfd')
        directory=actual_stat(cut['directory']);actual_stat(cut['pid_namespace'])
        need(directory['mode']&0o170000==0o040000,'actual existing proc namespace directory')
        for key in ('time','time_for_children'):
            probe=cut[key]
            need(type(probe) is dict and set(probe)=={'link_rc','link_errno','stat_rc','stat_errno','stat'} and
                 all(type(probe[k]) is int for k in ('link_rc','link_errno','stat_rc','stat_errno')) and
                 probe==dict(link_rc=-1,link_errno=2,stat_rc=-1,stat_errno=2,stat=None),
                 'actual absent TimeNS entries required; no errno/inode substitution')
        cuts.extend((integer(cut,'before_ns',1),integer(cut,'after_ns',1)))
    for key in ('directory','pid_namespace','time','time_for_children'):
        need(row['before'][key]==row['after'][key],'actual clock proc identity changed')
    need(all(a<=b for a,b in zip(cuts,cuts[1:])) and cuts[-1]-cuts[0]<=15_000_000_000,
         'bounded ordered actual CLOCK_MONOTONIC two cuts')
    return dict(pid=identity[0],birth=identity[1],observer_pid=identity[2],held_pidfd=identity[3],
                cuts=cuts,pid_namespace=row['after']['pid_namespace'])

def pair(a,b):
    need(a['pid_namespace']==b['pid_namespace'],'original participants changed actual PID namespace')

def participants(rows,*,domain,run,expected):
    need(type(rows) is dict and set(rows)==ROLES and type(expected) is dict and set(expected)==ROLES,
         'all six original native clock participants are mandatory')
    checked={role:observation(rows[role],domain=domain,run=run,role=role,expected=expected[role]) for role in ROLES}
    first=next(iter(checked.values()))
    for value in checked.values():pair(first,value)
    return dict(schema='actual-arm32-global-clock579-participants/v1',mode=domain.mode,
        boot=domain.kernel.boot_id,archive_sha256=domain.kernel.archive_sha256,
        kernel_sha256=domain.kernel.kernel_image_sha256,config_sha256=domain.kernel.actual_config_sha256,
        participants=checked,clock_domain_proven=True,onset_proven=False,accepted=False,formally_closed=[],
        first_artifact_behavior_gate_passed=False)
