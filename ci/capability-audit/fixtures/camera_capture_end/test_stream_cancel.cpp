#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <list>
#include <memory>
#include <mutex>
#include <thread>
#include <unordered_map>
#include <vector>
#include <algorithm>
#include <iostream>
#include <stdexcept>
#define private public
#include "capture_message.h"
#undef private
#define CAMERA_LOGI(...) ((void)0)
#define CHECK_IF_PTR_NULL_RETURN_VALUE(p, value) if ((p) == nullptr) { return value; }

namespace OHOS::Camera {
enum CameraBufferStatus { CAMERA_BUFFER_STATUS_OK, CAMERA_BUFFER_STATUS_DROP, CAMERA_BUFFER_STATUS_INVALID };
struct Buffer {
    CameraBufferStatus status = CAMERA_BUFFER_STATUS_OK;
    CameraBufferStatus GetBufferStatus() { return status; }
    void SetBufferStatus(CameraBufferStatus value) { status = value; }
    int GetIndex() { return 0; }
    int GetStreamId() { return 11; }
};
class CaptureRequest {
public:
    bool continuous = true;
    bool cancelled = true;
    std::shared_ptr<Buffer> buffer = std::make_shared<Buffer>();
    bool IsContinous() { return continuous; }
    bool NeedCancel() { return cancelled; }
    uint64_t GetEndTime() { return 1000; }
    int GetCaptureId() { return 101; }
    unsigned GetOwnerCount() { return 1; }
    bool NeedShutterCallback() { return false; }
    std::shared_ptr<Buffer> GetAttachedBuffer() { return buffer; }
};
struct Pipeline {
    unsigned cancels = 0;
    void CancelCapture(std::initializer_list<int>) { ++cancels; }
};
struct Tunnel { unsigned GetFrameCount() { return 7; } };
class StreamBase {
public:
    int streamId_ = 11;
    std::mutex wtLock_;
    std::mutex tsLock_;
    std::list<std::shared_ptr<CaptureRequest>> waitingList_;
    std::list<std::shared_ptr<CaptureRequest>> inTransitList_;
    std::shared_ptr<CaptureMessageOperator> messenger_;
    std::shared_ptr<Tunnel> tunnel_ = std::make_shared<Tunnel>();
    std::shared_ptr<Pipeline> pipeline_ = std::make_shared<Pipeline>();
    RetCode CancelRequest(const std::shared_ptr<CaptureRequest>& request);
    RetCode OnFrame(const std::shared_ptr<CaptureRequest>& request);
    void ReceiveBuffer(std::shared_ptr<Buffer>&) {}
};
#include "actual_stream_methods.inc"
}
using namespace OHOS::Camera;

void Require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }

struct Fixture {
    std::vector<MessageGroup> callbacks;
    StreamBase stream;
    std::shared_ptr<CaptureRequest> request = std::make_shared<CaptureRequest>();
    Fixture()
    {
        stream.messenger_ = std::make_shared<CaptureMessageOperator>(
            [this](MessageGroup& group) { callbacks.push_back(group); });
        stream.inTransitList_.push_back(request);
        stream.waitingList_.push_back(request);
    }
    void Drain()
    {
        auto& op = *stream.messenger_;
        Require(op.wakeup_, "expected queued ready message");
        op.running_ = true;
        op.HandleMessage();
        op.running_ = false;
    }
};

int main(int argc, char** argv)
{
    const bool groupingRepair = argc == 2 && std::string(argv[1]) == "--grouping-repair";
    Fixture coalesced;
    // Concrete cancellation interleaving: CaptureRequest::Cancel has set needCancel=true,
    // but before its owner CancelRequest acquires tsLock, the result thread enters OnFrame.
    Require(coalesced.stream.OnFrame(coalesced.request) == RC_OK, "OnFrame failed");
    Require(coalesced.stream.CancelRequest(coalesced.request) == RC_OK, "CancelRequest failed");
    Require(coalesced.stream.pipeline_->cancels == 2, "actual methods did not both emit cancellation");
    coalesced.Drain();
    Require(coalesced.callbacks.size() == (groupingRepair ? 1 : 0),
            "actual method duplicate-end queue poisoning expectation violated");

    Fixture separated;
    Require(separated.stream.OnFrame(separated.request) == RC_OK, "OnFrame failed");
    separated.Drain();
    Require(separated.stream.CancelRequest(separated.request) == RC_OK, "CancelRequest failed");
    separated.Drain();
    Require(separated.callbacks.size() == 2,
            "post-dispatch duplicate end source no longer reproduced");

    Fixture dropped;
    dropped.request->buffer->status = CAMERA_BUFFER_STATUS_DROP;
    Require(dropped.stream.OnFrame(dropped.request) == RC_OK, "dropped OnFrame failed");
    Require(dropped.stream.CancelRequest(dropped.request) == RC_OK, "dropped CancelRequest failed");
    Require(!dropped.stream.messenger_->wakeup_ && dropped.stream.inTransitList_.size() == 1,
            "dropped cancelled result pending-transit end loss no longer reproduced");
    std::cout << "actual StreamBase CancelRequest/OnFrame bodies: "
              << (groupingRepair ? "coalesced end preserved" : "coalesced end lost")
              << "; post-dispatch duplicate end REPRODUCED (2 callbacks); "
              << "cancelled dropped result loses end and leaves inTransit REPRODUCED" << std::endl;
}
