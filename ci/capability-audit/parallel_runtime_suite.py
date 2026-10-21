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


def supported_environment(environment):
    """Finite target applicability; representative() retains its first-package meaning.

    The caller still obtains this environment from the original validate_binding
    and actual archive/held boot. This predicate does not certify a VM or result.
    """
    return (type(environment) is dict and environment.get('device_type') in ('phone', '2in1') and
        (environment.get('product'), environment.get('guest_arch')) in (
            ('arm64_virt', 'arm64'), ('armv7a_virt', 'armv7a'), ('x86_64_virt', 'x86_64')))


def applicable_families(environment):
    if not supported_environment(environment):
        raise ValueError('finite actual full-source product/arch/device environment required')
    # Contacts is a phone-only provider contract. An inapplicable family receives
    # no pass/closure; all original phone families and all other profile duties remain.
    return tuple(name for name in FAMILIES if name != 'contacts-picker' or environment['device_type'] == 'phone')


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
    families = applicable_families(environment)
    if path is None: raise ValueError('QEMU_TEST_CAPABILITY_INPUTS must identify the real prebuilt capability inputs')
    value = read(path)
    if (set(value) != {'schema_version', 'product', 'device_type', 'families'} or
            type(value['schema_version']) is not int or value['schema_version'] != 1 or
            value['product'] != environment['product'] or value['device_type'] != environment['device_type'] or
            not isinstance(value['families'], dict) or set(value['families']) != set(families)):
        raise ValueError('complete fixed applicable capability input plan required')
    for name in families:
        _, required, optional = FAMILIES[name]
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
    if name not in applicable_families(environment):
        raise ValueError('capability family is not applicable to this actual product/device: ' + str(name))
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
