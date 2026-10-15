// Boundary shims execute the actual fixed adapter functions. No GPU or scene is
// simulated for product delivery; official translation-unit/guest tests remain.
#include "batch_system_graphics3d_plugin_abi.h"
#include <dlfcn.h>
#include <sys/resource.h>
#include <cstdlib>
#include <filesystem>
#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string_view>
#include <thread>
#include <type_traits>

#define META_NS Meta
#define SCENE_NS Scene
#define RENDER_NS Render
#define WIDGET_LOGE(...) ((void)0)
#define WIDGET_LOGI(...) ((void)0)
#define WIDGET_LOGD(...) ((void)0)
#define EGL_NO_CONTEXT nullptr
#define PLATFORM_CORE_ROOT_PATH /system/lib64
#define PLATFORM_CORE_PLUGIN_PATH /system/lib64/graphics3d
#define PLATFORM_APP_ROOT_PATH /system/lib64
#define PLATFORM_APP_PLUGIN_PATH /system/lib64/graphics3d
#define CHECK(x) do { if (!(x)) throw std::runtime_error(#x); } while (0)

struct Controls {
    std::string fail;
    int queueCreates = 0;
    int scheduled = 0;
    int engineCreates = 0;
    int renderInits = 0;
    int frames = 0;
    int engineLive = 0;
    int renderLive = 0;
    int applicationLive = 0;
} controls;

namespace Base {
template<class T> using shared_ptr = std::shared_ptr<T>;
template<class T> using weak_ptr = std::weak_ptr<T>;
}
namespace Core {
struct IInterface { virtual ~IInterface() = default; };
struct IFileManager {
    struct Ptr { explicit Ptr(IFileManager*) {} };
    void RegisterPath(const char*, const char*, bool) {}
};
struct IResourceManager {
    using Ptr = std::shared_ptr<IResourceManager>;
    void SetFileManager(const IFileManager::Ptr&) {}
};
struct EngineCreateInfo { PlatformCreateInfo platform; int app; int version; };
struct IClassFactory;
struct IEngine : IInterface {
    IEngine() { ++controls.engineLive; }
    ~IEngine() override { --controls.engineLive; }
    IFileManager files;
    struct Platform { void RegisterDefaultPaths(IFileManager&) const {} } platform;
    IFileManager& GetFileManager() { return files; }
    const Platform& GetPlatform() { return platform; }
    void Init() {}
    template<class T> T* GetInterface();
};
struct IEngineFactory {
    struct Result { IEngine* ptr; IEngine* get() const { return ptr; } };
    Result Create(const EngineCreateInfo&)
    {
        ++controls.engineCreates;
        return {controls.fail == "engine_instance" ? nullptr : new IEngine};
    }
};
static const int UID_ENGINE_FACTORY = 1;
template<class T> T* GetInstance(int)
{
    static T value;
    return controls.fail == "engine_factory" ? nullptr : &value;
}
}

namespace Render {
enum class DeviceBackendType { VULKAN, OPENGLES };
struct BackendExtraGLES { int depthBits = 0; void* sharedContext = nullptr; };
struct DeviceCreateInfo {
    DeviceBackendType backendType = DeviceBackendType::VULKAN;
    void* backendConfiguration = nullptr;
};
struct RenderCreateInfo { int applicationInfo = 0; DeviceCreateInfo deviceCreateInfo; };
enum class RenderResultCode { RENDER_SUCCESS, RENDER_FAILURE };
struct IShaderManager {
    struct ShaderFilePathDesc { const char* path; };
    void LoadShaderFiles(const ShaderFilePathDesc&) {}
};
struct IRenderContext : Core::IInterface {
    IRenderContext() { ++controls.renderLive; }
    ~IRenderContext() override { --controls.renderLive; }
    struct Device { IShaderManager shaders; IShaderManager& GetShaderManager() { return shaders; } } device;
    struct Renderer { void RenderFrame(std::initializer_list<int>) { ++controls.frames; } } renderer;
    RenderResultCode Init(const RenderCreateInfo&)
    {
        ++controls.renderInits;
        return controls.fail == "render_init" ? RenderResultCode::RENDER_FAILURE : RenderResultCode::RENDER_SUCCESS;
    }
    Device& GetDevice() { return device; }
    Renderer& GetRenderer() { return renderer; }
};
static const int UID_RENDER_CONTEXT = 2;
}
namespace Core {
struct IClassFactory {
    std::unique_ptr<IInterface> CreateInstance(int)
    {
        if (controls.fail == "render_instance") return {};
        return std::make_unique<Render::IRenderContext>();
    }
};
template<class T> T* IEngine::GetInterface()
{
    static T value;
    return controls.fail == "class_factory" ? nullptr : &value;
}
}

