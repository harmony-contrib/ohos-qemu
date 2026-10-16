/* Passive real-HDI observer. Never starts, stops, cancels or changes vibration. */
#include "v2_0/ivibrator_interface.h"
#include <cerrno>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <time.h>
#include <unistd.h>
using namespace OHOS::HDI::Vibrator::V2_0;

static bool Now(unsigned long long &ns)
{
    timespec value {};
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0 || value.tv_sec < 0 || value.tv_nsec < 0 ||
        value.tv_nsec >= 1000000000 || static_cast<unsigned long long>(value.tv_sec) > ULLONG_MAX / 1000000000ULL) return false;
    const auto seconds = static_cast<unsigned long long>(value.tv_sec) * 1000000000ULL;
    if (seconds > ULLONG_MAX - static_cast<unsigned long long>(value.tv_nsec)) return false;
    ns = seconds + static_cast<unsigned long long>(value.tv_nsec);
    return true;
}

static bool Number(const char *input, unsigned long &value)
{
    const std::string text(input);
    if (text.empty() || text.size() > 5 || text.find_first_not_of("0123456789") != std::string::npos) return false;
    errno = 0;
    char *end = nullptr;
    value = std::strtoul(input, &end, 10);
    return errno == 0 && end != nullptr && *end == '\0';
}

int main(int argc, char **argv)
{
    if (argc != 4 || getuid() != 0 || geteuid() != 0) return 2;
    const std::string run(argv[1]);
    unsigned long duration = 0, period = 0;
    if (run.size() != 32 || run.find_first_not_of("0123456789abcdef") != std::string::npos ||
        !Number(argv[2], duration) || duration < 100 || duration > 60000 ||
        !Number(argv[3], period) || period < 5 || period > 100 || period >= duration) return 2;
    std::ifstream input("/proc/sys/kernel/random/boot_id");
    std::string boot;
    if (!std::getline(input, boot) || boot.size() != 36 || boot.find_first_not_of("0123456789abcdef-") != std::string::npos) return 1;
    auto driver = IVibratorInterface::Get();
    if (driver == nullptr) return 1;
    const DeviceVibratorInfo device {0, 0};
    HapticCapacity capacity {};
    unsigned long long before = 0, after = 0;
    if (!Now(before)) return 1;
    const int32_t result = driver->GetHapticCapacity(device, capacity);
    if (!Now(after) || after < before) return 1;
    std::printf("{\"schema_version\":1,\"kind\":\"begin\",\"run_id\":\"%s\",\"boot_id\":\"%s\","
        "\"device_id\":0,\"vibrator_id\":0,\"uid\":%u,\"duration_ms\":%lu,\"period_ms\":%lu,"
        "\"before_ns\":%llu,\"after_ns\":%llu,\"result\":%d,",
        run.c_str(), boot.c_str(), static_cast<unsigned>(getuid()), duration, period, before, after, result);
    if (result == 0) {
        std::printf("\"time_delay\":%s,\"hd_haptic\":%s,\"preset_mapping\":%s}\n",
            capacity.isSupportTimeDelay ? "true" : "false", capacity.isSupportHdHaptic ? "true" : "false",
            capacity.isSupportPresetMapping ? "true" : "false");
    } else {
        std::printf("\"time_delay\":null,\"hd_haptic\":null,\"preset_mapping\":null}\n");
    }
    if (std::fflush(stdout) != 0 || result != 0 || !capacity.isSupportTimeDelay) return 1;
    const auto began = after;
    unsigned long count = 0;
    while (true) {
        bool running = false;
        if (!Now(before) || before < began) return 1;
        const int32_t status = driver->IsVibratorRunning(device, running);
        if (!Now(after) || after < before) return 1;
        std::printf("{\"schema_version\":1,\"kind\":\"sample\",\"run_id\":\"%s\",\"boot_id\":\"%s\","
            "\"sequence\":%lu,\"before_ns\":%llu,\"after_ns\":%llu,\"result\":%d,\"running\":",
            run.c_str(), boot.c_str(), ++count, before, after, status);
        if (status == 0) std::printf("%s", running ? "true" : "false");
        else std::printf("null"); // An RPC error is not a false/running observation.
        std::printf("}\n");
        if (std::fflush(stdout) != 0 || status != 0) return 1;
        if (after - began >= duration * 1000000ULL) break;
        timespec remaining {static_cast<time_t>(period / 1000), static_cast<long>(period % 1000 * 1000000UL)};
        while (nanosleep(&remaining, &remaining) != 0) if (errno != EINTR) return 1;
    }
    std::printf("{\"schema_version\":1,\"kind\":\"complete\",\"run_id\":\"%s\",\"boot_id\":\"%s\",\"samples\":%lu}\n",
        run.c_str(), boot.c_str(), count);
    return std::fflush(stdout) == 0 && !std::ferror(stdout) ? 0 : 1;
}
