/*
 * Copyright (c) 2021-2025 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "main_thread.h"

#include <malloc.h>
#include <new>
#include <regex>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <sys/types.h>
#include <unistd.h>
#include <map>

#include "resource_config_helper.h"
#include "ability_manager_client.h"
#include "constants.h"
#include "ability_delegator.h"
#include "ability_delegator_registry.h"
#include "ability_loader.h"
#include "ability_thread.h"
#include "ability_util.h"
#include "app_image_observer_manager.h"
#include "app_loader.h"
#include "app_recovery.h"
#include "appfreeze_inner.h"
#include "appfreeze_state.h"
#include "application_data_manager.h"
#include "application_env_impl.h"
#include "bundle_mgr_proxy.h"
#include "hitrace_meter.h"
#include "procinfo.h"
#ifdef SUPPORT_CHILD_PROCESS
#include "child_main_thread.h"
#include "child_process_manager.h"
#endif // SUPPORT_CHILD_PROCESS
#include "configuration_convertor.h"
#include "common_event_manager.h"
#include "global_constant.h"
#include "context_deal.h"
#include "context_impl.h"
#include "display_util.h"
#include "dump_arkweb_helper.h"
#include "dump_ffrt_helper.h"
#include "dump_ipc_helper.h"
#include "dump_process_helper.h"
#include "dump_runtime_helper.h"
#include "ets_exception_callback.h"
#include "ets_runtime.h"
#include "exit_reason.h"
#include "extension_ability_info.h"
#include "extension_module_loader.h"
#include "extension_plugin_info.h"
#include "ext_native_startup_manager.h"
#include "ext_native_startup_task.h"
#include "extract_resource_manager.h"
#include "ffrt.h"
#include "file_path_utils.h"
#include "forkall_helper.h"
#include "freeze_util.h"
#include "hilog_tag_wrapper.h"
#include "load_ability_callback_manager.h"
#ifdef SUPPORT_SCREEN
#include "locale_config_ext.h"
#include "ace_forward_compatibility.h"
#include "form_constants.h"
#include "cache.h"
#ifdef SUPPORT_APP_PREFERRED_LANGUAGE
#include "preferred_language.h"
#endif
#endif
#include "app_mgr_client.h"
#include "if_system_ability_manager.h"
#include "iservice_registry.h"
#include "js_runtime.h"
#ifdef CJ_FRONTEND
#include "cj_runtime.h"
#endif
#include "native_lib_util.h"
#include "ets_native_lib_util.h"
#include "native_startup_task.h"
#include "nlohmann/json.hpp"
#include "ohos_application.h"
#include "overlay_module_info.h"
#include "parameters.h"
#include "resource_manager.h"
#include "runtime.h"
#include "startup_util.h"
#include "sys_mgr_client.h"
#include "system_ability_definition.h"
#include "task_handler_client.h"
#include "time_util.h"
#include "uncaught_exception_callback.h"
#include "hisysevent_report.h"
#include "js_runtime_utils.h"
#include "context/application_context.h"
#include "os_account_manager_wrapper.h"
#ifdef SUPPORT_HIPERF
#include "appcapture_perf.h"
#endif

#include "sleep_clean.h"

#if defined(NWEB)
#include <thread>
#include "app_mgr_client.h"
#include "nweb_helper.h"
#endif

#if defined(NWEB) && defined(NWEB_GRAPHIC)
#include "nweb_adapter_helper.h"
#endif

#ifdef IMAGE_PURGEABLE_PIXELMAP
#include "purgeable_resource_manager.h"
#endif

#if defined(ABILITY_LIBRARY_LOADER) || defined(APPLICATION_LIBRARY_LOADER)
#include <dirent.h>
#include <dlfcn.h>
#endif
#include "xcollie/process_kill_reason.h"
namespace OHOS {
using AbilityRuntime::FreezeUtil;
namespace AppExecFwk {
using namespace OHOS::AbilityBase::Constants;
std::weak_ptr<OHOSApplication> MainThread::applicationForDump_;
std::shared_ptr<MainThread::MainHandler> MainThread::mainHandler_ = nullptr;
const std::string PERFCMD_PROFILE = "profile";
const std::string PERFCMD_DUMPHEAP = "dumpheap";
const std::string BASE_LINE_PERFCMD = "baseLineProfile";
namespace {
#ifdef APP_USE_ARM
constexpr char FORM_RENDER_LIB_PATH[] = "/system/lib/libformrender.z.so";
#elif defined(APP_USE_X86_64)
constexpr char FORM_RENDER_LIB_PATH[] = "/system/lib64/libformrender.z.so";
#else
constexpr char FORM_RENDER_LIB_PATH[] = "/system/lib64/libformrender.z.so";
#endif

constexpr int32_t DELIVERY_TIME = 200;
constexpr int32_t DISTRIBUTE_TIME = 100;
constexpr int32_t START_HIGH_SENSITIVE = 1;
constexpr int32_t EXIT_HIGH_SENSITIVE = 2;
constexpr int32_t UNSPECIFIED_USERID = -2;
constexpr int32_t JS_ERROR_EXIT = -2;
constexpr int32_t TIME_OUT = 120;
constexpr int32_t DEFAULT_SLEEP_TIME = 100000;

enum class SignalType {
    SIGNAL_JSHEAP_OLD,
    SIGNAL_JSHEAP,
    SIGNAL_JSHEAP_PRIV,
    SIGNAL_NO_TRIGGERID,
    SIGNAL_NO_TRIGGERID_PRIV,
    SIGNAL_FORCE_FULLGC,
};

constexpr char EVENT_KEY_PACKAGE_NAME[] = "PACKAGE_NAME";
constexpr char EVENT_KEY_VERSION[] = "VERSION";
constexpr char EVENT_KEY_TYPE[] = "TYPE";
constexpr char EVENT_KEY_HAPPEN_TIME[] = "HAPPEN_TIME";
constexpr char EVENT_KEY_REASON[] = "REASON";
constexpr char EVENT_KEY_JSVM[] = "JSVM";
constexpr char EVENT_KEY_CANGJIE[] = "CANGJIE";
constexpr char EVENT_KEY_SUMMARY[] = "SUMMARY";
constexpr char EVENT_KEY_PNAME[] = "PNAME";
constexpr char EVENT_KEY_THREAD_NAME[] = "THREAD_NAME";
constexpr char EVENT_KEY_APP_RUNNING_UNIQUE_ID[] = "APP_RUNNING_UNIQUE_ID";
constexpr char EVENT_KEY_PROCESS_RSS_MEMINFO[] = "PROCESS_RSS_MEMINFO";
constexpr char EVENT_KEY_PROCESS_LIFETIME[] = "PROCESS_LIFETIME";
constexpr char ERRORMANAGER_CAPTURE[] = "ERRORMANAGER_CAPTURE";
constexpr char IS_UNCATCH_FAULT[] = "IS_UNCATCH_FAULT";
constexpr char DEVELOPER_MODE_STATE[] = "const.security.developermode.state";
constexpr char PRODUCT_ASSERT_FAULT_DIALOG_ENABLED[] = "persisit.sys.abilityms.support_assert_fault_dialog";
constexpr const char* INHERIT_PLUGIN_NAMESPACE = "persist.sys.abilityms.inherit_plugin_namespace";
constexpr const char* PLUGIN_DEFAULT_NAMESPACE_LDDICTIONARY =
    "persist.sys.abilityms.plugin_default_namespace_lddictionary";
constexpr char KILL_REASON[] = "Kill Reason:Js Error";
constexpr const char* KEY_SKIP_ABILITY_STAGE_LIFECYCLE = "ohos.ability.param.skipAbilityStageLifecycle";

const int32_t JSCRASH_TYPE = 3;
const std::string JSVM_TYPE = "ARK";
const std::string SIGNAL_HANDLER = "OS_SignalHandler";

const int32_t CJERROR_TYPE = 9;
const std::string CANGJIE_TYPE = "CJNATIVE";

constexpr uint32_t CHECK_MAIN_THREAD_IS_ALIVE = 1;
constexpr int32_t LAUNCH_TASK_QOS = 5;

const std::string OVERLAY_STATE_CHANGED = "usual.event.OVERLAY_STATE_CHANGED";
const std::string JSON_KEY_APP_FONT_SIZE_SCALE = "fontSizeScale";
const std::string JSON_KEY_APP_FONT_MAX_SCALE = "fontSizeMaxScale";
const std::string JSON_KEY_APP_CONFIGURATION = "configuration";
const std::string DEFAULT_APP_FONT_SIZE_SCALE = "nonFollowSystem";
const std::string SYSTEM_DEFAULT_FONTSIZE_SCALE = "1.0";
const char* PC_LIBRARY_PATH = "/system/lib64/liblayered_parameters_manager.z.so";
const char* PC_FUNC_INFO = "DetermineResourceType";
const char* PRELOAD_APP_STARTUP = "PreloadAppStartup";
const int32_t TYPE_RESERVE = 1;
const int32_t TYPE_OTHERS = 2;
constexpr int32_t FOUNDATION_UID = 5523;

#if defined(NWEB) && defined(NWEB_GRAPHIC)
const std::string NWEB_SURFACE_NODE_NAME = "nwebPreloadSurface";
const std::string BLANK_URL = "about:blank";
constexpr uint32_t NWEB_SURFACE_SIZE = 1;
constexpr int32_t PRELOAD_TASK_DELAY_TIME = 2000;  //millisecond
#endif

extern "C" int DFX_SetAppRunningUniqueId(const char* appRunningId, size_t len) __attribute__((weak));

class LoadExtStartupTask : public AbilityRuntime::ExtNativeStartupTask {
public:
    LoadExtStartupTask() : ExtNativeStartupTask("LoadExtStartupTask")
    {}

    int32_t RunTask() override
    {
        AbilityRuntime::ExtNativeStartupManager::LoadExtStartupTask();
        return ERR_OK;
    }
};
} // namespace

void MainThread::GetNativeLibPath(const BundleInfo &bundleInfo, const HspList &hspList, AppLibPathMap &appLibPaths)
{
    std::string patchNativeLibraryPath = bundleInfo.applicationInfo.appQuickFix.deployedAppqfInfo.nativeLibraryPath;
    if (!patchNativeLibraryPath.empty()) {
        // libraries in patch lib path has a higher priority when loading.
        std::string patchLibPath = LOCAL_CODE_PATH;
        patchLibPath += (patchLibPath.back() == '/') ? patchNativeLibraryPath : "/" + patchNativeLibraryPath;
        TAG_LOGD(AAFwkTag::APPKIT, "lib path = %{private}s", patchLibPath.c_str());
        appLibPaths["default"].emplace_back(patchLibPath);
    }

    std::string nativeLibraryPath = bundleInfo.applicationInfo.nativeLibraryPath;
    if (!nativeLibraryPath.empty()) {
        if (nativeLibraryPath.back() == '/') {
            nativeLibraryPath.pop_back();
        }
        std::string libPath = LOCAL_CODE_PATH;
        libPath += (libPath.back() == '/') ? nativeLibraryPath : "/" + nativeLibraryPath;
        TAG_LOGD(AAFwkTag::APPKIT, "lib path = %{private}s", libPath.c_str());
        appLibPaths["default"].emplace_back(libPath);
        GetLibrarySupportDirectory(bundleInfo.hapModuleInfos, nativeLibraryPath, appLibPaths);
    } else {
        TAG_LOGI(AAFwkTag::APPKIT, "NativeLibPath empty");
    }

    for (auto &hapInfo : bundleInfo.hapModuleInfos) {
        TAG_LOGD(AAFwkTag::APPKIT,
            "moduleName: %{public}s, isLibIsolated: %{public}d, compressNativeLibs: %{public}d.",
            hapInfo.moduleName.c_str(), hapInfo.isLibIsolated, hapInfo.compressNativeLibs);
        GetPatchNativeLibPath(hapInfo, patchNativeLibraryPath, appLibPaths);
        GetHapSoPath(hapInfo, appLibPaths, hapInfo.hapPath.find(ABS_CODE_PATH));
    }

    for (auto &hspInfo : hspList) {
        TAG_LOGD(AAFwkTag::APPKIT, "bundle:%s, module:%s, nativeLibraryPath:%s", hspInfo.bundleName.c_str(),
            hspInfo.moduleName.c_str(), hspInfo.nativeLibraryPath.c_str());
        GetHspNativeLibPath(hspInfo, appLibPaths, hspInfo.hapPath.find(ABS_CODE_PATH) != 0u);
    }
}

void MainThread::GetPluginNativeLibPath(std::vector<AppExecFwk::PluginBundleInfo> &pluginBundleInfos,
    AppLibPathMap &appLibPaths)
{
    for (auto &pluginBundleInfo : pluginBundleInfos) {
        for (auto &pluginModuleInfo : pluginBundleInfo.pluginModuleInfos) {
            std::string libPath = pluginModuleInfo.nativeLibraryPath;
            if (!pluginModuleInfo.isLibIsolated) {
                libPath = pluginBundleInfo.nativeLibraryPath;
            }
            if (libPath.empty()) {
                continue;
            }
            std::string appLibPathKey = pluginBundleInfo.pluginBundleName + "/" + pluginModuleInfo.moduleName;
            libPath = std::string(LOCAL_CODE_PATH) + "/+plugins/" + libPath;
            TAG_LOGD(AAFwkTag::APPKIT, "appLibPathKey: %{private}s, libPath: %{private}s",
                appLibPathKey.c_str(), libPath.c_str());
            appLibPaths[appLibPathKey].emplace_back(libPath);
        }
    }
}

/**
 *
 * @brief Notify the AppMgrDeathRecipient that the remote is dead.
 *
 * @param remote The remote which is dead.
 */
void AppMgrDeathRecipient::OnRemoteDied(const wptr<IRemoteObject> &remote)
{
    TAG_LOGE(AAFwkTag::APPKIT, "remote died receive");
}

MainThread::MainThread()
{
#ifdef ABILITY_LIBRARY_LOADER
    fileEntries_.clear();
    nativeFileEntries_.clear();
    handleAbilityLib_.clear();
#endif  // ABILITY_LIBRARY_LOADER
}

MainThread::~MainThread()
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (watchdog_ != nullptr && !watchdog_->IsStopWatchdog()) {
        watchdog_->Stop();
        watchdog_ = nullptr;
    }
}

/**
 *
 * @brief Get the current MainThreadState.
 *
 * @return Returns the current MainThreadState.
 */
MainThreadState MainThread::GetMainThreadState() const
{
    return mainThreadState_;
}

/**
 *
 * @brief Set the runner state of mainthread.
 *
 * @param runnerStart whether the runner is started.
 */
void MainThread::SetRunnerStarted(bool runnerStart)
{
    isRunnerStarted_ = runnerStart;
}

/**
 *
 * @brief Get the runner state of mainthread.
 *
 * @return Returns the runner state of mainthread.
 */
bool MainThread::GetRunnerStarted() const
{
    return isRunnerStarted_;
}

/**
 *
 * @brief Get the newThreadId.
 *
 * @return Returns the newThreadId.
 */
int MainThread::GetNewThreadId()
{
    return newThreadId_++;
}

/**
 *
 * @brief Get the application.
 *
 * @return Returns the application.
 */
std::shared_ptr<OHOSApplication> MainThread::GetApplication() const
{
    return application_;
}

/**
 *
 * @brief Get the applicationInfo.
 *
 * @return Returns the applicationInfo.
 */
std::shared_ptr<ApplicationInfo> MainThread::GetApplicationInfo() const
{
    return applicationInfo_;
}

/**
 *
 * @brief Get the applicationImpl.
 *
 * @return Returns the applicationImpl.
 */
std::shared_ptr<ApplicationImpl> MainThread::GetApplicationImpl()
{
    return applicationImpl_;
}

/**
 *
 * @brief Connect the mainthread to the AppMgr.
 *
 */
bool MainThread::ConnectToAppMgr()
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    TAG_LOGD(AAFwkTag::APPKIT, "%{public}s start.", __func__);
    auto object = OHOS::DelayedSingleton<SysMrgClient>::GetInstance()->GetSystemAbility(APP_MGR_SERVICE_ID);
    if (object == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null object");
        return false;
    }
    deathRecipient_ = new (std::nothrow) AppMgrDeathRecipient();
    if (deathRecipient_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null deathRecipient_");
        return false;
    }

    if (!object->AddDeathRecipient(deathRecipient_)) {
        TAG_LOGE(AAFwkTag::APPKIT, "AddDeathRecipient failed");
        return false;
    }

    appMgr_ = iface_cast<IAppMgr>(object);
    if (appMgr_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null appMgr_");
        return false;
    }
    TAG_LOGI(AAFwkTag::APPKIT, "attach");
    appMgr_->AttachApplication(this);
    TAG_LOGD(AAFwkTag::APPKIT, "end");
    return true;
}

/**
 *
 * @brief Attach the mainthread to the AppMgr.
 *
 */
void MainThread::Attach()
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    TAG_LOGD(AAFwkTag::APPKIT, "Attach");
    if (!ConnectToAppMgr()) {
        TAG_LOGE(AAFwkTag::APPKIT, "attachApplication failed");
        return;
    }
    mainThreadState_ = MainThreadState::ATTACH;
    isDeveloperMode_ = system::GetBoolParameter(DEVELOPER_MODE_STATE, false);
    auto bundleMgrHelper = DelayedSingleton<BundleMgrHelper>::GetInstance();
    if (bundleMgrHelper == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null bundleMgrHelper");
        return;
    }
    bundleMgrHelper->PreConnect();
}

/**
 *
 * @brief remove the deathRecipient from appMgr.
 *
 */
void MainThread::RemoveAppMgrDeathRecipient()
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (appMgr_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "failed");
        return;
    }

    sptr<IRemoteObject> object = appMgr_->AsObject();
    if (object != nullptr) {
        object->RemoveDeathRecipient(deathRecipient_);
    } else {
        TAG_LOGE(AAFwkTag::APPKIT, "appMgr_->AsObject() failed");
    }
}

/**
 *
 * @brief Get the eventHandler of mainthread.
 *
 * @return Returns the eventHandler of mainthread.
 */
std::shared_ptr<EventHandler> MainThread::GetMainHandler() const
{
    return mainHandler_;
}

/**
 *
 * @brief Schedule the foreground lifecycle of application.
 *
 */
bool MainThread::ScheduleForegroundApplication()
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    FreezeUtil::GetInstance().AddAppLifecycleEvent(0, "ScheduleForegroundApplication");
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    wptr<MainThread> weak = this;
    auto task = [weak]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleForegroundApplication();
    };
    if (!mainHandler_->PostTask(task, "MainThread:ForegroundApplication")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
    auto tmpWatchdog = watchdog_;
    if (tmpWatchdog == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null Watch dog");
    } else {
        tmpWatchdog->SetBackgroundStatus(false);
    }
    return true;
}

/**
 *
 * @brief Schedule the background lifecycle of application.
 *
 */
void MainThread::ScheduleBackgroundApplication()
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    wptr<MainThread> weak = this;
    auto task = [weak]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleBackgroundApplication();
    };
    if (!mainHandler_->PostTask(task, "MainThread:BackgroundApplication")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }

    auto tmpWatchdog = watchdog_;
    if (tmpWatchdog == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null Watch dog");
        return;
    }
    tmpWatchdog->SetBackgroundStatus(true);
    tmpWatchdog = nullptr;
}

/**
 *
 * @brief Schedule the terminate lifecycle of application.
 *
 * @param isLastProcess When it is the last application process, pass in true.
 */
void MainThread::ScheduleTerminateApplication(bool isLastProcess)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    wptr<MainThread> weak = this;
    auto task = [weak, isLastProcess]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleTerminateApplication(isLastProcess);
    };
    if (!mainHandler_->PostTask(task, "MainThread:TerminateApplication")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
}

/**
 *
 * @brief Shrink the memory which used by application.
 *
 * @param level Indicates the memory trim level, which shows the current memory usage status.
 */
void MainThread::ScheduleShrinkMemory(const int level)
{
    TAG_LOGD(AAFwkTag::APPKIT, "level: %{public}d", level);
    wptr<MainThread> weak = this;
    auto task = [weak, level]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleShrinkMemory(level);
    };
    if (!mainHandler_->PostTask(task, "MainThread:ShrinkMemory")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
}

/**
 *
 * @brief Notify the memory level.
 *
 * @param level Indicates the memory trim level, which shows the current memory usage status.
 */
void MainThread::ScheduleMemoryLevel(const int level, bool isShellCall)
{
    TAG_LOGD(AAFwkTag::APPKIT, "level: %{public}d", level);
    wptr<MainThread> weak = this;
    auto task = [weak, level]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleMemoryLevel(level);
    };
    if (!mainHandler_->PostTask(task, "MainThread:MemoryLevel")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
}

/**
 *
 * @brief Get the application's memory allocation info.
 *
 * @param pid, pid input.
 * @param mallocInfo, dynamic storage information output.
 */
void MainThread::ScheduleHeapMemory(const int32_t pid, OHOS::AppExecFwk::MallocInfo &mallocInfo)
{
    struct mallinfo mi = mallinfo();
    uint64_t usmblks = mi.usmblks; // 当前从分配器中分配的总的堆内存大小
    uint64_t uordblks = mi.uordblks; // 当前已释放给分配器，分配缓存了未释放给系统的内存大小
    uint64_t fordblks = mi.fordblks; // 当前未释放的大小
    uint64_t hblkhd = mi.hblkhd; // 堆内存的总共占用大小
    TAG_LOGD(AAFwkTag::APPKIT, "The pid of the app we want to dump memory allocation information is: %{public}i", pid);
    TAG_LOGD(AAFwkTag::APPKIT, "usmblks: %{public}" PRIu64 ", uordblks: %{public}" PRIu64 ", "
        "fordblks: %{public}" PRIu64 ", hblkhd: %{public}" PRIu64 "", usmblks, uordblks, fordblks, hblkhd);
    mallocInfo.usmblks = usmblks;
    mallocInfo.uordblks = uordblks;
    mallocInfo.fordblks = fordblks;
    mallocInfo.hblkhd = hblkhd;
}

/**
 *
 * @brief the application triggerGC and dump jsheap memory.
 *
 * @param info, pid, tid, needGC, needSnapshot.
 */
void MainThread::ScheduleJsHeapMemory(OHOS::AppExecFwk::JsHeapDumpInfo &info)
{
    TAG_LOGI(AAFwkTag::APPKIT, "pid: %{public}d, tid: %{public}d, needGc: %{public}d, needSnapshot: %{public}d,\n"
        "needLeakobj: %{public}d, needBinary: %{public}d",
        info.pid, info.tid, info.needGc, info.needSnapshot, info.needLeakobj, info.needBinary);
    wptr<MainThread> weak = this;
    auto task = [weak, info]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleJsHeapMemory(info);
    };
    if (!mainHandler_->PostTask(task, "MainThread:HandleJsHeapMemory")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask HandleJsHeapMemory failed");
    }
}

/**
 *
 * @brief the application dump jshandle map.
 *
 * @param info, pid, tid.
 */
void MainThread::ScheduleJsHandleMap(OHOS::AppExecFwk::JsHandleMapInfo &info)
{
    TAG_LOGI(AAFwkTag::APPKIT, "pid: %{public}u, tid: %{public}u", info.pid, info.tid);
    wptr<MainThread> weak = this;
    auto task = [weak, info]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleJsHandleMap(info);
    };
    if (!mainHandler_->PostTask(task, "MainThread:HandleJsHandleMap")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask HandleJsHandleMap failed");
    }
}

/**
 *
 * @brief the application triggerGC and dump cjheap memory.
 *
 * @param info, pid, tid, needGC, needSnapshot.
 */
void MainThread::ScheduleCjHeapMemory(OHOS::AppExecFwk::CjHeapDumpInfo &info)
{
    TAG_LOGI(AAFwkTag::APPKIT, "pid: %{public}d, needGc: %{public}d, needSnapshot: %{public}d",
        info.pid, info.needGc, info.needSnapshot);
    wptr<MainThread> weak = this;
    auto task = [weak, info]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleCjHeapMemory(info);
    };
    if (!mainHandler_->PostTask(task, "MainThread:HandleCjHeapMemory")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask HandleCjHeapMemory failed");
    }
}

/**
 *
 * @brief triggerGC and dump application's memory info.
 *
 * @param info, pid, tid, needGC, needSnapshot.
 * @param callback The callback to receive dump result
 */
