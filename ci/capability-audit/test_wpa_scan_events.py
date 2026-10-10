"""WPA routing predicate boundaries, not actual scan or radio acceptance."""
from pathlib import Path
import unittest
from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/third_party/wpa_supplicant/scan_events'
PATCH = COMPONENT / '0001-report-real-qemu-scan-completion-outside-updater.patch'


class WpaScanEventTests(unittest.TestCase):
    def test_real_inline_predicate_preserves_updater_only_for_other_products(self):
        sections = patch_sections(PATCH)
        header = next(value for name, value in sections.items() if name.endswith('/common.h'))
        helper = '\n'.join(header[0][2])
        for qemu in (False, True):
            prefix = '#define CONFIG_OPEN_HARMONY_PATCH\n'
            if qemu:
                prefix += '#define CONFIG_QEMU_WPA_SCAN_EVENTS\n'
            source = prefix + '#include <stdbool.h>\n#include <assert.h>\n' + helper
            source += '\nstatic bool updater;\nbool IsUpdaterMode(void) { return updater; }\nint main(void) {\n'
            source += 'updater = false; assert(IsWpaScanEventEnabled() == ' + ('true' if qemu else 'false') + ');\n'
            source += 'updater = true; assert(IsWpaScanEventEnabled());\n}\n'
            with self.subTest(qemu=qemu): compile_run(source)

    def test_both_real_completion_paths_keep_two_scan_id_branches(self):
        sections = patch_sections(PATCH)
        for name in ('events.c', 'scan.c'):
            hunks = next(value for path, value in sections.items() if path.endswith('/' + name))
            self.assertEqual(len(hunks), 2)
            for _, old, new in hunks:
                self.assertEqual('\n'.join(new), '\n'.join(old).replace(
                    'if (IsUpdaterMode())', 'if (IsWpaScanEventEnabled())'))
                self.assertIn('struct WpaRecvScanResultParam', '\n'.join(new))
        self.assertEqual(len(sections), 4)

    def test_GN_flag_is_limited_to_three_QEMU_products(self):
        sections = patch_sections(PATCH)
        gn = next(value for path, value in sections.items() if path.endswith('/BUILD.gn'))
        text = '\n'.join(gn[0][2])
        for product in ('arm64_virt', 'armv7a_virt', 'x86_64_virt'):
            self.assertIn('product_name == "' + product + '"', text)
        self.assertIn('cflags += [ "-DCONFIG_QEMU_WPA_SCAN_EVENTS" ]', text)
        self.assertEqual(text.count('product_name =='), 3)
        self.assertNotIn('device_type', text)
        build = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertIn('bash "${QEMU_WPA_SCAN_EVENTS_COMPONENT_SCRIPT}"', build)


if __name__ == '__main__':
    unittest.main()
