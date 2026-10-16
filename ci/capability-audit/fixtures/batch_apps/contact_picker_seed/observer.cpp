// SPDX-License-Identifier: Apache-2.0
// Read-only root-owned runtime observer. Never grants permissions or mutates data.
#include <algorithm>
#include <charconv>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>
#include "accesstoken_kit.h"
#include "app_mgr_client.h"
#include "json.hpp"

using nlohmann::json;
using OHOS::Security::AccessToken::AccessTokenKit;
constexpr const char *CALLER = "com.ohos.qemu.contactpickercaller";
constexpr const char *SEED = "com.ohos.qemu.contactpickerseed";

int main(int argc, char **argv)
{
    if (argc < 3 || (std::string(argv[2]) != CALLER && std::string(argv[2]) != SEED)) {
        std::cerr << "usage: observer processes BUNDLE | permissions BUNDLE TOKEN\n";
        return 2;
    }
    const std::string bundle(argv[2]);
    if (argc == 3 && std::string(argv[1]) == "processes") {
        OHOS::AppExecFwk::AppMgrClient client;
        std::vector<OHOS::AppExecFwk::RunningProcessInfo> infos;
        const auto code = client.GetAllRunningProcesses(infos);
        json result = {{"api", "AppMgrClient::GetAllRunningProcesses"},
            {"error_code", static_cast<int>(code)}, {"bundle_name", bundle}, {"processes", json::array()}};
        if (static_cast<int>(code) == 0) {
            for (const auto &info : infos) {
                if (std::find(info.bundleNames.begin(), info.bundleNames.end(), bundle) != info.bundleNames.end()) {
                    result["processes"].push_back({{"pid", info.pid_}, {"bundleNames", info.bundleNames}});
                }
            }
        }
        std::cout << result.dump() << '\n';
        return static_cast<int>(code) == 0 ? 0 : 1;
    }
    if (argc != 4 || std::string(argv[1]) != "permissions") { return 2; }
    const std::string text(argv[3]);
    uint32_t token = 0;
    const auto parsed = std::from_chars(text.data(), text.data() + text.size(), token);
    if (text.empty() || text[0] == '0' || parsed.ec != std::errc() ||
        parsed.ptr != text.data() + text.size() || token == 0) { return 2; }
    OHOS::Security::AccessToken::HapTokenInfo info;
    const int tokenCode = AccessTokenKit::GetHapTokenInfo(token, info);
    if (tokenCode != 0 || info.bundleName != bundle) {
        std::cout << json({{"api", "AccessTokenKit::GetHapTokenInfo"},
            {"error_code", tokenCode}, {"bundle_matches", info.bundleName == bundle}, {"token_id", token}}).dump() << '\n';
        return 1;
    }
    std::cout << json({{"api", "AccessTokenKit::VerifyAccessToken"}, {"token_id", token},
        {"bundle_name", bundle}, {"READ_CONTACTS", AccessTokenKit::VerifyAccessToken(token, "ohos.permission.READ_CONTACTS")},
        {"WRITE_CONTACTS", AccessTokenKit::VerifyAccessToken(token, "ohos.permission.WRITE_CONTACTS")}}).dump() << '\n';
    return 0;
}
