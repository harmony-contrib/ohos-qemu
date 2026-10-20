/*
 * Copyright (c) 2023 Huawei Device Co., Ltd.
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

#ifndef I_STREAM_H
#define I_STREAM_H

#include "audio_info.h"
#include "audio_stream_info.h"

namespace OHOS {
namespace AudioStandard {
enum IOperation {
    OPERATION_INVALID = -1,
    OPERATION_STARTED,
    OPERATION_PAUSED,
    OPERATION_STOPPED,
    OPERATION_FLUSHED,
    OPERATION_DRAINED,
    OPERATION_RELEASED,
    OPERATION_UNDERRUN,
    OPERATION_UNDERFLOW,
    OPERATION_SET_OFFLOAD_ENABLE,
    OPERATION_UNSET_OFFLOAD_ENABLE,
    OPERATION_DATA_LINK_CONNECTING,
    OPERATION_DATA_LINK_CONNECTED,
    OPERATION_OFFLOAD_FLUSH_BEGIN,
    OPERATION_OFFLOAD_FLUSH_END,
    OFFLOAD_INACTIVE_BACKGROUND_RUNNING,
    OFFLOAD_ACTIVE_FOREGROUND_RUNNING,
    OPERATION_UPDATE_SPANSIZE,
    OPERATION_SESSION_EFFECT_ENABLED,
    OPERATION_SESSION_EFFECT_DISABLED,
};

enum IStatus {
    I_STATUS_INVALID = -1,
    I_STATUS_IDLE,
    I_STATUS_STARTING,
    I_STATUS_STARTED,
    I_STATUS_PAUSING,
    I_STATUS_PAUSED,
    I_STATUS_FLUSHING_WHEN_STARTED,
    I_STATUS_FLUSHING_WHEN_PAUSED,
    I_STATUS_FLUSHING_WHEN_STOPPED,
    I_STATUS_DRAINING,
    I_STATUS_DRAINED,
    I_STATUS_STOPPING,
    I_STATUS_STOPPED,
    I_STATUS_RELEASING,
    I_STATUS_RELEASED,
};

class IStatusCallback {
public:
    virtual void OnStatusUpdate(IOperation operation) = 0;
};

class IStreamStatusCallback {
public:
    virtual void OnStatusUpdate(IOperation operation, uint32_t streamIndex) = 0;
};

class IStream {
public:
    virtual void SetStreamIndex(uint32_t index) = 0;
    virtual uint32_t GetStreamIndex() = 0;
    virtual int32_t Start() = 0;
    virtual int32_t StartWithSyncId(const int32_t &syncId)
    {
        return Start();
    }
    virtual int32_t Pause(bool isStandby = false) = 0;
    virtual int32_t Flush() = 0;
    virtual int32_t Drain(bool stopFlag = false) = 0;
    virtual int32_t Stop() = 0;
    virtual int32_t Release() = 0;
    virtual void RegisterStatusCallback(const std::weak_ptr<IStatusCallback> &callback) = 0;
    virtual BufferDesc DequeueBuffer(size_t length) = 0;
    virtual int32_t EnqueueBuffer(const BufferDesc &bufferDesc) = 0;
};
} // namespace AudioStandard
} // namespace OHOS
#endif // I_STREAM_H
