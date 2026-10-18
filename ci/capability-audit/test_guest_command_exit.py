"""Command framing counterexamples; no device or behavior acceptance claims."""
import re
import tempfile
import unittest

from guest_ui import command_exit, GuestUi, GuestUiCommandError


class CommandExitTests(unittest.TestCase):
    marker = '__UITEST_EXIT_' + 'a'*32 + '__='

    def test_embedded_hdc_printf_is_preserved_and_not_a_second_footer(self):
        body = 'native log\nHDC_LOG ExecuteCommand: hilog -x; printf "\\n' + self.marker + '%s\\n" "$rc"'
        self.assertEqual(command_exit(body+'\n'+self.marker+'0\n', self.marker), (body,0))

    def test_empty_body_and_original_body_newlines(self):
        for body in ['', 'payload', 'payload\n', '\n\npayload\n\n']:
            with self.subTest(body=body):
                self.assertEqual(command_exit(body+'\n'+self.marker+'0\n',self.marker),(body,0))

    def test_reject_duplicate_real_records_echo_only_wrong_nonce_and_trailing_data(self):
        valid = 'payload\n'+self.marker+'0\n'
        other = self.marker.replace('a'*32,'b'*32)
        bad = [self.marker+'0\n', valid+'\n', valid+'late output\n',valid.rstrip('\n'),
               valid+' ', valid+valid, self.marker+'1\n'+valid,
               valid.replace(self.marker,other), 'ExecuteCommand printf "'+self.marker+'%s"',
               valid.replace(self.marker+'0',self.marker+'256'),
               valid.replace(self.marker+'0',self.marker+'-1')]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                command_exit(raw,self.marker)

    def test_crlf_is_normalized_without_stripping_body_or_accepting_bare_cr_footer(self):
        self.assertEqual(command_exit('payload\r\n\r\n'+self.marker+'0\r\n',self.marker),('payload\n',0))
        with self.assertRaises(ValueError): command_exit('payload\n'+self.marker+'0\r',self.marker)

    def test_nonzero_is_a_real_decoded_exit_but_ui_never_accepts_it(self):
        self.assertEqual(command_exit('actual failure\n'+self.marker+'7\n',self.marker),('actual failure',7))
        with tempfile.TemporaryDirectory() as work:
            def command(argv,label):
                marker = re.search(r'__UITEST_EXIT_[a-f0-9]{32}__=',argv[4])[0]
                return 'actual failure\n'+marker+'7\n'
            with self.assertRaises(GuestUiCommandError) as error:
                GuestUi(command,'fixture','fixture',work).shell('false','failed')
            self.assertEqual(error.exception.exit_code,7)
            self.assertEqual(error.exception.output,'actual failure')

    def test_ui_and_pure_parser_retain_identical_embedded_echo_body(self):
        with tempfile.TemporaryDirectory() as work:
            captured = []
            def command(argv,label):
                marker = re.search(r'__UITEST_EXIT_[a-f0-9]{32}__=',argv[4])[0]
                body = 'hilog: ExecuteCommand printf "\\n'+marker+'%s\\n"'
                raw=body+'\n'+marker+'0\n';captured.append((raw,marker,body));return raw
            value=GuestUi(command,'fixture','fixture',work).shell('hilog -x','logs')
            self.assertEqual(value,captured[0][2])
            self.assertEqual(command_exit(*captured[0][:2]),(value,0))

    def test_invalid_marker_shapes_are_not_protocols(self):
        for marker in ['wrong','__UITEST_EXIT_'+'a'*31+'__=',self.marker+'x']:
            with self.subTest(marker=marker),self.assertRaises(ValueError):command_exit('\n'+marker+'0\n',marker)


if __name__ == '__main__': unittest.main()
