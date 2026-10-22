"""Fixed virtual modem fd handover and actual kernel service observations.

Pure DATA helpers shared by the original producer and closed-IO replay. No
process, resource owner, launcher, privileged API or verdict is created here.
"""
from pathlib import Path
import re
import shlex

from capability578_owned_io import require
from settings_idle579_bindings import load_ref
from hap_identity_binding import strict_json
from guest_process_identity import starttime_shell, uids_shell

SONAME = 'libnetsys_native_manager.z.so'
BASE = 'foundation/communication/netmanager_base/services/netmanagernative/'
NATIVE_SOURCES = {
    BASE + 'BUILD.gn': 'ca34a5f72e51f2b7f297ffd1924a8e5b21993f89ea913b42491ab32591250ec9',
    BASE + 'src/netsys_native_service.cpp': 'cba1bf384b844a3ca3bd97d4b4d34a27fab2d35308978567ecde7f4598f020f2',
    BASE + 'src/qemu_modem_tun.cpp': '02ceb1c09861ed5fdee3944e6022439a9d1d0fd0134fb8869c8218dbb3b6e0fd',
    BASE + 'include/qemu_modem_tun.h': '6507372cf9854bfadfc3fb067b33adfa268a7797abacf3b3ba9929ecd4058887',
}


def product_input(inputs, archive_sha, product):
    row = inputs['telephony579']
    value = strict_json(load_ref(row['product_export']).decode())
    require(value['schema'] == 'telephony579-actual-product-input-export/v1' and
        value['archive']['sha256'] == archive_sha and value['product'] == product and
        set(value['native_sources']) == set(NATIVE_SOURCES),
        'complete actual same-package normal modem native source input')
    for logical, expected in NATIVE_SOURCES.items():
        load_ref(value['native_sources'][logical])
        require(value['native_sources'][logical]['sha256'] == expected,
            'actual full native source does not match the reviewed fixed product patch')
    for descriptor in value['native_sources'].values(): load_ref(descriptor)
    profile = strict_json(load_ref(value['installed_runtime_profile']).decode())
    from batch_system_build_runtime_helpers import validate_installed_profile
    validate_installed_profile(profile, archive_sha256=archive_sha)
    require(profile['product'] == product and SONAME in profile['dsos'], 'actual independent native DSO image profile')
    library = strict_json(load_ref(value['library']).decode())
    require(library['image_file'] == profile['dsos'][SONAME]['image_file'] and
        load_ref(library['image_file']) == load_ref(library['linked_output']),
        'normal native link bytes must equal independently dumped new image DSO')
    entry = profile['dsos'][SONAME]
    prefix = profile['source_root'] + '/out/' + product + '/packages/' + (profile['device'] if profile['schema_version'] == 1 else 'phone')
    staged = entry['staged']['path']
    require(staged.startswith(prefix + '/'), 'actual selected product installation prefix')
    guest = '/' + staged[len(prefix) + 1:]
    require(re.fullmatch(r'/(?:system|vendor)/lib(?:64)?/' + re.escape(SONAME), guest),
        'architecture-derived real native service DSO path')
    return value, guest, library['image_file']['sha256']


