// Run the actual adapter CPPs with typed, failure-injectable SDK mocks.
// This checks the private contract/lifetime; it is not a rendering test.
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <cstdarg>
#include <cstring>
#include <iostream>
#include <limits>
#include <mutex>
#include <string>
#include <thread>
#include <vector>
#include <securec.h>
#include <native_image/graphic_error_code.h>
#include <native_window/external_window.h>
#include "arkweb/ohos_adapter_ndk/graphic_adapter/native_image_adapter_impl.h"
#include "arkweb/ohos_adapter_ndk/graphic_adapter/native_window_adapter_impl.h"
#include "arkweb/ohos_adapter_ndk/hiviewdfx_adapter/hitrace_adapter_impl.h"

using namespace OHOS::NWeb;
std::shared_ptr<FrameAvailableListener> MakeReleaseListener(void*, bool);
std::shared_ptr<BufferRequestConfigAdapter> MakeReleaseRequest();
std::shared_ptr<BufferFlushConfigAdapter> MakeReleaseFlush(int64_t);
void ExerciseReleaseTrace(HiTraceAdapter*);

struct OH_NativeImage { OH_OnFrameAvailableListener listener{}; };
struct NativeWindow {};
struct NativeWindowBuffer {};
static NativeWindow window;
static NativeWindowBuffer windowBuffer;
static BufferHandle handle{};
static OH_NativeImage* image = nullptr;
static OH_OnFrameAvailableListener lastProposed{};
static int setResult = 0, unsetResult = 0, requestResult = 0;
static int destroyed = 0, timestampCalls = 0, flushCalls = 0;
static int64_t timestampValue = 0;
static std::vector<std::string> windowEvents, traceEvents;
static std::atomic<int> frameCalls{0}, nullFrameCalls{0};
static bool invokeOnDestroy = false;
static std::mutex frameMutex;
static std::condition_variable frameCondition;
static bool blockFrame = false, enteredFrame = false, releaseFrame = false;