void MainThread::ScheduleMem(OHOS::AppExecFwk::MemDumpInfo &info, sptr<IMemDumpCallback> callback)
{
    wptr<MainThread> weak = this;
    auto task = [weak, info, callback]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleMem(info, callback);
    };
    if (!mainHandler_->PostTask(task, "MainThread:HandleMem")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask HandleMem failed");
    }
}

/**
 *
 * @brief Schedule the application process exit safely.
 *
 */
void MainThread::ScheduleProcessSecurityExit()
{
    wptr<MainThread> weak = this;
    auto task = [weak]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleProcessSecurityExit();
    };
    bool result = mainHandler_->PostTask(task, "MainThread:ProcessSecurityExit");
    if (!result) {
        TAG_LOGE(AAFwkTag::APPKIT, "post task failed");
    }
}

/**
 *
 * @brief Schedule the application clear recovery page stack.
 *
 */
void MainThread::ScheduleClearPageStack()
{
    TAG_LOGI(AAFwkTag::APPKIT, "ScheduleClearPageStack called");
    if (applicationInfo_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null applicationInfo_");
        return;
    }

    auto bundleName = applicationInfo_->bundleName;
    AppRecovery::GetInstance().ClearPageStack(bundleName);
}

/**
 *
 * @brief Low the memory which used by application.
 *
 */
void MainThread::ScheduleLowMemory()
{}

/**
 *
 * @brief Launch the application.
 *
 * @param data The launchdata of the application witch launced.
 *
 */
void MainThread::ScheduleLaunchApplication(const AppLaunchData &data, const Configuration &config)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    FreezeUtil::GetInstance().AddAppLifecycleEvent(0, "ScheduleLaunchApplication");
    wptr<MainThread> weak = this;
    auto task = [weak, data, config]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleInitAssertFaultTask(data.GetDebugApp(), data.GetApplicationInfo().debug);
        appThread->HandleLaunchApplication(data, config);
        AbilityRuntime::ExtNativeStartupManager::GetInstance().RunPhaseTasks(
            AbilityRuntime::SchedulerPhase::PostLaunchApplication);
    };
    if (!mainHandler_->PostTask(task, "MainThread:LaunchApplication")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
}

/**
 *
 * @brief update the application info after new module installed.
 *
 * @param appInfo The latest application info obtained from bms for update abilityRuntimeContext.
 *
 */
void MainThread::ScheduleUpdateApplicationInfoInstalled(const ApplicationInfo &appInfo, const std::string &moduleName)
{
    TAG_LOGD(AAFwkTag::APPKIT, "ScheduleUpdateApplicationInfoInstalled");
    wptr<MainThread> weak = this;
    auto task = [weak, appInfo, moduleName]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        if (appInfo.bundleType != AppExecFwk::BundleType::APP_PLUGIN) {
            appThread->HandleUpdateApplicationInfoInstalled(appInfo, moduleName);
        } else {
            appThread->HandleUpdatePluginInfoInstalled(appInfo, moduleName);
        }
    };
    if (!mainHandler_->PostTask(task, "MainThread:UpdateApplicationInfoInstalled")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
}

void MainThread::ScheduleAbilityStage(const HapModuleInfo &abilityStage)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    wptr<MainThread> weak = this;
    auto task = [weak, abilityStage]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleAbilityStage(abilityStage);
    };
    if (!mainHandler_->PostTask(task, "MainThread:AbilityStage")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
}

bool MainThread::IsBgWorkingThread(const AbilityInfo &info)
{
    return info.extensionAbilityType == ExtensionAbilityType::BACKUP;
}

void MainThread::ScheduleLaunchAbility(const AbilityInfo &info, const sptr<IRemoteObject> &token,
    const std::shared_ptr<AAFwk::Want> &want, int32_t abilityRecordId, const std::shared_ptr<AppUpdateInfo> updateInfo)
{
    HITRACE_METER_NAME(HITRACE_TAG_ABILITY_MANAGER, __PRETTY_FUNCTION__);
    TAG_LOGI(AAFwkTag::APPKIT, "%{public}s called,ability %{public}s,%{public}d",
        __func__, info.name.c_str(), info.type);

    bool skipAbilityStageLifecycle = false;
    if (want != nullptr) {
        skipAbilityStageLifecycle = want->GetBoolParam(KEY_SKIP_ABILITY_STAGE_LIFECYCLE, false);
        want->RemoveParam(KEY_SKIP_ABILITY_STAGE_LIFECYCLE);
        AAFwk::Want newWant(*want);
        newWant.CloseAllFd();
    }
    std::shared_ptr<AbilityInfo> abilityInfo = std::make_shared<AbilityInfo>(info);
    auto abilityRecord = std::make_shared<AbilityLocalRecord>(abilityInfo, token, want, abilityRecordId);
    abilityRecord->SetSkipAbilityStageLifecycle(skipAbilityStageLifecycle);
    auto tmpWatchdog = watchdog_;
    if (tmpWatchdog != nullptr) {
        tmpWatchdog->SetBgWorkingThreadStatus(IsBgWorkingThread(info));
        tmpWatchdog = nullptr;
    }
    std::string entry = "MainThread::ScheduleLaunchAbility";
    FreezeUtil::GetInstance().AddLifecycleEvent(token, entry);

    wptr<MainThread> weak = this;
    auto task = [weak, abilityRecord, updateInfo]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleLaunchAbility(abilityRecord, updateInfo);
        OHOS::AppExecFwk::EventHandler::SetVsyncLazyMode(true);
    };
    if (!mainHandler_->PostTask(task, "MainThread:LaunchAbility")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
}

/**
 *
 * @brief clean the ability by token.
 *
 * @param token The token belong to the ability which want to be cleaned.
 *
 */
void MainThread::ScheduleCleanAbility(const sptr<IRemoteObject> &token, bool isCacheProcess)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called, with isCacheProcess =%{public}d.", isCacheProcess);
    FreezeUtil::GetInstance().DeleteAppLifecycleEvent(0);
    FreezeUtil::GetInstance().DeleteLifecycleEvent(token);
    wptr<MainThread> weak = this;
    auto task = [weak, token, isCacheProcess]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleCleanAbility(token, isCacheProcess);
    };
    if (!mainHandler_->PostTask(task, "MainThread:CleanAbility")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
}

/**
 *
 * @brief send the new profile.
 *
 * @param profile The updated profile.
 *
 */
void MainThread::ScheduleProfileChanged(const Profile &profile)
{
    TAG_LOGD(AAFwkTag::APPKIT, "profile name: %{public}s", profile.GetName().c_str());
}

/**
 *
 * @brief send the new config to the application.
 *
 * @param config The updated config.
 * @param reason The updated configuration scene flag.
 */
void MainThread::ScheduleConfigurationUpdated(const Configuration &config, ConfigUpdateReason reason)
{
    HITRACE_METER_NAME(HITRACE_TAG_ABILITY_MANAGER, __PRETTY_FUNCTION__);
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    wptr<MainThread> weak = this;
    auto task = [weak, config, reason]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleConfigurationUpdated(config, reason);
    };
    if (!mainHandler_->PostTask(task, "MainThread:ConfigurationUpdated")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
}

bool MainThread::CheckLaunchApplicationParam(const AppLaunchData &appLaunchData) const
{
    if (appLaunchData.GetApplicationInfo().name.empty()) {
        TAG_LOGE(AAFwkTag::APPKIT, "applicationName empty");
        return false;
    }

    if (appLaunchData.GetProcessInfo().GetProcessName().empty()) {
        TAG_LOGE(AAFwkTag::APPKIT, "processName empty");
        return false;
    }
    return true;
}

/**
 *
 * @brief Check whether the record is legal.
 *
 * @param record The record should be checked.
 *
 * @return if the record is legal, return true. else return false.
 */
bool MainThread::CheckAbilityItem(const std::shared_ptr<AbilityLocalRecord> &record) const
{
    if (record == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null record");
        return false;
    }

    std::shared_ptr<AbilityInfo> abilityInfo = record->GetAbilityInfo();
    sptr<IRemoteObject> token = record->GetToken();

    if (abilityInfo == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null abilityInfo");
        return false;
    }

    if (token == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null token");
        return false;
    }
    return true;
}

/**
 *
 * @brief Terminate the application but don't notify ams.
 *
 */
void MainThread::HandleTerminateApplicationLocal()
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (applicationImpl_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "error");
        return;
    }
    applicationImpl_->PerformTerminateStrong();

    std::shared_ptr<EventRunner> runner = mainHandler_->GetEventRunner();
    if (runner == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null runner");
        return;
    }

    if (watchdog_ != nullptr && !watchdog_->IsStopWatchdog()) {
        watchdog_->Stop();
        watchdog_ = nullptr;
    }

    int ret = runner->Stop();
    if (ret != ERR_OK) {
        TAG_LOGE(AAFwkTag::APPKIT, "ret = %{public}d", ret);
    }

    TAG_LOGD(AAFwkTag::APPKIT, "runner is stopped");
    SetRunnerStarted(false);
    HandleCancelAssertFaultTask();
}

void MainThread::HandleJsHeapMemory(const OHOS::AppExecFwk::JsHeapDumpInfo &info)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (mainHandler_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null mainHandler");
        return;
    }
    auto app = applicationForDump_.lock();
    if (app == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null app");
        return;
    }
    auto helper = std::make_shared<DumpRuntimeHelper>(app, applicationInfo_);
    helper->DumpJsHeap(info);
}

void MainThread::HandleJsHandleMap(const OHOS::AppExecFwk::JsHandleMapInfo &info)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (mainHandler_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null mainHandler");
        return;
    }
    auto app = applicationForDump_.lock();
    if (app == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null app");
        return;
    }
    auto helper = std::make_shared<DumpRuntimeHelper>(app, applicationInfo_);
    helper->DumpJsHandleMap(info);
}

void MainThread::HandleCjHeapMemory(const OHOS::AppExecFwk::CjHeapDumpInfo &info)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (mainHandler_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null mainHandler");
        return;
    }
    auto app = applicationForDump_.lock();
    if (app == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null app");
        return;
    }
    std::shared_ptr<DumpRuntimeHelper> helper;
    try {
        helper = std::make_shared<DumpRuntimeHelper>(app);
    } catch (const std::bad_alloc& e) {
        TAG_LOGE(AAFwkTag::APPKIT, "Failed to create DumpRuntimeHelper: %s", e.what());
        return;
    } catch (const std::exception& e) {
        TAG_LOGE(AAFwkTag::APPKIT, "Failed to create DumpRuntimeHelper: %s", e.what());
        return;
    } catch (...) {
        TAG_LOGE(AAFwkTag::APPKIT, "Failed to create DumpRuntimeHelper: unknown exception");
        return;
    }
    try {
        helper->DumpCjHeap(info);
    } catch (const std::exception& e) {
        TAG_LOGE(AAFwkTag::APPKIT, "DumpCjHeap failed: %s", e.what());
        return;
    } catch (...) {
        TAG_LOGE(AAFwkTag::APPKIT, "DumpCjHeap failed: unknown exception");
        return;
    }
}

void MainThread::HandleMem(const OHOS::AppExecFwk::MemDumpInfo &info, sptr<IMemDumpCallback> callback)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (mainHandler_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null mainHandler");
        return;
    }
    auto app = applicationForDump_.lock();
    if (app == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null app");
        return;
    }
    auto helper = std::make_shared<DumpRuntimeHelper>(app);
    helper->DumpMem(info, callback);
}

/**
 *
 * @brief Schedule the application process exit safely.
 *
 */
void MainThread::HandleProcessSecurityExit()
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    TAG_LOGD(AAFwkTag::APPKIT, "HandleProcessSecurityExit");
    if (abilityRecordMgr_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null abilityRecordMgr_");
        return;
    }
    if (application_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null application_");
        return;
    }
    std::vector<sptr<IRemoteObject>> tokens = abilityRecordMgr_->GetAllTokens();

    for (auto iter = tokens.begin(); iter != tokens.end(); ++iter) {
        HandleCleanAbilityLocal(*iter);
    }

    // in process cache state, there can be abilityStage with no abilities
    application_->CleanEmptyAbilityStage();

    HandleTerminateApplicationLocal();
}

bool MainThread::InitCreate(
    std::shared_ptr<ContextDeal> &contextDeal, ApplicationInfo &appInfo, ProcessInfo &processInfo)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    // get application shared point
    application_ = std::shared_ptr<OHOSApplication>(ApplicationLoader::GetInstance().GetApplicationByName());
    if (application_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "create failed");
        return false;
    }

    applicationInfo_ = std::make_shared<ApplicationInfo>(appInfo);
    if (applicationInfo_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null applicationInfo_");
        return false;
    }

    processInfo_ = std::make_shared<ProcessInfo>(processInfo);
    if (processInfo_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null processInfo_");
        return false;
    }

    applicationImpl_ = std::make_shared<ApplicationImpl>();
    if (applicationImpl_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null applicationImpl_");
        return false;
    }

    abilityRecordMgr_ = std::make_shared<AbilityRecordMgr>();
    if (abilityRecordMgr_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null AbilityRecordMgr");
        return false;
    }

    contextDeal = std::make_shared<ContextDeal>();
    if (contextDeal == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null contextDeal");
        return false;
    }
    AppExecFwk::AppfreezeInner::GetInstance()->SetApplicationInfo(applicationInfo_);

    application_->SetProcessInfo(processInfo_);
    contextDeal->SetApplicationInfo(applicationInfo_);
    contextDeal->SetBundleCodePath(applicationInfo_->codePath);  // BMS need to add cpath

    return true;
}

bool MainThread::CheckForHandleLaunchApplication(const AppLaunchData &appLaunchData)
{
    if (!CheckLaunchApplicationParam(appLaunchData)) {
        TAG_LOGE(AAFwkTag::APPKIT, "appLaunchData invalid");
        return false;
    }
    return true;
}

bool MainThread::InitResourceManager(std::shared_ptr<Global::Resource::ResourceManager> &resourceManager,
    const AppExecFwk::HapModuleInfo &entryHapModuleInfo, const std::string &bundleName,
    const Configuration &config, const ApplicationInfo &appInfo)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    bool isStageBased = entryHapModuleInfo.isStageBasedModel;
    if (isStageBased && appInfo.multiProjects) {
        TAG_LOGI(AAFwkTag::APPKIT, "multiProjects");
    } else {
        OnStartAbility(bundleName, resourceManager, entryHapModuleInfo, appInfo.debug);
    }

    std::unique_ptr<Global::Resource::ResConfig> resConfig(Global::Resource::CreateResConfig());
#if defined(SUPPORT_GRAPHICS) && defined(SUPPORT_APP_PREFERRED_LANGUAGE)
    icu::Locale systemLocale = Global::I18n::LocaleConfigExt::GetIcuLocale(
        config.GetItem(AAFwk::GlobalConfigurationKey::SYSTEM_LANGUAGE));

    resConfig->SetLocaleInfo(systemLocale);

    if (Global::I18n::PreferredLanguage::IsSetAppPreferredLanguage()) {
        UErrorCode status = U_ZERO_ERROR;
        icu::Locale preferredLocale =
            icu::Locale::forLanguageTag(Global::I18n::PreferredLanguage::GetAppPreferredLanguage(), status);
        resConfig->SetPreferredLocaleInfo(preferredLocale);
        AbilityRuntime::ApplicationConfigurationManager::GetInstance().SetLanguageSetLevel(
            AbilityRuntime::SetLevel::Application);
    }
#endif
    std::string colormode = config.GetItem(AAFwk::GlobalConfigurationKey::SYSTEM_COLORMODE);
    TAG_LOGD(AAFwkTag::APPKIT, "Colormode is %{public}s", colormode.c_str());
    resConfig->SetColorMode(ConvertColorMode(colormode));

    std::string hasPointerDevice = config.GetItem(AAFwk::GlobalConfigurationKey::INPUT_POINTER_DEVICE);
    TAG_LOGD(AAFwkTag::APPKIT, "HasPointerDevice is %{public}s", hasPointerDevice.c_str());
    resConfig->SetInputDevice(ConvertHasPointerDevice(hasPointerDevice));

    std::string deviceType = config.GetItem(AAFwk::GlobalConfigurationKey::DEVICE_TYPE);
    TAG_LOGD(AAFwkTag::APPKIT, "deviceType is %{public}s <---->  %{public}d", deviceType.c_str(),
        ConvertDeviceType(deviceType));
    resConfig->SetDeviceType(ConvertDeviceType(deviceType));

    std::string mcc = config.GetItem(AAFwk::GlobalConfigurationKey::SYSTEM_MCC);
    TAG_LOGD(AAFwkTag::APPKIT, "mcc is %{public}s", mcc.c_str());
    uint32_t mccNum = 0;
    if (AbilityRuntime::ResourceConfigHelper::ConvertStringToUint32(mcc, mccNum)) {
        resConfig->SetMcc(mccNum);
    }

    std::string mnc = config.GetItem(AAFwk::GlobalConfigurationKey::SYSTEM_MNC);
    TAG_LOGD(AAFwkTag::APPKIT, "mnc is %{public}s", mnc.c_str());
    uint32_t mncNum = 0;
    if (AbilityRuntime::ResourceConfigHelper::ConvertStringToUint32(mnc, mncNum)) {
        resConfig->SetMnc(mncNum);
    }

    resourceManager->UpdateResConfig(*resConfig);
    return true;
}

void MainThread::OnStartAbility(const std::string &bundleName,
    std::shared_ptr<Global::Resource::ResourceManager> &resourceManager,
    const AppExecFwk::HapModuleInfo &entryHapModuleInfo, const bool isDebugApp)
{
    std::regex pattern(std::string(ABS_CODE_PATH) + std::string(FILE_SEPARATOR) + bundleName);
    std::string loadPath =
        (!entryHapModuleInfo.hapPath.empty()) ? entryHapModuleInfo.hapPath : entryHapModuleInfo.resourcePath;
    if (!loadPath.empty()) {
        loadPath = std::regex_replace(loadPath, pattern, std::string(LOCAL_CODE_PATH));
        TAG_LOGD(AAFwkTag::APPKIT, "ModuleResPath: %{public}s", loadPath.c_str());
        // getOverlayPath
        if (overlayModuleInfos_.empty()) {
            if (!resourceManager->AddResource(loadPath.c_str())) {
                TAG_LOGE(AAFwkTag::APPKIT, "AddResource failed");
            }
        } else {
            std::vector<std::string> overlayPaths = GetOverlayPaths(bundleName, overlayModuleInfos_);
            TAG_LOGD(AAFwkTag::APPKIT, "OverlayPaths size:%{public}zu", overlayPaths.size());
            if (!resourceManager->AddResource(loadPath, overlayPaths)) {
                TAG_LOGE(AAFwkTag::APPKIT, "AddResource failed");
            }
            SubscribeOverlayChange(bundleName, loadPath, resourceManager, entryHapModuleInfo);
        }
        std::string hqfPath = entryHapModuleInfo.hqfInfo.hqfFilePath;
        if (!hqfPath.empty() && isDebugApp) {
            hqfPath = std::regex_replace(hqfPath, pattern, std::string(LOCAL_CODE_PATH));
            TAG_LOGI(AAFwkTag::APPKIT, "AddPatchResource hapPath:%{public}s, patchPath:%{public}s",
                loadPath.c_str(), hqfPath.c_str());
            if (!resourceManager->AddPatchResource(loadPath.c_str(), hqfPath.c_str())) {
                TAG_LOGE(AAFwkTag::APPKIT, "AddPatchResource failed");
            }
        }
    }
}

std::vector<std::string> MainThread::GetOverlayPaths(const std::string &bundleName,
    const std::vector<OverlayModuleInfo> &overlayModuleInfos)
{
    std::vector<std::string> overlayPaths;
    for (auto &it : overlayModuleInfos_) {
        if (std::regex_search(it.hapPath, std::regex(bundleName))) {
            it.hapPath = std::regex_replace(it.hapPath, std::regex(std::string(ABS_CODE_PATH) +
                std::string(FILE_SEPARATOR) + bundleName), std::string(LOCAL_CODE_PATH));
        } else {
            it.hapPath = std::regex_replace(it.hapPath, std::regex(ABS_CODE_PATH), LOCAL_BUNDLES);
        }
        if (it.state == OverlayState::OVERLAY_ENABLE) {
            TAG_LOGD(AAFwkTag::APPKIT, "hapPath: %{public}s", it.hapPath.c_str());
            overlayPaths.emplace_back(it.hapPath);
        }
    }
    return overlayPaths;
}

void MainThread::SubscribeOverlayChange(const std::string &bundleName, const std::string &loadPath,
    std::shared_ptr<Global::Resource::ResourceManager> &resourceManager,
    const AppExecFwk::HapModuleInfo &entryHapModuleInfo)
{
    // add listen overlay change
    EventFwk::MatchingSkills matchingSkills;
    matchingSkills.AddEvent(OVERLAY_STATE_CHANGED);
    EventFwk::CommonEventSubscribeInfo subscribeInfo(matchingSkills);
    subscribeInfo.SetThreadMode(EventFwk::CommonEventSubscribeInfo::COMMON);
    subscribeInfo.SetPublisherUid(FOUNDATION_UID);
    wptr<MainThread> weak = this;
    auto callback = [weak, resourceManager, bundleName, moduleName = entryHapModuleInfo.moduleName,
        loadPath](const EventFwk::CommonEventData &data) {
        TAG_LOGD(AAFwkTag::APPKIT, "On overlay changed");
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->OnOverlayChanged(data, resourceManager, bundleName, moduleName, loadPath);
    };
    auto subscriber = std::make_shared<OverlayEventSubscriber>(subscribeInfo, callback);
    bool subResult = EventFwk::CommonEventManager::SubscribeCommonEvent(subscriber);
    TAG_LOGD(AAFwkTag::APPKIT, "Overlay event subscriber register result is %{public}d", subResult);
}

void MainThread::OnOverlayChanged(const EventFwk::CommonEventData &data,
    const std::shared_ptr<Global::Resource::ResourceManager> &resourceManager, const std::string &bundleName,
    const std::string &moduleName, const std::string &loadPath)
{
    if (mainHandler_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null mainHandler");
        return;
    }
    wptr<MainThread> weak = this;
    auto task = [weak, data, resourceManager, bundleName, moduleName, loadPath]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleOnOverlayChanged(data, resourceManager, bundleName, moduleName, loadPath);
    };
    if (!mainHandler_->PostTask(task, "MainThread:OnOverlayChanged")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
}

void MainThread::HandleOnOverlayChanged(const EventFwk::CommonEventData &data,
    const std::shared_ptr<Global::Resource::ResourceManager> &resourceManager, const std::string &bundleName,
    const std::string &moduleName, const std::string &loadPath)
{
    TAG_LOGD(AAFwkTag::APPKIT, "begin");
    auto want = data.GetWant();
    std::string action = want.GetAction();
    if (action != OVERLAY_STATE_CHANGED) {
        TAG_LOGD(AAFwkTag::APPKIT, "Not this subscribe, action: %{public}s", action.c_str());
        return;
    }
    bool isEnable = data.GetWant().GetBoolParam(Constants::OVERLAY_STATE, false);
    // 1.get overlay hapPath
    if (resourceManager == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null resourceManager");
        return;
    }
    std::vector<OverlayModuleInfo> overlayModuleInfos;
    auto res = GetOverlayModuleInfos(bundleName, moduleName, overlayModuleInfos);
    if (res != ERR_OK) {
        return;
    }

    // 2.add/remove overlay hapPath
    if (loadPath.empty() || overlayModuleInfos.empty()) {
        TAG_LOGW(AAFwkTag::APPKIT, "hapPath empty");
    } else {
        if (isEnable) {
            std::vector<std::string> overlayPaths = GetAddOverlayPaths(overlayModuleInfos);
            if (!resourceManager->AddResource(loadPath, overlayPaths)) {
                TAG_LOGE(AAFwkTag::APPKIT, "AddResource failed");
            }
        } else {
            std::vector<std::string> overlayPaths = GetRemoveOverlayPaths(overlayModuleInfos);
            if (!resourceManager->RemoveResource(loadPath, overlayPaths)) {
                TAG_LOGE(AAFwkTag::APPKIT, "RemoveResource failed");
            }
        }
    }
}

