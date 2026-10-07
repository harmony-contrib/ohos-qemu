from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "patches/common/web/arkweb/m144_core_build"
PATCH = COMPONENT / "0001-reference-only-supported-angle-test-targets.patch"


class M144CoreBuildTests(unittest.TestCase):
    def test_hunk_counts_pristine_repeat_and_unknown_drift(self):
        patch_sections(PATCH)
        sdk_patch = COMPONENT / "0002-use-explicit-prepared-sdk-before-core-gn.patch"
        patch_sections(sdk_patch)
        header_patch = COMPONENT / "0003-declare-blankless-generated-header-dependency.patch"
        patch_sections(header_patch)
        cache_patch = COMPONENT / "0004-invalidate-glue-prepare-on-interface-content-change.patch"
        patch_sections(cache_patch)
        colors_patch = COMPONENT / "0005-build-colors-generator-only-with-host-toolchain-on-ohos.patch"
        patch_sections(colors_patch)
        colors_tests_patch = COMPONENT / "0006-select-host-colors-generator-in-chrome-unit-tests.patch"
        patch_sections(colors_tests_patch)
        stub_patch = COMPONENT / "0007-order-ndk-wrapper-links-after-real-stub-target.patch"
        patch_sections(stub_patch)
        host_patch = COMPONENT / "0008-retain-explicit-public-host-config-with-prepared-sdk.patch"
        patch_sections(host_patch)
        template_patch = COMPONENT / "0009-select-release-hvigor-in-the-public-project-source-template.patch"
        patch_sections(template_patch)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_preimages(root, (PATCH, sdk_patch, header_patch, cache_patch, colors_patch, colors_tests_patch, stub_patch, host_patch, template_patch))
            command = ["bash", str(COMPONENT / "apply.sh"), "--source-root", str(root)]
            for _ in range(2):
                subprocess.run(command, capture_output=True, check=True)
            subprocess.run(["git", "-C", str(root), "apply", "--reverse", str(PATCH)], check=True)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_only_test_aggregation_changes(self):
        sections = patch_sections(PATCH)
        self.assertEqual(set(sections), {"src/BUILD.gn", "src/third_party/angle/src/tests/BUILD.gn"})
        text = PATCH.read_text()
        for feature in ("angle_enable_vulkan =", "enable_webgl =", "enable_rust =", "arkweb_unittests ="):
            self.assertNotIn(feature, text)

    def test_official_prepare_copies_the_fixed_source_template_without_config_rollback(self):
        import json
        import shutil
        patch = COMPONENT / '0009-select-release-hvigor-in-the-public-project-source-template.patch'
        sections = patch_sections(patch)
        relative = 'src/third_party/ohos_nweb_hap/dependencies/rk/hvigor/hvigor-config.json5'
        self.assertEqual(set(sections), {relative})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_preimages(root, patch)
            subprocess.run(['git', '-C', str(root), 'apply', str(patch)], check=True)
            template = root / relative
            expected = {'modelVersion': '6.0.0', 'dependencies': {},
                        'properties': {'hvigor.dependency.useNpm': True}}
            self.assertEqual(json.loads(template.read_text()), expected)
            project = root / 'src/third_party/ohos_nweb_hap/hvigor'
            # The official public build removes this derived directory, then
            # copies dependencies/rk/* before the post-prepare patch hook.
            for _ in range(2):
                if project.exists():
                    shutil.rmtree(project)
                shutil.copytree(template.parent, project)
                self.assertEqual(json.loads((project / template.name).read_text()), expected)
        package = ROOT / 'patches/common/web/arkweb/m144_core_package'
        for number in ('0007-', '0008-'):
            current = next(package.glob(number + '*.patch'))
            self.assertNotIn('hvigor/hvigor-config.json5', current.read_text())

    def test_actual_stub_target_is_a_link_dependency_not_only_an_unordered_library_name(self):
        stub_patch = COMPONENT / '0007-order-ndk-wrapper-links-after-real-stub-target.patch'
        self.assertEqual(set(patch_sections(stub_patch)), {'src/arkweb/ohos_adapter_ndk/BUILD.gn'})
        added = [line for line in stub_patch.read_text().splitlines()
                 if line.startswith('+') and not line.startswith('+++')]
        self.assertEqual(added, ['+  deps = [":adapter_ndk_gen", ":adapter_ndk_stub"]'])
        self.assertIn('source_set("adapter_ndk_wrapper")', stub_patch.read_text())

    def test_ohos_colors_generator_preserves_real_action_and_non_ohos_targets(self):
        patch = COMPONENT / '0005-build-colors-generator-only-with-host-toolchain-on-ohos.patch'
        sections = patch_sections(patch)
        self.assertEqual(set(sections), {
            'src/chrome/browser/BUILD.gn',
            'src/chrome/browser/ui/webui/cr_components/theme_color_picker/BUILD.gn',
            'src/chrome/browser/ui/webui/signin/BUILD.gn',
            'src/chrome/browser/new_tab_page/chrome_colors/BUILD.gn',
        })
        text = patch.read_text()
        added = '\n'.join(line[1:] for line in text.splitlines() if line.startswith('+') and not line.startswith('+++'))
        self.assertEqual(added.count('generate_colors_info($host_toolchain)'), 3)
        self.assertEqual(added.count('_colors_info_tool,'), 3)
        self.assertIn('[ _colors_info_tool ]', added)
        self.assertIn('if (!is_ohos || current_toolchain == host_toolchain)', added)
        self.assertIn('compiled_action("generate_chrome_colors_info")', text)
        for forbidden in ('--no-undefined', '--fatal-warnings', '-nostartfiles', '_start',
                          'enable_webgl =', 'enable_rust =', 'arkweb_unittests ='):
            self.assertNotIn(forbidden, added)

    def test_native_builder_keeps_official_features_and_frozen_parse(self):
        builder = (ROOT / "scripts/build_m144_arkweb_core_in_docker.sh").read_text()
        self.assertIn("main() {", builder)
        self.assertTrue(builder.rstrip().endswith('main "$@"'))
        self.assertIn('prepare_m144_release_sources.py" --verify-only', builder)
        self.assertNotIn('check_revision "${SOURCE_ROOT}" 4ae5', builder)
        self.assertIn("f1becee9a78f65a094d17f9116727069aab5b235d4c9977346dbf8251a66a5db", builder)
        self.assertIn('"${SOURCE_ROOT}/arkweb/build/build.sh" -t n -A', builder)
        self.assertNotIn("enable_cef=false", builder)
        self.assertNotIn("arkweb_unittests=false", builder)
        self.assertNotIn("enable_rust=false", builder)

    def test_colors_generator_unit_test_edge_uses_host_without_disabling_tests(self):
        patch = COMPONENT / '0006-select-host-colors-generator-in-chrome-unit-tests.patch'
        self.assertEqual(set(patch_sections(patch)), {'src/chrome/test/BUILD.gn'})
        added = '\n'.join(line[1:] for line in patch.read_text().splitlines()
                          if line.startswith('+') and not line.startswith('+++'))
        self.assertEqual(added.count('generate_colors_info($host_toolchain)'), 1)
        self.assertEqual(added.count('_colors_info_tool,'), 1)
        self.assertIn('if (is_ohos)', added)
        for forbidden in ('arkweb_unittests', 'testonly =', 'unit_tests =', '_start', '-Wl'):
            self.assertNotIn(forbidden, added)

    def test_blankless_declares_generated_header_without_url_dependency_cycle(self):
        patch_file = COMPONENT / "0003-declare-blankless-generated-header-dependency.patch"
        self.assertEqual(set(patch_sections(patch_file)), {"src/base/BUILD.gn"})
        added = [line for line in patch_file.read_text().splitlines() if line.startswith('+') and not line.startswith('+++')]
        self.assertEqual(added, ['+    deps += [ "//build:robolectric_buildflags" ]'])
        self.assertNotIn('"//url"', patch_file.read_text())

    def test_prepare_content_key_is_stable_and_not_just_head_or_mtime(self):
        text = (COMPONENT / '0004-invalidate-glue-prepare-on-interface-content-change.patch').read_text()
        body = '\n'.join(line[1:] for line in text.splitlines() if line.startswith('+') and not line.startswith('+++'))
        helper = body[:body.index('local_header_sha256=')].rstrip()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'adapter').mkdir()
            header = root / 'adapter/example.h'
            header.write_text('// source header\n')
            formatter = root / 'clang-format'
            formatter.write_text('fixed formatter binary fixture')
            # macOS sort accepts -z only in some versions; production runs in
            # Linux Docker. The fixture substitutes its equivalent GNU gsort
            # when present, otherwise checks the declared body structurally.
            import shutil
            sort = shutil.which('gsort') or shutil.which('sort')
            result = subprocess.run([sort, '-z'], input=b'', capture_output=True)
            if result.returncode:
                self.skipTest('GNU-compatible sort -z required for this Linux cache fixture')
            helper = helper[helper.index('interface_headers_sha256()'):]
            script = 'INTERFACE_INCLUDE_DIR="$1"\nCLANG_FORMAT_DIR="$1"\nTASK_SORT="$2"\n' + helper.replace('sort -z', '"$TASK_SORT" -z') + '\ninterface_headers_sha256\n'
            def digest():
                return subprocess.check_output(['bash', '-c', script, 'fixture', str(root), sort], text=True)
            original = digest()
            header.touch()
            self.assertEqual(digest(), original)
            header.write_text('// patched input at the same commit\n')
            modified = digest()
            self.assertNotEqual(modified, original)
            self.assertEqual(digest(), modified)
            formatter.write_text('different pinned formatter binary fixture')
            self.assertNotEqual(digest(), modified)
        self.assertIn('local_header_sha256=$(sed -n', body)
        self.assertIn('interface_headers_sha256', body)
        self.assertNotIn('git reset', text)


if __name__ == "__main__":
    unittest.main()
