"""Read exact acceptance-package SysCaps without changing the guest or image."""
import base64
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ci/capability-audit'))
from run_root_probe import digest

FILES = ('device-profile.json', 'native-gap-abi-image.json')


def binding(boot, image, archive_sha, arch, boot_id):
    image = Path(image)
    env = boot.get('test_environment', {})
    initial = boot.get('initial_package_file_sha256', {})
    if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
            boot.get('archive_sha256') != archive_sha or env.get('boot_id') != boot_id or
            env.get('guest_arch') != arch or env.get('device_type') != 'phone' or
            env.get('external_keepalive') is not False or not image.is_file() or image.is_symlink() or
            image.name != 'system.img' or image.parent.name != 'images' or
            env.get('freshly_extracted_directory') != str(image.parent.parent) or
            digest(image) != initial.get('images/system.img')):
        raise ValueError('unchanged freshly extracted phone acceptance image and exact owned boot required')
    package = image.parent.parent
    values = {}
    for name in FILES:
        path = package / name
        if not path.is_file() or path.is_symlink() or digest(path) != initial.get(name):
            raise ValueError('actual acceptance-package metadata changed or is not checksummed: ' + name)
        values[name] = json.loads(path.read_text())
    report = values['native-gap-abi-image.json']
    if (report.get('status') != 'pass' or report.get('arch') != arch or report.get('device') != 'phone' or
            report.get('system_image_sha256') != digest(image) or
            report.get('device_profile_sha256') != initial['device-profile.json'] or
            report.get('actual_syscap_sha256') != values['device-profile.json'].get('resolved_syscap_sha256')):
        raise ValueError('packaged ABI/profile proof is not for this actual image and device')
    return values


def read_syscap(image, docker_image):
    image = Path(image)
    # debugfs and the repository's existing unique-inode extractor run in
    # Docker. Both the actual image and repository mounts are read-only.
    script = (
        "import base64,json,sys,tempfile; from pathlib import Path; "
        "sys.path.insert(0,'/work/scripts'); from ext_image_entries import dump_unique_file; "
        "temporary=tempfile.TemporaryDirectory(prefix='qemu-profile-image-'); "
        "path,identity=dump_unique_file(Path('/pkg/system.img'),"
        "('/etc/syscap.json','/system/etc/syscap.json'),Path(temporary.name),'/sbin/debugfs'); "
        "print(json.dumps({'bytes':base64.b64encode(path.read_bytes()).decode(), 'entry':identity})); "
        "temporary.cleanup()"
    )
    argv = ['docker', 'run', '--rm', '--platform', 'linux/amd64',
        '--mount', 'type=bind,src=' + str(image.parent) + ',dst=/pkg,readonly',
        '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
        '--entrypoint', 'python3', docker_image, '-c', script]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    if result.returncode or result.stderr.strip():
        raise ValueError('could not capture the unambiguous actual packaged SysCap file')
    value = json.loads(result.stdout)
    data = base64.b64decode(value['bytes'], validate=True)
    json.loads(data)
    if not data or set(value) != {'bytes', 'entry'}:
        raise ValueError('malformed actual-image capture')
    return data, value['entry'], argv


def capture(boot_path, archive, arch, boot_id, output, docker_image):
    boot_path, archive, output = Path(boot_path), Path(archive), Path(output)
    if boot_path.is_symlink() or not boot_path.is_file():
        raise ValueError('original owned acceptance boot evidence required')
    boot = json.loads(boot_path.read_text())
    image = boot_path.parent / 'extract' / archive.name.removesuffix('.tar.gz') / 'images/system.img'
    values = binding(boot, image, digest(archive), arch, boot_id)
    data, entry, argv = read_syscap(image, docker_image)
    path = output / 'actual-image-syscap.json'
    with path.open('xb') as stream:
        stream.write(data)
    if digest(path) != values['device-profile.json']['resolved_syscap_sha256']:
        raise ValueError('actual SysCaps differ from checksummed packaged profile')
    files = {'actual-image-syscap.json': {'file': str(path), 'sha256': digest(path)}}
    for name in FILES:
        path = output / name
        with path.open('xb') as stream:
            stream.write((image.parent.parent / name).read_bytes())
        files[name] = {'file': str(path), 'sha256': digest(path)}
    binding(boot, image, digest(archive), arch, boot_id)
    return {'system_image': str(image), 'system_image_sha256': digest(image),
        'image_contract_files': files, 'actual_syscap_image_entry': entry,
        'image_capture_command': argv, 'capture_sha256': digest(Path(__file__))}


def verify_capture(document, root, boot, archive_sha, arch, boot_id):
    root = Path(root)
    image = Path(document.get('system_image', ''))
    if root.parent / 'boot/extract' not in image.parents:
        raise ValueError('profile discovery image escaped the enclosing acceptance extraction')
    values = binding(boot, image, archive_sha, arch, boot_id)
    if (document.get('system_image_sha256') != digest(image) or
            document.get('capture_sha256') != digest(Path(__file__)) or
            set(document.get('image_contract_files', {})) != {'actual-image-syscap.json', *FILES}):
        raise ValueError('original complete actual-image capture and current verifier required')
    captured = {}
    for name, row in document['image_contract_files'].items():
        path = root / name
        if (row.get('file') != str(path) or path.is_symlink() or not path.is_file() or
                digest(path) != row.get('sha256')):
            raise ValueError('captured profile/SysCap escaped, changed or disappeared')
        captured[name] = json.loads(path.read_text())
        if name in FILES and path.read_bytes() != (image.parent.parent / name).read_bytes():
            raise ValueError('captured metadata differs from actual checksummed package')
    if digest(root / 'actual-image-syscap.json') != values['device-profile.json']['resolved_syscap_sha256']:
        raise ValueError('captured SysCap bytes are not the immutable actual-image SysCap bytes')
    if document.get('actual_syscap_image_entry') != values['native-gap-abi-image.json'].get('actual_syscap_image_entry'):
        raise ValueError('captured SysCap inode/path differs from actual packaged image proof')
    return captured['device-profile.json'], captured['actual-image-syscap.json']
