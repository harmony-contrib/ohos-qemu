"""Replay same-boot public APIs and real kernel inodes for the DMA-BUF backend gap."""
import json
from pathlib import Path
import re

from build_graphics_memory_app_probe import BUNDLE
from enclosing_acceptance_guest import validate_binding
from graphics_memory_kernel_contract import verify_samples
from power_test_policy import power_timeout
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest
from verify_compiled_ordinary_payload import verify_compiled_payload
from verify_graphics_memory_results import verify

ROOT = Path(__file__).resolve().parent
GAP = 'behavior:hidebug-dmabuf-kernel'


def verify_evidence(document, archive_sha, boot_id, arch):
    if (document.get('status') != 'pass' or document.get('failures') != [] or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('enclosing_guest_preserved') is not True or
            document.get('first_artifact_behavior_gate_passed') is not False or
            document.get('power_restoration') != 'unchanged_enclosing_policy' or
            document.get('power_before') != document.get('power_after') or
            document.get('runner_sha256') != digest(ROOT / 'run_graphics_memory_diagnostic.py') or
            document.get('verifier_sha256') != digest(ROOT / 'verify_graphics_memory_results.py') or
            document.get('kernel_verifier_sha256') != digest(ROOT / 'graphics_memory_kernel_contract.py')):
        raise ValueError('actual unchanged same-guest graphics memory proof required')
    boot = Path(document.get('enclosing_boot', ''))
    if (not boot.is_absolute() or boot.name != 'boot.json' or boot.parent.name != 'boot' or
            boot.is_symlink() or not boot.is_file() or digest(boot) != document.get('enclosing_boot_sha256')):
        raise ValueError('original enclosing boot evidence required')
    env = validate_binding(json.loads(boot.read_text()), archive_sha)
    if (env != document.get('test_environment') or env['boot_id'] != boot_id or env['guest_arch'] != arch or
            env['device_type'] != document.get('device')):
        raise ValueError('graphics proof belongs to another actual guest')
    root = boot.parent.parent / 'graphics-memory'
    run_id = document.get('run_id')
    if re.fullmatch('[a-f0-9]{32}', run_id or '') is None:
        raise ValueError('fresh ordinary graphics memory challenge required')
    verify_compiled_payload(document, root, arch, run_id, BUNDLE, 'graphics_memory', 'graphicsmemory',
                            'graphicsmemory-probe-inputs.json')
    files = {'actual_results': root / 'actual-results.log', 'ordinary_identity': root / 'ordinary-identity.json'}
    for key, path in files.items():
        if path.is_symlink() or not path.is_file() or digest(path) != document.get(key + '_sha256'):
            raise ValueError('actual graphics memory evidence changed: ' + key)
    uid = require_normal_identity(files['ordinary_identity'].read_text(), BUNDLE)
    result = verify(files['actual_results'].read_text(), run_id, uid)
    if document.get('result') != result:
        raise ValueError('reported allocation accounting differs from actual public API results')

    observations = {}
    kernels = []
    for row in document.get('guest_commands', []):
        path = Path(row.get('log', ''))
        if (path.parent != root / 'guest-commands' or path.is_symlink() or not path.is_file() or
                row.get('exit_code') != 0 or digest(path) != row.get('sha256')):
            raise ValueError('guest command was changed or did not succeed')
        text = path.read_text().replace('\r', '')
        suffix = re.search(r'\n__QEMU_CHILD_EXIT_[a-f0-9]{32}__=0\n$', text)
        if suffix is None:
            raise ValueError('successful real guest exit status required')
        label = re.sub(r'^\d+-', '', path.stem)
        if label in observations:
            raise ValueError('duplicate guest observation')
        observations[label] = text[:suffix.start()]
        if re.fullmatch(r'kernel-(?:before-allocations|during-[0-9]+)', label):
            expected = 'kernel-before-allocations' if not kernels else 'kernel-during-' + str(len(kernels) - 1)
            if label != expected:
                raise ValueError('actual kernel observation order changed')
            kernels.append(observations[label])
    actual_kernel = verify_samples(kernels, result['pid'], result['allocation_kib'])
    if (actual_kernel != document.get('kernel_result') or
            actual_kernel['baseline_bytes'] != result['graph_kib'][0] * 1024):
        raise ValueError('reported kernel allocation/release differs from actual inode records')
    status = observations.get('actual-process-identity', '')
    if (re.findall(r'^Pid:\s+(\d+)$', status, re.M) != [str(result['pid'])] or
            re.findall(r'^Tgid:\s+(\d+)$', status, re.M) != [str(result['pid'])] or
            re.findall(r'^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$', status, re.M) != [(str(uid),) * 4]):
        raise ValueError('observed kernel buffers do not belong to the real ordinary app process')
    if any(observations.get(label, '').strip() != boot_id for label in ('boot-before', 'final-boot')):
        raise ValueError('graphics memory test crossed kernel boot identities')
    if (power_timeout(observations.get('power-before', '')) != document['power_before'] or
            power_timeout(observations.get('power-after', '')) != document['power_after']):
        raise ValueError('enclosing power policy was not preserved in the actual guest')
    return dict(closed=[GAP], allocation_kib=result['allocation_kib'], kernel_inodes=actual_kernel['inodes'],
                not_claimed='all_HiDebug_APIs_or_other_architecture_profile_runs')
