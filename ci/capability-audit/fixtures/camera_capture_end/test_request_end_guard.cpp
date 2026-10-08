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
#include <set>
#include <map>
#define private public
#include "capture_message.h"
#include "real/capture_request.h"
#undef private
#define CAMERA_LOGI(...) ((void)0)
#define CHECK_IF_PTR_NULL_RETURN_VALUE(p, value) if ((p) == nullptr) { return value; }
#define CHECK_IF_EQUAL_RETURN_VALUE(p, q, value) if ((p) == (q)) { return value; }
#define CHECK_IF_NOT_EQUAL_RETURN_VALUE(p, q, value) if ((p) != (q)) { return value; }
namespace OHOS::Camera {
struct Pipeline {
    std::atomic<unsigned> cancels = 0;
    void CancelCapture(std::initializer_list<int>) { ++cancels; }
    RetCode Flush(std::initializer_list<int>) { return RC_OK; }
    RetCode Stop(std::initializer_list<int>) { return RC_OK; }
};
struct Tunnel {
    unsigned GetFrameCount() { return 7; }
    void NotifyStop() {}
    void WaitForAllBufferReturned() {}
    void CleanBuffers() {}
};
struct BufferPool { void ClearBuffers() {} };
class StreamBase : public IStream {
public:
    enum State { STREAM_STATE_IDLE, STREAM_STATE_BUSY };
    std::atomic<State> state_ = STREAM_STATE_BUSY;
    int streamId_ = 11;
    std::mutex wtLock_;
    std::mutex tsLock_;
    std::mutex smLock_;
    std::condition_variable cv_;
    bool isFirstRequest = false;
    unsigned returnedBuffers = 0;
    std::unique_ptr<std::thread> handler_;
    std::list<std::shared_ptr<CaptureRequest>> waitingList_;
    std::list<std::shared_ptr<CaptureRequest>> inTransitList_;
    std::shared_ptr<CaptureRequest> lastRequest_;
    std::shared_ptr<CaptureMessageOperator> messenger_;
    std::shared_ptr<Tunnel> tunnel_ = std::make_shared<Tunnel>();
    std::shared_ptr<Pipeline> pipeline_ = std::make_shared<Pipeline>();
    std::shared_ptr<BufferPool> bufferPool_ = std::make_shared<BufferPool>();
    RetCode StopStream();
    RetCode CancelRequest(const std::shared_ptr<CaptureRequest>& request) override;
    RetCode OnFrame(const std::shared_ptr<CaptureRequest>& request) override;
    RetCode Capture(const std::shared_ptr<CaptureRequest>&) override { return RC_OK; }
    int32_t GetStreamId() const override { return streamId_; }
    void ReceiveBuffer(std::shared_ptr<IBuffer>&) { ++returnedBuffers; }
};
#include "candidate_stream_methods.inc"
}
using namespace OHOS::Camera;

void Require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
struct Fixture {
    std::vector<MessageGroup> callbacks;
    std::shared_ptr<StreamBase> stream = std::make_shared<StreamBase>();
    std::shared_ptr<CaptureRequest> request;
    Fixture(bool continuous = true)
    {
        CaptureMeta settings;
        request = std::make_shared<CaptureRequest>(101, 1, settings, false, continuous);
        stream->messenger_ = std::make_shared<CaptureMessageOperator>(
            [this](MessageGroup& group) { callbacks.push_back(group); });
        Require(request->AddOwner(stream) == RC_OK, "real AddOwner failed");
        request->semr_->timestamp_ = 1000;
        auto buffer = std::make_shared<IBuffer>();
        request->AttachBuffer(buffer);
    }
    void Drain()
    {
        auto& op = *stream->messenger_;
        Require(op.wakeup_, "expected queued ready message");
        op.running_ = true;
        op.HandleMessage();
        op.running_ = false;
    }
};

