/* Copyright (c) 2026 OpenHarmony QEMU contributors. SPDX-License-Identifier: Apache-2.0 */
#include "location_vendor_lib.h"
#include "qemu_gnss_input.h"
#include <cerrno>
#include <mutex>

namespace OHOS::QemuGnss {
namespace Vendor = OHOS::HDI::Location;
// Config is explicit for native transport tests. The only exported device below pins the product path/UID.
class Provider {
public:
    explicit Provider(InputConfig config) : input_(std::move(config)) {}
    ~Provider() { Disable(); }
    int Enable(Vendor::GnssCallbackStruct* callbacks)
    {
        if (!callbacks || callbacks->size != sizeof(*callbacks) ||
            callbacks->gnssCallback.size != sizeof(callbacks->gnssCallback) ||
            !callbacks->gnssCallback.locationUpdate) return -EINVAL;
        std::lock_guard<std::mutex> lock(lifecycle_);
        if (input_.IsRunning()) return -EBUSY; // Never join an old callback while HDI Enable holds its own mutex.
        auto callback = callbacks->gnssCallback.locationUpdate; // Copy the function pointer; never retain caller storage.
        if (!input_.Start()) return -EIO;
        if (!input_.Register(this, [callback](const Fix& fix) {
            Vendor::GnssLocation location{};
            location.size = sizeof(location);
            location.fieldValidity = 1 | 2 | 32 | 512 | 1024 | fix.optionalFields;
            location.latitude = fix.latitude; location.longitude = fix.longitude;
            location.altitude = (fix.optionalFields & 4) ? fix.altitude : 0;
            location.speed = (fix.optionalFields & 8) ? fix.speed : 0;
            location.bearing = (fix.optionalFields & 16) ? fix.bearing : 0;
            location.horizontalAccuracy = fix.horizontalAccuracy; location.verticalAccuracy = (fix.optionalFields & 64) ? fix.verticalAccuracy : 0;
            location.timeForFix = fix.utcMs; location.timeSinceBoot = fix.bootNs;
            callback(&location); // Stack value is borrowed for the synchronous vendor callback only.
        })) { input_.Stop(); return -EIO; }
        return 0;
    }
    int Start(uint32_t category)
    { return category != 1 ? -ENOTSUP : (input_.Enable() ? 0 : -EIO); }
    int Stop(uint32_t category)
    { return category != 1 ? -ENOTSUP : (input_.Disable() ? 0 : -EIO); }
    int Disable()
    {
        // Stop is independently serialized, joins without holding this class lock, and tolerates worker reentry.
        input_.Stop();
        return 0;
    }
    int Configure(Vendor::GnssConfigParameter* config)
    {
        if (!config || config->size != sizeof(*config)) return -EINVAL;
        if (config->startCategory != 1) return -ENOTSUP;
        const auto& basic = config->u.gnssBasicConfig;
        if (basic.size != sizeof(basic) || basic.minInterval > 3600000) return -EINVAL;
        if (basic.gnssMode != 1) return -ENOTSUP;
        return input_.SetBatch(static_cast<int64_t>(basic.minInterval) * 1000000, 0) ? 0 : -EIO;
    }
private:
    std::mutex lifecycle_;
    GnssInput input_;
};
namespace {
Provider provider({"/dev/unix/socket/qemu_gnss/input", 0});
int Enable(Vendor::GnssCallbackStruct* callbacks) { return provider.Enable(callbacks); }
int Disable() { return provider.Disable(); }
int Start(uint32_t category) { return provider.Start(category); }
int Stop(uint32_t category) { return provider.Stop(category); }
int Configure(Vendor::GnssConfigParameter* config) { return provider.Configure(config); }
int Reference(int, Vendor::GnssReferenceInfo*) { return -ENOTSUP; }
void DeleteAuxiliary(uint16_t) {} // No assistance cache is maintained.
int Ephemeris(char*, int) { return -ENOTSUP; }
const void* Module(int) { return nullptr; }
const Vendor::GnssVendorInterface interface = {sizeof(Vendor::GnssVendorInterface), Enable, Disable, Start, Stop,
    Reference, Configure, DeleteAuxiliary, Ephemeris, nullptr, nullptr, Module};
const Vendor::GnssVendorInterface* Get() { return &interface; }
} // namespace
} // namespace OHOS::QemuGnss
extern "C" {
__attribute__((visibility("default"))) OHOS::HDI::Location::GnssVendorDevice GnssVendorInterface = {
    sizeof(OHOS::HDI::Location::GnssVendorDevice), OHOS::QemuGnss::Get};
}
