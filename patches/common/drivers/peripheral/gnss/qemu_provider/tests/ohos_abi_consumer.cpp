/*
 * Copyright (c) 2026 OpenHarmony QEMU contributors.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 * http://www.apache.org/licenses/LICENSE-2.0
 */

// This consumer uses the product headers and DSOs. It does not implement a
// GNSS service, substitute RefBase/IPC, or supply a location without input.
#include "gnss_interface_impl.h"
#include "location_vendor_interface.h"
#include "location_vendor_lib.h"

#include <atomic>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <time.h>
#include <unistd.h>

namespace Vendor = OHOS::HDI::Location;
namespace Public = OHOS::HDI::Location::Gnss::V2_0;

namespace {
std::atomic<unsigned> g_callbacks {0};
std::atomic<unsigned> g_invalid {0};
std::atomic<bool> g_cleanupReturned {false};
double g_expectedLatitude = 0;
double g_expectedLongitude = 0;

void SleepMs(unsigned milliseconds)
{
    timespec delay {milliseconds / 1000, static_cast<long>(milliseconds % 1000) * 1000000};
    while (nanosleep(&delay, &delay) < 0 && errno == EINTR) {}
}

void OnLocation(Vendor::GnssLocation* location)
{
    constexpr unsigned required = 1 | 2 | 32 | 512 | 1024;
    timespec now {};
    clock_gettime(CLOCK_BOOTTIME, &now);
    const uint64_t boot = static_cast<uint64_t>(now.tv_sec) * 1000000000 + now.tv_nsec;
    if (location == nullptr || location->size != sizeof(*location) ||
        (location->fieldValidity & required) != required ||
        !std::isfinite(location->latitude) || !std::isfinite(location->longitude) ||
        std::abs(location->latitude - g_expectedLatitude) > 1e-10 ||
        std::abs(location->longitude - g_expectedLongitude) > 1e-10 ||
        !std::isfinite(location->horizontalAccuracy) || location->horizontalAccuracy < 0 ||
        location->timeSinceBoot == 0 || location->timeSinceBoot > boot ||
        boot - location->timeSinceBoot > 30000000000ULL) {
        ++g_invalid;
        return;
    }
    const unsigned ordinal = ++g_callbacks;
    std::printf("LOCATION ordinal=%u latitude=%.12f longitude=%.12f utc_ms=%lld boot_ns=%llu validity=%u\n",
        ordinal, location->latitude, location->longitude,
        static_cast<long long>(location->timeForFix),
        static_cast<unsigned long long>(location->timeSinceBoot), location->fieldValidity);
    // The first genuine provider callback reenters the actual loader cleanup.
    // Only the loader's external reaper may join/unload its provider worker.
    if (ordinal == 1) {
        Vendor::LocationVendorInterface::DestroyInstance();
        g_cleanupReturned.store(true);
        std::puts("CALLBACK_CLEANUP_RETURNED");
    }
}

bool WaitCallbacks(unsigned count)
{
    for (unsigned i = 0; i < 500; ++i) {
        if (g_invalid.load() != 0) {
            return false;
        }
        if (g_callbacks.load() == count && (count != 1 || g_cleanupReturned.load())) {
            return true;
        }
        SleepMs(10);
    }
    return false;
}

bool ProviderMapped()
{
    // Inspection must not add a DSO reference that would prevent dlclose.
    FILE* stream = std::fopen("/proc/self/maps", "r");
    if (stream == nullptr) {
        return true;
    }
    bool mapped = false;
    char line[2048];
    while (std::fgets(line, sizeof(line), stream) != nullptr) {
        if (std::strstr(line, "vendorGnssAdapter.so") != nullptr) {
            mapped = true;
        }
    }
    std::fclose(stream);
    return mapped;
}

bool WaitUnmapped()
{
    for (unsigned i = 0; i < 500; ++i) {
        if (!ProviderMapped()) {
            return true;
        }
        SleepMs(10);
    }
    return false;
}

const Vendor::GnssVendorInterface* LoadTable()
{
    auto* loader = Vendor::LocationVendorInterface::GetInstance();
    return loader == nullptr ? nullptr : loader->GetGnssVendorInterface();
}

bool TableIsComplete(const Vendor::GnssVendorInterface* table)
{
    return table != nullptr && table->size == sizeof(*table) &&
        table->enableGnss != nullptr && table->disableGnss != nullptr &&
        table->startGnss != nullptr && table->stopGnss != nullptr &&
        table->injectsGnssReferenceInfo != nullptr && table->setGnssConfigPara != nullptr &&
        table->removeAuxiliaryData != nullptr && table->injectExtendedEphemeris != nullptr &&
        table->getCachedLocationsSize == nullptr && table->flushCachedGnssLocations == nullptr &&
        table->getGnssModuleIface != nullptr;
}

const Vendor::GnssVendorInterface* WaitTable()
{
    for (unsigned i = 0; i < 500; ++i) {
        const auto* table = LoadTable();
        if (TableIsComplete(table)) {
            return table;
        }
        SleepMs(10);
    }
    return nullptr;
}

bool Configure(Public::IGnssInterface& service)
{
    Public::GnssConfigPara config {};
    config.gnssBasic.gnssMode = Public::GNSS_WORKING_MODE_STANDALONE;
    config.gnssBasic.minInterval = 0;
    // This is a real generated public virtual call into the original HDI DSO,
    // which maps the public POD to the real vendor ABI and proxy function.
    const int result = service.SetGnssConfigPara(config);
    std::printf("PUBLIC_CONFIG result=%d\n", result);
    return result == 0;
}

bool Enable(const Vendor::GnssVendorInterface* table)
{
    Vendor::GnssCallbackStruct callbacks {};
    callbacks.size = sizeof(callbacks);
    callbacks.gnssCallback.size = sizeof(callbacks.gnssCallback);
    callbacks.gnssCallback.locationUpdate = OnLocation;
    // The provider/loader must own the copied callback after this stack exits.
    const int result = table->enableGnss(&callbacks);
    std::printf("VENDOR_ENABLE result=%d\n", result);
    return result == 0;
}

int Fail(const char* stage)
{
    std::fprintf(stderr, "FAIL stage=%s callbacks=%u invalid=%u errno=%d\n", stage,
        g_callbacks.load(), g_invalid.load(), errno);
    Vendor::LocationVendorInterface::DestroyInstance();
    return 1;
}
} // namespace