namespace Meta {
struct IAny { using Ptr = std::shared_ptr<IAny>; };
using Callback = std::function<IAny::Ptr()>;
struct ITaskQueueWaitableTask {};
struct Future {
    Callback callback;
    void Wait() { std::thread worker([this] { callback(); }); worker.join(); }
};
struct ITaskQueue : Core::IInterface {
    using Ptr = std::shared_ptr<ITaskQueue>;
    std::shared_ptr<Future> AddWaitableTask(Callback cb)
    {
        int attempt = ++controls.scheduled;
        if ((controls.fail == "check_schedule" && attempt == 1) ||
            (controls.fail == "init_schedule" && attempt == 2)) return {};
        return std::make_shared<Future>(Future{std::move(cb)});
    }
};
template<class T, class F> Callback MakeCallback(F fn) { return fn; }
struct QueueRegistry {
    std::map<std::string, ITaskQueue::Ptr> queues;
    ITaskQueue::Ptr GetTaskQueue(Base::Uid uid) { return queues[uid.value]; }
    bool RegisterTaskQueue(ITaskQueue::Ptr queue, Base::Uid uid)
    {
        if (controls.fail == std::string("register_") + uid.value) return false;
        queues[uid.value] = std::move(queue);
        return true;
    }
};
QueueRegistry& GetTaskQueueRegistry() { static QueueRegistry registry; return registry; }
enum class ObjectFlagBits { INTERNAL = 1, NATIVE = 2 };
int operator|(ObjectFlagBits lhs, ObjectFlagBits rhs) { return static_cast<int>(lhs) | static_cast<int>(rhs); }
using SharedPtrIInterface = std::shared_ptr<Core::IInterface>;
struct Property { template<class T> void SetValue(const T&) {} };
struct IMetadata {
    template<class T> void AddProperty(const T&) {}
    template<class T> Property* GetProperty(const char*)
    { static Property value; return controls.fail == "queue_property" ? nullptr : &value; }
};
template<class T> Property ConstructProperty(const char*, const T&, int) { return {}; }
template<class T> Property ConstructArrayProperty(const char*, std::initializer_list<T>, int) { return {}; }
namespace ClassId { static const int ThreadedTaskQueue = 1, FileResourceManager = 2; }
}
namespace Scene {
static const Base::Uid UID_SCENE_PLUGIN{"scene"};
struct SceneOptions {};
struct IRenderContext { using Ptr = std::shared_ptr<IRenderContext>; };
struct ISceneManager {};
struct IApplicationContext {
    using Ptr = std::shared_ptr<IApplicationContext>;
    struct ApplicationContextInfo {
        Meta::ITaskQueue::Ptr engine, app;
        std::shared_ptr<Render::IRenderContext> renderer;
        Core::IResourceManager::Ptr resources;
        SceneOptions options;
    };
    IApplicationContext() { ++controls.applicationLive; }
    ~IApplicationContext() { --controls.applicationLive; }
    bool Initialize(const ApplicationContextInfo&) { return controls.fail != "application_init"; }
    std::shared_ptr<IRenderContext> GetRenderContext()
    { return controls.fail == "scene_context" ? nullptr : std::make_shared<IRenderContext>(); }
    std::shared_ptr<ISceneManager> GetSceneManager()
    { return controls.fail == "scene_manager" ? nullptr : std::make_shared<ISceneManager>(); }
};
namespace ClassId { static const int ApplicationContext = 3; }
}
namespace Meta {
struct Registry {
    IMetadata context;
    IMetadata* GetDefaultObjectContext() { return controls.fail == "metadata" ? nullptr : &context; }
    template<class T> std::shared_ptr<T> Create(int)
    {
        if constexpr (std::is_same_v<T, ITaskQueue>) {
            int count = ++controls.queueCreates;
            if (controls.fail == "queue_" + std::to_string(count)) return {};
        } else if constexpr (std::is_same_v<T, Core::IResourceManager>) {
            if (controls.fail == "resources") return {};
        } else if constexpr (std::is_same_v<T, Scene::IApplicationContext>) {
            if (controls.fail == "application") return {};
        }
        return std::make_shared<T>();
    }
};
Registry& GetObjectRegistry() { static Registry registry; return registry; }
}
template<class T> T* interface_cast(Meta::IMetadata* object) { return static_cast<T*>(object); }
namespace CAM_PREVIEW_NS { static const Base::Uid UID_CAMERA_PREVIEW_PLUGIN{"camera"}; }

namespace OHOS::Render3D {
using IntfPtr = std::shared_ptr<Core::IInterface>;
using IntfWeakPtr = std::weak_ptr<Core::IInterface>;
struct EngineInstance {
    void* libHandle_ = nullptr;
    bool pluginsLoaded_ = false;
    Scene::IApplicationContext::Ptr applicationContext_;
    std::shared_ptr<Render::IRenderContext> renderContext_;
    std::shared_ptr<Core::IEngine> engine_;
} engineInstance_;
Meta::ITaskQueue::Ptr engineThread, ioThread, releaseThread;
static const Base::Uid ENGINE_THREAD{"engine"}, IO_QUEUE{"io"}, JS_RELEASE_THREAD{"release"};
static const int ENGINE_SERVICE_PRIORITY = 0;
struct HapInfo {
    std::string hapPath_, bundleName_, moduleName_;
    void* resourceManager_ = nullptr;
} hapInfo_;
HapInfo GetHapInfo() { return {}; }
void LockCompositor() {}
void UnlockCompositor() {}
struct LumeRenderConfig {
    std::string renderBackend_;
    static LumeRenderConfig& GetInstance() { static LumeRenderConfig instance; return instance; }
};
class SceneAdapter {
public:
    inline static bool engineInitSuccessful_ = false;
    static bool LoadEngineLib();
    static bool LoadPlugins(const Core::PlatformCreateInfo&);
    static bool InitEngine(Core::PlatformCreateInfo);
    static void ShutdownPluginRegistry();
    bool LoadPluginByUid(const Base::Uid&);
    bool LoadPluginsAndInit();
    void CreateRenderFunction() {}
};
#include "actual_adapter_functions.inc"
}

