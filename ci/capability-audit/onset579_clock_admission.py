"""Unexecuted clock-domain replay candidate; no Owner, IO, import hook or pass gate.

Root must first admit the actual package/launcher/kernel/config relationship with
its original kernel/profile verifier. A source config by itself is insufficient.
The dataclass is constructed only by that fixed Root code, never from a caller
JSON selector. Original PID/UID/birth/pidfd/OFD/HW/raw and cleanup replays remain
mandatory around this extra typed clock-domain check.
"""
from dataclasses import dataclass
import hashlib
import re


class ClockDomainPending(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise ValueError(message)


# The original official OH7 reference texts were now independently matched
# byte-for-byte to actual RO35 kernel14c77f. A differing implementation requires
# a new reviewed successor; versions or missing proc paths cannot admit it.
REFERENCE_SOURCE_PINS = {
    'init/Kconfig': '545e3c8fcb6f44dda9f0c91d1dd1705c6b652578646f824745731a0cd2d07e31',
    'arch/arm/Kconfig': '4793a64bb6fd5fcae3bf18cfa2a1bc733cee6773379c7aea3985f9f631201e1c',
    'lib/vdso/Kconfig': 'cbf9681abf0e9e41c7ae414cfc7afab0446236e6a09377ca8ced849190e47135',
    'fs/proc/namespaces.c': 'cc38b0cd358741199f25ecb99487caf46e3794bc8d444dd777791b7c1d49fb45',
    'include/linux/time_namespace.h': 'd99650e247b1d4faa704161063a1d7a94e8f9ab56cd28baff2cb4d1095cde81f',
}
# Actual9 implementation bytes were exported by original RO35 with source/out
# readonly. These pins review the implementation only; each actual package still
# requires original generated-config/kernel/held-boot admission. No DATA override.
ACTUAL_KERNEL_SOURCE_HEAD = '14c77f1541a53e814d89ad6dea5f7f211f9895a6'
ACTUAL_CLOCK_SOURCE_REVIEW = {'arch/arm/vdso/vgettimeofday.c': 'e5bf23424a0c328bea5bc4027f174b8339fb0f5787e7fa8a395d2a571203b513',
 'kernel/time/posix-timers.c': '6918cac7acc14895b03d371b0371b9e25ec5b8239aa11fd0d184acc6d2a97955',
 'kernel/time/timekeeping.c': 'd56f6561a288a4e8d87162e81038f82008f0168adbd3d6714b02e154f5074e08',
 'lib/vdso/gettimeofday.c': '63881cbf52d1f5d9cb3f5a699720202fac6081827b8b446e138a94dcfa430481'}
REQUIRED_ACTUAL_CLOCK_FILES = (
    'kernel/time/posix-timers.c', 'kernel/time/timekeeping.c',
    'lib/vdso/gettimeofday.c', 'arch/arm/vdso/vgettimeofday.c',
)
CLOCK_ROLES = frozenset(('af_producer', 'alsa_holder', 'af_client',
                         'status_sampler', 'control_client', 'renderer_receiver'))


@dataclass(frozen=True)
class AdmittedKernelIdentity:
    archive_sha256: str
    kernel_image_sha256: str
    actual_config_sha256: str
    actual_source_head: str
    product: str
    device: str
    boot_id: str
    original_kernel_admission_ref: tuple
    # Exact path/hash pairs from the actual source export, admitted by Root's
    # fixed source closure. These are not executable paths or a mode selector.
    actual_source_hashes: tuple


@dataclass(frozen=True)
class ClockDomain:
    kernel: AdmittedKernelIdentity
    mode: str


def config_symbols(raw):
    need(type(raw) is bytes and 16384 <= len(raw) <= 4 * 1024 * 1024 and
         raw.startswith(b'#\n# Automatically generated file; DO NOT EDIT.'),
         'complete actual generated kernel config required')
    result = {}
    for line in raw.decode('ascii').splitlines():
        setting = re.fullmatch(r'(CONFIG_[A-Z0-9_]+)=(.*)', line)
        unset = re.fullmatch(r'# (CONFIG_[A-Z0-9_]+) is not set', line)
        if setting or unset:
            key, value = setting.groups() if setting else (unset[1], 'n')
            need(key not in result, 'duplicate actual kernel config symbol')
            result[key] = value
    return result


def admit_clock_domain(*, kernel, config_raw, actual_sources):
    """Additional clock check AFTER original actual package/kernel admission.

    This function does not replace archive unpack/checksum, real QEMU argv,
    architecture/ABI/kernel-profile admission, build-to-kernel correspondence or
    held-guest boot identity. Root must supply their admitted identity, not a
    source-only .config or a JSON 'global_clock=true'.
    """
    need(type(kernel) is AdmittedKernelIdentity, 'fixed original kernel admission required')
    for digest in (kernel.archive_sha256, kernel.kernel_image_sha256, kernel.actual_config_sha256):
        need(type(digest) is str and re.fullmatch('[a-f0-9]{64}', digest), 'actual kernel identity SHA required')
    need(re.fullmatch('[a-f0-9]{40}', kernel.actual_source_head) and
         re.fullmatch('[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', kernel.boot_id),
         'actual kernel source and boot identity required')
    need(type(kernel.original_kernel_admission_ref) is tuple and len(kernel.original_kernel_admission_ref) == 2 and
         type(kernel.original_kernel_admission_ref[0]) is str and kernel.original_kernel_admission_ref[0].startswith('/') and
         re.fullmatch('[a-f0-9]{64}', kernel.original_kernel_admission_ref[1]), 'original kernel admission raw Ref required')
    need(kernel.product in ('arm64_virt', 'armv7a_virt', 'x86_64_virt') and kernel.device in ('phone', '2in1'),
         'fixed real product/profile pair required')
    need(hashlib.sha256(config_raw).hexdigest() == kernel.actual_config_sha256,
         'config bytes differ from the originally admitted packaged kernel')
    config = config_symbols(config_raw)
    need(all(config.get(key) == 'y' for key in ('CONFIG_PROC_FS', 'CONFIG_NAMESPACES', 'CONFIG_PID_NS', 'CONFIG_KCMP')),
         'original proc/process/namespace/OFD kernel prerequisites remain required')
    if config.get('CONFIG_TIME_NS', 'n') == 'y':
        need(config.get('CONFIG_GENERIC_VDSO_TIME_NS') == 'y', 'actual supported TimeNS kernel dependency')
        return ClockDomain(kernel, 'time_namespace')
    need(kernel.product == 'armv7a_virt' and config.get('CONFIG_ARM') == 'y' and
         config.get('CONFIG_ARM64', 'n') == config.get('CONFIG_64BIT', 'n') == 'n' and
         config.get('CONFIG_TIME_NS', 'n') == config.get('CONFIG_GENERIC_VDSO_TIME_NS', 'n') == 'n',
         'global candidate is limited to the actual ARM32 non-TimeNS kernel')
    need(kernel.actual_source_head==ACTUAL_KERNEL_SOURCE_HEAD, 'actual reviewed kernel source HEAD differs')
    need(type(actual_sources) is dict, 'actual kernel source bytes required')
    hashes = dict(kernel.actual_source_hashes)
    need(len(hashes) == len(kernel.actual_source_hashes), 'duplicate actual kernel source identity')
    for name, expected in REFERENCE_SOURCE_PINS.items():
        need(type(actual_sources.get(name)) is bytes and hashlib.sha256(actual_sources[name]).hexdigest() ==
             hashes.get(name) == expected, 'unreviewed/different actual TimeNS source: ' + name)
    if ACTUAL_CLOCK_SOURCE_REVIEW is None:
        raise ClockDomainPending('actual current kernel clock/VDSO source export and fixed source review are pending')
    need(set(ACTUAL_CLOCK_SOURCE_REVIEW) == set(REQUIRED_ACTUAL_CLOCK_FILES), 'complete fixed actual clock source review')
    for name, expected in ACTUAL_CLOCK_SOURCE_REVIEW.items():
        need(re.fullmatch('[a-f0-9]{64}', expected) and type(actual_sources.get(name)) is bytes and
             hashlib.sha256(actual_sources[name]).hexdigest() == hashes.get(name) == expected,
             'actual clock implementation differs: ' + name)
    return ClockDomain(kernel, 'kernel_global_monotonic')


def integer(row, key, minimum=0):
    need(type(row.get(key)) is int and row[key] >= minimum, 'actual bounded integer: ' + key)
    return row[key]


def actual_stat(row):
    need(type(row) is dict and set(row) == {'dev', 'ino', 'mode'}, 'complete actual namespace stat')
    integer(row, 'dev'); integer(row, 'ino', 1); integer(row, 'mode', 1)
    return row


def replay_clock_domain(*, domain, observations, expected_processes, run):
    """Pure data clock replay; never a replacement for original onset replay.

    observations are decoded actual source-pinned native records. The fixed Root
    caller obtains each expected (PID,birth,observer PID,held pidfd) from the same
    original resource/protocol receipts. JSON cannot choose roles or skip a role.
    """
    need(type(domain) is ClockDomain and re.fullmatch('[a-f0-9]{32}', run), 'admitted current kernel clock/run')
    need(type(expected_processes) is dict and set(expected_processes) == CLOCK_ROLES and
         type(observations) is list and len(observations) == len(CLOCK_ROLES), 'all original clock participants required')
    seen = {}; clock_id = pid_namespace = None
    for row in observations:
        need(type(row) is dict and set(row) == {'schema', 'kind', 'run', 'role', 'mode', 'pid', 'expected_birth',
             'observer_pid', 'held_pidfd', 'error', 'before', 'after'}, 'exact actual native clock record')
        role = row['role']
        need(role in CLOCK_ROLES and role not in seen and row['schema'] == 'onset579-clock-domain/v1' and
             row['kind'] == 'clock_domain579' and row['run'] == run and row['mode'] == domain.mode and
             type(row['error']) is int and row['error'] == 0, 'actual native clock identity/mode/error')
        need((integer(row, 'pid', 2), integer(row, 'expected_birth', 1), integer(row, 'observer_pid', 2),
              row['held_pidfd']) == expected_processes[role] and type(row['held_pidfd']) is int,
             'clock PID/birth/observer/original pidfd differs')
        need(row['held_pidfd'] == -1 if row['pid'] == row['observer_pid'] else row['held_pidfd'] >= 0,
             'foreign clock observation requires the already-held original pidfd')
        stamps = []
        for cut in (row['before'], row['after']):
            need(type(cut) is dict and set(cut) == {'birth', 'before_ns', 'after_ns', 'boot', 'pidfd_poll_rc',
                 'pidfd_revents', 'directory', 'pid_namespace', 'time', 'time_for_children'}, 'exact actual two-cut clock proof')
            need(integer(cut, 'birth', 1) == row['expected_birth'] and cut['boot'] == domain.kernel.boot_id and
                 type(cut['pidfd_poll_rc']) is int and cut['pidfd_poll_rc'] == 0 and
                 type(cut['pidfd_revents']) is int and cut['pidfd_revents'] == 0, 'same live incarnation/boot/pidfd required')
            actual_stat(cut['directory']); pidns = actual_stat(cut['pid_namespace'])
            need(cut['directory']['mode'] & 0o170000 == 0o040000, 'actual existing proc namespace directory')
            current = pidns['dev'], pidns['ino']
            if pid_namespace is None: pid_namespace = current
            need(current == pid_namespace, 'original participants no longer share the actual PID namespace')
            for key in ('time', 'time_for_children'):
                probe = cut[key]
                need(type(probe) is dict and set(probe) == {'link_rc', 'link_errno', 'stat_rc', 'stat_errno', 'stat'},
                     'actual lstat/stat observations required')
                if domain.mode == 'kernel_global_monotonic':
                    need(probe == dict(link_rc=-1, link_errno=2, stat_rc=-1, stat_errno=2, stat=None),
                         'non-TimeNS must be exact ENOENT with no synthetic namespace inode')
                else:
                    need(all(type(probe[k]) is int and probe[k] == 0 for k in
                         ('link_rc', 'link_errno', 'stat_rc', 'stat_errno')), 'actual TimeNS queries must succeed')
                    ns = actual_stat(probe['stat'])
                    if key == 'time':
                        current = ns['dev'], ns['ino']
                        if clock_id is None: clock_id = current
                        need(current == clock_id, 'original clocks belong to different actual time namespaces')
            stamps += [integer(cut, 'before_ns', 1), integer(cut, 'after_ns', 1)]
        need(row['before']['directory'] == row['after']['directory'] and
             row['before']['pid_namespace'] == row['after']['pid_namespace'] and
             row['before']['time'] == row['after']['time'] and
             row['before']['time_for_children'] == row['after']['time_for_children'], 'clock proc identity changed')
        need(all(a <= b for a, b in zip(stamps, stamps[1:])) and stamps[-1] - stamps[0] <= 15_000_000_000,
             'original bounded monotonic two-cut order')
        seen[role] = {'pid': row['pid'], 'birth': row['expected_birth'], 'cuts': stamps}
    return dict(schema='onset579-clock-domain-replay/v1', mode=domain.mode, participants=seen,
                archive_sha256=domain.kernel.archive_sha256, kernel_image_sha256=domain.kernel.kernel_image_sha256,
                config_sha256=domain.kernel.actual_config_sha256, boot_id=domain.kernel.boot_id,
                clock_domain_proven=True, onset_proven=False, accepted=False, formally_closed=[],
                first_artifact_behavior_gate_passed=False)