int main(int argc, char** argv)
{
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 3) {
        std::fprintf(stderr, "usage: %s expected_latitude expected_longitude\n", argv[0]);
        return 2;
    }
    g_expectedLatitude = std::strtod(argv[1], nullptr);
    g_expectedLongitude = std::strtod(argv[2], nullptr);
    if (!std::isfinite(g_expectedLatitude) || !std::isfinite(g_expectedLongitude) ||
        std::abs(g_expectedLatitude) > 90 || std::abs(g_expectedLongitude) > 180) {
        return 2;
    }
    std::puts("OHOS_CONSUMER_MAIN");
    std::printf("ABI vendor_device=%zu vendor_table=%zu location=%zu public_config=%zu\n",
        sizeof(Vendor::GnssVendorDevice), sizeof(Vendor::GnssVendorInterface),
        sizeof(Vendor::GnssLocation), sizeof(Public::GnssConfigPara));

    OHOS::sptr<Public::IGnssInterface> service = new Public::GnssInterfaceImpl();
    uint32_t major = 0;
    uint32_t minor = 0;
    if (service->GetVersion(major, minor) != 0 || major != 2 || minor != 0) {
        return Fail("public-version");
    }
    const auto* table = LoadTable();
    if (!TableIsComplete(table)) {
        return Fail("actual-vendor-table");
    }
    // Validate the real exported data object as data, rather than inventing a
    // function ABI for dlsym. This extra reference is closed before lifecycle.
    void* provider = dlopen("vendorGnssAdapter.so", RTLD_NOW | RTLD_LOCAL);
    if (provider == nullptr) {
        return Fail("provider-dlopen");
    }
    auto* device = static_cast<Vendor::GnssVendorDevice*>(dlsym(provider, "GnssVendorInterface"));
    const bool deviceValid = device != nullptr && device->size == sizeof(*device) &&
        device->getGnssInterface != nullptr && TableIsComplete(device->getGnssInterface());
    dlclose(provider);
    if (!deviceValid || !Enable(table)) {
        return Fail("vendor-enable");
    }
    if (!Configure(*service) || service->StartGnss(Public::GNSS_START_TYPE_NORMAL) != 0) {
        return Fail("public-config-start");
    }
    SleepMs(250);
    if (g_callbacks.load() != 0) {
        return Fail("no-input");
    }
    std::puts("READY_INPUT generation=1");
    if (!WaitCallbacks(1) || !WaitUnmapped()) {
        return Fail("callback-cleanup-unload");
    }
    std::puts("PROVIDER_UNMAPPED generation=1");

    table = WaitTable();
    if (!TableIsComplete(table) || !Enable(table) || !Configure(*service) ||
        service->StartGnss(Public::GNSS_START_TYPE_NORMAL) != 0) {
        return Fail("reload");
    }
    SleepMs(250);
    if (g_callbacks.load() != 1) {
        return Fail("reload-no-input");
    }
    std::puts("READY_INPUT generation=2");
    if (!WaitCallbacks(2) || service->StopGnss(Public::GNSS_START_TYPE_NORMAL) != 0) {
        return Fail("reload-callback-stop");
    }
    std::puts("STOPPED");
    SleepMs(250);
    if (g_callbacks.load() != 2 || g_invalid.load() != 0 || table->disableGnss() != 0) {
        return Fail("stopped-no-callback");
    }
    Vendor::LocationVendorInterface::DestroyInstance();
    Vendor::LocationVendorInterface::DestroyInstance();
    if (!WaitUnmapped()) {
        return Fail("final-unload");
    }
    service = nullptr;
    std::puts("PASS public-config-start-stop vendor-data-abi callbacks-cleanup-reload");
    return 0;
}
