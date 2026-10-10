"""Close only the audited missing-quota backend, with both kernel and app proof."""
import json
from pathlib import Path
import sys

from run_root_probe import digest, validate_elf

ROOT = Path(__file__).resolve().parents[2]
IDENTIFIER = 'behavior:storage-quota-not-mounted'


def verify(runtime, archive_sha, boot_id, device):
    boot_path = runtime / 'boot/boot.json'
    if boot_path.is_symlink() or not boot_path.is_file():
        raise ValueError('Storage closure requires original packaged boot evidence')
    boot = json.loads(boot_path.read_text())
    env = boot.get('test_environment', {})
    if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
            boot.get('scope') != 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate' or
            boot.get('archive_sha256') != archive_sha or env.get('boot_id') != boot_id or
            env.get('device_type') != device or env.get('external_keepalive') is not False or
            any(boot.get(key) for key in ('candidate_kernel', 'kernel_command_line_diagnostic',
                'diagnostic_assistance', 'diagnostic_power_button'))):
        raise ValueError('Storage closure cannot use a diagnostic kernel or another package/boot')
    quota = runtime / 'project-quota/result.json'
    ordinary = runtime / 'storage-stats/evidence.json'
    for path in (quota, ordinary):
        if path.is_symlink() or not path.is_file():
            raise ValueError('both kernel quota and ordinary-app Storage proof are mandatory')
    sys.path.insert(0, str(ROOT / 'scripts'))
    from verify_first_artifact_gate import verified_payload
    for name, path in (('project-quota', quota), ('storage-stats', ordinary)):
        verified_payload(name, path, {'sha256': archive_sha}, env)
    document = json.loads(quota.read_text())
    probe = Path(document.get('probe', ''))
    build = probe.parent / 'build.json'
    if (not probe.is_absolute() or probe.is_symlink() or not probe.is_file() or
            probe.name != 'project-quota-runtime' or build.is_symlink() or not build.is_file() or
            digest(probe) != document.get('probe_sha256')):
        raise ValueError('actual native quota executable and compiler evidence required')
    compiled = json.loads(build.read_text())
    source = Path(__file__).with_name('probes') / 'project_quota_runtime.c'
    if (compiled.get('status') != 'pass' or compiled.get('arch') != env['guest_arch'] or
            compiled.get('scope') != 'SDK_compile_NOT_guest_or_Storage_API' or
            compiled.get('first_artifact_behavior_gate_passed') is not False or
            compiled.get('source_sha256') != digest(source) or
            compiled.get('probe_sha256') != digest(probe)):
        raise ValueError('quota probe must match the actual reviewed no-capability writer source and ABI')
    validate_elf(probe, env['guest_arch'])
    return {IDENTIFIER: {'evidence': str(quota), 'sha256': digest(quota),
        'ordinary_evidence': str(ordinary), 'ordinary_sha256': digest(ordinary),
        'boot_evidence': str(boot_path), 'boot_sha256': digest(boot_path),
        'probe_build': str(build), 'probe_build_sha256': digest(build),
        'verifier': 'same_packaged_boot_secure_three_quota_mounts_real_no_cap_EDQUOT_recovery_and_ordinary_UID_data_cache_accounting',
        'not_claimed': 'all_privileged_Storage_APIs_other_filesystems_or_other_architecture_packages'}}
