"""Compare observed kernel zones with real thermal-service data; no simulation."""
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET

COMMANDS = {
    'hdi': 'cat /vendor/etc/thermal_config/thermal_hdi_config.xml',
    'policy': 'cat /system/etc/thermal_config/thermal_service_config.xml',
    'kernel': ('for thermal_node in /sys/class/thermal/thermal_zone*; do '
        'test -f "$thermal_node/type" || continue; '
        'printf "%s|%s|%s\\n" "${thermal_node##*/}" '
        '"$(cat "$thermal_node/type")" "$(cat "$thermal_node/temp")"; done'),
    'service': 'hidumper -s 3303 -a "-t"',
}


def capture(shell, output, phase):
    """Persist root-side readback separately from ordinary-app observations."""
    if phase not in ('before', 'after'):
        raise ValueError('unknown thermal capture phase')
    observed = {}
    for name, command in COMMANDS.items():
        path = output / ('thermal-' + phase + '-' + name + '.log')
        if path.exists():
            raise ValueError('fresh backend capture required')
        value = shell(command, 'actual-thermal-' + phase + '-' + name)
        path.write_text(value)
        observed[name] = {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    verify(*(Path(observed[name]['path']).read_text() for name in COMMANDS))
    return observed


def verify_capture(document, archive_sha, boot_id, run_id):
    if (set(document) != {'archive_sha256', 'boot_id', 'run_id', 'before', 'after', 'verifier_sha256'} or
            document['archive_sha256'] != archive_sha or document['boot_id'] != boot_id or
            document['run_id'] != run_id or document['verifier_sha256'] !=
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest()):
        raise ValueError('thermal backend capture belongs to another package/boot/caller or verifier')
    results = {}
    for phase in ('before', 'after'):
        observed = document[phase]
        if set(observed) != set(COMMANDS):
            raise ValueError('all actual thermal backend readbacks required')
        values = []
        for name in COMMANDS:
            record = observed[name]
            path = Path(record['path'])
            if (set(record) != {'path', 'sha256'} or not path.is_absolute() or path.is_symlink() or
                    not path.is_file() or path.name != 'thermal-' + phase + '-' + name + '.log' or
                    hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']):
                raise ValueError('actual thermal backend readback changed')
            values.append(path.read_text())
        results[phase] = verify(*values)
    return results


def verify(hdi_xml, service_xml, kernel, service):
    hdi = ET.fromstring(hdi_xml)
    policy = ET.fromstring(service_xml)
    for config in (hdi, policy):
        if (config.tag != 'thermal' or config.get('product') != 'qemu' or
                [item.get('value') for item in config.findall('./base/item[@tag="sim_tz"]')] != ['0']):
            raise ValueError('actual QEMU configuration must disable simulated thermal zones')
    zones = hdi.findall('./polling/group/thermal_zone')
    if len(zones) != 1 or zones[0].attrib != {'type': 'battery', 'replace': 'battery'}:
        raise ValueError('unexpected real kernel-to-HDI mapping')
    if [item.get('value') for item in policy.findall('./base/item[@tag="temperature_query_enum"]')] != ['battery']:
        raise ValueError('service must query the actual mapped battery zone')
    clusters = policy.findall('./level/sensor_cluster')
    if len(clusters) != 1 or clusters[0].attrib != {'name': 'qemu_battery', 'sensor': 'battery'}:
        raise ValueError('service policy uses an unavailable sensor')
    if [item.attrib for item in clusters[0].findall('item')] != [
            {'level': str(level), 'threshold': str(on), 'threshold_clr': str(off)}
            for level, on, off in ((1, 40000, 38000), (2, 43000, 41000), (3, 46000, 44000),
                                   (4, 48000, 46000), (5, 53000, 51000), (6, 58000, 56000),
                                   (7, 63000, 61000))]:
        raise ValueError('unexpected packaged thermal thresholds')
    observed = {}
    names = set()
    for line in kernel.splitlines():
        match = re.fullmatch(r'(thermal_zone[0-9]+)\|([^|\s]+)\|(-?[0-9]+)', line)
        if not match or match[1] in names or match[2] in observed:
            raise ValueError('malformed or ambiguous kernel thermal snapshot')
        names.add(match[1])
        observed[match[2]] = int(match[3])
    temperature = observed.get('battery')
    if temperature is None or not 0 < temperature < 38000:
        raise ValueError('require actual nonzero cool kernel reading, not absent/zero or an assumed hot state')
    pairs = re.findall(r'^Type: ([^\s]+)\s*\nTemperature: (-?[0-9]+)\s*$', service, re.M)
    if (pairs != [('battery', str(temperature))] or
            len(re.findall(r'^Type:', service, re.M)) != 1 or
            len(re.findall(r'^Temperature:', service, re.M)) != 1):
        raise ValueError('service did not publish exactly the real nonzero kernel reading')
    return {'closed': [], 'scope': 'real_kernel_to_thermal_service_readback_NOT_hot_transitions',
            'kernel_type': 'battery', 'service_type': 'battery',
            'kernel_raw_temperature': temperature, 'service_raw_temperature': temperature,
            'simulated_zones': False, 'hot_transitions_proven': False}
