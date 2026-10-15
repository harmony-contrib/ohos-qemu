"""Exercise actual SCM_RIGHTS and verify rejected messages leak no descriptors."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HEADERS = ROOT / 'patches/common/foundation/communication/netmanager_ext/openvpn_backend/files'


class ReceivedDescriptorTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith('linux'), 'SCM_RIGHTS truncation semantics must be checked on the target Linux kernel')
    def test_real_ancillary_single_extra_truncated_and_bad_payload(self):
        source = r'''
#include "received_descriptor.h"
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <fcntl.h>
int Count() {
 int result = 0;
 for (int fd = 0; fd < 512; ++fd) if (fcntl(fd, F_GETFD) >= 0) ++result;
 return result;
}
int main() {
 int sockets[2], pipefd[2];
 assert(socketpair(AF_UNIX, SOCK_DGRAM, 0, sockets) == 0);
 assert(pipe(pipefd) == 0);
 int baseline = Count();
 for (int repeat = 0; repeat < 64; ++repeat) {
  for (int count : {1, 2, 4, 8}) for (int payload : {1, 2}) {
   alignas(cmsghdr) char outgoing[CMSG_SPACE(8 * sizeof(int))] {};
   char bytes[] = "RR"; iovec data {bytes, static_cast<size_t>(payload)};
   msghdr sent {}; sent.msg_iov = &data; sent.msg_iovlen = 1;
   sent.msg_control = outgoing; sent.msg_controllen = CMSG_SPACE(count * sizeof(int));
   auto *header = CMSG_FIRSTHDR(&sent);
   header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
   header->cmsg_len = CMSG_LEN(count * sizeof(int));
   for (int i = 0; i < count; ++i) memcpy(reinterpret_cast<char *>(CMSG_DATA(header)) + i * sizeof(int), pipefd, sizeof(int));
   assert(sendmsg(sockets[0], &sent, 0) == payload);
   alignas(cmsghdr) char incoming[CMSG_SPACE(4 * sizeof(int))] {};
   char byte = 0; iovec target {&byte, 1}; msghdr received {};
   received.msg_iov = &target; received.msg_iovlen = 1;
   received.msg_control = incoming; received.msg_controllen = sizeof(incoming);
   int flags = 0;
#ifdef MSG_CMSG_CLOEXEC
   flags = MSG_CMSG_CLOEXEC;
#endif
   ssize_t size = recvmsg(sockets[1], &received, flags);
   assert(size >= 0);
   int fd = OhosOpenvpn::TakeSingleDescriptor(received, size, sizeof(incoming));
   if (count == 1 && payload == 1) {
    assert(fd >= 0);
#ifdef MSG_CMSG_CLOEXEC
    assert(fcntl(fd, F_GETFD) & FD_CLOEXEC);
#endif
    assert(write(pipefd[1], "x", 1) == 1);
    assert(read(fd, &byte, 1) == 1 && byte == 'x');
    close(fd);
   } else assert(fd == -1);
   if (Count() != baseline) {
    fprintf(stderr, "repeat=%d count=%d payload=%d flags=%d control=%zu baseline=%d actual=%d\\n",
      repeat, count, payload, received.msg_flags, static_cast<size_t>(received.msg_controllen), baseline, Count());
    return 1;
   }
  }
 }
 close(pipefd[0]); close(pipefd[1]); close(sockets[0]); close(sockets[1]);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            cpp, binary = directory / 'probe.cpp', directory / 'probe'
            cpp.write_text(source)
            compiled = subprocess.run([os.environ.get('CXX', 'clang++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-I', str(HEADERS),
                str(cpp), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(ran.returncode, 0, ran.stderr)


if __name__ == '__main__':
    unittest.main()