using namespace OHOS::Render3D;
int Loads()
{
    auto get = reinterpret_cast<int (*)()>(dlsym(engineInstance_.libHandle_, "BatchGraphicsLoads"));
    CHECK(get);
    return get();
}

int main(int argc, char** argv)
{
    try {
        CHECK(argc == 5);
        std::string scenario(argv[1]);
        const std::filesystem::path selected(argv[2]), good(argv[3]), bad(argv[4]);
        if (scenario == "missing_library_global") {
            auto global = dlopen(good.c_str(), RTLD_NOW | RTLD_GLOBAL);
            CHECK(global);
            CHECK(!SceneAdapter::LoadEngineLib());
            dlclose(global);
        } else if (scenario == "missing_export_retry") {
            CHECK(!SceneAdapter::LoadEngineLib());
            CHECK(engineInstance_.libHandle_ == nullptr && !Core::GetPluginRegister && !Core::CreatePluginRegistry);
            std::filesystem::remove(selected);
            std::filesystem::copy_file(good, selected);
            CHECK(SceneAdapter::LoadEngineLib());
        } else if (scenario == "preloaded_engine") {
            CHECK(SceneAdapter::LoadEngineLib());
            CHECK(SceneAdapter::LoadPlugins({}));
            CHECK(Loads() == 1);
        } else if (scenario == "plugin_retry") {
            setenv("BATCH_GRAPHICS_FAIL_PLUGINS", "1", 1);
            CHECK(!SceneAdapter::LoadPlugins({}));
            unsetenv("BATCH_GRAPHICS_FAIL_PLUGINS");
            CHECK(SceneAdapter::LoadPlugins({}));
            CHECK(Loads() == 2);
        } else if (scenario == "uid_failure") {
            CHECK(SceneAdapter::LoadPlugins({}));
            setenv("BATCH_GRAPHICS_DENY_UID", "requested", 1);
            SceneAdapter adapter;
            CHECK(!adapter.LoadPluginByUid(Base::Uid{"requested"}));
            CHECK(Loads() == 2);
        } else if (scenario == "plugin_once") {
            CHECK(SceneAdapter::LoadPlugins({}));
            CHECK(SceneAdapter::LoadPlugins({}));
            CHECK(Loads() == 1);
        } else if (scenario == "shutdown_reload") {
            CHECK(SceneAdapter::LoadPlugins({}));
            SceneAdapter::ShutdownPluginRegistry();
            CHECK(!engineInstance_.pluginsLoaded_ && !SceneAdapter::engineInitSuccessful_);
            CHECK(SceneAdapter::LoadPlugins({}));
            CHECK(Loads() == 1);
        } else if (scenario == "init_good" || scenario == "init_cached") {
            CHECK(SceneAdapter::InitEngine({}));
            CHECK(controls.engineLive == 1 && controls.renderLive == 1 && controls.applicationLive == 1);
            CHECK(controls.frames == 1);
            if (scenario == "init_cached") {
                SceneAdapter::engineInitSuccessful_ = true;
                CHECK(SceneAdapter::InitEngine({}));
                CHECK(controls.engineCreates == 1 && controls.frames == 1);
            }
        } else if (scenario == "init_retry") {
            controls.fail = "render_init";
            CHECK(!SceneAdapter::InitEngine({}));
            CHECK(controls.engineLive == 0 && controls.renderLive == 0 && controls.applicationLive == 0);
            controls.fail.clear();
            CHECK(SceneAdapter::InitEngine({}));
            CHECK(controls.engineCreates == 2 && controls.frames == 1);
        } else if (scenario.rfind("init_", 0) == 0) {
            controls.fail = scenario.substr(5);
            CHECK(!SceneAdapter::InitEngine({}));
            CHECK(controls.engineLive == 0 && controls.renderLive == 0 && controls.applicationLive == 0);
            CHECK(controls.frames == 0);
        } else {
            throw std::runtime_error("unknown scenario");
        }
        engineInstance_.applicationContext_.reset();
        engineInstance_.renderContext_.reset();
        engineInstance_.engine_.reset();
        SceneAdapter::ShutdownPluginRegistry();
        CHECK(controls.engineLive == 0 && controls.renderLive == 0 && controls.applicationLive == 0);
        std::cout << scenario << ": pass\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << argv[1] << ": " << error.what() << '\n';
        return 1;
    }
}
