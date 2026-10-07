#!/usr/bin/env python3
import json
import unittest
from verify_web_results import verify, REQUIRED


class WebResultTests(unittest.TestCase):
    def good_log(self):
        values = [f"{key}.result={json.dumps(value)}" for key, value in REQUIRED.items()]
        result = {"pass": True, "pixel": [51, 102, 153, 255], "error": 0, "invalid_shader_rejected": True}
        values.extend(f"web.graphics.webgl{version}.render.result={json.dumps(json.dumps(result))}" for version in (1, 2))
        values.extend(f"web.renderer.recovery.webgl{version}.render.result={json.dumps(json.dumps(result))}" for version in (1, 2))
        values.append('web.canvas.2d.render.result=' + json.dumps(json.dumps(result)))
        for count, name in enumerate(('js', 'reload', 'renderer.recovery'), start=1):
            values.append(f'web.js.proxy.callback={name}')
            values.append(f'web.{name}.proxy.result=' + json.dumps(json.dumps({'reply': f'arkts:{name}', 'calls': count})))
        return "\n".join(values + ["web.execution.complete=true"])

    def test_real_render_results_pass(self):
        self.assertEqual(verify(self.good_log())["status"], "pass")

    def test_context_only_results_cannot_pass(self):
        log = "\n".join(line for line in self.good_log().splitlines() if ".render." not in line)
        self.assertEqual(verify(log)["status"], "fail")

    def test_timeout_late_success_still_fails(self):
        self.assertEqual(verify(self.good_log() + "\nweb.graphics.webgl1.timeout=true")["status"], "fail")

    def test_wrong_pixel_cannot_pass_on_claimed_pass_true(self):
        log = self.good_log().replace("51, 102, 153, 255", "0, 0, 0, 255")
        self.assertEqual(verify(log)["status"], "fail")

    def test_missing_completion_and_empty_log_fail(self):
        self.assertEqual(verify(self.good_log().replace("web.execution.complete=true", ""))["status"], "fail")
        self.assertEqual(verify("")["status"], "fail")

    def test_proxy_return_alone_does_not_prove_native_callback(self):
        log = '\n'.join(line for line in self.good_log().splitlines() if '.callback=' not in line)
        self.assertEqual(verify(log)['status'], 'fail')

    def test_proxy_state_must_survive_navigation(self):
        log = self.good_log().replace('\\"calls\\": 3', '\\"calls\\": 1')
        self.assertNotEqual(log, self.good_log())
        self.assertEqual(verify(log)['status'], 'fail')

    def test_initial_render_success_does_not_prove_renderer_recovery(self):
        log = '\n'.join(line for line in self.good_log().splitlines() if 'web.renderer.recovery.webgl' not in line)
        self.assertEqual(verify(log)['status'], 'fail')

    def test_renderer_termination_failure_is_not_accepted(self):
        log = self.good_log().replace('web.renderer.terminate.result=true', 'web.renderer.terminate.result=false')
        self.assertEqual(verify(log)['status'], 'fail')

    def test_boolean_graphics_error_is_not_integer_zero(self):
        log = self.good_log().replace('\\"error\\": 0', '\\"error\\": false')
        self.assertEqual(verify(log)['status'], 'fail')


if __name__ == "__main__":
    unittest.main()
