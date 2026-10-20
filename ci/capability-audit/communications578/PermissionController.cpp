/* Real platform permission API probe; no token creation or service bypass.
 * argv: RUN32 BOOT36 OP32 TOKEN_ID EXPECTED_BUNDLE TARGET_PID
 * It attempts one fixed permission using killProcess=false. A SYSTEM_FIXED
 * denial is recorded as a denial, never reported as successful revocation.
 */
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <sstream>
#include <string>
#include <unistd.h>
#include "access_token.h"
#include "accesstoken_kit.h"

using namespace OHOS::Security::AccessToken;
namespace {
constexpr const char *PERMISSION = "ohos.permission.GET_NETWORK_INFO";
bool HexId(const std::string &s, size_t length, bool boot)
{
    if (s.size() != length) return false;
    for (size_t i = 0; i < length; ++i) {
        if (boot && (i == 8 || i == 13 || i == 18 || i == 23)) {
            if (s[i] != '-') return false;
        } else if (!((s[i] >= '0' && s[i] <= '9') || (s[i] >= 'a' && s[i] <= 'f'))) return false;
    }
    return true;
}
bool Decimal(const char *text, uint32_t &out)
{
    if (*text == '\0') return false;
    for (const char *p = text; *p; ++p) if (*p < '0' || *p > '9') return false;
    char *end = nullptr; errno = 0;
    unsigned long long value = std::strtoull(text, &end, 10);
    if (errno || *end || value == 0 || value > std::numeric_limits<uint32_t>::max()) return false;
    out = static_cast<uint32_t>(value); return true;
}
uint64_t StartTicks(uint32_t pid)
{
    std::ifstream file("/proc/" + std::to_string(pid) + "/stat");
    std::string raw; if (!std::getline(file, raw)) return 0;
    size_t close = raw.rfind(") "); if (close == std::string::npos) return 0;
    std::istringstream fields(raw.substr(close + 2)); std::string value;
    for (int field = 3; field <= 22; ++field) if (!(fields >> value)) return 0;
    for (char c : value) if (c < '0' || c > '9') return 0;
    errno = 0; unsigned long long number = std::strtoull(value.c_str(), nullptr, 10);
    return errno ? 0 : number;
}
}
int main(int argc, char **argv)
{
    if (argc != 7 || !HexId(argv[1], 32, false) || !HexId(argv[2], 36, true) || !HexId(argv[3], 32, false)) return 64;
    uint32_t token = 0, targetPid = 0;
    if (!Decimal(argv[4], token) || !Decimal(argv[6], targetPid)) return 65;
    std::string bundle = argv[5];
    if (bundle.rfind("org.harmonycontrib.communications578", 0) != 0 || bundle.size() > 160) return 66;
    for (char c : bundle) if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.')) return 66;
    std::ifstream bootFile("/proc/sys/kernel/random/boot_id"); std::string boot;
    if (!std::getline(bootFile, boot) || boot != argv[2]) return 67;
    HapTokenInfo info;
    int infoResult = AccessTokenKit::GetHapTokenInfo(token, info);
    if (infoResult != 0 || info.bundleName != bundle) {
        std::printf("{\"schema\":1,\"kind\":\"identity-rejected\",\"token_info_result\":%d}\n", infoResult);
        return 68;
    }
    uint64_t ticksBefore = StartTicks(targetPid); if (ticksBefore == 0) return 69;
    uint32_t flagBefore = 0, flagAfter = 0, flagFinal = 0;
    int flagResultBefore = AccessTokenKit::GetPermissionFlag(token, PERMISSION, flagBefore);
    int statusBefore = AccessTokenKit::VerifyAccessToken(token, PERMISSION);
    // This is the exact ordinary permission API route. Do not clear SYSTEM_FIXED,
    // write token policy memory, impersonate a native publisher or mint tokens.
    if (flagResultBefore != 0 || statusBefore != PERMISSION_GRANTED || (flagBefore & PERMISSION_SYSTEM_FIXED) == 0) return 70;
    int revoked = AccessTokenKit::RevokePermission(token, PERMISSION, PERMISSION_USER_FIXED, USER_GRANTED_PERM, false);
    int flagResultAfter = AccessTokenKit::GetPermissionFlag(token, PERMISSION, flagAfter);
    int statusAfter = AccessTokenKit::VerifyAccessToken(token, PERMISSION);
    int restoreResult = 0;
    if (flagResultAfter == 0 && (statusAfter != statusBefore || flagAfter != flagBefore)) {
        restoreResult = AccessTokenKit::GrantPermission(token, PERMISSION, flagBefore, USER_GRANTED_PERM);
    }
    int flagResultFinal = AccessTokenKit::GetPermissionFlag(token, PERMISSION, flagFinal);
    int statusFinal = AccessTokenKit::VerifyAccessToken(token, PERMISSION);
    uint64_t ticksAfter = StartTicks(targetPid);
    std::printf("{\"schema\":1,\"kind\":\"fixed-permission-revoke-attempt\",\"run_id\":\"%s\",\"boot_id\":\"%s\","
        "\"operation_id\":\"%s\",\"pid\":%d,\"uid\":%d,\"target_pid\":%u,\"target_token\":%u,"
        "\"bundle\":\"%s\",\"permission\":\"%s\",\"target_start_ticks_before\":%llu,\"target_start_ticks_after\":%llu,"
        "\"kill_process\":false,\"request_flag\":%u,\"update_flag\":%d,\"token_info_result\":%d,"
        "\"flag_result_before\":%d,\"status_before\":%d,\"flag_before\":%u,\"revoke_result\":%d,"
        "\"flag_result_after\":%d,\"status_after\":%d,\"flag_after\":%u,\"restore_result\":%d,"
        "\"flag_result_final\":%d,\"status_final\":%d,\"flag_final\":%u}\n",
        argv[1], argv[2], argv[3], static_cast<int>(getpid()), static_cast<int>(getuid()), targetPid, token,
        bundle.c_str(), PERMISSION, static_cast<unsigned long long>(ticksBefore), static_cast<unsigned long long>(ticksAfter),
        static_cast<unsigned int>(PERMISSION_USER_FIXED), static_cast<int>(USER_GRANTED_PERM), infoResult,
        flagResultBefore, statusBefore, flagBefore, revoked, flagResultAfter, statusAfter, flagAfter, restoreResult,
        flagResultFinal, statusFinal, flagFinal);
    return std::fflush(stdout) == 0 ? 0 : 71;
}
