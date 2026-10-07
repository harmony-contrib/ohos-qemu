"""Tool bootstrap safety/selection fixtures; no build/guest acceptance."""
import ast
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_m144_release_tools import GN_REVISION, install_tree, literal_entry, safe_member, selected_objects, tool_data_filter


class ReleaseBuildToolTests(unittest.TestCase):
    def test_deps_literal_does_not_execute_arbitrary_code(self):
        tree = ast.parse("vars = {'safe': 'fixed', 'bad': open('/not-read').read()}")
        self.assertEqual(literal_entry(tree, 'vars', 'safe'), 'fixed')
        with self.assertRaises(ValueError):
            literal_entry(tree, 'vars', 'bad')

    def test_linux_clang_selection_excludes_tidy_mac_and_coverage(self):
        paths = {
            'src/third_party/llvm-build/Release+Asserts': ['Linux_x64/clang-llvmorg-22.tar.xz',
                'Linux_x64/clang-tidy-llvmorg-22.tar.xz', 'Mac/clang-llvmorg-22.tar.xz',
                'Linux_x64/llvmobjdump-llvmorg-22.tar.xz'],
            'src/third_party/rust-toolchain': ['Linux_x64/rust-toolchain-fixed.tar.xz', 'Mac/rust-toolchain-fixed.tar.xz'],
            'src/third_party/node/linux': ['node'], 'src/third_party/node/node_modules': ['modules'],
            'src/buildtools/linux64-format': ['format'],
        }
        deps = {key: {'dep_type': 'gcs', 'bucket': 'pinned-bucket', 'objects': [
            {'object_name': value, 'sha256sum': 'a' * 64, 'size_bytes': 10, 'generation': 123} for value in values]}
            for key, values in paths.items()}
        source = "vars = " + repr({'gn_version': 'git_revision:' + GN_REVISION}) + '\ndeps = ' + repr(deps)
        selected = selected_objects(source)
        self.assertEqual(len(selected), 6)
        self.assertNotIn('tidy', ' '.join(item['object_name'] for item in selected))
        self.assertTrue(all(item['sha256sum'] == 'a' * 64 for item in selected))
        with self.assertRaises(ValueError):
            selected_objects(source.replace(GN_REVISION, '0' * 40))

    def test_tar_escape_special_file_and_absolute_link_rejected(self):
        for name in ('../escape', '/escape', 'dir/../../escape', 'dir\\escape'):
            with self.assertRaises(ValueError):
                safe_member(tarfile.TarInfo(name))
        member = tarfile.TarInfo('dir/link')
        member.type = tarfile.SYMTYPE
        for link in ('../../escape', '/absolute'):
            member.linkname = link
            with self.assertRaises(ValueError):
                safe_member(member)
        member.linkname = '../safe'
        safe_member(member)
        member.type = tarfile.CHRTYPE
        with self.assertRaises(ValueError):
            safe_member(member)

    def test_fixed_linux_sysroot_systemd_escaped_names_are_literal_not_traversal(self):
        member = tarfile.TarInfo(r'./lib/systemd/system/system-systemd\x2dcryptsetup.slice')
        safe_member(member, allow_linux_escaped_names=True)
        with self.assertRaises(ValueError):
            safe_member(member)
        with self.assertRaises(ValueError):
            safe_member(tarfile.TarInfo(r'../escape\x2dfile'), allow_linux_escaped_names=True)
        with self.assertRaises(ValueError):
            safe_member(tarfile.TarInfo(r'dir\..\escape'), allow_linux_escaped_names=True)

    def test_identical_reuse_and_add_missing_never_overwrites_unknown_file(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            stage, target = base / 'stage', base / 'target'
            stage.mkdir()
            (stage / 'tool').write_text('exact fixed archive bytes')
            install_tree(stage, target)
            install_tree(stage, target)
            (stage / 'additional').write_text('pinned missing tool')
            install_tree(stage, target)
            (target / 'tool').write_text('unknown edit')
            with self.assertRaises(ValueError):
                install_tree(stage, target)
            self.assertEqual((target / 'tool').read_text(), 'unknown edit')

    def test_explicit_text_crlf_preservation_is_hashed_not_arbitrary_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            stage, target = base / 'stage', base / 'target'
            stage.mkdir()
            target.mkdir()
            (stage / 'module.js').write_bytes(b'line1\r\nline2\r\n')
            (target / 'module.js').write_bytes(b'line1\nline2\n')
            with self.assertRaises(ValueError):
                install_tree(stage, target)
            proof = install_tree(stage, target, allow_crlf_normalized=True)['module.js']
            self.assertEqual(proof['preserved_existing_normalization'], 'CRLF_to_LF_only')
            self.assertNotEqual(proof['sha256'], proof['source_archive_sha256'])
            (target / 'module.js').write_bytes(b'line1\nchanged\n')
            with self.assertRaises(ValueError):
                install_tree(stage, target, allow_crlf_normalized=True)

    def test_unknown_alias_root_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            stage = base / 'stage'
            stage.mkdir()
            target = base / 'target'
            target.symlink_to(stage)
            with self.assertRaises(ValueError):
                install_tree(stage, target)

    def test_parent_relative_sysroot_link_extracts_without_filter_bypass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'sysroot.tar'
            payload = b'fixed font configuration'
            with tarfile.open(archive, 'w') as tar:
                file = tarfile.TarInfo('./usr/share/fontconfig/conf.avail/test.conf')
                file.size = len(payload)
                tar.addfile(file, io.BytesIO(payload))
                link = tarfile.TarInfo('./etc/fonts/conf.d/test.conf')
                link.type = tarfile.SYMTYPE
                link.linkname = '../../../usr/share/fontconfig/conf.avail/test.conf'
                tar.addfile(link)
            target = root / 'owned'
            with tarfile.open(archive) as tar:
                for member in tar.getmembers():
                    safe_member(member)
                tar.extractall(target, filter=tool_data_filter)
            self.assertEqual((target / 'etc/fonts/conf.d/test.conf').read_bytes(), payload)
            self.assertEqual((target / 'etc/fonts/conf.d/test.conf').readlink().as_posix(), link.linkname)
            malicious = tarfile.TarInfo('dir/link')
            malicious.type = tarfile.SYMTYPE
            malicious.linkname = '../alias/escape'
            (target / 'alias').symlink_to(root)
            with self.assertRaises(tarfile.LinkOutsideDestinationError):
                tool_data_filter(malicious, target)


if __name__ == '__main__':
    unittest.main()
