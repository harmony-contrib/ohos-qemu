// Actual pinned Future and global-lock wait; fake PixelMap/transport dependencies.
// This checks bounded waiting and result preservation, never renderer or IPC success.
#include <cassert>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <thread>
#include "surface_capture_future.h"
#include "budget.inc"

using namespace OHOS::Rosen;
std::timed_mutex OHOS::Rosen::DmUtils::HoldLock::resMtx;
thread_local bool OHOS::Rosen::DmUtils::HoldLock::lockStatus = false;

int main(int argc, char** argv)
{
    assert(argc == 2);
    assert(GET_HDR_PIXELMAP_TIMEOUT == std::strtol(argv[1], nullptr, 10));
    auto pixel = std::make_shared<OHOS::Media::PixelMap>();
    SurfaceCaptureFuture immediate;
    immediate.OnSurfaceCapture(pixel);
    assert(immediate.GetResult(GET_HDR_PIXELMAP_TIMEOUT) == pixel);
    SurfaceCaptureFuture failed;
    failed.OnSurfaceCaptureWithErrorCode(nullptr, nullptr, CaptureError::INJECTED_FAILURE);
    assert(failed.GetResult(GET_HDR_PIXELMAP_TIMEOUT) == nullptr);
    assert(failed.GetCaptureErrorCode() == CaptureError::INJECTED_FAILURE);
    SurfaceCaptureFuture hdr;
    hdr.OnSurfaceCaptureHDR(pixel, pixel);
    auto pair = hdr.GetHDRResult(GET_HDR_PIXELMAP_TIMEOUT);
    assert(pair.size() == 2 && pair[0] == pixel && pair[1] == pixel);
    SurfaceCaptureFuture delayed;
    std::thread producer([&] {
        std::this_thread::sleep_for(std::chrono::milliseconds(4500));
        DmUtils::HoldLock global;
        delayed.OnSurfaceCapture(pixel);
    });
    {
        DmUtils::HoldLock global;
        auto result = delayed.GetResult(GET_HDR_PIXELMAP_TIMEOUT);
        assert(result == (GET_HDR_PIXELMAP_TIMEOUT > 4500 ? pixel : nullptr));
    }
    producer.join();
    assert(delayed.GetResult(GET_HDR_PIXELMAP_TIMEOUT) == pixel);
    SurfaceCaptureFuture missing;
    auto started = std::chrono::steady_clock::now();
    assert(missing.GetResult(GET_HDR_PIXELMAP_TIMEOUT) == nullptr);
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - started).count();
    assert(elapsed >= GET_HDR_PIXELMAP_TIMEOUT && elapsed < GET_HDR_PIXELMAP_TIMEOUT + 3000);
    std::cout << "PASS immediate/null/error/HDR/delayed/global-lock-release/bounded-timeout "
              << GET_HDR_PIXELMAP_TIMEOUT << std::endl;
}
