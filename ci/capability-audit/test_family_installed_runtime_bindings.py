"""Pure host counterexamples for family adapters; no guest data or ELF build."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

import batch_media_wallpaper_artifacts as adapters
import batch_system_build_runtime_helpers as product
from batch_system_calendar_runtime_verify import raw_bound


def artifact(path):
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def runtime_row():
    def record(path, digest): return {'path': path, 'sha256': digest*64, 'bytes': 8}
    profile = {'schema_version': 1, 'kind': 'installed_product_runtime', 'product': 'arm64_virt', 'arch': 'arm64',
        'device': 'phone', 'source_root': '/ohos', 'archive': record('/host-only/F.tar.gz', 'a'),
        'system_image': dict(record('/host-only/system.img', 'b'),
                             archive_member='openharmony-qemu-arm64-arm64_virt-phone/images/system.img'), 'dsos': {}}
    for name, member, digest in (('libc++.so', '/lib64/chipset-sdk-sp/libc++.so', 'c'),
                                  ('libc.so', '/lib/ld-musl-aarch64.so.1', 'd'),
                                  ('libquery.z.so', '/lib64/platformsdk/libquery.z.so', 'e')):
        profile['dsos'][name] = {'soname': name, 'image_member': member,
            'staged': record('/ohos/out/arm64_virt/packages/phone/system' + member, digest),
            'image_file': record('/host-only/image-dump' + member, digest)}
    inputs = [copy.deepcopy(v['staged']) for v in profile['dsos'].values()]
    row = {'DT_NEEDED': sorted(profile['dsos']), 'actual_link_inputs': inputs,
           'actual_link_input_sonames': {v['staged']['path']: k for k, v in profile['dsos'].items()},
           'installed_runtime_profile': {'source': record('/host-only/profile.json', 'f'), 'profile': profile}}
    return row, {r['path']: r for r in inputs}


class InstalledFamilyBindingsTests(unittest.TestCase):
    def test_all_actual_needed_retained_and_loader_uses_real_soname_alias(self):
        row, inputs = runtime_row()
        result = adapters.installed_runtime_binding(row, row['DT_NEEDED'], inputs)
        self.assertEqual(row['DT_NEEDED'], [v['soname'] for v in result['product_DSOs']])
        self.assertEqual(('/system/lib64/chipset-sdk-sp/libc++.so',), product.runtime_guest_paths(result, 'libc++.so'))
        self.assertEqual(('/system/lib/ld-musl-aarch64.so.1',), product.runtime_guest_paths(result, 'libc.so'))
        for key in ('installed_runtime_profile', 'actual_link_inputs', 'actual_link_input_sonames'):
            self.assertEqual(row[key], result[key])

    def test_partial_needed_no_profile_wrong_soname_and_unretained_input_refused(self):
        row, inputs = runtime_row()
        with self.assertRaises(ValueError): adapters.installed_runtime_binding(row, row['DT_NEEDED'][:-1], inputs)
        mutations = [lambda v: v.pop('installed_runtime_profile'),
                     lambda v: v['installed_runtime_profile']['profile']['dsos'].pop('libquery.z.so'),
                     lambda v: v['actual_link_input_sonames'].clear(),
                     lambda v: v['actual_link_inputs'].append(copy.deepcopy(v['actual_link_inputs'][0]))]
        for change in mutations:
            value = copy.deepcopy(row); change(value)
            with self.subTest(change=mutations.index(change)), self.assertRaises(ValueError):
                adapters.installed_runtime_binding(value, value['DT_NEEDED'], inputs)
        with self.assertRaises(ValueError): adapters.installed_runtime_binding(row, row['DT_NEEDED'], {})

    def test_legacy_basename_candidate_and_other_archive_refused(self):
        row, _ = runtime_row(); name = 'libc++.so'; wanted = 'c'*64 + '  /system/lib64/chipset-sdk-sp/libc++.so'
        actual = product.verify_guest_runtime_raw(row, name, wanted, archive_sha256='a'*64)
        self.assertEqual('/system/lib64/chipset-sdk-sp/libc++.so', actual['path'])
        for raw in (wanted.replace('chipset-sdk-sp/', ''), wanted.replace('  /', ' /'), wanted + '\n' + wanted,
                    wanted.replace('c'*64, 'e'*64)):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                product.verify_guest_runtime_raw(row, name, raw, archive_sha256='a'*64)
        with self.assertRaises(ValueError): product.verify_guest_runtime_raw(row, name, wanted, archive_sha256='0'*64)

    def wallpaper_observation(self, directory):
        row, inputs = runtime_row(); binding = adapters.installed_runtime_binding(row, row['DT_NEEDED'], inputs)
        name = 'libc++.so'; raw = 'c'*64 + '  /system/lib64/chipset-sdk-sp/libc++.so'
        raw_path = directory/'raw.txt'; raw_path.write_text(raw)
        marker = '__UITEST_EXIT_' + 'f'*32 + '__='
        script = product.runtime_guest_script(binding, name)
        wrapped = script + '; task_ui_rc=$?; printf "\\n' + marker + '%s\\n" "$task_ui_rc"'
        log = directory/'command.log'; log.write_text(raw+'\n\n'+marker+'0\n')
        command = {'argv': ['/host-only/hdc', '-t', 'bound-target', 'shell', wrapped], 'exit_code': 0, **artifact(log)}
        return binding, name, {'command': 0, 'actual_hashes': artifact(raw_path)}, [command]

    def test_wallpaper_replay_binds_script_path_archive_target_and_raw_transport(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve(); binding, name, observation, commands = self.wallpaper_observation(directory)
            def verify(obs=observation, rows=commands):
                return adapters.verify_runtime_guest_observation(binding, name, obs, rows,
                    target='bound-target', archive_sha256='a'*64)
            self.assertEqual('/system/lib64/chipset-sdk-sp/libc++.so', verify()['path'])
            for mutate in (lambda v: v[0]['argv'].__setitem__(2, 'foreign-target'),
                           lambda v: v[0]['argv'].__setitem__(-1, v[0]['argv'][-1].replace('test -f', 'printf guessed; test -f')),
                           lambda v: v[0].__setitem__('exit_code', 1)):
                changed = copy.deepcopy(commands); mutate(changed)
                with self.assertRaises(ValueError): verify(rows=changed)
            changed = dict(observation, command=True)
            with self.assertRaises(ValueError): verify(obs=changed)
            log = directory/'command.log'; log.write_text('c'*64+'  /system/lib64/libc++.so\n\n__UITEST_EXIT_'+'f'*32+'__=0\n')
            commands[0].update(artifact(log))
            with self.assertRaises(ValueError): verify()

    def test_calendar_raw_replay_requires_profile_script_and_real_positive_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve(); row, _ = runtime_row()
            script = product.runtime_guest_script(row, 'libc.so'); raw = 'd'*64 + '  /system/lib/ld-musl-aarch64.so.1\n'
            marker = '__QEMU_CHILD_EXIT_'+'f'*32+'__='
            wrapped = '('+script+'); task_child_rc=$?; printf "\\n'+marker+'%s\\n" "$task_child_rc"'
            path = directory/'raw-0001-DSO.txt'; path.write_text(raw)
            log = directory/'guest.log'; log.write_text(raw+'\n'+marker+'0\n')
            command = {'argv': ['/host-only/hdc', '-t', 'bound-target', 'shell', wrapped], 'exit_code': 0,
                       'log': str(log), 'sha256': artifact(log)['sha256']}
            capture = {'guest_commands': [command]}
            self.assertEqual(raw, raw_bound(capture, artifact(path), script))
            with self.assertRaises(ValueError): raw_bound(capture, artifact(path), 'sha256sum /system/lib64/libc.so')
            invalid = directory/'raw-0000-DSO.txt'; invalid.write_text(raw)
            with self.assertRaises(ValueError): raw_bound(capture, artifact(invalid), script)
            log.write_text(raw+'\n'+marker+'1\n'); command['sha256'] = artifact(log)['sha256']
            with self.assertRaises(ValueError): raw_bound(capture, artifact(path), script)


if __name__ == '__main__': unittest.main()
