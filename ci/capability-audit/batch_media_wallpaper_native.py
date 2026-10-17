"""Bind packaged Wallpaper native provenance to two read-only live mappings.

The root build witness validates GN, fresh protected compilation and image DSO.
This module never starts/connects a renderer or treats a service token as a PID.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import tarfile

from batch_media_wallpaper_runtime import record
from batch_media_verify_wallpaper_runtime import checked
from boot_package import members_checked
from enclosing_acceptance_guest import validate_binding

LIBRARY = 'libwallpaper_service.z.so'
PRODUCTS = {'arm64': 'arm64_virt', 'armv7a': 'armv7a_virt', 'x86_64': 'x86_64_virt'}
PAYLOADS = {'inventory.json', 'graph.ninja', 'compile-commands.json', 'theme-service-args.txt',
            'theme-service-args.stderr.txt', 'theme-service-query.json', 'build-theme-service-args.txt',
            'build-theme-service-args.stderr.txt', 'build-theme-service-query.json',
            LIBRARY, 'witness.json', 'build-log.txt'}
SCOPE = 'current_archive_native_GN_image_and_read_only_live_mapping_NOT_service_token_PID'


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): value.update(block)
    return value.hexdigest()


def native_guard():
    # Root owns this public checker. No private compiler/recipe reimplementation.
    import qemu_wallpaper_build_witness
    return qemu_wallpaper_build_witness


def regular(path):
    path = Path(path)
    if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('actual non-symlink native evidence required')
    return path


def archive_native(archive, boot_path, output):
    """One stream of the current archive; re-dump its same-boot system.img DSO.

    Only bounded native evidence is copied. The multi-GB image is hashed while
    streaming and must match the original boot-extracted image used by QEMU.
    """
    archive = regular(archive); boot_path = regular(boot_path); output = Path(output)
    boot = json.loads(boot_path.read_text()); archive_sha = digest(archive)
    env = validate_binding(boot, archive_sha); product = PRODUCTS[env['guest_arch']]
    source = regular(Path(env['freshly_extracted_directory']) / 'images/system.img')
    if not any(token == str(source) or 'file='+str(source) in token.split(',')
               for token in shlex.split(env['qemu_command'])):
        raise ValueError('native image is not the actual QEMU boot image')
    output.mkdir(parents=True, exist_ok=False); native = output / 'wallpaper-native'; native.mkdir()
    selected = {'wallpaper-native/' + name for name in PAYLOADS} | {
        'wallpaper-native-image-evidence.json', 'contacts-theme-provider-evidence.json', 'SHA256SUMS'}
    if not archive.name.endswith('.tar.gz'): raise ValueError('actual packaged tar.gz required')
    root = archive.name.removesuffix('.tar.gz'); seen = []; hashes = {}; total = 0
    with tarfile.open(archive, 'r|gz') as stream:
        for item in stream:
            if len(seen) >= 50000: raise ValueError('excessive package entry count')
            seen.append(item)
            parsed = PurePosixPath(item.name)
            if (parsed.is_absolute() or '..' in parsed.parts or '\\' in item.name or
                    not parsed.parts or parsed.parts[0] != root or not (item.isfile() or item.isdir())):
                raise ValueError('unsafe native/package archive entry')
            relative = '/'.join(parsed.parts[1:])
            if relative.startswith('wallpaper-native/') and relative not in selected and item.isfile():
                raise ValueError('unexpected native evidence payload')
            if relative not in selected | {'images/system.img'}: continue
            if not item.isfile(): raise ValueError('native/image/checksum evidence must be regular')
            if item.size > (8 * 1024**3 if relative == 'images/system.img' else 128 * 1024**2):
                raise ValueError('bounded native/image payload budget exceeded')
            data = stream.extractfile(item); value = hashlib.sha256(); destination = None
            if relative in selected:
                total += item.size
                if total > 512 * 1024**2: raise ValueError('native evidence total exceeds budget')
                destination = (output / relative).open('xb')
            try:
                count = 0
                for block in iter(lambda: data.read(1024 * 1024), b''):
                    count += len(block); value.update(block)
                    if destination: destination.write(block)
                if count != item.size: raise ValueError('truncated native/image evidence')
                if relative in hashes: raise ValueError('duplicate native/image evidence')
                hashes[relative] = value.hexdigest()
            finally:
                data.close()
                if destination: destination.close()
    members_checked(seen, root)
    if set(hashes) != selected | {'images/system.img'}:
        raise ValueError('current package lacks complete native provenance')
    checksums = {}
    for line in (output / 'SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'([a-f0-9]{64}) [ *](?:\./)?(.+)', line)
        if not match: raise ValueError('malformed current archive checksum list')
        name = match[2]; parsed = PurePosixPath(name)
        if parsed.is_absolute() or '..' in parsed.parts or '\\' in name or name in checksums:
            raise ValueError('unsafe/duplicated current archive checksum')
        checksums[name] = match[1]
    initial = boot['initial_package_file_sha256']
    for name, checksum in hashes.items():
        if name == 'SHA256SUMS': continue  # It cannot checksum itself.
        if checksums.get(name) != checksum or initial.get(name) != checksum:
            raise ValueError('archive native witness differs from boot/checksum inventory: ' + name)
    if digest(source) != hashes['images/system.img']:
        raise ValueError('actual extracted QEMU system.img differs from current archive')
    guard = native_guard(); inventory = json.loads((native / 'inventory.json').read_text())
    guard.check_inventory(inventory, product, native)
    image = guard.image(source, native, product)
    if image != json.loads((output / 'wallpaper-native-image-evidence.json').read_text()):
        raise ValueError('packaged native image evidence differs from actual independent re-dump')
    if (image.get('status') != 'pass' or image.get('product') != product or
            image.get('system_image_sha256') != hashes['images/system.img'] or
            image.get('inventory_sha256') != hashes['wallpaper-native/inventory.json'] or
            image.get('library_sha256') != hashes['wallpaper-native/' + LIBRARY] or
            image.get('first_artifact_behavior_gate_passed') is not False):
        raise ValueError('public native image checker returned incomplete binding')
    return {'scope': SCOPE, 'archive_sha256': archive_sha, 'boot_id': env['boot_id'],
        'product': product, 'files_sha256': hashes, 'image': image, 'guard': record(guard.__file__),
        'system_image': {'path': str(source), 'sha256': hashes['images/system.img']},
        'library_guest_path': '/system/' + ('lib' if product == 'armv7a_virt' else 'lib64') + '/' + LIBRARY,
        # The suite independently recomputes this object during replay; bind
        # the newly shared process decoder as well as this native verifier.
        'process_capture_tools': {name: record(regular(Path(__file__).with_name(name))) for name in
            ('batch_network_openvpn_runtime_collect.py', 'batch_network_openvpn_runtime_project.py')},
        'service_token_to_pid_directly_observed': False, 'connection_caller_identity_observed': False,
        'first_artifact_behavior_gate_passed': False, 'ledger_closed': False}


def maps_script(request, native):
    """Same framed read-only process protocol as the VPN/UID observers."""
    from batch_network_openvpn_runtime_collect import snapshot_script
    return snapshot_script(request['nonce'], native['boot_id'], mode='maps', library=native['library_guest_path'])


def parse_maps(raw, request, native):
    from batch_network_openvpn_runtime_collect import parse_snapshot
    # GuestUi.shell and its independent command_output replay remove all final
    # LF bytes. Keep that exact raw artifact; restore one protocol terminator
    # only at this decoder boundary. Never strip an unexpected suffix here.
    if not isinstance(raw,str) or not raw or raw[-1] not in '0123456789':
        raise ValueError('exact GuestUi process capture without trailing LF/whitespace required')
    capture = parse_snapshot(raw + '\n', request['nonce'], native['boot_id'], mode='maps', library=native['library_guest_path'])
    if len(capture['processes']) != 1:
        from batch_network_openvpn_runtime_collect import SnapshotRace
        if any(items.get('maps_match',(None,None))[0] == 0 for pid,items in capture['queries'].items()
               if capture['classifications'][pid] in ('gone','zombie')):
            raise SnapshotRace('selected mapped process exited; fresh whole capture required')
        raise ValueError('one actual process mapping native service required')
    row = next(iter(capture['processes'].values())); pid = row['pid']; metadata = capture['metadata']
    status = dict(line.partition(':')[::2] for line in row['status'].splitlines() if ':' in line)
    stat = bytes.fromhex(row['raw_hex']).decode().rstrip('\n')
    mappings = [line for line in row['maps'].splitlines() if LIBRARY in line]
    # Reuse the established inode/device/hash/generation checks after the
    # framed decoder has validated every query and complete PID enumeration.
    legacy = '\n'.join(['WALLPAPER_NATIVE_MAPS_V1 '+request['nonce'],native['boot_id'],
        metadata['file-before-stat'],metadata['file-before-hash'],'PROCESS '+str(pid),
        'Name:'+status.get('Name',''),'Pid:'+status.get('Pid',''),'Uid:'+status.get('Uid',''),
        stat,' '.join(row['argv']),*mappings,'PROCESS_STAT_AFTER',stat,'END_PROCESS',
        metadata['file-after-stat'],metadata['file-after-hash'],'END_WALLPAPER_NATIVE_MAPS_V1 '+request['nonce']])
    value = _parse_maps_fields(legacy,request,native)
    value['argv'] = row['argv']; value['kernel_contract'] = capture['kernel_contract']
    return value


def _parse_maps_fields(raw, request, native):
    lines = raw.splitlines(); nonce = request['nonce']; library = native['library_guest_path']
    expected_hash = native['image']['library_sha256'] + '  ' + library
    if (len(raw) > 512 * 1024 or len(lines) < 13 or
            lines[0] != 'WALLPAPER_NATIVE_MAPS_V1 ' + nonce or lines[1] != native['boot_id'] or
            lines[-1] != 'END_WALLPAPER_NATIVE_MAPS_V1 ' + nonce or
            lines[2] != lines[-3] or lines[3] != expected_hash or lines[-2] != expected_hash):
        raise ValueError('fresh same-boot complete native maps/file hash evidence required')
    identity = re.fullmatch(r'([0-9]+) ([1-9][0-9]*) ([1-9][0-9]*)', lines[2])
    if not identity: raise ValueError('actual file device/inode/size missing')
    device, inode, size = map(int, identity.groups())
    major = ((device >> 8) & 0xfff) | ((device >> 32) & 0xfffff000)
    minor = (device & 0xff) | ((device >> 12) & 0xffffff00)
    process = lines[4:-3]
    if (len(process) < 10 or not re.fullmatch(r'PROCESS [1-9][0-9]*', process[0]) or
            process[-1] != 'END_PROCESS' or sum(v.startswith('PROCESS ') for v in process) != 1):
        raise ValueError('one actual process mapping native service required')
    pid = int(process[0].split()[1]); name, actual_pid, uid = process[1:4]
    if not re.fullmatch(r'Name:\s+\S.{0,127}', name) or actual_pid.split() != ['Pid:', str(pid)]:
        raise ValueError('actual mapped process status identity differs')
    match = re.fullmatch(r'Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)', uid)
    if not match or len(set(match.groups())) != 1 or not 0 <= int(match[1]) < 10000:
        raise ValueError('native system service process UID required')
    # Linux stat field22 identifies this process generation. comm may contain spaces.
    stat = re.fullmatch(r'([0-9]+) \((.*)\) (.+)', process[4])
    tail = stat[3].split() if stat else []
    if not stat or int(stat[1]) != pid or len(tail) < 20 or not tail[19].isdigit() or int(tail[19]) <= 0:
        raise ValueError('mapped process generation missing')
    after = re.fullmatch(r'([0-9]+) \((.*)\) (.+)',process[-2])
    after_tail = after[3].split() if after else []
    if (process[-3] != 'PROCESS_STAT_AFTER' or not after or int(after[1]) != pid or
            len(after_tail) < 20 or after_tail[19] != tail[19]):
        raise ValueError('mapped native process generation changed during read')
    if not process[5].strip() or len(process[5]) > 4096:
        raise ValueError('actual mapped process command missing')
    mappings = []; executable = False
    for line in process[6:-3]:
        match = re.fullmatch(r'([a-f0-9]+)-([a-f0-9]+)\s+([r-][w-][x-][ps])\s+([a-f0-9]+)\s+'
                            r'([a-f0-9]+):([a-f0-9]+)\s+([0-9]+)\s+(/.+)', line)
        if not match: raise ValueError('malformed/truncated actual native mapping')
        start, end, perms, offset, dev_major, dev_minor, observed_inode, path = match.groups()
        if (int(start,16) >= int(end,16) or int(offset,16) >= size or
                (int(dev_major,16), int(dev_minor,16), int(observed_inode), path) != (major, minor, inode, library)):
            raise ValueError('native mapping backing inode/device/path differs, replaced or deleted')
        executable |= 'x' in perms; mappings.append(line)
    if not executable or len(mappings) != len(set(mappings)):
        raise ValueError('native library is not uniquely actually executable/mapped')
    return {'pid': pid, 'uid': int(re.findall(r'\d+', uid)[0]),
        'process_start_ticks': int(tail[19]), 'process_name': name.split(':',1)[1].strip(),
        'cmdline': process[5], 'device': device, 'inode': inode, 'bytes': size,
        'library_guest_path': library, 'library_sha256': native['image']['library_sha256'], 'mappings': mappings,
        'service_token_to_pid_directly_observed': False, 'connection_caller_identity_observed': False}


def observe_maps(coordinator, request):
    native = json.loads(checked(coordinator.inputs['native']).read_text())
    if native['boot_id'] != coordinator.boot_id: raise ValueError('native proof belongs to another boot')
    import time
    from batch_network_openvpn_runtime_collect import SnapshotRace
    began = time.monotonic_ns(); base = request['details']['case'] + '-native-maps'
    for attempt in range(3):
        label = base + '-scan-' + str(attempt)
        raw = coordinator.shell(maps_script(request,native),label)
        try: parsed = parse_maps(raw,request,native); break
        except SnapshotRace:
            if attempt == 2: raise
            time.sleep(.05)
    artifact = coordinator.text(raw,label)
    coordinator.value.setdefault('native_mappings', []).append({'case': request['details']['case'],
        'nonce': request['nonce'], 'sequence': request['sequence'], 'began_ns': began,
        'finished_ns': time.monotonic_ns(), 'capture_label':label,'raw': artifact, 'parsed': parsed})
    coordinator.save()


def renderer_path(raw):
    """BMS owns selection. Only this bundle's system or installed HAP is read."""
    from batch_apps_contact_picker_runtime import objects
    start = raw.find('{')
    if start < 0: raise ValueError('actual Wallpaper BMS JSON required')
    value = json.JSONDecoder().raw_decode(raw[start:])[0]
    apps = [obj for obj in objects(value) if obj.get('bundleName',obj.get('name')) == 'com.ohos.wallpaper' and 'isSystemApp' in obj]
    if (len(apps) != 1 or apps[0].get('isSystemApp') is not True or
            type(apps[0].get('uid')) is not int or apps[0]['uid']//200000 != 100):
        raise ValueError('actual same-user Wallpaper system BMS app required')
    paths = set()
    for obj in objects(value):
        for key, path in obj.items():
            if key not in ('hapPath','hapSourceDir','moduleSourceDir') or not isinstance(path,str) or not path.endswith('.hap'): continue
            parsed = PurePosixPath(path)
            if (not path.startswith(('/system/app/com.ohos.wallpaper/','/data/app/el1/bundle/public/com.ohos.wallpaper/')) or
                    '..' in parsed.parts or parsed.as_posix() != path or '\\' in path or '\x00' in path or '\n' in path or '\r' in path):
                raise ValueError('unexpected or unsafe Wallpaper BMS HAP path')
            paths.add(path)
    if len(paths) != 1: raise ValueError('one actual BMS-selected Wallpaper HAP required')
    return paths.pop(), apps[0]['uid']


def hap_stat_script(remote):
    q = shlex.quote(remote)
    return 'test -f '+q+' && test ! -L '+q+" && stat -c '%u %g %a %s %Y %i' "+q+' && sha256sum '+q


def observe_renderer_hap(coordinator, request):
    import time
    label = request['details']['case']+'-renderer-installed'; began = time.monotonic_ns()
    raw = coordinator.shell('bm dump -n com.ohos.wallpaper',label+'-BMS')
    bms = coordinator.text(raw,label+'-BMS'); remote,uid = renderer_path(raw)
    transfer = coordinator.receive(remote,label+'-HAP',maximum=32*1024*1024)
    image_hap = checked(coordinator.inputs['renderer_provider_hap'])
    if checked(transfer['file']).read_bytes() != image_hap.read_bytes():
        raise ValueError('BMS-installed Wallpaper HAP differs from actual source-bound current image')
    coordinator.value.setdefault('renderer_installed_haps',[]).append({'case':request['details']['case'],
        'sequence':request['sequence'],'nonce':request['nonce'],'began_ns':began,'finished_ns':time.monotonic_ns(),
        'BMS':bms,'uid':uid,'transfer':transfer})
    coordinator.save()


def verify_renderer_haps(coordinator, native, image_hap, *, target):
    from batch_apps_wallpaper_connection import command_output
    from batch_media_verify_wallpaper_runtime import transferred
    rows = coordinator.get('renderer_installed_haps',[]); result=[]
    if [r['case'] for r in rows] != ['desktop-1','desktop-2']:
        raise ValueError('two actual BMS-installed Wallpaper HAP observations required')
    for row in rows:
        actions = [a for a in coordinator['actions'] if a['sequence'] == row['sequence']]
        if len(actions) != 1: raise ValueError('installed HAP has no unique actual action')
        action = actions[0]; request = json.loads(checked(action['request']).read_text())
        if (request['action'] != 'show-real-desktop' or request['details'] != {'case':row['case']} or
                request['nonce'] != row['nonce'] or request['boot_id'] != native['boot_id'] or
                not action['began_ns'] <= row['began_ns'] <= row['finished_ns'] <= action['finished_ns']):
            raise ValueError('BMS-installed HAP read outside actual same-boot public change ACK interval')
        label = row['case']+'-renderer-installed'
        raw = command_output(coordinator,label+'-BMS','bm dump -n com.ohos.wallpaper',row['BMS'],target)
        remote,uid = renderer_path(raw); transfer = row['transfer']
        if remote != transfer['remote'] or uid != row['uid']: raise ValueError('actual installed BMS path/UID differs')
        for suffix,key in (('stat','before'),('stat-after','after')):
            command_output(coordinator,label+'-HAP-'+suffix,hap_stat_script(remote),transfer[key],target)
        received,metadata = transferred(transfer)
        if received.read_bytes() != regular(image_hap).read_bytes(): raise ValueError('received installed renderer differs from source-bound image HAP')
        commands=[c for c in coordinator['commands'] if c['label']==label+'-HAP-recv']
        if (len(commands)!=1 or commands[0].get('exit_code')!=0 or commands[0]['argv'][1:]!=
                ['-t',target,'file','recv',remote,str(received)]):
            raise ValueError('actual installed renderer HAP transfer missing or wrong guest/path')
        checked({k:commands[0][k] for k in ('path','sha256')})
        result.append({'case':row['case'],'uid':uid,'remote':remote,'HAP':transfer['file'],'actual_stat':metadata})
    return result


def verify_mappings(coordinator, native, *, target):
    """Recompute raw mappings inside each Apply→ACK interval and exact transport."""
    rows = coordinator.get('native_mappings', [])
    if [r['case'] for r in rows] != ['desktop-1','desktop-2']:
        raise ValueError('both actual public desktop change mapping observations required')
    from batch_apps_wallpaper_connection import command_output
    results = []
    for row in rows:
        actions = [a for a in coordinator['actions'] if a['sequence'] == row['sequence']]
        if len(actions) != 1: raise ValueError('mapping has no unique actual action')
        action = actions[0]; request = json.loads(checked(action['request']).read_text())
        if (request['action'] != 'show-real-desktop' or request['details'] != {'case': row['case']} or
                request['nonce'] != row['nonce'] or request['boot_id'] != native['boot_id'] or
                not action['began_ns'] <= row['began_ns'] <= row['finished_ns'] <= action['finished_ns']):
            raise ValueError('native observation not inside real same-boot public change ACK interval')
        label=row.get('capture_label')
        if not isinstance(label,str) or not re.fullmatch(re.escape(row['case'])+r'-native-maps-scan-[0-2]',label):
            raise ValueError('exact successful complete mapping capture label required')
        raw = command_output(coordinator,label,maps_script(request,native),row['raw'],target)
        actual = parse_maps(raw, request, native)
        if row['parsed'] != actual: raise ValueError('native mapping normalization differs')
        results.append({'case':row['case'],'nonce':row['nonce'],'raw':row['raw'],**actual})
    return {'scope':SCOPE,'boot_id':native['boot_id'],'stages':results,
        'service_token_to_pid_directly_observed':False,'connection_caller_identity_observed':False,
        'first_artifact_behavior_gate_passed':False,'ledger_closed':False}
