// Local ABI for testing the extracted platform loader with real dlopen/dlsym.
// The test DSO is never installed or used as a product scene/render backend.
#pragma once
#include <cstddef>
#include <string>
#include <vector>
#define BASE_NS Base
#define CORE_NS Core
namespace Base {
struct Uid { const char* value; };
template<class T> using vector = std::vector<T>;
template<class T> struct array_view {
    T* data;
    size_t size;
    array_view(T* p, size_t n) : data(p), size(n) {}
};
}
namespace Core {
struct PlatformCreateInfo {
    const char* coreRoot = "";
    const char* corePlugin = "";
    const char* appRoot = "";
    const char* appPlugin = "";
    const char* hapPath = "";
    const char* bundle = "";
    const char* module = "";
    void* resources = nullptr;
};
struct PluginRegister {
    virtual ~PluginRegister() = default;
    virtual bool LoadPlugins(const Base::array_view<Base::Uid>&) = 0;
};
#ifdef BATCH_GRAPHICS_LIBRARY
void CreatePluginRegistry(const PlatformCreateInfo&);
PluginRegister& GetPluginRegister();
bool IsDebugBuild();
const char* GetVersionRev();
#else
inline void (*CreatePluginRegistry)(const PlatformCreateInfo&) = nullptr;
inline PluginRegister& (*GetPluginRegister)() = nullptr;
inline bool (*IsDebugBuild)() = nullptr;
inline const char* (*GetVersion)() = nullptr;
#endif
}
