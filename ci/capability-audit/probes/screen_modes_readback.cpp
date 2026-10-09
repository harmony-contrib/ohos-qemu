/* Copyright (c) 2026 Harmony Contrib. SPDX-License-Identifier: Apache-2.0 */
// Read-only root/HDC diagnostic of the real display service. This is NOT
// ordinary-app permission evidence and never changes a mode or grants access.
#include <cstdio>
#include <cinttypes>
#include <set>
#include "screen_manager.h"
#include "screen_info.h"

int main()
{
    using namespace OHOS;
    using namespace OHOS::Rosen;
    std::vector<sptr<Screen>> screens;
    const auto result = ScreenManager::GetInstance().GetAllScreens(screens);
    if (result != DMError::DM_OK || screens.empty()) {
        std::fprintf(stderr, "real GetAllScreens failed: %d\n", static_cast<int>(result));
        return 1;
    }
    std::set<ScreenId> ids;
    // Validate all records before writing a successful JSON observation.
    for (const auto& screen : screens) {
        if (screen == nullptr || screen->GetScreenInfo() == nullptr ||
            !ids.insert(screen->GetId()).second) return 2;
        std::set<uint32_t> modes;
        for (const auto& mode : screen->GetSupportedModes()) {
            if (mode == nullptr || mode->width_ == 0 || mode->height_ == 0 || mode->refreshRate_ == 0 ||
                !modes.insert(mode->id_).second) return 3;
        }
        if (screen->GetModeId() >= screen->GetSupportedModes().size()) return 4;
    }
    std::printf("QEMU_SCREEN_MODES:{\"scope\":\"root_readonly_actual_display_service\",\"screens\":[");
    bool firstScreen = true;
    for (const auto& screen : screens) {
        std::printf("%s{\"id\":%" PRIu64 ",\"sourceMode\":%u,\"activeModeIndex\":%u,\"modes\":[",
            firstScreen ? "" : ",", screen->GetId(),
            static_cast<unsigned>(screen->GetScreenInfo()->GetSourceMode()), screen->GetModeId());
        firstScreen = false;
        bool firstMode = true;
        for (const auto& mode : screen->GetSupportedModes()) {
            std::printf("%s{\"id\":%u,\"width\":%u,\"height\":%u,\"refreshRate\":%u}",
                firstMode ? "" : ",", mode->id_, mode->width_, mode->height_, mode->refreshRate_);
            firstMode = false;
        }
        std::printf("]}");
    }
    std::printf("]}\n");
    return 0;
}
