/* Copyright (c) 2026 OpenHarmony contributors.
 * Licensed under the Apache License, Version 2.0; see
 * http://www.apache.org/licenses/LICENSE-2.0
 * Distributed on an AS IS BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
 */
#ifndef OHOS_QEMU_MTP_STANDARD_FUNCTIONFS_H
#define OHOS_QEMU_MTP_STANDARD_FUNCTIONFS_H
#include "usbfn_mtp_impl.h"
#include <atomic>
#include <shared_mutex>
#include <thread>

namespace OHOS::HDI::Usb::Gadget::Mtp::V1_0 {
/* An ordinary product backend of the existing MTP HDI. All MTP sessions,
 * object permissions, media-library storage and protocol processing remain in
 * the original media_mtp service. No test response or object database exists
 * in this USB transport. The normal QEMU product selects it at GN build time.
 */
class QemuMtpFunctionFS final : public UsbfnMtpImpl {
public:
    ~QemuMtpFunctionFS() override;
    int32_t Start() override;
    int32_t Stop() override;
    int32_t Init() override { return Start(); }
    int32_t Release() override { return Stop(); }
    int32_t Read(std::vector<uint8_t> &data) override;
    int32_t Write(const std::vector<uint8_t> &data) override;
    int32_t ReceiveFile(const UsbFnMtpFileSlice &file) override;
    int32_t SendFile(const UsbFnMtpFileSlice &file) override;
    int32_t SendEvent(const std::vector<uint8_t> &data) override;
private:
    int Poll(int fd, short events, uint64_t generation, int timeoutMs = 30000);
    int Send(int fd, const uint8_t *data, size_t length, uint64_t generation);
    void Control();
    void Setup(uint8_t type, uint8_t request, uint16_t length);
    void CloseDescriptors();
    std::mutex lifecycle_, read_, write_, event_;
    std::shared_mutex active_;
    std::thread control_;
    std::atomic<bool> stopping_{true}, enabled_{false}, cancelled_{false}, busy_{false};
    std::atomic<uint64_t> generation_{0};
    std::atomic<uint16_t> packet_{512};
    int ep0_ = -1, in_ = -1, out_ = -1, interrupt_ = -1, wake_ = -1;
};
} // namespace OHOS::HDI::Usb::Gadget::Mtp::V1_0
#endif
