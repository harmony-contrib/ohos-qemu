"""Fixed new-package capability runners and independent evidence dispatch.

Prebuilt inputs are data. They cannot select an executable or relax a verifier.
The enclosing suite owns the VM and creates stable, same-directory boot copies.
"""
import importlib
import json
from pathlib import Path
import sys

from enclosing_acceptance_guest import validate_binding
from run_root_probe import digest

FAMILIES = {
    'contacts-picker': ('batch_apps_contact_picker_coordinator',
        ('inputs', 'signer-dist', 'observer-local', 'observer-receipt'), ('signer-jar',)),
    'wallpaper': ('batch_media_wallpaper_suite', ('artifacts',), ()),
    'external-inputs': ('batch_system_live_inputs_suite', ('artifacts',), ()),
    'knowledge-holiday': ('batch_media_knowledge_suite', ('artifacts',), ()),
}
TIMEOUTS = {'contacts-picker': 3600, 'wallpaper': 5400, 'external-inputs': 1800, 'knowledge-holiday': 3600}
REQUIRED = frozenset(FAMILIES)


def representative(environment):
    return (environment.get('product'), environment.get('device_type'), environment.get('guest_arch')) == (
        'arm64_virt', 'phone', 'arm64')


def read(path):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('absolute regular capability evidence/input required: ' + str(path))
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result: raise ValueError('duplicate capability input key: ' + key)
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=pairs)


def load_plan(path, environment):
    if not representative(environment): raise ValueError('representative capability inputs require ARM64 phone')
    if path is None: raise ValueError('QEMU_TEST_CAPABILITY_INPUTS must identify the real prebuilt capability inputs')
    value = read(path)
    if (set(value) != {'schema_version', 'product', 'device_type', 'families'} or
            type(value['schema_version']) is not int or value['schema_version'] != 1 or
            value['product'] != environment['product'] or value['device_type'] != environment['device_type'] or
            not isinstance(value['families'], dict) or set(value['families']) != REQUIRED):
        raise ValueError('complete fixed representative capability input plan required')
    for name, (_, required, optional) in FAMILIES.items():
        row = value['families'][name]
        if (not isinstance(row, dict) or not set(required) <= set(row) or
                set(row) - set(required) - set(optional)):
            raise ValueError('missing or unknown capability runner input: ' + name)
        for key, raw in row.items():
            if not isinstance(raw, str) or not Path(raw).is_absolute() or Path(raw).is_symlink():
                raise ValueError('absolute non-aliased capability path required: ' + name + '/' + key)
            if not (Path(raw).is_dir() if key == 'signer-dist' else Path(raw).is_file()):
                raise ValueError('actual prebuilt capability input missing: ' + name + '/' + key)
    return value


def boot_copy(boot, destination):
    """Retain qemu.log location; subsequent parent wake records cannot alter it."""
    boot, destination = Path(boot), Path(destination)
    if boot.parent.resolve() != destination.parent.resolve() or boot.resolve() == destination.resolve():
        raise ValueError('stable capability boot copy must retain the actual boot/qemu.log directory')
    before = digest(boot)
    with destination.open('xb') as stream: stream.write(boot.read_bytes())
    destination.chmod(0o400)
    if digest(boot) != before or digest(destination) != before:
        raise ValueError('actual boot evidence changed while freezing capability input')
    return destination


def argv(name, plan, boot, archive, hdc, output, suite_evidence):
    module, _, _ = FAMILIES[name]
    command = [sys.executable, str(Path(__file__).with_name(module + '.py')),
        '--boot', str(boot), '--archive', str(archive), '--hdc', str(hdc), '--output', str(output)]
    for key, value in plan['families'][name].items(): command += ['--' + key, value]
    if name == 'contacts-picker': command += ['--full-boundaries']
    if name == 'wallpaper': command += ['--suite-evidence', str(suite_evidence)]
    return command


def verify_family(name, path, archive, environment):
    if not representative(environment): raise ValueError('new capability family is not bound to ARM64 phone')
    path, archive = Path(path), Path(archive)
    payload = read(path)
    archive_sha = digest(archive)
    if (payload.get('status') != 'pass' or payload.get('archive_sha256') != archive_sha or
            payload.get('boot_id') != environment['boot_id'] or
            payload.get('cleanup_complete') is not True or payload.get('cleanup_errors') != []):
        raise ValueError('capability family is incomplete or belongs to another archive/boot: ' + name)
    boot = path.parent.parent / 'boot' / (name + '-boot.json')
    snapshot = read(boot)
    snapshot_env = validate_binding(snapshot, archive_sha)
    if snapshot_env != environment:
        raise ValueError('capability boot copy differs from the enclosing actual VM: ' + name)
    # Every family rechecks signatures, raw observations and source/build inputs.
    # A hash-consistent invented outer status is never a behavior proof.
    module = importlib.import_module(FAMILIES[name][0])
    result = module.verify_evidence(path, archive, boot)
    if name == 'contacts-picker' and (not isinstance(result, dict) or result.get('full_boundaries_verified') is not True):
        raise ValueError('actual Contacts deadline/navigation boundary observations are incomplete')
    if name == 'wallpaper' and (not isinstance(result, dict) or result.get('native_fallback_and_renderer_verified') is not True):
        raise ValueError('actual Wallpaper native/image/source HAP and renderer connections are incomplete')
    if name == 'knowledge-holiday' and (not isinstance(result, dict) or
            result.get('all_phases_verified') is not True or result.get('role_identity_and_signatures_verified') is not True or
            result.get('observer_product_ABI_verified') is not True or result.get('transport_guest_binding_verified') is not True):
        raise ValueError('actual Knowledge API phases, signed roles, product observer and guest transport are incomplete')
    return result


def verified_closures(name, evidence, archive, environment):
    verify_family(name, evidence, archive, environment)
    if name not in FAMILIES: raise ValueError('unknown capability family')
    # GNSS/accelerometer/public still covers a subset of the broad original
    # MSDP finding. It must never close missing clients or other modalities.
    identifiers = {'contacts-picker': ('behavior:contacts-picker-entrypoint-missing-phone',),
                   'wallpaper': ('behavior:wallpaper-ui-provider-missing',), 'external-inputs': (),
                   'knowledge-holiday': ()}[name]
    return {identifier: {'evidence': str(evidence), 'sha256': digest(evidence),
        'verifier': FAMILIES[name][0] + '.verify_evidence',
        'not_claimed': 'unrelated providers, APIs or broad MSDP client completion'} for identifier in identifiers}
