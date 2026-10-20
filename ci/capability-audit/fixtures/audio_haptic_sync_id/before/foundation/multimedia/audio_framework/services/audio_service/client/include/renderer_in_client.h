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
#ifndef RENDERER_IN_SERVER_H
#define RENDERER_IN_SERVER_H

#include "i_audio_stream.h"

namespace OHOS {
namespace AudioStandard {
class RendererInClient : public IAudioStream {
public:
    virtual ~RendererInClient() = default;
    static std::shared_ptr<RendererInClient> GetInstance(AudioStreamType eStreamType, int32_t appUid);
};
} // namespace AudioStandard
} // namespace OHOS
#endif // RENDERER_IN_SERVER_H