bool IsNeedLoadLibrary(const std::string &bundleName)
{
    std::vector<std::string> needLoadLibraryBundleNames{
        "com.ohos.contactsdataability",
        "com.ohos.medialibrary.medialibrarydata",
        "com.ohos.ringtonelibrary.ringtonelibrarydata",
        "com.ohos.telephonydataability",
        "com.ohos.FusionSearch",
        "com.ohos.formrenderservice"
    };

    return std::find(needLoadLibraryBundleNames.begin(), needLoadLibraryBundleNames.end(), bundleName)
        != needLoadLibraryBundleNames.end();
}

bool GetBundleForLaunchApplication(std::shared_ptr<BundleMgrHelper> bundleMgrHelper, const std::string &bundleName,
    int32_t appIndex, BundleInfo &bundleInfo)
{
    bool queryResult;
    if (AbilityRuntime::GlobalConstant::IsDlpIndex(appIndex)) {
        TAG_LOGD(AAFwkTag::APPKIT, "The bundleName = %{public}s", bundleName.c_str());
        queryResult = (bundleMgrHelper->GetSandboxBundleInfo(bundleName,
            appIndex, UNSPECIFIED_USERID, bundleInfo) == 0);
    } else {
        TAG_LOGD(AAFwkTag::APPKIT, "The bundleName = %{public}s", bundleName.c_str());
        queryResult = (bundleMgrHelper->GetBundleInfoForSelf(
            (static_cast<int32_t>(GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_EXTENSION_ABILITY) +
            static_cast<int32_t>(GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_HAP_MODULE) +
            static_cast<int32_t>(GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_DISABLE) +
            static_cast<int32_t>(GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_APPLICATION) +
            static_cast<int32_t>(GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_SIGNATURE_INFO) +
            static_cast<int32_t>(GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_ABILITY) +
#ifdef SUPPORT_GRAPHICS
            static_cast<int32_t>(GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_REQUESTED_PERMISSION) +
#endif
            static_cast<int32_t>(GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_METADATA)), bundleInfo) == ERR_OK);
    }
    return queryResult;
}
#ifdef CJ_FRONTEND
CJUncaughtExceptionInfo MainThread::CreateCjExceptionInfo(const std::string &bundleName,
    uint32_t versionCode, const std::string &hapPath, const std::string &appRunningId)
{
    CJUncaughtExceptionInfo uncaughtExceptionInfo;
    wptr<MainThread> weak_this = this;
    std::string processName = processInfo_ != nullptr ? processInfo_->GetProcessName() : "unknown";
    uncaughtExceptionInfo.hapPath = hapPath.c_str();
    uncaughtExceptionInfo.uncaughtTask = [weak_this, bundleName, versionCode, processName, appRunningId]
        (std::string summary, const CJErrorObject errorObj) {
            auto appThread = weak_this.promote();
            if (appThread == nullptr) {
                TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
                return;
            }
            time_t timet;
            time(&timet);
            std::string errName = errorObj.name ? errorObj.name : "[none]";
            std::string errMsg = errorObj.message ? errorObj.message : "[none]";
            std::string errStack = errorObj.stack ? errorObj.stack : "[none]";
            std::string errSummary = summary + "\nException info: " + errMsg + "\n" + "Stacktrace:\n" + errStack;
            auto hisyseventReport = std::make_shared<HisyseventReport>(10);
            hisyseventReport->InsertParam(EVENT_KEY_PACKAGE_NAME, bundleName);
            hisyseventReport->InsertParam(EVENT_KEY_VERSION, std::to_string(versionCode));
            hisyseventReport->InsertParam(EVENT_KEY_TYPE, CJERROR_TYPE);
            hisyseventReport->InsertParam(EVENT_KEY_HAPPEN_TIME, timet);
            hisyseventReport->InsertParam(EVENT_KEY_REASON, errName);
            hisyseventReport->InsertParam(EVENT_KEY_JSVM, JSVM_TYPE);
            hisyseventReport->InsertParam(EVENT_KEY_SUMMARY, errSummary);
            hisyseventReport->InsertParam(EVENT_KEY_PNAME, processName);
            hisyseventReport->InsertParam(EVENT_KEY_APP_RUNNING_UNIQUE_ID, appRunningId);
            hisyseventReport->InsertParam(EVENT_KEY_THREAD_NAME, DumpProcessHelper::GetThreadName());
            hisyseventReport->InsertParam(EVENT_KEY_PROCESS_RSS_MEMINFO,
                std::to_string(DumpProcessHelper::GetProcRssMemInfo()));
            hisyseventReport->Report("CJ_RUNTIME", "CJ_ERROR", HISYSEVENT_FAULT);
            ErrorObject appExecErrorObj = {
                .name = errName,
                .message = errMsg,
                .stack = errStack
            };
            FaultData faultData;
            faultData.faultType = FaultDataType::CJ_ERROR;
            faultData.errorObject = appExecErrorObj;
            DelayedSingleton<AppExecFwk::AppMgrClient>::GetInstance()->NotifyAppFault(faultData);
            if (ApplicationDataManager::GetInstance().NotifyCJUnhandledException(summary) &&
                ApplicationDataManager::GetInstance().NotifyCJExceptionObject(appExecErrorObj)) {
                return;
            }
            // if app's callback has been registered, let app decide whether exit or not.
            TAG_LOGE(AAFwkTag::APPKIT,
                "\n%{public}s is about to exit due to RuntimeError\nError type:%{public}s\n%{public}s\n"
                "message: %{public}s\nstack: %{public}s",
                bundleName.c_str(), errName.c_str(), summary.c_str(), errMsg.c_str(), errStack.c_str());
            AAFwk::ExitReason exitReason = { REASON_CJ_ERROR, errName };
            AbilityManagerClient::GetInstance()->RecordAppExitReason(exitReason);
            appThread->ScheduleProcessSecurityExit();
        };
    return uncaughtExceptionInfo;
}

CJEventReportInfo MainThread::CreateCjEventReportInfo(const std::string &bundleName,
    uint32_t versionCode, const std::string &hapPath, std::string &appRunningId)
{
    CJEventReportInfo reportInfo;
    wptr<MainThread> weak_this = this;
    reportInfo.hapPath = hapPath.c_str();
    std::string processName = processInfo_ != nullptr ? processInfo_->GetProcessName() : "unknown";
    reportInfo.reportInfoTask = [weak_this, bundleName, versionCode, processName, appRunningId =
        std::move(appRunningId)](const char* domain,
        const char* event, size_t hiSysEventType, const std::map<std::string, std::string>& params) {
            auto shared_this = weak_this.promote();
            if (shared_this == nullptr) {
                return;
            }
            time_t timet;
            time(&timet);
            auto hisyseventReport = std::make_shared<HisyseventReport>(10);
            hisyseventReport->InsertParam("PID", std::to_string(getpid()));
            hisyseventReport->InsertParam("TID", std::to_string(gettid()));
            hisyseventReport->InsertParam("PROCESS_NAME", processName);
            hisyseventReport->InsertParam("APP_RUNNING_UNIQUE_ID", appRunningId);
            for (const auto& [key, value] : params) {
                hisyseventReport->InsertParam(key.c_str(), value);
            }
            int32_t ret = hisyseventReport->Report(domain, event, static_cast<HiSysEventEventType>(hiSysEventType));
            auto it = params.find("DUMP_LOG_PATH");
            if (it != params.end() && it->second == "EMPTY") {
                TAG_LOGI(AAFwkTag::APPKIT, "DUMP_LOG_PATH is EMPTY, trigger CJ heap dump");
                OHOS::AppExecFwk::CjHeapDumpInfo cjHeapInfo;
                cjHeapInfo.needSnapshot = true;
                cjHeapInfo.needGc = false;
                cjHeapInfo.pid = getpid();
                shared_this->HandleCjHeapMemory(cjHeapInfo);
            }
        };
    return reportInfo;
}
#endif

bool MainThread::GetBundleAndHspListForUpdateRuntime(BundleInfo &bundleInfo, std::string bundleName, HspList &hspList)
{
    std::shared_ptr<ContextDeal> contextDeal = std::make_shared<ContextDeal>();
    contextDeal->SetApplicationInfo(applicationInfo_);
    contextDeal->SetBundleCodePath(applicationInfo_->codePath);
    auto bundleMgrHelper = contextDeal->GetBundleManager();
    if (bundleMgrHelper == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null bundleMgrHelper");
        return false;
    }

    ErrCode ret = bundleMgrHelper->GetBundleInfoForSelf (
        (static_cast<int32_t>(GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_HAP_MODULE) +
        static_cast<int32_t>(GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_APPLICATION)), bundleInfo);
    if (ret != ERR_OK) {
        TAG_LOGE(AAFwkTag::APPKIT, "get bundle Info failed: %{public}d", ret);
        return false;
    }

    ret = bundleMgrHelper->GetBaseSharedBundleInfos(bundleName, hspList,
    AppExecFwk::GetDependentBundleInfoFlag::GET_ALL_DEPENDENT_BUNDLE_INFO);
    if (ret != ERR_OK) {
        TAG_LOGE(AAFwkTag::APPKIT, "Get base shared bundle infos failed: %{public}d", ret);
        return false;
    }
    return true;
}

EtsEnv::ETSUncaughtExceptionInfo MainThread::CreateEtsExceptionInfo(const std::string &bundleName, uint32_t versionCode,
    const std::string &hapPath, std::string &appRunningId, int32_t pid, std::string &processName)
{
    EtsEnv::ETSUncaughtExceptionInfo uncaughtExceptionInfo;
    wptr<MainThread> weak = this;
    uncaughtExceptionInfo.uncaughtTask = [weak, bundleName, versionCode, appRunningId = std::move(appRunningId), pid,
                                             processName](std::string summary, const EtsEnv::ETSErrorObject errorObj) {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        time_t timet;
        time(&timet);
        auto hisyseventReport = std::make_shared<HisyseventReport>(11);
        hisyseventReport->InsertParam(EVENT_KEY_PACKAGE_NAME, bundleName);
        hisyseventReport->InsertParam(EVENT_KEY_VERSION, std::to_string(versionCode));
        hisyseventReport->InsertParam(EVENT_KEY_TYPE, JSCRASH_TYPE);
        hisyseventReport->InsertParam(EVENT_KEY_HAPPEN_TIME, timet);
        hisyseventReport->InsertParam(EVENT_KEY_REASON, errorObj.name);
        hisyseventReport->InsertParam(EVENT_KEY_JSVM, JSVM_TYPE);
        hisyseventReport->InsertParam(EVENT_KEY_SUMMARY, summary);
        hisyseventReport->InsertParam(EVENT_KEY_PNAME, processName);
        hisyseventReport->InsertParam(EVENT_KEY_APP_RUNNING_UNIQUE_ID, appRunningId);
        hisyseventReport->InsertParam(EVENT_KEY_PROCESS_RSS_MEMINFO,
            std::to_string(DumpProcessHelper::GetProcRssMemInfo()));
        hisyseventReport->InsertParam(EVENT_KEY_THREAD_NAME, DumpProcessHelper::GetThreadName());
        hisyseventReport->Report("AAFWK", "JS_ERROR", HISYSEVENT_FAULT);
        ErrorObject appExecErrorObj = { .name = errorObj.name, .message = errorObj.message, .stack = errorObj.stack };
        FaultData faultData;
        faultData.faultType = FaultDataType::JS_ERROR;
        faultData.errorObject = appExecErrorObj;
        AAFwk::ExitReasonCompability exitReason = { REASON_JS_ERROR, errorObj.name };
        exitReason.killId = HiviewDFX::ProcessKillReason::KillEventId::REASON_JS_ERROR;
        std::string eventKeyReason = "JsError";
        exitReason.killMsg = eventKeyReason;
        exitReason.innerMsg = eventKeyReason;
        bool foreground = false;
        if (appThread->applicationImpl_ &&
            appThread->applicationImpl_->GetState() == ApplicationImpl::APP_STATE_FOREGROUND) {
            foreground = true;
        }
        auto result = AbilityManagerClient::GetInstance()->RecordAppWithReason(pid, getuid(), exitReason);
        TAG_LOGW(AAFwkTag::APPKIT, "Record result=%{public}d, send event [FRAMEWORK,PROCESS_KILL], "
            "pid=%{public}d, processName=%{public}s, msg=%{public}s, foreground=%{public}d",
            result, pid, processName.c_str(), eventKeyReason.c_str(), foreground);
        DelayedSingleton<AppExecFwk::AppMgrClient>::GetInstance()->NotifyAppFault(faultData);
        if (ApplicationDataManager::GetInstance().NotifyETSErrorObject(appExecErrorObj)) {
            return;
        }
        TAG_LOGE(AAFwkTag::APPKIT, "\n%{public}s is about to exit due to RuntimeError\nError "
            "type:%{public}s\n%{public}s", bundleName.c_str(), errorObj.name.c_str(), summary.c_str());
        _exit(JS_ERROR_EXIT);
    };
    return uncaughtExceptionInfo;
}
/**
 *
 * @brief Launch the application.
 *
 * @param appLaunchData The launchdata of the application witch launced.
 *
 */
void MainThread::HandleLaunchApplication(const AppLaunchData &appLaunchData, const Configuration &config)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    ForkAllHelper::HandleDebugAppLaunchDelay(appLaunchData, isDeveloperMode_);
    FreezeUtil::GetInstance().AddAppLifecycleEvent(0, "HandleLaunchApplication begin");
    ffrt::submit([]() {}, ffrt::task_attr().qos(LAUNCH_TASK_QOS));
    AppExecFwk::AppImageObserverManager::GetInstance().SetImageProcessType(appLaunchData.GetImageProcessType());
    if (!CheckForHandleLaunchApplication(appLaunchData)) {
        TAG_LOGE(AAFwkTag::APPKIT, "CheckForHandleLaunchApplication failed");
        return;
    }

    if (appLaunchData.GetDebugApp() && watchdog_ != nullptr && !watchdog_->IsStopWatchdog()) {
        SetAppDebug(AbilityRuntime::AppFreezeState::AppFreezeFlag::DEBUG_LAUNCH_MODE, true);
        watchdog_->Stop();
        watchdog_.reset();
    }

    auto appInfo = appLaunchData.GetApplicationInfo();
    ProcessInfo processInfo = appLaunchData.GetProcessInfo();
    TAG_LOGD(AAFwkTag::APPKIT, "InitCreate Start");
    std::shared_ptr<ContextDeal> contextDeal;
    if (!InitCreate(contextDeal, appInfo, processInfo)) {
        TAG_LOGE(AAFwkTag::APPKIT, "InitCreate failed");
        return;
    }
    auto bundleMgrHelper = contextDeal->GetBundleManager();
    if (bundleMgrHelper == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null bundleMgrHelper");
        return;
    }
    BundleInfo bundleInfo;
    auto bundleName = appInfo.bundleName;
    if (!GetBundleForLaunchApplication(bundleMgrHelper, bundleName, appLaunchData.GetAppIndex(), bundleInfo)) {
        TAG_LOGE(AAFwkTag::APPKIT, "get bundleInfo failed");
        return;
    }
    auto tmpWatchdog = watchdog_;
    bool isSystemApp = bundleInfo.applicationInfo.isSystemApp;
    if (tmpWatchdog != nullptr) {
        tmpWatchdog->SetBundleInfo(bundleName, appInfo.versionName, isSystemApp);
        tmpWatchdog = nullptr;
    }

    bool moduelJson = false;
    bool isStageBased = false;
    bool findEntryHapModuleInfo = false;
#ifdef CJ_FRONTEND
    bool isCJApp = false;
#endif
    AppExecFwk::HapModuleInfo entryHapModuleInfo;
    if (!bundleInfo.hapModuleInfos.empty()) {
        for (auto hapModuleInfo : bundleInfo.hapModuleInfos) {
            if (hapModuleInfo.moduleType == AppExecFwk::ModuleType::ENTRY) {
                findEntryHapModuleInfo = true;
                entryHapModuleInfo = hapModuleInfo;
                break;
            }
        }
        if (!findEntryHapModuleInfo) {
            TAG_LOGW(AAFwkTag::APPKIT, "HandleLaunchApplication find entry hap module info failed");
            entryHapModuleInfo = bundleInfo.hapModuleInfos.back();
        }
#ifdef CJ_FRONTEND
        if (!entryHapModuleInfo.abilityInfos.empty()) {
            auto srcEntrancenName = entryHapModuleInfo.abilityInfos.front().srcEntrance;
            isCJApp = AbilityRuntime::CJRuntime::IsCJAbility(srcEntrancenName);
            AbilityRuntime::CJRuntime::SetPackageName(srcEntrancenName);
        }
#endif
        moduelJson = entryHapModuleInfo.isModuleJson;
        isStageBased = entryHapModuleInfo.isStageBasedModel;
    }

#ifdef SUPPORT_SCREEN
    std::vector<OHOS::AppExecFwk::Metadata> metaData = entryHapModuleInfo.metadata;
    bool isFullUpdate = std::any_of(metaData.begin(), metaData.end(), [](const auto &metaDataItem) {
        return metaDataItem.name == "ArkTSPartialUpdate" && metaDataItem.value == "false";
    });
    bool isReqForm = std::any_of(bundleInfo.reqPermissions.begin(), bundleInfo.reqPermissions.end(),
        [] (const auto &reqPermission) {
        return reqPermission == OHOS::AppExecFwk::Constants::PERMISSION_REQUIRE_FORM;
    });
    {
        HITRACE_METER_NAME(HITRACE_TAG_APP, "Ace::AceForwardCompatibility::Init");
        Ace::AceForwardCompatibility::Init(bundleName, appInfo.apiCompatibleVersion, (isFullUpdate || isReqForm));
    }
#endif

    if (IsNeedLoadLibrary(bundleName)) {
        std::vector<std::string> localPaths;
        ChangeToLocalPath(bundleName, appInfo.moduleSourceDirs, localPaths);
        LoadAbilityLibrary(localPaths);
        LoadNativeLibrary(bundleInfo, appInfo.nativeLibraryPath);
#ifdef SUPPORT_SCREEN
    } else if (Ace::AceForwardCompatibility::PipelineChanged()) {
        std::vector<std::string> localPaths;
        ChangeToLocalPath(bundleName, appInfo.moduleSourceDirs, localPaths);
        LoadAbilityLibrary(localPaths);
#endif
    }
    if (appInfo.needAppDetail) {
        TAG_LOGD(AAFwkTag::APPKIT,
            "MainThread::handleLaunchApplication %{public}s need add app detail ability library path",
            bundleName.c_str());
        LoadAppDetailAbilityLibrary(appInfo.appDetailAbilityLibraryPath);
    }
    LoadAppLibrary();

    applicationForDump_ = application_;

    if (isStageBased) {
        AppRecovery::GetInstance().InitApplicationInfo(GetMainHandler(), GetApplicationInfo());
    }
    TAG_LOGD(AAFwkTag::APPKIT, "stageBased:%{public}d moduleJson:%{public}d size:%{public}zu",
        isStageBased, moduelJson, bundleInfo.hapModuleInfos.size());

    // create contextImpl
    std::shared_ptr<AbilityRuntime::ContextImpl> contextImpl = std::make_shared<AbilityRuntime::ContextImpl>();
    contextImpl->SetApplicationInfo(std::make_shared<ApplicationInfo>(appInfo));
    contextImpl->SetProcessName(processInfo.GetProcessName());
    std::shared_ptr<AbilityRuntime::ApplicationContext> applicationContext =
        AbilityRuntime::ApplicationContext::GetInstance();
    int32_t appIndex = appLaunchData.GetAppIndex();
    std::string instanceKey = appLaunchData.GetInstanceKey();
    applicationContext->SetCurrentAppCloneIndex(appIndex);
    applicationContext->SetCurrentInstanceKey(instanceKey);
    applicationContext->SetCurrentAppMode(static_cast<int32_t>(appInfo.multiAppMode.multiAppModeType));
    applicationContext->AttachContextImpl(contextImpl);
    auto appRunningId = appLaunchData.GetAppRunningUniqueId();
    applicationContext->SetAppRunningUniqueId(appRunningId);
    if (DFX_SetAppRunningUniqueId != nullptr) {
        DFX_SetAppRunningUniqueId(appRunningId.c_str(), appRunningId.length());
    }
    application_->SetApplicationContext(applicationContext);

#ifdef SUPPORT_SCREEN
    OHOS::EglSetCacheDir(applicationContext->GetCacheDir());
#endif

    HspList hspList;
    ErrCode ret = bundleMgrHelper->GetBaseSharedBundleInfos(appInfo.bundleName, hspList,
        AppExecFwk::GetDependentBundleInfoFlag::GET_ALL_DEPENDENT_BUNDLE_INFO);
    if (ret != ERR_OK) {
        TAG_LOGE(AAFwkTag::APPKIT, "Get base shared bundle infos failed: %{public}d", ret);
    }

    std::map<std::string, std::string> pkgContextInfoJsonStringMap;
    std::vector<AppExecFwk::PluginBundleInfo> pluginBundleInfos;
    AppLibPathMap appLibPaths {};
    std::vector<std::string> pluginModuleNames;
    if (appInfo.hasPlugin) {
        if (bundleMgrHelper->GetPluginInfosForSelf(pluginBundleInfos) != ERR_OK) {
            TAG_LOGE(AAFwkTag::JSRUNTIME, "GetPluginInfosForSelf failed");
        }
        GetPluginNativeLibPath(pluginBundleInfos, appLibPaths);
        for (auto &pluginBundleInfo : pluginBundleInfos) {
            for (auto &pluginModuleInfo : pluginBundleInfo.pluginModuleInfos) {
                pkgContextInfoJsonStringMap[pluginModuleInfo.moduleName] = pluginModuleInfo.hapPath;
            }
        }
        for (const auto &appLibPath : appLibPaths) {
            pluginModuleNames.emplace_back(appLibPath.first);
        }
    }

    for (auto hapModuleInfo : bundleInfo.hapModuleInfos) {
        pkgContextInfoJsonStringMap[hapModuleInfo.moduleName] = hapModuleInfo.hapPath;
        if (hapModuleInfo.deduplicateHar) {
            application_->SetDeduplicateHar(hapModuleInfo.deduplicateHar);
        }
    }

    GetNativeLibPath(bundleInfo, hspList, appLibPaths);
    TAG_LOGD(AAFwkTag::APPKIT, "the application isSystemApp: %{public}d", isSystemApp);
#ifdef CJ_FRONTEND
    AbilityRuntime::CJRuntime::SetAppVersion(bundleInfo.applicationInfo.compileSdkVersion);
    if (appInfo.asanEnabled) {
        AbilityRuntime::CJRuntime::SetSanitizerVersion(SanitizerKind::ASAN);
    }
    if (isCJApp) {
        AbilityRuntime::CJRuntime::SetAppLibPath(appLibPaths);
    } else {
#endif
        if (IsEtsAPP(appInfo)) {
            AppLibPathMap etsAppLibPaths {};
            std::map<std::string, std::string> abcPathsToBundleModuleNameMap {};
            GetEtsNativeLibPath(bundleInfo, hspList, etsAppLibPaths, abcPathsToBundleModuleNameMap);
            AbilityRuntime::ETSRuntime::SetAppLibPath(etsAppLibPaths, abcPathsToBundleModuleNameMap, isSystemApp);
        } else {
            AbilityRuntime::JsRuntime::SetAppLibPath(appLibPaths, isSystemApp);
            if (IsPluginNamespaceInherited()) {
                AbilityRuntime::JsRuntime::InheritPluginNamespace(pluginModuleNames);
            }
            auto lddictionaries = ParsePluginDefaultNamespaceLdDictionary();
            if (!lddictionaries.empty()) {
                AbilityRuntime::JsRuntime::CreatePluginDefaultNamespace(lddictionaries);
            }
        }
#ifdef CJ_FRONTEND
    }