int main()
{
    Fixture coalesced;
    coalesced.stream->inTransitList_.push_back(coalesced.request);
    coalesced.stream->waitingList_.push_back(coalesced.request);
    coalesced.request->needCancel_ = true;
    Require(coalesced.stream->OnFrame(coalesced.request) == RC_OK, "OnFrame failed");
    Require(coalesced.request->Cancel() == RC_OK, "real Cancel failed");
    Require(coalesced.stream->pipeline_->cancels == 1, "per-request owner must cancel pipeline once");
    coalesced.Drain();
    Require(coalesced.callbacks.size() == 1, "coalesced duplicate must produce one end");

    Fixture separated;
    separated.stream->inTransitList_.push_back(separated.request);
    separated.request->needCancel_ = true;
    Require(separated.stream->OnFrame(separated.request) == RC_OK, "OnFrame failed");
    separated.Drain();
    Require(separated.request->Cancel() == RC_OK, "post-dispatch real Cancel failed");
    Require(!separated.stream->messenger_->wakeup_, "post-dispatch duplicate must not queue again");
    Require(separated.callbacks.size() == 1, "post-dispatch exact-once failed");

    Fixture concurrent;
    std::vector<std::thread> threads;
    for (int i = 0; i < 64; ++i) threads.emplace_back([&] {
        Require(concurrent.request->Cancel() == RC_OK, "concurrent real Cancel failed");
    });
    for (auto& thread : threads) thread.join();
    concurrent.Drain();
    Require(concurrent.callbacks.size() == 1 && concurrent.stream->pipeline_->cancels == 1,
            "concurrent Cancel must emit exactly one end per owner");

    for (int iteration = 0; iteration < 1000; ++iteration) {
        Fixture racing;
        racing.stream->inTransitList_.push_back(racing.request);
        racing.stream->waitingList_.push_back(racing.request);
        racing.request->needCancel_ = true;
        std::atomic<bool> ready = false;
        std::thread result([&] {
            while (!ready.load()) std::this_thread::yield();
            Require(racing.stream->OnFrame(racing.request) == RC_OK, "racing OnFrame failed");
        });
        std::thread cancel([&] {
            while (!ready.load()) std::this_thread::yield();
            Require(racing.request->Cancel() == RC_OK, "racing real Cancel failed");
        });
        ready = true;
        result.join();
        cancel.join();
        racing.Drain();
        Require(racing.callbacks.size() == 1 && racing.stream->pipeline_->cancels == 1 &&
                racing.stream->inTransitList_.empty() && racing.stream->returnedBuffers == 1,
                "concurrent OnFrame/Cancel must return frame and complete once");
    }

    Fixture eos(false);
    eos.stream->inTransitList_.push_back(eos.request);
    Require(eos.stream->OnFrame(eos.request) == RC_OK, "normal EOS failed");
    eos.Drain();
    Require(eos.callbacks.size() == 1 && eos.request->GetAttachedBuffer()->GetBufferStatus() ==
            CAMERA_BUFFER_STATUS_OK, "normal EOS must keep successful image and end");
    Require(!eos.request->TryMarkCaptureEnded(99), "non-owner stream cannot claim end");

    Fixture reusedContinuous;
    for (int frame = 0; frame < 100; ++frame) {
        reusedContinuous.stream->inTransitList_.push_back(reusedContinuous.request);
        Require(reusedContinuous.stream->OnFrame(reusedContinuous.request) == RC_OK,
                "same continuous request normal OnFrame failed");
        Require(!reusedContinuous.stream->messenger_->wakeup_ &&
                reusedContinuous.request->endedStreams_.empty() &&
                reusedContinuous.request->GetAttachedBuffer()->GetBufferStatus() == CAMERA_BUFFER_STATUS_OK,
                "ordinary repeated continuous frames must not mark or emit final end");
    }
    Require(reusedContinuous.stream->returnedBuffers == 100, "continuous frames must return every buffer");
    Require(reusedContinuous.request->Cancel() == RC_OK, "cancel repeated continuous request failed");
    reusedContinuous.Drain();
    Require(reusedContinuous.callbacks.size() == 1,
            "continuous request repeated-frame lifetime must finish exactly once");

    Fixture repeatedTransit;
    repeatedTransit.request->needCancel_ = true;
    repeatedTransit.stream->inTransitList_.push_back(repeatedTransit.request);
    repeatedTransit.stream->inTransitList_.push_back(repeatedTransit.request);
    Require(repeatedTransit.stream->OnFrame(repeatedTransit.request) == RC_OK, "first pending OnFrame failed");
    Require(!repeatedTransit.stream->messenger_->wakeup_ &&
            repeatedTransit.stream->inTransitList_.size() == 1,
            "first of two pending copies must not complete before last result");
    Require(repeatedTransit.stream->OnFrame(repeatedTransit.request) == RC_OK, "last pending OnFrame failed");
    repeatedTransit.Drain();
    Require(repeatedTransit.callbacks.size() == 1 && repeatedTransit.stream->returnedBuffers == 2,
            "two pending copies must complete exactly once only after final retirement");

    Fixture dropped;
    dropped.stream->inTransitList_.push_back(dropped.request);
    dropped.request->needCancel_ = true;
    dropped.request->GetAttachedBuffer()->SetBufferStatus(CAMERA_BUFFER_STATUS_DROP);
    Require(dropped.stream->OnFrame(dropped.request) == RC_OK, "cancelled DROP OnFrame failed");
    Require(dropped.stream->inTransitList_.empty(), "DROP result must retire actual transit entry");
    Require(dropped.stream->returnedBuffers == 1 && dropped.request->GetAttachedBuffer()->GetBufferStatus() ==
            CAMERA_BUFFER_STATUS_DROP, "DROP buffer must be returned once without becoming successful image");
    dropped.Drain();
    Require(dropped.request->Cancel() == RC_OK, "Cancel after dropped completion failed");
    Require(!dropped.stream->messenger_->wakeup_ && dropped.callbacks.size() == 1,
            "cancelled DROP must finish exactly once");

    Fixture dropThenCancel;
    dropThenCancel.stream->inTransitList_.push_back(dropThenCancel.request);
    dropThenCancel.request->GetAttachedBuffer()->SetBufferStatus(CAMERA_BUFFER_STATUS_DROP);
    Require(dropThenCancel.stream->OnFrame(dropThenCancel.request) == RC_OK, "ordinary DROP OnFrame failed");
    Require(dropThenCancel.stream->inTransitList_.empty() && !dropThenCancel.stream->messenger_->wakeup_ &&
            dropThenCancel.stream->returnedBuffers == 1 && dropThenCancel.request->GetAttachedBuffer()->
                GetBufferStatus() == CAMERA_BUFFER_STATUS_DROP,
            "ordinary uncancelled DROP must not finish continuous flow or return a successful image");
    Require(dropThenCancel.request->Cancel() == RC_OK, "Cancel after ordinary DROP failed");
    dropThenCancel.Drain();
    Require(dropThenCancel.callbacks.size() == 1, "ordinary DROP then Cancel must complete once");

    Fixture dropThenStop;
    dropThenStop.stream->inTransitList_.push_back(dropThenStop.request);
    dropThenStop.request->GetAttachedBuffer()->SetBufferStatus(CAMERA_BUFFER_STATUS_DROP);
    Require(dropThenStop.stream->OnFrame(dropThenStop.request) == RC_OK, "DROP before stop failed");
    // StopStream cancels the continuous waiting request before flushing pending buffers.
    dropThenStop.stream->waitingList_.push_back(dropThenStop.request);
    dropThenStop.stream->lastRequest_ = dropThenStop.request;
    Require(dropThenStop.stream->StopStream() == RC_OK, "StopStream after DROP failed");
    dropThenStop.Drain();
    Require(dropThenStop.callbacks.size() == 1 && dropThenStop.stream->returnedBuffers == 1,
            "ordinary DROP then StopStream must return buffer and complete once");

    Fixture photoDrop(false);
    photoDrop.stream->inTransitList_.push_back(photoDrop.request);
    photoDrop.request->GetAttachedBuffer()->SetBufferStatus(CAMERA_BUFFER_STATUS_DROP);
    Require(photoDrop.stream->OnFrame(photoDrop.request) == RC_OK, "single capture DROP failed");
    photoDrop.Drain();
    Require(photoDrop.callbacks.size() == 1 && photoDrop.stream->returnedBuffers == 1 &&
            photoDrop.request->GetAttachedBuffer()->GetBufferStatus() == CAMERA_BUFFER_STATUS_DROP,
            "single capture DROP must end without forging a successful photo");

    Fixture stopped;
    stopped.stream->inTransitList_.push_back(stopped.request);
    stopped.stream->lastRequest_ = stopped.request;
    stopped.request->needCancel_ = true;
    Require(stopped.stream->StopStream() == RC_OK, "StopStream failed");
    stopped.Drain();
    Require(stopped.request->Cancel() == RC_OK, "Cancel after stop failed");
    Require(!stopped.stream->messenger_->wakeup_ && stopped.callbacks.size() == 1,
            "StopStream/Cancel must share end guard");

    Fixture restarted;
    for (int run = 0; run < 100; ++run) {
        CaptureMeta settings;
        auto fresh = std::make_shared<CaptureRequest>(101, 1, settings, false, true);
        Require(fresh->AddOwner(restarted.stream) == RC_OK, "fresh owner registration failed");
        fresh->semr_->timestamp_ = 1000;
        Require(fresh->Cancel() == RC_OK, "fresh restart cancellation failed");
        restarted.Drain();
    }
    Require(restarted.callbacks.size() == 100,
            "request-lifetime guard must not suppress real new capture restarts");

    Fixture composite;
    auto peer = std::make_shared<StreamBase>();
    peer->streamId_ = 12;
    peer->messenger_ = composite.stream->messenger_;
    Require(composite.request->AddOwner(peer) == RC_OK, "second owner registration failed");
    Require(composite.request->GetOwnerCount() == 2, "real composite owner count incorrect");
    Require(composite.request->Cancel() == RC_OK, "composite real cancellation failed");
    composite.Drain();
    Require(composite.callbacks.size() == 1 && composite.callbacks[0].size() == 2 &&
            composite.callbacks[0][0]->GetStreamId() != composite.callbacks[0][1]->GetStreamId(),
            "request guard must preserve legitimate multi-stream peers");

    std::cout << "full actual CaptureRequest + exact candidate StreamBase three end methods: "
              << "coalesced/post-dispatch/concurrent end exact-once; normal EOS; stop; "
              << "1000 concurrent OnFrame/Cancel races; "
              << "100 same-request continuous frames and multiple pending copies; "
              << "100 fresh same-ID restarts; composite cancellation; non-owner rejection PASS"
              << "; cancelled/ordinary/single-shot DROP retirement and status preservation PASS"
              << std::endl;
}
