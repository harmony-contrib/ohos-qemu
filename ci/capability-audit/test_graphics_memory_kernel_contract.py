import unittest

from graphics_memory_kernel_contract import verify_samples

HEADER = 'Dma-buf objects usage of processes:\nProcess pid fd size_bytes ino exp_pid exp_task_comm buf_name exp_name\n'


def table(inodes):
    return HEADER + ''.join(f'audit 2134 {index + 5} 16777216 {inode} 0 audit NULL virtio_gpu\n'
                            for index, inode in enumerate(inodes))


class GraphicsMemoryKernelTests(unittest.TestCase):
    def test_real_inode_lifecycle_and_duplicate_fds(self):
        samples = [table(values) for values in ([], [25, 25], [25], [25, 26], [26], [], [])]
        result = verify_samples(samples, 2134, [16384, 16384])
        self.assertEqual(result['inodes'], [25, 26])
        self.assertEqual(result['closed'], [])

    def test_missing_restoration_allocation_or_foreign_process_fails(self):
        for values in (([], [25], [25, 26], [26]), ([], [25], []),
                       ([], [25], [25, 26], [25], []), ([], [25], [25, 26], [27], [])):
            with self.assertRaises(ValueError):
                verify_samples([table(row) for row in values], 2134, [16384, 16384])
        with self.assertRaises(ValueError):
            verify_samples([table(row) for row in ([], [25], [25, 26], [26], [])], 2135, [16384, 16384])

    def test_geometry_and_changed_inode_size_fail(self):
        samples = [table(row) for row in ([], [25], [25, 26], [26], [])]
        with self.assertRaises(ValueError):
            verify_samples(samples, 2134, [32768, 16384])
        samples[2] = samples[2].replace('16777216', '33554432')
        with self.assertRaises(ValueError):
            verify_samples(samples, 2134, [16384, 16384])

    def test_stable_preexisting_buffers_are_not_counted_as_test_allocations(self):
        samples = [table(row) for row in ([10], [10, 25], [10, 25, 26], [10, 26], [10])]
        self.assertEqual(verify_samples(samples, 2134, [16384, 16384])['baseline_inodes'], [10])
        samples[-1] = table([])
        with self.assertRaises(ValueError):
            verify_samples(samples, 2134, [16384, 16384])
