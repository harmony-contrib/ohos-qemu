/* SPDX-License-Identifier: Apache-2.0 */
#ifndef QEMU_WALLPAPER_RENDERER_H
#define QEMU_WALLPAPER_RENDERER_H
#include <cstdint>
#include <memory>
#include "event_handler.h"
namespace OHOS::WallpaperMgrService {
// QEMU's separate renderer HAP. No caller permissions, file state or UI policy
// are changed here. A successful connection means a real extension callback.
class QemuWallpaperRenderer {
public:
    virtual ~QemuWallpaperRenderer() = default;
    static std::shared_ptr<QemuWallpaperRenderer> Create(const std::shared_ptr<AppExecFwk::EventHandler> &handler);
    virtual void Request(int32_t foregroundUser = -1) = 0;
    virtual void Stop() = 0;
};
}
#endif
