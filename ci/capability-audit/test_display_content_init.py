"""Initialization patch guards; these do not replace packaged screenshot tests."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/graphic/graphic_2d/display_content_init'
RELATIVE = 'foundation/graphic/graphic_2d/rosen/modules/render_service_base/include/pipeline/rs_logical_display_render_node.h'
ORIGINAL = '''    void InitRenderParams() override;

    ScreenId screenId_ = INVALID_SCREEN_ID;
    Rect contentRect_;
    std::vector<Occlusion::Rect> topSurfaceOpaqueRects_;

    // bounds rotation
'''


class DisplayContentInitTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='qemu-display-init-')
        self.addCleanup(directory.cleanup)
        self.source = Path(directory.name)
        self.target = self.source / RELATIVE
        self.target.parent.mkdir(parents=True)
        self.target.write_text(ORIGINAL)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.source)],
                              text=True, capture_output=True)

    def test_initialize_only_rect_and_idempotence(self):
        for _ in range(2):
            result = self.apply()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.target.read_text(), ORIGINAL.replace('Rect contentRect_;',
                             'Rect contentRect_ = {0, 0, 0, 0};'))

    def test_refuse_changed_layout(self):
        self.target.write_text(ORIGINAL.replace('Rect contentRect_;', 'Rect renamed_;'))
        before = self.target.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.target.read_bytes(), before)

    def test_recheck_after_marker(self):
        self.assertEqual(self.apply().returncode, 0)
        self.target.write_text(self.target.read_text().replace('{0, 0, 0, 0}', '{0, 0, 64, 65535}'))
        self.assertNotEqual(self.apply().returncode, 0)

    def test_shared_build_includes_component(self):
        text = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertIn('graphic_2d/display_content_init/apply.sh', text)
        self.assertIn('bash "${DISPLAY_CONTENT_INIT_SCRIPT}" --source-root "${OHOS_ROOT}"', text)
