/* Copyright (c) 2026 OpenHarmony contributors.
 * Licensed under the Apache License, Version 2.0; see
 * http://www.apache.org/licenses/LICENSE-2.0
 * Distributed on an AS IS BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
 */
#include "qemu_mtp_functionfs.h"
#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <endian.h>
#include <fcntl.h>
#include <limits>
#include <linux/usb/ch9.h>
#include <linux/usb/functionfs.h>
#include <poll.h>
#include <sys/eventfd.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <unistd.h>

namespace OHOS::HDI::Usb::Gadget::Mtp::V1_0 {
namespace {
constexpr long FUNCTIONFS_SUPER_MAGIC = 0x0a647361;
constexpr char DIRECTORY[] = "/dev/usb-ffs/mtp";
constexpr size_t CHUNK = 16384;
constexpr int CANCELLED = -20; // Existing HDI MTP cancellation return contract.
struct __attribute__((packed)) Set {
    usb_interface_descriptor interface;
    usb_endpoint_descriptor_no_audio in, out, interrupt;
};
struct __attribute__((packed)) Descriptors {
    usb_functionfs_descs_head_v2 head;
    uint32_t fsCount, hsCount;
    Set fs, hs;
};
Set EndpointSet(uint16_t packet)
{
    Set value{};
    value.interface.bLength = sizeof(value.interface); value.interface.bDescriptorType = USB_DT_INTERFACE;
    value.interface.bNumEndpoints = 3; value.interface.bInterfaceClass = USB_CLASS_STILL_IMAGE;
    value.interface.bInterfaceSubClass = 1; value.interface.bInterfaceProtocol = 1; value.interface.iInterface = 1;
    value.in.bLength = sizeof(value.in); value.in.bDescriptorType = USB_DT_ENDPOINT;
    value.in.bEndpointAddress = USB_DIR_IN | 1; value.in.bmAttributes = USB_ENDPOINT_XFER_BULK;
    value.in.wMaxPacketSize = htole16(packet); value.out = value.in; value.out.bEndpointAddress = USB_DIR_OUT | 2;
    value.interrupt = value.in; value.interrupt.bEndpointAddress = USB_DIR_IN | 3;
    value.interrupt.bmAttributes = USB_ENDPOINT_XFER_INT; value.interrupt.wMaxPacketSize = htole16(28);
    value.interrupt.bInterval = 6;
    return value;
}
int Describe(int fd)
{
    Descriptors value{};
    value.head.magic = htole32(FUNCTIONFS_DESCRIPTORS_MAGIC_V2); value.head.length = htole32(sizeof(value));
    value.head.flags = htole32(FUNCTIONFS_HAS_FS_DESC | FUNCTIONFS_HAS_HS_DESC);
    value.fsCount = value.hsCount = htole32(4); value.fs = EndpointSet(64); value.hs = EndpointSet(512);
    if (write(fd, &value, sizeof(value)) != static_cast<ssize_t>(sizeof(value))) return -errno;
    constexpr char NAME[] = "OpenHarmony Media Transfer Protocol";
    std::array<uint8_t, sizeof(usb_functionfs_strings_head) + sizeof(uint16_t) + sizeof(NAME)> data{};
    usb_functionfs_strings_head header{htole32(FUNCTIONFS_STRINGS_MAGIC), htole32(data.size()), htole32(1), htole32(1)};
    uint16_t language = htole16(0x0409); memcpy(data.data(), &header, sizeof(header));
    memcpy(data.data() + sizeof(header), &language, sizeof(language));
    memcpy(data.data() + sizeof(header) + sizeof(language), NAME, sizeof(NAME));
    return write(fd, data.data(), data.size()) == static_cast<ssize_t>(data.size()) ? 0 : -errno;
}
struct FdCloser { int fd; ~FdCloser() { if (fd >= 0) close(fd); } };
struct Busy { std::atomic<bool> &value; explicit Busy(std::atomic<bool> &v) : value(v) { value.store(true); } ~Busy() { value.store(false); } };
int WriteFile(int fd, const uint8_t *data, size_t size, int64_t offset)
{
    size_t done = 0;
    while (done < size) {
        ssize_t count = pwrite(fd, data + done, size - done, offset + static_cast<int64_t>(done));
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) return count < 0 ? -errno : -EIO;
        done += static_cast<size_t>(count);
    }
    return 0;
}
} // namespace
QemuMtpFunctionFS::~QemuMtpFunctionFS() { (void)Stop(); }
void QemuMtpFunctionFS::CloseDescriptors()
{
    for (int *fd : {&interrupt_, &out_, &in_, &ep0_, &wake_}) { if (*fd >= 0) close(*fd); *fd = -1; }
}
int32_t QemuMtpFunctionFS::Start()
{
    std::lock_guard<std::mutex> life(lifecycle_); std::unique_lock<std::shared_mutex> active(active_);
    if (!stopping_.load()) return 0;
    struct stat st{}; struct statfs fs{};
    if (lstat(DIRECTORY, &st) != 0 || !S_ISDIR(st.st_mode) || st.st_uid != 0 ||
        statfs(DIRECTORY, &fs) != 0 || fs.f_type != FUNCTIONFS_SUPER_MAGIC) return -ENODEV;
    wake_ = eventfd(0, EFD_NONBLOCK | EFD_CLOEXEC);
    ep0_ = open("/dev/usb-ffs/mtp/ep0", O_RDWR | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
    int status = ep0_ < 0 || wake_ < 0 ? -errno : Describe(ep0_);
    if (status == 0) {
        in_ = open("/dev/usb-ffs/mtp/ep1", O_RDWR | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
        out_ = open("/dev/usb-ffs/mtp/ep2", O_RDWR | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
        interrupt_ = open("/dev/usb-ffs/mtp/ep3", O_RDWR | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
        if (in_ < 0 || out_ < 0 || interrupt_ < 0) status = -errno;
    }
    if (status != 0) { CloseDescriptors(); return status; }
    cancelled_.store(false); enabled_.store(false); stopping_.store(false);
    control_ = std::thread(&QemuMtpFunctionFS::Control, this);
    return 0;
}
int32_t QemuMtpFunctionFS::Stop()
{
    std::lock_guard<std::mutex> life(lifecycle_);
    stopping_.store(true); generation_.fetch_add(1); enabled_.store(false);
    uint64_t one = 1; if (wake_ >= 0) (void)write(wake_, &one, sizeof(one));
    if (control_.joinable()) control_.join();
    std::unique_lock<std::shared_mutex> active(active_); CloseDescriptors();
    cancelled_.store(false); busy_.store(false); return 0;
}
int QemuMtpFunctionFS::Poll(int fd, short events, uint64_t generation, int timeoutMs)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeoutMs);
    while (!stopping_.load()) {
        if (std::chrono::steady_clock::now() >= deadline) return -ETIMEDOUT;
        if (cancelled_.load()) return CANCELLED;
        if (generation_.load() != generation) return -ENODEV;
        if (!enabled_.load()) { std::this_thread::sleep_for(std::chrono::milliseconds(50)); continue; }
        pollfd row{fd, events, 0}; int result = poll(&row, 1, 100);
        if (result < 0 && errno == EINTR) continue;
        if (result < 0) return -errno;
        if (row.revents & events) return 0;
        if (row.revents & (POLLHUP | POLLERR | POLLNVAL)) return -ENODEV;
    }
    return -ENODEV;
}
int QemuMtpFunctionFS::Send(int fd, const uint8_t *data, size_t size, uint64_t generation)
{
    size_t done = 0;
    do {
        int status = Poll(fd, POLLOUT, generation); if (status != 0) return status;
        ssize_t count = write(fd, data == nullptr ? nullptr : data + done, size - done);
        if (count < 0 && (errno == EINTR || errno == EAGAIN)) continue;
        if (count < 0 || (count == 0 && size != 0)) return count < 0 ? -errno : -EIO;
        done += static_cast<size_t>(count);
        if (size == 0) break;
    } while (done < size);
    return 0;
}
int32_t QemuMtpFunctionFS::Read(std::vector<uint8_t> &data)
{
    std::shared_lock<std::shared_mutex> active(active_); std::lock_guard<std::mutex> readLock(read_);
    const uint64_t generation = generation_.load(); data.resize(10240);
    while (true) {
        // The original MtpMonitor joins after changing its own running flag.
        // A bounded idle read lets that normal join reach CloseDriver/HDI Stop.
        int status = Poll(out_, POLLIN, generation, 1000); if (status != 0) { data.clear(); return status; }
        ssize_t count = read(out_, data.data(), data.size());
        if (count < 0 && (errno == EINTR || errno == EAGAIN)) continue;
        if (count < 0) { data.clear(); return -errno; }
        data.resize(static_cast<size_t>(count)); return count > 0 ? 0 : -ENODEV;
    }
}
int32_t QemuMtpFunctionFS::Write(const std::vector<uint8_t> &data)
{
    if (data.empty()) return -EINVAL;
    std::shared_lock<std::shared_mutex> active(active_); std::lock_guard<std::mutex> writeLock(write_);
    Busy busy(busy_); uint64_t generation = generation_.load();
    int status = Send(in_, data.data(), data.size(), generation);
    if (status == 0 && data.size() % packet_.load() == 0) status = Send(in_, nullptr, 0, generation);
    return status;
}
int32_t QemuMtpFunctionFS::ReceiveFile(const UsbFnMtpFileSlice &file)
{
    FdCloser closeFile{file.fd};
    if (file.fd < 0 || file.offset < 0 || file.length < 0) return -EINVAL;
    std::shared_lock<std::shared_mutex> active(active_); std::lock_guard<std::mutex> readLock(read_);
    Busy busy(busy_); uint64_t generation = generation_.load(), done = 0;
    const bool unlimited = static_cast<uint64_t>(file.length) == 0xffffffffULL;
    std::array<uint8_t, CHUNK> buffer{};
    while (unlimited || done < static_cast<uint64_t>(file.length)) {
        size_t wanted = unlimited ? buffer.size() : std::min<uint64_t>(buffer.size(), static_cast<uint64_t>(file.length) - done);
        int status = Poll(out_, POLLIN, generation);
        // Preserve the existing real MediaLibrary ReceiveObj HDI contract:
        // -20 triggers its owned partial-object unlink/database cleanup and
        // suppresses the cancelled transaction response; -17 is disconnect.
        if (status != 0) return status == CANCELLED ? CANCELLED : -17;
        ssize_t count = read(out_, buffer.data(), wanted);
        if (count < 0 && (errno == EINTR || errno == EAGAIN)) continue;
        if (count < 0) return -errno;
        if (count == 0) return unlimited ? (fsync(file.fd) == 0 ? 0 : -errno) : -EIO;
        status = WriteFile(file.fd, buffer.data(), static_cast<size_t>(count), file.offset + static_cast<int64_t>(done));
        if (status != 0) return status;
        done += static_cast<uint64_t>(count);
        if (unlimited && static_cast<size_t>(count) < wanted) break;
    }
    return fsync(file.fd) == 0 ? 0 : -errno;
}
int32_t QemuMtpFunctionFS::SendFile(const UsbFnMtpFileSlice &file)
{
    FdCloser closeFile{file.fd};
    if (file.fd < 0 || file.offset < 0 || file.length < 0) return -EINVAL;
    std::shared_lock<std::shared_mutex> active(active_); std::lock_guard<std::mutex> writeLock(write_);
    Busy busy(busy_); uint64_t generation = generation_.load(), done = 0;
    std::array<uint8_t, CHUNK> buffer{}; size_t header = file.command == 0 && file.transactionId == 0 ? 0 : 12;
    if (header != 0) {
        uint64_t total = static_cast<uint64_t>(file.length) + header;
        uint32_t length = htole32(static_cast<uint32_t>(std::min<uint64_t>(total, 0xffffffffULL)));
        uint16_t kind = htole16(2), code = htole16(file.command); uint32_t id = htole32(file.transactionId);
        memcpy(buffer.data(), &length, 4); memcpy(buffer.data() + 4, &kind, 2);
        memcpy(buffer.data() + 6, &code, 2); memcpy(buffer.data() + 8, &id, 4);
    }
    const uint64_t total = static_cast<uint64_t>(file.length) + header;
    bool first = true;
    while (first || done < static_cast<uint64_t>(file.length)) {
        size_t prefix = first ? header : 0;
        size_t wanted = std::min<uint64_t>(buffer.size() - prefix, static_cast<uint64_t>(file.length) - done);
        size_t loaded = 0;
        while (loaded < wanted) {
            ssize_t count = pread(file.fd, buffer.data() + prefix + loaded, wanted - loaded, file.offset + static_cast<int64_t>(done + loaded));
            if (count < 0 && errno == EINTR) continue;
            if (count <= 0) return count < 0 ? -errno : -EIO;
            loaded += static_cast<size_t>(count);
        }
        if (prefix + loaded != 0) { int status = Send(in_, buffer.data(), prefix + loaded, generation); if (status != 0) return status; }
        done += loaded; first = false;
    }
    return total != 0 && total % packet_.load() == 0 ? Send(in_, nullptr, 0, generation) : 0;
}
int32_t QemuMtpFunctionFS::SendEvent(const std::vector<uint8_t> &data)
{
    if (data.empty() || data.size() > 28) return -EINVAL;
    std::shared_lock<std::shared_mutex> active(active_); std::lock_guard<std::mutex> eventLock(event_);
    return Send(interrupt_, data.data(), data.size(), generation_.load());
}
void QemuMtpFunctionFS::Setup(uint8_t type, uint8_t request, uint16_t length)
{
    if ((type & USB_TYPE_MASK) == USB_TYPE_CLASS && request == 0x64 && !(type & USB_DIR_IN) && length == 6) {
        std::array<uint8_t, 6> payload{};
        ssize_t size = -1;
        for (unsigned retry = 0; retry < 30 && !stopping_.load(); ++retry) {
            size = read(ep0_, payload.data(), payload.size());
            if (size >= 0 || (errno != EAGAIN && errno != EINTR)) break;
            pollfd row{ep0_, POLLIN, 0}; (void)poll(&row, 1, 50);
        }
        if (size == static_cast<ssize_t>(payload.size()) && payload[0] == 0x01 && payload[1] == 0x40) {
            cancelled_.store(true); generation_.fetch_add(1);
        }
    } else if ((type & USB_TYPE_MASK) == USB_TYPE_CLASS && request == 0x67 && (type & USB_DIR_IN) && length >= 4) {
        uint16_t result[2] = {htole16(4), htole16(cancelled_.load() || busy_.load() ? 0x2019 : 0x2001)};
        (void)write(ep0_, result, sizeof(result));
    } else if ((type & USB_TYPE_MASK) == USB_TYPE_CLASS && request == 0x66 && !(type & USB_DIR_IN) && length == 0) {
        generation_.fetch_add(1); (void)ioctl(in_, FUNCTIONFS_FIFO_FLUSH); (void)ioctl(out_, FUNCTIONFS_FIFO_FLUSH);
        cancelled_.store(false); (void)read(ep0_, nullptr, 0);
    } else {
        if (type & USB_DIR_IN) (void)read(ep0_, nullptr, 0); else (void)write(ep0_, nullptr, 0);
    }
}
void QemuMtpFunctionFS::Control()
{
    while (!stopping_.load()) {
        pollfd rows[2] = {{ep0_, POLLIN, 0}, {wake_, POLLIN, 0}};
        int count = poll(rows, 2, 100); if (count < 0 && errno == EINTR) continue;
        if (count < 0 || rows[1].revents & POLLIN) break;
        if (!(rows[0].revents & POLLIN)) continue;
        usb_functionfs_event event{}; ssize_t size = read(ep0_, &event, sizeof(event));
        if (size < 0 && errno == EAGAIN) continue;
        if (size != static_cast<ssize_t>(sizeof(event))) break;
        if (event.type == FUNCTIONFS_ENABLE) {
            usb_endpoint_descriptor descriptor{};
            if (ioctl(in_, FUNCTIONFS_ENDPOINT_DESC, &descriptor) == 0) {
                uint16_t actual = le16toh(descriptor.wMaxPacketSize) & 0x7ff;
                if (actual == 64 || actual == 512) packet_.store(actual);
            }
            enabled_.store(true);
        } else if (event.type == FUNCTIONFS_DISABLE || event.type == FUNCTIONFS_UNBIND) {
            enabled_.store(false); generation_.fetch_add(1);
        } else if (event.type == FUNCTIONFS_SETUP) {
            Setup(event.u.setup.bRequestType, event.u.setup.bRequest, le16toh(event.u.setup.wLength));
        }
    }
    enabled_.store(false); generation_.fetch_add(1);
}
} // namespace OHOS::HDI::Usb::Gadget::Mtp::V1_0
