import unittest

from hdc_transport import failed


class TransportTests(unittest.TestCase):
    def test_zero_exit_stderr_transport_failure(self):
        self.assertTrue(failed('', 'Connect server failed\n'))

    def test_existing_errors_on_either_stream(self):
        for text in ('[Fail] execute failed', 'Device not found or connected'):
            self.assertTrue(failed(text))
            self.assertTrue(failed('', text))

    def test_real_identity_is_not_transport_failure(self):
        self.assertFalse(failed('0\nphone \naarch64\n'))

    def test_discussion_of_error_is_not_a_transport_message(self):
        self.assertFalse(failed('test: Connect server failed expected=false\n'))