void RecordFrame(void* context)
{
    if (context == nullptr) { ++nullFrameCalls; }
    else { assert(context == &window); }
    ++frameCalls;
    std::unique_lock<std::mutex> lock(frameMutex);
    if (blockFrame) {
        enteredFrame = true;
        frameCondition.notify_all();
        frameCondition.wait(lock, [] { return releaseFrame; });
    }
}
static void Dispatch(OH_OnFrameAvailableListener listener)
{
    if (listener.onFrameAvailable) { listener.onFrameAvailable(listener.context); }
}
extern "C" {
OH_NativeImage* OH_NativeImage_Create(uint32_t, uint32_t) { return image = new OH_NativeImage; }
OH_NativeImage* OH_ConsumerSurface_Create() { return image = new OH_NativeImage; }
OHNativeWindow* OH_NativeImage_AcquireNativeWindow(OH_NativeImage*) { return &window; }
int32_t OH_NativeImage_AttachContext(OH_NativeImage*, uint32_t) { return 0; }
int32_t OH_NativeImage_DetachContext(OH_NativeImage*) { return 0; }
int32_t OH_NativeImage_UpdateSurfaceImage(OH_NativeImage*) { return 0; }
int64_t OH_NativeImage_GetTimestamp(OH_NativeImage*) { return 99; }
int32_t OH_NativeImage_GetTransformMatrix(OH_NativeImage*, float[16]) { return 0; }
int32_t OH_NativeImage_GetSurfaceId(OH_NativeImage*, uint64_t* value) { *value = 7; return 0; }
int32_t OH_NativeImage_SetOnFrameAvailableListener(OH_NativeImage* value, OH_OnFrameAvailableListener listener)
{
    lastProposed = listener;
    if (setResult == 0) { value->listener = listener; }
    return setResult;
}
int32_t OH_NativeImage_UnsetOnFrameAvailableListener(OH_NativeImage* value)
{
    if (unsetResult == 0) { value->listener = {}; }
    return unsetResult;
}
void OH_NativeImage_Destroy(OH_NativeImage** value)
{
    if (invokeOnDestroy) { Dispatch((*value)->listener); }
    delete *value;
    *value = nullptr;
    image = nullptr;
    ++destroyed;
}
int32_t OH_NativeImage_AcquireNativeWindowBuffer(OH_NativeImage*, OHNativeWindowBuffer** value, int* fence)
{ *value = &windowBuffer; *fence = -1; return 0; }
int32_t OH_NativeImage_ReleaseNativeWindowBuffer(OH_NativeImage*, OHNativeWindowBuffer*, int) { return 0; }
int32_t OH_NativeBuffer_FromNativeWindowBuffer(OHNativeWindowBuffer*, OH_NativeBuffer** value)
{ *value = nullptr; return -1; }
BufferHandle* OH_NativeWindow_GetBufferHandleFromNative(OHNativeWindowBuffer*) { return &handle; }
void OH_NativeWindow_DestroyNativeWindow(OHNativeWindow*) {}
int32_t OH_NativeWindow_NativeWindowRequestBuffer(OHNativeWindow*, OHNativeWindowBuffer** value, int* fence)
{ *value = &windowBuffer; *fence = -1; return requestResult; }
int32_t OH_NativeWindow_NativeWindowHandleOpt(OHNativeWindow*, int code, ...)
{
    if (code == SET_UI_TIMESTAMP) {
        va_list args;
        va_start(args, code);
        timestampValue = va_arg(args, int64_t);
        va_end(args);
        ++timestampCalls;
        windowEvents.emplace_back("timestamp");
    }
    return 0;
}
int32_t OH_NativeWindow_NativeWindowFlushBuffer(OHNativeWindow*, OHNativeWindowBuffer*, int fence, Region region)
{
    assert(fence == -1 && region.rects != nullptr);
    assert(region.rects->x == 1 && region.rects->y == 2);
    assert(region.rects->w == 16 && region.rects->h == 8 && region.rectNumber == 0);
    ++flushCalls;
    windowEvents.emplace_back("flush");
    return 73;
}
void OH_HiTrace_StartTrace(const char* value) { traceEvents.emplace_back("start:" + std::string(value)); }
void OH_HiTrace_FinishTrace() { traceEvents.emplace_back("finish"); }
void OH_HiTrace_StartAsyncTrace(const char* value, int32_t id)
{ assert(id == 42); traceEvents.emplace_back("async:" + std::string(value)); }
void OH_HiTrace_FinishAsyncTrace(const char* value, int32_t id)
{ assert(id == 42); traceEvents.emplace_back("async_finish:" + std::string(value)); }
void OH_HiTrace_CountTrace(const char* value, int64_t count)
{ traceEvents.emplace_back("count:" + std::string(value) + ":" + std::to_string(count)); }
void OH_HiTrace_StartTraceEx(HiTrace_Output_Level level, const char* name, const char* value)
{ assert(static_cast<int>(level) == 1); traceEvents.emplace_back("ex:" + std::string(name) + ":" + value); }
void* CachedParameterCreate(const char*, const char*) { return nullptr; }
errno_t strcpy_s(char* dest, size_t size, const char* src)
{ if (strlen(src) >= size) { return 1; } memcpy(dest, src, strlen(src) + 1); return 0; }
}

