/* SPDX-License-Identifier: Apache-2.0
 * Independent AccessToken observation for only the disposable audit application.
 * No grant path exists. Revoke keeps the process alive for the active test.
 */
#include "accesstoken_kit.h"
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <time.h>
#include <unistd.h>

using namespace OHOS::Security::AccessToken;

static int Fail(const char *stage, int status)
{
    fprintf(stderr, "AUDIO_CAPTURE_TOKEN_FAIL stage=%s rc=%d pid=%ld uid=%ld euid=%ld\n",
        stage, status, static_cast<long>(getpid()), static_cast<long>(getuid()), static_cast<long>(geteuid()));
    return status;
}

static unsigned long long NowNs(int &error)
{
    struct timespec value {};
    error = 0;
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) { error = errno; return 0; }
    return static_cast<unsigned long long>(value.tv_sec) * 1000000000ULL + value.tv_nsec;
}

int main(int argc, char **argv)
{
    if ((argc != 4 && argc != 5) || getuid() != 0 ||
        (strcmp(argv[3], "query") != 0 && strcmp(argv[3], "revoke") != 0 &&
         strcmp(argv[3], "query-background") != 0)) return Fail("arguments-or-root", 2);
    const std::string run(argv[1]);
    if (run.size() != 32 || run.find_first_not_of("0123456789abcdef") != std::string::npos) return Fail("run-id", 2);
    const std::string uidText(argv[2]);
    if (uidText.empty() || uidText.find_first_not_of("0123456789") != std::string::npos) return Fail("uid-text", 2);
    char *end = nullptr;
    const unsigned long expected = strtoul(argv[2], &end, 10);
    if (*end != '\0' || expected / 200000 != 100 || expected % 200000 < 10000) return Fail("ordinary-uid", 2);
    const char *bundle = argc == 5 ? argv[4] : "org.harmonycontrib.capabilityaudit";
    if (strcmp(bundle, "org.harmonycontrib.capabilityaudit") != 0 &&
        strcmp(bundle, "org.harmonycontrib.capabilityauditfocus") != 0) return Fail("bundle", 2);
    const char *permission = strcmp(argv[3], "query-background") == 0 ?
        "ohos.permission.KEEP_BACKGROUND_RUNNING" : "ohos.permission.MICROPHONE";
    const AccessTokenID token = AccessTokenKit::GetHapTokenID(100, bundle, 0);
    HapTokenInfo info {};
    const int queried = AccessTokenKit::GetHapTokenInfo(token, info);
    if (token == 0 || queried != 0 || info.tokenID != token || info.userID != 100 ||
        info.instIndex != 0 || info.bundleName != bundle) {
        fprintf(stderr, "AUDIO_CAPTURE_TOKEN_CONTEXT run=%s operation=%s expected_uid=%lu expected_bundle=%s "
            "token=%u get_hap_info_rc=%d info_token=%u info_uid=%d info_user=%d info_inst=%d actual_bundle_hex=",
            run.c_str(), argv[3], expected, bundle, token, queried, info.tokenID, info.uid, info.userID, info.instIndex);
        for (unsigned char byte : info.bundleName) fprintf(stderr, "%02x", static_cast<unsigned>(byte));
        fprintf(stderr, "\n");
        return Fail("hap-token-identity", 1);
    }
    int beforeClockError = 0, afterClockError = 0;
    const auto beforeNs = NowNs(beforeClockError);
    const int before = AccessTokenKit::VerifyAccessToken(token, permission, true);
    int action = 0;
    if (strcmp(argv[3], "revoke") == 0) {
        if (before != PERMISSION_GRANTED) {
            fprintf(stderr, "AUDIO_CAPTURE_TOKEN_CONTEXT run=%s token=%u permission=%s before=%d\n",
                run.c_str(), token, permission, before);
            return Fail("revoke-precondition", 1);
        }
        action = AccessTokenKit::RevokePermission(token, permission, PERMISSION_USER_SET, USER_GRANTED_PERM, false);
    }
    const int after = AccessTokenKit::VerifyAccessToken(token, permission, true);
    const auto afterNs = NowNs(afterClockError);
    if (beforeNs == 0 || afterNs < beforeNs) {
        fprintf(stderr, "AUDIO_CAPTURE_TOKEN_CONTEXT run=%s token=%u before_ns=%llu after_ns=%llu "
            "before_clock_errno=%d after_clock_errno=%d\n", run.c_str(), token, beforeNs, afterNs,
            beforeClockError, afterClockError);
        return Fail("monotonic-clock", 1);
    }
    // BMS is the application UID authority; expected_uid is only the argv echo.
    // This product's HapTokenInfoParcel does not transport info.uid.
    printf("{\"run_id\":\"%s\",\"bundle\":\"%s\",\"user_id\":100,\"expected_uid\":%lu,"
        "\"identity_schema\":\"hap-bms-access-token/v1\",\"at_reported_uid\":%d,\"at_query_rc\":%d,"
        "\"at_token_id\":%u,\"at_user_id\":%d,\"at_inst_index\":%d,\"at_bundle\":\"%s\","
        "\"token_id\":%u,\"permission\":\"%s\",\"operation\":\"%s\",\"result\":%d,"
        "\"before\":%d,\"after\":%d,\"before_ns\":%llu,\"after_ns\":%llu}\n", run.c_str(), bundle, expected,
        info.uid, queried, info.tokenID, info.userID, info.instIndex, info.bundleName.c_str(), token, permission,
        argv[3], action, before, after, beforeNs, afterNs);
    if (action == 0 && (after == PERMISSION_GRANTED || after == PERMISSION_DENIED)) return 0;
    fprintf(stderr, "AUDIO_CAPTURE_TOKEN_CONTEXT run=%s token=%u action_rc=%d before=%d after=%d\n",
        run.c_str(), token, action, before, after);
    return Fail("permission-result", 1);
}