#endif
    
    LoadExtStartupTasks();

    if (isStageBased) {
        // Create runtime
        auto hapPath = entryHapModuleInfo.hapPath;
        auto moduleName = entryHapModuleInfo.moduleName;
        AbilityRuntime::Runtime::Options options;
        options.bundleName = appInfo.bundleName;
        options.codePath = LOCAL_CODE_PATH;
        options.hapPath = hapPath;
        options.moduleName = moduleName;
        options.eventRunner = mainHandler_->GetEventRunner();
        options.loadAce = true;
        options.isBundle = (entryHapModuleInfo.compileMode != AppExecFwk::CompileMode::ES_MODULE);
        options.isDebugVersion = bundleInfo.applicationInfo.debug;
        options.arkNativeFilePath = bundleInfo.applicationInfo.arkNativeFilePath;
        options.uid = bundleInfo.applicationInfo.uid;
        options.apiTargetVersion = appInfo.apiTargetVersion;
        options.pkgContextInfoJsonStringMap = pkgContextInfoJsonStringMap;
        options.isStartWithDebug = appLaunchData.GetDebugApp();
        options.allowArkTsLargeHeap = appInfo.allowArkTsLargeHeap;
        options.versionCode = appInfo.versionCode;
        options.arkTSMode = appInfo.arkTSMode;
#ifdef CJ_FRONTEND
        if (isCJApp) {
            options.lang = AbilityRuntime::Runtime::Language::CJ;
        } else {
            SetRuntimeLang(appInfo, options);
        }
#else
        SetRuntimeLang(appInfo, options);
#endif
        if (applicationInfo_->appProvisionType == Constants::APP_PROVISION_TYPE_DEBUG) {
            TAG_LOGD(AAFwkTag::APPKIT, "multi-thread mode: %{public}d", appLaunchData.GetMultiThread());
            options.isMultiThread = appLaunchData.GetMultiThread();
            TAG_LOGD(AAFwkTag::JSRUNTIME, "Start Error-Info-Enhance Mode: %{public}d.",
                appLaunchData.GetErrorInfoEnhance());
            options.isErrorInfoEnhance = appLaunchData.GetErrorInfoEnhance();
        }
        options.jitEnabled = appLaunchData.IsJITEnabled();
        options.isMainProcess = appLaunchData.GetMainProcess();
#ifdef SUPPORT_CHILD_PROCESS
        AbilityRuntime::ChildProcessManager::GetInstance().SetForkProcessJITEnabled(appLaunchData.IsJITEnabled());
        TAG_LOGD(AAFwkTag::APPKIT, "isStartWithDebug:%{public}d, debug:%{public}d, isNativeStart:%{public}d",
            appLaunchData.GetDebugApp(), appInfo.debug, appLaunchData.isNativeStart());
        AbilityRuntime::ChildProcessManager::GetInstance().SetForkProcessDebugOption(appInfo.bundleName,
            appLaunchData.GetDebugApp(), appInfo.debug, appLaunchData.isNativeStart());
        AbilityRuntime::ChildProcessManager::GetInstance().SetApplication(application_);
#endif // SUPPORT_CHILD_PROCESS
        if (!pluginBundleInfos.empty()) {
            for (auto &pluginBundleInfo : pluginBundleInfos) {
                for (auto &pluginModuleInfo : pluginBundleInfo.pluginModuleInfos) {
                    options.packageNameList[pluginModuleInfo.moduleName] = pluginModuleInfo.packageName;
                    if (pluginModuleInfo.moduleArkTSMode != AppExecFwk::Constants::ARKTS_MODE_DYNAMIC) {
                        options.staticPluginHspPathList.push_back(pluginModuleInfo.hapPath);
                    }
                    TAG_LOGI(AAFwkTag::APPKIT, "moduleName %{public}s, packageName %{public}s",
                        pluginModuleInfo.moduleName.c_str(), pluginModuleInfo.packageName.c_str());
                }
            }
        }
        if (!bundleInfo.hapModuleInfos.empty()) {
            for (auto hapModuleInfo : bundleInfo.hapModuleInfos) {
                options.hapModulePath[hapModuleInfo.moduleName] = hapModuleInfo.hapPath;
                options.packageNameList[hapModuleInfo.moduleName] = hapModuleInfo.packageName;
                options.aotCompileStatusMap[hapModuleInfo.moduleName] =
                    static_cast<int32_t>(hapModuleInfo.aotCompileStatus);
                if (hapModuleInfo.moduleArkTSMode == AppExecFwk::Constants::ARKTS_MODE_DYNAMIC) {
                    continue;
                }
                TAG_LOGD(AAFwkTag::APPKIT, "staticHapModuleNameList: %{public}s", hapModuleInfo.moduleName.c_str());
                options.staticHapModuleNameList.push_back(hapModuleInfo.moduleName);
                if (hapModuleInfo.moduleType == AppExecFwk::ModuleType::SHARED) {
                    TAG_LOGD(AAFwkTag::APPKIT, "appInnerHspPathList: %{public}s", hapModuleInfo.hapPath.c_str());
                    options.appInnerHspPathList.push_back(hapModuleInfo.hapPath);
                }
            }
        }
        for (const auto &hsp : hspList) {
            options.commonHspBundleInfos.push_back(
                {hsp.versionCode, hsp.bundleName, hsp.moduleName, hsp.hapPath, hsp.moduleArkTSMode});
        }
        options.enableWarmStartupSmartGC =
            (appLaunchData.GetAppPreloadMode() == AppExecFwk::PreloadMode::PRE_MAKE ||
             appLaunchData.GetAppPreloadMode() == AppExecFwk::PreloadMode::PRELOAD_MODULE);
        TAG_LOGI(AAFwkTag::APPKIT, "SmartGC:%{public}d version:%{public}u",
            static_cast<int32_t>(options.enableWarmStartupSmartGC), bundleInfo.versionCode);
        auto perfCmd = appLaunchData.GetPerfCmd();
        auto findPos = perfCmd.find(BASE_LINE_PERFCMD);
        if (findPos != std::string::npos && (appLaunchData.GetDebugFromLocal() || isDeveloperMode_)) {
            options.baseLineProfile = true;
        }
        auto runtime = AbilityRuntime::Runtime::Create(options);
        if (!runtime) {
            TAG_LOGE(AAFwkTag::APPKIT, "null runtime");
            return;
        }
        runtimeUpdateParam_.option = options;
        if (appInfo.debug && appLaunchData.GetDebugApp()) {
            wptr<MainThread> weak = this;
            auto cb = [weak]() {
                auto appThread = weak.promote();
                if (appThread == nullptr) {
                    TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
                    return false;
                }
                return appThread->NotifyDeviceDisConnect();
            };
            runtime->SetDeviceDisconnectCallback(cb);
        }
        int32_t pid = -1;
        std::string processName = "";
        if (processInfo_ != nullptr) {
            pid = processInfo_->GetPid();
            processName = processInfo_->GetProcessName();
            TAG_LOGD(AAFwkTag::APPKIT, "pid is %{public}d, processName is %{public}s", pid, processName.c_str());
        }
        AbilityRuntime::Runtime::DebugOption debugOption;
        debugOption.arkTSMode = appInfo.arkTSMode;
        debugOption.isStartWithDebug = appLaunchData.GetDebugApp();
        debugOption.processName = processName;
        debugOption.isDebugApp = appInfo.debug;
        debugOption.isStartWithNative = appLaunchData.isNativeStart();
        debugOption.appProvisionType = applicationInfo_->appProvisionType;
        debugOption.isDebugFromLocal = appLaunchData.GetDebugFromLocal();
        debugOption.perfCmd = perfCmd;
        debugOption.isDeveloperMode = isDeveloperMode_;
        debugOption.bundleName = appInfo.bundleName;
        runtime->SetDebugOption(debugOption);
        if (perfCmd.find(PERFCMD_PROFILE) != std::string::npos ||
            perfCmd.find(PERFCMD_DUMPHEAP) != std::string::npos ||
            options.baseLineProfile) {
            TAG_LOGD(AAFwkTag::APPKIT, "perfCmd is %{public}s", perfCmd.c_str());
            runtime->StartProfiler(debugOption);
        } else {
            runtime->StartDebugMode(debugOption);
        }

        std::vector<HqfInfo> hqfInfos = appInfo.appQuickFix.deployedAppqfInfo.hqfInfos;
        std::map<std::string, std::string> modulePaths;
        if (!hqfInfos.empty()) {
            for (auto it = hqfInfos.begin(); it != hqfInfos.end(); it++) {
                TAG_LOGI(AAFwkTag::APPKIT, "moudelName: %{private}s, hqfFilePath: %{private}s",
                    it->moduleName.c_str(), it->hqfFilePath.c_str());
                modulePaths.insert(std::make_pair(it->moduleName, it->hqfFilePath));
            }
            runtime->RegisterQuickFixQueryFunc(modulePaths);
        }

        auto bundleName = appInfo.bundleName;
        auto versionCode = appInfo.versionCode;
#ifdef CJ_FRONTEND
        void* mainEnv = nullptr;
        if (runtime->GetLanguage() == AbilityRuntime::Runtime::Language::ETS) {
            auto& etsRuntime = static_cast<AbilityRuntime::ETSRuntime&>(*runtime);
            auto& jsRuntime = static_cast<AbilityRuntime::JsRuntime&>(*etsRuntime.GetJsRuntime());
            mainEnv = jsRuntime.GetNapiEnv();
        } else if (runtime->GetLanguage() == AbilityRuntime::Runtime::Language::JS) {
            mainEnv = (static_cast<AbilityRuntime::JsRuntime&>(*runtime)).GetNapiEnv();
        }
        AbilityRuntime::CJRuntime::SetMainNAPIEnv(mainEnv);
        if (!isCJApp) {
#endif
            if (IsEtsAPP(appInfo)) {
                auto expectionInfo =
                    CreateEtsExceptionInfo(bundleName, versionCode, hapPath, appRunningId, pid, processName);
                (static_cast<AbilityRuntime::ETSRuntime&>(*runtime)).RegisterUncaughtExceptionHandler(expectionInfo);
                UncatchableTaskInfo uncatchableTaskInfo = {bundleName, versionCode, appRunningId, pid, processName};
                RegisterHybridException(runtime, appInfo, hapPath, uncatchableTaskInfo);
            } else {
                JsEnv::UncaughtExceptionInfo uncaughtExceptionInfo;
                uncaughtExceptionInfo.hapPath = hapPath;
                runtimeUpdateParam_.hapPath= hapPath;
                UncatchableTaskInfo uncatchableTaskInfo = {bundleName, versionCode, appRunningId, pid, processName};
                runtimeUpdateParam_.uncatchableTaskInfo = uncatchableTaskInfo;
                InitUncatchableTask(uncaughtExceptionInfo.uncaughtTask, uncatchableTaskInfo);
                (static_cast<AbilityRuntime::JsRuntime&>(*runtime)).RegisterUncaughtExceptionHandler(
                    uncaughtExceptionInfo);
                JsEnv::UncatchableTask uncatchableTask;
                InitUncatchableTask(uncatchableTask, uncatchableTaskInfo, true);
                (static_cast<AbilityRuntime::JsRuntime&>(*runtime)).RegisterUncatchableExceptionHandler(
                    uncatchableTask);
                TransferEnvToEventHandler(runtime);
            }
#ifdef CJ_FRONTEND
        } else {
            auto expectionInfo = CreateCjExceptionInfo(bundleName, versionCode, hapPath, appRunningId);
            (static_cast<AbilityRuntime::CJRuntime&>(*runtime)).RegisterUncaughtExceptionHandler(expectionInfo);
            auto reportInfo = CreateCjEventReportInfo(bundleName, versionCode, hapPath, appRunningId);
            (static_cast<AbilityRuntime::CJRuntime&>(*runtime)).RegisterEventHandler(reportInfo);
        }
#endif
        wptr<MainThread> weak = this;
        auto callback = [weak](const AAFwk::ExitReason &exitReason) {
            auto appThread = weak.promote();
            if (appThread == nullptr) {
                TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            }
            AbilityManagerClient::GetInstance()->RecordAppExitReason(exitReason);
            appThread->ScheduleProcessSecurityExit();
        };
        applicationContext->RegisterProcessSecurityExit(callback);

        application_->SetRuntime(std::move(runtime));

        std::weak_ptr<OHOSApplication> wpApplication = application_;
        AbilityLoader::GetInstance().RegisterUIAbility("UIAbility",
            [wpApplication](const std::string &codeLanguage) -> AbilityRuntime::UIAbility* {
            auto app = wpApplication.lock();
            if (app != nullptr) {
                return AbilityRuntime::UIAbility::Create(app->GetSpecifiedRuntime(codeLanguage));
            }
            TAG_LOGE(AAFwkTag::APPKIT, "failed");
            return nullptr;
        });
#ifdef CJ_FRONTEND
        if (!isCJApp) {
#endif
            if (application_ != nullptr) {
                TAG_LOGD(AAFwkTag::APPKIT, "LoadAllExtensions lan:%{public}s", appInfo.arkTSMode.c_str());
                LoadAllExtensions();
            }
            if (!IsEtsAPP(appInfo)) {
                auto &runtime = application_->GetRuntime();
                if (runtime == nullptr) {
                    TAG_LOGE(AAFwkTag::APPKIT, "null runtime");
                    return;
                }
                SetJsIdleCallback(wpApplication, runtime);
            }
#ifdef CJ_FRONTEND
        } else {
            LoadAllExtensions();
        }
#endif
    }

    auto usertestInfo = appLaunchData.GetUserTestInfo();
    if (usertestInfo) {
        if (!PrepareAbilityDelegator(usertestInfo, isStageBased, entryHapModuleInfo, bundleInfo.targetVersion)) {
            TAG_LOGE(AAFwkTag::APPKIT, "PrepareAbilityDelegator failed");
            return;
        }
    }

    // init resourceManager.
    auto moduleName = entryHapModuleInfo.moduleName;
    std::string loadPath =
        entryHapModuleInfo.hapPath.empty() ? entryHapModuleInfo.resourcePath : entryHapModuleInfo.hapPath;
    std::regex inner_pattern(std::string(ABS_CODE_PATH) + std::string(FILE_SEPARATOR) + bundleInfo.name);
    loadPath = std::regex_replace(loadPath, inner_pattern, LOCAL_CODE_PATH);
    application_->SetEntryLoadPath(loadPath);
    auto res = GetOverlayModuleInfos(bundleInfo.name, moduleName, overlayModuleInfos_);
    std::vector<std::string> overlayPaths;
    if (res == ERR_OK) {
        overlayPaths = GetAddOverlayPaths(overlayModuleInfos_);
    }
    std::unique_ptr<Global::Resource::ResConfig> resConfig(Global::Resource::CreateResConfig());
    int32_t appType;
    if (bundleInfo.applicationInfo.codePath == std::to_string(TYPE_RESERVE)) {
        appType = TYPE_RESERVE;
    } else if (bundleInfo.applicationInfo.codePath == std::to_string(TYPE_OTHERS)) {
        appType = TYPE_OTHERS;
    } else {
        appType = 0;
    }
    std::shared_ptr<Global::Resource::ResourceManager> resourceManager(Global::Resource::CreateResourceManager(
        bundleInfo.name, moduleName, loadPath, overlayPaths, *resConfig, appType));

    if (resourceManager == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null resourceManager");
        return;
    }

    Configuration appConfig = config;
    ParseAppConfigurationParams(bundleInfo.applicationInfo.configuration, appConfig);
    if (Global::I18n::PreferredLanguage::IsSetAppPreferredLanguage()) {
        std::string preferredLanguage = Global::I18n::PreferredLanguage::GetAppPreferredLanguage();
        appConfig.AddItem(AAFwk::GlobalConfigurationKey::SYSTEM_LANGUAGE, preferredLanguage);
        std::string locale = appConfig.GetItem(AAFwk::GlobalConfigurationKey::SYSTEM_LOCALE);
        appConfig.AddItem(AAFwk::GlobalConfigurationKey::SYSTEM_LOCALE,
            AbilityRuntime::ApplicationConfigurationManager::GetUpdatedLocale(locale, preferredLanguage));
    }
    HandleConfigByPlugin(appConfig, bundleInfo);
    std::string systemSizeScale = appConfig.GetItem(AAFwk::GlobalConfigurationKey::APP_FONT_SIZE_SCALE);
    if (!systemSizeScale.empty() && systemSizeScale.compare(DEFAULT_APP_FONT_SIZE_SCALE) == 0) {
        appConfig.AddItem(AAFwk::GlobalConfigurationKey::SYSTEM_FONT_SIZE_SCALE, SYSTEM_DEFAULT_FONTSIZE_SCALE);
    }

    if (!InitResourceManager(resourceManager, entryHapModuleInfo, bundleInfo.name,
        appConfig, bundleInfo.applicationInfo)) {
        TAG_LOGE(AAFwkTag::APPKIT, "InitResourceManager failed");
        return;
    }
    contextImpl->SetResourceManager(resourceManager);
    AbilityBase::ExtractResourceManager::GetExtractResourceManager().SetGlobalObject(resourceManager);

    contextDeal->initResourceManager(resourceManager);
    contextDeal->SetApplicationContext(application_);
    application_->AttachBaseContext(contextDeal);
    application_->SetAbilityRecordMgr(abilityRecordMgr_);
    application_->SetConfiguration(appConfig);
    contextImpl->SetConfiguration(application_->GetConfiguration());
    application_->InitJSLeakWatcher(bundleInfo.name);

    applicationImpl_->SetRecordId(appLaunchData.GetRecordId());
    applicationImpl_->SetApplication(application_);
    AppExecFwk::AppfreezeInner::GetInstance()->SetAppfreezeApplication(application_);
    mainThreadState_ = MainThreadState::READY;
    if (!applicationImpl_->PerformAppReady()) {
        TAG_LOGE(AAFwkTag::APPKIT, "applicationImpl_->PerformAppReady failed");
        return;
    }
    FreezeUtil::GetInstance().AddAppLifecycleEvent(0, "HandleLaunchApplication end");
    // L1 needs to add corresponding interface
    ApplicationEnvImpl *pAppEvnIml = ApplicationEnvImpl::GetInstance();

    if (pAppEvnIml) {
        pAppEvnIml->SetAppInfo(*applicationInfo_.get(), appLaunchData.GetAppPreloadMode());
    } else {
        TAG_LOGE(AAFwkTag::APPKIT, "null pAppEvnIml");
    }

#if defined(NWEB) && defined(NWEB_GRAPHIC)
    if (appLaunchData.IsAllowedNWebPreload()) {
        HandleNWebPreload();
    }
#endif
    RunNativeStartupTask(bundleInfo, appLaunchData);
    if (!IsEtsAPP(appInfo) &&
        (appLaunchData.IsNeedPreloadModule() ||
        appLaunchData.GetAppPreloadMode() == AppExecFwk::PreloadMode::PRELOAD_MODULE)) {
        PreloadModule(bundleInfo, appLaunchData, entryHapModuleInfo, application_->GetRuntime());
        if (appMgr_ == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appMgr");
            return;
        }
        appMgr_->PreloadModuleFinished(applicationImpl_->GetRecordId());
        TAG_LOGI(AAFwkTag::APPKIT, "preload module finished");
    }
}

std::string GetProcessLifeCycleByPid(pid_t pid)
{
    uint64_t lifeTimeSeconds = 0;
    int errCode = OHOS::HiviewDFX::GetProcessLifeCycle(pid, lifeTimeSeconds);
    if (errCode != 0) {
        TAG_LOGE(AAFwkTag::APPKIT, "Get process lifeCycle fail, errCode: %{public}d", errCode);
    }
    std::string lifeTime = std::to_string(lifeTimeSeconds) + "s";
    return lifeTime;
}

/**
 *
 * @brief Init the uncatchable task.
 *
 * @param uncatchableTaskInfo The info of the uncatchable task.
 * @param isUncatchable Weather task is uncatcheable.
 *
 */
void MainThread::InitUncatchableTask(JsEnv::UncatchableTask &uncatchableTask, const UncatchableTaskInfo &uncatchableTaskInfo,
    bool isUncatchable)
{
    wptr<MainThread> weak = this;
    uncatchableTask = [weak, bundleName = uncatchableTaskInfo.bundleName,
        versionCode = uncatchableTaskInfo.versionCode, appRunningId = uncatchableTaskInfo.appRunningId,
        pid = uncatchableTaskInfo.pid, processName = uncatchableTaskInfo.processName, isUncatchable]
        (std::string summary, const JsEnv::ErrorObject errorObject, napi_env env, napi_value exception) {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }

        time_t timet;
        time(&timet);
        std::string lifeTime = GetProcessLifeCycleByPid(pid);
        if (!ApplicationDataManager::jsErrorHasReport_.exchange(true)) {
            auto hisyseventReport = std::make_shared<HisyseventReport>(14);
            hisyseventReport->InsertParam(EVENT_KEY_PACKAGE_NAME, bundleName);
            hisyseventReport->InsertParam(EVENT_KEY_VERSION, std::to_string(versionCode));
            hisyseventReport->InsertParam(EVENT_KEY_TYPE, JSCRASH_TYPE);
            hisyseventReport->InsertParam(EVENT_KEY_HAPPEN_TIME, timet);
            hisyseventReport->InsertParam(EVENT_KEY_REASON, errorObject.name);
            hisyseventReport->InsertParam(EVENT_KEY_JSVM, JSVM_TYPE);
            hisyseventReport->InsertParam(EVENT_KEY_SUMMARY, summary);
            hisyseventReport->InsertParam(EVENT_KEY_PNAME, processName);
            hisyseventReport->InsertParam(EVENT_KEY_APP_RUNNING_UNIQUE_ID, appRunningId);
            hisyseventReport->InsertParam(EVENT_KEY_PROCESS_RSS_MEMINFO,
                std::to_string(DumpProcessHelper::GetProcRssMemInfo()));
            hisyseventReport->InsertParam(EVENT_KEY_THREAD_NAME, DumpProcessHelper::GetThreadName());
            hisyseventReport->InsertParam(EVENT_KEY_PROCESS_LIFETIME, lifeTime);
            hisyseventReport->InsertParam(ERRORMANAGER_CAPTURE,
                ApplicationDataManager::GetInstance().GetHasOnErrorCallback());
            hisyseventReport->InsertParam(IS_UNCATCH_FAULT, isUncatchable);
            int result = hisyseventReport->Report("AAFWK", "JS_ERROR", HISYSEVENT_FAULT);
            TAG_LOGW(AAFwkTag::APPKIT, "hisysevent write result=%{public}d, send event [FRAMEWORK,JS_ERROR],"
                " packageName=%{public}s, pid=%{public}d, appRunningId=%{public}s, threadName=%{public}s,"
                " isUncatchable=%{public}d", result, bundleName.c_str(), pid, appRunningId.c_str(),
                DumpProcessHelper::GetThreadName().c_str(), isUncatchable);
            ApplicationDataManager::jsErrorEnv_.store(env, std::memory_order_relaxed);
        }

        ApplicationDataManager::GetInstance().SetIsUncatchable(isUncatchable);

        bool foreground = (appThread->applicationImpl_ && appThread->applicationImpl_->GetState() ==
            ApplicationImpl::APP_STATE_FOREGROUND) ? true : false;
        ProcessExitInfo info = {bundleName, errorObject.name, summary, appRunningId, processName, pid, foreground,
            isUncatchable};
        ProcessExit(info);

        ErrorObject appExecErrorObj = { errorObject.name, errorObject.message, errorObject.stack};
        napi_env mainEnv = nullptr;
        auto &runtime = appThread->application_->GetRuntime();
        if (runtime->GetLanguage() == AbilityRuntime::Runtime::Language::ETS) {
            auto& etsRuntime = static_cast<AbilityRuntime::ETSRuntime&>(*runtime);
            auto& jsRuntime = static_cast<AbilityRuntime::JsRuntime&>(*etsRuntime.GetJsRuntime());
            mainEnv = jsRuntime.GetNapiEnv();
        } else {
            mainEnv = (static_cast<AbilityRuntime::JsRuntime&>(*runtime)).GetNapiEnv();
        }
        ApplicationDataManager::ExceptionParams params = {env, mainEnv, exception, summary, isUncatchable};
        if (ApplicationDataManager::NotifyUncaughtException(params, appExecErrorObj)) {
            return;
        }

        if (!isUncatchable && ApplicationDataManager::GetInstance().NotifyUnhandledException(summary) &&
            ApplicationDataManager::GetInstance().NotifyExceptionObject(appExecErrorObj)) {
            return;
        }

        if (ApplicationDataManager::jsErrorEnv_.load(std::memory_order_relaxed) != env) {
            TAG_LOGW(AAFwkTag::APPKIT, "Current thread does not need to exit the process");
            return;
        }
        _exit(JS_ERROR_EXIT);
    };
}

/**
 *
 * @brief Handle process exit.
 *
 * @param processExitInfo The info of the process exit info.
 *
 */
