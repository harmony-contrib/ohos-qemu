#include <cstdio>
#include "iservice_registry.h"

// Request only the two audited Fusion SAs through the actual packaged SAMGR.
// Init still owns their UID/GID, token, capability and executable setup.
int main()
{
    auto manager = OHOS::SystemAbilityManagerClient::GetInstance().GetSystemAbilityManager();
    if (manager == nullptr) {
        std::puts("{\"samgr_available\":false}");
        return 1;
    }
    for (int round = 1; round <= 2; ++round) {
        for (int ability : {8631, 8630}) {
            auto remote = manager->LoadSystemAbility(ability, 4);
            const bool loaded = remote != nullptr;
            std::printf("{\"ability\":%d,\"round\":%d,\"loaded\":%s}\n",
                ability, round, loaded ? "true" : "false");
            std::fflush(stdout);
            if (!loaded) {
                return 1;
            }
        }
    }
    return 0;
}
