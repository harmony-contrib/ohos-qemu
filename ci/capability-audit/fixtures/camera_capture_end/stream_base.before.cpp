/*
 * Copyright (c) 2021 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "stream_base.h"
#include "buffer_adapter.h"
#include "buffer_manager.h"
#include "watchdog.h"

namespace OHOS::Camera {
std::map<VdiStreamIntent, std::string> IStream::g_availableStreamType = {
    {PREVIEW, STREAM_INTENT_TO_STRING(PREVIEW)},
    {VIDEO, STREAM_INTENT_TO_STRING(VIDEO)},
    {STILL_CAPTURE, STREAM_INTENT_TO_STRING(STILL_CAPTURE)},
    {POST_VIEW, STREAM_INTENT_TO_STRING(POST_VIEW)},
    {ANALYZE, STREAM_INTENT_TO_STRING(ANALYZE)},
    {CUSTOM, STREAM_INTENT_TO_STRING(CUSTOM)},
};

StreamBase::StreamBase(const int32_t id,
                       const VdiStreamIntent type,
                       std::shared_ptr<IPipelineCore>& p,
                       std::shared_ptr<CaptureMessageOperator>& m) : calltimes_(0)
{
    streamId_ = id;
    streamType_ = static_cast<int32_t>(type);
    pipelineCore_ = p;
    messenger_ = m;
}

StreamBase::~StreamBase()
{
    if (state_ == STREAM_STATE_BUSY) {
        StopStream();
    }

    if (hostStreamMgr_ != nullptr) {
        hostStreamMgr_->DestroyHostStream({streamId_});
    }

    if (pipeline_ != nullptr) {
        pipeline_->DestroyPipeline({streamId_});
    }
}

RetCode StreamBase::ConfigStream(StreamConfiguration& config)
{
    std::unique_lock<std::mutex> l(smLock_);
    if (state_ != STREAM_STATE_IDLE) {
        return RC_ERROR;
    }

    streamConfig_ = config;
    streamConfig_.usage = GetUsage();
    if (tunnel_ != nullptr) {
        streamConfig_.tunnelMode = true;
    }
    streamConfig_.bufferCount = static_cast<int32_t>(GetBufferCount());
    streamConfig_.maxBatchCaptureCount = 1;
    streamConfig_.maxCaptureCount = 1;
    // get device cappability to override configuration
    return RC_OK;
}

RetCode StreamBase::CommitStream()
{
    std::unique_lock<std::mutex> l(smLock_);
    CHECK_IF_NOT_EQUAL_RETURN_VALUE(state_, STREAM_STATE_IDLE, RC_ERROR);

    CHECK_IF_PTR_NULL_RETURN_VALUE(pipelineCore_, RC_ERROR);

    pipeline_ = pipelineCore_->GetStreamPipelineCore();
    CHECK_IF_PTR_NULL_RETURN_VALUE(pipeline_, RC_ERROR);

    hostStreamMgr_ = pipelineCore_->GetHostStreamMgr();
    CHECK_IF_PTR_NULL_RETURN_VALUE(hostStreamMgr_, RC_ERROR);

    HostStreamInfo info;
    info.type_ = static_cast<VdiStreamIntent>(streamType_);
    info.streamId_ = streamId_;
    info.width_ = streamConfig_.width;
    info.height_ = streamConfig_.height;
    info.format_ = streamConfig_.format;
    info.usage_ = streamConfig_.usage;
    info.encodeType_ = streamConfig_.encodeType;

    if (streamConfig_.tunnelMode) {
        BufferManager* mgr = BufferManager::GetInstance();
        CHECK_IF_PTR_NULL_RETURN_VALUE(mgr, RC_ERROR);

        if (bufferPool_ == nullptr) {
            poolId_ = mgr->GenerateBufferPoolId();
            CHECK_IF_EQUAL_RETURN_VALUE(poolId_, 0, RC_ERROR);
            bufferPool_ = mgr->GetBufferPool(poolId_);
            CHECK_IF_PTR_NULL_RETURN_VALUE(bufferPool_, RC_ERROR);
        }
        info.bufferPoolId_ = poolId_;
        info.bufferCount_ = GetBufferCount();
        RetCode rc = bufferPool_->Init(streamConfig_.width, streamConfig_.height, streamConfig_.usage,
                                       streamConfig_.format, GetBufferCount(), CAMERA_BUFFER_SOURCE_TYPE_EXTERNAL);

        CHECK_IF_NOT_EQUAL_RETURN_VALUE(rc, RC_OK, RC_ERROR);
    }
    RetCode rc = hostStreamMgr_->CreateHostStream(info, [this](auto buffer) { HandleResult(buffer); });
    if (rc != RC_OK) {
        CAMERA_LOGE("commit stream [id:%{public}d] to pipeline failed.", streamId_);
        return RC_ERROR;
    }
    CAMERA_LOGI("commit a stream to pipeline id[%{public}d], w[%{public}d], h[%{public}d], poolId[%{public}llu], \
        encodeType = %{public}d", info.streamId_, info.width_, info.height_, info.bufferPoolId_, info.encodeType_);
    state_ = STREAM_STATE_ACTIVE;
    return RC_OK;
}

RetCode StreamBase::StartStream()
{
    CHECK_IF_PTR_NULL_RETURN_VALUE(pipeline_, RC_ERROR);

    int origin = calltimes_.fetch_add(1);
    if (origin != 0) {
        // already called, no reenter
        CAMERA_LOGE("Now will not start, current start %{public}d times", calltimes_.load());
        return RC_ERROR;
    }

    std::unique_lock<std::mutex> l(smLock_);
    if (state_ != STREAM_STATE_ACTIVE) {
        return RC_ERROR;
    }

    CAMERA_LOGI("start stream [id:%{public}d] begin", streamId_);
    tunnel_->NotifyStart();

    RetCode rc = pipeline_->Prepare({streamId_});
    if (rc != RC_OK) {
        CAMERA_LOGE("pipeline [id:%{public}d] prepare failed", streamId_);
        return rc;
    }

    state_ = STREAM_STATE_BUSY;
    std::string threadName =
        g_availableStreamType[static_cast<VdiStreamIntent>(streamType_)] + "#" + std::to_string(streamId_);
    handler_ = std::make_unique<std::thread>([this, &threadName] {
        prctl(PR_SET_NAME, threadName.c_str());
        while (state_ == STREAM_STATE_BUSY) {
            tunnel_->DumpStats(3); // set output interval to 30 second
            HandleRequest();
        }
    });
    if (handler_ == nullptr) {
        state_ = STREAM_STATE_ACTIVE;
        return RC_ERROR;
    }

    rc = pipeline_->Start({streamId_});
    if (rc != RC_OK) {
        CAMERA_LOGE("pipeline [%{public}d] start failed", streamId_);
        return RC_ERROR;
    }
    CAMERA_LOGI("start stream [id:%{public}d] end", streamId_);

    return RC_OK;
}

RetCode StreamBase::StopStream()
{
    CHECK_IF_PTR_NULL_RETURN_VALUE(pipeline_, RC_ERROR);
    std::unique_lock<std::mutex> l(smLock_);

    CAMERA_LOGI("stop stream [id:%{public}d] begin", streamId_);
    {
        std::unique_lock<std::mutex> l(wtLock_);
        CHECK_IF_EQUAL_RETURN_VALUE(state_, STREAM_STATE_IDLE, RC_OK);

        state_ = STREAM_STATE_IDLE;
        tunnel_->NotifyStop();
        cv_.notify_all();
    }

    if (handler_ != nullptr && handler_->joinable()) {
        handler_->join();
        handler_ = nullptr;
    }

    if (!waitingList_.empty()) {
        auto request = waitingList_.front();
        if (request != nullptr && request->IsContinous()) {
            request->Cancel();
        }
    }
    {
        std::unique_lock<std::mutex> l(wtLock_);
        waitingList_.clear();
    }

    RetCode rc = pipeline_->Flush({streamId_});
    CHECK_IF_NOT_EQUAL_RETURN_VALUE(rc, RC_OK, RC_ERROR);
    tunnel_->WaitForAllBufferReturned();
    rc = pipeline_->Stop({streamId_});
    CHECK_IF_NOT_EQUAL_RETURN_VALUE(rc, RC_OK, RC_ERROR);

    if (lastRequest_ != nullptr && lastRequest_->IsContinous() && !inTransitList_.empty() && messenger_ != nullptr) {
        std::shared_ptr<ICaptureMessage> endMessage =
            std::make_shared<CaptureEndedMessage>(streamId_, lastRequest_->GetCaptureId(),
            lastRequest_->GetEndTime(), lastRequest_->GetOwnerCount(), tunnel_->GetFrameCount());
        CAMERA_LOGV("end of stream [%{public}d], ready to send end message", streamId_);
        messenger_->SendMessage(endMessage);
    }
    CAMERA_LOGI("stop stream [id:%{public}d] end", streamId_);
    isFirstRequest = true;
    inTransitList_.clear();
    tunnel_->CleanBuffers();
    bufferPool_->ClearBuffers();
    return RC_OK;
}

RetCode StreamBase::AddRequest(std::shared_ptr<CaptureRequest>& request)
{
    CHECK_IF_PTR_NULL_RETURN_VALUE(request, RC_ERROR);
    request->AddOwner(shared_from_this());

    if (isFirstRequest) {
        RetCode rc = StartStream();
        if (rc != RC_OK) {
            CAMERA_LOGE("start stream [id:%{public}d] failed", streamId_);
            return RC_ERROR;
        }
        request->SetFirstRequest(true);
        isFirstRequest = false;
    }

    {
        std::unique_lock<std::mutex> l(wtLock_);
        waitingList_.emplace_back(request);
        cv_.notify_one();
    }

    return RC_OK;
}

RetCode StreamBase::CancelRequest(const std::shared_ptr<CaptureRequest>& request)
{
    CHECK_IF_PTR_NULL_RETURN_VALUE(request, RC_ERROR);
    CHECK_IF_PTR_NULL_RETURN_VALUE(messenger_, RC_ERROR);
    {
        // We don't care if this request is continious-capture or single-capture, just erase it.
        // And those requests in inTransitList_ removed in HandleResult.
        std::unique_lock<std::mutex> wl(wtLock_);
        auto it = std::find(waitingList_.begin(), waitingList_.end(), request);
        if (it != waitingList_.end()) {
            waitingList_.erase(it);
            CAMERA_LOGI("stream [id:%{public}d], cancel request(capture id:%{public}d) success",
                streamId_, request->GetCaptureId());
        }
    }

    if (request->IsContinous()) {
        // may be this is the last request
        std::unique_lock<std::mutex> tl(tsLock_);
        auto it = std::find(inTransitList_.begin(), inTransitList_.end(), request);
        if (it == inTransitList_.end()) {
            std::shared_ptr<ICaptureMessage> endMessage =
                std::make_shared<CaptureEndedMessage>(streamId_, request->GetCaptureId(), request->GetEndTime(),
                                                      request->GetOwnerCount(), tunnel_->GetFrameCount());
            CAMERA_LOGV("end of stream [%{public}d], ready to send end message", streamId_);
            messenger_->SendMessage(endMessage);
            pipeline_->CancelCapture({streamId_});
        }
    }
    return RC_OK;
}

void StreamBase::HandleRequest()
{
    if (waitingList_.empty()) {
        std::unique_lock<std::mutex> l(wtLock_);
        if (waitingList_.empty()) {
            cv_.wait(l, [this] { return !(state_ == STREAM_STATE_BUSY && waitingList_.empty()); });
        }
    }
    if (state_ != STREAM_STATE_BUSY) {
        return;
    }

    std::shared_ptr<CaptureRequest> request = nullptr;
    {
        // keep a copy of continious-capture in waitingList_, unless it's going to be canceled.
        std::unique_lock<std::mutex> l(wtLock_);
        if (waitingList_.empty()) {
            return;
        }
        request = waitingList_.front();
        CHECK_IF_PTR_NULL_RETURN_VOID(request);
        CAMERA_LOGI("HandleRequest streamId = [%{public}d] and needCancel = [%{public}d]",
            streamId_, request->NeedCancel() ? 1 : 0);
        if (!request->IsContinous()) {
            waitingList_.pop_front();
        }
    }
    if (request == nullptr) {
        CAMERA_LOGE("fatal error, stream [%{public}d] request list is not empty, but can't get one", streamId_);
        return;
    }

    if (request->NeedCancel()) {
        return;
    }

    request->Process(streamId_);

    return;
}

RetCode StreamBase::Capture(const std::shared_ptr<CaptureRequest>& request)
{
    CHECK_IF_PTR_NULL_RETURN_VALUE(request, RC_ERROR);
    CHECK_IF_PTR_NULL_RETURN_VALUE(pipeline_, RC_ERROR);

    RetCode rc = RC_ERROR;
    if (request->IsFirstOne() && !request->IsContinous()) {
        DeliverStreamBuffer();
    } else {
        do {
            rc = DeliverStreamBuffer();
            {
                std::unique_lock<std::mutex> l(wtLock_);
                if (waitingList_.empty()) {
                    CAMERA_LOGI("Capture stream [id:%{public}d] stop deliver buffer.", streamId_);
                    break;
                }
            }
        } while (rc != RC_OK && state_ == STREAM_STATE_BUSY);
    }

    rc = pipeline_->Config({streamId_}, request->GetCaptureSetting());
    if (rc != RC_OK) {
        CAMERA_LOGE("stream [id:%{public}d] config pipeline failed.", streamId_);
        return RC_ERROR;
    }

    rc = pipeline_->Capture({streamId_}, request->GetCaptureId());
    if (rc != RC_OK) {
        CAMERA_LOGE("stream [id:%{public}d] take a capture failed.", streamId_);
        return RC_ERROR;
    }

    {
        std::unique_lock<std::mutex> l(tsLock_);
        inTransitList_.emplace_back(request);
    }

    if (request->IsFirstOne()) {
        if (messenger_ == nullptr) {
            CAMERA_LOGE("stream [id:%{public}d] can't send message, messenger_ is null", streamId_);
            return RC_ERROR;
        }
        std::shared_ptr<ICaptureMessage> startMessage = std::make_shared<CaptureStartedMessage>(
            streamId_, request->GetCaptureId(), request->GetBeginTime(), request->GetOwnerCount());
        messenger_->SendMessage(startMessage);
        request->SetFirstRequest(false);
    }

    return RC_OK;
}

RetCode StreamBase::DeliverStreamBuffer()
{
    CHECK_IF_PTR_NULL_RETURN_VALUE(tunnel_, RC_ERROR);
    CHECK_IF_PTR_NULL_RETURN_VALUE(bufferPool_, RC_ERROR);

    std::shared_ptr<IBuffer> buffer = tunnel_->GetBuffer();
    CHECK_IF_PTR_NULL_RETURN_VALUE(buffer, RC_ERROR);

    buffer->SetEncodeType(streamConfig_.encodeType);
    buffer->SetStreamId(streamId_);
    bufferPool_->AddBuffer(buffer);
    CAMERA_LOGI("stream [id:%{public}d] enqueue buffer index:%{public}d, size:%{public}d",
        streamId_, buffer->GetIndex(), buffer->GetSize());
    return RC_OK;
}

void StreamBase::HandleResult(std::shared_ptr<IBuffer>& buffer)
{
    CHECK_IF_PTR_NULL_RETURN_VOID(buffer);
    if (buffer->GetBufferStatus() == CAMERA_BUFFER_STATUS_INVALID) {
        CAMERA_LOGI("stream [id:%{public}d], this buffer(index:%{public}d) has nothing to do with request.", streamId_,
                    buffer->GetIndex());
        ReceiveBuffer(buffer);
        return;
    }

    if (buffer->GetStreamId() != streamId_) {
        CAMERA_LOGE("fatal error, stream [%{public}d] reveived a wrong buffer, index:%{public}d. \
            this buffer belongs to stream:%{public}d", streamId_, buffer->GetIndex(), buffer->GetStreamId());
        return;
    }

    int32_t captureId = buffer->GetCaptureId();
    std::shared_ptr<CaptureRequest> request = nullptr;
    {
        std::unique_lock<std::mutex> l(tsLock_);
        for (auto& r : inTransitList_) {
            if (r == nullptr) {
                continue;
            }
            if (r->GetCaptureId() == captureId) {
                request = r;
                break;
            }
        }
    }
    if (request == nullptr) {
        CAMERA_LOGI("stream [id:%{public}d], this buffer(index:%{public}d) has nothing to do with request.",
            streamId_, buffer->GetIndex());
        buffer->SetBufferStatus(CAMERA_BUFFER_STATUS_INVALID);
        ReceiveBuffer(buffer);
        return;
    }
    request->AttachBuffer(buffer);
    // To synchronize multiple stream, bottom-layer device stream need be synchronized first.
    request->OnResult(streamId_);
    lastRequest_ = request;
}

RetCode StreamBase::OnFrame(const std::shared_ptr<CaptureRequest>& request)
{
    CHECK_IF_PTR_NULL_RETURN_VALUE(request, RC_ERROR);
    CHECK_IF_PTR_NULL_RETURN_VALUE(pipeline_, RC_ERROR);
    CHECK_IF_PTR_NULL_RETURN_VALUE(messenger_, RC_ERROR);
    auto buffer = request->GetAttachedBuffer();
    CameraBufferStatus status = buffer->GetBufferStatus();
    if (status != CAMERA_BUFFER_STATUS_OK) {
        if (status != CAMERA_BUFFER_STATUS_DROP) {
            std::shared_ptr<ICaptureMessage> errorMessage =
                std::make_shared<CaptureErrorMessage>(streamId_, request->GetCaptureId(), request->GetEndTime(),
                                                      request->GetOwnerCount(), static_cast<VdiStreamError>(status));
            messenger_->SendMessage(errorMessage);
        } else {
            CAMERA_LOGE("stream [id:%{public}d] drop buffer index:%{public}d, status:%{public}d",
                streamId_, buffer->GetIndex(), buffer->GetBufferStatus());
            ReceiveBuffer(buffer);
            return RC_OK;
        }
    }
    CAMERA_LOGI("stream = [%{public}d] OnFrame and NeedCancel = [%{public}d]", buffer->GetStreamId(),
        request->NeedCancel() ? 1 : 0);
    request->NeedCancel() ? buffer->SetBufferStatus(CAMERA_BUFFER_STATUS_DROP) :
                            buffer->SetBufferStatus(CAMERA_BUFFER_STATUS_OK);
    ReceiveBuffer(buffer);
    if (request->NeedShutterCallback()) {
        std::shared_ptr<ICaptureMessage> shutterMessage = std::make_shared<FrameShutterMessage>(
            streamId_, request->GetCaptureId(), request->GetEndTime(), request->GetOwnerCount());
        messenger_->SendMessage(shutterMessage);
    }
    bool isEnded = !request->IsContinous() || request->NeedCancel();
    {
        // inTransitList_ may has multiple copies of continious-capture request, we just need erase one of them.
        std::unique_lock<std::mutex> l(tsLock_);
        for (auto it = inTransitList_.begin(); it != inTransitList_.end(); it++) {
            if ((*it) == request) {
                inTransitList_.erase(it);
                break;
            }
        }
        if (isEnded) {
            // if this is the last request of capture, send CaptureEndedMessage.
            auto it = std::find(inTransitList_.begin(), inTransitList_.end(), request);
            if (it == inTransitList_.end()) {
                std::shared_ptr<ICaptureMessage> endMessage =
                    std::make_shared<CaptureEndedMessage>(streamId_, request->GetCaptureId(), request->GetEndTime(),
                                                          request->GetOwnerCount(), tunnel_->GetFrameCount());
                CAMERA_LOGV("end of stream [%d], capture id = %d", streamId_, request->GetCaptureId());
                messenger_->SendMessage(endMessage);
                pipeline_->CancelCapture({streamId_});
            }
        }
    }
    return RC_OK;
}

RetCode StreamBase::ReceiveBuffer(std::shared_ptr<IBuffer>& buffer)
{
    CHECK_IF_PTR_NULL_RETURN_VALUE(buffer, RC_ERROR);
    CHECK_IF_PTR_NULL_RETURN_VALUE(tunnel_, RC_ERROR);
    CHECK_IF_PTR_NULL_RETURN_VALUE(bufferPool_, RC_ERROR);

    CAMERA_LOGI("stream [id:%{public}d] dequeue buffer index:%{public}d, status:%{public}d",
        streamId_, buffer->GetIndex(), buffer->GetBufferStatus());
    bufferPool_->ReturnBuffer(buffer);
    tunnel_->PutBuffer(buffer);
    return RC_OK;
}

uint64_t StreamBase::GetFrameCount() const
{
    CHECK_IF_PTR_NULL_RETURN_VALUE(tunnel_, 0);
    return tunnel_->GetFrameCount();
}

RetCode StreamBase::AttachStreamTunnel(std::shared_ptr<StreamTunnel>& tunnel)
{
    std::unique_lock<std::mutex> l(smLock_);
    if (state_ == STREAM_STATE_BUSY || state_ == STREAM_STATE_OFFLINE) {
        return RC_ERROR;
    }

    tunnel_ = tunnel;
    CHECK_IF_PTR_NULL_RETURN_VALUE(tunnel_, RC_ERROR);
    tunnel_->SetBufferCount(GetBufferCount());
    TunnelConfig config = {(uint32_t)streamConfig_.width, (uint32_t)streamConfig_.height,
        (uint32_t)streamConfig_.format, streamConfig_.usage};
    tunnel_->Config(config);
    tunnel_->SetStreamId(streamId_);
    streamConfig_.tunnelMode = true;
    return RC_OK;
}

RetCode StreamBase::DetachStreamTunnel()
{
    std::unique_lock<std::mutex> l(smLock_);
    if (state_ == STREAM_STATE_BUSY || state_ == STREAM_STATE_OFFLINE) {
        return RC_ERROR;
    }

    tunnel_.reset();
    streamConfig_.tunnelMode = false;

    state_ = STREAM_STATE_IDLE;
    return RC_OK;
}

RetCode StreamBase::ChangeToOfflineStream(std::shared_ptr<OfflineStream> offlineStream)
{
    (void)offlineStream;
    return RC_OK;
}

uint64_t StreamBase::GetUsage()
{
#ifdef BUFFER_PARTIAL_USAGE
    // Used to solve the problem of flashing stripes in unisoc camera preview screen
    return CAMERA_USAGE_SW_WRITE_OFTEN | CAMERA_USAGE_MEM_DMA;
#else
    return CAMERA_USAGE_SW_WRITE_OFTEN | CAMERA_USAGE_SW_READ_OFTEN | CAMERA_USAGE_MEM_DMA;
#endif
}

uint32_t StreamBase::GetBufferCount()
{
#ifdef PREVIEW_BUFFER_NUM
    return PREVIEW_BUFFER_NUM; // buffer count
#else
    constexpr uint32_t defaultBufferCount = 3;
    return defaultBufferCount;
#endif
}

StreamConfiguration StreamBase::GetStreamAttribute() const
{
    return streamConfig_;
}

int32_t StreamBase::GetStreamId() const
{
    return streamId_;
}

bool StreamBase::IsRunning() const
{
    return state_ == STREAM_STATE_BUSY;
}

bool StreamBase::GetTunnelMode() const
{
    return streamConfig_.tunnelMode;
}

void StreamBase::DumpStatsInfo() const
{
    if (tunnel_ != nullptr) {
        tunnel_->DumpStats();
    }
}

void StreamBase::ReleaseStreamBufferPool()
{
    BufferManager* mgr = BufferManager::GetInstance();
    if (mgr != nullptr) {
        mgr->EraseBufferPoolMapById(poolId_);
    }
    bufferPool_ = nullptr;
}
} // namespace OHOS::Camera
