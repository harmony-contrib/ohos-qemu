#include "serial_token_id.h"
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>

int main() {
    constexpr uint32_t UNCHANGED = 123;
    constexpr uint32_t FIRST_UNSIGNED_ONLY_TOKEN = 2147483648U;
    uint32_t token = UNCHANGED;
    if (!OHOS::Serial::ParseSerialTokenId("2147483648", token) || token != FIRST_UNSIGNED_ONLY_TOKEN || !OHOS::Serial::ParseSerialTokenId("4294967295", token) || token != std::numeric_limits<uint32_t>::max()) {
        return EXIT_FAILURE;
    }
    for (const char* invalid : { "", "0", "0001", "-1", "+1", " 1", "1 ", "1x", "4294967296",
             "18446744073709551616" }) {
        token = UNCHANGED;
        if (OHOS::Serial::ParseSerialTokenId(invalid, token) || token != UNCHANGED) {
            std::cerr << "invalid token accepted or output modified: " << invalid << std::endl;
            return EXIT_FAILURE;
        }
    }
    std::cout << "PASS actual candidate token parser; host helper only, not product/runtime acceptance" << std::endl;
    return EXIT_SUCCESS;
}
