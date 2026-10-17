/* Read-only actual AccessToken observer; no grant/revoke/permission mutation. */
#include "accesstoken_kit.h"
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <time.h>
#include <unistd.h>
using namespace OHOS::Security::AccessToken;

static unsigned long long Now()
{
    timespec value {};
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) { return 0; }
    return static_cast<unsigned long long>(value.tv_sec) * 1000000000ULL + value.tv_nsec;
}

int main(int argc, char **argv)
{
    if (argc != 5 || getuid() != 0) { return 2; }
    const std::string run(argv[1]), uidText(argv[2]), bundle(argv[3]), permission(argv[4]);
    if (run.size() != 32 || run.find_first_not_of("0123456789abcdef") != std::string::npos ||
        uidText.empty() || uidText.size() > 9 || uidText.find_first_not_of("0123456789") != std::string::npos) { return 2; }
    const bool wallpaper = permission == "ohos.permission.SET_WALLPAPER" &&
        (bundle == "org.harmonycontrib.wallpaperchallenge" || bundle == "com.ohos.settings");
    const bool query = permission == "ohos.permission.READ_IMAGEVIDEO" && bundle == "org.harmonycontrib.wallpaperquery";
    if (!wallpaper && !query) { return 2; }
    const unsigned long uid = std::strtoul(uidText.c_str(), nullptr, 10);
    if (uid / 200000 != 100 || (bundle != "com.ohos.settings" && uid % 200000 < 10000)) { return 2; }
    const AccessTokenID token = AccessTokenKit::GetHapTokenID(100, bundle, 0);
    HapTokenInfo info {};
    const int queried = AccessTokenKit::GetHapTokenInfo(token, info);
    if (token == 0 || queried != 0 || info.tokenID != token ||
        info.userID != 100 || info.instIndex != 0 || info.bundleName != bundle) { return 1; }
    std::ifstream stream("/proc/sys/kernel/random/boot_id");
    std::string boot;
    if (!std::getline(stream, boot) || boot.size() != 36 || boot.find_first_not_of("0123456789abcdef-") != std::string::npos) { return 1; }
    const auto began = Now();
    const int first = AccessTokenKit::VerifyAccessToken(token, permission, true);
    const int second = AccessTokenKit::VerifyAccessToken(token, permission, true);
    const auto ended = Now();
    if (began == 0 || ended < began || first != second || (first != PERMISSION_GRANTED && first != PERMISSION_DENIED)) { return 1; }
    // Only the collector's original BMS record supplies the application UID.
    std::printf("{\"run_id\":\"%s\",\"boot_id\":\"%s\",\"bundle\":\"%s\",\"expected_uid\":%lu,"
        "\"identity_schema\":\"hap-bms-access-token/v1\",\"at_reported_uid\":%d,\"at_query_rc\":%d,"
        "\"at_token_id\":%u,\"at_user_id\":%d,\"at_inst_index\":%d,\"at_bundle\":\"%s\","
        "\"user_id\":100,\"token_id\":%u,\"permission\":\"%s\",\"grant\":%d,"
        "\"before_ns\":%llu,\"after_ns\":%llu}\n", run.c_str(), boot.c_str(), bundle.c_str(), uid,
        info.uid, queried, info.tokenID, info.userID, info.instIndex, info.bundleName.c_str(),
        token, permission.c_str(), first, began, ended);
    return std::ferror(stdout) ? 1 : 0;
}
