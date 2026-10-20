/*
 * Copyright (C) 2021-2026 Huawei Device Co., Ltd.
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

#include "player_server.h"
#include <map>
#include <unistd.h>
#include <unordered_set>
#include <cmath>
#include <cinttypes>
#include "media_log.h"
#include "media_errors.h"
#include "engine_factory_repo.h"
#include "player_server_state.h"
#include "media_dfx.h"
#include "media_utils.h"
#include "ipc_skeleton.h"
#include "media_permission.h"
#include "accesstoken_kit.h"
#include "av_common.h"
#include "parameter.h"
#include "parameters.h"
#include "qos.h"
#include "player_server_event_receiver.h"
#include "common/media_source.h"
#include "audio_info.h"
#include "osal/utils/steady_clock.h"
#include "common/event.h"

using namespace OHOS::QOS;

namespace {
    constexpr OHOS::HiviewDFX::HiLogLabel LABEL = {LOG_CORE, LOG_DOMAIN_PLAYER, "PlayerServer"};
    constexpr int32_t MAX_SUBTITLE_TRACK_NUN = 8;
    constexpr int32_t MEMORY_USAGE_VERSION_ISOLATION = 20;
    static bool g_isFirstInit = true;
    const std::map<OHOS::Media::PlayerErrorType, std::string> ERROR_TYPE_INFOS = {
        {OHOS::Media::PlayerErrorType::PLAY_ERR, "PLAY_ERR-"},
        {OHOS::Media::PlayerErrorType::NET_ERR, "NET_ERR-"},
        {OHOS::Media::PlayerErrorType::CONTAINER_ERR, "CONTAINER_ERR-"},
        {OHOS::Media::PlayerErrorType::DEM_FMT_ERR, "DEM_FMT_ERR-"},
        {OHOS::Media::PlayerErrorType::DEM_PARSE_ERR, "DEM_PARSE_ERR-"},
        {OHOS::Media::PlayerErrorType::AUD_DEC_ERR, "AUD_DEC_ERR-"},
        {OHOS::Media::PlayerErrorType::VID_DEC_ERR, "VID_DEC_ERR-"},
        {OHOS::Media::PlayerErrorType::DRM_ERR, "DRM_ERR-"},
        {OHOS::Media::PlayerErrorType::AUD_OUTPUT_ERR, "AUD_OUTPUT_ERR-"},
        {OHOS::Media::PlayerErrorType::VPE_ERR, "VPE_ERR-"}
    };
}

namespace OHOS {
namespace Media {
using namespace OHOS::HiviewDFX;
using namespace OHOS::Media::Plugins;
const std::string START_TAG = "PlayerCreate->Start";
const std::string STOP_TAG = "PlayerStop->Destroy";
std::vector<std::string> PlayerServer::dolbyList_ = {};
static const std::unordered_map<int32_t, std::string> STATUS_TO_STATUS_DESCRIPTION_TABLE = {
    {PLAYER_STATE_ERROR, "PLAYER_STATE_ERROR"},
    {PLAYER_IDLE, "PLAYER_IDLE"},
    {PLAYER_INITIALIZED, "PLAYER_INITIALIZED"},
    {PLAYER_PREPARING, "PLAYER_PREPARING"},
    {PLAYER_PREPARED, "PLAYER_PREPARED"},
    {PLAYER_STARTED, "PLAYER_STARTED"},
    {PLAYER_PAUSED, "PLAYER_PAUSED"},
    {PLAYER_STOPPED, "PLAYER_STOPPED"},
    {PLAYER_PLAYBACK_COMPLETE, "PLAYER_PLAYBACK_COMPLETE"},
};
std::shared_ptr<IPlayerService> PlayerServer::Create()
{
    std::shared_ptr<PlayerServer> server = std::make_shared<PlayerServer>();
    CHECK_AND_RETURN_RET_LOG(server != nullptr, nullptr, "failed to new PlayerServer");
    (void)server->Init();
    return server;
}

PlayerServer::PlayerServer()
{
    MEDIA_LOGD("0x%{public}06" PRIXPTR " Instances create", FAKE_POINTER(this));
    instanceId_ = FAKE_POINTER(this);
}

PlayerServer::~PlayerServer()
{
    MEDIA_LOGD("0x%{public}06" PRIXPTR " Instances destroy", FAKE_POINTER(this));
}

int32_t PlayerServer::Init()
{
    MediaTrace trace("PlayerServer::Init");

    idleState_ = std::make_shared<IdleState>(*this);
    initializedState_ = std::make_shared<InitializedState>(*this);
    preparingState_ = std::make_shared<PreparingState>(*this);
    preparedState_ = std::make_shared<PreparedState>(*this);
    playingState_ = std::make_shared<PlayingState>(*this);
    pausedState_ = std::make_shared<PausedState>(*this);
    stoppedState_ = std::make_shared<StoppedState>(*this);
    playbackCompletedState_ = std::make_shared<PlaybackCompletedState>(*this);
    appTokenId_ = IPCSkeleton::GetCallingTokenID();
    appUid_ = IPCSkeleton::GetCallingUid();
    appPid_ = IPCSkeleton::GetCallingPid();
    appName_ = GetClientBundleName(appUid_);
    uint64_t tokenId = IPCSkeleton::GetCallingFullTokenID();
    isCalledBySystemApp_ = OHOS::Security::AccessToken::AccessTokenKit::IsSystemAppByFullTokenID(tokenId);
    if (g_isFirstInit) {
        MEDIA_LOGI("appUid: %{public}d, appPid: %{public}d, appName: %{public}s", appUid_, appPid_, appName_.c_str());
        g_isFirstInit = false;
    } else {
        MEDIA_LOGD("appUid: %{public}d, appPid: %{public}d, appName: %{public}s", appUid_, appPid_, appName_.c_str());
    }
    apiVersion_ = GetApiInfo(appUid_, appName_);

    PlayerServerStateMachine::Init(idleState_);
    MEDIA_LOGI("0x%{public}06" PRIXPTR " Instances create 0x%{public}06" PRIXPTR,
        FAKE_POINTER(this), FAKE_POINTER(GetCurrState().get()));

    std::string bootState = system::GetParameter("bootevent.boot.completed", "false");
    isBootCompleted_.store(bootState == "true");
    if (isBootCompleted_.load() && appUid_ != 0) {
        int32_t userId = -1;
        AccountSA::OsAccountManager::GetOsAccountLocalIdFromUid(appUid_, userId);
        userId_.store(userId);
        std::weak_ptr<PlayerServer> server = std::static_pointer_cast<PlayerServer>(shared_from_this());
        commonEventReceiver_ = std::make_shared<PlayerServerCommonEventReceiver>(server);
    }
    MEDIA_LOGI("0x%{public}06" PRIXPTR "Dump Info: lastOpStatus: %{public}s, lastErrMsg: %{public}s, "
        "speedMode: %{public}d, looping: %{public}s, effectMode: %{public}d, leftVolume: %{public}f, "
        "rightVolume: %{public}f", FAKE_POINTER(this), lastOpStatus_?"true":"false",
        lastErrMsg_.c_str(), config_.speedMode, config_.looping?"true":"false", config_.effectMode,
        config_.leftVolume, config_.rightVolume);
    return MSERR_OK;
}

int32_t PlayerServer::SetPlayerProducer(const PlayerProducer producer)
{
    std::lock_guard<std::mutex> lock(mutex_);
    MediaTrace trace("PlayerServer::SetPlayerProducer " + std::to_string(producer));
    playerProducer_ = producer;
    return MSERR_OK;
}

int32_t PlayerServer::SetSource(const std::string &url)
{
    std::lock_guard<std::mutex> lock(mutex_);
    MediaTrace trace("PlayerServer::SetSource url");
    CHECK_AND_RETURN_RET_LOG(!url.empty(), MSERR_INVALID_VAL, "url is empty");
    MEDIA_LOGW("0x%{public}06" PRIXPTR " KPI-TRACE: PlayerServer SetSource in(url)", FAKE_POINTER(this));
    if (url.find("http") != std::string::npos) {
        int32_t permissionResult = MediaPermission::CheckNetWorkPermission(appUid_, appPid_, appTokenId_);
        if (permissionResult != Security::AccessToken::PERMISSION_GRANTED) {
            MEDIA_LOGE("user do not have the right to access INTERNET");
            OnErrorMessage(MSERR_USER_NO_PERMISSION, "user do not have the right to access INTERNET");
            FaultSourceEventWrite(appName_, instanceId_, "player_framework",
                static_cast<int8_t>(SourceType::SOURCE_TYPE_URI), url, "user do not have the right to access INTERNET");
            return MSERR_INVALID_OPERATION;
        }
    }
    config_.url = url;
    int32_t ret = InitPlayEngine(url);
    if (ret != MSERR_OK) {
        FaultSourceEventWrite(appName_, instanceId_, "player_framework",
            static_cast<int8_t>(SourceType::SOURCE_TYPE_URI), url, "SetSource Failed!");
    }
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "SetSource Failed!");
    return ret;
}

int32_t PlayerServer::SetSource(const std::shared_ptr<IMediaDataSource> &dataSrc)
{
    std::lock_guard<std::mutex> lock(mutex_);
    MediaTrace trace("PlayerServer::SetSource dataSrc");
    CHECK_AND_RETURN_RET_LOG(dataSrc != nullptr, MSERR_INVALID_VAL, "data source is nullptr");
    MEDIA_LOGW("KPI-TRACE: PlayerServer SetSource in(dataSrc)");
    dataSrc_ = dataSrc;
    std::string url = "media data source";
    config_.url = url;
    int32_t ret = InitPlayEngine(url);
    if (ret != MSERR_OK) {
        FaultSourceEventWrite(appName_, instanceId_, "player_framework",
            static_cast<int8_t>(SourceType::SOURCE_TYPE_STREAM), url, "SetSource Failed!");
    }
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "InitPlayEngine Failed!");
    int64_t size = 0;
    (void)dataSrc_->GetSize(size);
    if (size == -1) {
        config_.looping = false;
        config_.speedMode = SPEED_FORWARD_1_00_X;
        isLiveStream_ = true;
    }
    return ret;
}

int32_t PlayerServer::SetSource(int32_t fd, int64_t offset, int64_t size)
{
    std::lock_guard<std::mutex> lock(mutex_);
    MediaTrace trace("PlayerServer::SetSource fd");
    MEDIA_LOGW("KPI-TRACE: PlayerServer SetSource in(fd), fd: %{public}d, offset: %{public}" PRId64
        ", size: %{public}" PRId64, fd, offset, size);
    int32_t ret;
    if (uriHelper_ != nullptr) {
        std::string uri = uriHelper_->FormattedUri();
        MEDIA_LOGI("UriHelper already existed, uri: %{private}s", uri.c_str());
        ret = InitPlayEngine(uri);
        if (ret != MSERR_OK) {
            FaultSourceEventWrite(appName_, instanceId_, "player_framework",
                static_cast<int8_t>(SourceType::SOURCE_TYPE_FD), uri, "SetSource Failed!");
        }
        CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "SetSource Failed!");
    } else {
        MEDIA_LOGI("UriHelper is nullptr, create a new instance.");
        auto uriHelper = std::make_unique<UriHelper>(fd, offset, size);
        CHECK_AND_RETURN_RET_LOG(uriHelper->AccessCheck(UriHelper::URI_READ),
            MSERR_INVALID_VAL, "Failed to read the fd");
        ret = InitPlayEngine(uriHelper->FormattedUri());
        if (ret != MSERR_OK) {
            FaultSourceEventWrite(appName_, instanceId_, "player_framework",
                static_cast<int8_t>(SourceType::SOURCE_TYPE_FD), uriHelper->FormattedUri(),  "SetSource Failed!");
        }
        CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "SetSource Failed!");
        uriHelper_ = std::move(uriHelper);
        CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_INVALID_VAL, "playerEngine_ is nullptr");
        playerEngine_->SetPerfRecEnabled(
            uriHelper_ != nullptr && uriHelper_->GetFdLocation() == FdLocation::LOCAL);
    }
    config_.url = "file descriptor source";

    return ret;
}

int32_t PlayerServer::InitPlayEngine(const std::string &url)
{
    MEDIA_LOGI("PlayEngine Init");
    CHECK_AND_RETURN_RET_LOG(lastOpStatus_ == PLAYER_IDLE, MSERR_INVALID_OPERATION,
        "current state is: %{public}s, not support SetSource", GetStatusDescription(lastOpStatus_).c_str());
    int32_t ret = taskMgr_.Init();
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "task mgr init failed");
    MEDIA_LOGI("current url is : %{private}s", url.c_str());
    auto engineFactory = EngineFactoryRepo::Instance().GetEngineFactory(
        IEngineFactory::Scene::SCENE_PLAYBACK, appUid_, url);
    CHECK_AND_RETURN_RET_LOG(engineFactory != nullptr, MSERR_CREATE_PLAYER_ENGINE_FAILED,
        "failed to get engine factory");
    playerEngine_ = engineFactory->CreatePlayerEngine(appUid_, appPid_, appTokenId_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_CREATE_PLAYER_ENGINE_FAILED,
        "failed to create player engine");
    SetParameter();
    MEDIA_LOGI("Setted InstanceId");
    if (dataSrc_ != nullptr) {
        ret = playerEngine_->SetSource(dataSrc_);
    } else if (mediaSource_ != nullptr) {
        if (mediaSource_->GetenableOfflineCache() && mediaSource_->sourceLoader_ == nullptr) {
            OnErrorCb(MSERR_INVALID_OPERATION, "Cannot set local cache and proxy download at the same time.");
            return MSERR_INVALID_OPERATION;
        }
        ret = playerEngine_->SetMediaSource(mediaSource_, strategy_);
    } else {
        ret = playerEngine_->SetSource(url);
    }
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "SetSource Failed! ret=%{public}d", ret);
    MEDIA_LOGI("player engine SetSource success");
    std::shared_ptr<IPlayerEngineObs> obs = shared_from_this();
    ret = playerEngine_->SetObs(obs);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "SetObs Failed!");
    ret = playerEngine_->SetMaxAmplitudeCbStatus(
        playerProducer_ == PlayerProducer::NAPI ? maxAmplitudeCbStatus_ : true);
    ret = playerEngine_->SetSeiMessageCbStatus(seiMessageCbStatus_, payloadTypes_);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "SetMaxAmplitudeCbStatus Failed!");
    ret = playerEngine_->EnableReportMediaProgress(
        playerProducer_ == PlayerProducer::NAPI ? enableReportMediaProgress_ : true);
    TRUE_LOG(ret != MSERR_OK, MEDIA_LOGW, "PlayerEngine enable report media progress failed, ret %{public}d", ret);
    InitPcmCallback();

    if (playerCb_ != nullptr) {
        playerCb_->SetInterruptListenerFlag(
            playerProducer_ == PlayerProducer::NAPI ? enableReportAudioInterrupt_ : true);
    }
    playerEngine_->ForceLoadVideo(isForceLoadVideo_);
    lastOpStatus_ = PLAYER_INITIALIZED;
    ChangeState(initializedState_);
    Format format;
    OnInfo(INFO_TYPE_STATE_CHANGE, PLAYER_INITIALIZED, format);
    return MSERR_OK;
}

void PlayerServer::SetParameter()
{
    playerEngine_->SetInstancdId(instanceId_);
    playerEngine_->SetApiVersion(apiVersion_.load());
    playerEngine_->SetIsCalledBySystemApp(isCalledBySystemApp_);
}

int32_t PlayerServer::AddSubSource(const std::string &url)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr!");

    if (subtitleTrackNum_ >= MAX_SUBTITLE_TRACK_NUN) {
        MEDIA_LOGE("Can not add sub source, subtitle track num is %{public}u, exceed the max num.", subtitleTrackNum_);
        return MSERR_INVALID_OPERATION;
    }

    MEDIA_LOGD("PlayerServer AddSubSource in(url).");
    MediaTrace::TraceBegin("PlayerServer::AddSubSource", FAKE_POINTER(this));
    (void)playerEngine_->AddSubSource(url);

    return MSERR_OK;
}

int32_t PlayerServer::AddSubSource(int32_t fd, int64_t offset, int64_t size)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");

    if (subtitleTrackNum_ >= MAX_SUBTITLE_TRACK_NUN) {
        MEDIA_LOGE("Can not add sub source, subtitle track num is %{public}u, exceed the max num", subtitleTrackNum_);
        return MSERR_INVALID_OPERATION;
    }

    auto uriHelper = std::make_shared<UriHelper>(fd, offset, size);
    CHECK_AND_RETURN_RET_LOG(uriHelper->AccessCheck(UriHelper::URI_READ), MSERR_INVALID_VAL, "Failed to read the fd");

    MEDIA_LOGD("PlayerServer AddSubSource in(fd)");
    MediaTrace::TraceBegin("PlayerServer::AddSubSource", FAKE_POINTER(this));
    (void)playerEngine_->AddSubSource(uriHelper->FormattedUri());
    subUriHelpers_.emplace_back(uriHelper);

    return MSERR_OK;
}

int32_t PlayerServer::SetStartFrameRateOptEnabled(bool enabled)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    auto startFrameRateOptTask = std::make_shared<TaskHandler<int32_t>>([this, enabled]() {
        MediaTrace trace("PlayerServer::SetStartFrameRateOptEnabled");
        CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, taskMgr_.MarkTaskDone("SetStartFrameRateOptEnabled done"),
            "SetStartFrameRateOptEnabled failed, playerEngine is nullptr");
        auto res = playerEngine_->SetStartFrameRateOptEnabled(enabled);
        taskMgr_.MarkTaskDone("SetStartFrameRateOptEnabled done");
        return res;
    });
    taskMgr_.LaunchTask(startFrameRateOptTask, PlayerServerTaskType::LIGHT_TASK, "SetStartFrameRateOptEnabled");
    return MSERR_OK;
}

int32_t PlayerServer::Prepare()
{
    if (inReleasing_.load()) {
        MEDIA_LOGE("Can not Prepare, now in releasing");
        return MSERR_INVALID_OPERATION;
    }
    std::lock_guard<std::mutex> lock(mutex_);
    MEDIA_LOGD("KPI-TRACE: PlayerServer Prepare in");

    if (lastOpStatus_ == PLAYER_INITIALIZED || lastOpStatus_ == PLAYER_STOPPED) {
        return OnPrepare(false);
    }
    MEDIA_LOGE("Can not Prepare, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
    return MSERR_INVALID_OPERATION;
}

int32_t PlayerServer::SetRenderFirstFrame(bool display)
{
    std::lock_guard<std::mutex> lock(mutex_);
    if (lastOpStatus_ != PLAYER_INITIALIZED) {
        MEDIA_LOGE("Can not SetRenderFirstFrame, currentState is not PLAYER_INITIALIZED");
        return MSERR_INVALID_OPERATION;
    }
    MEDIA_LOGD("PlayerServer SetRenderFirstFrame in, display %{public}d", display);

    if (isLiveStream_) {
        MEDIA_LOGE("Can not SetRenderFirstFrame, it is live-stream");
        return MSERR_OK;
    }

    if (playerEngine_ != nullptr) {
        int32_t ret = playerEngine_->SetRenderFirstFrame(display);
        CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "SetRenderFirstFrame Failed!");
    }
    return MSERR_OK;
}

int32_t PlayerServer::SetPlayRange(int64_t start, int64_t end)
{
    std::lock_guard<std::mutex> lock(mutex_);
    if (lastOpStatus_ != PLAYER_INITIALIZED
        && lastOpStatus_ != PLAYER_PAUSED
        && lastOpStatus_ != PLAYER_PLAYBACK_COMPLETE) {
        MEDIA_LOGE("Can not SetPlayRange, currentState is %{public}s",
            GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }

    if (isLiveStream_) {
        MEDIA_LOGE("Can not SetPlayRange, it is live-stream");
        return MSERR_OK;
    }

    if (playerEngine_ != nullptr) {
        int32_t ret = playerEngine_->SetPlayRange(start, end);
        CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "SetPlayRange Failed!");
    }
    return MSERR_OK;
}

int32_t PlayerServer::SetPlayRangeWithMode(int64_t start, int64_t end, PlayerSeekMode mode)
{
    std::lock_guard<std::mutex> lock(mutex_);
    if (lastOpStatus_ != PLAYER_INITIALIZED
        && lastOpStatus_ != PLAYER_PREPARED
        && lastOpStatus_ != PLAYER_PAUSED
        && lastOpStatus_ != PLAYER_STOPPED
        && lastOpStatus_ != PLAYER_PLAYBACK_COMPLETE) {
        MEDIA_LOGE("Can not SetPlayRangeWithMode, currentState is %{public}s",
            GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }
    if (isLiveStream_) {
        MEDIA_LOGE("Can not SetPlayRangeWithMode, it is live-stream");
        return MSERR_INVALID_OPERATION;
    }
    auto setPlayRangeTask = std::make_shared<TaskHandler<void>>([this, start, end, mode]() {
        MediaTrace::TraceBegin("PlayerServer::SetPlayRange", FAKE_POINTER(this));
        auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
        (void)currState->SetPlayRangeWithMode(start, end, mode);
    });
    int ret = taskMgr_.LaunchTask(setPlayRangeTask, PlayerServerTaskType::STATE_CHANGE, "set playRange");
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "SetPlayRangeWithMode failed");
    return MSERR_OK;
}

int32_t PlayerServer::HandleSetPlayRange(int64_t start, int64_t end, PlayerSeekMode mode)
{
    MEDIA_LOGI("KPI-TRACE: PlayerServer HandleSetPlayRange in");
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_INVALID_OPERATION, "playerEngine_ is nullptr");
    int32_t ret = playerEngine_->SetPlayRangeWithMode(start, end, mode);
    taskMgr_.MarkTaskDone("HandleSetPlayRange done");
    MediaTrace::TraceEnd("PlayerServer::SetPlayRange", FAKE_POINTER(this));
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine SetPlayRangeWithMode Failed!");
    return MSERR_OK;
}

int32_t PlayerServer::PrepareAsync()
{
    if (inReleasing_.load()) {
        MEDIA_LOGE("Can not Prepare, now in releasing");
        return MSERR_INVALID_OPERATION;
    }
    std::lock_guard<std::mutex> lock(mutex_);
    MEDIA_LOGD("KPI-TRACE: PlayerServer PrepareAsync in");

    if (lastOpStatus_ == PLAYER_INITIALIZED || lastOpStatus_ == PLAYER_STOPPED) {
        return OnPrepare(false);
    }
    MEDIA_LOGE("Can not Prepare, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
    return MSERR_INVALID_OPERATION;
}

int32_t PlayerServer::OnPrepare(bool sync)
{
    MEDIA_LOGD("KPI-TRACE: PlayerServer OnPrepare in");
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");

    int32_t ret = MSERR_OK;
    lastOpStatus_ = PLAYER_PREPARED;
    isInterruptNeeded_ = false;
    playerEngine_->SetInterruptState(false);
    auto preparedTask = std::make_shared<TaskHandler<int32_t>>([this]() {
        MediaTrace::TraceBegin("PlayerServer::PrepareAsync", FAKE_POINTER(this));
#ifdef SUPPORT_VIDEO
        {
            std::lock_guard<std::mutex> lock(surfaceMutex_);
            auto surface = weakSurface_.promote();
            if (surface != nullptr) {
                int32_t res = playerEngine_->SetVideoSurface(surface);
                CHECK_AND_RETURN_RET_LOG(res == MSERR_OK,
                    static_cast<int32_t>(MSERR_INVALID_OPERATION), "Engine SetVideoSurface Failed!");
            }
        }
        {
            std::lock_guard<std::mutex> lock(sideOutputSurfaceMutex_);
            if (sideOutputSurface_ != nullptr) {
                int32_t res = playerEngine_->SetVideoOutput(sideOutputSurface_);
                CHECK_AND_RETURN_RET_LOG(res == MSERR_OK,
                    static_cast<int32_t>(MSERR_INVALID_OPERATION), "Engine SetVideoOutput Failed!");
            }
        }
#endif
        auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
        return currState->Prepare();
    });

    ret = taskMgr_.LaunchTask(preparedTask, PlayerServerTaskType::STATE_CHANGE, "prepare");
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "Prepare launch task failed");

    if (sync) {
        (void)preparedTask->GetResult(); // wait HandlePrpare
    }
    MEDIA_LOGD("KPI-TRACE: PlayerServer OnPrepare out");
    return MSERR_OK;
}

int32_t PlayerServer::HandlePrepare()
{
    MEDIA_LOGI("KPI-TRACE: PlayerServer HandlePrepare in");
    if (config_.hasTrackSelectionFilter) {
        (void)playerEngine_->SetTrackSelectionFilter(config_.trackSelectionFilter_);
    }
    int32_t ret = playerEngine_->PrepareAsync();
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Server Prepare Failed!");
    CHECK_AND_RETURN_RET_LOG(!isInterruptNeeded_, MSERR_OK, "Cancel prepare");
    if (config_.leftVolume < 1.0f) {
        (void)playerEngine_->SetVolume(config_.leftVolume, config_.rightVolume);
    }
    if (config_.looping) {
        (void)playerEngine_->SetLooping(config_.looping);
    }
    if (config_.speedMode != SPEED_FORWARD_1_00_X) {
        MediaTrace::TraceBegin("PlayerServer::SetPlaybackSpeed", FAKE_POINTER(this));
        auto rateTask = std::make_shared<TaskHandler<void>>([this]() {
            int ret = playerEngine_->SetPlaybackSpeed(config_.speedMode);
            CHECK_AND_RETURN_LOG(ret == MSERR_OK, "Engine SetPlaybackSpeed Failed!");
        });
        auto cancelTask = std::make_shared<TaskHandler<void>>([this]() {
            MEDIA_LOGI("Interrupted speed action");
            taskMgr_.MarkTaskDone("interrupted speed done");
        });

        (void)taskMgr_.SpeedTask(rateTask, cancelTask, "prepare-speed", config_.speedMode);
    }

    if (config_.effectMode != OHOS::AudioStandard::AudioEffectMode::EFFECT_DEFAULT) {
        MediaTrace::TraceBegin("PlayerServer::SetAudioEffectMode", FAKE_POINTER(this));
        auto effectTask = std::make_shared<TaskHandler<void>>([this]() {
            int ret = playerEngine_->SetAudioEffectMode(config_.effectMode);
            taskMgr_.MarkTaskDone("SetAudioEffectMode done");
            CHECK_AND_RETURN_LOG(ret == MSERR_OK, "Engine SetAudioEffectMode Failed!");
        });
        (void)taskMgr_.LaunchTask(effectTask, PlayerServerTaskType::STATE_CHANGE, "SetAudioEffectMode", nullptr);
    }
    
    return MSERR_OK;
}

int32_t PlayerServer::Play()
{
    std::lock_guard<std::mutex> lock(mutex_);
    MEDIA_LOGD("PlayerServer Play in");
    if (lastOpStatus_ == PLAYER_PREPARED || lastOpStatus_ == PLAYER_PLAYBACK_COMPLETE ||
        lastOpStatus_ == PLAYER_PAUSED) {
        return OnPlay();
    }
    if (lastOpStatus_ == PLAYER_STARTED && isInSeekContinous_.load()) {
        return ExitSeekContinousAsync(true);
    }
    MEDIA_LOGE("Can not Play, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
    return MSERR_INVALID_OPERATION;
}

int32_t PlayerServer::OnPlay()
{
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    if (lastOpStatus_ == PLAYER_PLAYBACK_COMPLETE && dataSrc_ != nullptr) {
        int64_t size = 0;
        (void)dataSrc_->GetSize(size);
        if (size == -1) {
            MEDIA_LOGE("Can not play in complete status, it is live-stream");
            OnErrorMessage(MSERR_EXT_API9_UNSUPPORT_CAPABILITY, "Can not play in complete status, it is live-stream");
            return MSERR_INVALID_OPERATION;
        }
    }

    auto playingTask = std::make_shared<TaskHandler<void>>([this]() {
        MediaTrace::TraceBegin("PlayerServer::Play", FAKE_POINTER(this));
        auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
        (void)currState->Play();
    });
    MEDIA_LOGD("PlayerServer OnPlay in");
    int ret = taskMgr_.LaunchTask(playingTask, PlayerServerTaskType::STATE_CHANGE, "play");
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "Play failed");

    lastOpStatus_ = PLAYER_STARTED;
    return MSERR_OK;
}

int32_t PlayerServer::HandlePlay()
{
    ExitSeekContinous(true);
    TryFlvLiveRestartLink();
    int32_t ret = playerEngine_->Play();
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine Play Failed!");

    return MSERR_OK;
}

int32_t PlayerServer::BackGroundChangeState(PlayerStates state, bool isBackGroundCb)
{
    backgroundState_ = state;
    MEDIA_LOGI("PlayerServer::BackGroundChangeState is called");
    isBackgroundCb_ = isBackGroundCb;
    if (state == PLAYER_PAUSED) {
        isBackgroundChanged_ = true;
        return PlayerServer::Pause();
    }
    if (state == PLAYER_STARTED) {
        isBackgroundChanged_ = true;
        return PlayerServer::Play();
    }
    return MSERR_INVALID_OPERATION;
}

int32_t PlayerServer::Pause()
{
    std::lock_guard<std::mutex> lock(mutex_);
    MEDIA_LOGI("0x%{public}06" PRIXPTR " PlayerServer Pause in", FAKE_POINTER(this));
    if (lastOpStatus_ == PLAYER_PAUSED) {
        MEDIA_LOGE("Can not Pause, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_OK;
    }
    if (lastOpStatus_ != PLAYER_STARTED) {
        MEDIA_LOGE("Can not Pause, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }
    return OnPause(false);
}

int32_t PlayerServer::OnPause(bool isSystemOperation)
{
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    MEDIA_LOGI("0x%{public}06" PRIXPTR " PlayerServer OnPause in", FAKE_POINTER(this));

    auto pauseTask = std::make_shared<TaskHandler<void>>([this, isSystemOperation]() {
        MediaTrace::TraceBegin("PlayerServer::Pause", FAKE_POINTER(this));
        auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
        (void)currState->Pause(isSystemOperation);
    });

    int ret = taskMgr_.LaunchTask(pauseTask, PlayerServerTaskType::STATE_CHANGE, "pause");
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "Pause failed");

    lastOpStatus_ = PLAYER_PAUSED;
    return MSERR_OK;
}

int32_t PlayerServer::HandlePause(bool isSystemOperation)
{
    MEDIA_LOGI("KPI-TRACE: PlayerServer HandlePause in");
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_INVALID_OPERATION, "playerEngine_ is nullptr");
    ExitSeekContinous(true);
    int32_t ret = playerEngine_->Pause(isSystemOperation);
    UpdateFlvLivePauseTime();
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine Pause Failed!");

    return MSERR_OK;
}

int32_t PlayerServer::Freeze()
{
    std::lock_guard<std::mutex> lock(mutex_);
    if (lastOpStatus_ != PLAYER_STARTED) {
        MEDIA_LOGE("Can not Freeze, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_OK;
    }
    if (playerCb_ != nullptr) {
        playerCb_->SetFreezeFlag(true);
    }
    auto ret = OnFreeze();
    isFrozen_ = ret == MSERR_OK;
    return ret;
}

int32_t PlayerServer::OnFreeze()
{
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    MEDIA_LOGI("0x%{public}06" PRIXPTR " PlayerServer OnFreeze in", FAKE_POINTER(this));
    auto freezeTask = std::make_shared<TaskHandler<void>>([this]() {
        MediaTrace Trace("PlayerServer::Freeze");
        MEDIA_LOGI("PlayerServer::OnFreeze start");
        auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
        (void)currState->Freeze();
        MEDIA_LOGI("PlayerServer::OnFreeze end");
    });

    auto cancelTask = std::make_shared<TaskHandler<void>>([this]() {
        MEDIA_LOGI("cancel OnFreeze");
        taskMgr_.MarkTaskDone("interrupted OnFreeze done");
    });

    int ret = taskMgr_.FreezeTask(freezeTask, cancelTask, "Freeze");
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "Freeze failed");

    return MSERR_OK;
}

int32_t PlayerServer::HandleFreeze()
{
    MEDIA_LOGI("PlayerServer HandleFreeze in");
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_INVALID_OPERATION, "playerEngine_ is nullptr");
    ExitSeekContinous(true);
    bool isNoNeedToFreeze = false;
    int32_t ret = playerEngine_->Freeze(isNoNeedToFreeze);
    UpdateFlvLivePauseTime();
    if (ret != MSERR_OK) {
        MEDIA_LOGI("Engine Freeze Failed!");
        taskMgr_.MarkTaskDone("Freeze done");
        return MSERR_INVALID_OPERATION;
    }
    if (isNoNeedToFreeze) {
        CHECK_AND_RETURN_RET_NOLOG(playerCb_ != nullptr, MSERR_OK);
        playerCb_->SetFreezeFlag(false);
        taskMgr_.MarkTaskDone("Freeze done");
        return MSERR_OK;
    }
    ret = HandleLiteFreeze();
    MEDIA_LOGI("HandleLiteFreeze ret is %{public}d", ret);
    taskMgr_.MarkTaskDone("Freeze done");
    return ret;
}

int32_t PlayerServer::HandleLiteFreeze()
{
    CHECK_AND_RETURN_RET_NOLOG(!isMemoryExchanged_, MSERR_OK);
    auto ret = playerEngine_->NotifyMemoryExchange(true);
    isMemoryExchanged_ = true;
    return ret;
}

int32_t PlayerServer::UnFreeze()
{
    std::lock_guard<std::mutex> lock(mutex_);
    if (playerCb_ != nullptr) {
        playerCb_->SetFreezeFlag(false);
    }
    if (!isFrozen_) {
        MEDIA_LOGE("Can not UnFreeze, is not FrozenState");
        return MSERR_OK;
    }
    auto ret = OnUnFreeze();
    isFrozen_ = ret != MSERR_OK;
    return ret;
}

int32_t PlayerServer::OnUnFreeze()
{
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    MEDIA_LOGI("0x%{public}06" PRIXPTR " PlayerServer OnUnFreeze in", FAKE_POINTER(this));
    auto unFreezeTask = std::make_shared<TaskHandler<void>>([this]() {
        MediaTrace Trace("PlayerServer::UnFreeze");
        MEDIA_LOGI("PlayerServer::OnUnFreeze start");
        auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
        (void)currState->UnFreeze();
        MEDIA_LOGI("PlayerServer::OnUnFreeze end");
    });

    auto cancelTask = std::make_shared<TaskHandler<void>>([this]() {
        MEDIA_LOGI("cancel OnUnFreeze");
        taskMgr_.MarkTaskDone("cancel OnUnFreeze done");
    });

    int ret = taskMgr_.UnFreezeTask(unFreezeTask, cancelTask, "UnFreeze");
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "UnFreeze failed");

    return MSERR_OK;
}

int32_t PlayerServer::HandleUnFreeze()
{
    MEDIA_LOGI("PlayerServer HandleUnFreeze in");
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_INVALID_OPERATION, "playerEngine_ is nullptr");
    (void)HandleLiteUnFreeze();
    ExitSeekContinous(true);
    playerEngine_->ResumeSourceDownload();
    if (playerEngine_->IsFlvLive()) {
        HandleFlvLiveRestartLink();
    }
    int32_t ret = playerEngine_->UnFreeze();
    taskMgr_.MarkTaskDone("UnFreeze done");
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine UnFreeze Failed!");

    return MSERR_OK;
}

int32_t PlayerServer::HandleLiteUnFreeze()
{
    CHECK_AND_RETURN_RET_NOLOG(isMemoryExchanged_, MSERR_OK);
    auto ret = playerEngine_->NotifyMemoryExchange(false);
    isMemoryExchanged_ = false;
    return ret;
}

int32_t PlayerServer::HandlePauseDemuxer()
{
    MEDIA_LOGI("KPI-TRACE: PlayerServer HandlePauseDemuxer in");
    MediaTrace::TraceBegin("PlayerServer::HandlePauseDemuxer", FAKE_POINTER(this));
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_INVALID_OPERATION, "playerEngine_ is nullptr");
    int32_t ret = playerEngine_->PauseDemuxer();
    taskMgr_.MarkTaskDone("PauseDemuxer done");
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine PauseDemuxer Failed!");
    return MSERR_OK;
}

int32_t PlayerServer::HandleResumeDemuxer()
{
    MEDIA_LOGI("KPI-TRACE: PlayerServer HandleResumeDemuxer in");
    MediaTrace::TraceBegin("PlayerServer::HandleResumeDemuxer", FAKE_POINTER(this));
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_INVALID_OPERATION, "playerEngine_ is nullptr");
    TryFlvLiveRestartLink();
    int32_t ret = playerEngine_->ResumeDemuxer();
    taskMgr_.MarkTaskDone("ResumeDemuxer done");
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine ResumeDemuxer Failed!");
    return MSERR_OK;
}

int32_t PlayerServer::Stop()
{
    std::lock_guard<std::mutex> lock(mutex_);

    if (lastOpStatus_ == PLAYER_PREPARED || lastOpStatus_ == PLAYER_STARTED ||
        lastOpStatus_ == PLAYER_PLAYBACK_COMPLETE || lastOpStatus_ == PLAYER_PAUSED) {
        MediaTrace::TraceBegin("PlayerServer::Stop", FAKE_POINTER(this));
        disableStoppedCb_ = false;
        return OnStop(false);
    }
    MEDIA_LOGE("Can not Stop, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
    return MSERR_INVALID_OPERATION;
}

int32_t PlayerServer::OnStop(bool sync)
{
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    isInterruptNeeded_ = true;
    playerEngine_->SetInterruptState(true);
    taskMgr_.ClearAllTask();
    auto stopTask = std::make_shared<TaskHandler<void>>([this]() {
        auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
        (void)currState->Stop();
    });

    (void)taskMgr_.LaunchTask(stopTask, PlayerServerTaskType::STATE_CHANGE, "stop");
    if (sync) {
        (void)stopTask->GetResult(); // wait HandleStop
    }
    lastOpStatus_ = PLAYER_STOPPED;
    MEDIA_LOGD("PlayerServer OnStop out");
    return MSERR_OK;
}

int32_t PlayerServer::HandleStop()
{
    ExitSeekContinous(false);
    int32_t ret = playerEngine_->Stop();
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine Stop Failed!");

    return MSERR_OK;
}

int32_t PlayerServer::Reset()
{
    std::lock_guard<std::mutex> lock(mutex_);
    MediaTrace trace("PlayerServer::Reset");
    if (lastOpStatus_ == PLAYER_IDLE) {
        MEDIA_LOGE("Can not Reset, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }
    return OnReset();
}

int32_t PlayerServer::OnReset()
{
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    disableStoppedCb_ = true;
    if (lastOpStatus_ == PLAYER_PREPARED || lastOpStatus_ == PLAYER_STARTED ||
        lastOpStatus_ == PLAYER_PLAYBACK_COMPLETE || lastOpStatus_ == PLAYER_PAUSED) {
        (void)OnStop(true);
    } else if (lastOpStatus_ == PLAYER_STATE_ERROR && playerEngine_ != nullptr) {
        isInterruptNeeded_ = true;
        MEDIA_LOGW("error state interrupt");
        playerEngine_->SetInterruptState(true);
    }

    MEDIA_LOGD("PlayerServer OnReset in");
    taskMgr_.ClearAllTask();
    auto idleTask = std::make_shared<TaskHandler<void>>([this]() {
        ChangeState(idleState_);
    });
    (void)taskMgr_.LaunchTask(idleTask, PlayerServerTaskType::STATE_CHANGE, "reset");
    (void)idleTask->GetResult();
    (void)taskMgr_.Reset();
    lastOpStatus_ = PLAYER_IDLE;
    isLiveStream_ = false;
    subtitleTrackNum_ = 0;
    isStreamUsagePauseRequired_ = true;

    return MSERR_OK;
}

int32_t PlayerServer::HandleReset()
{
    (void)playerEngine_->Reset();
    std::thread([playerEngine = std::move(playerEngine_), uriHelper = std::move(uriHelper_)]() mutable -> void {
        MEDIA_LOGI("HandleReset: create new thread");
        std::unique_ptr<UriHelper> helper = std::move(uriHelper);
        std::unique_ptr<IPlayerEngine> engine = std::move(playerEngine);
        MEDIA_LOGI("HandleReset: thread finished");
    }).detach();
    dataSrc_ = nullptr;
    config_.looping = false;
    uriHelper_ = nullptr;
    mediaSource_ = nullptr;
    {
        decltype(subUriHelpers_) temp;
        temp.swap(subUriHelpers_);
    }
    lastErrMsg_.clear();
    errorCbOnce_ = false;
    disableNextSeekDone_ = false;
    totalMemoryUage_ = 0;
    isVideoOutputEnabled_.store(false);
    isSuperResolutionEnabled_.store(false);
    isCameraPostprocessingEnabled_.store(false);
    Format format;
    OnInfo(INFO_TYPE_STATE_CHANGE, PLAYER_IDLE, format);
    return MSERR_OK;
}

int32_t PlayerServer::Release()
{
    std::lock_guard<std::mutex> lock(mutex_);
    MediaTrace trace("PlayerServer::Release");
    inReleasing_ = true;
    {
        std::lock_guard<std::mutex> lockCb(mutexCb_);
        playerCb_ = nullptr;
    }
    MEDIA_LOGD("PlayerServer Release in");
    if (lastOpStatus_ != PLAYER_IDLE) {
        (void)OnReset();
    }
    ReportMediaInfo(instanceId_);
    GetMediaInfoContainInstanceNum();
#ifdef SUPPORT_VIDEO
    auto surface = weakSurface_.promote();
    if (surface != nullptr) {
        surface_ = nullptr;
    }
#endif
    return MSERR_OK;
}

int32_t PlayerServer::SetVolumeMode(int32_t mode)
{
    std::lock_guard<std::mutex> lock(mutex_);
    if (lastOpStatus_ == PLAYER_STATE_ERROR) {
        MEDIA_LOGE("Can not SetVolume, currentState is PLAYER_STATE_ERROR");
        return MSERR_INVALID_OPERATION;
    }
    MEDIA_LOGD("PlayerServer SetVolumeMode in mode %{public}d", mode);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    (void)playerEngine_->SetVolumeMode(mode);
    return MSERR_OK;
}

int32_t PlayerServer::SetVolume(float leftVolume, float rightVolume)
{
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (lastOpStatus_ == PLAYER_STATE_ERROR) {
            MEDIA_LOGE("Can not SetVolume, currentState is PLAYER_STATE_ERROR");
            return MSERR_INVALID_OPERATION;
        }
        MEDIA_LOGD("PlayerServer SetVolume in leftVolume %{public}f %{public}f", leftVolume, rightVolume);
        constexpr float maxVolume = 1.0f;
        if ((leftVolume < 0) || (leftVolume > maxVolume) || (rightVolume < 0) || (rightVolume > maxVolume)) {
            MEDIA_LOGE("SetVolume failed, the volume should be set to a value ranging from 0 to 5");
            return MSERR_INVALID_OPERATION;
        }

        config_.leftVolume = leftVolume;
        config_.rightVolume = rightVolume;
        if (IsEngineStarted()) {
            auto task = std::make_shared<TaskHandler<void>>([this]() {
                (void)playerEngine_->SetVolume(config_.leftVolume, config_.rightVolume);
                taskMgr_.MarkTaskDone("volume done");
            });
            (void)taskMgr_.LaunchTask(task, PlayerServerTaskType::STATE_CHANGE, "volume");
        } else {
            MEDIA_LOGI("Waiting for the engine state is <prepared> to take effect");
        }
    }

    Format format;
    (void)format.PutFloatValue(PlayerKeys::PLAYER_VOLUME_LEVEL, leftVolume);
    MEDIA_LOGI("SetVolume callback");
    OnInfoNoChangeStatus(INFO_TYPE_VOLUME_CHANGE, 0, format);
    return MSERR_OK;
}

bool PlayerServer::IsEngineStarted()
{
    if (playerEngine_ != nullptr) {
        if (GetCurrState() == preparedState_ || GetCurrState() == playingState_ ||
            GetCurrState() == pausedState_ || GetCurrState() == playbackCompletedState_) {
            return true;
        }
    }
    return false;
}

bool PlayerServer::IsValidSeekMode(PlayerSeekMode mode)
{
    switch (mode) {
        case SEEK_PREVIOUS_SYNC:
        case SEEK_NEXT_SYNC:
        case SEEK_CLOSEST_SYNC:
        case SEEK_CLOSEST:
        case SEEK_CONTINOUS:
            break;
        default:
            MEDIA_LOGE("Unknown seek mode %{public}d", mode);
            return false;
    }
    return true;
}

int32_t PlayerServer::Seek(int64_t mSeconds, PlayerSeekMode mode)
{
    std::lock_guard<std::mutex> lock(mutex_);
    int32_t checkRet = CheckSeek(mSeconds, mode);
    CHECK_AND_RETURN_RET_LOG(checkRet == MSERR_OK, checkRet, "check seek faild");

    MEDIA_LOGD("seek position %{public}" PRId64 ", seek mode is %{public}d", mSeconds, mode);
    if (mode == SEEK_CONTINOUS) {
        return SeekContinous(mSeconds);
    }
    mSeconds = std::max(int64_t {0}, mSeconds);
    auto seekTask = std::make_shared<TaskHandler<void>>([this, mSeconds, mode]() {
        MediaTrace::TraceBegin("PlayerServer::Seek", FAKE_POINTER(this));
        MEDIA_LOGI("PlayerServer::Seek start");
        auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
        (void)currState->Seek(mSeconds, mode);
        MEDIA_LOGI("PlayerServer::Seek end");
    });

    auto cancelTask = std::make_shared<TaskHandler<void>>([this, mSeconds]() {
        MEDIA_LOGI("Interrupted seek action");
        Format format;
        OnInfoNoChangeStatus(INFO_TYPE_SEEKDONE, mSeconds, format);
        taskMgr_.MarkTaskDone("interrupted seek done");
    });

    int32_t ret = taskMgr_.SeekTask(seekTask, cancelTask, "seek", mode, mSeconds);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "Seek failed");

    MEDIA_LOGI("Queue seekTask end, position %{public}" PRId64 ", seek mode is %{public}d", mSeconds, mode);
    return MSERR_OK;
}

int32_t PlayerServer::SeekToDefaultPosition()
{
    std::lock_guard<std::mutex> lock(mutex_);
    MEDIA_LOGI("PlayerServer SeekToDefaultPosition in");

    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    int32_t ret = playerEngine_->SeekToDefaultPosition();
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine SeekToDefaultPosition Failed!");

    MEDIA_LOGI("PlayerServer SeekToDefaultPosition end");
    return MSERR_OK;
}

int32_t PlayerServer::HandleSeek(int64_t mSeconds, PlayerSeekMode mode)
{
    MEDIA_LOGI("KPI-TRACE: PlayerServer HandleSeek in, mSeconds: %{public}" PRId64 ", mode: %{public}d", mSeconds, mode);
    ExitSeekContinous(false);
    int32_t ret = playerEngine_->Seek(mSeconds, mode);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine Seek Failed!");
    MEDIA_LOGD("PlayerServer HandleSeek end");
    return MSERR_OK;
}

int32_t PlayerServer::GetCurrentTime(int32_t &currentTime)
{
    // delete lock, cannot be called concurrently with Reset or Release
    currentTime = -1;
    if (lastOpStatus_ == PLAYER_IDLE || lastOpStatus_ == PLAYER_STATE_ERROR) {
        MEDIA_LOGE("Can not GetCurrentTime, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }
    if (isLiveStream_ && dataSrc_ == nullptr) {
        MEDIA_LOGD("It is live-stream");
        return MSERR_OK;
    }

    MEDIA_LOGD("PlayerServer GetCurrentTime in, currentState is %{public}s",
        GetStatusDescription(lastOpStatus_).c_str());
    if (lastOpStatus_ != PLAYER_PREPARED && lastOpStatus_ != PLAYER_STARTED && lastOpStatus_ != PLAYER_PAUSED &&
        lastOpStatus_ != PLAYER_PLAYBACK_COMPLETE) {
        currentTime = 0;
        MEDIA_LOGD("get position at state: %{public}s, return 0", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_OK;
    }

    if (playerEngine_ != nullptr) {
        int32_t ret = playerEngine_->GetCurrentTime(currentTime);
        CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine GetCurrentTime Failed!");
    }
    return MSERR_OK;
}

int32_t PlayerServer::GetPlaybackPosition(int32_t &playbackPosition)
{
    // delete lock, cannot be called concurrently with Reset or Release
    if (lastOpStatus_ == PLAYER_IDLE || lastOpStatus_ == PLAYER_STATE_ERROR) {
        MEDIA_LOGE("Can not GetPlaybackPosition, currentState is %{public}s",
            GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }

    MEDIA_LOGD("PlayerServer GetPlaybackPosition in, currentState is %{public}s",
        GetStatusDescription(lastOpStatus_).c_str());
    if (lastOpStatus_ != PLAYER_PREPARED && lastOpStatus_ != PLAYER_STARTED && lastOpStatus_ != PLAYER_PAUSED &&
        lastOpStatus_ != PLAYER_PLAYBACK_COMPLETE) {
        playbackPosition = 0;
        MEDIA_LOGD("get position at state: %{public}s, return 0", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_OK;
    }

    if (playerEngine_ != nullptr) {
        int32_t ret = playerEngine_->GetPlaybackPosition(playbackPosition);
        CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine GetPlaybackPosition Failed!");
    }
    return MSERR_OK;
}

int32_t PlayerServer::GetCurrentPresentationTimestamp(int64_t &currentPresentation)
{
    if (lastOpStatus_ == PLAYER_IDLE || lastOpStatus_ == PLAYER_STATE_ERROR) {
        MEDIA_LOGE("Can not GetCurrentPresentationTimestamp, currentState is %{public}s",
            GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }

    MEDIA_LOGD("PlayerServer GetCurrentPresentationTimestamp in, currentState is %{public}s",
        GetStatusDescription(lastOpStatus_).c_str());
    if (lastOpStatus_ != PLAYER_STARTED && lastOpStatus_ != PLAYER_PAUSED &&
        lastOpStatus_ != PLAYER_PLAYBACK_COMPLETE) {
        currentPresentation = 0;
        MEDIA_LOGD("get position at state: %{public}s, return 0", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_OK;
    }

    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    int32_t ret = playerEngine_->GetCurrentPresentationTimestamp(currentPresentation);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION,
        "Engine GetCurrentPresentationTimestamp Failed!");
    return MSERR_OK;
}

int32_t PlayerServer::GetVideoTrackInfo(std::vector<Format> &videoTrack)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");

    if (lastOpStatus_ != PLAYER_PREPARED && lastOpStatus_ != PLAYER_PAUSED &&
        lastOpStatus_ != PLAYER_STARTED && lastOpStatus_ != PLAYER_PLAYBACK_COMPLETE) {
        MEDIA_LOGE("Can not get track info, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }
    MEDIA_LOGD("PlayerServer GetVideoTrackInfo in");
    int32_t ret = playerEngine_->GetVideoTrackInfo(videoTrack);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine GetVideoTrackInfo Failed!");
    return MSERR_OK;
}

int32_t PlayerServer::GetPlaybackInfo(Format &playbackInfo)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");

    if (lastOpStatus_ != PLAYER_PREPARED && lastOpStatus_ != PLAYER_PAUSED &&
        lastOpStatus_ != PLAYER_STARTED && lastOpStatus_ != PLAYER_PLAYBACK_COMPLETE) {
        MEDIA_LOGE("Can not get track info, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }
    MEDIA_LOGD("PlayerServer GetPlaybackInfo in");
    int32_t ret = playerEngine_->GetPlaybackInfo(playbackInfo);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine GetPlaybackInfo Failed!");
    return MSERR_OK;
}

int32_t PlayerServer::GetPlaybackStatisticMetrics(Format &playbackStatisticMetrics)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");

    if (lastOpStatus_ != PLAYER_PREPARED && lastOpStatus_ != PLAYER_PAUSED && lastOpStatus_ != PLAYER_STARTED &&
        lastOpStatus_ != PLAYER_PLAYBACK_COMPLETE && lastOpStatus_ != PLAYER_STOPPED) {
        MEDIA_LOGE("Can not get playback statistic metrics, currentState is %{public}s",
            GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }
    MEDIA_LOGD("PlayerServer GetPlaybackStatisticMetrics in");
    int32_t ret = playerEngine_->GetPlaybackStatisticMetrics(playbackStatisticMetrics);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine GetPlaybackStatisticMetrics Failed!");
    return MSERR_OK;
}

int32_t PlayerServer::GetAudioTrackInfo(std::vector<Format> &audioTrack)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");

    if (lastOpStatus_ != PLAYER_PREPARED && lastOpStatus_ != PLAYER_PAUSED &&
        lastOpStatus_ != PLAYER_STARTED && lastOpStatus_ != PLAYER_PLAYBACK_COMPLETE) {
        MEDIA_LOGE("Can not get track info, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }
    MEDIA_LOGD("PlayerServer GetAudioTrackInfo in");
    int32_t ret = playerEngine_->GetAudioTrackInfo(audioTrack);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine GetAudioTrackInfo Failed!");
    return MSERR_OK;
}

int32_t PlayerServer::GetSubtitleTrackInfo(std::vector<Format> &subtitleTrack)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");

    if (lastOpStatus_ != PLAYER_PREPARED && lastOpStatus_ != PLAYER_PAUSED &&
        lastOpStatus_ != PLAYER_STARTED && lastOpStatus_ != PLAYER_PLAYBACK_COMPLETE) {
        MEDIA_LOGE("Can not get track info, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }
    MEDIA_LOGD("PlayerServer GetSubtitleTrackInfo in");
    int32_t ret = playerEngine_->GetSubtitleTrackInfo(subtitleTrack);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine GetSubtitleTrackInfo Failed!");
    return MSERR_OK;
}

int32_t PlayerServer::GetVideoWidth()
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");

    if (lastOpStatus_ != PLAYER_PREPARED && lastOpStatus_ != PLAYER_PAUSED &&
        lastOpStatus_ != PLAYER_STARTED && lastOpStatus_ != PLAYER_STOPPED &&
        lastOpStatus_ != PLAYER_PLAYBACK_COMPLETE) {
        MEDIA_LOGE("Can not get track info, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }
    MEDIA_LOGD("PlayerServer GetVideoWidth in");
    return playerEngine_->GetVideoWidth();
}

int32_t PlayerServer::GetVideoHeight()
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");

    if (lastOpStatus_ != PLAYER_PREPARED && lastOpStatus_ != PLAYER_PAUSED &&
        lastOpStatus_ != PLAYER_STARTED && lastOpStatus_ != PLAYER_STOPPED &&
        lastOpStatus_ != PLAYER_PLAYBACK_COMPLETE) {
        MEDIA_LOGE("Can not get track info, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }
    MEDIA_LOGD("PlayerServer GetVideoHeight in");
    return playerEngine_->GetVideoHeight();
}

int32_t PlayerServer::GetDuration(int32_t &duration)
{
    // delete lock, cannot be called concurrently with Reset or Release
    if (lastOpStatus_ == PLAYER_IDLE || lastOpStatus_ == PLAYER_INITIALIZED || lastOpStatus_ == PLAYER_STATE_ERROR) {
        MEDIA_LOGE("Can not GetDuration, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }

    MEDIA_LOGD("PlayerServer GetDuration in");
    duration = -1;
    if (playerEngine_ != nullptr) {
        int ret = playerEngine_->GetDuration(duration);
        CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine GetDuration Failed!");
    }
    MEDIA_LOGD("PlayerServer GetDuration %{public}d", duration);
    return MSERR_OK;
}

int32_t PlayerServer::GetSeekableRanges(std::vector<Plugins::SeekRange> &seekableRanges)
{
    // delete lock, cannot be called concurrently with Reset or Release
    if (lastOpStatus_ == PLAYER_IDLE || lastOpStatus_ == PLAYER_INITIALIZED || lastOpStatus_ == PLAYER_STATE_ERROR) {
        MEDIA_LOGE("Can not GetSeekableRanges, currentState is %{public}s",
            GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }

    MEDIA_LOGD("PlayerServer GetSeekableRanges in");
    seekableRanges.clear();
    if (playerEngine_ != nullptr) {
        seekableRanges = playerEngine_->GetSeekableRanges();
    }
    MEDIA_LOGD("PlayerServer GetSeekableRanges size %{public}zu", seekableRanges.size());
    return MSERR_OK;
}

int32_t PlayerServer::GetLoadedRanges(std::vector<Plugins::SeekRange> &loadedRanges)
{
    // delete lock, cannot be called concurrently with Reset or Release
    if (lastOpStatus_ == PLAYER_IDLE || lastOpStatus_ == PLAYER_INITIALIZED || lastOpStatus_ == PLAYER_STATE_ERROR) {
        MEDIA_LOGE("Can not GetLoadedRanges, currentState is %{public}s",
            GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }

    MEDIA_LOGD("PlayerServer GetLoadedRanges in");
    loadedRanges.clear();
    if (playerEngine_ != nullptr) {
        loadedRanges = playerEngine_->GetLoadedRanges();
    }
    MEDIA_LOGD("PlayerServer GetLoadedRanges size %{public}zu", loadedRanges.size());
    return MSERR_OK;
}

int32_t PlayerServer::GetApiVersion(int32_t &apiVersion)
{
    apiVersion = apiVersion_.load();
    MEDIA_LOGD("PlayerServer GetApiVersion %{public}d", apiVersion);
    return MSERR_OK;
}

void PlayerServer::ClearConfigInfo()
{
    std::lock_guard<std::mutex> lock(mutex_);

    config_.looping = false;
    config_.leftVolume = INVALID_VALUE;
    config_.rightVolume = INVALID_VALUE;
    config_.speedMode = SPEED_FORWARD_1_00_X;
    config_.url = "";
}

int32_t PlayerServer::SetPlaybackSpeed(PlaybackRateMode mode)
{
    std::lock_guard<std::mutex> lock(mutex_);

    if ((lastOpStatus_ != PLAYER_STARTED) && (lastOpStatus_ != PLAYER_PREPARED) &&
        (lastOpStatus_ != PLAYER_PAUSED) && (lastOpStatus_ != PLAYER_PLAYBACK_COMPLETE)) {
        MEDIA_LOGE("Can not SetPlaybackSpeed, currentState is %{public}s",
            GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }
    MEDIA_LOGD("PlayerServer SetPlaybackSpeed in, mode %{public}d", mode);
    if (isLiveStream_ && !IsLiveSeek()) {
        MEDIA_LOGE("Can not SetPlaybackSpeed, it is live-stream");
        OnErrorMessage(MSERR_EXT_API9_UNSUPPORT_CAPABILITY, "Can not SetPlaybackSpeed, it is live-stream");
        return MSERR_INVALID_OPERATION;
    }

    auto rateTask = std::make_shared<TaskHandler<void>>([this, mode]() {
        MediaTrace::TraceBegin("PlayerServer::SetPlaybackSpeed", FAKE_POINTER(this));
        auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
        (void)currState->SetPlaybackSpeed(mode);
    });

    auto cancelTask = std::make_shared<TaskHandler<void>>([this, mode]() {
        MEDIA_LOGI("Interrupted speed action");
        Format format;
        OnInfoNoChangeStatus(INFO_TYPE_SPEEDDONE, mode, format);
        taskMgr_.MarkTaskDone("interrupted speed done");
    });

    int ret = taskMgr_.SpeedTask(rateTask, cancelTask, "speed", config_.speedMode);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "SetPlaybackSpeed failed");

    return MSERR_OK;
}

int32_t PlayerServer::SetPlaybackRate(float rate)
{
    std::lock_guard<std::mutex> lock(mutex_);

    if ((lastOpStatus_ != PLAYER_STARTED) && (lastOpStatus_ != PLAYER_PREPARED) &&
        (lastOpStatus_ != PLAYER_PAUSED) && (lastOpStatus_ != PLAYER_PLAYBACK_COMPLETE)) {
        MEDIA_LOGE("Can not SetPlaybackRate, currentState is %{public}s",
            GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }
    MEDIA_LOGD("PlayerServer SetPlaybackRate in, rate %{public}f", rate);
    if (isLiveStream_ && !IsLiveSeek()) {
        MEDIA_LOGE("Can not SetPlaybackRate, it is live-stream");
        OnErrorMessage(MSERR_EXT_API9_UNSUPPORT_CAPABILITY, "Can not SetPlaybackRate, it is live-stream");
        return MSERR_INVALID_OPERATION;
    }

    auto rateTask = std::make_shared<TaskHandler<void>>([this, rate]() {
        MediaTrace::TraceBegin("PlayerServer::SetPlaybackRate", FAKE_POINTER(this));
        auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
        (void)currState->SetPlaybackRate(rate);
    });

    auto cancelTask = std::make_shared<TaskHandler<void>>([this, rate]() {
        MEDIA_LOGI("Interrupted rate action");
        Format format;
        OnInfoNoChangeStatus(INFO_TYPE_RATEDONE, rate, format);
        taskMgr_.MarkTaskDone("interrupted rate done");
    });

    int32_t ret = taskMgr_.SpeedTask(rateTask, cancelTask, "rate", config_.speedRate);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "SetPlaybackRate failed");

    return MSERR_OK;
}

int32_t PlayerServer::HandleSetPlaybackSpeed(PlaybackRateMode mode)
{
    if (config_.speedMode == mode) {
        MEDIA_LOGD("The speed mode is same, mode = %{public}d", mode);
        Format format;
        OnInfoNoChangeStatus(INFO_TYPE_SPEEDDONE, mode, format);
        taskMgr_.MarkTaskDone("set speed mode is same");
        MediaTrace::TraceEnd("PlayerServer::SetPlaybackSpeed", FAKE_POINTER(this));
        return MSERR_OK;
    }

    if (playerEngine_ != nullptr) {
        int ret = playerEngine_->SetPlaybackSpeed(mode);
        CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine SetPlaybackSpeed Failed!");
    }
    config_.speedMode = mode;
    return MSERR_OK;
}

int32_t PlayerServer::HandleSetPlaybackRate(float rate)
{
    constexpr float EPSILON = 1e-6;
    if (std::fabs(config_.speedRate - rate) < EPSILON) {
        MEDIA_LOGD("The speed rate is same, rate = %{public}f", rate);
        Format format;
        (void)format.PutFloatValue(PlayerKeys::PLAYER_PLAYBACK_RATE, rate);
        OnInfoNoChangeStatus(INFO_TYPE_RATEDONE, rate, format);
        taskMgr_.MarkTaskDone("set speed rate is same");
        MediaTrace::TraceEnd("PlayerServer::SetPlaybackRate", FAKE_POINTER(this));
        return MSERR_OK;
    }

    if (playerEngine_ != nullptr) {
        int32_t ret = playerEngine_->SetPlaybackRate(rate);
        CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine SetPlaybackRate Failed!");
    }
    config_.speedRate = rate;
    return MSERR_OK;
}

int32_t PlayerServer::SetMediaSource(const std::shared_ptr<AVMediaSource> &mediaSource, AVPlayStrategy strategy)
{
    std::lock_guard<std::mutex> lock(mutex_);
    MediaTrace trace("PlayerServer::SetMediaSource");
    CHECK_AND_RETURN_RET_LOG(mediaSource != nullptr, MSERR_INVALID_VAL, "mediaSource is nullptr");

    mediaSource_ = mediaSource;
    strategy_ = strategy;

    std::string uri = mediaSource_->url;
    MEDIA_LOGI("server url: %{public}s", mediaSource_->url.c_str());
    std::string mimeType = mediaSource_->GetMimeType();
    size_t pos1 = uri.find("?");
    size_t pos2 = uri.find("offset=");
    size_t pos3 = uri.find("&");
    if (mimeType == AVMimeType::APPLICATION_M3U8 && pos1 != std::string::npos && pos2 != std::string::npos &&
        pos3 != std::string::npos) {
        CHECK_AND_RETURN_RET_LOG(strlen("fd://") < pos1, MSERR_INVALID_VAL, "Failed to read fd.");
        CHECK_AND_RETURN_RET_LOG(pos2 + strlen("offset=") < pos3, MSERR_INVALID_VAL, "Failed to read fd.");
        std::string fdStr = uri.substr(strlen("fd://"), pos1 - strlen("fd://"));
        std::string offsetStr = uri.substr(pos2 + strlen("offset="), pos3 - pos2 - strlen("offset="));
        CHECK_AND_RETURN_RET_LOG(pos3 + sizeof("&size") < uri.size(),
            MSERR_INVALID_VAL, "Failed to read fd.");
        std::string sizeStr = uri.substr(pos3 + sizeof("&size"));
        int32_t fd = -1;
        int32_t offset = -1;
        int32_t size = -1;
        CHECK_AND_RETURN_RET_LOG(StrToInt(fdStr, fd), MSERR_INVALID_VAL, "Failed to read fd.");
        CHECK_AND_RETURN_RET_LOG(StrToInt(offsetStr, offset), MSERR_INVALID_VAL, "Failed to read offset.");
        CHECK_AND_RETURN_RET_LOG(StrToInt(sizeStr, size), MSERR_INVALID_VAL, "Failed to read size.");

        auto uriHelper = std::make_unique<UriHelper>(fd, offset, size);
        CHECK_AND_RETURN_RET_LOG(uriHelper->AccessCheck(UriHelper::URI_READ), MSERR_INVALID_VAL, "Failed ro read fd.");
        uriHelper_ = std::move(uriHelper);
        mediaSource_->url = uriHelper_->FormattedUri();
    }

    int32_t ret = InitPlayEngine(mediaSource->url);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "SetMediaSource Failed!");

    config_.url = mediaSource_->url;
    config_.header = mediaSource_->header;
    config_.strategy_ = strategy;

    return MSERR_OK;
}

void PlayerServer::HandleEos()
{
    if (config_.looping.load()) {
        auto seekTask = std::make_shared<TaskHandler<void>>([this]() {
            MediaTrace::TraceBegin("PlayerServer::Seek", FAKE_POINTER(this));
            disableNextSeekDone_ = true;
            auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
            if (playerEngine_ != nullptr) {
                int64_t startTime = playerEngine_->GetPlayRangeStartTime();
                int64_t endTime = playerEngine_->GetPlayRangeEndTime();
                PlayerSeekMode seekMode = static_cast<PlayerSeekMode>(playerEngine_->GetPlayRangeSeekMode());
                int32_t seekTime = (startTime != -1 && endTime != -1) ? startTime : 0;
                playerEngine_->SetEosInLoopForFrozen(false);
                (void)currState->Seek(seekTime, seekMode);
            }
        });

        auto cancelTask = std::make_shared<TaskHandler<void>>([this]() {
            MEDIA_LOGI("Interrupted seek action");
            CHECK_AND_RETURN_LOG(playerEngine_ != nullptr, "PlayerEngine is null.");
            playerEngine_->SetEosInLoopForFrozen(false);
            taskMgr_.MarkTaskDone("interrupted seek done");
            disableNextSeekDone_ = false;
        });

        int32_t ret = taskMgr_.SeekTask(seekTask, cancelTask, "eos seek", SEEK_PREVIOUS_SYNC, 0);
        CHECK_AND_RETURN_LOG(ret == MSERR_OK, "Seek failed");
    }
}

void PlayerServer::PreparedHandleEos()
{
    MEDIA_LOGI("PlayerServer PreparedHandleEos in");
    if (!config_.looping.load()) {
        lastOpStatus_ = PLAYER_PLAYBACK_COMPLETE;
        ChangeState(playbackCompletedState_);
        (void)taskMgr_.MarkTaskDone("play->completed done");
    }
}

void PlayerServer::HandleInterruptEvent(const Format &infoBody)
{
    MEDIA_LOGI("0x%{public}06" PRIXPTR " HandleInterruptEvent in ", FAKE_POINTER(this));
    int32_t hintType = -1;
    int32_t forceType = -1;
    int32_t eventType = -1;
    (void)infoBody.GetIntValue(PlayerKeys::AUDIO_INTERRUPT_TYPE, eventType);
    (void)infoBody.GetIntValue(PlayerKeys::AUDIO_INTERRUPT_FORCE, forceType);
    (void)infoBody.GetIntValue(PlayerKeys::AUDIO_INTERRUPT_HINT, hintType);
    if (forceType == OHOS::AudioStandard::INTERRUPT_FORCE) {
        if (hintType == OHOS::AudioStandard::INTERRUPT_HINT_PAUSE ||
            hintType == OHOS::AudioStandard::INTERRUPT_HINT_STOP) {
            interruptEventState_ = PLAYER_IDLE;
        }
    }
}

void PlayerServer::HandleAudioDeviceChangeEvent(const Format &infoBody)
{
    MEDIA_LOGI("0x%{public}06" PRIXPTR " HandleAudioDeviceChangeEvent in ", FAKE_POINTER(this));
    int32_t reason = -1;
    (void)infoBody.GetIntValue(PlayerKeys::AUDIO_DEVICE_CHANGE_REASON, reason);
    if (!deviceChangeCallbackflag_ &&
        reason == static_cast<int32_t>(OHOS::AudioStandard::AudioStreamDeviceChangeReason::OLD_DEVICE_UNAVALIABLE) &&
        isStreamUsagePauseRequired_) {
        audioDeviceChangeState_ = PLAYER_PAUSED;
        (void)BackGroundChangeState(PLAYER_PAUSED, true);
    }
}

int32_t PlayerServer::GetPlaybackSpeed(PlaybackRateMode &mode)
{
    std::lock_guard<std::mutex> lock(mutex_);

    if (lastOpStatus_ == PLAYER_STATE_ERROR) {
        MEDIA_LOGE("Can not GetPlaybackSpeed, currentState is PLAYER_STATE_ERROR");
        return MSERR_INVALID_OPERATION;
    }
    MEDIA_LOGD("PlayerServer GetPlaybackSpeed in");

    mode = config_.speedMode;
    return MSERR_OK;
}

int32_t PlayerServer::GetPlaybackRate(float &rate)
{
    std::lock_guard<std::mutex> lock(mutex_);

    if (lastOpStatus_ == PLAYER_STATE_ERROR) {
        MEDIA_LOGE("Can not GetPlaybackRate, currentState is PLAYER_STATE_ERROR");
        return MSERR_INVALID_OPERATION;
    }
    MEDIA_LOGD("PlayerServer GetPlaybackRate in");

    rate = config_.speedRate;
    return MSERR_OK;
}

int32_t PlayerServer::SelectBitRate(uint32_t bitRate)
{
    std::unique_lock<std::mutex> lock(mutex_);
    if (playerEngine_ != nullptr) {
        int ret = playerEngine_->SelectBitRate(bitRate, false);
        CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine SelectBitRate Failed!");
    }
    return MSERR_OK;
}

#ifdef SUPPORT_VIDEO
int32_t PlayerServer::SetVideoSurface(sptr<Surface> surface)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(surface != nullptr, MSERR_INVALID_VAL, "surface is nullptr");

    bool setSurfaceFirst = lastOpStatus_ == PLAYER_INITIALIZED;
    bool switchSurface = lastOpStatus_ == PLAYER_PREPARED ||
        lastOpStatus_ == PLAYER_STARTED ||
        lastOpStatus_ == PLAYER_PAUSED ||
        lastOpStatus_ == PLAYER_STOPPED ||
        lastOpStatus_ == PLAYER_PLAYBACK_COMPLETE;
    
    if (setSurfaceFirst) {
        MEDIA_LOGI("set surface first in %{public}s state", GetStatusDescription(lastOpStatus_).c_str());
    } else if (switchSurface) {
        MEDIA_LOGI("switch surface in %{public}s state", GetStatusDescription(lastOpStatus_).c_str());
        auto innerSurface1 = weakSurface_.promote();
        if (innerSurface1 == nullptr && !isForceLoadVideo_ &&
            mutedMediaType_ != OHOS::Media::MediaType::MEDIA_TYPE_VID) {
            MEDIA_LOGE("old surface is required before switching surface");
            return MSERR_INVALID_OPERATION;
        }
    } else {
        MEDIA_LOGE("current state: %{public}s, can not SetVideoSurface", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }
    MEDIA_LOGD("PlayerServer SetVideoSurface in");
    {
        std::lock_guard<std::mutex> surfaceLock(surfaceMutex_);
        surface_ = surface;
        weakSurface_ = wptr<Surface>(surface_);
    }
    CHECK_AND_RETURN_RET_LOG(switchSurface && playerEngine_ != nullptr, MSERR_OK,
        "current state: %{public}s, playerEngine == nullptr: %{public}d, can not SetVideoSurface",
        GetStatusDescription(lastOpStatus_).c_str(), playerEngine_ == nullptr);
    auto task = std::make_shared<TaskHandler<void>>([this]() {
        std::lock_guard<std::mutex> surfaceLock(surfaceMutex_);
        auto innerSurface2 = weakSurface_.promote();
        CHECK_AND_RETURN_LOG(innerSurface2 != nullptr, "surface is null");
        (void)playerEngine_->SetVideoSurface(innerSurface2);
        taskMgr_.MarkTaskDone("SetVideoSurface done");
    });
    int32_t ret = taskMgr_.SetVideoSurfaeTask(task, "SetVideoSurface");
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "SetVideoSurface launch task failed");
    return MSERR_OK;
}
#endif

int32_t PlayerServer::SetDecryptConfig(const sptr<DrmStandard::IMediaKeySessionService> &keySessionProxy,
    bool svp)
{
    MEDIA_LOGI("PlayerServer SetDecryptConfig");
#ifdef SUPPORT_AVPLAYER_DRM
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(keySessionProxy != nullptr, MSERR_INVALID_VAL, "keySessionProxy is nullptr");

    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_INVALID_VAL, "playerEngine_ is nullptr");
    int32_t res = playerEngine_->SetDecryptConfig(keySessionProxy, svp);
    CHECK_AND_RETURN_RET_LOG(res == MSERR_OK,
        static_cast<int32_t>(MSERR_INVALID_OPERATION), "Engine SetDecryptConfig Failed!");
    MEDIA_LOGI("PlayerServer SetDecryptConfig out");
    return MSERR_OK;
#else
    (void)keySessionProxy;
    (void)svp;
    return 0;
#endif
}

bool PlayerServer::IsPlaying()
{
    std::lock_guard<std::mutex> lock(mutex_);
    if (lastOpStatus_ == PLAYER_STATE_ERROR) {
        MEDIA_LOGE("0x%{public}06" PRIXPTR " Can not judge IsPlaying, currentState is PLAYER_STATE_ERROR",
            FAKE_POINTER(this));
        return false;
    }

    return lastOpStatus_ == PLAYER_STARTED;
}

bool PlayerServer::IsPrepared()
{
    std::lock_guard<std::mutex> lock(mutex_);
    if (lastOpStatus_ == PLAYER_STATE_ERROR) {
        MEDIA_LOGE("Can not judge IsPrepared, currentState is PLAYER_STATE_ERROR");
        return false;
    }

    return lastOpStatus_ == PLAYER_PREPARED;
}

bool PlayerServer::IsCompleted()
{
    std::lock_guard<std::mutex> lock(mutex_);
    if (lastOpStatus_ == PLAYER_STATE_ERROR) {
        MEDIA_LOGE("Can not judge IsCompleted, currentState is PLAYER_STATE_ERROR");
        return false;
    }

    return lastOpStatus_ == PLAYER_PLAYBACK_COMPLETE;
}

bool PlayerServer::IsLooping()
{
    std::lock_guard<std::mutex> lock(mutex_);
    if (lastOpStatus_ == PLAYER_STATE_ERROR) {
        MEDIA_LOGE("Can not judge IsLooping, currentState is PLAYER_STATE_ERROR");
        return false;
    }

    return config_.looping;
}

int32_t PlayerServer::SetLooping(bool loop)
{
    std::lock_guard<std::mutex> lock(mutex_);
    if (lastOpStatus_ == PLAYER_STATE_ERROR) {
        MEDIA_LOGE("Can not SetLooping, currentState is PLAYER_STATE_ERROR");
        return MSERR_INVALID_OPERATION;
    }
    MEDIA_LOGD("PlayerServer SetLooping in, loop %{public}d", loop);

    if (isLiveStream_) {
        MEDIA_LOGE("Can not SetLooping, it is live-stream");
        OnErrorMessage(MSERR_EXT_API9_UNSUPPORT_CAPABILITY, "Can not SetLooping, it is live-stream");
        return MSERR_INVALID_OPERATION;
    }

    if (lastOpStatus_ == PLAYER_IDLE || lastOpStatus_ == PLAYER_INITIALIZED || GetCurrState() == preparingState_) {
        MEDIA_LOGI("Waiting for the engine state is <prepared> to take effect");
        config_.looping = loop;
        return MSERR_OK;
    }

    if (playerEngine_ != nullptr) {
        int32_t ret = playerEngine_->SetLooping(loop);
        CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "SetLooping Failed!");
    }
    config_.looping = loop;
    return MSERR_OK;
}

int32_t PlayerServer::SetParameter(const Format &param)
{
    std::lock_guard<std::mutex> lock(mutex_);
    if (lastOpStatus_ == PLAYER_STATE_ERROR) {
        MEDIA_LOGE("Can not SetParameter, currentState is PLAYER_STATE_ERROR");
        return MSERR_INVALID_OPERATION;
    }

    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");

    if (param.ContainKey(PlayerKeys::STREAM_USAGE)) {
        int32_t streamUsage = OHOS::AudioStandard::STREAM_USAGE_UNKNOWN;
        CHECK_AND_RETURN_RET(param.GetIntValue(PlayerKeys::STREAM_USAGE, streamUsage), MSERR_INVALID_VAL);
        MEDIA_LOGI("streamUsage = %{public}d", streamUsage);
        if (streamUsage != OHOS::AudioStandard::STREAM_USAGE_MUSIC &&
            streamUsage != OHOS::AudioStandard::STREAM_USAGE_MOVIE &&
            streamUsage != OHOS::AudioStandard::STREAM_USAGE_AUDIOBOOK) {
            isStreamUsagePauseRequired_ = false;
        }
        MEDIA_LOGI("isStreamUsagePauseRequired_ = %{public}d", isStreamUsagePauseRequired_);
    }

    if (param.ContainKey(PlayerKeys::AUDIO_EFFECT_MODE)) {
        int32_t effectMode = OHOS::AudioStandard::AudioEffectMode::EFFECT_DEFAULT;
        CHECK_AND_RETURN_RET(param.GetIntValue(PlayerKeys::AUDIO_EFFECT_MODE, effectMode), MSERR_INVALID_VAL);
        return SetAudioEffectMode(effectMode);
    }

    int32_t ret = playerEngine_->SetParameter(param);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "SetParameter Failed!");

    if (param.ContainKey(PlayerKeys::CONTENT_TYPE)) {
        config_.effectMode = OHOS::AudioStandard::AudioEffectMode::EFFECT_DEFAULT;
    }

    return MSERR_OK;
}

int32_t PlayerServer::SetAudioEffectMode(const int32_t effectMode)
{
    MEDIA_LOGD("SetAudioEffectMode in");
    CHECK_AND_RETURN_RET(lastOpStatus_ == PLAYER_PREPARED || lastOpStatus_ == PLAYER_STARTED ||
        lastOpStatus_ == PLAYER_PLAYBACK_COMPLETE || lastOpStatus_ == PLAYER_PAUSED, MSERR_INVALID_OPERATION);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    CHECK_AND_RETURN_RET_LOG(effectMode <= OHOS::AudioStandard::AudioEffectMode::EFFECT_DEFAULT &&
        effectMode >= OHOS::AudioStandard::AudioEffectMode::EFFECT_NONE, MSERR_INVALID_VAL,
        "Invalid effectMode parameter");
    int32_t ret = playerEngine_->SetAudioEffectMode(effectMode);
    if (ret == MSERR_OK) {
        config_.effectMode = effectMode;
    }

    return ret;
}

int32_t PlayerServer::SetPlayerCallback(const std::shared_ptr<PlayerCallback> &callback)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(callback != nullptr, MSERR_INVALID_VAL, "callback is nullptr");

    if (lastOpStatus_ != PLAYER_IDLE && lastOpStatus_ != PLAYER_INITIALIZED) {
        MEDIA_LOGE("Can not SetPlayerCallback, currentState is %{public}s",
            GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }

    {
        std::lock_guard<std::mutex> lockCb(mutexCb_);
        playerCb_ = callback;
    }
    return MSERR_OK;
}

int32_t PlayerServer::SelectTrack(int32_t index, PlayerSwitchMode mode)
{
    std::lock_guard<std::mutex> lock(mutex_);

    CHECK_AND_RETURN_RET_LOG(lastOpStatus_ == PLAYER_PREPARED || lastOpStatus_ == PLAYER_STARTED ||
        lastOpStatus_ == PLAYER_PAUSED || lastOpStatus_ == PLAYER_PLAYBACK_COMPLETE, MSERR_INVALID_OPERATION,
        "invalid state %{public}s", GetStatusDescription(lastOpStatus_).c_str());
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");

    auto task = std::make_shared<TaskHandler<void>>([this, index, mode]() {
        MediaTrace::TraceBegin("PlayerServer::track", FAKE_POINTER(this));
        CHECK_AND_RETURN(IsEngineStarted());
        int32_t ret = playerEngine_->SelectTrack(index, mode);
        taskMgr_.MarkTaskDone("SelectTrack done");
        CHECK_AND_RETURN_LOG(ret == MSERR_OK, "failed to SelectTrack");
    });
    int32_t ret = taskMgr_.LaunchTask(task, PlayerServerTaskType::STATE_CHANGE, "SelectTrack");
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "SelectTrack launch task failed");

    return MSERR_OK;
}

int32_t PlayerServer::DeselectTrack(int32_t index)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(lastOpStatus_ == PLAYER_PREPARED || lastOpStatus_ == PLAYER_STARTED ||
        lastOpStatus_ == PLAYER_PAUSED || lastOpStatus_ == PLAYER_PLAYBACK_COMPLETE, MSERR_INVALID_OPERATION,
        "invalid state %{public}s", GetStatusDescription(lastOpStatus_).c_str());
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");

    auto task = std::make_shared<TaskHandler<void>>([this, index]() {
        MediaTrace::TraceBegin("PlayerServer::track", FAKE_POINTER(this));
        CHECK_AND_RETURN(IsEngineStarted());
        int32_t ret = playerEngine_->DeselectTrack(index);
        taskMgr_.MarkTaskDone("DeselectTrack done");
        CHECK_AND_RETURN_LOG(ret == MSERR_OK, "failed to DeselectTrack");
    });
    int32_t ret = taskMgr_.LaunchTask(task, PlayerServerTaskType::STATE_CHANGE, "DeselectTrack");
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "DeselectTrack launch task failed");

    return MSERR_OK;
}

int32_t PlayerServer::GetCurrentTrack(int32_t trackType, int32_t &index)
{
    CHECK_AND_RETURN_RET_LOG(trackType >= Media::MediaType::MEDIA_TYPE_AUD &&
        trackType <= Media::MediaType::MEDIA_TYPE_SUBTITLE, MSERR_INVALID_VAL,
        "Invalid trackType %{public}d", trackType);

    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(lastOpStatus_ == PLAYER_PREPARED || lastOpStatus_ == PLAYER_STARTED ||
        lastOpStatus_ == PLAYER_PAUSED || lastOpStatus_ == PLAYER_PLAYBACK_COMPLETE, MSERR_INVALID_OPERATION,
        "invalid state %{public}s", GetStatusDescription(lastOpStatus_).c_str());
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");

    return playerEngine_->GetCurrentTrack(trackType, index);
}

void PlayerServer::FormatToString(std::string &dumpString, std::vector<Format> &videoTrack)
{
    for (auto iter = videoTrack.begin(); iter != videoTrack.end(); iter++) {
        dumpString += iter->Stringify();
        dumpString += '\n';
    }
}

int32_t PlayerServer::DumpInfo(int32_t fd)
{
    std::string dumpString;
    if (playerEngine_ == nullptr) {
        dumpString +=
            "The engine is not created, note: engine can't be created until set source.\n";
    }
    dumpString += "PlayerServer current state is: " + GetStatusDescription(lastOpStatus_) + "\n";
    if (lastErrMsg_.size() != 0) {
        dumpString += "PlayerServer last error is: " + lastErrMsg_ + "\n";
    }
    dumpString += "PlayerServer url is: " + config_.url + "\n";
    dumpString += "PlayerServer play back speed is: " + std::to_string(config_.speedMode) + "\n";
    std::string loopflag = config_.looping ? "" : "not ";
    dumpString += "PlayerServer current " + loopflag + "in looping mode\n";
    dumpString += "PlayerServer left volume and right volume is: " +
        std::to_string(config_.leftVolume) + ", " + std::to_string(config_.rightVolume) + "\n";
    dumpString += "PlayerServer audio effect mode is: " + std::to_string(config_.effectMode) + "\n";
    if (playerEngine_ != nullptr) {
        dumpString += "PlayerServer enable HEBC: " + std::to_string(playerEngine_->GetHEBCMode()) + "\n";
        playerEngine_->OnDumpInfo(fd);
    }
    dumpString += "PlayerServer client bundle name is: " + appName_ + "\n";
    dumpString += "PlayerServer instance id is: " + std::to_string(instanceId_) + "\n";
    std::vector<Format> videoTrack;
    (void)GetVideoTrackInfo(videoTrack);
    dumpString += "PlayerServer video tracks info: \n";
    FormatToString(dumpString, videoTrack);
    
    std::vector<Format> audioTrack;
    (void)GetAudioTrackInfo(audioTrack);
    dumpString += "PlayerServer audio tracks info: \n";
    FormatToString(dumpString, audioTrack);
    
    int32_t currentTime = -1;
    (void)GetCurrentTime(currentTime);
    dumpString += "PlayerServer current time is: " + std::to_string(currentTime) + "\n";
    write(fd, dumpString.c_str(), dumpString.size());

    return MSERR_OK;
}

std::string PlayerServer::GetPlayerErrorTypeStr(PlayerErrorType errorType)
{
    std::string errorTypeStr = "";
    auto it = ERROR_TYPE_INFOS.find(errorType);
    if (it != ERROR_TYPE_INFOS.end()) {
        errorTypeStr = ERROR_TYPE_INFOS.at(errorType);
    }
    return errorTypeStr;
}

void PlayerServer::OnError(PlayerErrorType errorType, int32_t errorCode, const std::string &description)
{
    auto errorMsg = GetPlayerErrorTypeStr(errorType);
    errorMsg += MSErrorToExtErrorString(static_cast<MediaServiceErrCode>(errorCode)) + ", ";
    errorMsg += MSErrorToString(static_cast<MediaServiceErrCode>(errorCode))+ ", ";
    errorMsg += description != "" ? description + "-" : "null-";
    return OnErrorMessage(errorCode, errorMsg);
}

void PlayerServer::OnErrorMessage(int32_t errorCode, const std::string &errorMsg)
{
    if (static_cast<MediaServiceExtErrCodeAPI9>(errorCode) == MSERR_EXT_API9_IO) {
        MEDIA_LOGD("0x%{public}06" PRIXPTR " PlayerServer OnErrorMessage Error in", FAKE_POINTER(this));
        auto pauseTask = std::make_shared<TaskHandler<void>>([this, errorCode, errorMsg]() {
            MediaTrace::TraceBegin("PlayerServer::PauseIoError", FAKE_POINTER(this));
            MEDIA_LOGI("PlayerServer::PauseIoError start");
            auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
            (void)currState->Pause(true);
            OnErrorCb(errorCode, errorMsg);
            MEDIA_LOGI("PlayerServer::PauseIoError end");
        });
        taskMgr_.LaunchTask(pauseTask, PlayerServerTaskType::STATE_CHANGE, "pause");
        MEDIA_LOGI("0x%{public}06" PRIXPTR " PlayerServer OnErrorMessage IO Error out", FAKE_POINTER(this));
        return;
    } else if (errorCode == MSERR_DEMUXER_BUFFER_NO_MEMORY) {
        auto pauseTask = std::make_shared<TaskHandler<void>>([this, errorCode, errorMsg]() {
            MEDIA_LOGI("MSERR_DEMUXER_BUFFER_NO_MEMORY PauseDemuxer start");
            auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
            (void)currState->PauseDemuxer();
            OnErrorCb(errorCode, errorMsg);
            MEDIA_LOGI("MSERR_DEMUXER_BUFFER_NO_MEMORY PauseDemuxer end");
        });
        taskMgr_.LaunchTask(pauseTask, PlayerServerTaskType::LIGHT_TASK, "PauseDemuxer");
        return;
    }
    OnErrorCb(errorCode, errorMsg);
}

void PlayerServer::OnErrorCb(int32_t errorCode, const std::string &errorMsg)
{
    std::lock_guard<std::mutex> lockCb(mutexCb_);
    lastErrMsg_ = errorMsg;
    if (playerCb_ != nullptr && !errorCbOnce_) {
        playerCb_->OnError(errorCode, errorMsg);
        errorCbOnce_ = true;
    }
}

void PlayerServer::OnInfo(PlayerOnInfoType type, int32_t extra, const Format &infoBody)
{
    std::lock_guard<std::mutex> lockCb(mutexCb_);
    int32_t ret = HandleMessage(type, extra, infoBody);
    InnerOnInfo(type, extra, infoBody, ret);
}

void PlayerServer::DoCheckLiveDelayTime()
{
    CHECK_AND_RETURN(playerEngine_ != nullptr);
    MEDIA_LOGI("DoCheckLiveDelayTime");
    PlaybackRateMode mode = PlaybackRateMode::SPEED_FORWARD_1_00_X;
    bool isExceedMaxDelayTime = playerEngine_->IsNeedChangePlaySpeed(mode, isXSpeedPlay_);
    if (isExceedMaxDelayTime) {
        int32_t ret = playerEngine_->SetPlaybackSpeed(mode);
        sumPauseTime_ = (ret == MSERR_OK && mode == PlaybackRateMode::SPEED_FORWARD_1_20_X) ? 0 : sumPauseTime_;
    }
    return;
}

void PlayerServer::InnerOnInfo(PlayerOnInfoType type, int32_t extra, const Format &infoBody, const int32_t ret)
{
    if (type == INFO_TYPE_IS_LIVE_STREAM) {
        isLiveStream_ = true;
    } else if (type == INFO_TYPE_TRACK_NUM_UPDATE) {
        subtitleTrackNum_ = static_cast<uint32_t>(extra);
        return;
    }
    CHECK_AND_RETURN_LOG(CheckState(type, extra), "OnInfo check state failed");
    if (type == INFO_TYPE_DEFAULTTRACK || type == INFO_TYPE_TRACK_DONE || type == INFO_TYPE_ADD_SUBTITLE_DONE) {
        return;
    }
    if (playerCb_ != nullptr && type == INFO_TYPE_ERROR_MSG) {
        int32_t errorCode = extra;
        Format newInfo = infoBody;
        auto errorMsg = MSErrorToString(static_cast<MediaServiceErrCode>(errorCode));
        newInfo.PutIntValue(std::string(PlayerKeys::PLAYER_ERROR_TYPE), errorCode);
        newInfo.PutStringValue(std::string(PlayerKeys::PLAYER_ERROR_MSG), errorMsg);
        playerCb_->OnInfo(type, extra, newInfo);
        return;
    }
    if (type == INFO_TYPE_BUFFERING_UPDATE) {
        OnBufferingUpdate(type, extra, infoBody);
    }
    if (type == INFO_TYPE_FLV_AUTO_SELECT_BITRATE) {
        OnFlvAutoSelectBitRate(extra);
        return;
    }
    if (playerCb_ != nullptr && ret == MSERR_OK) {
        bool isBackgroudPause = (extra == backgroundState_ || extra == interruptEventState_ ||
            extra == audioDeviceChangeState_);
        if (isBackgroundChanged_ && type == INFO_TYPE_STATE_CHANGE && isBackgroudPause) {
            MEDIA_LOGI("Background change state to %{public}d, Status reporting %{public}d", extra, isBackgroundCb_);
            if (isBackgroundCb_) {
                Format newInfo = infoBody;
                newInfo.PutIntValue(PlayerKeys::PLAYER_STATE_CHANGED_REASON, StateChangeReason::BACKGROUND);
                playerCb_->OnInfo(type, extra, newInfo);
                isBackgroundCb_ = false;
            }
            isBackgroundChanged_ = false;
            interruptEventState_ = PLAYER_IDLE;
            audioDeviceChangeState_ = PLAYER_IDLE;
        } else {
            playerCb_->OnInfo(type, extra, infoBody);
        }
    } else {
        MEDIA_LOGD("0x%{public}06" PRIXPTR " playerCb_ != nullptr %{public}d, ret %{public}d",
            FAKE_POINTER(this), playerCb_ != nullptr, ret);
    }
}

void PlayerServer::OnDfxInfo(const DfxEvent &event)
{
    MEDIA_LOGD("OnDfxInfo, type: %{public}d", static_cast<int32_t>(event.type));
    if (event.type == DfxEventType::DFX_INFO_MEMORY_USAGE) {
        totalMemoryUage_ = AnyCast<uint32_t>(event.param);
        MEDIA_LOGD("OnDfxInfo %{public}d", static_cast<int32_t>(totalMemoryUage_.load()));
    }
}

void PlayerServer::OnSystemOperation(PlayerOnSystemOperationType type, PlayerOperationReason reason)
{
    std::lock_guard<std::mutex> lock(mutex_);
    MEDIA_LOGI("PlayerServer OnSystemOperation start, type: %{public}d, reason: %{public}d", static_cast<int32_t>(type),
        static_cast<int32_t>(reason));
    switch (type) {
        case OPERATION_TYPE_PAUSE:
            if (lastOpStatus_ == PLAYER_STARTED) {
                (void)OnPause(true);
            }
            break;
        case OPERATION_TYPE_CHECK_LIVE_DELAY:
            DoCheckLiveDelayTime();
            break;
        default:
            MEDIA_LOGI("Can not OnSystemOperation, currentState is %{public}s",
                GetStatusDescription(lastOpStatus_).c_str());
            break;
    }
}

void PlayerServer::OnBufferingUpdate(PlayerOnInfoType type, int32_t extra, const Format &infoBody)
{
    Format newInfo = infoBody;
    int info = -1;
    infoBody.GetIntValue(std::string(PlayerKeys::PLAYER_BUFFERING_START), info);
    if (info == 1) {
        OnNotifyBufferingStart();
        return;
    }
    infoBody.GetIntValue(std::string(PlayerKeys::PLAYER_BUFFERING_END), info);
    if (info == 1) {
        OnNotifyBufferingEnd();
        return;
    }
}

void PlayerServer::OnNotifyBufferingStart()
{
    MEDIA_LOGD("0x%{public}06" PRIXPTR " PlayerServer OnNotifyBufferingStart in", FAKE_POINTER(this));
    auto pauseTask = std::make_shared<TaskHandler<void>>([this]() {
        MediaTrace::TraceBegin("PlayerServer::PauseDemuxer", FAKE_POINTER(this));
        MEDIA_LOGI("PauseDemuxer start");
        auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
        (void)currState->PauseDemuxer();
        MEDIA_LOGI("PauseDemuxer end");
    });
    taskMgr_.LaunchTask(pauseTask, PlayerServerTaskType::LIGHT_TASK, "PauseDemuxer");
    MEDIA_LOGI("0x%{public}06" PRIXPTR " PlayerServer OnNotifyBufferingStart out", FAKE_POINTER(this));
    UpdateFlvLivePauseTime();
    return;
}

void PlayerServer::OnNotifyBufferingEnd()
{
    MEDIA_LOGD("0x%{public}06" PRIXPTR " PlayerServer OnNotifyBufferingEnd in", FAKE_POINTER(this));
    auto playingTask = std::make_shared<TaskHandler<void>>([this]() {
        MediaTrace::TraceBegin("PlayerServer::ResumeDemuxer", FAKE_POINTER(this));
        MEDIA_LOGI("ResumeDemuxer start");
        auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
        (void)currState->ResumeDemuxer();
        MEDIA_LOGI("ResumeDemuxer end");
    });
    taskMgr_.LaunchTask(playingTask, PlayerServerTaskType::LIGHT_TASK, "ResumeDemuxer");
    MEDIA_LOGI("0x%{public}06" PRIXPTR " PlayerServer OnNotifyBufferingEnd out", FAKE_POINTER(this));
    return;
}

void PlayerServer::OnFlvAutoSelectBitRate(uint32_t bitRate)
{
    MEDIA_LOGI("0x%{public}06" PRIXPTR " PlayerServer OnFlvAutoSelectBitRate in", FAKE_POINTER(this));
    CHECK_AND_RETURN(playerEngine_ != nullptr);
    auto autoSelectBitRateTask = std::make_shared<TaskHandler<void>>([this, bitRate]() {
        MediaTrace::TraceBegin("PlayerServer::OnFlvAutoSelectBitRate", FAKE_POINTER(this));
        if (playerEngine_ == nullptr) {
            MEDIA_LOGI("OnFlvAutoSelectBitRate task end, playerEngine_ is null");
            taskMgr_.MarkTaskDone("flv auto select bitrate ignore");
            return;
        }
        int32_t ret = playerEngine_->SelectBitRate(bitRate, true);
        MEDIA_LOGI("OnFlvAutoSelectBitRate task end");
        taskMgr_.MarkTaskDone("flv auto select bitrate done");
        CHECK_AND_RETURN_LOG(ret == MSERR_OK, "flv auto select bit rate failed");
    });
    taskMgr_.LaunchTask(autoSelectBitRateTask, PlayerServerTaskType::LIGHT_TASK, "AutoSelectBitRateTask");
    MEDIA_LOGD("0x%{public}06" PRIXPTR " PlayerServer OnFlvAutoSelectBitRate out", FAKE_POINTER(this));
    return;
}

void PlayerServer::UpdateFlvLivePauseTime()
{
    CHECK_AND_RETURN_LOG(playerEngine_ != nullptr, "playerEngine_ is nullptr");
    CHECK_AND_RETURN_NOLOG(playerEngine_->IsFlvLive());
    if (pauseTimestamp_ == HST_TIME_NONE) {
        pauseTimestamp_ = SteadyClock::GetCurrentTimeMs();
        if (pauseTimestamp_ < 0) {
            MEDIA_LOGI("get current time failed");
            pauseTimestamp_ = HST_TIME_NONE;
        }
    }
}

void PlayerServer::TryFlvLiveRestartLink()
{
    CHECK_AND_RETURN_LOG(playerEngine_ != nullptr, "playerEngine_ is nullptr");
    CHECK_AND_RETURN_NOLOG(playerEngine_->IsFlvLive());
    if (pauseTimestamp_ != HST_TIME_NONE) {
        sumPauseTime_ += CalculatePauseTime();
        pauseTimestamp_ = HST_TIME_NONE;
        bool isNeededRestartLink = playerEngine_->IsPauseForTooLong(sumPauseTime_);
        if (isNeededRestartLink) {
            HandleFlvLiveRestartLink();
        }
    }
}

int64_t PlayerServer::CalculatePauseTime()
{
    int64_t curTime = SteadyClock::GetCurrentTimeMs();
    return (curTime > pauseTimestamp_) ? (curTime - pauseTimestamp_) : 0;
}

void PlayerServer::HandleFlvLiveRestartLink()
{
    MEDIA_LOGI("HandleRestartLink");
    std::lock_guard<std::mutex> lock(mutex_);
    sumPauseTime_ = 0;
    pauseTimestamp_ = HST_TIME_NONE;
    playerEngine_->DoRestartLiveLink();
    playerEngine_->SetPlaybackSpeed(PlaybackRateMode::SPEED_FORWARD_1_00_X);
    isXSpeedPlay_ = false;
}

void PlayerServer::OnInfoNoChangeStatus(PlayerOnInfoType type, int32_t extra, const Format &infoBody)
{
    std::lock_guard<std::mutex> lockCb(mutexCb_);

    if (playerCb_ != nullptr) {
        playerCb_->OnInfo(type, extra, infoBody);
    }
}

const std::string &PlayerServer::GetStatusDescription(int32_t status)
{
    static const std::string ILLEGAL_STATE = "PLAYER_STATUS_ILLEGAL";
    if (status < PLAYER_STATE_ERROR || status > PLAYER_PLAYBACK_COMPLETE) {
        return ILLEGAL_STATE;
    }

    return STATUS_TO_STATUS_DESCRIPTION_TABLE.find(status)->second;
}

std::string PlayerServerState::GetStateName() const
{
    return name_;
}

int32_t PlayerServerStateMachine::HandleMessage(PlayerOnInfoType type, int32_t extra, const Format &infoBody)
{
    if (currState_ != nullptr) {
        return currState_->OnMessageReceived(type, extra, infoBody);
    }
    return MSERR_OK;
}

void PlayerServerStateMachine::Init(const std::shared_ptr<PlayerServerState> &state)
{
    currState_ = state;
}

void PlayerServerStateMachine::ChangeState(const std::shared_ptr<PlayerServerState> &state)
{
    {
        // Resolve the deadlock between reset and state callback
        std::unique_lock<std::recursive_mutex> lock(recMutex_);

        if (state == nullptr || (state == currState_)) {
            return;
        }

        if (currState_) {
            MEDIA_LOGD("exit state %{public}s", currState_->name_.c_str());
            currState_->StateExit();
        }
        MEDIA_LOGI("instance: 0x%{public}06" PRIXPTR " change state to %{public}s",
            FAKE_POINTER(this), state->name_.c_str());
        currState_ = state;
    }
    state->StateEnter();
}

std::shared_ptr<PlayerServerState> PlayerServerStateMachine::GetCurrState()
{
    std::unique_lock<std::recursive_mutex> lock(recMutex_);
    return currState_;
}

void PlayerServer::OnCommonEventReceived(const std::string &event)
{
    MEDIA_LOGI("instance: 0x%{public}06" PRIXPTR " receive event %{public}s",
            FAKE_POINTER(this), event.c_str());
    if (event == EventFwk::CommonEventSupport::COMMON_EVENT_USER_BACKGROUND) {
        std::weak_ptr<PlayerServer> server = std::static_pointer_cast<PlayerServer>(shared_from_this());
        auto pauseTask = std::make_shared<TaskHandler<void>>([server]() {
            std::shared_ptr<PlayerServer> spServer = server.lock();
            if (spServer != nullptr) {
                spServer->taskMgr_.MarkTaskDone("receiveccommonevent done");
                (void)spServer->OnSystemOperation(OPERATION_TYPE_PAUSE, OPERATION_REASON_USER_BACKGROUND);
            }
        });
        taskMgr_.LaunchTask(pauseTask, PlayerServerTaskType::STATE_CHANGE, "receiveccommonevent");
    }
}

int32_t PlayerServer::GetUserId()
{
    return userId_.load();
}

std::shared_ptr<CommonEventReceiver> PlayerServer::GetCommonEventReceiver()
{
    return commonEventReceiver_;
}

bool PlayerServer::IsBootCompleted()
{
    return isBootCompleted_.load();
}

int32_t PlayerServer::SetMediaMuted(OHOS::Media::MediaType mediaType, bool isMuted)
{
    CHECK_AND_RETURN_RET(mediaType == OHOS::Media::MediaType::MEDIA_TYPE_AUD ||
        mediaType == OHOS::Media::MediaType::MEDIA_TYPE_VID, MSERR_INVALID_VAL);
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET(lastOpStatus_ == PLAYER_INITIALIZED || lastOpStatus_ == PLAYER_PREPARED ||
                             lastOpStatus_ == PLAYER_STARTED || lastOpStatus_ == PLAYER_PLAYBACK_COMPLETE ||
                             lastOpStatus_ == PLAYER_PAUSED || lastOpStatus_ == PLAYER_STOPPED,
                         MSERR_INVALID_STATE);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "engine is nullptr");
    auto mediaMuteTask = std::make_shared<TaskHandler<int32_t>>([this, mediaType, isMuted]() {
        MediaTrace trace("PlayerServer::SetMediaMuted");
        CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, taskMgr_.MarkTaskDone("SetMediaMuted done"),
            "SetMediaMuted failed, playerEngine is nullptr");
        auto res = playerEngine_->SetMediaMuted(mediaType, isMuted);
        MEDIA_LOGI("SetMediaMuted %{public}u %{public}u", mediaType, isMuted);
        taskMgr_.MarkTaskDone("SetMediaMuted done");
        return res;
    });
    taskMgr_.LaunchTask(mediaMuteTask, PlayerServerTaskType::LIGHT_TASK, "SetMediaMuted");
    return MSERR_OK;
}

int32_t PlayerServer::SetPlaybackStrategy(AVPlayStrategy playbackStrategy)
{
    MediaTrace::TraceBegin("PlayerServer::SetPlaybackStrategy", FAKE_POINTER(this));
    std::lock_guard<std::mutex> lock(mutex_);
    bool isValidState = lastOpStatus_ == PLAYER_INITIALIZED || lastOpStatus_ == PLAYER_STOPPED;
    CHECK_AND_RETURN_RET_LOG(isValidState, MSERR_INVALID_STATE,
        "can not set playback strategy, current state is %{public}d", static_cast<int32_t>(lastOpStatus_.load()));
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "engine is nullptr");
    MEDIA_LOGD("PlayerServer::SetPlaybackStrategy mutedMediaType is: %{public}d", playbackStrategy.mutedMediaType);
    MEDIA_LOGD("SetPlaybackStrategy keepDecodingOnmute is: %{public}d ", playbackStrategy.keepDecodingOnMute);
    mutedMediaType_ = playbackStrategy.mutedMediaType;
    return playerEngine_->SetPlaybackStrategy(playbackStrategy);
}

int32_t PlayerServer::SetTrackSelectionFilter(AVPlayTrackSelectionFilter trackFilter)
{
    MediaTrace::TraceBegin("PlayerServer::SetTrackSelectionFilter", FAKE_POINTER(this));
    MEDIA_LOGD("SetTrackSelectionFilter");
    std::lock_guard<std::mutex> lock(mutex_);
    config_.trackSelectionFilter_ = trackFilter;
    config_.hasTrackSelectionFilter = true;
    
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_OK, "engine is nullptr");
    return playerEngine_->SetTrackSelectionFilter(trackFilter);
}

int32_t PlayerServer::GetTrackSelectionFilter(AVPlayTrackSelectionFilter &trackFilter)
{
    MEDIA_LOGD("GetTrackSelectionFilter");
    MediaTrace::TraceBegin("PlayerServer::GetTrackSelectionFilter", FAKE_POINTER(this));
    std::lock_guard<std::mutex> lock(mutex_);
    trackFilter = config_.trackSelectionFilter_;
    return MSERR_OK;
}

int32_t PlayerServer::SetSuperResolution(bool enabled)
{
    MediaTrace::TraceBegin("PlayerServer::SetSuperResolution", FAKE_POINTER(this));
    std::lock_guard<std::mutex> lock(mutex_);
    bool isValidState = lastOpStatus_ == PLAYER_INITIALIZED || lastOpStatus_ == PLAYER_PREPARED ||
                        lastOpStatus_ == PLAYER_STARTED || lastOpStatus_ == PLAYER_PAUSED ||
                        lastOpStatus_ == PLAYER_STOPPED || lastOpStatus_ == PLAYER_PLAYBACK_COMPLETE;
    CHECK_AND_RETURN_RET_LOG(isValidState, MSERR_INVALID_STATE,
        "can not set super resolution, current state is %{public}d", static_cast<int32_t>(lastOpStatus_.load()));
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "engine is nullptr");

    CHECK_AND_RETURN_RET_LOG(!isVideoOutputEnabled_.load(), MSERR_INVALID_OPERATION,
        "super resolution is mutually exclusive with side output");

    isSuperResolutionEnabled_.store(enabled);
    return playerEngine_->SetSuperResolution(enabled);
}

int32_t PlayerServer::SetVideoWindowSize(int32_t width, int32_t height)
{
    MediaTrace::TraceBegin("PlayerServer::SetVideoWindowSize", FAKE_POINTER(this));
    std::lock_guard<std::mutex> lock(mutex_);
    bool isValidState = lastOpStatus_ == PLAYER_INITIALIZED || lastOpStatus_ == PLAYER_PREPARED ||
                        lastOpStatus_ == PLAYER_STARTED || lastOpStatus_ == PLAYER_PAUSED ||
                        lastOpStatus_ == PLAYER_STOPPED || lastOpStatus_ == PLAYER_PLAYBACK_COMPLETE;
    CHECK_AND_RETURN_RET_LOG(isValidState, MSERR_INVALID_STATE,
        "can not set video window size, current state is %{public}d", static_cast<int32_t>(lastOpStatus_.load()));
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "engine is nullptr");
    return playerEngine_->SetVideoWindowSize(width, height);
}

int32_t PlayerServer::CheckSeek(int64_t mSeconds, PlayerSeekMode mode)
{
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");

    MEDIA_LOGI("KPI-TRACE: PlayerServer Seek in");
    if (lastOpStatus_ != PLAYER_PREPARED && lastOpStatus_ != PLAYER_PAUSED &&
        lastOpStatus_ != PLAYER_STARTED && lastOpStatus_ != PLAYER_PLAYBACK_COMPLETE) {
        MEDIA_LOGE("Can not Seek, currentState is %{public}s", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }

    if (IsValidSeekMode(mode) != true) {
        MEDIA_LOGE("Seek failed, inValid mode");
        return MSERR_INVALID_VAL;
    }
    return MSERR_OK;
}

int32_t PlayerServer::SeekContinous(int64_t mSeconds)
{
    if (mSeconds == -1) {
        ExitSeekContinousAsync(true);
        return MSERR_OK;
    }
    {
        std::lock_guard<std::mutex> lock(seekContinousMutex_);
        if (!isInSeekContinous_.load()) {
            UpdateContinousBatchNo();
            isInSeekContinous_.store(true);
        }
    }
    int64_t seekContinousBatchNo = seekContinousBatchNo_.load();
    mSeconds = std::max(int64_t {0}, mSeconds);
    auto seekContinousTask = std::make_shared<TaskHandler<void>>([this, mSeconds, seekContinousBatchNo]() {
        MediaTrace trace("PlayerServer::SeekContinous");
        MEDIA_LOGI("PlayerServer::Seek start");
        auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
        (void)currState->SeekContinous(mSeconds, seekContinousBatchNo);
        MEDIA_LOGI("PlayerServer::SeekContinous end");
        taskMgr_.MarkTaskDone("seek continous done");
    });

    int32_t ret = taskMgr_.SeekContinousTask(seekContinousTask, "seek continous");
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "SeekContinous failed");

    MEDIA_LOGI("Queue seekTask end, position %{public}" PRId64, mSeconds);
    return MSERR_OK;
}

int32_t PlayerServer::HandleSeekContinous(int64_t mSeconds, int64_t batchNo)
{
    MEDIA_LOGI("KPI-TRACE: PlayerServer HandleSeek in, mSeconds: %{public}" PRId64, mSeconds);
    int32_t ret = playerEngine_->SeekContinous(mSeconds, batchNo);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine Seek Failed!");
    MEDIA_LOGI("PlayerServer HandleSeek end");
    return MSERR_OK;
}

int32_t PlayerServer::ExitSeekContinous(bool align)
{
    {
        std::lock_guard<std::mutex> lock(seekContinousMutex_);
        if (!isInSeekContinous_.load()) {
            return MSERR_OK;
        }
        UpdateContinousBatchNo();
        isInSeekContinous_.store(false);
    }
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    return playerEngine_->ExitSeekContinous(align, seekContinousBatchNo_.load());
}

int32_t PlayerServer::ExitSeekContinousAsync(bool align)
{
    {
        std::lock_guard<std::mutex> lock(seekContinousMutex_);
        if (!isInSeekContinous_.load()) {
            return MSERR_OK;
        }
        UpdateContinousBatchNo();
        isInSeekContinous_.store(false);
    }
    int64_t seekContinousBatchNo = seekContinousBatchNo_.load();
    auto exitSeekContinousTask = std::make_shared<TaskHandler<void>>([this, align, seekContinousBatchNo]() {
        MediaTrace trace("PlayerServer::ExitSeekContinousAsync");
        MEDIA_LOGI("PlayerServer::ExitSeekContinous start");
        if (playerEngine_ == nullptr) {
            MEDIA_LOGE("playerEngine_ is nullptr!");
            taskMgr_.MarkTaskDone("exit seek continous done");
            return;
        }
        playerEngine_->ExitSeekContinous(align, seekContinousBatchNo);
        MEDIA_LOGI("PlayerServer::ExitSeekContinous end");
        taskMgr_.MarkTaskDone("exit seek continous done");
    });
    int32_t ret = taskMgr_.SeekContinousTask(exitSeekContinousTask, "exit seek continous");
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "SeekContinous failed");
    return MSERR_OK;
}

int32_t PlayerServer::SetDeviceChangeCbStatus(bool status)
{
    deviceChangeCallbackflag_ = status;
    MEDIA_LOGI("Set DeviceChangeFlag success, status = %{public}d", deviceChangeCallbackflag_);
    return MSERR_OK;
}

int32_t PlayerServer::SetSubtitleCbDfxStatus(bool isRegistered)
{
    std::lock_guard<std::mutex> lock(mutex_);
    int32_t state = static_cast<int32_t>(lastOpStatus_.load());
    if (isRegistered) {
        RecordSubtitleCbRegister(CallType::AVPLAYER, appUid_, instanceId_, state);
    } else {
        RecordSubtitleCbUnregister(CallType::AVPLAYER, appUid_, instanceId_, state);
    }
    return MSERR_OK;
}

void PlayerServer::UpdateContinousBatchNo()
{
    seekContinousBatchNo_++;
}

bool PlayerServer::CheckState(PlayerOnInfoType type, int32_t extra)
{
    auto currState = std::static_pointer_cast<BaseState>(GetCurrState());
    bool isCompletedInfo = type == INFO_TYPE_STATE_CHANGE && extra == PlayerStates::PLAYER_PLAYBACK_COMPLETE;
    bool isEosInfo = type == INFO_TYPE_EOS;
    CHECK_AND_RETURN_RET_LOG(currState != stoppedState_ || !(isCompletedInfo || isEosInfo), false,
        "do not report completed or eos in stopped state");

    bool isErrorInfo = type == INFO_TYPE_STATE_CHANGE && extra == PlayerStates::PLAYER_STATE_ERROR;
    CHECK_AND_RETURN_RET_LOG(currState != idleState_ || !isErrorInfo, false, "do not report error in idle state");

    bool isPreparedInfo = type == INFO_TYPE_STATE_CHANGE && extra == PlayerStates::PLAYER_PREPARED;
    CHECK_AND_RETURN_RET_LOG(currState != idleState_ || !isPreparedInfo, false,
        "do not report prepared in idle state");
    return true;
}

int32_t PlayerServer::SetMaxAmplitudeCbStatus(bool status)
{
    maxAmplitudeCbStatus_ = status;
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    return playerEngine_->SetMaxAmplitudeCbStatus(maxAmplitudeCbStatus_);
}

bool PlayerServer::IsSeekContinuousSupported()
{
    MediaTrace trace("PlayerServer::IsSeekContinuousSupported");
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET(lastOpStatus_ == PLAYER_PREPARED || lastOpStatus_ == PLAYER_STARTED ||
        lastOpStatus_ == PLAYER_PLAYBACK_COMPLETE || lastOpStatus_ == PLAYER_PAUSED, false);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, false, "engine is nullptr");
    bool isSeekContinuousSupported = false;
    int32_t ret = playerEngine_->IsSeekContinuousSupported(isSeekContinuousSupported);
    return ret == MSERR_OK && isSeekContinuousSupported;
}

int32_t PlayerServer::SetSeiMessageCbStatus(bool status, const std::vector<int32_t> &payloadTypes)
{
    seiMessageCbStatus_ = status;
    payloadTypes_.assign(payloadTypes.begin(), payloadTypes.end());
    CHECK_AND_RETURN_RET_NOLOG(
        playerEngine_ == nullptr, playerEngine_->SetSeiMessageCbStatus(status, payloadTypes));
    return MSERR_OK;
}

uint32_t PlayerServer::GetMemoryUsage()
{
    int32_t version = apiVersion_.load();
    CHECK_AND_RETURN_RET_LOG(version >= MEMORY_USAGE_VERSION_ISOLATION, 0, "api version is low %{public}d", version);
    return totalMemoryUage_.load();
}

int32_t PlayerServer::SetReopenFd(int32_t fd)
{
    MEDIA_LOGD("Set reopenFd success, fd = %{public}d", fd);
    CHECK_AND_RETURN_RET_NOLOG(playerEngine_ == nullptr, playerEngine_->SetReopenFd(fd));
    return MSERR_OK;
}
 
int32_t PlayerServer::EnableCameraPostprocessing()
{
    MediaTrace::TraceBegin("PlayerServer::EnableCameraPostprocessing", FAKE_POINTER(this));
    std::lock_guard<std::mutex> lock(mutex_);
    bool isValidState = lastOpStatus_ == PLAYER_INITIALIZED;
    CHECK_AND_RETURN_RET_LOG(isValidState, MSERR_INVALID_STATE,
        "can not enable camera postProcessor, current state is %{public}d", static_cast<int32_t>(lastOpStatus_.load()));
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "engine is nullptr");

    CHECK_AND_RETURN_RET_LOG(!isVideoOutputEnabled_.load(), MSERR_INVALID_OPERATION,
        "camera postprocessing is mutually exclusive with side output");

    isCameraPostprocessingEnabled_.store(true);
    return playerEngine_->EnableCameraPostprocessing();
}

int32_t PlayerServer::SetCameraPostprocessing(bool isOpen)
{
    MediaTrace::TraceBegin("PlayerServer::SetCameraPostprocessing", FAKE_POINTER(this));
    std::lock_guard<std::mutex> lock(mutex_);
    bool isSupportOpenPostProcess = lastOpStatus_ == PLAYER_PREPARED || lastOpStatus_ == PLAYER_PAUSED ||
        lastOpStatus_ == PLAYER_PLAYBACK_COMPLETE;
    CHECK_AND_RETURN_RET_LOG(isSupportOpenPostProcess, MSERR_INVALID_OPERATION, "last status is not prepared");
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    return playerEngine_->SetCameraPostprocessing(isOpen);
}

int32_t PlayerServer::EnableReportMediaProgress(bool enable)
{
    std::lock_guard<std::mutex> lock(mutex_);
    enableReportMediaProgress_ = enable;
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    return playerEngine_->EnableReportMediaProgress(enableReportMediaProgress_);
}

int32_t PlayerServer::EnableReportAudioInterrupt(bool enable)
{
    std::lock_guard<std::mutex> lock(mutex_);
    enableReportAudioInterrupt_ = enable;
    if (playerCb_ != nullptr) {
        playerCb_->SetInterruptListenerFlag(enableReportAudioInterrupt_);
    }
    return MSERR_OK;
}

int32_t PlayerServer::ForceLoadVideo(bool status)
{
    std::lock_guard<std::mutex> lock(mutex_);
    isForceLoadVideo_ = status;
    auto forceLoadVideoTask = std::make_shared<TaskHandler<int32_t>>([this, status]() {
        MediaTrace trace("PlayerServer::ForceLoadVideo");
        CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, taskMgr_.MarkTaskDone("ForceLoadVideo done"),
            "ForceLoadVideo failed, playerEngine is nullptr");
        auto res = playerEngine_->ForceLoadVideo(status);
        MEDIA_LOGI("ForceLoadVideo %{public}d", status);
        taskMgr_.MarkTaskDone("ForceLoadVideo done");
        return res;
    });
    taskMgr_.LaunchTask(forceLoadVideoTask, PlayerServerTaskType::LIGHT_TASK, "ForceLoadVideo");
    return MSERR_OK;
}

int32_t PlayerServer::SetLoudnessGain(float loudnessGain)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine is nullptr");
    constexpr float maxLoudnessGain = 24.0f;
    constexpr float minLoudnessGain = -90.0f;
    if ((loudnessGain < minLoudnessGain) || (loudnessGain > maxLoudnessGain)) {
        MEDIA_LOGE("SetLoudnessGain failed, the loudnessGain should be set to a value ranging from -90 to 24");
        return MSERR_INVALID_OPERATION;
    }
    
    if (GetCurrState() == preparedState_ || GetCurrState() == playingState_ ||
        GetCurrState() == pausedState_ || GetCurrState() == playbackCompletedState_ ||
        GetCurrState() == stoppedState_) {
        return playerEngine_->SetLoudnessGain(loudnessGain);
    }
    MEDIA_LOGW("SetLoudnessGain called in invalid state");
    return MSERR_INVALID_OPERATION;
}

int32_t PlayerServer::GetGlobalInfo(std::shared_ptr<Meta> &globalInfo)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    MEDIA_LOGI("PlayerServer GetGlobalInfo in");
    int32_t ret = playerEngine_->GetGlobalInfo(globalInfo);
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "get global info failed");
    return MSERR_OK;
}

int32_t PlayerServer::GetMediaDescription(Format &format)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    if (GetCurrState() != preparedState_ && GetCurrState() != playingState_ &&
        GetCurrState() != pausedState_ && GetCurrState() != playbackCompletedState_ &&
        GetCurrState() != stoppedState_) {
        MEDIA_LOGW("GetMediaDescription called in invalid state");
        return MSERR_INVALID_OPERATION;
    }
    return playerEngine_->GetMediaDescription(format);
}

int32_t PlayerServer::GetTrackDescription(Format &format, uint32_t trackIndex)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    if (GetCurrState() != preparedState_ && GetCurrState() != playingState_ &&
        GetCurrState() != pausedState_ && GetCurrState() != playbackCompletedState_ &&
        GetCurrState() != stoppedState_) {
        MEDIA_LOGW("GetTrackDescription called in invalid state");
        return MSERR_INVALID_OPERATION;
    }
    std::vector<Format> trackInfo;
    playerEngine_->GetVideoTrackInfo(trackInfo);
    playerEngine_->GetAudioTrackInfo(trackInfo);
    playerEngine_->GetSubtitleTrackInfo(trackInfo);
    for (const auto& item: trackInfo) {
        int32_t index = -1;
        item.GetIntValue("track_index", index);
        if (index == static_cast<int32_t>(trackIndex)) {
            format = item;
            return MSERR_OK;
        }
    }
    return MSERR_INVALID_OPERATION;
}

int32_t PlayerServer::SetDolbyPassthroughCallback(std::shared_ptr<IDolbyPassthrough> &dolbyPassthrough)
{
    MEDIA_LOGI("PlayerServer::SetDolbyPassthroughCallback");
    std::lock_guard<std::mutex> lock(mutex_);
    MediaTrace trace("PlayerServer::SetDolbyPassthroughCallback");
    CHECK_AND_RETURN_RET_LOG(dolbyPassthrough != nullptr, MSERR_INVALID_VAL, "dolbyPassthrough is nullptr");
    GetPassthroughCallbackInstance() = dolbyPassthrough;
    dolbyList_.clear();
    return MSERR_OK;
}

std::shared_ptr<IDolbyPassthrough>& PlayerServer::GetPassthroughCallbackInstance()
{
    MEDIA_LOGI("RegisterAudioPassthroughCallback: GetPassthroughCallbackInstance");
    static auto instance = std::shared_ptr<IDolbyPassthrough>();
    return instance;
}

bool PlayerServer::IsAudioPass(const char* mimeType)
{
    MEDIA_LOGI("PlayerFilterCallback IsAudioPassthrough.");
    CHECK_AND_RETURN_RET(mimeType != nullptr, false);
    auto callbackInstance = PlayerServer::GetPassthroughCallbackInstance();
    CHECK_AND_RETURN_RET(callbackInstance != nullptr, false);
    return callbackInstance->IsAudioPass(mimeType);
}

std::vector<std::string> PlayerServer::GetDolbyList()
{
    MEDIA_LOGI("PlayerFilterCallback GetDolbyList.");
    auto callbackInstance = PlayerServer::GetPassthroughCallbackInstance();
    CHECK_AND_RETURN_RET(callbackInstance != nullptr, {});
    if (dolbyList_.empty()) {
        dolbyList_ = callbackInstance->GetList();
    }
    return dolbyList_;
}

bool PlayerServer::IsLiveSeek()
{
    CHECK_AND_RETURN_RET(playerEngine_ != nullptr, false);
    return playerEngine_->IsLiveSeek();
}

int32_t PlayerServer::SetVideoOutput(sptr<Surface> surface)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(surface != nullptr, MSERR_INVALID_VAL, "surface is nullptr");

    CHECK_AND_RETURN_RET_LOG(!isSuperResolutionEnabled_.load() && !isCameraPostprocessingEnabled_.load(),
        MSERR_INVALID_OPERATION, "side output is mutually exclusive with super resolution or camera postprocessing");
 
    bool isRightStatus = lastOpStatus_ == PLAYER_IDLE ||
        lastOpStatus_ == PLAYER_INITIALIZED;
    
    if (!isRightStatus) {
        MEDIA_LOGE("current state: %{public}s, can not SetVideoOutput", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }
    
    isVideoOutputEnabled_.store(true);
    MEDIA_LOGD("PlayerServer SetVideoOutput in");
    {
        std::lock_guard<std::mutex> surfaceLock(sideOutputSurfaceMutex_);
        sideOutputSurface_ = surface;
    }
    auto task = std::make_shared<TaskHandler<void>>([this]() {
        std::lock_guard<std::mutex> surfaceLock(sideOutputSurfaceMutex_);
        (void)playerEngine_->SetVideoOutput(sideOutputSurface_);
        taskMgr_.MarkTaskDone("SetVideoOutput done");
    });
    int32_t ret = taskMgr_.SetVideoSurfaeTask(task, "SetVideoOutput");
    CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, ret, "SetVideoOutput launch task failed");
    return MSERR_OK;
}
 
int32_t PlayerServer::GetVideoSample(int32_t &outputResult)
{
    std::lock_guard<std::mutex> lock(mutex_);

    CHECK_AND_RETURN_RET_LOG(!isSuperResolutionEnabled_.load() && !isCameraPostprocessingEnabled_.load(),
        MSERR_INVALID_OPERATION, "side output is mutually exclusive with super resolution or camera postprocessing");
 
    bool isRightStatus = (lastOpStatus_ == PLAYER_STARTED || lastOpStatus_ == PLAYER_PAUSED);
    
    if (!isRightStatus) {
        MEDIA_LOGE("current state: %{public}s, can not GetVideoSample", GetStatusDescription(lastOpStatus_).c_str());
        return MSERR_INVALID_OPERATION;
    }

    CHECK_AND_RETURN_RET_LOG(!isInSeekContinous_, MSERR_INVALID_OPERATION,
        "calling this interface is not supported during seeking");

    if (playerEngine_ != nullptr) {
        int ret = playerEngine_->GetVideoSample(outputResult);
        CHECK_AND_RETURN_RET_LOG(ret == MSERR_OK, MSERR_INVALID_OPERATION, "Engine GetVideoSample Failed!");
    }
    MEDIA_LOGD("PlayerServer GetVideoSample %{public}d", outputResult);
    return MSERR_OK;
}

int32_t PlayerServer::SetPCMCallback(const std::shared_ptr<IPCMCallback> &callback)
{
    std::lock_guard<std::mutex> lock(mutex_);
    bool isValidState = lastOpStatus_ == PLAYER_IDLE || lastOpStatus_ == PLAYER_INITIALIZED;
    CHECK_AND_RETURN_RET_LOG(isValidState, MSERR_INVALID_STATE,
        "can not SetPCMCallback, current state is %{public}d", static_cast<int32_t>(lastOpStatus_.load()));

    // If playerEngine_ not init, save pcmCallback_ and use it after playerEngine_ init
    pcmCallback_ = callback;
    CHECK_AND_RETURN_RET_NOLOG(playerEngine_ == nullptr, playerEngine_->SetPCMCallback(callback));
    return MSERR_OK;
}

int32_t PlayerServer::SetPCMOutputStatus(bool isEnable)
{
    std::lock_guard<std::mutex> lock(mutex_);
    bool isValidState = lastOpStatus_ == PLAYER_IDLE || lastOpStatus_ == PLAYER_INITIALIZED;
    CHECK_AND_RETURN_RET_LOG(isValidState, MSERR_INVALID_STATE,
        "can not SetPCMOutputStatus, current state is %{public}d", static_cast<int32_t>(lastOpStatus_.load()));

    // If playerEngine_ not init, save isPcmOutputEnable_ and use it after playerEngine_ init
    isPcmOutputEnable_ = isEnable;
    CHECK_AND_RETURN_RET_NOLOG(playerEngine_ == nullptr, playerEngine_->SetPCMOutputStatus(isEnable));
    return MSERR_OK;
}

int32_t PlayerServer::SetPCMProcessorStatus(bool isEnable)
{
    std::lock_guard<std::mutex> lock(mutex_);
    bool isValidState = lastOpStatus_ == PLAYER_IDLE || lastOpStatus_ == PLAYER_INITIALIZED;
    CHECK_AND_RETURN_RET_LOG(isValidState, MSERR_INVALID_STATE,
        "can not SetPCMProcessorStatus, current state is %{public}d", static_cast<int32_t>(lastOpStatus_.load()));

    // If playerEngine_ not init, save isPcmProcessorEnable_ and use it after playerEngine_ init
    isPcmProcessorEnable_ = isEnable;
    CHECK_AND_RETURN_RET_NOLOG(playerEngine_ == nullptr, playerEngine_->SetPCMProcessorStatus(isEnable));
    return MSERR_OK;
}

int32_t PlayerServer::SetPCMProcessorMaxLen(int32_t maxProcessedPcmLen)
{
    std::lock_guard<std::mutex> lock(mutex_);
    bool isValidState = lastOpStatus_ == PLAYER_IDLE || lastOpStatus_ == PLAYER_INITIALIZED;
    CHECK_AND_RETURN_RET_LOG(isValidState, MSERR_INVALID_STATE,
        "can not SetPCMProcessorMaxLen, current state is %{public}d", static_cast<int32_t>(lastOpStatus_.load()));

    // If playerEngine_ not init, save maxProcessedPcmLen_ and use it after playerEngine_ init
    maxProcessedPcmLen_ = maxProcessedPcmLen;
    CHECK_AND_RETURN_RET_NOLOG(playerEngine_ == nullptr, playerEngine_->SetPCMProcessorMaxLen(maxProcessedPcmLen));
    return MSERR_OK;
}

void PlayerServer::InitPcmCallback()
{
    CHECK_AND_RETURN_LOG(playerEngine_ != nullptr, "PlayerEngine is nullptr.");
    int32_t ret = playerEngine_->SetPCMCallback(pcmCallback_);
    TRUE_LOG(ret != MSERR_OK, MEDIA_LOGW, "PlayerEngine SetPCMOutputCallback failed, ret %{public}d", ret);

    ret = playerEngine_->SetPCMOutputStatus(isPcmOutputEnable_);
    TRUE_LOG(ret != MSERR_OK, MEDIA_LOGW, "PlayerEngine SetPCMOutputStatus failed, ret %{public}d", ret);

    ret = playerEngine_->SetPCMProcessorStatus(isPcmProcessorEnable_);
    TRUE_LOG(ret != MSERR_OK, MEDIA_LOGW, "PlayerEngine SetPCMProcessorStatus failed, ret %{public}d", ret);

    ret = playerEngine_->SetPCMProcessorMaxLen(maxProcessedPcmLen_);
    TRUE_LOG(ret != MSERR_OK, MEDIA_LOGW, "PlayerEngine SetPCMProcessorMaxLen failed, ret %{public}d", ret);
}

int32_t PlayerServer::AddAdsMediaSource(const std::shared_ptr<AVMediaSource> &mediaSource,
    int64_t startMs, std::string &outId)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    MEDIA_LOGI("PlayerServer AddAdsMediaSource in, startMs: %{public}" PRId64, startMs);
    return playerEngine_->AddAdsMediaSource(mediaSource, startMs, outId);
}

int32_t PlayerServer::RemoveAdsMediaSource(const std::string &id)
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    MEDIA_LOGI("PlayerServer RemoveAdsMediaSource in, id: %{public}s", id.c_str());
    return playerEngine_->RemoveAdsMediaSource(id);
}

int32_t PlayerServer::SkipCurrentAdsMediaSource()
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    MEDIA_LOGI("PlayerServer SkipCurrentAdsMediaSource in");
    return playerEngine_->SkipCurrentAdsMediaSource();
}

int32_t PlayerServer::DisableAllAdsMediaSource()
{
    std::lock_guard<std::mutex> lock(mutex_);
    CHECK_AND_RETURN_RET_LOG(playerEngine_ != nullptr, MSERR_NO_MEMORY, "playerEngine_ is nullptr");
    MEDIA_LOGI("PlayerServer DisableAllAdsMediaSource in");
    return playerEngine_->DisableAllAdsMediaSource();
}
} // namespace Media
} // namespace OHOS
