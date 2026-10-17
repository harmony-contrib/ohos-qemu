/* SPDX-License-Identifier: Apache-2.0
 * Read-only product-ABI observer. Never starts/stops/cleans a vibration effect.
 * Root builds with actual product proxy, AccessToken and cross-DSO CFI flags.
 */
#include "v2_0/ivibrator_interface.h"
#include "accesstoken_kit.h"
#include <cerrno>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

using namespace OHOS::HDI::Vibrator::V2_0;
using namespace OHOS::Security::AccessToken;

static uint64_t Now(clockid_t clock)
{
    timespec value {};
    if (clock_gettime(clock, &value) != 0 || value.tv_sec < 0) return 0;
    return static_cast<uint64_t>(value.tv_sec) * 1000000000ULL + value.tv_nsec;
}

static bool Hex(const char *value, size_t length)
{
    return strlen(value) == length && strspn(value, "0123456789abcdef") == length;
}

static bool Boot(const char *expected)
{
    char value[64] {};
    FILE *file = fopen("/proc/sys/kernel/random/boot_id", "r");
    if (file == nullptr) return false;
    const bool read = fgets(value, sizeof(value), file) != nullptr;
    fclose(file);
    value[strcspn(value, "\r\n")] = '\0';
    return read && strlen(expected) == 36 && strcmp(value, expected) == 0;
}

static bool Number(const char *text, unsigned long minimum, unsigned long maximum, unsigned long &value)
{
    if (*text == '\0' || strspn(text, "0123456789") != strlen(text)) return false;
    char *end = nullptr;
    errno = 0;
    value = strtoul(text, &end, 10);
    return errno == 0 && end != nullptr && *end == '\0' && value >= minimum && value <= maximum;
}

int main(int argc, char **argv)
{
    if (argc < 4 || getuid() != 0 || geteuid() != 0 || !Hex(argv[2], 32) || !Boot(argv[3])) return 2;
    const char *run = argv[2];
    const char *boot = argv[3];
    if (strcmp(argv[1], "clock") == 0 && argc == 4) {
        const uint64_t before = Now(CLOCK_MONOTONIC), realtime = Now(CLOCK_REALTIME), after = Now(CLOCK_MONOTONIC);
        if (before == 0 || realtime == 0 || after < before) return 1;
        printf("{\"kind\":\"clock\",\"run_id\":\"%s\",\"boot_id\":\"%s\",\"before_ns\":%" PRIu64
            ",\"after_ns\":%" PRIu64 ",\"realtime_ns\":%" PRIu64 "}\n", run, boot, before, after, realtime);
        return 0;
    }
    if (strcmp(argv[1], "token") == 0 && argc == 6) {
        unsigned long uid = 0;
        if (!Number(argv[5], 20010000, 20199999, uid)) return 2;
        const std::string bundle(argv[4]);
        if (bundle != "org.harmonycontrib.audiohapticqa" && bundle != "org.harmonycontrib.audiohapticdenied") return 2;
        const AccessTokenID token = AccessTokenKit::GetHapTokenID(100, bundle, 0);
        HapTokenInfo info {};
        if (token == 0 || AccessTokenKit::GetHapTokenInfo(token, info) != 0 || info.tokenID != token ||
            info.userID != 100 || info.instIndex != 0 || info.bundleName != bundle || info.uid != static_cast<int32_t>(uid)) return 1;
        const uint64_t before = Now(CLOCK_MONOTONIC);
        const int result = AccessTokenKit::VerifyAccessToken(token, "ohos.permission.VIBRATE", true);
        const uint64_t after = Now(CLOCK_MONOTONIC);
        printf("{\"kind\":\"token\",\"run_id\":\"%s\",\"boot_id\":\"%s\",\"bundle\":\"%s\","
            "\"uid\":%lu,\"token_id\":%u,\"VIBRATE\":%d,\"before_ns\":%" PRIu64 ",\"after_ns\":%" PRIu64 "}\n",
            run, boot, bundle.c_str(), uid, token, result, before, after);
        return before > 0 && after >= before && (result == 0 || result == -1) ? 0 : 1;
    }
    if (strcmp(argv[1], "sample") != 0 || argc != 7) return 2;
    unsigned long duration = 0, interval = 0;
    if (!Number(argv[4], 100, 900000, duration) || !Number(argv[5], 1, 50, interval)) return 2;
    const std::string stopFile(argv[6]);
    if (stopFile != "/data/local/tmp/audio-haptic-" + std::string(run) + "/sampler-stop") return 2;
    struct stat entry {};
    if (lstat(stopFile.c_str(), &entry) == 0 || errno != ENOENT) return 2;
    auto driver = IVibratorInterface::Get();
    if (driver == nullptr) return 1;
    const DeviceVibratorInfo device {0, 0};
    printf("{\"kind\":\"begin\",\"run_id\":\"%s\",\"boot_id\":\"%s\",\"pid\":%d,\"uid\":%u,"
        "\"interval_ms\":%lu,\"device_id\":0,\"vibrator_id\":0}\n", run, boot, getpid(), getuid(), interval);
    fflush(stdout);
    const uint64_t began = Now(CLOCK_MONOTONIC);
    uint64_t sequence = 0;
    bool stoppedByOwner = false;
    while (Now(CLOCK_MONOTONIC) - began < duration * 1000000ULL) {
        errno = 0;
        if (lstat(stopFile.c_str(), &entry) == 0) {
            if (!S_ISREG(entry.st_mode) || entry.st_uid != 0 || entry.st_nlink != 1) return 1;
            stoppedByOwner = true;
            break;
        }
        if (errno != ENOENT) return 1;
        const uint64_t before = Now(CLOCK_MONOTONIC), realtime = Now(CLOCK_REALTIME);
        bool running = false;
        const int32_t result = driver->IsVibratorRunning(device, running);
        const uint64_t after = Now(CLOCK_MONOTONIC);
        printf("{\"kind\":\"sample\",\"sequence\":%" PRIu64 ",\"before_ns\":%" PRIu64
            ",\"after_ns\":%" PRIu64 ",\"realtime_ns\":%" PRIu64 ",\"result\":%d,\"running\":%s}\n",
            ++sequence, before, after, realtime, result, result == 0 ? (running ? "true" : "false") : "null");
        fflush(stdout);
        if (result != 0 || before == 0 || after < before || realtime == 0) return 1;
        timespec wait {static_cast<time_t>(interval / 1000), static_cast<long>((interval % 1000) * 1000000)};
        while (nanosleep(&wait, &wait) != 0) { if (errno != EINTR) return 1; }
    }
    if (!Boot(boot)) return 1;
    printf("{\"kind\":\"complete\",\"run_id\":\"%s\",\"boot_id\":\"%s\",\"samples\":%" PRIu64
        ",\"owner_stop\":%s}\n", run, boot, sequence, stoppedByOwner ? "true" : "false");
    return stoppedByOwner && sequence > 0 ? 0 : 1;
}
