/* Copyright (c) 2026 OpenHarmony contributors.
 * Licensed under the Apache License, Version 2.0; see
 * http://www.apache.org/licenses/LICENSE-2.0
 * Distributed on an AS IS BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
 */
#ifndef OHOS_MEDIA_QEMU_MTP_FUNCTIONFS_WATCHER_H
#define OHOS_MEDIA_QEMU_MTP_FUNCTIONFS_WATCHER_H
#include <atomic>
#include <chrono>
#include <mutex>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <thread>
#include "media_mtp_service_manager.h"
#include "parameters.h"

namespace OHOS::Media {
/* Standard FunctionFS readiness is a real kernel filesystem state. The QEMU
 * product uses the existing MediaMtpServiceManager and EDM enable policy; no
 * common event, USB function getter, user consent or MTP response is forged.
 * The normal DataShare extension owns and joins this worker in Init/Stop.
 */
class QemuMtpMountWatcher final {
public:
    ~QemuMtpMountWatcher() { Stop(); }
    void Start()
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (thread_.joinable()) return;
        stopping_.store(false); thread_ = std::thread([this] { Run(); });
    }
    void Stop()
    {
        std::lock_guard<std::mutex> lock(mutex_); stopping_.store(true);
        if (thread_.joinable()) thread_.join();
    }
    static QemuMtpMountWatcher &Instance() { static QemuMtpMountWatcher watcher; return watcher; }
private:
    bool Ready()
    {
        struct stat path{}; struct statfs fs{};
        return lstat("/dev/usb-ffs/mtp", &path) == 0 && S_ISDIR(path.st_mode) && path.st_uid == 0 &&
            statfs("/dev/usb-ffs/mtp", &fs) == 0 && fs.f_type == 0x0a647361 &&
            !OHOS::system::GetBoolParameter("persist.edm.mtp_server_disable", false);
    }
    void Run()
    {
        bool active = false;
        while (!stopping_.load()) {
            const bool ready = Ready();
            if (ready && !active) {
                MediaMtpServiceManager::StartMtpService(MtpMode::MTP_MODE); active = true;
            } else if (!ready && active) {
                MediaMtpServiceManager::StopMtpService(); active = false;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(250));
        }
        if (active) MediaMtpServiceManager::StopMtpService();
    }
    std::atomic<bool> stopping_{true};
    std::mutex mutex_;
    std::thread thread_;
};
} // namespace OHOS::Media
#endif
