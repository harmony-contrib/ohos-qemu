#define BATCH_GRAPHICS_LIBRARY
#include "batch_system_graphics3d_plugin_abi.h"
#include <cstdlib>

namespace {
int loads = 0;
int registries = 0;
class Register final : public Core::PluginRegister {
public:
    bool LoadPlugins(const Base::array_view<Base::Uid>& list) override
    {
        ++loads;
        if (std::getenv("BATCH_GRAPHICS_FAIL_PLUGINS")) return false;
        auto denied = std::getenv("BATCH_GRAPHICS_DENY_UID");
        for (size_t i = 0; i < list.size; ++i) {
            if (denied && std::string(list.data[i].value) == denied) return false;
        }
        return true;
    }
} registry;
}

namespace Core {
void CreatePluginRegistry(const PlatformCreateInfo&) { ++registries; }
PluginRegister& GetPluginRegister() { return registry; }
bool IsDebugBuild() { return false; }
#ifndef BATCH_GRAPHICS_MISSING_EXPORT
const char* GetVersionRev() { return "host-boundary-fixture"; }
#endif
}
extern "C" int BatchGraphicsLoads() { return loads; }
extern "C" int BatchGraphicsRegistries() { return registries; }
