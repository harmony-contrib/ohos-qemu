"""Compare the selected source and actual image BMS preinstall entry."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'patches/lib'))
from preinstall_selection import entry, same_json, uninstall_policy
from ext_image_entries import dump_unique_file
from verify_alsa_config_image import debugfs_path, file_sha256


def verify_selection(source, bundle, image=None, scratch=None):
    path = source / 'vendor/ohemu/virt/preinstall-config/install_list.json'
    expected = entry(path.read_bytes(), bundle)
    result = {'entry': expected, 'source_sha256': file_sha256(path)}
    veto = path.with_name('uninstall_list.json')
    policy = uninstall_policy(veto.read_bytes(), bundle)
    result['source_uninstall_sha256'] = file_sha256(veto)
    if image is not None:
        directory = scratch / 'install-selection';directory.mkdir()
        actual, identity = dump_unique_file(image, ('/etc/app/install_list.json', '/system/etc/app/install_list.json'),
                                           directory, debugfs_path())
        entry(actual.read_bytes(), bundle)
        result.update(identity)
        result['image_file_sha256'] = file_sha256(actual)
        actual, identity = dump_unique_file(image, ('/etc/app/uninstall_list.json', '/system/etc/app/uninstall_list.json'),
                                           directory, debugfs_path())
        if not same_json(uninstall_policy(actual.read_bytes(), bundle), policy):
            raise ValueError('packaged uninstall/recover policy differs from validated source')
        result['uninstall_policy'] = {**identity, 'image_file_sha256': file_sha256(actual)}
    return result
