// Exercise the actual StreamBase methods with a consumer that returns a
// buffer immediately at publication. This is a permitted asynchronous order,
// not a simulation of a successful packaged Camera test.
#include <algorithm>
#include <condition_variable>
#include <functional>
#include <iostream>
#include <list>
#include <map>
#include <set>
#include <stdexcept>
#include <thread>
#include <unordered_map>
#include <vector>
#define private public
#include "capture_message.h"
#include "real/capture_request.h"
#undef private
#define CAMERA_LOGI(...) ((void)0)
#define CHECK_IF_PTR_NULL_RETURN_VOID(p) if ((p) == nullptr) { return; }

namespace OHOS::Camera {
struct Pipeline {
    bool ready = false;
    int captureId = -1;
    RetCode configResult = RC_OK;
    RetCode captureResult = RC_OK;
    unsigned captures = 0;
    unsigned cancels = 0;
    RetCode Config(std::initializer_list<int>, const CaptureMeta&) { return configResult; }
    RetCode Capture(std::initializer_list<int>, int id)
    {
        ++captures;
        if (captureResult == RC_OK) { ready = true; captureId = id; }
        return captureResult;
    }
    void CancelCapture(std::initializer_list<int>) { ++cancels; ready = false; }
};
struct Tunnel {
    unsigned acquired = 0;
    unsigned returned = 0;
    std::function<void()> onAcquire;
    std::shared_ptr<IBuffer> GetBuffer()
    {
        ++acquired;
        if (onAcquire) onAcquire();
        return std::make_shared<IBuffer>();
    }
    RetCode PutBuffer(const std::shared_ptr<IBuffer>&) { ++returned; return RC_OK; }
    unsigned GetFrameCount() { return returned; }
};
struct BufferPool {
    unsigned published = 0;
    std::function<void(std::shared_ptr<IBuffer>&)> consumer;
    RetCode AddBuffer(std::shared_ptr<IBuffer>& buffer)
    {
        ++published;
        consumer(buffer);
        return RC_OK;
    }
};
class StreamBase : public IStream {
public:
    enum State { STREAM_STATE_IDLE, STREAM_STATE_BUSY };
    std::atomic<State> state_ = STREAM_STATE_BUSY;
    int streamId_ = 11;
    struct { int encodeType = 0; } streamConfig_;
    std::mutex wtLock_, tsLock_;
    std::list<std::shared_ptr<CaptureRequest>> waitingList_, inTransitList_;
    std::shared_ptr<CaptureRequest> lastRequest_;
    std::shared_ptr<CaptureMessageOperator> messenger_;
    std::shared_ptr<Tunnel> tunnel_ = std::make_shared<Tunnel>();
    std::shared_ptr<Pipeline> pipeline_ = std::make_shared<Pipeline>();
    std::shared_ptr<BufferPool> bufferPool_ = std::make_shared<BufferPool>();
    RetCode Capture(const std::shared_ptr<CaptureRequest>&) override;
    RetCode CancelRequest(const std::shared_ptr<CaptureRequest>&) override;
    RetCode OnFrame(const std::shared_ptr<CaptureRequest>&) override;
    RetCode DeliverStreamBuffer();
    void HandleResult(std::shared_ptr<IBuffer>&);
    int32_t GetStreamId() const override { return streamId_; }
    RetCode ReceiveBuffer(std::shared_ptr<IBuffer>& buffer) { return tunnel_->PutBuffer(buffer); }
};
#include "publication_stream_methods.inc"
}
using namespace OHOS::Camera;
void Require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
struct Fixture {
    std::shared_ptr<StreamBase> stream = std::make_shared<StreamBase>();
    std::shared_ptr<CaptureRequest> request;
    unsigned rejectedBeforeConfiguration = 0;
    Fixture(bool continuous = true)
    {
        CaptureMeta settings;
        request = std::make_shared<CaptureRequest>(101, 1, settings, false, continuous);
        Require(request->AddOwner(stream) == RC_OK, "AddOwner");
        request->SetFirstRequest(true);
        stream->waitingList_.push_back(request);
        stream->messenger_ = std::make_shared<CaptureMessageOperator>([](MessageGroup&) {});
        stream->bufferPool_->consumer = [this](std::shared_ptr<IBuffer>& buffer) {
            if (!stream->pipeline_->ready) {
                ++rejectedBeforeConfiguration;
                buffer->SetBufferStatus(CAMERA_BUFFER_STATUS_INVALID);
            } else {
                buffer->SetCaptureId(stream->pipeline_->captureId);
            }
            stream->HandleResult(buffer);
        };
    }
};
int main(int argc, char** argv)
{
    bool repaired = argc == 2 && std::string(argv[1]) == "--repaired";
    Fixture immediate;
    Require(immediate.stream->Capture(immediate.request) == RC_OK, "capture submission failed");
    Require(immediate.request->Cancel() == RC_OK, "cancel failed");
    if (!repaired) {
        Require(immediate.rejectedBeforeConfiguration == 1, "original must publish before pipeline setup");
        Require(immediate.stream->inTransitList_.size() == 1, "original phantom transit not reproduced");
        Require(immediate.request->endedStreams_.empty(), "original missing end not reproduced");
        std::cout << "REPRODUCED: publication before setup leaves phantom transit and no capture end\n";
        return 0;
    }
    Require(immediate.rejectedBeforeConfiguration == 0, "published before configuration");
    Require(immediate.stream->inTransitList_.empty(), "immediate result not retired");
    Require(immediate.request->endedStreams_.count(11) == 1, "missing capture end");
    Require(immediate.stream->tunnel_->returned == 1, "buffer not returned exactly once");

    Fixture cancelled;
    cancelled.stream->tunnel_->onAcquire = [&] { cancelled.request->Cancel(); };
    Require(cancelled.stream->Capture(cancelled.request) == RC_ERROR, "cancel during acquisition must abort");
    Require(cancelled.stream->bufferPool_->published == 0 && cancelled.stream->pipeline_->captures == 0,
            "cancelled acquisition must not submit a new capture");
    Require(cancelled.stream->inTransitList_.empty() && cancelled.stream->tunnel_->returned == 1,
            "cancelled unpublished buffer must return once without phantom transit");
    for (bool failConfig : {false, true}) {
        Fixture failed;
        if (failConfig) failed.stream->pipeline_->configResult = RC_ERROR;
        else failed.stream->pipeline_->captureResult = RC_ERROR;
        Require(failed.stream->Capture(failed.request) == RC_ERROR, "pipeline failure must propagate");
        Require(failed.stream->inTransitList_.empty() && failed.stream->bufferPool_->published == 0 &&
                failed.stream->tunnel_->returned == 1, "setup failure must roll back reservation and buffer");
    }
    Fixture photo(false);
    Require(photo.stream->Capture(photo.request) == RC_OK, "single capture failed");
    Require(photo.stream->inTransitList_.empty() && photo.request->endedStreams_.count(11) == 1,
            "immediate single capture must complete");
    Fixture repeated;
    auto consumer = repeated.stream->bufferPool_->consumer;
    repeated.stream->bufferPool_->consumer = [&](std::shared_ptr<IBuffer>& buffer) {
        // Completion on another thread must not wait for a transit mutex
        // retained by the producer across AddBuffer.
        std::thread result([&] { consumer(buffer); });
        result.join();
    };
    for (int frame = 0; frame < 100; ++frame) {
        Require(repeated.stream->Capture(repeated.request) == RC_OK, "repeated capture failed");
        Require(repeated.stream->inTransitList_.empty() && repeated.request->endedStreams_.empty(),
                "continuous fast results must retire without premature end");
    }
    Require(repeated.request->Cancel() == RC_OK && repeated.stream->pipeline_->cancels == 1 &&
            repeated.stream->tunnel_->returned == 100, "continuous capture must end exactly once");
    Fixture stopped;
    stopped.stream->tunnel_->onAcquire = [&] { stopped.stream->state_ = StreamBase::STREAM_STATE_IDLE; };
    Require(stopped.stream->Capture(stopped.request) == RC_ERROR &&
            stopped.stream->bufferPool_->published == 0 && stopped.stream->inTransitList_.empty() &&
            stopped.stream->tunnel_->returned == 1, "stop during acquisition must not publish");
    Fixture queued;
    queued.stream->bufferPool_->consumer = [](std::shared_ptr<IBuffer>&) {};
    Require(queued.stream->Capture(queued.request) == RC_OK, "queued capture failed");
    queued.stream->pipeline_->configResult = RC_ERROR;
    Require(queued.stream->Capture(queued.request) == RC_ERROR && queued.stream->inTransitList_.size() == 1,
            "failed subsequent submission must preserve older transit reservation");
    Require(queued.request->Cancel() == RC_OK && queued.request->endedStreams_.empty(),
            "cancel must await older in-flight result");
    auto oldBuffer = std::make_shared<IBuffer>();
    oldBuffer->SetCaptureId(101);
    queued.stream->HandleResult(oldBuffer);
    Require(queued.stream->inTransitList_.empty() && queued.request->endedStreams_.count(11) == 1 &&
            queued.stream->tunnel_->returned == 2, "last older result must complete cancelled capture");
    std::cout << "PASS: actual Capture publication, immediate result, cancellation and setup failure boundaries\n";
}
