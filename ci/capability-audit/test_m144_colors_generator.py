import struct
import unittest

from check_m144_colors_generator import check_graph, check_host_elf


class M144ColorsGeneratorTests(unittest.TestCase):
    def test_real_header_shape_accepts_x86_64_exec_and_pie_only(self):
        for kind in (2, 3):
            header = bytearray(64)
            header[:7] = b'\x7fELF\x02\x01\x01'
            struct.pack_into('<HH', header, 16, kind, 62)
            check_host_elf(header)

    def test_wrong_target_abi_byte_order_or_type_is_rejected(self):
        for kind, machine, elf_class, endian in ((3, 183, 2, 1), (2, 40, 1, 1),
                                                 (1, 62, 2, 1), (3, 62, 2, 2)):
            header = bytearray(64)
            header[:7] = b'\x7fELF' + bytes((elf_class, endian, 1))
            struct.pack_into('<HH', header, 16, kind, machine)
            with self.assertRaises(ValueError):
                check_host_elf(header)
        with self.assertRaises(ValueError):
            check_host_elf(b'not an executable')

    def test_current_graph_keeps_real_host_action_and_rejects_target_or_missing_tool(self):
        label = 'chrome/browser/new_tab_page/chrome_colors/'
        target = ('command = python3 ../../build/gn_run_binary.py clang_x64/generate_colors_info '
                  'gen/' + label + 'generated_colors_info.h\n')
        host = 'subninja clang_x64/obj/' + label + 'generate_colors_info.ninja\n'
        check_graph(target, host)
        for invalid_target, invalid_host in (
                (target + 'subninja obj/' + label + 'generate_colors_info.ninja\n', host),
                (target, ''), ('command = fake_generator\n', host)):
            with self.assertRaises(ValueError):
                check_graph(invalid_target, invalid_host)


if __name__ == '__main__':
    unittest.main()
