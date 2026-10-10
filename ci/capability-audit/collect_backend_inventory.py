"""Read-only observations on the suite-owned new boot; never gap closure.

Missing nodes/configurations remain raw diagnostic observations, not success or
failure of an API. Real behavior verifiers must independently establish fixes.
"""
import hashlib
import json
from pathlib import Path
import re


QUERIES = (
    ('thermal-zones', '''for zone in /sys/class/thermal/thermal_zone*; do
  [ -d "$zone" ] || continue
  printf 'zone=%s\n' "$zone"
  for field in type temp; do
    printf '%s=' "$field"
    cat "$zone/$field" 2>&1
  done
done'''),
    ('thermal-configurations', '''for config in \
  /vendor/etc/thermal_config/thermal_hdi_config.xml \
  /system/etc/thermal_config/thermal_service_config.xml; do
  printf 'configuration=%s\n' "$config"
  if [ -f "$config" ]; then cat "$config" 2>&1; else printf 'ABSENT\n'; fi
done'''),
    ('network-devices', '''for device in /sys/class/net/*; do
  [ -d "$device" ] || continue
  printf 'device=%s\n' "$device"
  for field in ifindex type operstate; do
    printf '%s=' "$field"
    cat "$device/$field" 2>&1
  done
done'''),
    ('bluetooth-devices', '''if [ -d /sys/class/bluetooth ]; then
  for device in /sys/class/bluetooth/*; do
    [ -e "$device" ] || continue
    printf 'device=%s\n' "$device"
    readlink "$device" 2>&1
  done
else
  printf 'ABSENT\n'
fi'''),
    ('netmanager-bpf-namespace', '''printf 'observer_mount_namespace='
readlink /proc/self/ns/mnt
printf 'observer_bpf_maps\n'
ls -ld /sys/fs/bpf/netsys/maps 2>&1
found=0
for service_pid in $(pidof netsysnative); do
  case "$service_pid" in ''|*[!0-9]*) continue ;; esac
  [ "$(cat /proc/$service_pid/comm 2>/dev/null)" = netsysnative ] || continue
  found=1
  printf 'netsysnative_pid=%s\nservice_mount_namespace=' "$service_pid"
  readlink /proc/$service_pid/ns/mnt
  cat /proc/$service_pid/status /proc/$service_pid/mountinfo 2>&1
  printf 'service_bpf_maps\n'
  ls -l /proc/$service_pid/root/sys/fs/bpf/netsys/maps 2>&1
done
if [ "$found" = 0 ]; then printf 'NO_NETSYSNATIVE_PROCESS\n'; fi'''),
)


def collect(guest, output, archive_sha256, boot_id):
    if (re.fullmatch(r'[0-9a-f]{64}', archive_sha256) is None or
            re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id) is None):
        raise ValueError('actual new archive and kernel boot identity are required')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    document = {'schema_version': 1, 'status': 'diagnostic_NOT_behavior_pass',
        'scope': 'read_only_system_backend_inventory_NOT_API_tests_or_gap_closure',
        'archive_sha256': archive_sha256, 'boot_id': boot_id,
        'first_artifact_behavior_gate_passed': False, 'observations': [],
        'not_claimed': ['API behavior', 'permissions', 'device operation', 'full capability support']}
    path = output / 'inventory.json'

    def save():
        path.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')

    def same_boot(label):
        guest.healthy()
        if guest.shell('cat /proc/sys/kernel/random/boot_id', label).strip() != boot_id:
            raise ValueError('backend inventory is no longer on the exact owned new boot')

    save()
    same_boot('backend-inventory-before')
    for label, script in QUERIES:
        text = guest.shell(script, 'backend-inventory-' + label)
        raw = output / (label + '.txt')
        raw.write_text(text, encoding='utf-8')
        document['observations'].append({'label': label, 'script': script,
            'raw': str(raw.resolve()), 'sha256': hashlib.sha256(raw.read_bytes()).hexdigest()})
        save()
    same_boot('backend-inventory-after')
    document['kernel_boot_id_unchanged'] = True
    save()
    return document