def handover(rows, *, run, boot, operation, peer_pid):
    require(re.fullmatch('[a-f0-9]{32}', operation) and type(peer_pid) is int and peer_pid > 0,
        'original peer and finite control nonce')
    original = [r for r in rows if r['kind'] == 'backend' and r['operation_id'] == operation]
    payloads = [bytes.fromhex(r['hex']).decode() for r in original]
    request = 'QMT1\t' + run + '\t' + boot + '\t' + operation + '\n'
    require(payloads.count(request) == 1, 'one raw original nonce-bound native TUN request')
    replies = [p for p in payloads if p.startswith(request[:-1] + '\t')]
    identities = [p for p in payloads if p.startswith('TUN-SERVER\t')]
    require(len(replies) == len(identities) == 1, 'one complete actual native fd handover and kernel peer identity')
    match = re.fullmatch(re.escape(request[:-1]) + r'\t([1-9][0-9]*)\t(0|[1-9][0-9]*)\t([1-9][0-9]*)\t' + str(peer_pid) + '\n', replies[0])
    require(match is not None, 'actual native PID/UID/ifindex and original peer credentials')
    pid, uid, index = map(int, match.groups())
    require(identities[0] == 'TUN-SERVER\t' + str(pid) + '\t' + str(uid) + '\tu:r:netsysnative:s0\n',
        'SO_PEERSEC and SO_PEERCRED must authenticate the actual normal product service')
    selected = [r for r in original if bytes.fromhex(r['hex']).decode() in (request, replies[0], identities[0])]
    require([bytes.fromhex(r['hex']).decode() for r in selected] == [request,replies[0],identities[0]],
        'actual kernel handshake order')
    return dict(pid=pid, uid=uid, ifindex=index, operation=operation, request=request,
        response=replies[0], kernel_peer=identities[0], wire_sequences=[r['seq'] for r in selected])


def service_script(pid, guest, digest, boot):
    require(type(pid) is int and pid > 0 and re.fullmatch('[a-f0-9]{64}', digest) and
        re.fullmatch('[a-f0-9-]{36}', boot) and re.fullmatch(r'/(?:system|vendor)/lib(?:64)?/' + re.escape(SONAME), guest),
        'fixed real service image observation inputs')
    p = str(pid)
    return ('test "$(cat /proc/sys/kernel/random/boot_id)" = ' + shlex.quote(boot) + ' || exit 1; '
        'printf "__QMT579_START__\\n"; ' + starttime_shell(p) + ' || exit 1; '
        'printf "__QMT579_UID__\\n"; ' + uids_shell(p) + ' || exit 1; '
        'printf "__QMT579_CONTEXT__\\n"; cat /proc/' + p + '/attr/current || exit 1; '
        'printf "\\n__QMT579_ARGV__\\n"; tr "\\000" "\\n" < /proc/' + p + '/cmdline || exit 1; '
        'printf "__QMT579_LIBRARY__\\n"; sha256sum ' + shlex.quote(guest) + ' || exit 1; '
        'printf "__QMT579_MAPS__\\n"; cat /proc/' + p + '/maps || exit 1; '
        'printf "__QMT579_END__\\n"; ' + starttime_shell(p) + ' || exit 1')


def service_observation(raw, facts, guest, digest):
    names = ('START','UID','CONTEXT','ARGV','LIBRARY','MAPS','END')
    values = {}
    rest = raw
    for index,name in enumerate(names):
        marker = '__QMT579_' + name + '__\n'
        require(rest.startswith(marker) and raw.count(marker) == 1, 'complete actual native process observation frame')
        rest = rest[len(marker):]
        if index + 1 < len(names):
            next_marker = '__QMT579_' + names[index + 1] + '__\n'
            value, found, rest = rest.partition(next_marker)
            require(found, 'missing actual native process observation section')
            values[name] = value
            rest = next_marker + rest
        else: values[name] = rest
    require(re.fullmatch('[1-9][0-9]*\n',values['START']) and values['START'] == values['END'],
        'actual native process generation changed or was reused')
    require(values['UID'] == ' '.join([str(facts['uid'])] * 4) + '\n' and
        values['CONTEXT'].rstrip('\0\r\n') == 'u:r:netsysnative:s0', 'actual native service UID and SELinux context')
    require(values['ARGV'] == '/system/bin/sa_main\n/system/profile/netsysnative.json\n' and
        values['LIBRARY'] == digest + '  ' + guest + '\n', 'actual normal SA profile and independently installed native library bytes')
    mappings = [line.split() for line in values['MAPS'].splitlines()]
    require(any(len(row) == 6 and row[1] == 'r-xp' and row[-1] == guest for row in mappings),
        'actual service must map executable pages from this new image DSO')
    return dict(pid=facts['pid'],uid=facts['uid'],start_ticks=int(values['START']),
        context='u:r:netsysnative:s0',guest_library=guest,library_sha256=digest)
