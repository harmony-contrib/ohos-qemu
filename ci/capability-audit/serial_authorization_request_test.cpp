#include "serial_authorization_request.h"
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <iostream>

namespace {
enum class RandomMode { Real,
    InterruptedThenShort,
    Unavailable,
    ZeroRead };
RandomMode mode = RandomMode::Real;
size_t calls = 0;
constexpr size_t SHORT_READ_BYTES = 7;
constexpr uint8_t TEST_RANDOM_BYTE = 0xAB;
constexpr size_t HEX_CHARACTERS_PER_BYTE = 2;
constexpr size_t SECOND_RANDOM_CALL = 2;
constexpr const char* DEVICE = "0403_6001_QEMU_ttyUSB0";
}

extern "C" ssize_t __real_getrandom(void* buffer, size_t length, unsigned int flags);

extern "C" ssize_t __wrap_getrandom(void* buffer, size_t length, unsigned int flags) {
    if (flags != GRND_NONBLOCK) {
        std::abort();
    }
    ++calls;
    if (mode == RandomMode::Real) {
        return __real_getrandom(buffer, length, flags);
    }
    if (mode == RandomMode::Unavailable) {
        errno = EAGAIN;
        return -1;
    }
    if (mode == RandomMode::ZeroRead) {
        return 0;
    }
    if (calls == 1) {
        errno = EINTR;
        return -1;
    }
    size_t count = calls == SECOND_RANDOM_CALL ? SHORT_READ_BYTES : length;
    std::memset(buffer, TEST_RANDOM_BYTE, count);
    return static_cast<ssize_t>(count);
}

bool CheckRealRandom() {
    const std::string prefix = std::string(DEVICE) + "#request-";
    const size_t expectedLength = prefix.size() + OHOS::Serial::SERIAL_AUTHORIZATION_NONCE_BYTES * HEX_CHARACTERS_PER_BYTE;
    std::string first;
    std::string second;
    return OHOS::Serial::BuildSerialAuthorizationRequestId(DEVICE, first) && OHOS::Serial::BuildSerialAuthorizationRequestId(DEVICE, second) && first != second && first.find(prefix) == 0 && second.find(prefix) == 0 && first.size() == expectedLength && second.size() == expectedLength;
}

bool CheckFailure(RandomMode selected) {
    mode = selected;
    calls = 0;
    std::string request = "unchanged";
    return !OHOS::Serial::BuildSerialAuthorizationRequestId(DEVICE, request) && request == "unchanged" && calls == 1;
}

int main() {
    if (!CheckRealRandom() || !CheckFailure(RandomMode::Unavailable) || !CheckFailure(RandomMode::ZeroRead)) {
        return EXIT_FAILURE;
    }
    mode = RandomMode::InterruptedThenShort;
    calls = 0;
    std::string request;
    if (!OHOS::Serial::BuildSerialAuthorizationRequestId(DEVICE, request) || request != std::string(DEVICE) + "#request-abababababababababababababababab") {
        return EXIT_FAILURE;
    }
    calls = 0;
    request = "unchanged";
    if (OHOS::Serial::BuildSerialAuthorizationRequestId("", request) || request != "unchanged" || calls != 0) {
        return EXIT_FAILURE;
    }
    std::cout << "PASS actual request helper: real host entropy + controlled EINTR/short/zero/EAGAIN boundaries;"
                 " not product/runtime acceptance"
              << std::endl;
    return EXIT_SUCCESS;
}
