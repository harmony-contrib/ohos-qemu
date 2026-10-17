// SPDX-License-Identifier: Apache-2.0
// Root builds with current product innerkit ABI/CFI. Read-only, never grant/revoke.
#include <algorithm>
#include <fstream>
#include <iostream>
#include <string>
#include <time.h>
#include <unistd.h>
#include <vector>
#include "accesstoken_kit.h"
#include "app_mgr_client.h"
#include "json.hpp"
using nlohmann::json;
using namespace OHOS::Security::AccessToken;
static uint64_t Now(clockid_t clock) {
    timespec value {};
    if (clock_gettime(clock, &value) != 0) return 0;
    return static_cast<uint64_t>(value.tv_sec) * 1000000000ULL + value.tv_nsec;
}
int main(int argc, char** argv) {
    if (argc != 3 || getuid() != 0) return 2;
    const std::string run(argv[1]), bundle(argv[2]);
    if (run.size() != 32 || run.find_first_not_of("0123456789abcdef") != std::string::npos ||
        (bundle != "org.harmonycontrib.calendarproducer" && bundle != "org.harmonycontrib.calendarobserver" &&
         bundle != "org.harmonycontrib.calendardenied" && bundle != "com.ohos.calendardata")) return 2;
    const AccessTokenID token = AccessTokenKit::GetHapTokenID(100, bundle, 0);
    HapTokenInfo info {};
    if (!token || AccessTokenKit::GetHapTokenInfo(token, info) != 0 || info.tokenID != token ||
        info.bundleName != bundle || info.instIndex != 0 || info.userID != 100 || info.uid / 200000 != 100) return 1;
    std::ifstream stream("/proc/sys/kernel/random/boot_id"); std::string boot;
    if (!std::getline(stream, boot) || boot.size() != 36 || boot.find_first_not_of("0123456789abcdef-") != std::string::npos) return 1;
    const uint64_t before = Now(CLOCK_MONOTONIC), realtime = Now(CLOCK_REALTIME), boottime = Now(CLOCK_BOOTTIME);
    json permissions = json::object(), definitions = json::object();
    for (const char* name : {"ohos.permission.READ_CALENDAR", "ohos.permission.WRITE_CALENDAR",
         "ohos.permission.READ_WHOLE_CALENDAR", "ohos.permission.WRITE_WHOLE_CALENDAR", "ohos.permission.NOTIFICATION_CONTROLLER"}) {
        const int first = AccessTokenKit::VerifyAccessToken(token, name, true);
        if (first != AccessTokenKit::VerifyAccessToken(token, name, true) ||
            (first != PERMISSION_GRANTED && first != PERMISSION_DENIED)) return 1;
        permissions[name] = first;
        PermissionDef definition {};
        if (AccessTokenKit::GetDefPermission(name, definition) != 0 || definition.permissionName != name) return 1;
        definitions[name] = {{"permissionName", definition.permissionName}, {"grantMode", definition.grantMode},
            {"availableLevel", definition.availableLevel}, {"availableType", definition.availableType},
            {"provisionEnable", definition.provisionEnable}};
    }
    OHOS::AppExecFwk::AppMgrClient client; std::vector<OHOS::AppExecFwk::RunningProcessInfo> infos;
    const auto code = client.GetAllRunningProcesses(infos); json processes = json::array();
    if (static_cast<int>(code) != 0) return 1;
    for (const auto& item : infos) {
        if (std::find(item.bundleNames.begin(), item.bundleNames.end(), bundle) != item.bundleNames.end()) {
            processes.push_back({{"pid", item.pid_}, {"bundleNames", item.bundleNames}});
        }
    }
    const uint64_t after = Now(CLOCK_MONOTONIC);
    if (!before || !realtime || !boottime || after < before) return 1;
    std::cout << json({{"schema_version", 1}, {"run_id", run}, {"boot_id", boot}, {"bundle", bundle},
        {"uid", info.uid}, {"token_id", token}, {"user_id", info.userID},
        {"permission_api", "AccessTokenKit::VerifyAccessToken"}, {"permissions", permissions},
        {"definition_api", "AccessTokenKit::GetDefPermission"}, {"definitions", definitions},
        {"process_api", "AppMgrClient::GetAllRunningProcesses"}, {"processes", processes},
        {"before_ns", before}, {"after_ns", after}, {"realtime_ns", realtime}, {"boottime_ns", boottime}}).dump() << '\n';
    return std::cout ? 0 : 1;
}