void MainThread::ProcessExit(const ProcessExitInfo& info)
{
    // if app's callback has been registered, let app decide whether exit or not.
    TAG_LOGE(AAFwkTag::APPKIT, "\n%{public}s is about to exit due to RuntimeError\nError type:%{public}s\n"
        "%{public}s", info.bundleName.c_str(), info.errorObjectName.c_str(), info.summary.c_str());
    AAFwk::ExitReasonCompability exitReason = { REASON_JS_ERROR, info.errorObjectName };
    exitReason.killId = HiviewDFX::ProcessKillReason::KillEventId::REASON_JS_ERROR;
    auto result = AbilityManagerClient::GetInstance()->RecordAppWithReason(info.pid, getuid(), exitReason);

    TAG_LOGW(AAFwkTag::APPKIT, "Record result=%{public}d, send event [FRAMEWORK,PROCESS_KILL,JS_ERROR],"
        " pid=%{public}d, processName=%{public}s, msg=%{public}s, foreground=%{public}d, isUncatchable=%{public}d",
        result, info.pid, info.processName.c_str(), KILL_REASON, info.foreground, info.isUncatchable);
}

#if defined(NWEB) && defined(NWEB_GRAPHIC)
void MainThread::HandleNWebPreload()
{
    if (!mainHandler_) {
        TAG_LOGE(AAFwkTag::APPKIT, "mainHandler is nullptr");
        return;
    }

    auto task = [this]() {
        if (!NWeb::NWebHelper::Instance().InitAndRun(true)) {
            TAG_LOGE(AAFwkTag::APPKIT, "init NWebEngine failed");
            return;
        }
        Rosen::RSSurfaceNodeConfig config;
        config.SurfaceNodeName = NWEB_SURFACE_NODE_NAME;
        preloadSurfaceNode_ = Rosen::RSSurfaceNode::Create(config, false);
        if (!preloadSurfaceNode_) {
            TAG_LOGE(AAFwkTag::APPKIT, "preload surface node is nullptr");
            return;
        }
        auto surface = preloadSurfaceNode_->GetSurface();
        if (!surface) {
            TAG_LOGE(AAFwkTag::APPKIT, "preload surface is nullptr");
            preloadSurfaceNode_ = nullptr;
            return;
        }
        auto initArgs = std::make_shared<NWeb::NWebEngineInitArgsImpl>();
        preloadNWeb_ = NWeb::NWebAdapterHelper::Instance().CreateNWeb(surface, initArgs,
            NWEB_SURFACE_SIZE, NWEB_SURFACE_SIZE, false);
        if (!preloadNWeb_) {
            TAG_LOGE(AAFwkTag::APPKIT, "create preLoadNWeb failed");
            return;
        }
        auto handler = std::make_shared<NWebPreloadHandlerImpl>();
        preloadNWeb_->SetNWebHandler(handler);
        preloadNWeb_->Load(BLANK_URL);
        TAG_LOGI(AAFwkTag::APPKIT, "init NWeb success");
    };

    mainHandler_->PostIdleTask(task, "MainThread::NWEB_PRELOAD", PRELOAD_TASK_DELAY_TIME);
    TAG_LOGI(AAFwkTag::APPKIT, "postIdleTask success");
}
#endif

void MainThread::ProcessMainAbility(const AbilityInfo &info, const std::unique_ptr<AbilityRuntime::Runtime>& runtime)
{
    std::string srcPath(info.package);
    if (!info.isModuleJson) {
    /* temporary compatibility api8 + config.json */
        srcPath.append("/assets/js/");
        if (!info.srcPath.empty()) {
            srcPath.append(info.srcPath);
        }
        srcPath.append("/").append(info.name).append(".abc");
    } else {
        if (info.srcEntrance.empty()) {
            TAG_LOGE(AAFwkTag::UIABILITY, "empty srcEntrance");
            return;
        }
        srcPath.append("/");
        srcPath.append(info.srcEntrance);
        srcPath.erase(srcPath.rfind("."));
        srcPath.append(".abc");
        TAG_LOGD(AAFwkTag::UIABILITY, "jsAbility srcPath: %{public}s", srcPath.c_str());
    }

    std::string moduleName(info.moduleName);
    moduleName.append("::").append(info.name);
    bool isEsmode = info.compileMode == AppExecFwk::CompileMode::ES_MODULE;
    runtime->PreloadMainAbility(moduleName, srcPath, info.hapPath, isEsmode, info.srcEntrance);
}

void MainThread::PreloadModule(const BundleInfo &bundleInfo, const AppLaunchData &appLaunchData,
    const AppExecFwk::HapModuleInfo &entryHapModuleInfo, const std::unique_ptr<AbilityRuntime::Runtime> &runtime)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    const AppExecFwk::HapModuleInfo* preloadModuleInfo = nullptr;
    for (const auto& hapModuleInfo: bundleInfo.hapModuleInfos) {
        if (hapModuleInfo.moduleName == appLaunchData.GetPreloadModuleName()) {
            preloadModuleInfo = &hapModuleInfo;
            break;
        }
    }
    if (preloadModuleInfo == nullptr) {
        preloadModuleInfo = &entryHapModuleInfo;
    }
    std::string preloadAbilityName = appLaunchData.GetPreloadAbilityName();
    if (preloadAbilityName.empty()) {
        preloadAbilityName = preloadModuleInfo->mainAbility;
    }
    TAG_LOGI(AAFwkTag::APPKIT, "preload module %{public}s", preloadModuleInfo->moduleName.c_str());
    auto callback = []() {};
    bool isAsyncCallback = false;
    application_->AddAbilityStage(*preloadModuleInfo, callback, isAsyncCallback, preloadAbilityName);
    if (isAsyncCallback) {
        return;
    }
    for (const auto& info : preloadModuleInfo->abilityInfos) {
        if (info.name == preloadAbilityName) {
            ProcessMainAbility(info, runtime);
            return;
        }
    }
    for (auto& extensionInfo : preloadModuleInfo->extensionInfos) {
        if (extensionInfo.name == preloadAbilityName) {
            AbilityInfo abilityInfo;
            AbilityRuntime::StartupUtil::InitAbilityInfoFromExtension(
                const_cast<ExtensionAbilityInfo&>(extensionInfo), abilityInfo);
            ProcessMainAbility(abilityInfo, runtime);
            return;
        }
    }
}

#ifdef ABILITY_LIBRARY_LOADER
void MainThread::CalcNativeLiabraryEntries(const BundleInfo &bundleInfo, std::string &nativeLibraryPath)
{
    bool loadSoFromDir = bundleInfo.hapModuleInfos.empty();
    std::vector<std::string> nativeFileEntries;
    for (const auto &item: bundleInfo.hapModuleInfos) {
        if (!item.compressNativeLibs) {
            TAG_LOGD(AAFwkTag::APPKIT, "handle entries for: %{public}s, with path: %{public}s",
                item.moduleName.c_str(), item.nativeLibraryPath.c_str());
            if (item.nativeLibraryPath.empty()) {
                TAG_LOGD(AAFwkTag::APPKIT, "nativeLibraryPath empty: %{public}s", item.moduleName.c_str());
                continue;
            }
            std::string libPath = GetLibPath(item.hapPath, bundleInfo.isPreInstallApp);
            libPath += (libPath.back() == '/') ? item.nativeLibraryPath : "/" + item.nativeLibraryPath;
            TAG_LOGI(AAFwkTag::APPKIT, "module lib path: %{public}s", libPath.c_str());
            if (libPath.back() != '/') {
                libPath.push_back('/');
            }
            for (const auto &entryName : item.nativeLibraryFileNames) {
                TAG_LOGD(AAFwkTag::APPKIT, "add entry: %{public}s", entryName.c_str());
                nativeFileEntries.emplace_back(libPath + entryName);
            }
        } else {
            TAG_LOGD(AAFwkTag::APPKIT, "compressNativeLibs flag true for: %{public}s", item.moduleName.c_str());
            loadSoFromDir = true;
        }
    }

    if (loadSoFromDir) {
        if (nativeLibraryPath.empty()) {
            TAG_LOGW(AAFwkTag::APPKIT, "nativeLibPath empty");
            return;
        }

        if (nativeLibraryPath.back() == '/') {
            nativeLibraryPath.pop_back();
        }
        std::string libPath = LOCAL_CODE_PATH;
        libPath += (libPath.back() == '/') ? nativeLibraryPath : "/" + nativeLibraryPath;
        TAG_LOGD(AAFwkTag::APPKIT, "native library path = %{public}s", libPath.c_str());

        if (!ScanDir(libPath, nativeFileEntries_)) {
            TAG_LOGW(AAFwkTag::APPKIT, "scanDir %{public}s not exits", libPath.c_str());
        }
    }

    if (!nativeFileEntries.empty()) {
        nativeFileEntries_.insert(nativeFileEntries_.end(), nativeFileEntries.begin(), nativeFileEntries.end());
    }
}

void MainThread::LoadNativeLibrary(const BundleInfo &bundleInfo, std::string &nativeLibraryPath)
{
    CalcNativeLiabraryEntries(bundleInfo, nativeLibraryPath);
    if (nativeFileEntries_.empty()) {
        TAG_LOGW(AAFwkTag::APPKIT, "No native library");
        return;
    }
    char resolvedPath[PATH_MAX] = {0};
    void *handleAbilityLib = nullptr;
    for (auto fileEntry : nativeFileEntries_) {
        if (fileEntry.empty() || fileEntry.size() >= PATH_MAX) {
            continue;
        }
        if (realpath(fileEntry.c_str(), resolvedPath) == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "errno = %{public}d", errno);
            continue;
        }
        handleAbilityLib = dlopen(resolvedPath, RTLD_NOW | RTLD_GLOBAL);
        if (handleAbilityLib == nullptr) {
            if (fileEntry.find("libformrender.z.so") == std::string::npos) {
                TAG_LOGE(AAFwkTag::APPKIT, "dlopen %{public}s, [%{public}s] failed", fileEntry.c_str(), dlerror());
                exit(-1);
            } else {
                TAG_LOGD(AAFwkTag::APPKIT, "Load libformrender.z.so from native lib path.");
                handleAbilityLib = dlopen(FORM_RENDER_LIB_PATH, RTLD_NOW | RTLD_GLOBAL);
                if (handleAbilityLib == nullptr) {
                    TAG_LOGE(AAFwkTag::APPKIT, "dlopen %{public}s, [%{public}s] failed",
                        FORM_RENDER_LIB_PATH, dlerror());
                    exit(-1);
                }
                fileEntry = FORM_RENDER_LIB_PATH;
            }
        }
        TAG_LOGD(AAFwkTag::APPKIT, "success to dlopen %{public}s", fileEntry.c_str());
        handleAbilityLib_.emplace_back(handleAbilityLib);
    }
}
#endif

void MainThread::ChangeToLocalPath(const std::string &bundleName,
    const std::vector<std::string> &sourceDirs, std::vector<std::string> &localPath)
{
    std::regex pattern(std::string(ABS_CODE_PATH) + std::string(FILE_SEPARATOR) + bundleName
        + std::string(FILE_SEPARATOR));
    for (auto item : sourceDirs) {
        if (item.empty()) {
            continue;
        }
        localPath.emplace_back(
            std::regex_replace(item, pattern, std::string(LOCAL_CODE_PATH) + std::string(FILE_SEPARATOR)));
    }
}

void MainThread::ChangeToLocalPath(const std::string &bundleName,
    const std::string &sourceDir, std::string &localPath)
{
    std::regex pattern(std::string(ABS_CODE_PATH) + std::string(FILE_SEPARATOR) + bundleName);
    if (sourceDir.empty()) {
        return;
    }
    bool isExist = false;
    try {
        isExist = std::regex_search(localPath, std::regex(bundleName));
    } catch (...) {
        TAG_LOGE(AAFwkTag::APPKIT, "ChangeToLocalPath error localPath:%{public}s bundleName:%{public}s",
            localPath.c_str(), bundleName.c_str());
    }
    if (isExist) {
        localPath = std::regex_replace(localPath, pattern, std::string(LOCAL_CODE_PATH));
    } else {
        localPath = std::regex_replace(localPath, std::regex(ABS_CODE_PATH), LOCAL_BUNDLES);
    }
}

void MainThread::DoUpdatePluginInfoInstalled(std::vector<AppExecFwk::PluginBundleInfo> &pluginBundleInfos,
    const std::vector<std::string> &pluginModuleNames)
{
    if (!applicationInfo_) {
        TAG_LOGE(AAFwkTag::APPKIT, "null applicationInfo_");
        return;
    }
    if (!application_) {
        TAG_LOGE(AAFwkTag::APPKIT, "null application_");
        return;
    }
    applicationInfo_->hasPlugin = true;
    application_->UpdateApplicationInfoInstalled(*applicationInfo_);
    AppLibPathMap appLibPaths {};
    GetPluginNativeLibPath(pluginBundleInfos, appLibPaths);
    AbilityRuntime::JsRuntime::SetOrUpdateLibPath(appLibPaths, applicationInfo_->isSystemApp);
    std::vector<std::string> moduleNames;
    for (const auto &appLibPath : appLibPaths) {
        moduleNames.emplace_back(appLibPath.first);
    }
    if (IsPluginNamespaceInherited()) {
        AbilityRuntime::JsRuntime::InheritPluginNamespace(moduleNames);
    }
}

void MainThread::HandleUpdatePluginInfoInstalled(const ApplicationInfo &pluginAppInfo, const std::string &moduleName)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (!application_) {
        TAG_LOGE(AAFwkTag::APPKIT, "null application_");
        return;
    }
    auto &runtime = application_->GetRuntime();
    if (runtime == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null runtime");
        return;
    }

    if (runtime->GetLanguage() != Runtime::Language::JS) {
        TAG_LOGE(AAFwkTag::APPKIT, "only support js");
        return;
    }

    AbilityRuntime::JsRuntime* jsRuntime = static_cast<AbilityRuntime::JsRuntime*>(runtime.get());
    if (jsRuntime == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null runtime");
        return;
    }

    auto bundleMgrHelper = DelayedSingleton<BundleMgrHelper>::GetInstance();
    if (bundleMgrHelper == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null bundleMgrHelper");
        return;
    }

    std::vector<AppExecFwk::PluginBundleInfo> pluginBundleInfos;
    if (bundleMgrHelper->GetPluginInfosForSelf(pluginBundleInfos) != ERR_OK) {
        TAG_LOGE(AAFwkTag::JSRUNTIME, "GetPluginInfosForSelf failed");
        return;
    }

    std::vector<std::string> pluginModuleNames;
    for (auto &pluginBundleInfo : pluginBundleInfos) {
        for (auto &pluginModuleInfo : pluginBundleInfo.pluginModuleInfos) {
            if (moduleName == pluginModuleInfo.moduleName &&
                pluginBundleInfo.pluginBundleName == pluginAppInfo.name) {
                jsRuntime->UpdatePkgContextInfoJson(moduleName, pluginModuleInfo.hapPath, pluginModuleInfo.packageName);
                TAG_LOGI(AAFwkTag::APPKIT,
                    "UpdatePkgContextInfoJson moduleName: %{public}s, hapPath: %{public}s",
                    moduleName.c_str(), pluginModuleInfo.hapPath.c_str());
                pluginModuleNames.emplace_back(moduleName);
            }
        }
    }
    if (!pluginModuleNames.empty()) {
        DoUpdatePluginInfoInstalled(pluginBundleInfos, pluginModuleNames);
    }
}

void MainThread::HandleUpdateApplicationInfoInstalled(const ApplicationInfo &appInfo, const std::string &moduleNames)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (!application_) {
        TAG_LOGE(AAFwkTag::APPKIT, "null application_");
        return;
    }
    application_->UpdateApplicationInfoInstalled(appInfo);

    auto &runtime = application_->GetRuntime();
    if (runtime == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null runtime");
        return;
    }

    if (runtime->GetLanguage() == AbilityRuntime::Runtime::Language::JS) {
        auto bundleMgrHelper = DelayedSingleton<BundleMgrHelper>::GetInstance();
        if (bundleMgrHelper == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null bundleMgrHelper");
            return;
        }

        std::vector<std::string> moduleNameList;
        AbilityBase::SplitString(moduleNames, moduleNameList, 0, ",");
        for (const auto &moduleName : moduleNameList) {
            AbilityInfo abilityInfo;
            abilityInfo.bundleName = appInfo.bundleName;
            abilityInfo.package = moduleName;
            HapModuleInfo hapModuleInfo;
            if (!bundleMgrHelper->GetHapModuleInfo(abilityInfo, hapModuleInfo)) {
                TAG_LOGE(AAFwkTag::APPKIT, "GetHapModuleInfo failed");
                return;
            }
            static_cast<AbilityRuntime::JsRuntime&>(*runtime).UpdatePkgContextInfoJson(hapModuleInfo.moduleName,
                hapModuleInfo.hapPath, hapModuleInfo.packageName);
            TAG_LOGI(AAFwkTag::APPKIT,
                "UpdatePkgContextInfoJson moduleName: %{public}s, hapPath: %{public}s, packageName: %{public}s",
                hapModuleInfo.moduleName.c_str(), hapModuleInfo.hapPath.c_str(), hapModuleInfo.packageName.c_str());
        }
    }
}

void MainThread::HandleAbilityStage(const HapModuleInfo &abilityStage)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (!application_) {
        TAG_LOGE(AAFwkTag::APPKIT, "null application_");
        return;
    }

    wptr<MainThread> weak = this;
    auto callback = [weak]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        if (!appThread->appMgr_ || !appThread->applicationImpl_) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appMgr_");
            return;
        }
        appThread->appMgr_->AddAbilityStageDone(appThread->applicationImpl_->GetRecordId());
    };
    bool isAsyncCallback = false;
    application_->AddAbilityStage(abilityStage, callback, isAsyncCallback);
    if (isAsyncCallback) {
        return;
    }

    if (!appMgr_ || !applicationImpl_) {
        TAG_LOGE(AAFwkTag::APPKIT, "null appMgr_");
        return;
    }

    appMgr_->AddAbilityStageDone(applicationImpl_->GetRecordId());
}

void MainThread::LoadAllExtensions(NativeEngine &nativeEngine)
{
    (void)nativeEngine;
    return LoadAllExtensions();
}

void MainThread::LoadAllExtensions()
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    TAG_LOGD(AAFwkTag::APPKIT, "LoadAllExtensions");
    auto extensionPlugins = AbilityRuntime::ExtensionPluginInfo::GetInstance().GetExtensionPlugins();
    if (extensionPlugins.empty()) {
        TAG_LOGE(AAFwkTag::APPKIT, "no extension type map");
        return;
    }

    std::map<int32_t, std::string> extensionTypeMap;
    for (auto& item : extensionPlugins) {
        extensionTypeMap.insert(std::pair<int32_t, std::string>(item.extensionType, item.extensionName));

        std::string file = item.extensionLibFile;
        std::weak_ptr<OHOSApplication> wApp = application_;
        AbilityLoader::GetInstance().RegisterExtension(item.extensionName,
            [wApp, file](const std::string &codeLanguage) -> AbilityRuntime::Extension* {
            auto app = wApp.lock();
            if (app != nullptr) {
                return AbilityRuntime::ExtensionModuleLoader::GetLoader(file.c_str())
                    .Create(app->GetSpecifiedRuntime(codeLanguage));
            }
            TAG_LOGE(AAFwkTag::APPKIT, "failed");
            return nullptr;
        });
    }
    application_->SetExtensionTypeMap(extensionTypeMap);
}

bool MainThread::PrepareAbilityDelegator(const std::shared_ptr<UserTestRecord> &record, bool isStageBased,
    const AppExecFwk::HapModuleInfo &entryHapModuleInfo, uint32_t targetVersion)
{
    TAG_LOGD(AAFwkTag::APPKIT, "enter, isStageBased = %{public}d", isStageBased);
    if (!record) {
        TAG_LOGE(AAFwkTag::APPKIT, "Invalid UserTestRecord");
        return false;
    }
    auto args = std::make_shared<AbilityDelegatorArgs>(record->want);
    if (isStageBased) { // Stage model
        TAG_LOGD(AAFwkTag::APPKIT, "Stage model");
        if (args == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "test args is null");
            return false;
        }
        AppExecFwk::ModuleTestRunner tsTestRunner;
        if (!GetTestRunnerTypeAndPath(args->GetTestBundleName(), args->GetTestModuleName(), tsTestRunner)) {
            TAG_LOGE(AAFwkTag::APPKIT, "query testrunner failed");
        }
        args->SetTestRunnerModeAndPath(tsTestRunner.arkTSMode, tsTestRunner.srcPath);
        auto testRunner = TestRunner::Create(application_->GetRuntime(), args, false);
        auto delegator = IAbilityDelegator::Create(application_->GetRuntime(), application_->GetAppContext(),
            std::move(testRunner), record->observer);
        AbilityDelegatorRegistry::RegisterInstance(delegator, args, application_->GetRuntime()->GetLanguage());
        {
            void *napiEnvVoid = nullptr;
            void *aniVmVoid = nullptr;
            auto &curRuntime = application_->GetRuntime();
            bool isHybrid = applicationInfo_ &&
                applicationInfo_->arkTSMode == AbilityRuntime::CODE_LANGUAGE_ARKTS_HYBRID;
            if (isHybrid && curRuntime->GetLanguage() == AbilityRuntime::Runtime::Language::ETS) {
                auto &etsRuntime = static_cast<AbilityRuntime::ETSRuntime &>(*curRuntime);
                auto aniEnv = etsRuntime.GetAniEnv();
                if (aniEnv != nullptr) {
                    aniVmVoid = reinterpret_cast<void *>(aniEnv);
                }
                const auto &jsRuntime = etsRuntime.GetJsRuntime();
                if (jsRuntime) {
                    napiEnvVoid = reinterpret_cast<void *>(
                        static_cast<AbilityRuntime::JsRuntime &>(*jsRuntime).GetNapiEnv());
                }
            } else if (isHybrid && curRuntime->GetLanguage() == AbilityRuntime::Runtime::Language::JS) {
                napiEnvVoid = reinterpret_cast<void *>(
                    static_cast<AbilityRuntime::JsRuntime &>(*curRuntime).GetNapiEnv());
            }
            AbilityDelegatorRegistry::SetRuntimeEnvs(napiEnvVoid, aniVmVoid);
        }
        delegator->SetApiTargetVersion(targetVersion);
        delegator->Prepare();
        if (applicationInfo_ && applicationInfo_->arkTSMode == AbilityRuntime::CODE_LANGUAGE_ARKTS_HYBRID) {
            auto currentLanguage = application_->GetRuntime()->GetLanguage();
            auto targetLanguage = AbilityRuntime::Runtime::Language::JS;
            if (currentLanguage == AbilityRuntime::Runtime::Language::JS) {
                targetLanguage = AbilityRuntime::Runtime::Language::ETS;
            }
            auto interopTestRunner = TestRunner::Create(application_->GetRuntime(), args, false);
            auto interopDelegator = IAbilityDelegator::Create(application_->GetRuntime(),
                application_->GetAppContext(), std::move(interopTestRunner), record->observer);
            AbilityDelegatorRegistry::RegisterInstance(interopDelegator, args, targetLanguage);
            interopDelegator->SetApiTargetVersion(targetVersion);
            interopDelegator->Prepare();
        }
    } else { // FA model
        TAG_LOGD(AAFwkTag::APPKIT, "FA model");
        AbilityRuntime::Runtime::Options options;
        options.codePath = LOCAL_CODE_PATH;
        options.eventRunner = mainHandler_->GetEventRunner();
        options.hapPath = entryHapModuleInfo.hapPath;
        options.loadAce = false;
        options.isStageModel = false;
        options.isTestFramework = true;
        if (applicationInfo_) {
            options.apiTargetVersion = applicationInfo_->apiTargetVersion;
        }
        if (entryHapModuleInfo.abilityInfos.empty()) {
            TAG_LOGE(AAFwkTag::APPKIT, "abilityInfos failed");
            return false;
        }
        bool isFaJsModel = entryHapModuleInfo.abilityInfos.front().srcLanguage == "js" ? true : false;
        static auto runtime = AbilityRuntime::Runtime::Create(options);
        auto testRunner = TestRunner::Create(runtime, args, isFaJsModel);
        if (testRunner == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null testRunner");
            return false;
        }
        if (!testRunner->Initialize()) {
            TAG_LOGE(AAFwkTag::APPKIT, "initialize testRunner failed");
            return false;
        }
        auto delegator = std::make_shared<AbilityDelegator>(
            application_->GetAppContext(), std::move(testRunner), record->observer);
        AbilityDelegatorRegistry::RegisterInstance(delegator, args, runtime->GetLanguage());
        delegator->SetApiTargetVersion(targetVersion);
        delegator->Prepare();
    }
    return true;
}

