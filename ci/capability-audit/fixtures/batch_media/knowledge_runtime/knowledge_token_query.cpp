/* Read-only product API observer candidate. Root builds and binds ELF + DSOs. */
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
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) return 0;
    return static_cast<unsigned long long>(value.tv_sec) * 1000000000ULL + value.tv_nsec;
}

int main(int argc, char **argv)
{
    if (argc != 4 || getuid() != 0) return 2;
    const std::string run(argv[1]), uidText(argv[2]), bundle(argv[3]);
    if (run.size() != 32 || run.find_first_not_of("0123456789abcdef") != std::string::npos ||
        uidText.empty() || uidText.size() > 9 || uidText.find_first_not_of("0123456789") != std::string::npos) return 2;
    if (bundle != "org.harmonycontrib.knowledgeimporter" && bundle != "org.harmonycontrib.knowledgedenied" &&
        bundle != "org.harmonycontrib.knowledgequery" && bundle != "org.harmonycontrib.knowledgecurator") return 2;
    const unsigned long uid = std::strtoul(uidText.c_str(), nullptr, 10);
    if (uid / 200000 != 100 || uid % 200000 < 10000) return 2;
    const AccessTokenID token = AccessTokenKit::GetHapTokenID(100, bundle, 0);
    HapTokenInfo info {};
    const int queried = AccessTokenKit::GetHapTokenInfo(token, info);
    if (token == 0 || queried != 0 || info.tokenID != token ||
        info.userID != 100 || info.instIndex != 0 || info.bundleName != bundle) return 1;
    std::ifstream stream("/proc/sys/kernel/random/boot_id");
    std::string boot;
    if (!std::getline(stream, boot) || boot.size() != 36 || boot.find_first_not_of("0123456789abcdef-") != std::string::npos) return 1;
    const auto before = Now();
    const int read = AccessTokenKit::VerifyAccessToken(token, "ohos.permission.READ_IMAGEVIDEO", true);
    const int again = AccessTokenKit::VerifyAccessToken(token, "ohos.permission.READ_IMAGEVIDEO", true);
    const bool curator = bundle == "org.harmonycontrib.knowledgecurator";
    int write = PERMISSION_DENIED;
    if (curator) write = AccessTokenKit::VerifyAccessToken(token, "ohos.permission.WRITE_IMAGEVIDEO", true);
    const auto after = Now();
    if (before == 0 || after < before || read != again ||
        (read != PERMISSION_GRANTED && read != PERMISSION_DENIED) ||
        (write != PERMISSION_GRANTED && write != PERMISSION_DENIED)) return 1;
    std::printf("{\"schema_version\":2,\"api\":\"AccessTokenKit::VerifyAccessToken\",\"run_id\":\"%s\","
        "\"boot_id\":\"%s\",\"bundle\":\"%s\",\"expected_uid\":%lu,"
        "\"identity_schema\":\"hap-bms-access-token/v1\",\"at_reported_uid\":%d,\"at_query_rc\":%d,"
        "\"at_token_id\":%u,\"at_user_id\":%d,\"at_inst_index\":%d,\"at_bundle\":\"%s\","
        "\"user_id\":100,\"token_id\":%u,\"READ_IMAGEVIDEO\":%d,\"WRITE_IMAGEVIDEO\":",
        run.c_str(), boot.c_str(), bundle.c_str(), uid, info.uid, queried, info.tokenID, info.userID,
        info.instIndex, info.bundleName.c_str(), token, read);
    if (curator) std::printf("%d", write);
    else std::printf("null"); // Not queried: never represent a missing query as an actual denial.
    std::printf(",\"before_ns\":%llu,\"after_ns\":%llu}\n", before, after);
    return std::ferror(stdout) ? 1 : 0;
}