static void TestListeners()
{
    NativeImageAdapterImpl adapter;
    assert(adapter.SetOnFrameAvailableListener(MakeReleaseListener(&window, true)) == NATIVE_ERROR_UNKNOWN);
    adapter.CreateNativeImage(1, 2);
    assert(adapter.SetOnFrameAvailableListener(nullptr) == NATIVE_ERROR_UNKNOWN);
    assert(adapter.SetOnFrameAvailableListener(MakeReleaseListener(&window, false)) == NATIVE_ERROR_UNKNOWN);
    auto first = MakeReleaseListener(&window, true);
    std::weak_ptr<FrameAvailableListener> oldWeak = first;
    assert(adapter.SetOnFrameAvailableListener(first) == 0);
    auto oldDispatch = image->listener;
    first.reset();
    assert(!oldWeak.expired());
    Dispatch(oldDispatch);
    assert(frameCalls == 1);
    setResult = 81;
    auto rejected = MakeReleaseListener(&window, true);
    std::weak_ptr<FrameAvailableListener> rejectedWeak = rejected;
    assert(adapter.SetOnFrameAvailableListener(rejected) == 81);
    auto failedDispatch = lastProposed;
    rejected.reset();
    assert(rejectedWeak.expired() && !oldWeak.expired());
    Dispatch(failedDispatch);
    assert(frameCalls == 1);
    Dispatch(oldDispatch);
    assert(frameCalls == 2);
    setResult = 0;
    auto current = MakeReleaseListener(nullptr, true);
    std::weak_ptr<FrameAvailableListener> currentWeak = current;
    assert(adapter.SetOnFrameAvailableListener(current) == 0);
    current.reset();
    assert(oldWeak.expired());
    Dispatch(oldDispatch);
    assert(frameCalls == 2);
    Dispatch(image->listener);
    assert(frameCalls == 3 && nullFrameCalls == 1);
    unsetResult = 82;
    assert(adapter.UnsetOnFrameAvailableListener() == 82 && !currentWeak.expired());
    auto activeDispatch = image->listener;
    unsetResult = 0;
    assert(adapter.UnsetOnFrameAvailableListener() == 0 && currentWeak.expired());
    Dispatch(activeDispatch);
    assert(frameCalls == 3);
    adapter.DestroyNativeImage();
    adapter.DestroyNativeImage();
    assert(adapter.UnsetOnFrameAvailableListener() == NATIVE_ERROR_UNKNOWN);
    NativeImageAdapterImpl::OnFrameAvailable(nullptr);

    // An in-flight callback retains the listener while successful unset clears the map.
    adapter.NewNativeImage();
    auto inflight = MakeReleaseListener(&window, true);
    std::weak_ptr<FrameAvailableListener> inflightWeak = inflight;
    assert(adapter.SetOnFrameAvailableListener(inflight) == 0);
    inflight.reset();
    blockFrame = true;
    auto concurrentDispatch = image->listener;
    std::thread thread([&] { Dispatch(concurrentDispatch); });
    {
        std::unique_lock<std::mutex> lock(frameMutex);
        frameCondition.wait(lock, [] { return enteredFrame; });
    }
    assert(adapter.UnsetOnFrameAvailableListener() == 0 && !inflightWeak.expired());
    {
        std::lock_guard<std::mutex> lock(frameMutex);
        releaseFrame = true;
        frameCondition.notify_all();
    }
    thread.join();
    assert(inflightWeak.expired());
    blockFrame = false;
    adapter.DestroyNativeImage();

    // SDK teardown may finish a queued callback; release the registry only afterwards.
    for (int index = 0; index < 100; ++index) {
        auto temporary = std::make_unique<NativeImageAdapterImpl>();
        temporary->CreateNativeImage(1, 2);
        auto listener = MakeReleaseListener(&window, true);
        std::weak_ptr<FrameAvailableListener> weak = listener;
        assert(temporary->SetOnFrameAvailableListener(listener) == 0);
        auto lateDispatch = image->listener;
        listener.reset();
        invokeOnDestroy = true;
        int before = frameCalls;
        temporary.reset();
        invokeOnDestroy = false;
        assert(weak.expired() && frameCalls == before + 1);
        Dispatch(lateDispatch);
        assert(frameCalls == before + 1);
    }
    assert(destroyed == 102);
}

static void TestTimestamp()
{
    ProducerNativeAdapterImpl producer(&window), missing(nullptr);
    int32_t fence = -1;
    auto request = MakeReleaseRequest();
    assert(missing.RequestBuffer(fence, request) == nullptr);
    assert(producer.RequestBuffer(fence, nullptr) == nullptr);
    auto buffer = producer.RequestBuffer(fence, request);
    assert(buffer && timestampCalls == 0);
    requestResult = 83;
    assert(producer.RequestBuffer(fence, request) == nullptr && timestampCalls == 0);
    requestResult = 0;
    for (int64_t value : {int64_t(0), int64_t(-1), int64_t(123456789123LL), std::numeric_limits<int64_t>::max()}) {
        auto config = MakeReleaseFlush(value);
        windowEvents.clear();
        assert(producer.FlushBuffer(buffer, fence, config) == 73);
        assert(timestampValue == value);
        assert((windowEvents == std::vector<std::string>{"timestamp", "flush"}));
    }
    assert(timestampCalls == 4 && flushCalls == 4);
    assert(producer.FlushBuffer(nullptr, fence, MakeReleaseFlush(9)) == -1);
    assert(producer.FlushBuffer(buffer, fence, nullptr) == -1);
    assert(missing.FlushBuffer(buffer, fence, MakeReleaseFlush(9)) == -1);
    assert(timestampCalls == 4 && flushCalls == 4);
}

int main()
{
    TestListeners();
    TestTimestamp();
    auto& trace = HiTraceAdapterImpl::GetInstance();
    ExerciseReleaseTrace(&trace);
    assert((traceEvents == std::vector<std::string>{"start:start", "finish", "async:async",
        "async_finish:async", "count:count:4294967298", "start:ohos", "finish", "count:ohos_count:8589934593"}));
    HiTraceAdapter& base = trace;
    base.StartTraceEx(static_cast<HiTrace_Output_Level>(1), "local", "data", 2.0f);
    assert(traceEvents.back() == "ex:local:data");
    std::cout << "{\"case\":\"actual_m144_private_contract_mock_sdk\",\"destroy_cycles\":100,"
        "\"timestamp_boundaries\":4,\"separate_release_header_caller\":true,\"errors\":0}\n";
}