void MainThread::UpdateWorkProcessInfo(std::shared_ptr<AppUpdateInfo> updateInfo)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    CHECK_POINTER_LOG(applicationImpl_, "applicationImpl_ is null");
    CHECK_POINTER_LOG(application_, "application_ is null");
    if (updateInfo != nullptr && !applicationImpl_->IsUpdated()) {
        TAG_LOGI(AAFwkTag::APPKIT, "called");
        auto applicationContext = AbilityRuntime::ApplicationContext::GetInstance();
        CHECK_POINTER_LOG(applicationContext, "null applicationContext");
        applicationImpl_->SetRecordId(updateInfo->appRecordId);
        applicationContext->SetAppRunningUniqueId(updateInfo->appRunningUniqueId);
        AppImageObserverManager::GetInstance().SetImageProcessType(static_cast<int32_t>(ImageProcessType::WORK));
        if (DFX_SetAppRunningUniqueId != nullptr) {
            DFX_SetAppRunningUniqueId(updateInfo->appRunningUniqueId.c_str(), updateInfo->appRunningUniqueId.length());
        }
        applicationImpl_->MarkUpdated();
        application_->OnHyperSnapUpdate();
    }
}

/**
 *
 * @brief launch the ability.
 *
 * @param abilityRecord The abilityRecord which belongs to the ability launched.
 *
 */
void MainThread::HandleLaunchAbility(const std::shared_ptr<AbilityLocalRecord> &abilityRecord,
    std::shared_ptr<AppUpdateInfo> updateInfo)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    CHECK_POINTER_LOG(abilityRecord, "parameter(abilityRecord) is null");
    std::string connector = "##";
    std::string traceName = __PRETTY_FUNCTION__ + connector;
    if (abilityRecord->GetWant() != nullptr) {
        traceName += abilityRecord->GetWant()->GetElement().GetBundleName();
    } else {
        TAG_LOGE(AAFwkTag::APPKIT, "null want");
    }
    HITRACE_METER_NAME(HITRACE_TAG_APP, traceName);
    CHECK_POINTER_LOG(applicationImpl_, "applicationImpl_ is null");
    CHECK_POINTER_LOG(abilityRecordMgr_, "abilityRecordMgr_ is null");

    bool needNotifyApplicationPreAbilityCreate = false;
    if (!AppExecFwk::AppImageObserverManager::GetInstance().IsAbilityCreated()) {
        AppExecFwk::AppImageObserverManager::GetInstance().SetAbilityCreated(true);
        needNotifyApplicationPreAbilityCreate = true;
    }

    UpdateWorkProcessInfo(updateInfo);
    if (needNotifyApplicationPreAbilityCreate) {
        TAG_LOGI(AAFwkTag::APPKIT, "NtfyAppPreAbiCreate");
        AppExecFwk::AppImageObserverManager::GetInstance().NotifyApplicationPreAbilityCreate();
    }

    if (!CheckAndUpdateRuntime(abilityRecord)) {
        TAG_LOGE(AAFwkTag::APPKIT, "UpdateRuntime failed");
        return;
    }

    auto abilityToken = abilityRecord->GetToken();
    CHECK_POINTER_LOG(abilityToken, "abilityRecord->GetToken failed");
    std::string entry = "MainThread::HandleLaunchAbility";
    FreezeUtil::GetInstance().AddLifecycleEvent(abilityToken, entry);

    abilityRecordMgr_->SetToken(abilityToken);
    abilityRecordMgr_->AddAbilityRecord(abilityToken, abilityRecord);

    if (!IsApplicationReady()) {
        TAG_LOGE(AAFwkTag::APPKIT, "should launch application first");
        return;
    }

    if (!CheckAbilityItem(abilityRecord)) {
        TAG_LOGE(AAFwkTag::APPKIT, "record invalid");
        return;
    }
    LoadExtensionBlockList(abilityRecord);
    mainThreadState_ = MainThreadState::RUNNING;
    wptr<MainThread> weak = this;
    auto callback = [weak, abilityRecord](const std::shared_ptr<AbilityRuntime::Context> &stageContext) {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        auto application = appThread->GetApplication();
        if (application == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null application");
            return;
        }
        auto &runtime = application->GetRuntime();
        appThread->UpdateRuntimeModuleChecker(runtime);
#ifdef APP_ABILITY_USE_TWO_RUNNER
        AbilityThread::AbilityThreadMain(application, abilityRecord, stageContext);
#else
        AbilityThread::AbilityThreadMain(application, abilityRecord, mainHandler_->GetEventRunner(), stageContext);
#endif
    };
#ifdef SUPPORT_SCREEN
    Rosen::DisplayId displayId = Rosen::DISPLAY_ID_INVALID;
    if (abilityRecord->GetWant() != nullptr) {
        displayId = static_cast<uint64_t>(abilityRecord->GetWant()->GetIntParam(
            AAFwk::Want::PARAM_RESV_DISPLAY_ID, static_cast<uint32_t>(Rosen::DISPLAY_ID_INVALID)));
    }
    if (displayId == Rosen::DISPLAY_ID_INVALID) {
        displayId = static_cast<Rosen::DisplayId>(AAFwk::DisplayUtil::GetDefaultDisplayId());
    }
    Rosen::DisplayManager::GetInstance().AddDisplayIdFromAms(displayId, abilityRecord->GetToken());
    TAG_LOGD(AAFwkTag::APPKIT, "add displayId: %{public}" PRIu64, displayId);
#endif
    bool isAsyncCallback = false;
    std::shared_ptr<AbilityRuntime::Context> stageContext = application_->AddAbilityStage(
        abilityRecord, callback, isAsyncCallback);
    if (isAsyncCallback) {
        return;
    }
    auto &runtime = application_->GetRuntime();
    UpdateRuntimeModuleChecker(runtime);
#ifdef APP_ABILITY_USE_TWO_RUNNER
    AbilityThread::AbilityThreadMain(application_, abilityRecord, stageContext);
#else
    AbilityThread::AbilityThreadMain(application_, abilityRecord, mainHandler_->GetEventRunner(), stageContext);
#endif
}

/**
 *
 * @brief Clean the ability but don't notify ams.
 *
 * @param token The token which belongs to the ability launched.
 *
 */
void MainThread::HandleCleanAbilityLocal(const sptr<IRemoteObject> &token)
{
    TAG_LOGD(AAFwkTag::APPKIT, "start");
    if (!IsApplicationReady()) {
        TAG_LOGE(AAFwkTag::APPKIT, "should launch application first");
        return;
    }

    if (token == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null token");
        return;
    }

    std::shared_ptr<AbilityLocalRecord> record = abilityRecordMgr_->GetAbilityItem(token);
    CHECK_POINTER_TAG_LOG(record, AAFwkTag::APPKIT, "abilityRecord not found");
    std::shared_ptr<AbilityInfo> abilityInfo = record->GetAbilityInfo();
    CHECK_POINTER_TAG_LOG(abilityInfo, AAFwkTag::APPKIT, "record->GetAbilityInfo() failed");
    TAG_LOGD(AAFwkTag::APPKIT, "ability name: %{public}s", abilityInfo->name.c_str());
    abilityRecordMgr_->RemoveAbilityRecord(token);
    application_->CleanAbilityStage(token, abilityInfo, false);
#ifdef APP_ABILITY_USE_TWO_RUNNER
    std::shared_ptr<EventRunner> runner = record->GetEventRunner();
    if (runner != nullptr) {
        int ret = runner->Stop();
        if (ret != ERR_OK) {
            TAG_LOGE(AAFwkTag::APPKIT, "ret = %{public}d", ret);
        }
        abilityRecordMgr_->RemoveAbilityRecord(token);
        application_->CleanAbilityStage(token, abilityInfo, false);
    } else {
        TAG_LOGW(AAFwkTag::APPKIT, "runner not found");
    }
#endif
}

/**
 *
 * @brief Clean the ability.
 *
 * @param token The token which belongs to the ability launched.
 *
 */
void MainThread::HandleCleanAbility(const sptr<IRemoteObject> &token, bool isCacheProcess)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    if (applicationInfo_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null applicationInfo");
        return;
    }
    TAG_LOGD(AAFwkTag::APPKIT, "Handle clean ability start, app is %{public}s.", applicationInfo_->name.c_str());

    if (!IsApplicationReady()) {
        TAG_LOGE(AAFwkTag::APPKIT, "should launch application first");
        return;
    }
    CHECK_POINTER_TAG_LOG(token, AAFwkTag::APPKIT, "token is null");
    std::shared_ptr<AbilityLocalRecord> record = abilityRecordMgr_->GetAbilityItem(token);
    CHECK_POINTER_TAG_LOG(record, AAFwkTag::APPKIT, "abilityRecord not found");
    std::shared_ptr<AbilityInfo> abilityInfo = record->GetAbilityInfo();
    CHECK_POINTER_TAG_LOG(abilityInfo, AAFwkTag::APPKIT, "record->GetAbilityInfo() failed");
#ifdef SUPPORT_GRAPHICS
    if (abilityInfo->type == AbilityType::PAGE && abilityInfo->isStageBasedModel) {
        AppRecovery::GetInstance().RemoveAbility(token);
    }
#endif
    abilityRecordMgr_->RemoveAbilityRecord(token);
    application_->CleanAbilityStage(token, abilityInfo, isCacheProcess);
#ifdef APP_ABILITY_USE_TWO_RUNNER
    std::shared_ptr<EventRunner> runner = record->GetEventRunner();
    if (runner != nullptr) {
        int ret = runner->Stop();
        if (ret != ERR_OK) {
            TAG_LOGE(AAFwkTag::APPKIT, "ret = %{public}d", ret);
        }
        abilityRecordMgr_->RemoveAbilityRecord(token);
        application_->CleanAbilityStage(token, abilityInfo, isCacheProcess);
    } else {
        TAG_LOGW(AAFwkTag::APPKIT, "runner not found");
    }
#endif
    appMgr_->AbilityCleaned(token);
    TAG_LOGD(AAFwkTag::APPKIT, "end. app: %{public}s, ability: %{public}s.",
        applicationInfo_->name.c_str(), abilityInfo->name.c_str());
}

/**
 *
 * @brief Foreground the application.
 *
 */
void MainThread::HandleForegroundApplication()
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    FreezeUtil::GetInstance().AddAppLifecycleEvent(0, "HandleForegroundApplication");
    TAG_LOGI(AAFwkTag::APPKIT, "called");
    if ((application_ == nullptr) || (appMgr_ == nullptr)) {
        TAG_LOGE(AAFwkTag::APPKIT, "null application_ or appMgr_");
        return;
    }

    if (!applicationImpl_->PerformForeground()) {
        FreezeUtil::GetInstance().AddAppLifecycleEvent(0, "HandleForegroundApplication; fail");
        TAG_LOGE(AAFwkTag::APPKIT, "applicationImpl_->PerformForeground() failed");
    }

    // Start accessing PurgeableMem if the event of foreground is successful.
#ifdef IMAGE_PURGEABLE_PIXELMAP
    PurgeableMem::PurgeableResourceManager::GetInstance().BeginAccessPurgeableMem();
#endif

    TAG_LOGD(AAFwkTag::APPKIT, "to foreground success, recordId is %{public}d", applicationImpl_->GetRecordId());
    appMgr_->ApplicationForegrounded(applicationImpl_->GetRecordId());
}

/**
 *
 * @brief Background the application.
 *
 */
void MainThread::HandleBackgroundApplication()
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    TAG_LOGI(AAFwkTag::APPKIT, "start");
    FreezeUtil::GetInstance().AddAppLifecycleEvent(0, "HandleBackgroundApplication");
    if ((application_ == nullptr) || (appMgr_ == nullptr)) {
        TAG_LOGE(AAFwkTag::APPKIT, "error");
        return;
    }

    if (!applicationImpl_->PerformBackground()) {
        TAG_LOGE(AAFwkTag::APPKIT, "applicationImpl_->PerformBackground() failed");
    }

    // End accessing PurgeableMem if the event of background is successful.
#ifdef IMAGE_PURGEABLE_PIXELMAP
    PurgeableMem::PurgeableResourceManager::GetInstance().EndAccessPurgeableMem();
#endif

    appMgr_->ApplicationBackgrounded(applicationImpl_->GetRecordId());
}

/**
 *
 * @brief Terminate the application.
 *
 * @param isLastProcess When it is the last application process, pass in true.
 */
void MainThread::HandleTerminateApplication(bool isLastProcess)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    TAG_LOGD(AAFwkTag::APPKIT, "start");
    if ((applicationImpl_ == nullptr) || (appMgr_ == nullptr)) {
        TAG_LOGE(AAFwkTag::APPKIT, "error");
        return;
    }

    if (!applicationImpl_->PerformTerminate(isLastProcess)) {
        TAG_LOGD(AAFwkTag::APPKIT, "PerformTerminate() failed");
    }

    std::shared_ptr<EventRunner> runner = mainHandler_->GetEventRunner();
    if (runner == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null runner");
        return;
    }

    if (watchdog_ != nullptr && !watchdog_->IsStopWatchdog()) {
        watchdog_->Stop();
        watchdog_ = nullptr;
    }

    int ret = runner->Stop();
    if (ret != ERR_OK) {
        TAG_LOGE(AAFwkTag::APPKIT, "ret = %{public}d", ret);
    }
    SetRunnerStarted(false);
    appMgr_->ApplicationTerminated(applicationImpl_->GetRecordId());
}

/**
 *
 * @brief Shrink the memory which used by application.
 *
 * @param level Indicates the memory trim level, which shows the current memory usage status.
 *
 */
void MainThread::HandleShrinkMemory(const int level)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);

    if (applicationImpl_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null applicationImpl_");
        return;
    }

    applicationImpl_->PerformMemoryLevel(level);
}

/**
 *
 * @brief Handle NotifyMemoryLevel.
 *
 * @param level Indicates the memory trim level, which shows the current memory usage status.
 *
 */
void MainThread::HandleMemoryLevel(int level)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    TAG_LOGD(AAFwkTag::APPKIT, "start");

    if (application_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null application_");
        return;
    }

    application_->OnMemoryLevel(level);
}

/**
 *
 * @brief send the new config to the application.
 *
 * @param config The updated config.
 * @param reason The updated scene flag.
 *
 */
void MainThread::HandleConfigurationUpdated(const Configuration &config, ConfigUpdateReason reason)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    if (applicationImpl_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null applicationImpl_");
        return;
    }

    applicationImpl_->PerformConfigurationUpdated(config, reason);
}

void MainThread::TaskTimeoutDetected(const std::shared_ptr<EventRunner> &runner)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    TAG_LOGD(AAFwkTag::APPKIT, "start");

    auto deliveryTimeoutCallback = []() {
        TAG_LOGD(AAFwkTag::APPKIT, "delivery timeout");
    };
    auto distributeTimeoutCallback = []() {
        TAG_LOGD(AAFwkTag::APPKIT, "distribute timeout");
    };

    if (runner !=nullptr && mainHandler_ != nullptr) {
        runner->SetDeliveryTimeout(DELIVERY_TIME);
        mainHandler_->SetDeliveryTimeoutCallback(deliveryTimeoutCallback);

        runner->SetDistributeTimeout(DISTRIBUTE_TIME);
        mainHandler_->SetDistributeTimeoutCallback(distributeTimeoutCallback);
    }
}

void MainThread::Init(const std::shared_ptr<EventRunner> &runner)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    TAG_LOGD(AAFwkTag::APPKIT, "Start");
    mainHandler_ = std::make_shared<MainHandler>(runner, this);
    bool isRescueMode = (system::GetParameter("soc.boot.mode", "") == "rescue");
    if (!isRescueMode) {
        TAG_LOGE(AAFwkTag::APPKIT, "is not in rescue mode");
        watchdog_ = std::make_shared<Watchdog>();
    }

    //since kernel use lazy fpu, but MainThread use fpu frequently
    //set actv eager fpu enhance performance of MainThread
    //it is ok if kernel do not support this prctl, the overhead of this prctl is ~ns.
    #define HM_PR_ACTV_SET_FPU 0x53465055
    #define ACTV_EAGER_FPU_BIT  0x1
    (void)prctl(HM_PR_ACTV_SET_FPU, ACTV_EAGER_FPU_BIT, true, 0, 0);

    extensionConfigMgr_ = std::make_shared<AbilityRuntime::ExtensionConfigMgr>();
    wptr<MainThread> weak = this;
    auto task = [weak]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null abilityThread");
            return;
        }
        appThread->SetRunnerStarted(true);
    };
    if (!mainHandler_->PostTask(task, "MainThread:SetRunnerStarted")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
    TaskTimeoutDetected(runner);

    if (!isRescueMode) {
        TAG_LOGE(AAFwkTag::APPKIT, "is not in rescue mode");
        watchdog_->Init(mainHandler_);
    }

    AppExecFwk::AppfreezeInner::GetInstance()->SetMainHandler(mainHandler_);
}

void MainThread::HandleSignal(int signal, [[maybe_unused]] siginfo_t *siginfo, void *context)
{
    if (signal != MUSL_SIGNAL_JSHEAP) {
        TAG_LOGE(AAFwkTag::APPKIT, "signal: %{public}d", signal);
        return;
    }
    TAG_LOGI(AAFwkTag::APPKIT, "sival_int: %{public}d", siginfo->si_value.sival_int);
    if (static_cast<SignalType>(siginfo->si_value.sival_int) != SignalType::SIGNAL_FORCE_FULLGC) {
        HandleDumpHeapPrepare();
    }
    switch (static_cast<SignalType>(siginfo->si_value.sival_int)) {
        case SignalType::SIGNAL_JSHEAP_OLD: {
            auto heapFunc = []() { return MainThread::HandleDumpHeap(false); };
            mainHandler_->PostTask(heapFunc, "MainThread::SIGNAL_JSHEAP_OLD");
            break;
        }
        case SignalType::SIGNAL_JSHEAP: {
            auto heapFunc = []() { return MainThread::HandleDumpHeap(false); };
            mainHandler_->PostTask(heapFunc, "MainThread::SIGNAL_JSHEAP");
            break;
        }
        case SignalType::SIGNAL_JSHEAP_PRIV: {
            auto privateHeapFunc = []() { return MainThread::HandleDumpHeap(true); };
            mainHandler_->PostTask(privateHeapFunc, "MainThread:SIGNAL_JSHEAP_PRIV");
            break;
        }
        case SignalType::SIGNAL_NO_TRIGGERID: {
            auto heapFunc = []() { return MainThread::HandleDumpHeap(false); };
            mainHandler_->PostTask(heapFunc, "MainThread::SIGNAL_JSHEAP");

            auto noTriggerIdFunc = []() { MainThread::DestroyHeapProfiler(); };
            mainHandler_->PostTask(noTriggerIdFunc, "MainThread::SIGNAL_NO_TRIGGERID");
            break;
        }
        case SignalType::SIGNAL_NO_TRIGGERID_PRIV: {
            auto privateHeapFunc = []() { return MainThread::HandleDumpHeap(true); };
            mainHandler_->PostTask(privateHeapFunc, "MainThread:SIGNAL_JSHEAP_PRIV");

            auto noTriggerIdFunc = []() { MainThread::DestroyHeapProfiler(); };
            mainHandler_->PostTask(noTriggerIdFunc, "MainThread::SIGNAL_NO_TRIGGERID_PRIV");
            break;
        }
        case SignalType::SIGNAL_FORCE_FULLGC: {
            auto forceFullGCFunc = []() { MainThread::ForceFullGC(); };
            ffrt::submit(forceFullGCFunc);
            break;
        }
        default:
            break;
    }
}

void MainThread::HandleDumpHeapPrepare()
{
    TAG_LOGD(AAFwkTag::APPKIT, "start");
    if (mainHandler_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null mainHandler");
        return;
    }
    auto app = applicationForDump_.lock();
    if (app == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null app");
        return;
    }
    auto &runtime = app->GetRuntime();
    if (runtime == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null runtime");
        return;
    }
    runtime->GetHeapPrepare();
}

void MainThread::HandleDumpHeap(bool isPrivate)
{
    TAG_LOGD(AAFwkTag::APPKIT, "start");
    if (mainHandler_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null mainHandler");
        return;
    }
    auto app = applicationForDump_.lock();
    if (app == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null app");
        return;
    }
    auto &runtime = app->GetRuntime();
    if (runtime == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null runtime");
        return;
    }
    auto taskFork = [&runtime, &isPrivate] {
        TAG_LOGD(AAFwkTag::APPKIT, "HandleDump Heap taskFork start");
        time_t startTime = time(nullptr);
        int pid = -1;
        if ((pid = fork()) < 0) {
            TAG_LOGE(AAFwkTag::APPKIT, "err:%{public}d", errno);
            return;
        }
        if (pid == 0) {
            runtime->AllowCrossThreadExecution();
            runtime->DumpHeapSnapshot(isPrivate);
            TAG_LOGI(AAFwkTag::APPKIT, "HandleDumpHeap successful, now you can check some file");
            _exit(0);
        }
        while (true) {
            int status = 0;
            pid_t p = waitpid(pid, &status, 0);
            if (p < 0) {
                TAG_LOGE(AAFwkTag::APPKIT, "HandleDumpHeap waitpid return p=%{public}d, err:%{public}d", p, errno);
                break;
            }
            if (p == pid) {
                TAG_LOGE(AAFwkTag::APPKIT, "HandleDumpHeap dump process exited status: %{public}d", status);
                break;
            }
            if (time(nullptr) > startTime + TIME_OUT) {
                TAG_LOGE(AAFwkTag::APPKIT, "time out to wait childprocess, killing forkpid %{public}d", pid);
                kill(pid, SIGKILL);
                break;
            }
            usleep(DEFAULT_SLEEP_TIME);
        }
    };

    ffrt::submit(taskFork, {}, {}, ffrt::task_attr().qos(ffrt::qos_user_initiated));
    runtime->DumpCpuProfile();
}

void MainThread::DestroyHeapProfiler()
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (mainHandler_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null mainHandler");
        return;
    }

    auto task = [] {
        auto app = applicationForDump_.lock();
        if (app == nullptr || app->GetRuntime() == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null runtime");
            return;
        }
        app->GetRuntime()->DestroyHeapProfiler();
    };
    mainHandler_->PostTask(task, "MainThread:DestroyHeapProfiler");
}

void MainThread::ForceFullGC()
{
    TAG_LOGD(AAFwkTag::APPKIT, "Force fullGC");
    if (mainHandler_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null mainHandler");
        return;
    }

    auto task = [] {
        auto app = applicationForDump_.lock();
        if (app == nullptr || app->GetRuntime() == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null runtime");
            return;
        }
        app->GetRuntime()->ForceFullGC();
    };
    mainHandler_->PostTask(task, "MainThread:ForceFullGC");
}

void MainThread::Start()
{
    TAG_LOGI(AAFwkTag::APPKIT, "mainthread start, pid:%{public}d", getprocpid());

    std::shared_ptr<EventRunner> runner = EventRunner::GetMainEventRunner();
    if (runner == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null runner");
        return;
    }
    sptr<MainThread> thread = sptr<MainThread>(new (std::nothrow) MainThread());
    if (thread == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null thread");
        return;
    }

    struct sigaction sigAct;
    sigemptyset(&sigAct.sa_mask);
    sigAct.sa_flags = SA_SIGINFO;
    sigAct.sa_sigaction = &MainThread::HandleSignal;
    sigaction(MUSL_SIGNAL_JSHEAP, &sigAct, NULL);

    thread->Init(runner);

    thread->Attach();

    int ret = runner->Run();
    if (ret != ERR_OK) {
        TAG_LOGE(AAFwkTag::APPKIT, "ret = %{public}d", ret);
    }

    thread->RemoveAppMgrDeathRecipient();
}

void MainThread::StartChild(const std::map<std::string, int32_t> &fds)
{
#ifdef SUPPORT_CHILD_PROCESS
    TAG_LOGI(AAFwkTag::APPKIT, "MainThread StartChild, fds size:%{public}zu", fds.size());
    ChildMainThread::Start(fds);
#endif  // SUPPORT_CHILD_PROCESS
}

void MainThread::PreloadExtensionPlugin()
{
    AbilityRuntime::ExtensionPluginInfo::GetInstance().Preload();
}

MainThread::MainHandler::MainHandler(const std::shared_ptr<EventRunner> &runner, const sptr<MainThread> &thread)
    : AppExecFwk::EventHandler(runner), mainThreadObj_(thread)
{}

/**
 *
 * @brief Process the event.
 *
 * @param event the event want to be processed.
 *
 */
