// Separate TU: use the actual release headers, never the private mirrors.
#include <cstdint>
#include <memory>
#include <string>
#include "third_party/ohos_ndk/includes/ohos_adapter/graphic_adapter.h"
#include "third_party/ohos_ndk/includes/ohos_adapter/hitrace_adapter.h"

using namespace OHOS::NWeb;
extern void RecordFrame(void*);
namespace {
class Listener final : public FrameAvailableListener {
public:
    Listener(void* context, bool valid) : context_(context), valid_(valid) {}
    void* GetContext() override { return context_; }
    OnFrameAvailableCb GetOnFrameAvailableCb() override { return valid_ ? RecordFrame : nullptr; }
private:
    void* context_;
    bool valid_;
};
class Request final : public BufferRequestConfigAdapter {
public:
    int32_t GetWidth() override { return 64; }
    int32_t GetHeight() override { return 32; }
    int32_t GetStrideAlignment() override { return 8; }
    int32_t GetFormat() override { return PIXEL_FMT_RGBA_8888; }
    uint64_t GetUsage() override { return 0; }
    int32_t GetTimeout() override { return 17; }
    ColorGamutAdapter GetColorGamut() override { return ColorGamutAdapter::SRGB; }
    TransformTypeAdapter GetTransformType() override { return TransformTypeAdapter::ROTATE_NONE; }
};
class Flush final : public BufferFlushConfigAdapter {
public:
    explicit Flush(int64_t timestamp) : timestamp_(timestamp) {}
    int32_t GetX() override { return 1; }
    int32_t GetY() override { return 2; }
    int32_t GetW() override { return 16; }
    int32_t GetH() override { return 8; }
    int64_t GetTimestamp() override { return timestamp_; }
private:
    int64_t timestamp_;
};
}

std::shared_ptr<FrameAvailableListener> MakeReleaseListener(void* context, bool valid)
{
    return std::make_shared<Listener>(context, valid);
}
std::shared_ptr<BufferRequestConfigAdapter> MakeReleaseRequest() { return std::make_shared<Request>(); }
std::shared_ptr<BufferFlushConfigAdapter> MakeReleaseFlush(int64_t timestamp)
{
    return std::make_shared<Flush>(timestamp);
}
void ExerciseReleaseTrace(HiTraceAdapter* adapter)
{
    adapter->StartTrace("start", 3.0f);
    adapter->FinishTrace();
    adapter->StartAsyncTrace("async", 42, 4.0f);
    adapter->FinishAsyncTrace("async", 42);
    adapter->CountTrace("count", 0x100000002LL);
    (void)adapter->IsHiTraceEnable();
    adapter->StartOHOSTrace("ohos", 5.0f);
    adapter->FinishOHOSTrace();
    adapter->CountOHOSTrace("ohos_count", 0x200000001LL);
    (void)adapter->IsACETraceEnable();
}
