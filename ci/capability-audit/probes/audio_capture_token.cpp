/* SPDX-License-Identifier: Apache-2.0
 * Independent AccessToken observation for only the disposable audit application.
 * No grant path exists. Revoke keeps the process alive for the active test.
 */
#include "accesstoken_kit.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <time.h>
#include <unistd.h>

using namespace OHOS::Security::AccessToken;

static unsigned long long NowNs()
{
    struct timespec value {};
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) return 0;
    return static_cast<unsigned long long>(value.tv_sec) * 1000000000ULL + value.tv_nsec;
}

int main(int argc, char **argv)
{
    if (argc != 4 || getuid() != 0 ||
        (strcmp(argv[3], "query") != 0 && strcmp(argv[3], "revoke") != 0)) return 2;
    const std::string run(argv[1]);
    if (run.size() != 32 || run.find_first_not_of("0123456789abcdef") != std::string::npos) return 2;
    const std::string uidText(argv[2]);
    if (uidText.empty() || uidText.find_first_not_of("0123456789") != std::string::npos) return 2;
    char *end = nullptr;
    const unsigned long expected = strtoul(argv[2], &end, 10);
    if (*end != '\0' || expected / 200000 != 100 || expected % 200000 < 10000) return 2;
    constexpr const char *bundle = "org.harmonycontrib.capabilityaudit";
    constexpr const char *permission = "ohos.permission.MICROPHONE";
    const AccessTokenID token = AccessTokenKit::GetHapTokenID(100, bundle, 0);
    HapTokenInfo info {};
    const int queried = AccessTokenKit::GetHapTokenInfo(token, info);
    if (token == 0 || queried != 0 || info.tokenID != token || info.userID != 100 ||
        info.instIndex != 0 || info.bundleName != bundle || info.uid != static_cast<int32_t>(expected)) return 1;
    const auto beforeNs = NowNs();
    const int before = AccessTokenKit::VerifyAccessToken(token, permission, true);
    int action = 0;
    if (strcmp(argv[3], "revoke") == 0) {
        if (before != PERMISSION_GRANTED) return 1;
        action = AccessTokenKit::RevokePermission(token, permission, PERMISSION_USER_SET, USER_GRANTED_PERM, false);
    }
    const int after = AccessTokenKit::VerifyAccessToken(token, permission, true);
    const auto afterNs = NowNs();
    if (beforeNs == 0 || afterNs < beforeNs) return 1;
    printf("{\"run_id\":\"%s\",\"bundle\":\"%s\",\"user_id\":100,\"uid\":%lu,"
        "\"token_id\":%u,\"permission\":\"%s\",\"operation\":\"%s\",\"result\":%d,"
        "\"before\":%d,\"after\":%d,\"before_ns\":%llu,\"after_ns\":%llu}\n", run.c_str(), bundle, expected, token, permission,
        argv[3], action, before, after, beforeNs, afterNs);
    return action == 0 && (after == PERMISSION_GRANTED || after == PERMISSION_DENIED) ? 0 : 1;
}