void MainThread::MainHandler::ProcessEvent(const OHOS::AppExecFwk::InnerEvent::Pointer &event)
{
    auto eventId = event->GetInnerEventId();
    if (eventId == CHECK_MAIN_THREAD_IS_ALIVE) {
        auto mt = mainThreadObj_.promote();
        if (mt != nullptr) {
            mt->CheckMainThreadIsAlive();
        }
    }
}

/**
 *
 * @brief Check whether the OHOSApplication is ready.
 *
 * @return if the record is legal, return true. else return false.
 *
 */
bool MainThread::IsApplicationReady() const
{
    TAG_LOGD(AAFwkTag::APPKIT, "start");
    if (application_ == nullptr || applicationImpl_ == nullptr) {
        TAG_LOGW(AAFwkTag::APPKIT, "null application_ or applicationImpl_");
        return false;
    }

    return true;
}

#ifdef ABILITY_LIBRARY_LOADER
/**
 *
 * @brief Load the ability library.
 *
 * @param libraryPaths the library paths.
 *
 */
void MainThread::LoadAbilityLibrary(const std::vector<std::string> &libraryPaths)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
#ifdef ABILITY_LIBRARY_LOADER
    TAG_LOGD(AAFwkTag::APPKIT, "start");
#ifdef SUPPORT_SCREEN
    LoadAceAbilityLibrary();
#endif
    size_t size = libraryPaths.size();
    for (size_t index = 0; index < size; index++) {
        std::string libraryPath = libraryPaths[index];
        TAG_LOGD(AAFwkTag::APPKIT, "Try to scanDir %{public}s", libraryPath.c_str());
        if (!ScanDir(libraryPath, fileEntries_)) {
            TAG_LOGW(AAFwkTag::APPKIT, "scanDir %{public}s not exits", libraryPath.c_str());
        }
        libraryPath = libraryPath + "/libs";
        if (!ScanDir(libraryPath, fileEntries_)) {
            TAG_LOGW(AAFwkTag::APPKIT, "scanDir %{public}s not exits", libraryPath.c_str());
        }
    }

    if (fileEntries_.empty()) {
        TAG_LOGD(AAFwkTag::APPKIT, "No ability library");
        return;
    }

    char resolvedPath[PATH_MAX] = {0};
    void *handleAbilityLib = nullptr;
    for (const auto& fileEntry : fileEntries_) {
        if (fileEntry.empty() || fileEntry.size() >= PATH_MAX) {
            continue;
        }
        if (realpath(fileEntry.c_str(), resolvedPath) == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "errno = %{public}d", errno);
            continue;
        }

        handleAbilityLib = dlopen(resolvedPath, RTLD_NOW | RTLD_GLOBAL);
        if (handleAbilityLib == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "dlopen %{public}s, [%{public}s] failed", resolvedPath, dlerror());
            exit(-1);
        }
        TAG_LOGI(AAFwkTag::APPKIT, "Success to dlopen %{public}s", fileEntry.c_str());
        handleAbilityLib_.emplace_back(handleAbilityLib);
    }
#endif  // ABILITY_LIBRARY_LOADER
}

void MainThread::LoadAceAbilityLibrary()
{
    void *AceAbilityLib = nullptr;
    const char *path = Ace::AceForwardCompatibility::GetAceLibName();
    AceAbilityLib = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (AceAbilityLib == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "dlopen %{public}s, [%{public}s] failed", path, dlerror());
    } else {
        TAG_LOGD(AAFwkTag::APPKIT, "Success to dlopen %{public}s", path);
        handleAbilityLib_.emplace_back(AceAbilityLib);
    }
}

void MainThread::LoadAppLibrary()
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
#ifdef APPLICATION_LIBRARY_LOADER
    std::string appPath = applicationLibraryPath;
    TAG_LOGI(AAFwkTag::APPKIT, "calling dlopen. appPath=%{public}s", appPath.c_str());
    handleAppLib_ = dlopen(appPath.c_str(), RTLD_NOW | RTLD_GLOBAL);
    if (handleAppLib_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "dlopen %{public}s, [%{public}s] failed", appPath.c_str(), dlerror());
        exit(-1);
    }
#endif  // APPLICATION_LIBRARY_LOADER
}

void MainThread::LoadAppDetailAbilityLibrary(std::string &nativeLibraryPath)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
#ifdef ABILITY_LIBRARY_LOADER
    TAG_LOGD(AAFwkTag::APPKIT, "try to scanDir %{public}s", nativeLibraryPath.c_str());
    std::vector<std::string> fileEntries;
    if (!ScanDir(nativeLibraryPath, fileEntries)) {
        TAG_LOGW(AAFwkTag::APPKIT, "scanDir %{public}s not exits", nativeLibraryPath.c_str());
    }
    if (fileEntries.empty()) {
        TAG_LOGW(AAFwkTag::APPKIT, "No ability library");
        return;
    }
    char resolvedPath[PATH_MAX] = {0};
    void *handleAbilityLib = nullptr;
    for (const auto& fileEntry : fileEntries) {
        if (fileEntry.empty() || fileEntry.size() >= PATH_MAX) {
            continue;
        }
        if (realpath(fileEntry.c_str(), resolvedPath) == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "errno: %{public}d", errno);
            continue;
        }

        handleAbilityLib = dlopen(resolvedPath, RTLD_NOW | RTLD_GLOBAL);
        if (handleAbilityLib == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "dlopen %{public}s, [%{public}s] failed", resolvedPath, dlerror());
            exit(-1);
        }
        TAG_LOGI(AAFwkTag::APPKIT, "Success to dlopen %{public}s", fileEntry.c_str());
        handleAbilityLib_.emplace_back(handleAbilityLib);
    }
#endif // ABILITY_LIBRARY_LOADER
}

bool MainThread::ScanDir(const std::string &dirPath, std::vector<std::string> &files)
{
    DIR *dirp = opendir(dirPath.c_str());
    if (dirp == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "MainThread::ScanDir open dir:%{public}s fail", dirPath.c_str());
        return false;
    }
    struct dirent *df = nullptr;
    for (;;) {
        df = readdir(dirp);
        if (df == nullptr) {
            break;
        }

        std::string currentName(df->d_name);
        if (currentName.compare(".") == 0 || currentName.compare("..") == 0) {
            continue;
        }

        if (CheckFileType(currentName, abilityLibraryType_)) {
            files.emplace_back(dirPath + pathSeparator_ + currentName);
        }
    }

    if (closedir(dirp) == -1) {
        TAG_LOGW(AAFwkTag::APPKIT, "close dir fail");
    }
    return true;
}

/**
 *
 * @brief Check the fileType.
 *
 * @param fileName The fileName of the lib.
 * @param extensionName The extensionName of the lib.
 *
 * @return if the FileType is legal, return true. else return false.
 *
 */
bool MainThread::CheckFileType(const std::string &fileName, const std::string &extensionName)
{
    TAG_LOGD(AAFwkTag::APPKIT, "path is %{public}s, support suffix is %{public}s",
        fileName.c_str(),
        extensionName.c_str());

    if (fileName.empty()) {
        TAG_LOGE(AAFwkTag::APPKIT, "file name empty");
        return false;
    }

    auto position = fileName.rfind('.');
    if (position == std::string::npos) {
        TAG_LOGW(AAFwkTag::APPKIT, "filename no extension name");
        return false;
    }

    std::string suffixStr = fileName.substr(position);
    return LowerStr(suffixStr) == extensionName;
}

void MainThread::HandleScheduleAcceptWant(const AAFwk::Want &want, const std::string &moduleName)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (!application_) {
        TAG_LOGE(AAFwkTag::APPKIT, "null application_");
        return;
    }
    wptr<MainThread> weak = this;
    auto callback = [weak, wantCopy = want] (std::string specifiedFlag) {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        if (appThread->appMgr_ == nullptr || appThread->applicationImpl_ == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appMgr_");
            return;
        }
        appThread->appMgr_->ScheduleAcceptWantDone(appThread->applicationImpl_->GetRecordId(),
            wantCopy, specifiedFlag);
    };
    bool isAsync = false;
    application_->ScheduleAcceptWant(want, moduleName, callback, isAsync);
    if (!isAsync) {
        TAG_LOGI(AAFwkTag::APPKIT, "sync call");
    }
}

void MainThread::ScheduleAcceptWant(const AAFwk::Want &want, const std::string &moduleName)
{
    TAG_LOGD(AAFwkTag::APPKIT, "start");
    wptr<MainThread> weak = this;
    auto task = [weak, want, moduleName]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleScheduleAcceptWant(want, moduleName);
    };
    if (mainHandler_ == nullptr || !mainHandler_->PostTask(task, "MainThread:AcceptWant")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
    TAG_LOGI(AAFwkTag::APPKIT, "ScheduleAcceptWant end");
}

void MainThread::SchedulePrepareTerminate(const std::string &moduleName)
{
    TAG_LOGD(AAFwkTag::APPKIT, "SchedulePrepareTerminate called");
    if (getpid() == gettid()) {
        TAG_LOGE(AAFwkTag::APPKIT, "in app main thread");
        HandleSchedulePrepareTerminate(moduleName);
        return;
    }
    wptr<MainThread> weak = this;
    auto asyncTask = [weak, moduleName] {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleSchedulePrepareTerminate(moduleName);
    };
    if (mainHandler_ == nullptr || !mainHandler_->PostTask(asyncTask, "MainThread::SchedulePrepareTerminate")) {
        TAG_LOGE(AAFwkTag::APPKIT, "post asynctask failed");
    }
}

void MainThread::HandleSchedulePrepareTerminate(const std::string &moduleName)
{
    if (!application_) {
        TAG_LOGE(AAFwkTag::APPKIT, "null application_");
        return;
    }

    wptr<MainThread> weak = this;
    auto callback = [weak, _moduleName = moduleName] (AppExecFwk::OnPrepareTerminationResult result) {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        TAG_LOGI(AAFwkTag::APPKIT, "in callback, prepareTermination=%{public}d, isExist=%{public}d",
            result.prepareTermination, result.isExist);
        AbilityManagerClient::GetInstance()->KillProcessWithPrepareTerminateDone(_moduleName,
            result.prepareTermination, result.isExist);
    };
    bool isAsync = false;
    application_->SchedulePrepareTerminate(moduleName, callback, isAsync);
    if (!isAsync) {
        TAG_LOGI(AAFwkTag::APPKIT, "sync call");
    }
}

void MainThread::HandleScheduleNewProcessRequest(const AAFwk::Want &want, const std::string &moduleName)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (!application_) {
        TAG_LOGE(AAFwkTag::APPKIT, "null application_");
        return;
    }
    wptr<MainThread> weak = this;
    auto callback = [weak, wantCopy = want] (std::string specifiedFlag) {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        if (appThread->appMgr_ == nullptr || appThread->applicationImpl_ == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appMgr_");
            return;
        }
        appThread->appMgr_->ScheduleNewProcessRequestDone(appThread->applicationImpl_->GetRecordId(),
            wantCopy, specifiedFlag);
    };
    bool isAsync = false;
    application_->ScheduleNewProcessRequest(want, moduleName, callback, isAsync);
    if (!isAsync) {
        TAG_LOGD(AAFwkTag::APPKIT, "sync call");
    }
}

void MainThread::ScheduleNewProcessRequest(const AAFwk::Want &want, const std::string &moduleName)
{
    TAG_LOGD(AAFwkTag::APPKIT, "start");
    wptr<MainThread> weak = this;
    auto task = [weak, want, moduleName]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleScheduleNewProcessRequest(want, moduleName);
    };
    if (!mainHandler_->PostTask(task, "MainThread:ScheduleNewProcessRequest")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
    TAG_LOGI(AAFwkTag::APPKIT, "ScheduleNewProcessRequest end");
}

void MainThread::CheckMainThreadIsAlive()
{
    auto tmpWatchdog = watchdog_;
    if (tmpWatchdog == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null Watch dog");
        return;
    }

    tmpWatchdog->SetAppMainThreadState(true);
    tmpWatchdog->AllowReportEvent();
    tmpWatchdog = nullptr;
}
#endif  // ABILITY_LIBRARY_LOADER

int32_t MainThread::ScheduleNotifyLoadRepairPatch(const std::string &bundleName,
    const sptr<IQuickFixCallback> &callback, const int32_t recordId)
{
    HITRACE_METER_NAME(HITRACE_TAG_ABILITY_MANAGER, __PRETTY_FUNCTION__);
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    wptr<MainThread> weak = this;
    auto task = [weak, bundleName, callback, recordId]() {
        auto appThread = weak.promote();
        if (appThread == nullptr || appThread->application_ == nullptr || callback == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null parameter");
            return;
        }

        bool ret = true;
        std::vector<std::pair<std::string, std::string>> hqfFilePair;
        if (appThread->GetHqfFileAndHapPath(bundleName, hqfFilePair)) {
            for (auto it = hqfFilePair.begin(); it != hqfFilePair.end(); it++) {
                TAG_LOGI(AAFwkTag::APPKIT, "hqfFile: %{private}s, hapPath: %{private}s",
                    it->first.c_str(), it->second.c_str());
                ret = appThread->application_->NotifyLoadRepairPatch(it->first, it->second);
            }
        } else {
            TAG_LOGD(AAFwkTag::APPKIT, "ScheduleNotifyLoadRepairPatch, There's no hqfFile need to load");
        }

        callback->OnLoadPatchDone(ret ? NO_ERROR : ERR_INVALID_OPERATION, recordId);
    };
    if (mainHandler_ == nullptr || !mainHandler_->PostTask(task, "MainThread:NotifyLoadRepairPatch")) {
        TAG_LOGE(AAFwkTag::APPKIT, "ScheduleNotifyLoadRepairPatch, Post task failed");
        return ERR_INVALID_VALUE;
    }

    return NO_ERROR;
}

int32_t MainThread::ScheduleNotifyHotReloadPage(const sptr<IQuickFixCallback> &callback, const int32_t recordId)
{
    HITRACE_METER_NAME(HITRACE_TAG_ABILITY_MANAGER, __PRETTY_FUNCTION__);
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    wptr<MainThread> weak = this;
    auto task = [weak, callback, recordId]() {
        auto appThread = weak.promote();
        if (appThread == nullptr || appThread->application_ == nullptr || callback == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null parameter");
            return;
        }
        auto ret = appThread->application_->NotifyHotReloadPage();
        callback->OnReloadPageDone(ret ? NO_ERROR : ERR_INVALID_OPERATION, recordId);
    };
    if (mainHandler_ == nullptr || !mainHandler_->PostTask(task, "MainThread:NotifyHotReloadPage")) {
        TAG_LOGE(AAFwkTag::APPKIT, "Post task failed");
        return ERR_INVALID_VALUE;
    }

    return NO_ERROR;
}

bool MainThread::GetHqfFileAndHapPath(const std::string &bundleName,
    std::vector<std::pair<std::string, std::string>> &fileMap)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    auto bundleMgrHelper = DelayedSingleton<BundleMgrHelper>::GetInstance();
    if (bundleMgrHelper == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null bundleMgrHelper");
        return false;
    }

    BundleInfo bundleInfo;
    if (bundleMgrHelper->GetBundleInfoForSelfWithOutCache(
        (static_cast<int32_t>(AppExecFwk::GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_HAP_MODULE) +
        static_cast<int32_t>(AppExecFwk::GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_ABILITY) +
        static_cast<int32_t>(AppExecFwk::GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_APPLICATION) +
        static_cast<int32_t>(AppExecFwk::GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_DISABLE) +
        static_cast<int32_t>(AppExecFwk::GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_SIGNATURE_INFO) +
        static_cast<int32_t>(AppExecFwk::GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_EXTENSION_ABILITY) +
        static_cast<int32_t>(AppExecFwk::GetBundleInfoFlag::GET_BUNDLE_INFO_WITH_METADATA)), bundleInfo) != ERR_OK) {
        TAG_LOGE(AAFwkTag::APPKIT, "Get bundle info of %{public}s failed", bundleName.c_str());
        return false;
    }

    for (auto hapInfo : bundleInfo.hapModuleInfos) {
        if (hapInfo.hqfInfo.hqfFilePath.empty()) {
            continue;
        }
        std::string resolvedHapPath(AbilityBase::GetLoadPath(hapInfo.hapPath));
        std::string resolvedHqfFile(AbilityBase::GetLoadPath(hapInfo.hqfInfo.hqfFilePath));
        TAG_LOGD(AAFwkTag::APPKIT, "bundleName: %{public}s, moduleName: %{public}s, processName: %{private}s, "
            "hqf file: %{private}s, hap path: %{private}s", bundleName.c_str(), hapInfo.moduleName.c_str(),
            hapInfo.process.c_str(), resolvedHqfFile.c_str(), resolvedHapPath.c_str());
        fileMap.push_back(std::pair<std::string, std::string>(resolvedHqfFile, resolvedHapPath));
    }
    return true;
}

int32_t MainThread::ScheduleNotifyUnLoadRepairPatch(const std::string &bundleName,
    const sptr<IQuickFixCallback> &callback, const int32_t recordId)
{
    HITRACE_METER_NAME(HITRACE_TAG_ABILITY_MANAGER, __PRETTY_FUNCTION__);
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    wptr<MainThread> weak = this;
    auto task = [weak, bundleName, callback, recordId]() {
        auto appThread = weak.promote();
        if (appThread == nullptr || appThread->application_ == nullptr || callback == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null parameter");
            return;
        }

        bool ret = true;
        std::vector<std::pair<std::string, std::string>> hqfFilePair;
        if (appThread->GetHqfFileAndHapPath(bundleName, hqfFilePair)) {
            for (auto it = hqfFilePair.begin(); it != hqfFilePair.end(); it++) {
                TAG_LOGI(AAFwkTag::APPKIT, "hqfFile: %{private}s", it->first.c_str());
                ret = appThread->application_->NotifyUnLoadRepairPatch(it->first);
            }
        } else {
            TAG_LOGD(AAFwkTag::APPKIT, "ScheduleNotifyUnLoadRepairPatch, There's no hqfFile need to unload");
        }

        callback->OnUnloadPatchDone(ret ? NO_ERROR : ERR_INVALID_OPERATION, recordId);
    };
    if (mainHandler_ == nullptr || !mainHandler_->PostTask(task, "MainThread:NotifyUnLoadRepairPatch")) {
        TAG_LOGE(AAFwkTag::APPKIT, "ScheduleNotifyUnLoadRepairPatch, Post task failed");
        return ERR_INVALID_VALUE;
    }

    return NO_ERROR;
}

int32_t MainThread::ScheduleNotifyAppFault(const FaultData &faultData)
{
    if (mainHandler_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null mainHandler");
        return ERR_INVALID_VALUE;
    }

    if (faultData.faultType == FaultDataType::APP_FREEZE) {
        return AppExecFwk::AppfreezeInner::GetInstance()->AppfreezeHandle(faultData, false);
    }

#ifdef SUPPORT_HIPERF
    if (faultData.faultType == FaultDataType::CPU_LOAD) {
        ffrt::submit([faultData] {
            AppExecFwk::AppCapturePerf::GetInstance().CapturePerf(faultData);
        });
        return NO_ERROR;
    }
#endif

    if (faultData.faultType == FaultDataType::SLEEP_CLEAN) {
        if (AppExecFwk::SleepClean::GetInstance().HandleSleepClean(faultData, application_)) {
            SleepCleanKill();
        }
        return NO_ERROR;
    }

    wptr<MainThread> weak = this;
    auto task = [weak, faultData] {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->NotifyAppFault(faultData);
    };
    mainHandler_->PostTask(task, "MainThread:NotifyAppFault");
    return NO_ERROR;
}

void MainThread::NotifyAppFault(const FaultData &faultData)
{
    ApplicationDataManager::GetInstance().NotifyAppFault(faultData);
}

void MainThread::LoadExtensionBlockList(const std::shared_ptr<AbilityLocalRecord> &abilityRecord)
{
    if (!extensionConfigMgr_) {
        TAG_LOGE(AAFwkTag::APPKIT, "null extensionConfigMgr_");
        return;
    }
    if (!abilityRecord) {
        TAG_LOGE(AAFwkTag::APPKIT, "null abilityRecord");
        return;
    }
    if (!abilityRecord->GetAbilityInfo()) {
        TAG_LOGE(AAFwkTag::APPKIT, "null abilityInfo");
        return;
    }
    if (!application_) {
        TAG_LOGE(AAFwkTag::APPKIT, "null application_");
        return;
    }
    int32_t extensionType = static_cast<int32_t>(abilityRecord->GetAbilityInfo()->extensionAbilityType);
    TAG_LOGD(AAFwkTag::APPKIT, "type = %{public}d", extensionType);
    std::string extensionName;
    application_->GetExtensionNameByType(extensionType, extensionName);
    extensionConfigMgr_->LoadExtensionBlockList(extensionName, extensionType);
}

void MainThread::UpdateRuntimeModuleChecker(const std::unique_ptr<AbilityRuntime::Runtime> &runtime)
{
    if (!extensionConfigMgr_) {
        TAG_LOGE(AAFwkTag::APPKIT, "null extensionConfigMgr_");
        return;
    }
    extensionConfigMgr_->UpdateRuntimeModuleChecker(runtime);
}

int MainThread::GetOverlayModuleInfos(const std::string &bundleName, const std::string &moduleName,
    std::vector<OverlayModuleInfo> &overlayModuleInfos) const
{
    auto bundleMgrHelper = DelayedSingleton<BundleMgrHelper>::GetInstance();
    if (bundleMgrHelper == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null bundleMgrHelper");
        return ERR_INVALID_VALUE;
    }

    auto overlayMgrProxy = bundleMgrHelper->GetOverlayManagerProxy();
    if (overlayMgrProxy == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null overlayMgrProxy");
        return ERR_INVALID_VALUE;
    }

    auto ret = overlayMgrProxy->GetTargetOverlayModuleInfo(moduleName, overlayModuleInfos);
    if (ret != ERR_OK) {
        TAG_LOGE(AAFwkTag::APPKIT, "failed");
        return ret;
    }
    std::sort(overlayModuleInfos.begin(), overlayModuleInfos.end(),
        [](const OverlayModuleInfo& lhs, const OverlayModuleInfo& rhs) -> bool {
        return lhs.priority > rhs.priority;
    });
    TAG_LOGD(AAFwkTag::APPKIT, "the size of overlay is: %{public}zu", overlayModuleInfos.size());
    return ERR_OK;
}

std::vector<std::string> MainThread::GetAddOverlayPaths(const std::vector<OverlayModuleInfo> &overlayModuleInfos)
{
    std::vector<std::string> addPaths;
    for (auto &it : overlayModuleInfos) {
        auto iter = std::find_if(
            overlayModuleInfos_.begin(), overlayModuleInfos_.end(), [it](OverlayModuleInfo item) {
                return it.moduleName == item.moduleName;
            });
        if ((iter != overlayModuleInfos_.end()) && (it.state == AppExecFwk::OverlayState::OVERLAY_ENABLE)) {
            iter->state = it.state;
            ChangeToLocalPath(iter->bundleName, iter->hapPath, iter->hapPath);
            TAG_LOGD(AAFwkTag::APPKIT, "add path:%{public}s", iter->hapPath.c_str());
            addPaths.emplace_back(iter->hapPath);
        }
    }
    return addPaths;
}

std::vector<std::string> MainThread::GetRemoveOverlayPaths(const std::vector<OverlayModuleInfo> &overlayModuleInfos)
{
    std::vector<std::string> removePaths;
    for (auto &it : overlayModuleInfos) {
        auto iter = std::find_if(
            overlayModuleInfos_.begin(), overlayModuleInfos_.end(), [it](OverlayModuleInfo item) {
                return it.moduleName == item.moduleName;
            });
        if ((iter != overlayModuleInfos_.end()) && (it.state != AppExecFwk::OverlayState::OVERLAY_ENABLE)) {
            iter->state = it.state;
            ChangeToLocalPath(iter->bundleName, iter->hapPath, iter->hapPath);
            TAG_LOGD(AAFwkTag::APPKIT, "remove path:%{public}s", iter->hapPath.c_str());
            removePaths.emplace_back(iter->hapPath);
        }
    }

    return removePaths;
}

