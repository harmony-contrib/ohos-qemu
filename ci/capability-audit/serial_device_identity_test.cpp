// Actual production helper with controlled stat syscall boundaries.
// This unit fixture is not a simulated HDI/service or runtime acceptance.
#include "serial_device_identity.h"
#include <cassert>
#include <cerrno>
#include <iostream>

namespace {
struct stat device = {};
struct stat sysfs = {};
int deviceError = 0;
int sysfsError = 0;
unsigned calls = 0;
constexpr const char* PORT = "ttyUSB0";
constexpr const char* KEY_PREFIX = "0403_6001_FTDI_ttyUSB0#attachment-";
constexpr unsigned EXPECTED_STAT_CALLS = 2;
} // namespace

extern "C" int __wrap_stat(const char* path, struct stat* result) {
    ++calls;
    std::string input(path);
    bool isDevice = input.compare(0, std::string("/dev/").size(), "/dev/") == 0;
    assert(input == "/dev/ttyUSB0" || input == "/sys/class/tty/ttyUSB0/device");
    int error = isDevice ? deviceError : sysfsError;
    if (error != 0) {
        errno = error;
        return -1;
    }
    *result = isDevice ? device : sysfs;
    return 0;
}

void PrepareMetadata() {
    using namespace OHOS::Serial;
    device.st_mode = S_IFCHR;
    device.st_dev = 1;
    device.st_ino = 1;
    device.st_rdev = 1;
    device.st_ctim.tv_sec = 1;
    sysfs.st_mode = S_IFDIR;
    sysfs.st_ino = 1;
    sysfs.st_ctim.tv_sec = 1;
}

void VerifyReplacement(const std::string& original) {
    using namespace OHOS::Serial;
    assert(SerialAttachmentMatches(PORT, original));
    ++device.st_ino;
    assert(!SerialAttachmentMatches(PORT, original));
    --device.st_ino;
    ++device.st_ctim.tv_nsec;
    assert(!SerialAttachmentMatches(PORT, original));
    --device.st_ctim.tv_nsec;
    ++sysfs.st_ino;
    assert(!SerialAttachmentMatches(PORT, original));
    --sysfs.st_ino;
    ++sysfs.st_ctim.tv_nsec;
    assert(!SerialAttachmentMatches(PORT, original));
    --sysfs.st_ctim.tv_nsec;
}

void VerifyMissingAndTypes(const std::string& original) {
    using namespace OHOS::Serial;
    for (int error : { ENOENT, EACCES, EIO }) {
        deviceError = error;
        assert(!SerialAttachmentMatches(PORT, original));
        deviceError = 0;
        sysfsError = error;
        assert(!SerialAttachmentMatches(PORT, original));
        sysfsError = 0;
    }
    device.st_mode = S_IFREG;
    assert(!SerialAttachmentMatches(PORT, original));
    device.st_mode = S_IFCHR;
    sysfs.st_mode = S_IFREG;
    assert(!SerialAttachmentMatches(PORT, original));
    sysfs.st_mode = S_IFDIR;
}

int main() {
    using namespace OHOS::Serial;
    PrepareMetadata();
    std::string identity;
    assert(ReadSerialAttachmentIdentity(PORT, identity));
    assert(calls == EXPECTED_STAT_CALLS);
    std::string original = KEY_PREFIX + identity;
    VerifyReplacement(original);
    VerifyMissingAndTypes(original);
    assert(!SerialAttachmentMatches(PORT, "0403_6001_ttyUSB0"));
    assert(!SerialAttachmentMatches(PORT, original + "suffix"));
    assert(IsSerialUsbAttachment("ttyACM123"));
    for (const char* invalid : { "ttyUSB", "ttyUSB-1", "ttyUSB0/../ttyAMA0", "/dev/ttyUSB0", "ttyS0", "ttyAMA0" }) {
        identity = "preserve-on-failure";
        calls = 0;
        assert(!ReadSerialAttachmentIdentity(invalid, identity));
        assert(identity == "preserve-on-failure" && calls == 0);
    }
    std::cout << "PASS actual attachment helper: node/sysfs absence, replacement, permissions, path isolation\n";
}
