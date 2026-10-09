import json
import unittest

from run_fa_particle_probe import process_ids, verify_page, verify_process


class FaParticleRunnerTests(unittest.TestCase):
    def test_page_and_service_process_set(self):
        self.assertEqual(process_ids('312 490\n'), ['312', '490'])
        for text in ('', '0', '-1', '12 12', '12;echo pass', '1 2 3 4 5 6 7 8 9'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                process_ids(text)

    def test_all_four_kernel_uids_must_match(self):
        uid = 20010038
        verify_process('Name:\tprobe\nUid:\t' + '\t'.join([str(uid)] * 4) + '\n', uid)
        for text in ('Uid:\t0 0 0 0\n', 'Uid:\t20010038 0 20010038 20010038\n',
                     'Uid:\t20010038 20010038 20010038\n', '',
                     'Uid:\t20010038 20010038 20010038 20010038\n' * 2):
            with self.subTest(text=text), self.assertRaises(ValueError):
                verify_process(text, uid)

    def test_exact_fresh_page_start(self):
        nonce = '1' * 32
        text = 'log QEMU_FA_PAGE:' + json.dumps({'nonce': nonce, 'status': 'pass'})
        verify_page(text, nonce)
        for value in ('', text + '\n' + text, text.replace('pass', 'fail'),
                      text.replace(nonce, '2' * 32), text.replace('"pass"', '"pass", "extra": true')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                verify_page(value, nonce)


if __name__ == '__main__':
    unittest.main()