int32_t MainThread::ScheduleChangeAppGcState(int32_t state, uint64_t tid)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called, state is %{public}d", state);
    if (mainHandler_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null mainHandler");
        return ERR_INVALID_VALUE;
    }

    if (tid > 0) {
        ChangeAppGcState(state, tid);
        return NO_ERROR;
    }

    wptr<MainThread> weak = this;
    auto task = [weak, state, tid] {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->ChangeAppGcState(state);
    };

    if (state == START_HIGH_SENSITIVE || state == EXIT_HIGH_SENSITIVE) {
        ChangeAppGcState(state);
    } else {
        mainHandler_->PostTask(task, "MainThread:ChangeAppGcState");
    }
    return NO_ERROR;
}

int32_t MainThread::ChangeAppGcState(int32_t state, uint64_t tid)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (application_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null application_");
        return ERR_INVALID_VALUE;
    }
    auto &runtime = application_->GetRuntime();
    if (runtime == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null runtime");
        return ERR_INVALID_VALUE;
    }
    if (runtime->GetLanguage() == AbilityRuntime::Runtime::Language::CJ) {
        return NO_ERROR;
    }

    NativeEngine* nativeEngine = nullptr;

    if (runtime->GetLanguage() == AbilityRuntime::Runtime::Language::ETS) {
        auto& etsRuntime = static_cast<AbilityRuntime::ETSRuntime&>(*runtime);
        auto& jsRuntime = static_cast<AbilityRuntime::JsRuntime&>(*etsRuntime.GetJsRuntime());
        nativeEngine = &jsRuntime.GetNativeEngine();
    } else {
        nativeEngine = &(static_cast<AbilityRuntime::JsRuntime&>(*runtime)).GetNativeEngine();
    }

    if (nativeEngine == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null nativeEngine");
        return ERR_INVALID_VALUE;
    }
    if (tid > 0) {
        TAG_LOGD(AAFwkTag::APPKIT, "tid is %{private}" PRIu64, tid);
        nativeEngine->NotifyForceExpandState(tid, state);
        return NO_ERROR;
    }
    nativeEngine->NotifyForceExpandState(state);
    return NO_ERROR;
}

void MainThread::AttachAppDebug(bool isDebugFromLocal)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    SetAppDebug(AbilityRuntime::AppFreezeState::AppFreezeFlag::ATTACH_DEBUG_MODE, true);

    if (!isDebugFromLocal) {
        TAG_LOGE(AAFwkTag::APPKIT, "no local debug");
        return;
    }
    wptr<MainThread> weak = this;
    auto task = [weak] {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->OnAttachLocalDebug(true);
    };
    if (mainHandler_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null handler");
        return;
    }
    if (!mainHandler_->PostTask(task, "MainThread:AttachAppDebug")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
}

int32_t MainThread::OnAttachLocalDebug(bool isDebugFromLocal)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (application_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null application_");
        return ERR_INVALID_VALUE;
    }
    auto &runtime = application_->GetRuntime();
    if (runtime == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null runtime");
        return ERR_INVALID_VALUE;
    }
    runtime->StartLocalDebugMode(isDebugFromLocal);
    return NO_ERROR;
}

void MainThread::DetachAppDebug()
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    SetAppDebug(AbilityRuntime::AppFreezeState::AppFreezeFlag::ATTACH_DEBUG_MODE, false);
}

bool MainThread::NotifyDeviceDisConnect()
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    if (appMgr_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null appMgr");
        return false;
    }
    bool isLastProcess = appMgr_->IsFinalAppProcess();
    ScheduleTerminateApplication(isLastProcess);
    return true;
}

void MainThread::AssertFaultPauseMainThreadDetection()
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    SetAppDebug(AbilityRuntime::AppFreezeState::AppFreezeFlag::ASSERT_DEBUG_MODE, true);
    if (appMgr_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null appMgr");
        return;
    }
    appMgr_->SetAppAssertionPauseState(true);
}

void MainThread::AssertFaultResumeMainThreadDetection()
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    SetAppDebug(AbilityRuntime::AppFreezeState::AppFreezeFlag::ASSERT_DEBUG_MODE, false);
    if (appMgr_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null appMgr");
        return;
    }
    appMgr_->SetAppAssertionPauseState(false);
}

void MainThread::HandleInitAssertFaultTask(bool isDebugModule, bool isDebugApp)
{
    if (!isDeveloperMode_) {
        TAG_LOGE(AAFwkTag::APPKIT, "developer Mode false");
        return;
    }
    if (!system::GetBoolParameter(PRODUCT_ASSERT_FAULT_DIALOG_ENABLED, false)) {
        TAG_LOGD(AAFwkTag::APPKIT, "Unsupport assert fault dialog");
        return;
    }
    if (!isDebugApp) {
        TAG_LOGE(AAFwkTag::APPKIT, "Non-debug version application");
        return;
    }
    auto assertThread = DelayedSingleton<AbilityRuntime::AssertFaultTaskThread>::GetInstance();
    if (assertThread == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null assertThread");
        return;
    }
    assertThread->InitAssertFaultTask(this, isDebugModule);
    assertThread_ = assertThread;
}

void MainThread::SetAppDebug(uint32_t modeFlag, bool isDebug)
{
    TAG_LOGD(AAFwkTag::APPKIT, "called");
    auto state = DelayedSingleton<AbilityRuntime::AppFreezeState>::GetInstance();
    if (state == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null state");
        return;
    }

    if (!isDebug) {
        TAG_LOGD(AAFwkTag::APPKIT, "Call Cancel modeFlag is %{public}u", modeFlag);
        state->CancelAppFreezeState(modeFlag);
        return;
    }

    TAG_LOGD(AAFwkTag::APPKIT, "Call Set modeFlag is %{public}u", modeFlag);
    state->SetAppFreezeState(modeFlag);
}

void MainThread::HandleCancelAssertFaultTask()
{
    auto assertThread = assertThread_.lock();
    if (assertThread == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null assertThread");
        return;
    }
    assertThread->Stop();
}

int32_t MainThread::ScheduleDumpIpcStart(std::string& result)
{
    TAG_LOGD(AAFwkTag::APPKIT, "MainThread::ScheduleDumpIpcStart::pid:%{public}d", getprocpid());
    DumpIpcHelper::DumpIpcStart(result);
    return ERR_OK;
}

int32_t MainThread::ScheduleDumpIpcStop(std::string& result)
{
    TAG_LOGD(AAFwkTag::APPKIT, "pid:%{public}d", getprocpid());
    DumpIpcHelper::DumpIpcStop(result);
    return ERR_OK;
}

int32_t MainThread::ScheduleDumpIpcStat(std::string& result)
{
    TAG_LOGD(AAFwkTag::APPKIT, "pid:%{public}d", getprocpid());
    DumpIpcHelper::DumpIpcStat(result);
    return ERR_OK;
}

int32_t MainThread::ScheduleDumpFfrt(std::string& result)
{
    TAG_LOGD(AAFwkTag::APPKIT, "pid:%{public}d", getprocpid());
    return DumpFfrtHelper::DumpFfrt(result);
}

int32_t MainThread::ScheduleDumpArkWeb(const std::string &customArgs, std::string &result)
{
    return DumpArkWebHelper::DumpArkWeb(customArgs, result);
}

/**
 *
 * @brief Set watchdog background status of applicaton.
 *
 */
void MainThread::SetWatchdogBackgroundStatus(bool status)
{
    auto tmpWatchdog = watchdog_;
    if (tmpWatchdog == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null Watch dog");
        return;
    }
    tmpWatchdog->SetBackgroundStatus(status);
    tmpWatchdog = nullptr;
}

/**
 *
 * @brief Notify application to prepare for process caching.
 *
 */
void MainThread::ScheduleCacheProcess()
{
    TAG_LOGD(AAFwkTag::APPKIT, "ScheduleCacheProcess");
    wptr<MainThread> weak = this;
    auto task = [weak]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->HandleCacheProcess();
    };
    if (mainHandler_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null handler");
        return;
    }
    if (!mainHandler_->PostTask(task, "MainThread:ScheduleCacheProcess")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
}

void MainThread::ParseAppConfigurationParams(const std::string configuration, Configuration &appConfig)
{
    TAG_LOGD(AAFwkTag::APPKIT, "start");
    appConfig.AddItem(AAFwk::GlobalConfigurationKey::APP_FONT_SIZE_SCALE, DEFAULT_APP_FONT_SIZE_SCALE);
    if (configuration.empty()) {
        TAG_LOGD(AAFwkTag::ABILITYMGR, "empty config");
        return;
    }
    TAG_LOGI(AAFwkTag::APPKIT, "ParseAppConfigurationParams config:%{public}s", appConfig.GetName().c_str());
    nlohmann::json configurationJson = nlohmann::json::parse(configuration, nullptr, false);
    if (configurationJson.is_discarded()) {
        TAG_LOGE(AAFwkTag::ABILITYMGR, "discarded error");
        return;
    }
    if (!configurationJson.contains(JSON_KEY_APP_CONFIGURATION)) {
        TAG_LOGE(AAFwkTag::ABILITYMGR, "app config not exist");
        return;
    }
    nlohmann::json jsonObject;
    auto& configValue = configurationJson.at(JSON_KEY_APP_CONFIGURATION);
    if (!configValue.is_object()) {
        TAG_LOGE(AAFwkTag::ABILITYMGR, "config not object");
        return;
    }
    jsonObject = configValue.get<nlohmann::json>();
    if (jsonObject.empty()) {
        TAG_LOGE(AAFwkTag::ABILITYMGR, "null app config");
        return;
    }
    if (jsonObject.contains(JSON_KEY_APP_FONT_SIZE_SCALE)
        && jsonObject[JSON_KEY_APP_FONT_SIZE_SCALE].is_string()) {
        std::string configFontSizeScal = jsonObject.at(JSON_KEY_APP_FONT_SIZE_SCALE).get<std::string>();
        appConfig.AddItem(AAFwk::GlobalConfigurationKey::APP_FONT_SIZE_SCALE,
            jsonObject.at(JSON_KEY_APP_FONT_SIZE_SCALE).get<std::string>());
    }
    if (jsonObject.contains(JSON_KEY_APP_FONT_MAX_SCALE)
        && jsonObject[JSON_KEY_APP_FONT_MAX_SCALE].is_string()) {
        std::string appFontMaxScale = jsonObject.at(JSON_KEY_APP_FONT_MAX_SCALE).get<std::string>();
        const std::regex INTEGER_REGEX("^[-+]?([0-9]+)([.]([0-9]+))?$");
        if (std::regex_match(appFontMaxScale, INTEGER_REGEX)) {
            appConfig.AddItem(AAFwk::GlobalConfigurationKey::APP_FONT_MAX_SCALE, appFontMaxScale);
        }
    }
    TAG_LOGD(AAFwkTag::APPKIT, "configuration_: %{public}s", appConfig.GetName().c_str());
}

/**
 *
 * @brief Notify application to prepare for process caching.
 *
 */
void MainThread::HandleCacheProcess()
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    TAG_LOGD(AAFwkTag::APPKIT, "start");

    // force gc
    if (application_ != nullptr) {
        auto &runtime = application_->GetRuntime();
        if (runtime == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null runtime");
            return;
        }
        runtime->ForceFullGC();
    }
}

void MainThread::SetRuntimeLang(ApplicationInfo &appInfo, AbilityRuntime::Runtime::Options &options)
{
    if (appInfo.arkTSMode == AbilityRuntime::CODE_LANGUAGE_ARKTS_1_2 ||
        appInfo.arkTSMode == AbilityRuntime::CODE_LANGUAGE_ARKTS_HYBRID) {
        options.lang = AbilityRuntime::Runtime::Language::ETS;
    } else {
        options.lang = AbilityRuntime::Runtime::Language::JS;
    }
}

bool MainThread::IsEtsAPP(const ApplicationInfo &appInfo)
{
    return appInfo.arkTSMode == AbilityRuntime::CODE_LANGUAGE_ARKTS_1_2 ||
        appInfo.arkTSMode == AbilityRuntime::CODE_LANGUAGE_ARKTS_HYBRID;
}

void MainThread::HandleConfigByPlugin(Configuration &config, BundleInfo &bundleInfo)
{
    if (PC_LIBRARY_PATH == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "PC_LIBRARY_PATH == nullptr");
        return;
    }

    void* handle = dlopen(PC_LIBRARY_PATH, RTLD_LAZY);
    if (handle == nullptr) {
        TAG_LOGW(AAFwkTag::APPKIT, "reason %{public}sn", dlerror());
        return;
    }

    auto entry = reinterpret_cast<void* (*)(Configuration &, BundleInfo &)>(dlsym(handle, PC_FUNC_INFO));
    if (entry == nullptr) {
        dlclose(handle);
        TAG_LOGE(AAFwkTag::APPKIT, "get func fail");
        return;
    }

    entry(config, bundleInfo);
}

void MainThread::SetJsIdleCallback(const std::weak_ptr<OHOSApplication> &wpApplication,
    const std::unique_ptr<AbilityRuntime::Runtime> &runtime)
{
    auto &jsEngine = (static_cast<AbilityRuntime::JsRuntime &>(*runtime)).GetNativeEngine();
    IdleTimeCallback callback = [wpApplication](int32_t idleTime) {
        auto app = wpApplication.lock();
        if (app == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null app");
            return;
        }
        auto &runtime = app->GetRuntime();
        if (runtime == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null runtime");
            return;
        }
        if (runtime->GetLanguage() == AbilityRuntime::Runtime::Language::ETS) {
            auto &etsRuntime = static_cast<AbilityRuntime::ETSRuntime &>(*runtime);
            auto &jsRuntime =  etsRuntime.GetJsRuntime();
            if (jsRuntime != nullptr) {
                auto &nativeEngine =
                    (static_cast<AbilityRuntime::JsRuntime &>(*jsRuntime)).GetNativeEngine();
                nativeEngine.NotifyIdleTime(idleTime);
            }
        } else {
            auto &nativeEngine = (static_cast<AbilityRuntime::JsRuntime &>(*runtime)).GetNativeEngine();
            nativeEngine.NotifyIdleTime(idleTime);
        }
    };
    idleTime_ = std::make_shared<IdleTime>(mainHandler_, callback);

    IdleNotifyStatusCallback cb = idleTime_->GetIdleNotifyFunc();
    jsEngine.NotifyIdleStatusControl(cb);

    auto helper = std::make_shared<DumpRuntimeHelper>(application_);
    helper->SetAppFreezeFilterCallback();
}

void MainThread::PreloadAppStartup(const BundleInfo &bundleInfo, const AppLaunchData &appLaunchData) const
{
    if (application_ == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null application_");
        return;
    }
    application_->PreloadAppStartup(bundleInfo, appLaunchData.GetPreloadModuleName(),
        appLaunchData.GetStartupTaskData());
}

void MainThread::LoadExtStartupTasks()
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    std::map<std::string, std::shared_ptr<AbilityRuntime::StartupTask>> nativeStartupTask;

    auto loadExtStartupTask = std::make_shared<LoadExtStartupTask>();
    std::shared_ptr<AbilityRuntime::StartupTask> extStartupTask;
    AbilityRuntime::ExtNativeStartupManager::BuildExtStartupTask(loadExtStartupTask, extStartupTask);
    if (extStartupTask != nullptr) {
        nativeStartupTask.emplace(extStartupTask->GetName(), extStartupTask);
    } else {
        TAG_LOGE(AAFwkTag::APPKIT, "null extStartupTask");
    }
    AbilityRuntime::ExtNativeStartupManager::RunNativeStartupTask(nativeStartupTask);
}

void MainThread::RunNativeStartupTask(const BundleInfo &bundleInfo, const AppLaunchData &appLaunchData)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    std::map<std::string, std::shared_ptr<AbilityRuntime::StartupTask>> nativeStartupTask;
    wptr<MainThread> weak = this;
    auto task = [weak, bundleInfo, appLaunchData](
        std::unique_ptr<AbilityRuntime::StartupTaskResultCallback> callback)->int32_t {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            AbilityRuntime::OnCompletedCallback::OnCallback(std::move(callback),
                AbilityRuntime::ERR_STARTUP_INTERNAL_ERROR);
            return AbilityRuntime::ERR_STARTUP_INTERNAL_ERROR;
        }
        appThread->PreloadAppStartup(bundleInfo, appLaunchData);
        AbilityRuntime::OnCompletedCallback::OnCallback(std::move(callback), ERR_OK);
        return ERR_OK;
    };
    auto preloadAppStartup = std::make_shared<AbilityRuntime::NativeStartupTask>(PRELOAD_APP_STARTUP, task);
    nativeStartupTask.emplace(preloadAppStartup->GetName(), preloadAppStartup);
    AbilityRuntime::ExtNativeStartupManager::RunNativeStartupTask(nativeStartupTask);
}

bool MainThread::GetTestRunnerTypeAndPath(const std::string bundleName, const std::string moduleName,
    AppExecFwk::ModuleTestRunner &tsTestRunner)
{
    auto bundleMgrHelper = DelayedSingleton<BundleMgrHelper>::GetInstance();
    if (bundleMgrHelper == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null bundleMgrHelper");
        return false;
    }
    ErrCode ret = bundleMgrHelper->GetTestRunnerTypeAndPath(bundleName, moduleName,
        tsTestRunner);
    if (ret != ERR_OK) {
        TAG_LOGE(AAFwkTag::APPKIT, "get testrunner failed: %{public}d", ret);
        return false;
    }
    return true;
}

void MainThread::RegisterHybridException(const std::unique_ptr<AbilityRuntime::Runtime> &runtime,
    const ApplicationInfo &appInfo, const std::string &hapPath, const UncatchableTaskInfo &uncatchableTaskInfo)
{
    if (appInfo.arkTSMode == AbilityRuntime::CODE_LANGUAGE_ARKTS_HYBRID) {
        auto &jsRuntime = (static_cast<AbilityRuntime::ETSRuntime&>(*runtime)).GetJsRuntime();
        if (jsRuntime != nullptr) {
            JsEnv::UncaughtExceptionInfo uncaughtExceptionInfo;
            uncaughtExceptionInfo.hapPath = hapPath;

            InitUncatchableTask(uncaughtExceptionInfo.uncaughtTask, uncatchableTaskInfo);
            (static_cast<AbilityRuntime::JsRuntime&>(*jsRuntime)).RegisterUncaughtExceptionHandler(
                uncaughtExceptionInfo, true);
            JsEnv::UncatchableTask uncatchableTask;
            InitUncatchableTask(uncatchableTask, uncatchableTaskInfo, true);
            (static_cast<AbilityRuntime::JsRuntime&>(*jsRuntime)).RegisterUncatchableExceptionHandler(
                uncatchableTask, true);
        }
    }
}

void MainThread::OnLoadAbilityFinished(uint64_t callbackId, int32_t pid)
{
    LoadAbilityCallbackManager::GetInstance().OnLoadAbilityFinished(callbackId, pid);
}

void MainThread::ScheduleUpdateWorkProcessInfo(std::shared_ptr<AppUpdateInfo> updateInfo)
{
    wptr<MainThread> weak = this;
    auto task = [weak, updateInfo]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return;
        }
        appThread->UpdateWorkProcessInfo(updateInfo);
    };
    if (!mainHandler_->PostTask(task, "MainThread:ScheduleUpdateWorkProcessInfo")) {
        TAG_LOGE(AAFwkTag::APPKIT, "PostTask task failed");
    }
}

bool MainThread::IsPluginNamespaceInherited()
{
    isPluginNamespaceInherited_ = system::GetBoolParameter(INHERIT_PLUGIN_NAMESPACE, false);
    TAG_LOGD(AAFwkTag::APPKIT, "inherit_plugin_namespace: %{public}d", isPluginNamespaceInherited_);
    return isPluginNamespaceInherited_;
}

std::string MainThread::ParsePluginDefaultNamespaceLdDictionary()
{
    pluginDefaultNamespaceLdDictionary_ = system::GetParameter(PLUGIN_DEFAULT_NAMESPACE_LDDICTIONARY, "");
    TAG_LOGD(AAFwkTag::APPKIT, "plugin_default_namespace_lddictionary: %{public}s",
        pluginDefaultNamespaceLdDictionary_.c_str());
    return pluginDefaultNamespaceLdDictionary_;
}

void MainThread::SleepCleanKill()
{
    int64_t beginTime = AbilityRuntime::TimeUtil::SystemTimeMillisecond();
    auto task = [ weak = wptr<MainThread>(this), beginTime]() {
        auto appThread = weak.promote();
        if (appThread == nullptr) {
            TAG_LOGE(AAFwkTag::APPKIT, "null appThread");
            return ;
        }
        if (AbilityRuntime::TimeUtil::SystemTimeMillisecond() - beginTime < AppExecFwk::SLEEP_CLEAN_TIMEOUT &&
            appThread->applicationImpl_->GetState() != ApplicationImpl::APP_STATE_FOREGROUND) {
            AbilityManagerClient::GetInstance()->RecordAppExitReason({ REASON_RESOURCE_CONTROL,
                "Js_Heap_Sleep_Clean_Kill" });
            _exit(0);
        }
    };
    mainHandler_->PostTask(task, "Sleep Clean:Over HeapSize", AppExecFwk::SLEEP_CLEAN_DELAY_TIME);
}

bool MainThread::CheckAndUpdateRuntime(const std::shared_ptr<AbilityLocalRecord> &abilityRecord)
{
    HITRACE_METER_NAME(HITRACE_TAG_APP, __PRETTY_FUNCTION__);
    if (abilityRecord == nullptr || applicationInfo_ == nullptr || abilityRecord->GetAbilityInfo() == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null abilityRecord or applicationInfo or abilityInfo");
        return false;
    }
    if (abilityRecord->GetAbilityInfo()->arkTSMode != AbilityRuntime::CODE_LANGUAGE_ARKTS_1_2 ||
        applicationInfo_->arkTSMode != AbilityRuntime::CODE_LANGUAGE_ARKTS_1_0) {
        return true;
    }
    auto &runtime = application_->GetRuntime();
    if (runtime == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null runtime");
        return false;
    }
    if (runtime->GetLanguage() != AbilityRuntime::Runtime::Language::JS) {
        return true;
    }
    HITRACE_METER_NAME(HITRACE_TAG_APP, "Update Runtime");
    BundleInfo bundleInfo;
    HspList hspList;
    if (!GetBundleAndHspListForUpdateRuntime(bundleInfo,
        runtimeUpdateParam_.uncatchableTaskInfo.bundleName, hspList)) {
        TAG_LOGE(AAFwkTag::APPKIT, "Get Bundle or hspList failed");
        return false;
    }
    AppLibPathMap etsAppLibPaths {};
    std::map<std::string, std::string> abcPathsToBundleModuleNameMap {};
    GetEtsNativeLibPath(bundleInfo, hspList, etsAppLibPaths, abcPathsToBundleModuleNameMap);
    AbilityRuntime::ETSRuntime::SetAppLibPath(
        etsAppLibPaths, abcPathsToBundleModuleNameMap, applicationInfo_->isSystemApp);
    runtimeUpdateParam_.option.preload = false;
    if (!application_->UpdateETSRuntime(runtimeUpdateParam_.option)) {
        TAG_LOGE(AAFwkTag::APPKIT, "UpdateETSRuntime failed");
        return false;
    }
    auto &etsRuntime = application_->GetRuntime();
    if (etsRuntime == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null etsRuntime");
        return false;
    }
    auto expectionInfo = CreateEtsExceptionInfo(runtimeUpdateParam_.uncatchableTaskInfo.bundleName,
        runtimeUpdateParam_.uncatchableTaskInfo.versionCode, runtimeUpdateParam_.hapPath,
        runtimeUpdateParam_.uncatchableTaskInfo.appRunningId, runtimeUpdateParam_.uncatchableTaskInfo.pid,
        runtimeUpdateParam_.uncatchableTaskInfo.processName);
    (static_cast<AbilityRuntime::ETSRuntime&>(*etsRuntime)).RegisterUncaughtExceptionHandler(expectionInfo);
    return true;
}

void MainThread::TransferEnvToEventHandler(std::unique_ptr<Runtime> &runtime)
{
    if (mainHandler_ == nullptr || runtime == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "null mainHandler or runtime");
        return;
    }
    auto eventRunner = mainHandler_->GetEventRunner();
    auto env = (static_cast<AbilityRuntime::JsRuntime&>(*runtime)).GetNapiEnv();
    if (eventRunner == nullptr || env == nullptr) {
        TAG_LOGE(AAFwkTag::APPKIT, "transfer env to eventRunner error");
        return;
    }
    eventRunner->EventSetEnvToHandler(env);
}
}  // namespace AppExecFwk
}  // namespace OHOS
