#pragma once
#include <algorithm>
#include <array>
#include <cstring>
#include <sys/socket.h>
#include <unistd.h>

namespace OhosOpenvpn {
// recvmsg has already installed every delivered descriptor in this process.
// Rejecting extra/truncated ancillary data must close those descriptors too.
inline int TakeSingleDescriptor(msghdr &message, ssize_t received, size_t capacity)
{
    std::array<int, 4> descriptors {};
    size_t count = 0;
    bool valid = received == 1 && !(message.msg_flags & (MSG_CTRUNC | MSG_TRUNC));
    if (!message.msg_control || capacity < CMSG_LEN(0)) return -1;
    msghdr bounded = message;
    bounded.msg_controllen = std::min(static_cast<size_t>(message.msg_controllen), capacity);
    if (message.msg_controllen > capacity) valid = false;
    auto *end = static_cast<unsigned char *>(bounded.msg_control) + bounded.msg_controllen;
    for (auto *header = CMSG_FIRSTHDR(&bounded); header; header = CMSG_NXTHDR(&bounded, header)) {
        size_t available = end - reinterpret_cast<unsigned char *>(header);
        if (available < CMSG_LEN(0) || header->cmsg_len < CMSG_LEN(0)) {
            valid = false;
            break;
        }
        if (header->cmsg_level != SOL_SOCKET || header->cmsg_type != SCM_RIGHTS ||
            (header->cmsg_len - CMSG_LEN(0)) % sizeof(int)) {
            valid = false;
            continue;
        }
        // Some kernels retain the original cmsg_len on MSG_CTRUNC. Only the
        // descriptors actually present in the supplied buffer were delivered.
        if (header->cmsg_len > available) valid = false;
        size_t bytes = std::min(static_cast<size_t>(header->cmsg_len), available) - CMSG_LEN(0);
        bytes -= bytes % sizeof(int);
        for (size_t offset = 0; offset < bytes; offset += sizeof(int)) {
            int fd = -1;
            memcpy(&fd, reinterpret_cast<char *>(CMSG_DATA(header)) + offset, sizeof(fd));
            if (count < descriptors.size()) descriptors[count++] = fd;
            else { close(fd); valid = false; }
        }
    }
    if (valid && count == 1) return descriptors[0];
    for (size_t i = 0; i < count; ++i) close(descriptors[i]);
    return -1;
}
} // namespace OhosOpenvpn
