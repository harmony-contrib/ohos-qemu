/*
 * Copyright (c) 2023-2026 Huawei Device Co., Ltd.
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


#include "player.h"
#define HST_LOG_TAG "HiPlayer"

#include "hiplayer_impl.h"

#include <chrono>
#include <shared_mutex>

#include "audio_device_descriptor.h"
#include "common/log.h"
#include "common/media_source.h"
#include "directory_ex.h"
#include "filter/filter_factory.h"
#include "media_errors.h"
#include "plugin/plugin_event.h"
#include "osal/task/jobutils.h"
#include "osal/task/pipeline_threadpool.h"
#include "osal/task/task.h"
#include "osal/utils/dump_buffer.h"
#include "plugin/plugin_time.h"
#include "media_dfx.h"
#include "media_utils.h"
#include "meta_utils.h"
#include "meta/media_types.h"
#include "meta/format.h"
#include "meta/any.h"
#include "param_wrapper.h"
#include "osal/utils/steady_clock.h"
#include "scoped_timer.h"
#include "dfx_agent.h"

namespace {
constexpr OHOS::HiviewDFX::HiLogLabel LABEL = { LOG_CORE, LOG_DOMAIN_SYSTEM_PLAYER, "HiPlayer" };
const float MAX_MEDIA_VOLUME = 1.0f; // standard interface volume is between 0 to 1.
const int32_t AUDIO_SINK_MAX_LATENCY = 400; // audio sink write latency ms
const int32_t FRAME_RATE_UNIT_MULTIPLE = 100; // the unit of frame rate is frames per 100s
const int32_t PLAYING_SEEK_WAIT_TIME = 200; // wait up to 200 ms for new frame after seek in playing.
const int32_t FLV_LIVE_PREPARE_WAIT_TIME = 30000; // wait max 30s for flv live stream with play water line.
const int64_t PLAY_RANGE_DEFAULT_VALUE = -1; // play range default value.
const int64_t SAMPLE_AMPLITUDE_INTERVAL = 100;
const int64_t REPORT_PROGRESS_INTERVAL = 100; // progress interval is 100ms
const double FRAME_RATE_DEFAULT = -1.0;
const double FRAME_RATE_FOR_SEEK_PERFORMANCE = 2000.0;
const double TIME_CONVERSION_UNIT  = 1000;
const double CHECK_DELAY_INTERVAL  = 200;
constexpr int32_t BUFFERING_LOG_FREQUENCY = 5;
constexpr int32_t NOTIFY_BUFFERING_END_PARAM = 0;
constexpr int64_t FIRST_FRAME_FRAME_REPORT_DELAY_MS = 50;
constexpr double PAUSE_LONG_TIME_FACTOR = 5;
constexpr int64_t DEMUXER_INIT_WARNING_MS = 50;
static const std::unordered_set<OHOS::AudioStandard::StreamUsage> FOCUS_EVENT_USAGE_SET = {
    OHOS::AudioStandard::StreamUsage::STREAM_USAGE_UNKNOWN,
    OHOS::AudioStandard::StreamUsage::STREAM_USAGE_MEDIA,
    OHOS::AudioStandard::StreamUsage::STREAM_USAGE_MUSIC,
    OHOS::AudioStandard::StreamUsage::STREAM_USAGE_MOVIE,
    OHOS::AudioStandard::StreamUsage::STREAM_USAGE_GAME,
    OHOS::AudioStandard::StreamUsage::STREAM_USAGE_AUDIOBOOK,
};
const std::string TOTAL_MEMORY_SIZE = "TOTAL_MEMORY_SIZE";
const std::string DEMUXER_PLUGIN = "DEMUXER_PLUGIN";
constexpr uint32_t MEMORY_REPORT_LIMITE = 100 * 1024; // 100MB
constexpr uint32_t MAX_DEMUXER_MEMORY_USAGE = 50 * 1024; // 50MB
constexpr uint32_t MEMORY_B_TO_KB = 1024;
static const std::unordered_map<std::string, uint32_t> MEMORY_USAGE_REPORT_LIMITS = {
    { DEMUXER_PLUGIN, MAX_DEMUXER_MEMORY_USAGE }
};

static void CopyStringDetail(const std::map<std::string, OHOS::Media::Any>& details,
    const std::string_view& key, OHOS::Media::Format& format)
{
    auto it = details.find(std::string(key));
    if (it != details.end()) {
        format.PutStringValue(key, OHOS::Media::AnyCast<std::string>(it->second));
    }
}

static void CopyBoolDetail(const std::map<std::string, OHOS::Media::Any>& details,
    const std::string_view& key, OHOS::Media::Format& format)
{
    auto it = details.find(std::string(key));
    if (it != details.end()) {
        format.PutIntValue(key, static_cast<int32_t>(OHOS::Media::AnyCast<bool>(it->second)));
    }
}

static void CopyIntDetail(const std::map<std::string, OHOS::Media::Any>& details,
    const std::string_view& key, OHOS::Media::Format& format)
{
    auto it = details.find(std::string(key));
    if (it != details.end()) {
        format.PutIntValue(key, static_cast<int32_t>(OHOS::Media::AnyCast<int64_t>(it->second)));
    }
}

static void CopyLongDetail(const std::map<std::string, OHOS::Media::Any>& details,
    const std::string_view& key, OHOS::Media::Format& format)
{
    auto it = details.find(std::string(key));
    if (it != details.end()) {
        format.PutLongValue(key, OHOS::Media::AnyCast<int64_t>(it->second));
    }
}
}

namespace OHOS {
namespace Media {
using namespace Pipeline;
class PlayerEventReceiver : public EventReceiver {
public:
    explicit PlayerEventReceiver(HiPlayerImpl* hiPlayerImpl, std::string playerId)
    {
        MEDIA_LOG_I("PlayerEventReceiver ctor called.");
        std::unique_lock<std::shared_mutex> lk(cbMutex_);
        hiPlayerImpl_ = hiPlayerImpl;
        task_ = std::make_unique<Task>("PlayerEventReceiver", playerId, TaskType::GLOBAL,
            OHOS::Media::TaskPriority::HIGH, false);
    }

    void OnEvent(const Event &event) override
    {
        MEDIA_LOG_DD("PlayerEventReceiver OnEvent.");
        task_->SubmitJobOnce([this, event] {
            std::shared_lock<std::shared_mutex> lk(cbMutex_);
            FALSE_RETURN(hiPlayerImpl_ != nullptr);
            hiPlayerImpl_->OnEvent(event);
        });
    }

    void OnDfxEvent(const DfxEvent &event) override
    {
        MEDIA_LOG_DD("PlayerEventReceiver OnDfxEvent.");
        std::shared_lock<std::shared_mutex> lk(cbMutex_);
        FALSE_RETURN(hiPlayerImpl_ != nullptr);
        hiPlayerImpl_->HandleDfxEvent(event);
    }

    void NotifyRelease() override
    {
        MEDIA_LOG_D("PlayerEventReceiver NotifyRelease.");
        std::unique_lock<std::shared_mutex> lk(cbMutex_);
        hiPlayerImpl_ = nullptr;
    }

    void OnMemoryUsageEvent(const DfxEvent& event) override
    {
        MEDIA_LOG_D("PlayerEventReceiver OnMemoryUsageEvent.");
        task_->SubmitJobOnce([this, event] {
            std::shared_lock<std::shared_mutex> lk(cbMutex_);
            FALSE_RETURN(hiPlayerImpl_ != nullptr);
            hiPlayerImpl_->HandleMemoryUsageEvent(event);
        });
    }

private:
    std::shared_mutex cbMutex_ {};
    HiPlayerImpl* hiPlayerImpl_;
    std::unique_ptr<Task> task_;
};

class PlayerFilterCallback : public FilterCallback {
public:
    explicit PlayerFilterCallback(HiPlayerImpl* hiPlayerImpl)
    {
        MEDIA_LOG_I("PlayerFilterCallback ctor called.");
        std::unique_lock<std::shared_mutex> lk(cbMutex_);
        hiPlayerImpl_ = hiPlayerImpl;
    }

    Status OnCallback(const std::shared_ptr<Filter>& filter, FilterCallBackCommand cmd,
        OHOS::Media::Pipeline::StreamType outType) override
    {
        MEDIA_LOG_D("PlayerFilterCallback OnCallback.");
        std::shared_lock<std::shared_mutex> lk(cbMutex_);
        FALSE_RETURN_V(hiPlayerImpl_ != nullptr, Status::OK); // hiPlayerImpl_ is destructed
        return hiPlayerImpl_->OnCallback(filter, cmd, outType);
    }

    bool IsAudioPassthroughCallback(const char* mimeType) override
    {
        MEDIA_LOG_I("PlayerFilterCallback IsAudioPassthrough.");
        std::shared_lock<std::shared_mutex> lk(cbMutex_);
        FALSE_RETURN_V(hiPlayerImpl_ != nullptr, false);
        FALSE_RETURN_V(mimeType != nullptr, false);
        return hiPlayerImpl_->IsAudioPass(mimeType);
    }

    std::vector<std::string> GetDolbyListCallback() override
    {
        MEDIA_LOG_I("PlayerFilterCallback GetDolbyList.");
        std::shared_lock<std::shared_mutex> lk(cbMutex_);
        FALSE_RETURN_V(hiPlayerImpl_ != nullptr, {});
        return hiPlayerImpl_->GetDolbyList();
    }

    void NotifyRelease() override
    {
        MEDIA_LOG_D("PlayerEventReceiver NotifyRelease.");
        std::unique_lock<std::shared_mutex> lk(cbMutex_);
        hiPlayerImpl_ = nullptr;
    }

    void HandleVideoCodecChange(const std::shared_ptr<Meta>& meta, bool& isCodecChanged, bool isSmoothSwitch) override
    {
        MEDIA_LOG_I("PlayerFilterCallback HandleVideoCodecChange isSmoothSwitch = %{public}d", isSmoothSwitch);
        isCodecChanged = false;
        std::shared_lock<std::shared_mutex> lk(cbMutex_);
        FALSE_RETURN(hiPlayerImpl_ != nullptr);
        return hiPlayerImpl_->HandleVideoCodecChange(meta, isCodecChanged, isSmoothSwitch);
    }

private:
    std::shared_mutex cbMutex_ {};
    HiPlayerImpl* hiPlayerImpl_;
};

HiPlayerImpl::HiPlayerImpl(int32_t appUid, int32_t appPid, uint32_t appTokenId, uint64_t appFullTokenId)
    : appUid_(appUid), appPid_(appPid), appTokenId_(appTokenId), appFullTokenId_(appFullTokenId)
{
    MEDIA_LOG_D("hiPlayerImpl ctor appUid " PUBLIC_LOG_D32 " appPid " PUBLIC_LOG_D32
        " appTokenId %{private}" PRIu32 " appFullTokenId %{private}" PRIu64,
        appUid_, appPid_, appTokenId_, appFullTokenId_);
    playerId_ = std::string("HiPlayer_") + std::to_string(OHOS::Media::Pipeline::Pipeline::GetNextPipelineId());
    pipeline_ = std::make_shared<OHOS::Media::Pipeline::Pipeline>();
    syncManager_ = std::make_shared<MediaSyncManager>();
    callbackLooper_.SetPlayEngine(this, playerId_);
    liveController_.CreateTask(playerId_);
    bundleName_ = GetClientBundleName(appUid);
    dfxAgent_ = std::make_shared<DfxAgent>(playerId_, bundleName_);
    dfxAgent_->SetMetricsCallback([this](std::weak_ptr<DfxAgent> agent, const DfxEvent& event) {
        auto info = AnyCast<AVMetricsEvent>(event.param);
        FALSE_RETURN(syncManager_ != nullptr);
        int64_t playbackPosMs = Plugins::HstTime2Ms(syncManager_->GetMediaTimeNow());
        info.playbackPosition = playbackPosMs;
        HandleMetricsEventByType(info);
    });
}

void HiPlayerImpl::HandleMetricsEventByType(const AVMetricsEvent& infoCopy)
{
    MEDIA_LOG_I_SHORT("infoCopy.metricsEventType: " PUBLIC_LOG_D32, infoCopy.metricsEventType);
    switch (infoCopy.metricsEventType) {
        case AVMetricsEventType::AV_METRICS_EVENT_TYPE_LOADINGRATE_CHANGE: {
            HandleLoadingBitrateEvent(infoCopy);
            break;
        }
        case AVMetricsEventType::AV_METRICS_EVENT_TYPE_LOADING_ERROR: {
            HandleLoadingErrorEvent(infoCopy);
            break;
        }
        case AVMetricsEventType::AV_METRICS_EVENT_TYPE_CONTENT_CHANGED: {
            HandleMediaChangedEvent(infoCopy);
            break;
        }
        case AVMetricsEventType::AV_METRICS_EVENT_TYPE_CONTENT_DISCONTINUITY: {
            HandleMediaDiscontinueEvent(infoCopy);
            break;
        }
        case AVMetricsEventType::AV_METRICS_EVENT_TYPE_AUDIO_ABNORMAL: {
            HandleAudioStatusEvent(infoCopy);
            break;
        }
        case AVMetricsEventType::AV_METRICS_EVENT_TYPE_CODEC_ABNORMAL: {
            HandleCodecAbnormalEvent(infoCopy);
            break;
        }
        case AVMetricsEventType::AV_METRICS_EVENT_TYPE_LIP_ASYNC: {
            HandleLipAsyncEvent(infoCopy);
            break;
        }
        case AVMetricsEventType::AV_METRICS_EVENT_TYPE_STALLING: {
            HandleStallingEvent(infoCopy);
            break;
        }
        default:
            break;
    }
}

void HiPlayerImpl::HandleStallingEvent(const AVMetricsEvent& infoCopy)
{
    int64_t duration = AnyCast<int64_t>(infoCopy.details.at("Duration"));
    int32_t mediaType = AnyCast<int32_t>(infoCopy.details.at("MediaType"));
    if (callbackLooper_.IsStarted()) {
        Format format;
        format.PutIntValue(PlayerKeys::PLAYER_METRICS_EVENT_TYPE,
            static_cast<int32_t>(AV_METRICS_EVENT_TYPE_STALLING));
        format.PutLongValue(PlayerKeys::PLAYER_STALLING_TIMESTAMP, infoCopy.timeStamp);
        format.PutLongValue(PlayerKeys::PLAYER_STALLING_TIMELINE, infoCopy.playbackPosition);
        format.PutLongValue(PlayerKeys::PLAYER_STALLING_DURATION, duration);
        format.PutIntValue(PlayerKeys::PLAYER_STALLING_MEDIA_TYPE, static_cast<int32_t>(mediaType));
        MEDIA_LOG_I("sending stalling event: timestamp=%{public}" PRId64 ", timeline=%{public}" PRId64\
            ", duration=%{public}" PRId64 ", mediaType=%{public}d",
            infoCopy.timeStamp, infoCopy.playbackPosition, duration, static_cast<int32_t>(mediaType));
        callbackLooper_.OnInfo(INFO_TYPE_METRICS_EVENT, 0, format);
    }
}

HiPlayerImpl::~HiPlayerImpl()
{
    MEDIA_LOG_D("~HiPlayerImpl dtor called");
    {
        std::unique_lock<std::mutex> lock(pipelineMutex_);
        if (pipeline_ != nullptr && demuxer_) {
            pipeline_->RemoveHeadFilter(demuxer_);
        }
    }
    if (dfxAgent_ != nullptr) {
        dfxAgent_.reset();
    }
    if (playerEventReceiver_ != nullptr) {
        playerEventReceiver_->NotifyRelease();
    }
    if (playerFilterCallback_ != nullptr) {
        playerFilterCallback_->NotifyRelease();
    }
    PipeLineThreadPool::GetInstance().DestroyThread(playerId_);
}

void HiPlayerImpl::ReleaseInner()
{
    pipeline_->Stop();
    audioSink_.reset();
#ifdef SUPPORT_VIDEO
    if (videoDecoder_) {
        interruptMonitor_->DeregisterListener(videoDecoder_);
        videoDecoder_.reset();
    }
#endif
    if (subtitleSink_) {
        subtitleSink_.reset();
    }
    syncManager_.reset();
    if (demuxer_) {
        pipeline_->RemoveHeadFilter(demuxer_);
    }
}

Status HiPlayerImpl::Init()
{
    MediaTrace trace("HiPlayerImpl::Init");
    MEDIA_LOG_I("Init start");
    auto playerEventReceiver = std::make_shared<PlayerEventReceiver>(this, playerId_);
    auto playerFilterCallback = std::make_shared<PlayerFilterCallback>(this);
    auto interruptMonitor = std::make_shared<InterruptMonitor>();
    FALSE_RETURN_V_MSG_E(playerEventReceiver != nullptr && playerFilterCallback != nullptr &&
        interruptMonitor != nullptr, Status::ERROR_NO_MEMORY, "fail to init hiplayImpl");
    playerEventReceiver_ = playerEventReceiver;
    playerFilterCallback_ = playerFilterCallback;
    interruptMonitor_ = interruptMonitor;
    MEDIA_LOG_D("pipeline init");
    pipeline_->Init(playerEventReceiver_, playerFilterCallback_, playerId_);
    MEDIA_LOG_D("pipeline Init out");
    for (std::pair<std::string, bool>& item: completeState_) {
        item.second = false;
    }
    GetDumpFlag();
    return Status::OK;
}

void HiPlayerImpl::GetDumpFlag()
{
    const std::string dumpTag = "sys.media.player.dump.enable";
    std::string dumpEnable;
    int32_t dumpRes = OHOS::system::GetStringParameter(dumpTag, dumpEnable, "false");
    isDump_ = (dumpEnable == "true");
    MEDIA_LOG_D_SHORT("get dump flag, dumpRes: %{public}d, isDump_: %{public}d", dumpRes, isDump_);
}

void HiPlayerImpl::SetDefaultAudioRenderInfo(const std::vector<std::shared_ptr<Meta>> &trackInfos)
{
    MEDIA_LOG_D_SHORT("SetDefaultAudioRenderInfo");
    bool hasVideoTrack = false;
    for (size_t index = 0; index < trackInfos.size(); index++) {
        std::shared_ptr<Meta> meta = trackInfos[index];
        if (meta == nullptr) {
            continue;
        }
        std::string trackMime;
        if (!meta->GetData(Tag::MIME_TYPE, trackMime)) {
            continue;
        }
        if (trackMime.find("video/") == 0) {
            hasVideoTrack = true;
        }
    }
    Plugins::AudioRenderInfo audioRenderInfo;
    if (hasVideoTrack) {
        audioRenderInfo = {AudioStandard::CONTENT_TYPE_MOVIE, AudioStandard::STREAM_USAGE_MOVIE, 0};
    } else {
        audioRenderInfo = {AudioStandard::CONTENT_TYPE_MUSIC, AudioStandard::STREAM_USAGE_MUSIC, 0};
    }
    if (audioRenderInfo_ == nullptr) {
        audioRenderInfo_ = std::make_shared<Meta>();
        audioRenderInfo_->SetData(Tag::AUDIO_RENDER_INFO, audioRenderInfo);
    }
}

int32_t HiPlayerImpl::GetRealPath(const std::string &url, std::string &realUrlPath) const
{
    std::string fileHead = "file://";
    std::string tempUrlPath;

    if (url.find(fileHead) == 0 && url.size() > fileHead.size()) {
        tempUrlPath = url.substr(fileHead.size());
    } else {
        tempUrlPath = url;
    }
    if (tempUrlPath.find("..") != std::string::npos) {
        MEDIA_LOG_E("invalid url. The Url (%{private}s) path may be invalid.", tempUrlPath.c_str());
        return MSERR_FILE_ACCESS_FAILED;
    }
    bool ret = PathToRealPath(tempUrlPath, realUrlPath);
    if (!ret) {
        MEDIA_LOG_E("invalid url. The Url (%{private}s) path may be invalid.", url.c_str());
        return MSERR_OPEN_FILE_FAILED;
    }
    if (access(realUrlPath.c_str(), R_OK) != 0) {
        return MSERR_FILE_ACCESS_FAILED;
    }
    return MSERR_OK;
}

bool HiPlayerImpl::IsFileUrl(const std::string &url) const
{
    return url.find("://") == std::string::npos || url.find("file://") == 0;
}

bool HiPlayerImpl::IsNetworkUrl(const std::string &url) const
{
    return url.find("http") == 0 || url.find("https") == 0;
}

bool HiPlayerImpl::IsValidPlayRange(int64_t start, int64_t end) const
{
    if (start < PLAY_RANGE_DEFAULT_VALUE || end < PLAY_RANGE_DEFAULT_VALUE || end == 0) {
        return false;
    }
    if (pipelineStates_ == PlayerStates::PLAYER_INITIALIZED) {
        return true;
    }
    if ((end == PLAY_RANGE_DEFAULT_VALUE) && (start < durationMs_.load())) {
        return true;
    }
    if (start >= end || start >= durationMs_.load() || end > durationMs_.load()) {
        return false;
    }
    return true;
}

bool HiPlayerImpl::IsInValidSeekTime(int64_t seekPos)
{
    if (endTimeWithMode_ == PLAY_RANGE_DEFAULT_VALUE) {
        return false;
    }
    int64_t seekTime = static_cast<int64_t>(seekPos);
    if (startTimeWithMode_ == PLAY_RANGE_DEFAULT_VALUE) {
        if (seekTime > endTimeWithMode_) {
            endTimeWithMode_ = PLAY_RANGE_DEFAULT_VALUE;
            pipeline_->SetPlayRange(startTimeWithMode_, endTimeWithMode_);
        }
        return false;
    }
    return seekTime < startTimeWithMode_ || seekTime > endTimeWithMode_;
}

int64_t HiPlayerImpl::GetPlayStartTime()
{
    if (playRangeStartTime_ > PLAY_RANGE_DEFAULT_VALUE) {
        return playRangeStartTime_;
    }
    int64_t rePlayStartTime = 0;
    if (startTimeWithMode_ != PLAY_RANGE_DEFAULT_VALUE && endTimeWithMode_ != PLAY_RANGE_DEFAULT_VALUE) {
        rePlayStartTime = startTimeWithMode_;
    }
    return rePlayStartTime;
}

void HiPlayerImpl::SetInstancdId(uint64_t instanceId)
{
    instanceId_ = instanceId;
    if (dfxAgent_ != nullptr) {
        dfxAgent_->SetInstanceId(std::to_string(instanceId_));
    }
}

void HiPlayerImpl::SetApiVersion(int32_t apiVersion)
{
    apiVersion_ = apiVersion;
}

int32_t HiPlayerImpl::SetSource(const std::string& uri)
{
    MediaTrace trace("HiPlayerImpl::SetSource uri");
    MEDIA_LOG_D("HiPlayerImpl SetSource uri");
    CreateMediaInfo(CallType::AVPLAYER, appUid_, instanceId_);
    CreatePlaybackInfo(CallType::AVPLAYER, appUid_, instanceId_);
    CreateStallingInfo(CallType::AVPLAYER, appUid_, instanceId_);
    CreatePlayErrInfo(CallType::AVPLAYER, appUid_, instanceId_);
    playStatisticalInfo_.sourceUrl = "private";
    playStatisticalInfo_.sourceType = static_cast<int32_t>(SourceType::SOURCE_TYPE_URI);
    url_ = uri;
    PlayerDfxSourceType sourceType = PlayerDfxSourceType::DFX_SOURCE_TYPE_UNKNOWN;
    if (IsFileUrl(uri)) {
        std::string realUriPath;
        int32_t result = GetRealPath(uri, realUriPath);
        if (result != MSERR_OK) {
            CollectionErrorInfo(result, "SetSource error: GetRealPath error");
            return result;
        }
        url_ = "file://" + realUriPath;
        sourceType = PlayerDfxSourceType::DFX_SOURCE_TYPE_URL_FILE;
        SetPerfRecEnabled(true);
    }
    if (IsNetworkUrl(uri)) {
        isNetWorkPlay_ = true;
        sourceType = PlayerDfxSourceType::DFX_SOURCE_TYPE_URL_NETWORK;
    }
    if (url_.find("fd://") == 0) {
        sourceType = PlayerDfxSourceType::DFX_SOURCE_TYPE_URL_FD;
        SetPerfRecEnabled(true);
    }
    if (dfxAgent_ != nullptr) {
        dfxAgent_->SetSourceType(sourceType);
        sourceType_ = sourceType;
    }
    hasExtSub_ = false;
    pipelineStates_ = PlayerStates::PLAYER_INITIALIZED;
    int ret = TransStatus(Status::OK);
    playStatisticalInfo_.errCode = ret;
    ResetEnableCameraPostProcess();
    return ret;
}

int32_t HiPlayerImpl::SetMediaSource(const std::shared_ptr<AVMediaSource> &mediaSource, AVPlayStrategy strategy)
{
    MediaTrace trace("HiPlayerImpl::SetMediaSource.");
    MEDIA_LOG_I("SetMediaSource entered media source stream");
    CreatePlaybackInfo(CallType::AVPLAYER, appUid_, instanceId_);
    CreateStallingInfo(CallType::AVPLAYER, appUid_, instanceId_);
    if (!ValidateAndInitMediaSource(mediaSource)) {     // 提取关键成员
        return MSERR_INVALID_VAL;
    }
    this->ExtractStrategyParams(strategy);
    SetFlvLiveParams(strategy);
    FALSE_RETURN_V(IsLivingMaxDelayTimeValid(), TransStatus(Status::ERROR_INVALID_PARAMETER));
 
    if (HandleDataSource(mediaSource)) {        // DataSource类型的源
        return playStatisticalInfo_.errCode;
    }
    HandleFileDescriptor(mediaSource);      // fd类型的源
    int32_t ret = HandleFileUrl();      // 本地file类型的源
    if (ret != MSERR_OK) {
        return ret;
    }
    DetermineSourceType();      // 标记源类型
    pipelineStates_ = PlayerStates::PLAYER_INITIALIZED;
    ret = TransStatus(Status::OK);
    playStatisticalInfo_.errCode = ret;
    return ret;
}
 
bool HiPlayerImpl::ValidateAndInitMediaSource(const std::shared_ptr<AVMediaSource> &mediaSource)
{
    if (mediaSource == nullptr) {
        CollectionErrorInfo(MSERR_INVALID_VAL, "mediaSource is nullptr");
        return false;
    }
    enable_ = mediaSource->GetenableOfflineCache();
    header_ = mediaSource->header;
    playMediaStreamVec_ = mediaSource->GetAVPlayMediaStreamList();
    url_ = playMediaStreamVec_.empty() ? mediaSource->url : playMediaStreamVec_[0].url;
    sourceLoader_ = mediaSource->sourceLoader_;
    mimeType_ = mediaSource->GetMimeType();
    return true;
}
 
bool HiPlayerImpl::HandleDataSource(const std::shared_ptr<AVMediaSource> &mediaSource)
{
    if (!mediaSource->IsDataSourceSet()) {
        return false;
    }
    dataSrc_ = mediaSource->GetDataSource();
    if (dfxAgent_ != nullptr) {
        dfxAgent_->SetSourceType(PlayerDfxSourceType::DFX_SOURCE_TYPE_DATASRC);
        sourceType_ = PlayerDfxSourceType::DFX_SOURCE_TYPE_DATASRC;
    }
    pipelineStates_ = PlayerStates::PLAYER_INITIALIZED;
    int ret = TransStatus(Status::OK);
    playStatisticalInfo_.errCode = ret;
    return true;
}
 
void HiPlayerImpl::HandleFileDescriptor(const std::shared_ptr<AVMediaSource> &mediaSource)
{
    if (mediaSource->IsFileDescriptorSet()) {
        fileDescriptor_ = mediaSource->GetFileDescriptor();
        url_ = "fd://" + std::to_string(fileDescriptor_.fd) + "?offset=" +
               std::to_string(fileDescriptor_.offset) + "&size=" + std::to_string(fileDescriptor_.size);
    }
}
 
int32_t HiPlayerImpl::HandleFileUrl()
{
    if (mimeType_ != AVMimeTypes::APPLICATION_M3U8 && IsFileUrl(url_)) {
        std::string realUriPath;
        int32_t result = GetRealPath(url_, realUriPath);
        if (result != MSERR_OK) {
            CollectionErrorInfo(result, "SetSource error: GetRealPath error");
            return result;
        }
        url_ = "file://" + realUriPath;
    }
    return MSERR_OK;
}
 
void HiPlayerImpl::DetermineSourceType()
{
    PlayerDfxSourceType sourceType = PlayerDfxSourceType::DFX_SOURCE_TYPE_MEDIASOURCE_LOCAL;
    if (IsNetworkUrl(url_)) {
        isNetWorkPlay_ = true;
        sourceType = PlayerDfxSourceType::DFX_SOURCE_TYPE_MEDIASOURCE_NETWORK;
    }
    if (dfxAgent_ != nullptr) {
        dfxAgent_->SetSourceType(sourceType);
        sourceType_ = sourceType;
    }
}

int32_t HiPlayerImpl::SetSource(const std::shared_ptr<IMediaDataSource>& dataSrc)
{
    MediaTrace trace("HiPlayerImpl::SetSource dataSrc");
    MEDIA_LOG_I("SetSource in source stream");
    CreatePlaybackInfo(CallType::AVPLAYER, appUid_, instanceId_);
    CreateStallingInfo(CallType::AVPLAYER, appUid_, instanceId_);
    if (dataSrc == nullptr) {
        MEDIA_LOG_E("SetSource error: dataSrc is null");
    }
    if (dfxAgent_ != nullptr) {
        dfxAgent_->SetSourceType(PlayerDfxSourceType::DFX_SOURCE_TYPE_DATASRC);
        sourceType_ = PlayerDfxSourceType::DFX_SOURCE_TYPE_DATASRC;
    }
    playStatisticalInfo_.sourceType = static_cast<int32_t>(SourceType::SOURCE_TYPE_STREAM);
    dataSrc_ = dataSrc;
    hasExtSub_ = false;
    pipelineStates_ = PlayerStates::PLAYER_INITIALIZED;
    int ret = TransStatus(Status::OK);
    playStatisticalInfo_.errCode = ret;
    ResetEnableCameraPostProcess();
    return ret;
}

int32_t HiPlayerImpl::AddSubSource(const std::string &url)
{
    MediaTrace trace("HiPlayerImpl::AddSubSource uri");
    MEDIA_LOG_I("AddSubSource entered source uri: %{private}s", url.c_str());
    subUrl_ = url;
    if (IsFileUrl(url)) {
        std::string realUriPath;
        int32_t result = GetRealPath(url, realUriPath);
        if (result != MSERR_OK) {
            MEDIA_LOG_E("AddSubSource error: GetRealPath error");
            return result;
        }
        subUrl_ = "file://" + realUriPath;
    }

    hasExtSub_ = true;
    return TransStatus(Status::OK);
}

void HiPlayerImpl::ResetIfSourceExisted()
{
    FALSE_RETURN(demuxer_ != nullptr);
    MEDIA_LOG_I("Source is existed, reset the relatived objects");
    ReleaseInner();
    {
        std::unique_lock<std::mutex> lock(pipelineMutex_);
        if (pipeline_ != nullptr) {
            pipeline_.reset();
        }
    }
    if (audioDecoder_ != nullptr) {
        audioDecoder_.reset();
    }

    pipeline_ = std::make_shared<OHOS::Media::Pipeline::Pipeline>();
    if (pipeline_ != nullptr) {
        pipeline_->Init(playerEventReceiver_, playerFilterCallback_, playerId_);
    }
    syncManager_ = std::make_shared<MediaSyncManager>();
    MEDIA_LOG_I("Reset the relatived objects end");
}

int32_t HiPlayerImpl::Prepare()
{
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetPlayRange(int64_t start, int64_t end)
{
    if (!IsValidPlayRange(start, end)) {
        MEDIA_LOG_E("SetPlayRange failed! start: " PUBLIC_LOG_D64 ", end: " PUBLIC_LOG_D64,
                    start, end);
        UpdateStateNoLock(PlayerStates::PLAYER_STATE_ERROR);
        return TransStatus(Status::ERROR_INVALID_OPERATION);
    }
    playRangeStartTime_ = start;
    playRangeEndTime_ = end;

    if (pipeline_ != nullptr) {
        pipeline_->SetPlayRange(playRangeStartTime_, playRangeEndTime_);
    }

    MEDIA_LOG_I("SetPlayRange success! start: " PUBLIC_LOG_D64 ", end: " PUBLIC_LOG_D64,
                playRangeStartTime_, playRangeEndTime_);
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetPlayRangeWithMode(int64_t start, int64_t end, PlayerSeekMode mode)
{
    Status rtv = Status::OK;
    if (!IsValidPlayRange(start, end)) {
        MEDIA_LOG_E("SetPlayRangeWithMode failed! start: " PUBLIC_LOG_D64 ", end: "
            PUBLIC_LOG_D64, start, end);
        rtv = Status::ERROR_INVALID_PARAMETER;
        Event event{"engine", EventType::EVENT_ERROR, TransStatus(rtv), ""};
        OnEvent(event);
        return TransStatus(rtv);
    }
    startTimeWithMode_ = start;
    endTimeWithMode_ = end;
    playRangeSeekMode_ = mode;
    isSetPlayRange_ = true;
    if (pipelineStates_ == PlayerStates::PLAYER_INITIALIZED ||
        pipelineStates_ == PlayerStates::PLAYER_STOPPED) {
        MEDIA_LOG_I("current state is initialized/stopped SetPlayRangeWithMode start: "
             PUBLIC_LOG_D64 ", end: " PUBLIC_LOG_D64, startTimeWithMode_, endTimeWithMode_);
        return TransStatus(rtv);
    }
    if (pipeline_ != nullptr && demuxer_ != nullptr) {
        pipeline_->SetPlayRange(startTimeWithMode_, endTimeWithMode_);
        int64_t seekTimeMs = 0;
        if (startTimeWithMode_ > PLAY_RANGE_DEFAULT_VALUE) {
            seekTimeMs = startTimeWithMode_;
        }
        MEDIA_LOG_I("seek to start time: " PUBLIC_LOG_D64, seekTimeMs);
        pipeline_->Flush();
        rtv = doSeek(seekTimeMs, playRangeSeekMode_);
        if (rtv != Status::OK) {
            UpdateStateNoLock(PlayerStates::PLAYER_STATE_ERROR);
            MEDIA_LOG_E("seek failed to start time: " PUBLIC_LOG_D64, seekTimeMs);
            return TransStatus(rtv);
        }
        if (demuxer_->IsRenderNextVideoFrameSupported() && !demuxer_->IsVideoEos()) {
            rtv = pipeline_->Preroll(true);
        }
        if (pipelineStates_ == PlayerStates::PLAYER_PLAYBACK_COMPLETE) {
            isDoCompletedSeek_ = true;
            OnStateChanged(PlayerStateId::PAUSE);
        }
        Format format;
        callbackLooper_.OnInfo(INFO_TYPE_POSITION_UPDATE, static_cast<int32_t>(seekTimeMs), format);
    }
    MEDIA_LOG_I("SetPlayRangeWithMode start: " PUBLIC_LOG_D64 ", end: " PUBLIC_LOG_D64,
                startTimeWithMode_, endTimeWithMode_);
    return TransStatus(rtv);
}

int64_t HiPlayerImpl::GetPlayRangeStartTime()
{
    return startTimeWithMode_ != PLAY_RANGE_DEFAULT_VALUE ? startTimeWithMode_ : playRangeStartTime_;
}

int64_t HiPlayerImpl::GetPlayRangeEndTime()
{
    return endTimeWithMode_ != PLAY_RANGE_DEFAULT_VALUE ? endTimeWithMode_ : playRangeEndTime_;
}

int32_t HiPlayerImpl::GetPlayRangeSeekMode()
{
    return playRangeSeekMode_;
}

int32_t HiPlayerImpl::SetRenderFirstFrame(bool display)
{
    MEDIA_LOG_I("SetRenderFirstFrame in, display: " PUBLIC_LOG_D32, display);
    renderFirstFrame_ = display;
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetIsCalledBySystemApp(bool isCalledBySystemApp)
{
    MEDIA_LOG_I("SetIsCalledBySystemApp in, isCalledBySystemApp: " PUBLIC_LOG_D32, isCalledBySystemApp);
    isCalledBySystemApp_ = isCalledBySystemApp;
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetStartFrameRateOptEnabled(bool enabled)
{
    MEDIA_LOG_I("enabled: " PUBLIC_LOG_D32, enabled);
    isEnableStartFrameRateOpt_ = enabled;
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::PrepareAsync()
{
    MediaTrace trace("HiPlayerImpl::PrepareAsync");
    MEDIA_LOG_D("HiPlayerImpl PrepareAsync");
    int64_t startTime = GetCurrentMillisecond();
    if (IsPrepareStateValid()) {
        CollectionErrorInfo(MSERR_INVALID_OPERATION, "PrepareAsync pipelineStates not initialized or stopped");
        return MSERR_INVALID_OPERATION;
    }
    auto ret = Status::OK;
    if (!isNeedSwDecoder_) {
        ret = Init();
        if (ret != Status::OK || isInterruptNeeded_.load()) {
            return HandleErrorRet(Status::ERROR_UNSUPPORTED_FORMAT, "PrepareAsync error: init error");
        }
    }
    isBufferingEnd_ = false;
    DoSetMediaSource(ret);
    if (mutedMediaType_ == OHOS::Media::MediaType::MEDIA_TYPE_VID) {
        MEDIA_LOG_I("HiPlayerImpl::PrepareAsync, do setMute true");
        demuxer_->SetMediaMuted(OHOS::Media::MediaType::MEDIA_TYPE_VID, true);
    }
    if (ret != Status::OK && !isInterruptNeeded_.load()) {
        OnEvent({"engine", EventType::EVENT_ERROR, MSERR_UNSUPPORT_CONTAINER_TYPE, mimeType_});
        return HandleErrorRet(Status::ERROR_UNSUPPORTED_FORMAT, "PrepareAsync error: DoSetSource error" + mimeType_);
    }
    FALSE_RETURN_V(!BreakIfInterruptted(), TransStatus(Status::OK));
    NotifyBufferingUpdate(PlayerKeys::PLAYER_BUFFERING_START, 0);
    MEDIA_LOG_I("PrepareAsync:current pipeline state: " PUBLIC_LOG_S, StringnessPlayerState(pipelineStates_).c_str());
    OnStateChanged(PlayerStateId::PREPARING);
    ret = pipeline_->Prepare();
    if (ret != Status::OK) {
        MEDIA_LOG_E("PrepareAsync failed with error " PUBLIC_LOG_D32, ret);
        return HandleErrorRet(ret, "pipeline PrepareAsync failed");
    }
    SetFlvObs();
    InitDuration();
    SetSeiMessageListener();
    UpdateMediaFirstPts();
    ret = DoSetPlayRange();
    FALSE_RETURN_V_MSG_E(ret == Status::OK, TransStatus(ret), "DoSetPlayRange failed");
    if (demuxer_ != nullptr && demuxer_->IsRenderNextVideoFrameSupported() && IsAppEnableRenderFirstFrame(appUid_)) {
        ret = pipeline_->Preroll(renderFirstFrame_);
        if (ret != Status::OK) {
            return HandleErrorRet(ret, "PrepareFrame failed.");
        }
    }
    UpdatePlayerStateAndNotify();
    prepareDuration_ = GetCurrentMillisecond() - startTime;
    MEDIA_LOG_I("PrepareAsync End");
    SetMediaKitReport("avplayer prepare out");
    return TransStatus(ret);
}

bool HiPlayerImpl::IsPrepareStateValid() const
{
    return !(pipelineStates_ == PlayerStates::PLAYER_INITIALIZED || pipelineStates_ == PlayerStates::PLAYER_STOPPED) &&
        !isNeedSwDecoder_;
}

void HiPlayerImpl::CollectionErrorInfo(int32_t errCode, const std::string& errMsg)
{
    MEDIA_LOG_E("Error: " PUBLIC_LOG_S, errMsg.c_str());
    playStatisticalInfo_.errCode = errCode;
    playStatisticalInfo_.errMsg = errMsg;
}

int32_t HiPlayerImpl::HandleErrorRet(Status ret, const std::string& errMsg)
{
    auto errCode = TransStatus(ret);
    CollectionErrorInfo(errCode, errMsg);
    return errCode;
}

void HiPlayerImpl::DoSetMediaSource(Status& ret)
{
    if (dataSrc_ != nullptr) {
        ret = DoSetSource(std::make_shared<MediaSource>(dataSrc_));
    } else if (sourceLoader_ != nullptr) {
        auto mediaSource = std::make_shared<MediaSource>(url_, header_);
        if (mediaSource == nullptr) {
            MEDIA_LOG_I("mediaSource == nullptr");
            ret = Status::ERROR_NO_MEMORY;
            return;
        }
        mediaSource->SetSourceLoader(sourceLoader_);
        mediaSource->enableOfflineCache(enable_);
        ret = DoSetSource(mediaSource);
    } else {
        if (!header_.empty()) {
            MEDIA_LOG_I("DoSetSource header");
            ret = DoSetSource(std::make_shared<MediaSource>(url_, header_));
        } else {
            MEDIA_LOG_I("DoSetSource url");
            ret = DoSetSource(std::make_shared<MediaSource>(url_));
        }
    }
}

Status HiPlayerImpl::DoSetPlayRange()
{
    Status ret = Status::OK;
    int64_t rangeStartTime = GetPlayRangeStartTime();
    std::pair<int64_t, bool> startInfo;
    if (rangeStartTime == -1 && demuxer_->GetStartInfo(startInfo) && startInfo.first > 0) {
        rangeStartTime = startInfo.first;
    }
    int64_t rangeEndTime = GetPlayRangeEndTime();
    if (!IsValidPlayRange(rangeStartTime, rangeEndTime)) {
        MEDIA_LOG_E("DoSetPlayRange failed! start: " PUBLIC_LOG_D64 ", end: " PUBLIC_LOG_D64,
                    rangeStartTime, rangeEndTime);
        ret = Status::ERROR_INVALID_PARAMETER;
        Event event{"engine", EventType::EVENT_ERROR, TransStatus(ret), ""};
        OnEvent(event);
        return ret;
    }
    if ((pipeline_ != nullptr) && (rangeEndTime > PLAY_RANGE_DEFAULT_VALUE)) {
        pipeline_->SetPlayRange(rangeStartTime, rangeEndTime);
    }
    if ((pipeline_ != nullptr) && (rangeStartTime > PLAY_RANGE_DEFAULT_VALUE)) {
        MEDIA_LOG_I("seek to start time: " PUBLIC_LOG_D64, rangeStartTime);
        pipeline_ -> Flush();
        ret = doSeek(rangeStartTime, playRangeSeekMode_);
        if (ret != Status::OK) {
            UpdateStateNoLock(PlayerStates::PLAYER_STATE_ERROR);
            MEDIA_LOG_E("seek failed to start time: " PUBLIC_LOG_D64, rangeStartTime);
            return ret;
        }
        Format format;
        callbackLooper_.OnInfo(INFO_TYPE_POSITION_UPDATE, static_cast<int32_t>(rangeStartTime), format);
    }
    return ret;
}

void HiPlayerImpl::UpdatePlayerStateAndNotify()
{
    NotifyBufferingUpdate(PlayerKeys::PLAYER_BUFFERING_END, 0);
    if (durationMs_ <= 0) {
        HandleIsLiveStreamEvent(true);
    }
    NotifyDurationUpdate(PlayerKeys::PLAYER_CACHED_DURATION, durationMs_.load());
    InitVideoWidthAndHeight();
    NotifyResolutionChange();
    NotifyPositionUpdate();
    DoInitializeForHttp();
    if (notNotifyForSw_) {
        MEDIA_LOG_I("need to Swdecoder");
        notNotifyForSw_ = false;
        return;
    }
    OnStateChanged(PlayerStateId::READY);
}

void HiPlayerImpl::UpdateMediaFirstPts()
{
    FALSE_RETURN(syncManager_ != nullptr);
    std::string mime;
    FALSE_RETURN_MSG(demuxer_ != nullptr, "demuxer_ is nullptr");
    std::vector<std::shared_ptr<Meta>> metaInfo = demuxer_->GetStreamMetaInfo();
    int64_t startTime = 0;
    for (const auto& trackInfo : metaInfo) {
        if (trackInfo == nullptr || !(trackInfo->GetData(Tag::MIME_TYPE, mime))) {
            MEDIA_LOG_W("TrackInfo is null or get mime fail");
            continue;
        }
        if (!(mime.find("audio/") == 0 || mime.find("video/") == 0)) {
            MEDIA_LOG_W("Not audio or video track");
            continue;
        }
        if (trackInfo->GetData(Tag::MEDIA_START_TIME, startTime)) {
            syncManager_->SetMediaStartPts(startTime);
        }
    }
    startTime = syncManager_->GetMediaStartPts();
    if (startTime != HST_TIME_NONE) {
        mediaStartPts_ = startTime;
    }
}

bool HiPlayerImpl::BreakIfInterruptted()
{
    if (isInterruptNeeded_.load()) {
        OnStateChanged(PlayerStateId::READY);
        return true;
    }
    return false;
}

void HiPlayerImpl::SetInterruptState(bool isInterruptNeeded)
{
    MEDIA_LOG_I("Hiplayer SetInterrupt %{public}d", isInterruptNeeded);
    isInterruptNeeded_ = isInterruptNeeded;
    if (interruptMonitor_) {
        interruptMonitor_->SetInterruptState(isInterruptNeeded);
    }
    if (isDrmProtected_) {
        std::unique_lock<std::mutex> drmLock(drmMutex_);
        stopWaitingDrmConfig_ = true;
        drmConfigCond_.notify_all();
    }
    if (isFlvLive_ && bufferDurationForPlaying_ > 0) {
        flvLiveCond_.notify_all();
    }
}

int32_t HiPlayerImpl::SelectBitRate(uint32_t bitRate, bool isAutoSelect)
{
    MEDIA_LOG_D("HiPlayerImpl:: Select BitRate %{public}d", bitRate);
    FALSE_RETURN_V_MSG_E(demuxer_ != nullptr,
        MSERR_INVALID_OPERATION, "SelectBitRate failed, demuxer_ is null");
    Status ret = demuxer_->SelectBitRate(bitRate, isAutoSelect);
    if (ret == Status::OK) {
        Format bitRateFormat;
        callbackLooper_.OnInfo(INFO_TYPE_BITRATEDONE, bitRate, bitRateFormat);
        MEDIA_LOG_I("SelectBitRate success");
        return MSERR_OK;
    }
    MEDIA_LOG_I("SelectBitRate failed");
    return MSERR_INVALID_OPERATION;
}

void HiPlayerImpl::DoInitializeForHttp()
{
    if (!isNetWorkPlay_) {
        MEDIA_LOG_E("DoInitializeForHttp failed, not network play");
        return;
    }
    std::vector<uint32_t> vBitRates;
    MEDIA_LOG_D_SHORT("DoInitializeForHttp");
    FALSE_RETURN_MSG(demuxer_ != nullptr, "demuxer_ is nullptr");
    auto ret = demuxer_->GetBitRates(vBitRates);
    if (ret == Status::OK && vBitRates.size() > 0) {
        int mSize = static_cast<int>(vBitRates.size());
        const int size = mSize;
        uint32_t* bitrates = vBitRates.data();
        Format bitRateFormat;
        (void)bitRateFormat.PutBuffer(std::string(PlayerKeys::PLAYER_AVAILABLE_BITRATES),
            static_cast<uint8_t *>(static_cast<void *>(bitrates)), size * sizeof(uint32_t));
        callbackLooper_.OnInfo(INFO_TYPE_BITRATE_COLLECT, 0, bitRateFormat);
        MEDIA_LOG_I("OnInfo INFO_TYPE_BITRATE_COLLEC");
    } else {
        MEDIA_LOG_D("GetBitRates failed, ret %{public}d", ret);
    }
}

int32_t HiPlayerImpl::Play()
{
    MediaTrace trace("HiPlayerImpl::Play");
    MEDIA_LOG_I("Play entered.");
    startTime_ = GetCurrentMillisecond();
    playStartTime_ = GetCurrentMillisecond();
    eosInLoopForFrozen_ = false;
    int32_t ret = MSERR_INVALID_VAL;
    if (!IsValidPlayRange(playRangeStartTime_, playRangeEndTime_)) {
        MEDIA_LOG_E("SetPlayRange failed! start: " PUBLIC_LOG_D64 ", end: " PUBLIC_LOG_D64,
                    playRangeStartTime_, playRangeEndTime_);
        UpdateStateNoLock(PlayerStates::PLAYER_STATE_ERROR);
        return TransStatus(Status::ERROR_INVALID_OPERATION);
    }
    ApplyAudioHapticsSyncId();
    if (pipelineStates_ == PlayerStates::PLAYER_PLAYBACK_COMPLETE || pipelineStates_ == PlayerStates::PLAYER_STOPPED) {
        isStreaming_ = true;
        ret = ((GetPlayRangeStartTime() > PLAY_RANGE_DEFAULT_VALUE) ?
            TransStatus(Seek(GetPlayStartTime(), playRangeSeekMode_, false)) :
            TransStatus(Seek(0, PlayerSeekMode::SEEK_PREVIOUS_SYNC, false)));
        callbackLooper_.StartReportMediaProgress(REPORT_PROGRESS_INTERVAL);
        callbackLooper_.StartCollectMaxAmplitude(SAMPLE_AMPLITUDE_INTERVAL);
    } else if (pipelineStates_ == PlayerStates::PLAYER_PAUSED) {
        DoPausedPlay(ret);
    } else {
        if (playRangeStartTime_ > PLAY_RANGE_DEFAULT_VALUE) {
            ret = TransStatus(Seek(playRangeStartTime_, PlayerSeekMode::SEEK_PREVIOUS_SYNC, false));
        }
        callbackLooper_.StartReportMediaProgress(REPORT_PROGRESS_INTERVAL);
        callbackLooper_.StartCollectMaxAmplitude(SAMPLE_AMPLITUDE_INTERVAL);
        syncManager_->Resume();
        ret = TransStatus(pipeline_->Start());
        if (ret != MSERR_OK) {
            UpdateStateNoLock(PlayerStates::PLAYER_STATE_ERROR);
        }
    }
    StartFlvCheckLiveDelayTime();
    if (ret == MSERR_OK) {
        if (!isInitialPlay_) {
            OnStateChanged(PlayerStateId::PLAYING);
        } else {
            MEDIA_LOG_D_SHORT("InitialPlay, pending to change state of playing");
        }
    } else {
        CollectionErrorInfo(ret, "Play failed");
    }
    return ret;
}

void HiPlayerImpl::DoPausedPlay(int32_t &ret)
{
    if (playRangeStartTime_ > PLAY_RANGE_DEFAULT_VALUE) {
        ret = TransStatus(Seek(playRangeStartTime_, PlayerSeekMode::SEEK_PREVIOUS_SYNC, false));
    }
    callbackLooper_.StartReportMediaProgress(REPORT_PROGRESS_INTERVAL);
    callbackLooper_.StartCollectMaxAmplitude(SAMPLE_AMPLITUDE_INTERVAL);
    ret = TransStatus(Resume());
    return;
}

int32_t HiPlayerImpl::Pause(bool isSystemOperation)
{
    MediaTrace trace("HiPlayerImpl::Pause");
    MEDIA_LOG_I("Pause in");
    FALSE_RETURN_V_MSG_E(pipelineStates_ != PlayerStates::PLAYER_PLAYBACK_COMPLETE,
        TransStatus(Status::OK), "completed not allow pause");
    Status ret = Status::OK;
    CacheBuffer();
    ret = pipeline_->Pause();
    syncManager_->Pause();
    if (ret != Status::OK) {
        UpdateStateNoLock(PlayerStates::PLAYER_STATE_ERROR);
    }
    if (videoDecoder_ != nullptr) {
        videoDecoder_->NotifyPause();
    }
    callbackLooper_.StopReportMediaProgress();
    StopFlvCheckLiveDelayTime();
    callbackLooper_.StopCollectMaxAmplitude();
    callbackLooper_.ManualReportMediaProgressOnce();
    {
        AutoLock lock(interruptMutex_);
        OnStateChanged(PlayerStateId::PAUSE, isSystemOperation);
        if (isSystemOperation) {
            ReportAudioInterruptEvent();
        }
    }
    UpdatePlayTotalDuration();
    return TransStatus(ret);
}

int32_t HiPlayerImpl::Freeze(bool &isNoNeedToFreeze)
{
    MediaTrace trace("HiPlayerImpl::Freeze");
    MEDIA_LOG_I("Freeze in");
    std::unique_lock<std::mutex> lock(freezeMutex_);
    
    if (pipelineStates_ != PlayerStates::PLAYER_STARTED && pipelineStates_ != PlayerStates::PLAYER_PREPARED) {
        MEDIA_LOG_I("can not freeze, current state = %{public}d", static_cast<int32_t>(pipelineStates_));
        PauseSourceDownload();
        return TransStatus(Status::OK);
    }

    if (eosInLoopForFrozen_ || pipelineStates_ == PlayerStates::PLAYER_PREPARED) {
        MEDIA_LOG_I("can not freeze in loop mode, current state = %{public}d", static_cast<int32_t>(pipelineStates_));
        isNoNeedToFreeze = true;
        eosInLoopForFrozen_ = false;
        return TransStatus(Status::OK);
    }

    callbackLooper_.StopReportMediaProgress();
    StopFlvCheckLiveDelayTime();
    callbackLooper_.StopCollectMaxAmplitude();
    CacheBuffer();
    Status ret = Status::OK;
    ret = demuxer_->Freeze();
    syncManager_->Pause();
    PauseSourceDownload();
    if (audioSink_ != nullptr) {
        audioSink_->FreezeAudioSink();
    }

    if (ret != Status::OK) {
        UpdateStateNoLock(PlayerStates::PLAYER_STATE_ERROR);
        return TransStatus(ret);
    }
    UpdateStateNoLock(PlayerStates::PLAYER_FROZEN, false, false);
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::UnFreeze()
{
    MediaTrace trace("HiPlayerImpl::UnFreeze");
    MEDIA_LOG_I("UnFreeze in");
    std::unique_lock<std::mutex> lock(freezeMutex_);

    if (pipelineStates_ != PlayerStates::PLAYER_FROZEN) {
        MEDIA_LOG_I("can not unfreeze, current state = %{public}d", static_cast<int32_t>(pipelineStates_));
        if (audioSink_ != nullptr) {
            audioSink_->UnFreezeAudioSink();
        }
        if (isForzenSeekRecv_) {
            pipeline_ -> Flush();
        }
        isForzenSeekRecv_ = false;
        return TransStatus(Status::OK);
    }
    if (isForzenSeekRecv_) {
        Seek(frozenSeekTime_, frozenSeekMode_, true, true);
        isForzenSeekRecv_ = false;
    }

    if (audioSink_ != nullptr) {
        audioSink_->UnFreezeAudioSink();
    }

    callbackLooper_.StartReportMediaProgress(REPORT_PROGRESS_INTERVAL);
    callbackLooper_.StartCollectMaxAmplitude(SAMPLE_AMPLITUDE_INTERVAL);
    Status ret = Status::OK;
    syncManager_->Resume();
    ret = demuxer_->UnFreeze();
    startTime_ = GetCurrentMillisecond();
    StartFlvCheckLiveDelayTime();
    if (ret != Status::OK) {
        UpdateStateNoLock(PlayerStates::PLAYER_STATE_ERROR);
        return TransStatus(ret);
    }
    UpdateStateNoLock(PlayerStates::PLAYER_STARTED, false, false);
    return TransStatus(ret);
}

int32_t HiPlayerImpl::PauseSourceDownload()
{
    FALSE_RETURN_V_NOLOG(!isDownloadPaused_, MSERR_OK);
    demuxer_->StopBufferring(true);
    isDownloadPaused_ = true;
    return MSERR_OK;
}

int32_t HiPlayerImpl::ResumeSourceDownload()
{
    FALSE_RETURN_V_NOLOG(isDownloadPaused_, MSERR_OK);
    demuxer_->StopBufferring(false);
    isDownloadPaused_ = false;
    return MSERR_OK;
}

void HiPlayerImpl::ReportAudioInterruptEvent()
{
    isHintPauseReceived_ = false;
    if (!interruptNotifyPlay_.load()) {
        isSaveInterruptEventNeeded_.store(false);
        return;
    }
    MEDIA_LOG_I("alreay receive an interrupt end event");
    interruptNotifyPlay_.store(false);
    Format format;
    int32_t hintType = interruptEvent_.hintType;
    int32_t forceType = interruptEvent_.forceType;
    int32_t eventType = interruptEvent_.eventType;
    (void)format.PutIntValue(PlayerKeys::AUDIO_INTERRUPT_TYPE, eventType);
    (void)format.PutIntValue(PlayerKeys::AUDIO_INTERRUPT_FORCE, forceType);
    (void)format.PutIntValue(PlayerKeys::AUDIO_INTERRUPT_HINT, hintType);
    callbackLooper_.OnInfo(INFO_TYPE_INTERRUPT_EVENT, hintType, format);
}

int32_t HiPlayerImpl::PauseDemuxer()
{
    MediaTrace trace("HiPlayerImpl::PauseDemuxer");
    MEDIA_LOG_I("PauseDemuxer in");
    callbackLooper_.StopReportMediaProgress();
    callbackLooper_.StopCollectMaxAmplitude();
    StopFlvCheckLiveDelayTime();
    syncManager_->Pause();
    SetBuffering(true);
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::ResumeDemuxer()
{
    MediaTrace trace("HiPlayerImpl::ResumeDemuxer");
    MEDIA_LOG_I("ResumeDemuxer in");
    FALSE_RETURN_V_MSG_E(pipelineStates_ != PlayerStates::PLAYER_STATE_ERROR,
        TransStatus(Status::OK), "PLAYER_STATE_ERROR not allow ResumeDemuxer");
    if (curState_ != PlayerStateId::PREPARING && curState_ != PlayerStateId::READY) {
        callbackLooper_.StartReportMediaProgress(REPORT_PROGRESS_INTERVAL);
        callbackLooper_.StartCollectMaxAmplitude(SAMPLE_AMPLITUDE_INTERVAL);
    }
    StartFlvCheckLiveDelayTime();
    syncManager_->Resume();
    FALSE_GOON_NOEXEC(pipelineStates_ != PlayerStates::PLAYER_PAUSED, demuxer_->ResumeDemuxerReadLoop());
    SetBuffering(false);
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetBuffering(bool isBuffering)
{
    if (audioSink_ != nullptr) {
        audioSink_->SetBuffering(isBuffering);
    }
    if (videoDecoder_ != nullptr) {
        videoDecoder_->SetBuffering(isBuffering);
    }
    return TransStatus(Status::OK);
}

int64_t HiPlayerImpl::GetCurrentMillisecond()
{
    auto duration = std::chrono::steady_clock::now().time_since_epoch();
    return std::chrono::duration_cast<std::chrono::milliseconds>(duration).count();
}

int32_t HiPlayerImpl::Stop()
{
    MediaTrace trace("HiPlayerImpl::Stop");
    MEDIA_LOG_I("Stop entered.");

    AutoLock lock(handleCompleteMutex_);
    UpdatePlayStatistics();
    callbackLooper_.StopReportMediaProgress();
    StopFlvCheckLiveDelayTime();
    callbackLooper_.StopCollectMaxAmplitude();
    if (draggingPlayerAgent_ != nullptr) {
        draggingPlayerAgent_->Release();
        draggingPlayerAgent_ = nullptr;
    }

    // close demuxer first to avoid concurrent problem
    auto ret = Status::ERROR_UNKNOWN;
    {
        std::unique_lock<std::mutex> lock(pipelineMutex_);
        if (pipeline_ != nullptr) {
            ret = pipeline_->Stop();
        }
    }
    syncManager_->Stop();
    if (audioDecoder_ != nullptr) {
        audioDecoder_->Flush();
    }
    #ifdef SUPPORT_VIDEO
        if (videoDecoder_) {
            videoDecoder_->Stop();
            videoDecoder_->Flush();
        }
    #endif
    if (audioSink_ != nullptr) {
        audioSink_->Flush();
    }
    if (subtitleSink_ != nullptr) {
        subtitleSink_->Flush();
    }
    for (std::pair<std::string, bool>& item: completeState_) {
        item.second = false;
    }

    ResetPlayRangeParameter();
    if (pipelineStates_ != PlayerStates::PLAYER_PREPARED) {
        AppendPlayerMediaInfo();
    }
    OnStateChanged(PlayerStateId::STOPPED);
    return TransStatus(ret);
}

void HiPlayerImpl::ResetPlayRangeParameter()
{
    playRangeStartTime_ = PLAY_RANGE_DEFAULT_VALUE;
    playRangeEndTime_ = PLAY_RANGE_DEFAULT_VALUE;
    startTimeWithMode_ = PLAY_RANGE_DEFAULT_VALUE;
    endTimeWithMode_ = PLAY_RANGE_DEFAULT_VALUE;
    isSetPlayRange_ = false;
    playRangeSeekMode_ = PlayerSeekMode::SEEK_PREVIOUS_SYNC;
}

void HiPlayerImpl::UpdatePlayStatistics()
{
    MEDIA_LOG_D("HiPlayerImpl UpdatePlayStatistics");
    playStatisticalInfo_.isDrmProtected = isDrmProtected_;
    if (demuxer_ != nullptr) {
        DownloadInfo downLoadInfo;
        auto ret = demuxer_->GetDownloadInfo(downLoadInfo);
        if (ret == Status::OK) {
            MEDIA_LOG_D("GetDownloadInfo success");
            playStatisticalInfo_.avgDownloadRate = downLoadInfo.avgDownloadRate;
            playStatisticalInfo_.avgDownloadSpeed = downLoadInfo.avgDownloadSpeed;
            playStatisticalInfo_.totalDownLoadBits = downLoadInfo.totalDownLoadBits;
            playStatisticalInfo_.isTimeOut = downLoadInfo.isTimeOut;
        } else {
            MEDIA_LOG_E("GetDownloadInfo failed with error " PUBLIC_LOG_D32, ret);
        }
    } else {
        MEDIA_LOG_E("GetDownloadInfo failed demuxer is null");
    }
    if (videoDecoder_ != nullptr) {
        auto ret = videoDecoder_->GetLagInfo(playStatisticalInfo_.lagTimes, playStatisticalInfo_.maxLagDuration,
            playStatisticalInfo_.avgLagDuration);
        if (ret == Status::OK) {
            MEDIA_LOG_D("GetLagInfo success");
        } else {
            MEDIA_LOG_E("GetLagInfo failed with error " PUBLIC_LOG_D32, ret);
        }
    } else {
        MEDIA_LOG_E("GetLagInfo failed videoDecoder is null error");
    }
}

inline bool HiPlayerImpl::IsStatisticalInfoValid()
{
    return playStatisticalInfo_.playDuration >= 0 && playStatisticalInfo_.startLatency >= 0;
}

void HiPlayerImpl::UpdatePlayTotalDuration()
{
    int64_t startTime = startTime_.load();
    FALSE_RETURN_NOLOG(startTime != -1);
    startTime_ = -1;
    playTotalDuration_ += GetCurrentMillisecond() - startTime;
}

void HiPlayerImpl::MetricsUpdateDuration()
{
    if (pipelineStates_ != PlayerStates::PLAYER_STARTED) {
        return;
    }
    int64_t startTime = startTime_.load();
    startTime_ = GetCurrentMillisecond();
    playTotalDuration_ += startTime_ - startTime;
}

void HiPlayerImpl::AppendPlayerMediaInfo()
{
    MEDIA_LOG_D_SHORT("AppendPlayerMediaInfo entered.");
    UpdatePlayTotalDuration();
    playStatisticalInfo_.playDuration = static_cast<int32_t>(playTotalDuration_);
    playStatisticalInfo_.maxSeekLatency = static_cast<int32_t>(maxSeekLatency_);
    playStatisticalInfo_.maxAccurateSeekLatency = static_cast<int32_t>(maxAccurateSeekLatency_);
    playStatisticalInfo_.maxSurfaceSwapLatency = static_cast<int32_t>(maxSurfaceSwapLatency_);
    playStatisticalInfo_.containerMime = playStatisticalInfo_.videoMime + " : " + playStatisticalInfo_.audioMime;
    FALSE_RETURN_MSG(IsStatisticalInfoValid(), "statistical info is invalid, don't report to bigdata");

    std::shared_ptr<Meta> meta = std::make_shared<Meta>();
    meta->SetData(Tag::AV_PLAYER_ERR_CODE, playStatisticalInfo_.errCode);
    meta->SetData(Tag::AV_PLAYER_ERR_MSG, playStatisticalInfo_.errMsg);
    meta->SetData(Tag::AV_PLAYER_PLAY_DURATION, playStatisticalInfo_.playDuration);
    meta->SetData(Tag::AV_PLAYER_SOURCE_TYPE, playStatisticalInfo_.sourceType);
    meta->SetData(Tag::MEDIA_FILE_URI, playStatisticalInfo_.sourceUrl);
    meta->SetData(Tag::AV_PLAYER_AVG_DOWNLOAD_RATE, playStatisticalInfo_.avgDownloadRate);
    meta->SetData(Tag::AV_PLAYER_AVG_DOWNLOAD_SPEED, playStatisticalInfo_.avgDownloadSpeed);
    meta->SetData(Tag::AV_PLAYER_DOWNLOAD_TOTAL_BITS, playStatisticalInfo_.totalDownLoadBits);
    meta->SetData(Tag::AV_PLAYER_DOWNLOAD_TIME_OUT, playStatisticalInfo_.isTimeOut);
    meta->SetData(Tag::AV_PLAYER_CONTAINER_MIME, playStatisticalInfo_.containerMime);
    meta->SetData(Tag::AV_PLAYER_VIDEO_MIME, playStatisticalInfo_.videoMime);
    meta->SetData(Tag::AV_PLAYER_VIDEO_RESOLUTION, playStatisticalInfo_.videoResolution);
    meta->SetData(Tag::AV_PLAYER_VIDEO_BITRATE, playStatisticalInfo_.videoBitrate);
    meta->SetData(Tag::AV_PLAYER_VIDEO_FRAMERATE, playStatisticalInfo_.videoFrameRate);
    meta->SetData(Tag::AV_PLAYER_HDR_TYPE, playStatisticalInfo_.hdrType);
    meta->SetData(Tag::AV_PLAYER_AUDIO_MIME, playStatisticalInfo_.audioMime);
    meta->SetData(Tag::AUDIO_SAMPLE_RATE, playStatisticalInfo_.audioSampleRate);
    meta->SetData(Tag::AUDIO_CHANNEL_COUNT, playStatisticalInfo_.audioChannelCount);
    meta->SetData(Tag::AV_PLAYER_AUDIO_BITRATE, playStatisticalInfo_.audioBitrate);
    meta->SetData(Tag::AV_PLAYER_IS_DRM_PROTECTED, playStatisticalInfo_.isDrmProtected);
    meta->SetData(Tag::AV_PLAYER_START_LATENCY, playStatisticalInfo_.startLatency);
    meta->SetData(Tag::AV_PLAYER_MAX_SEEK_LATENCY, playStatisticalInfo_.maxSeekLatency);
    meta->SetData(Tag::AV_PLAYER_MAX_ACCURATE_SEEK_LATENCY, playStatisticalInfo_.maxAccurateSeekLatency);
    meta->SetData(Tag::AV_PLAYER_LAG_TIMES, playStatisticalInfo_.lagTimes);
    meta->SetData(Tag::AV_PLAYER_MAX_LAG_DURATION, playStatisticalInfo_.maxLagDuration);
    meta->SetData(Tag::AV_PLAYER_AVG_LAG_DURATION, playStatisticalInfo_.avgLagDuration);
    meta->SetData(Tag::AV_PLAYER_MAX_SURFACESWAP_LATENCY, playStatisticalInfo_.maxSurfaceSwapLatency);
    meta->SetData(Tag::AV_PLAYER_BUFFER_DURATION, bufferDuration_);
    AppendMediaInfo(meta, instanceId_);
}

void HiPlayerImpl::AppendPlaybackStatisticsInfo()
{
    auto fmt = std::make_shared<Format>();
    if (GetPlaybackStatisticMetrics(*fmt) == TransStatus(Status::OK)) {
        auto now = std::chrono::system_clock::now();
        fmt->PutLongValue(
            "timestamp", std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()).count());
        AppendPlaybackInfo(fmt, instanceId_);
    } else {
        MEDIA_LOG_W("GetPlaybackStatisticMetrics failed, skipping record");
    }
}

int32_t HiPlayerImpl::Reset()
{
    MediaTrace trace("HiPlayerImpl::Reset");
    AppendPlaybackStatisticsInfo();
    if (pipelineStates_ == PlayerStates::PLAYER_STOPPED) {
        return TransStatus(Status::OK);
    }
    singleLoop_ = false;
    auto ret = Stop();
    if (syncManager_ != nullptr) {
        syncManager_->ResetMediaStartPts();
        syncManager_->Reset();
    }
    if (dfxAgent_ != nullptr) {
        dfxAgent_->SetSourceType(PlayerDfxSourceType::DFX_SOURCE_TYPE_UNKNOWN);
        dfxAgent_->ResetAgent();
        sourceType_ = PlayerDfxSourceType::DFX_SOURCE_TYPE_UNKNOWN;
        fileType_ = FileType::UNKNOW;
    }
    OnStateChanged(PlayerStateId::STOPPED);
    return ret;
}

int32_t HiPlayerImpl::SeekToCurrentTime(int32_t mSeconds, PlayerSeekMode mode)
{
    MEDIA_LOG_I("SeekToCurrentTime in. mSeconds : " PUBLIC_LOG_D32 ", seekMode : " PUBLIC_LOG_D32,
                mSeconds, static_cast<int32_t>(mode));
    return Seek(mSeconds, mode);
}

Status HiPlayerImpl::Seek(int64_t mSeconds, PlayerSeekMode mode, bool notifySeekDone, bool isUnFreezeSeek)
{
    MediaTrace trace("HiPlayerImpl::Seek");
    MEDIA_LOG_I("Seek entered. mSeconds : " PUBLIC_LOG_D64 ", seekMode : " PUBLIC_LOG_D32,
                mSeconds, static_cast<int32_t>(mode));

    if (durationMs_.load() > 0) {
        int64_t seekStartTime = GetCurrentMillisecond();
        if (audioSink_ != nullptr) {
            audioSink_->SetIsTransitent(true);
        }
        isSeek_ = true;
        int64_t seekPos = std::max(static_cast<int64_t>(0),
            std::min(mSeconds, static_cast<int64_t>(durationMs_.load())));
        auto rtv = seekPos >= 0 ? Status::OK : Status::ERROR_INVALID_PARAMETER;
        if (rtv == Status::OK) {
            rtv = HandleSeek(seekPos, mode, isUnFreezeSeek);
        }
        NotifySeek(rtv, notifySeekDone, seekPos);
        if (audioSink_ != nullptr) {
            audioSink_->SetIsTransitent(false);
        }
        isSeek_ = false;
        UpdateMaxSeekLatency(mode, seekStartTime);
        return rtv;
    } else {
        return LiveSeek(mSeconds, mode, notifySeekDone, isUnFreezeSeek);
    }
}

Status HiPlayerImpl::LiveSeek(int64_t mSeconds, PlayerSeekMode mode, bool notifySeekDone, bool isUnFreezeSeek)
{
    int64_t seekStartTime = GetCurrentMillisecond();
    if (audioSink_ != nullptr) {
        audioSink_->SetIsTransitent(true);
    }
    int32_t curPosMs = 0;
    int32_t curPostAfterSeek = std::numeric_limits<int32_t>::max();
    (void)GetCurrentTime(curPosMs);
    isSeek_ = true;
    int64_t seekPos = mSeconds;
    auto rtv = seekPos >= 0 ? Status::OK : Status::ERROR_INVALID_PARAMETER;
    auto range = GetSeekableRanges();
    if (range.empty()) {
        MEDIA_LOG_E("Live stream seek failed, seekable range is empty");
        return Status::ERROR_INVALID_PARAMETER;
    }
    for (const auto& item : range) {
        if (rtv == Status::OK && seekPos >= Plugins::HstTime2Ms(item.start) &&
            seekPos <= Plugins::HstTime2Ms(item.end)) {
            // Seekable range uses absolute time, while seek interface uses relative time,
            // so need to convert it to relative time before seek.
            rtv = HandleSeek(seekPos - Plugins::HstTime2Ms(item.start), mode, isUnFreezeSeek);
        }
    }
    NotifySeek(rtv, notifySeekDone, seekPos);
    if (audioSink_ != nullptr) {
        audioSink_->SetIsTransitent(false);
    }
    isSeek_ = false;
    (void)GetCurrentTime(curPostAfterSeek);
    MEDIA_LOG_I("curPosMs : " PUBLIC_LOG_D32 ", curPostAfterSeek : " PUBLIC_LOG_D32, curPosMs, curPostAfterSeek);
    if (rtv == Status::OK && curPosMs > curPostAfterSeek) {
        MEDIA_LOG_I("Into live stream seek mode.");
        isLiveSeek_ = true;
    }
    UpdateMaxSeekLatency(mode, seekStartTime);
    return rtv;
}

Status HiPlayerImpl::HandleSeek(int64_t seekPos, PlayerSeekMode mode, bool isUnFreezeSeek)
{
    switch (pipelineStates_) {
        case PlayerStates::PLAYER_STARTED: {
            return doStartedSeek(seekPos, mode);
        }
        case PlayerStates::PLAYER_PAUSED: {
            return doPausedSeek(seekPos, mode);
        }
        case PlayerStates::PLAYER_PLAYBACK_COMPLETE: {
            return doCompletedSeek(seekPos, mode);
        }
        case PlayerStates::PLAYER_PREPARED: {
            return doPreparedSeek(seekPos, mode);
        }
        case PlayerStates::PLAYER_FROZEN: {
            return doFrozenSeek(seekPos, mode, isUnFreezeSeek);
        }
        default:
            MEDIA_LOG_I_SHORT("Seek in error pipelineStates: " PUBLIC_LOG_D32,
                static_cast<int32_t>(pipelineStates_));
            return Status::ERROR_WRONG_STATE;
    }
}

void HiPlayerImpl::UpdateMaxSeekLatency(PlayerSeekMode mode, int64_t seekStartTime)
{
    int64_t seekDiffTime = GetCurrentMillisecond() - seekStartTime;
    if (mode == PlayerSeekMode::SEEK_CLOSEST) {
        maxAccurateSeekLatency_ = (maxAccurateSeekLatency_ > seekDiffTime) ? maxAccurateSeekLatency_ : seekDiffTime;
    } else {
        maxSeekLatency_ = (maxSeekLatency_ > seekDiffTime) ? maxSeekLatency_ : seekDiffTime;
    }
}

void HiPlayerImpl::NotifySeek(Status rtv, bool flag, int64_t seekPos)
{
    if (rtv != Status::OK) {
        MEDIA_LOG_E("Seek done, seek error");
        FALSE_RETURN_MSG(!isInterruptNeeded_.load(), " Seek is Interrupted");
        // change player state to PLAYER_STATE_ERROR when seek error.
        UpdateStateNoLock(PlayerStates::PLAYER_STATE_ERROR);
        Format format;
        callbackLooper_.OnError(PlayerErrorType::PLAY_ERR, MSERR_DATA_SOURCE_IO_ERROR, "");
        callbackLooper_.OnInfo(INFO_TYPE_SEEKDONE, -1, format);
        return;
    }
    flag ? NotifySeekDone(seekPos) : NotifyBufferEnd();
}

int32_t HiPlayerImpl::Seek(int64_t mSeconds, PlayerSeekMode mode)
{
    MediaTrace trace("HiPlayerImpl::Seek.");
    AutoLock lock(handleCompleteMutex_);
    if (IsInValidSeekTime(mSeconds)) {
        MEDIA_LOG_E("Current seek time is not at playRange");
        auto errCode = TransStatus(Status::ERROR_INVALID_PARAMETER);
        Event event{"engine", EventType::EVENT_ERROR, errCode, ""};
        OnEvent(event);
        return errCode;
    }
    MEDIA_LOG_I("Seek.");
    return TransStatus(Seek(mSeconds, mode, true));
}

int32_t HiPlayerImpl::SeekToDefaultPosition()
{
    MEDIA_LOG_I("SeekToDefaultPosition.");
    SetPlaybackSpeed(PlaybackRateMode::SPEED_FORWARD_1_00_X);
    SetPlaybackRate(1.0f);
    isLiveSeek_ = false;
    return TransStatus(Status::OK);
}

Status HiPlayerImpl::doPreparedSeek(int64_t seekPos, PlayerSeekMode mode)
{
    MEDIA_LOG_I("doPreparedSeek.");
    pipeline_ -> Flush();
    auto rtv = doSeek(seekPos, mode);
    if ((rtv == Status::OK) && demuxer_->IsRenderNextVideoFrameSupported() && !demuxer_->IsVideoEos()) {
        rtv = pipeline_->Preroll(true);
    }
    return rtv;
}

Status HiPlayerImpl::doStartedSeek(int64_t seekPos, PlayerSeekMode mode)
{
    MEDIA_LOG_I("doStartedSeek");
    CacheBuffer();
    pipeline_ -> Pause();
    pipeline_ -> Flush();
    auto rtv = doSeek(seekPos, mode);
    pipeline_ -> Resume();
    inEosSeek_ = false;
    return rtv;
}

Status HiPlayerImpl::doPausedSeek(int64_t seekPos, PlayerSeekMode mode)
{
    MEDIA_LOG_I("doPausedSeek.");
    pipeline_ -> Pause();
    pipeline_ -> Flush();
    auto rtv = doSeek(seekPos, mode);
    inEosSeek_ = false;
    if ((rtv == Status::OK) && demuxer_->IsRenderNextVideoFrameSupported() && !demuxer_->IsVideoEos()) {
        rtv = pipeline_->Preroll(true);
    }
    return rtv;
}

Status HiPlayerImpl::doFrozenSeek(int64_t seekPos, PlayerSeekMode mode, bool isUnFreezeSeek)
{
    MEDIA_LOG_I("doFrozenSeek. isUnFreezeSeek = %{public}d", isUnFreezeSeek);
    if (isUnFreezeSeek) {
        pipeline_ -> Flush();
        auto rtv = doSeek(seekPos, mode);
        inEosSeek_ = false;
        return rtv;
    } else {
        isForzenSeekRecv_ = true;
        frozenSeekTime_ = seekPos;
        frozenSeekMode_ = mode;
        return Status::OK;
    }
}

void HiPlayerImpl::SetEosInLoopForFrozen(bool status)
{
    eosInLoopForFrozen_ = status;
}

Status HiPlayerImpl::doCompletedSeek(int64_t seekPos, PlayerSeekMode mode)
{
    MEDIA_LOG_D("doCompletedSeek");
    pipeline_ -> Flush();
    auto rtv = doSeek(seekPos, mode);
    if (mode != SEEK_CLOSEST && audioSink_ != nullptr) {
        audioSink_->SetSeekTime(0);
    }
    if (isStreaming_) {
        MEDIA_LOG_D("doCompletedSeek isStreaming_ is true");
        pipeline_->Resume();
        syncManager_->Resume();
    } else {
        if ((rtv == Status::OK) && demuxer_->IsRenderNextVideoFrameSupported() && !demuxer_->IsVideoEos()) {
            rtv = pipeline_->Preroll(true);
        }
        isDoCompletedSeek_ = true;
        callbackLooper_.StopReportMediaProgress();
        callbackLooper_.StopCollectMaxAmplitude();
        callbackLooper_.ManualReportMediaProgressOnce();
        OnStateChanged(PlayerStateId::PAUSE);
    }
    return rtv;
}

Status HiPlayerImpl::doSetPlaybackSpeed(float speed)
{
    MEDIA_LOG_I("doSetPlaybackSpeed %{public}f", speed);
    Status res = Status::OK;
    if (audioSink_ != nullptr) {
        res = audioSink_->SetSpeed(speed);
    }
    if (subtitleSink_ != nullptr) {
        res = subtitleSink_->SetSpeed(speed);
    }
    if (res != Status::OK) {
        MEDIA_LOG_E("doSetPlaybackSpeed audioSink set speed  error");
        return res;
    }
    if (videoDecoder_ != nullptr) {
        res = videoDecoder_->SetSpeed(speed);
    }
    if (syncManager_ != nullptr) {
        res = syncManager_->SetPlaybackRate(speed);
    }
    if (res != Status::OK) {
        MEDIA_LOG_E("doSetPlaybackSpeed syncManager set audio speed error");
        return res;
    }
    if (demuxer_ != nullptr) {
        demuxer_->SetSpeed(speed);
    }
    return Status::OK;
}

bool HiPlayerImpl::NeedSeekClosest()
{
    MEDIA_LOG_D("NeedSeekClosest begin");
    std::vector<Format> trackInfo;
    GetAudioTrackInfo(trackInfo);
    if (trackInfo.size() == 0) {
        MEDIA_LOG_D("NeedSeekClosest end true");
        return true;
    }
    for (size_t i = 0; i < trackInfo.size(); i++) {
        int32_t trackIndex = -1;
        trackInfo[i].GetIntValue("track_index", trackIndex);
        if (trackIndex != currentAudioTrackId_) {
            continue;
        }
        std::string mime = "";
        trackInfo[i].GetStringValue("codec_mime", mime);
        if (mime == "audio/x-ape") {
            MEDIA_LOG_D("NeedSeekClosest end false");
            return false;
        }
    }
    MEDIA_LOG_D("NeedSeekClosest end true");
    return true;
}

Status HiPlayerImpl::doSeek(int64_t seekPos, PlayerSeekMode mode)
{
    MEDIA_LOG_D("doSeek");
    int64_t seekTimeUs = 0;
    FALSE_RETURN_V_MSG_E(Plugins::Us2HstTime(seekPos, seekTimeUs),
        Status::ERROR_INVALID_PARAMETER, "Invalid seekPos: %{public}" PRId64, seekPos);
    if (mode == PlayerSeekMode::SEEK_CLOSEST && NeedSeekClosest()) {
        return HandleSeekClosest(seekPos, seekTimeUs);
    }
    if (mode == PlayerSeekMode::SEEK_CLOSEST) {   // reset mode
        mode = PlayerSeekMode::SEEK_NEXT_SYNC;
        if (audioSink_) {
            audioSink_->SetSeekTime(seekTimeUs);
        }
    }
    if (videoDecoder_ != nullptr) {
        videoDecoder_->SetSeekTime(seekTimeUs + mediaStartPts_, mode);
        videoDecoder_->ResetSeekInfo();
    }
    int64_t realSeekTime = seekPos;
    auto seekMode = Transform2SeekMode(mode);
    auto rtv = demuxer_->SeekTo(seekPos, seekMode, realSeekTime);
    // if it has no next key frames, seek previous.
    if (rtv != Status::OK && mode == PlayerSeekMode::SEEK_NEXT_SYNC) {
        seekMode = Transform2SeekMode(PlayerSeekMode::SEEK_PREVIOUS_SYNC);
        rtv = demuxer_->SeekTo(seekPos, seekMode, realSeekTime);
    }
    if (rtv == Status::OK) {
        syncManager_->Seek(seekTimeUs);
        NotifySubtitleSeek();
    }
    return rtv;
}

Status HiPlayerImpl::HandleSeekClosest(int64_t seekPos, int64_t seekTimeUs)
{
    MEDIA_LOG_I_SHORT("doSeek SEEK_CLOSEST");
    isSeekClosest_.store(true);
    if (videoDecoder_ != nullptr) {
        videoDecoder_->SetSeekTime(seekTimeUs + mediaStartPts_, PlayerSeekMode::SEEK_CLOSEST);
    }
    if (audioSink_ != nullptr) {
        audioSink_->SetIsCancelStart(true);
    }
    seekAgent_ = std::make_shared<SeekAgent>(demuxer_, mediaStartPts_);
    interruptMonitor_->RegisterListener(seekAgent_);
    FALSE_RETURN_V(!isInterruptNeeded_, Status::OK);
    SetFrameRateForSeekPerformance(FRAME_RATE_FOR_SEEK_PERFORMANCE);
    bool timeout = false;
    auto res = seekAgent_->Seek(seekPos, timeout, playerEventReceiver_);
    SetFrameRateForSeekPerformance(FRAME_RATE_DEFAULT);
    MEDIA_LOG_I_SHORT("seekAgent_ Seek end");
    if (res != Status::OK) {
        MEDIA_LOG_E_SHORT("Seek closest failed");
    } else {
        syncManager_->Seek(seekTimeUs, true);
        if (timeout && videoDecoder_ != nullptr) {
            videoDecoder_->ResetSeekInfo();
        }
    }
    if (audioSink_ != nullptr) {
        audioSink_->SetIsCancelStart(false);
    }
    NotifySubtitleSeek();
    interruptMonitor_->DeregisterListener(seekAgent_);
    seekAgent_.reset();
    return res;
}

int32_t HiPlayerImpl::SetVolumeMode(int32_t mode)
{
    MEDIA_LOG_D("SetVolumeMode in mode = %{public}d", mode);
    volumeMode_ = mode;
    Status ret = Status::OK;
    if (audioSink_ != nullptr) {
        ret = audioSink_->SetVolumeMode(mode);
    }
    if (ret != Status::OK) {
        MEDIA_LOG_E("SetVolume failed with error " PUBLIC_LOG_D32, static_cast<int>(ret));
    }
    return TransStatus(ret);
}

int32_t HiPlayerImpl::SetVolume(float leftVolume, float rightVolume)
{
    MEDIA_LOG_D("SetVolume in");
    FALSE_RETURN_V_MSG_E(!(leftVolume < 0 || leftVolume > MAX_MEDIA_VOLUME
        || rightVolume < 0 || rightVolume > MAX_MEDIA_VOLUME),
        (int32_t)Status::ERROR_INVALID_PARAMETER, "volume not valid, should be in range [0,100]");
    float volume = 0.0f;
    if (leftVolume < 1e-6 && rightVolume >= 1e-6) {  // 1e-6
        volume = rightVolume;
    } else if (rightVolume < 1e-6 && leftVolume >= 1e-6) {  // 1e-6
        volume = leftVolume;
    } else {
        volume = (leftVolume + rightVolume) / 2;  // 2
    }
    volume /= MAX_MEDIA_VOLUME;  // normalize to 0~1
    FALSE_RETURN_V_MSG_E(audioSink_ != nullptr, (int32_t)TransStatus(Status::ERROR_INVALID_OPERATION),
        "Set volume failed, audio sink is nullptr");
    MEDIA_LOG_D("Sink SetVolume");
    Status ret = audioSink_->SetVolume(volume);
    if (ret != Status::OK) {
        MEDIA_LOG_E("SetVolume failed with error " PUBLIC_LOG_D32, static_cast<int>(ret));
    }
    return TransStatus(ret);
}

int32_t HiPlayerImpl::SetVideoSurface(sptr<Surface> surface)
{
    MEDIA_LOG_D("SetVideoSurface in");
#ifdef SUPPORT_VIDEO
    int64_t startSetSurfaceTime = GetCurrentMillisecond();
    FALSE_RETURN_V_MSG_E(surface != nullptr, (int32_t)(Status::ERROR_INVALID_PARAMETER),
                         "Set video surface failed, surface == nullptr");
    surface_ = surface;
    if (videoDecoder_ != nullptr &&
        pipelineStates_ != PlayerStates::PLAYER_STOPPED &&
        pipelineStates_ != PlayerStates::PLAYER_STATE_ERROR) {
        return TransStatus(videoDecoder_->SetVideoSurface(surface));
    }
    int64_t endSetSurfaceTime = GetCurrentMillisecond();
    int64_t diffTime = endSetSurfaceTime - startSetSurfaceTime;
    maxSurfaceSwapLatency_ = maxSurfaceSwapLatency_ > diffTime ? maxSurfaceSwapLatency_ : diffTime;
#endif
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetDecryptConfig(const sptr<OHOS::DrmStandard::IMediaKeySessionService> &keySessionProxy,
    bool svp)
{
    MEDIA_LOG_I("SetDecryptConfig in");
#ifdef SUPPORT_AVPLAYER_DRM
    FALSE_RETURN_V_MSG_E(keySessionProxy != nullptr, (int32_t)(Status::ERROR_INVALID_PARAMETER),
        "SetDecryptConfig failed, keySessionProxy == nullptr");
    keySessionServiceProxy_ = keySessionProxy;
    if (svp) {
        svpMode_ = HiplayerSvpMode::SVP_TRUE;
    } else {
        svpMode_ = HiplayerSvpMode::SVP_FALSE;
    }

    std::unique_lock<std::mutex> drmLock(drmMutex_);
    MEDIA_LOG_I("For Drmcond SetDecryptConfig will trig drmPreparedCond");
    isDrmPrepared_ = true;
    drmConfigCond_.notify_all();
#endif
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetLooping(bool loop)
{
    MEDIA_LOG_I("SetLooping in, loop: " PUBLIC_LOG_D32, loop);
    singleLoop_ = loop;
    if (audioSink_ != nullptr) {
        audioSink_->SetLooping(loop);
    }
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetParameter(const Format& params)
{
    MediaTrace trace("HiPlayerImpl::SetParameter");
    if (params.ContainKey(PlayerKeys::PLAYER_AUDIO_HAPTICS_SYNC_ID)) {
        int32_t syncId = DEFAULT_SYNC_ID;
        params.GetIntValue(PlayerKeys::PLAYER_AUDIO_HAPTICS_SYNC_ID, syncId);
        (void)SetAudioHapticsSyncId(syncId);
    }

    if (params.ContainKey(PlayerKeys::PRIVACY_TYPE)) {
        params.GetIntValue(PlayerKeys::PRIVACY_TYPE, audioPrivacyType_);
    }
#ifdef SUPPORT_VIDEO
    if (params.ContainKey(PlayerKeys::VIDEO_SCALE_TYPE)) {
        int32_t videoScaleType = 0;
        params.GetIntValue(PlayerKeys::VIDEO_SCALE_TYPE, videoScaleType);
        return SetVideoScaleType(VideoScaleType(videoScaleType));
    }
#endif
    if (params.ContainKey(PlayerKeys::CONTENT_TYPE) && params.ContainKey(PlayerKeys::STREAM_USAGE)) {
        int32_t contentType;
        int32_t streamUsage;
        int32_t rendererFlag;
        int32_t volumeMode = volumeMode_;
        MEDIA_LOG_I("volumeMode_ = %{public}d", volumeMode_);
        params.GetIntValue(PlayerKeys::CONTENT_TYPE, contentType);
        params.GetIntValue(PlayerKeys::STREAM_USAGE, streamUsage);
        params.GetIntValue(PlayerKeys::RENDERER_FLAG, rendererFlag);
        if (params.ContainKey(PlayerKeys::VOLUME_MODE)) {
            params.GetIntValue(PlayerKeys::VOLUME_MODE, volumeMode);
        }
        return SetAudioRendererInfo(contentType, streamUsage, rendererFlag, volumeMode);
    }
    if (params.ContainKey(PlayerKeys::AUDIO_INTERRUPT_MODE)) {
        int32_t interruptMode = 0;
        params.GetIntValue(PlayerKeys::AUDIO_INTERRUPT_MODE, interruptMode);
        return SetAudioInterruptMode(interruptMode);
    }
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetObs(const std::weak_ptr<IPlayerEngineObs>& obs)
{
    MEDIA_LOG_D_SHORT("SetObs");
    callbackLooper_.StartWithPlayerEngineObs(obs);
    playerEngineObs_ = obs;
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::GetCurrentTime(int32_t& currentPositionMs)
{
    if (!isSetPlayRange_ && (curState_ == PlayerStateId::EOS || inEosSeek_)) {
        currentPositionMs = durationMs_.load();
        return TransStatus(Status::OK);
    }
    if (isSeek_.load()) {
        return TransStatus(Status::ERROR_UNKNOWN);
    }
    FALSE_RETURN_V(syncManager_ != nullptr, TransStatus(Status::ERROR_NULL_POINTER));
    currentPositionMs = Plugins::HstTime2Us32(syncManager_->GetMediaTimeNow());
    MEDIA_LOG_D("GetCurrentTime currentPositionMs: " PUBLIC_LOG_D32, currentPositionMs);
    if (currentPositionMs < 0) {
        currentPositionMs = 0;
    }
    if (durationMs_.load() > 0 && currentPositionMs > durationMs_.load()) {
        currentPositionMs = durationMs_.load();
    }
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::GetPlaybackPosition(int32_t& playbackPositionMs)
{
    FALSE_RETURN_V(syncManager_ != nullptr, TransStatus(Status::ERROR_NULL_POINTER));
    playbackPositionMs = Plugins::HstTime2Us32(syncManager_->GetMediaTimeNow());
    MEDIA_LOG_D("GetPlaybackPosition playbackPositionMs: " PUBLIC_LOG_D32, playbackPositionMs);
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::GetCurrentPresentationTimestamp(int64_t &currentPresentation)
{
    FALSE_RETURN_V(syncManager_ != nullptr, TransStatus(Status::ERROR_NULL_POINTER));
    currentPresentation = syncManager_->GetMediaTimeNow();
    int64_t startPts = syncManager_->GetMediaStartPts();
    FALSE_RETURN_V_MSG_E(startPts != HST_TIME_NONE, currentPresentation, "startPts is none");
    currentPresentation += startPts;
    MEDIA_LOG_D("GetCurrentPresentationTimestamp: " PUBLIC_LOG_D64, currentPresentation);
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::GetDuration(int32_t& durationMs)
{
    durationMs = durationMs_.load();
    MEDIA_LOG_D_SHORT("GetDuration " PUBLIC_LOG_D32, durationMs);
    return TransStatus(Status::OK);
}

std::vector<Plugins::SeekRange> HiPlayerImpl::GetSeekableRanges()
{
    FALSE_RETURN_V(demuxer_ != nullptr, {});
    return demuxer_->GetSeekableRanges();
}

std::vector<Plugins::SeekRange> HiPlayerImpl::GetLoadedRanges()
{
    FALSE_RETURN_V(demuxer_ != nullptr, {});
    return demuxer_->GetLoadedRanges();
}

int32_t HiPlayerImpl::InitDuration()
{
    FALSE_RETURN_V_MSG_E(demuxer_ != nullptr,
        TransStatus(Status::ERROR_WRONG_STATE), "Get media duration failed, demuxer is not ready");
    int64_t duration = 0;
    bool found = false;
    if (demuxer_->GetDuration(duration)) {
        found = true;
    } else {
        MEDIA_LOG_W("Get media duration failed");
    }
    if (found && duration != playWindowDurationMs_.load()) {
        if (duration < 0) {
            playWindowDurationMs_ = Plugins::HstTime2Us(-1 * duration);
        } else {
            playWindowDurationMs_ = Plugins::HstTime2Us(duration);
        }
    }
    if (found && duration > 0 && duration != durationMs_.load()) {
        durationMs_ = Plugins::HstTime2Us(duration);
    }
    durationMs_ = std::max(durationMs_.load(), 0);
    MEDIA_LOG_D("duration: " PUBLIC_LOG_D32, durationMs_.load());
    auto meta = std::make_shared<Meta>();
    if (audioSink_ && meta) {
        meta->SetData(Tag::MEDIA_DURATION, durationMs_.load());
        audioSink_->SetParameter(meta);
    }
    return TransStatus(Status::OK);
}

void HiPlayerImpl::SetBundleName(std::string bundleName)
{
    if (!bundleName.empty()) {
        MEDIA_LOG_I("SetBundleName bundleName: " PUBLIC_LOG_S, bundleName.c_str());
        demuxer_->SetBundleName(bundleName);
    } else {
        MEDIA_LOG_I("SetBundleName failed");
    }
}

void HiPlayerImpl::EnableStartFrameRateOpt(Format &videoTrack)
{
    double frameRate = 1;
    if (videoTrack.GetDoubleValue("frame_rate", frameRate) && syncManager_ != nullptr) {
        frameRate /= FRAME_RATE_UNIT_MULTIPLE;
        syncManager_->SetInitialVideoFrameRate(frameRate);
        MEDIA_LOG_I("VideoSink initial frameRate is " PUBLIC_LOG_D64, static_cast<int64_t>(frameRate));
    }
}

int32_t HiPlayerImpl::InitVideoWidthAndHeight()
{
#ifdef SUPPORT_VIDEO
    std::vector<Format> videoTrackInfo;
    GetVideoTrackInfo(videoTrackInfo);
    if (videoTrackInfo.size() == 0) {
        MEDIA_LOG_E("InitVideoWidthAndHeight failed, as videoTrackInfo is empty!");
        return TransStatus(Status::ERROR_INVALID_OPERATION);
    }
    int32_t currentVideoTrackId = demuxer_->GetCurrentVideoTrackId();
    FALSE_RETURN_V_MSG_E(currentVideoTrackId != -1, TransStatus(Status::ERROR_INVALID_OPERATION),
        "InitVideoWidthAndHeight failed, as currentVideoTrackId is invalid!");
    for (auto& videoTrack : videoTrackInfo) {
        int32_t videoTrackId = -1;
        videoTrack.GetIntValue("track_index", videoTrackId);
        if (videoTrackId != currentVideoTrackId) {
            continue;
        }
        if (isEnableStartFrameRateOpt_) {
            EnableStartFrameRateOpt(videoTrack);
        }
        int32_t height;
        videoTrack.GetIntValue("height", height);
        int32_t width;
        videoTrack.GetIntValue("width", width);
        if (height <= 0 && width <= 0) {
            continue;
        }
        int32_t rotation = 0;
        needSwapWH_ = videoTrack.GetIntValue(Tag::VIDEO_ROTATION, rotation)
            && (rotation == rotation90 || rotation == rotation270);
        MEDIA_LOG_D("rotation %{public}d", rotation);
        videoWidth_ = !needSwapWH_.load() ? width : height;
        videoHeight_ = !needSwapWH_.load() ? height : width;
        MEDIA_LOG_D("InitVideo width %{public}d, height %{public}d",
            videoWidth_.load(), videoHeight_.load());
        break;
    }
#endif
    return TransStatus(Status::OK);
}

Status HiPlayerImpl::InitAudioDefaultTrackIndex()
{
    if (!demuxer_) {
        return Status::ERROR_UNKNOWN;
    }
    std::vector<std::shared_ptr<Meta>> metaInfo = demuxer_->GetStreamMetaInfo();
    std::string mime;
    for (size_t trackIndex = 0; trackIndex < metaInfo.size(); trackIndex++) {
        auto trackInfo = metaInfo[trackIndex];
        if (!(trackInfo->GetData(Tag::MIME_TYPE, mime))) {
            MEDIA_LOG_W("Get MIME fail");
            continue;
        }
        if (IsAudioMime(mime)) {
            defaultAudioTrackId_ = static_cast<int32_t>(trackIndex);
            break;
        }
    }
    currentAudioTrackId_ = defaultAudioTrackId_;
    return Status::OK;
}

Status HiPlayerImpl::InitVideoDefaultTrackIndex()
{
    if (!demuxer_) {
        return Status::ERROR_UNKNOWN;
    }
    std::vector<std::shared_ptr<Meta>> metaInfo = demuxer_->GetStreamMetaInfo();
    std::string mime;
    for (size_t trackIndex = 0; trackIndex < metaInfo.size(); trackIndex++) {
        auto trackInfo = metaInfo[trackIndex];
        if (!(trackInfo->GetData(Tag::MIME_TYPE, mime))) {
            MEDIA_LOG_W("Get MIME fail");
            continue;
        }
        if (IsVideoMime(mime)) {
            defaultVideoTrackId_ = static_cast<int32_t>(trackIndex);
            break;
        }
    }
    currentVideoTrackId_ = defaultVideoTrackId_;
    return Status::OK;
}

Status HiPlayerImpl::InitSubtitleDefaultTrackIndex()
{
    if (!demuxer_) {
        return Status::ERROR_UNKNOWN;
    }
    std::vector<std::shared_ptr<Meta>> metaInfo = demuxer_->GetStreamMetaInfo();
    std::string mime;
    for (size_t trackIndex = 0; trackIndex < metaInfo.size(); trackIndex++) {
        auto trackInfo = metaInfo[trackIndex];
        if (!(trackInfo->GetData(Tag::MIME_TYPE, mime))) {
            MEDIA_LOG_W("Get MIME fail");
            continue;
        }
        if (IsSubtitleMime(mime)) {
            defaultSubtitleTrackId_ = static_cast<int32_t>(trackIndex);
            break;
        }
    }
    currentSubtitleTrackId_ = defaultSubtitleTrackId_;
    return Status::OK;
}

int32_t HiPlayerImpl::SetAudioEffectMode(int32_t effectMode)
{
    MEDIA_LOG_I("SetAudioEffectMode in");
    Status res = Status::OK;
    if (audioSink_ != nullptr) {
        res = audioSink_->SetAudioEffectMode(effectMode);
    }
    if (res != Status::OK) {
        MEDIA_LOG_E("audioSink set AudioEffectMode error");
        return MSERR_UNKNOWN;
    }
    return MSERR_OK;
}

int32_t HiPlayerImpl::GetAudioEffectMode(int32_t &effectMode)
{
    MEDIA_LOG_I("GetAudioEffectMode in");
    Status res = Status::OK;
    if (audioSink_ != nullptr) {
        res = audioSink_->GetAudioEffectMode(effectMode);
    }
    FALSE_RETURN_V_MSG_E(res == Status::OK,
        MSERR_UNKNOWN, "audioSink get AudioEffectMode error");
    return MSERR_OK;
}

float HiPlayerImpl::GetMaxAmplitude()
{
    float maxAmplitude = 0.0f;
    if (audioSink_ != nullptr) {
        maxAmplitude = audioSink_->GetMaxAmplitude();
    }
    return maxAmplitude;
}

int32_t HiPlayerImpl::SetPlaybackSpeed(PlaybackRateMode mode)
{
    MEDIA_LOG_I("SetPlaybackSpeed %{public}d", mode);
    float speed = TransformPlayRate2Float(mode);
    Format format;
    if (doSetPlaybackSpeed(speed) != Status::OK) {
        MEDIA_LOG_E("SetPlaybackSpeed audioSink set speed error");
        callbackLooper_.OnInfo(INFO_TYPE_SPEEDDONE, mode, format);
        return MSERR_UNKNOWN;
    }
    playbackRateMode_ = mode;
    callbackLooper_.OnInfo(INFO_TYPE_SPEEDDONE, mode, format);
    MEDIA_LOG_I("SetPlaybackSpeed end");
    return MSERR_OK;
}

int32_t HiPlayerImpl::SetPlaybackRate(float rate)
{
    MEDIA_LOG_I("SetPlaybackRate %{public}f", rate);
    int32_t extra = 0;
    Format format;
    if (doSetPlaybackSpeed(rate) != Status::OK) {
        MEDIA_LOG_E("SetPlaybackRate audioSink set speed error");
        callbackLooper_.OnInfo(INFO_TYPE_RATEDONE, extra, format);
        return MSERR_UNKNOWN;
    }
    playbackRate_ = rate;
    (void)format.PutFloatValue(PlayerKeys::PLAYER_PLAYBACK_RATE, rate);
    callbackLooper_.OnInfo(INFO_TYPE_RATEDONE, extra, format);
    MEDIA_LOG_I("SetPlaybackRate end");
    return MSERR_OK;
}

int32_t HiPlayerImpl::GetPlaybackSpeed(PlaybackRateMode& mode)
{
    MEDIA_LOG_I("GetPlaybackSpeed in");
    mode = playbackRateMode_.load();
    MEDIA_LOG_I("GetPlaybackSpeed end, mode is " PUBLIC_LOG_D32, mode);
    return MSERR_OK;
}

int32_t HiPlayerImpl::GetPlaybackRate(float& rate)
{
    MEDIA_LOG_I("GetPlaybackRate in");
    rate = playbackRate_.load();
    MEDIA_LOG_I("GetPlaybackRate end, rate is %{public}f", rate);
    return MSERR_OK;
}

bool HiPlayerImpl::IsVideoMime(const std::string& mime)
{
    return mime.find("video/") == 0;
}

bool HiPlayerImpl::IsAudioMime(const std::string& mime)
{
    return mime.find("audio/") == 0;
}

bool HiPlayerImpl::IsSubtitleMime(const std::string& mime)
{
    if (mime == "application/x-subrip" || mime == "text/vtt") {
        return true;
    }
    return false;
}

bool HiPlayerImpl::IsNeedAudioSinkChangeTrack(std::vector<std::shared_ptr<Meta>>& metaInfo, int32_t trackId)
{
    if (trackId == currentAudioTrackId_) {
        return false;
    }
    MEDIA_LOG_I("CurTrackId " PUBLIC_LOG_D32 " trackId " PUBLIC_LOG_D32, currentAudioTrackId_, trackId);

    int32_t sampleRate = -1;
    int32_t channels = -1;
    Plugins::AudioSampleFormat sampleFormat;

    int32_t currentSampleRate = -1;
    int32_t currentChannels = -1;
    Plugins::AudioSampleFormat currentSampleFormat;

    FALSE_RETURN_V(metaInfo[trackId]->GetData(Tag::AUDIO_SAMPLE_RATE, sampleRate), true);
    FALSE_RETURN_V(metaInfo[currentAudioTrackId_]->GetData(Tag::AUDIO_SAMPLE_RATE, currentSampleRate), true);
    FALSE_RETURN_V(sampleRate == currentSampleRate, true);

    FALSE_RETURN_V(metaInfo[trackId]->GetData(Tag::AUDIO_CHANNEL_COUNT, channels), true);
    FALSE_RETURN_V(metaInfo[currentAudioTrackId_]->GetData(Tag::AUDIO_CHANNEL_COUNT, currentChannels), true);
    FALSE_RETURN_V(channels == currentChannels, true);

    FALSE_RETURN_V(metaInfo[trackId]->GetData(Tag::AUDIO_SAMPLE_FORMAT, sampleFormat), true);
    FALSE_RETURN_V(metaInfo[currentAudioTrackId_]->GetData(Tag::AUDIO_SAMPLE_FORMAT, currentSampleFormat), true);
    MEDIA_LOG_I("sampleformat: CurTrackId" PUBLIC_LOG_D32 " trackId" PUBLIC_LOG_D32, currentSampleFormat,
        sampleFormat);
    FALSE_RETURN_V(sampleFormat == currentSampleFormat, true);

    std::string mimeType;
    AudioStandard::AudioEncodingType encodingType;
    std::string currentMimeType;
    AudioStandard::AudioEncodingType currentEncodingType;
    FALSE_RETURN_V(metaInfo[trackId]->GetData(Tag::MIME_TYPE, mimeType), true);
    FALSE_RETURN_V(metaInfo[currentAudioTrackId_]->GetData(Tag::MIME_TYPE, currentMimeType), true);
    encodingType = (mimeType == MimeType::AUDIO_AVS3DA)
                ? AudioStandard::ENCODING_AUDIOVIVID : AudioStandard::ENCODING_PCM;
    currentEncodingType = (currentMimeType == MimeType::AUDIO_AVS3DA)
                ? AudioStandard::ENCODING_AUDIOVIVID : AudioStandard::ENCODING_PCM;
    FALSE_RETURN_V(mimeType == currentMimeType, true);

    return false;
}

int32_t HiPlayerImpl::GetCurrentTrack(int32_t trackType, int32_t &index)
{
    FALSE_RETURN_V_MSG_W(trackType >= OHOS::Media::MediaType::MEDIA_TYPE_AUD &&
        trackType <= OHOS::Media::MediaType::MEDIA_TYPE_SUBTITLE,
        MSERR_INVALID_VAL, "Invalid trackType %{public}d", trackType);
    if (trackType == OHOS::Media::MediaType::MEDIA_TYPE_AUD) {
        if (currentAudioTrackId_ < 0) {
            if (Status::OK != InitAudioDefaultTrackIndex()) {
                return MSERR_UNKNOWN;
            }
        }
        index = currentAudioTrackId_;
    } else if (trackType == OHOS::Media::MediaType::MEDIA_TYPE_VID) {
        if (currentVideoTrackId_ < 0) {
            if (Status::OK != InitVideoDefaultTrackIndex()) {
                return MSERR_UNKNOWN;
            }
        }
        index = currentVideoTrackId_;
    } else if (trackType == OHOS::Media::MediaType::MEDIA_TYPE_SUBTITLE) {
        if (currentSubtitleTrackId_ < 0) {
            if (Status::OK != InitSubtitleDefaultTrackIndex()) {
                return MSERR_UNKNOWN;
            }
        }
        index = currentSubtitleTrackId_;
    } else {
        (void)index;
    }

    return MSERR_OK;
}

int32_t HiPlayerImpl::InnerSelectTrack(std::string mime, int32_t trackId, PlayerSwitchMode mode)
{
    if (Status::OK != demuxer_->SelectTrack(trackId)) {
        MEDIA_LOG_E_SHORT("SelectTrack error. trackId is " PUBLIC_LOG_D32, trackId);
        return MSERR_UNKNOWN;
    }
    if (IsSubtitleMime(mime)) {
        currentSubtitleTrackId_ = trackId;
    } else if (IsAudioMime(mime)) {
        currentAudioTrackId_ = trackId;
        int32_t curPosMs = 0;
        GetCurrentTime(curPosMs);
        MEDIA_LOG_I("Audio SelectTrack seek begin " PUBLIC_LOG_D32, trackId);
        return TransStatus(Seek(curPosMs, PlayerSeekMode::SEEK_CLOSEST, false));
    } else if (IsVideoMime(mime)) {
        currentVideoTrackId_ = trackId;
        int32_t curPosMs = 0;
        GetCurrentTime(curPosMs);
        if (mode == PlayerSwitchMode::SWITCH_SEGMENT) {
            MEDIA_LOG_I("SelectTrack seek begin SWITCH_SEGMENT " PUBLIC_LOG_D32, trackId);
            return TransStatus(Seek(curPosMs, PlayerSeekMode::SEEK_PREVIOUS_SYNC, false));
        } else if (mode == PlayerSwitchMode::SWITCH_CLOSEST) {
            MEDIA_LOG_I("SelectTrack seek begin SWITCH_CLOSEST " PUBLIC_LOG_D32, trackId);
            return TransStatus(Seek(curPosMs, PlayerSeekMode::SEEK_CLOSEST, false));
        }
    }
    return MSERR_OK;
}

int32_t HiPlayerImpl::SelectTrack(int32_t trackId, PlayerSwitchMode mode)
{
    MEDIA_LOG_I("SelectTrack begin trackId is " PUBLIC_LOG_D32, trackId);
    std::vector<std::shared_ptr<Meta>> metaInfo = demuxer_->GetStreamMetaInfo();
    std::string mime;
    FALSE_RETURN_V_MSG_W(trackId >= 0 && trackId < static_cast<int32_t>(metaInfo.size()),
        MSERR_INVALID_VAL, "SelectTrack trackId invalid");
    if (!(metaInfo[trackId]->GetData(Tag::MIME_TYPE, mime))) {
        MEDIA_LOG_E("SelectTrack trackId " PUBLIC_LOG_D32 "get mime error", trackId);
        return MSERR_INVALID_VAL;
    }
    if (IsAudioMime(mime)) {
        FALSE_RETURN_V_MSG_W(trackId != currentAudioTrackId_, MSERR_INVALID_VAL, "SelectTrack trackId invalid");
        if (currentAudioTrackId_ < 0) {
            if (Status::OK != InitAudioDefaultTrackIndex()) {
                MEDIA_LOG_W("Init audio default track index fail");
            }
        }
    } else if (IsVideoMime(mime)) {
        FALSE_RETURN_V_MSG_W(trackId != currentVideoTrackId_, MSERR_INVALID_VAL, "SelectTrack trackId invalid");
        if (currentVideoTrackId_ < 0) {
            if (Status::OK != InitVideoDefaultTrackIndex()) {
                MEDIA_LOG_W("Init video default track index fail");
            }
        }
    } else if (IsSubtitleMime(mime)) {
        FALSE_RETURN_V_MSG_W(trackId != currentSubtitleTrackId_, MSERR_INVALID_VAL, "SelectTrack trackId invalid");
        if (currentSubtitleTrackId_ < 0) {
            if (Status::OK != InitSubtitleDefaultTrackIndex()) {
                MEDIA_LOG_W("Init subtitle default track index fail");
            }
        }
    } else {
        MEDIA_LOG_E("SelectTrack invalid mimeType. trackId is " PUBLIC_LOG_D32, trackId);
        return MSERR_UNKNOWN;
    }
    return InnerSelectTrack(mime, trackId, mode);
}

int32_t HiPlayerImpl::DeselectTrack(int32_t trackId)
{
    MEDIA_LOG_I("DeselectTrack trackId is " PUBLIC_LOG_D32, trackId);
    std::vector<std::shared_ptr<Meta>> metaInfo = demuxer_->GetStreamMetaInfo();
    FALSE_RETURN_V_MSG_W(trackId >= 0 && trackId < static_cast<int32_t>(metaInfo.size()),
        MSERR_INVALID_VAL, "DeselectTrack trackId invalid");
    std::string mime;
    if (!(metaInfo[trackId]->GetData(Tag::MIME_TYPE, mime))) {
        MEDIA_LOG_E("DeselectTrack trackId " PUBLIC_LOG_D32 "get mime error", trackId);
        return MSERR_INVALID_VAL;
    }
    if (IsAudioMime(mime)) {
        FALSE_RETURN_V_MSG_W(trackId == currentAudioTrackId_ && currentAudioTrackId_ >= 0,
            MSERR_INVALID_VAL, "DeselectTrack trackId invalid");
        return SelectTrack(defaultAudioTrackId_, PlayerSwitchMode::SWITCH_SMOOTH);
    } else if (IsVideoMime(mime)) {
        FALSE_RETURN_V_MSG_W(trackId == currentVideoTrackId_ && currentVideoTrackId_ >= 0,
            MSERR_INVALID_VAL, "DeselectTrack trackId invalid");
        return SelectTrack(defaultVideoTrackId_, PlayerSwitchMode::SWITCH_SMOOTH);
    } else if (IsSubtitleMime(mime)) {
        FALSE_RETURN_V_MSG_W(trackId == currentSubtitleTrackId_ && currentSubtitleTrackId_ >= 0,
            MSERR_INVALID_VAL, "DeselectTrack trackId invalid");
        if (needUpdateSubtitle_.load()) {
            needUpdateSubtitle_.store(false);
        } else {
            needUpdateSubtitle_.store(true);
        }
    } else {}
    return MSERR_OK;
}

int32_t HiPlayerImpl::GetVideoTrackInfo(std::vector<Format>& videoTrack)
{
    MEDIA_LOG_D("GetVideoTrackInfo in");
    FALSE_RETURN_V(demuxer_ != nullptr, MSERR_INVALID_STATE);
    std::string mime;
    std::vector<std::shared_ptr<Meta>> metaInfo = demuxer_->GetStreamMetaInfo();
    for (size_t trackIndex = 0; trackIndex < metaInfo.size(); trackIndex++) {
        auto trackInfo = metaInfo[trackIndex];
        if (!(trackInfo->GetData(Tag::MIME_TYPE, mime)) || mime.find("invalid") == 0) {
            MEDIA_LOG_W("Get MIME fail");
            continue;
        }
        if (IsVideoMime(mime)) {
            Format videoTrackInfo {};
            playStatisticalInfo_.videoMime = mime;
            videoTrackInfo.PutStringValue("codec_mime", mime);
            videoTrackInfo.PutIntValue("track_type", static_cast<int32_t>(OHOS::Media::Plugins::MediaType::VIDEO));
            videoTrackInfo.PutIntValue("track_index", trackIndex);
            int64_t bitRate;
            trackInfo->GetData(Tag::MEDIA_BITRATE, bitRate);
            playStatisticalInfo_.videoBitrate = static_cast<int32_t>(bitRate);
            videoTrackInfo.PutLongValue("bitrate", bitRate);
            double frameRate;
            trackInfo->GetData(Tag::VIDEO_FRAME_RATE, frameRate);
            playStatisticalInfo_.videoFrameRate = static_cast<float>(frameRate);
            videoTrackInfo.PutDoubleValue("frame_rate", frameRate * FRAME_RATE_UNIT_MULTIPLE);
            int32_t height = GetSarVideoHeight(trackInfo);
            videoTrackInfo.PutIntValue("height", height);
            int32_t width = GetSarVideoWidth(trackInfo);
            playStatisticalInfo_.videoResolution = std::to_string(width) + "x" + std::to_string(height);
            videoTrackInfo.PutIntValue("width", width);
            Plugins::VideoRotation rotation;
            trackInfo->Get<Tag::VIDEO_ROTATION>(rotation);
            videoTrackInfo.PutIntValue(Tag::VIDEO_ROTATION, rotation);
            videoTrackInfo.PutStringValue("track_name", "video");
            bool isHdr = false;
            trackInfo->GetData(Tag::VIDEO_IS_HDR_VIVID, isHdr);
            if (isHdr) {
                playStatisticalInfo_.hdrType = static_cast<int8_t>(VideoHdrType::VIDEO_HDR_TYPE_VIVID);
                videoTrackInfo.PutIntValue("hdr_type", 1);
            } else {
                playStatisticalInfo_.hdrType = static_cast<int8_t>(VideoHdrType::VIDEO_HDR_TYPE_NONE);
                videoTrackInfo.PutIntValue("hdr_type", 0);
            }
            videoTrack.emplace_back(std::move(videoTrackInfo));
        }
    }
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::GetSarVideoWidth(std::shared_ptr<Meta> trackInfo)
{
    int32_t width;
    trackInfo->GetData(Tag::VIDEO_WIDTH, width);
    double videoSar;
    bool ret = trackInfo->GetData(Tag::VIDEO_SAR, videoSar);
    if (ret && videoSar < 1) {
        width = static_cast<int32_t>(width * videoSar);
    }
    return width;
}

int32_t HiPlayerImpl::GetSarVideoHeight(std::shared_ptr<Meta> trackInfo)
{
    int32_t height;
    trackInfo->GetData(Tag::VIDEO_HEIGHT, height);
    double videoSar;
    bool ret = trackInfo->GetData(Tag::VIDEO_SAR, videoSar);
    if (ret && videoSar > 1) {
        height = static_cast<int32_t>(height / videoSar);
    }
    return height;
}

int32_t HiPlayerImpl::GetPlaybackInfo(Format& playbackInfo)
{
    MEDIA_LOG_D("GetPlaybackInfo in");

    PlaybackInfo playbackInfoTmp;
    auto ret = demuxer_->GetPlaybackInfo(playbackInfoTmp);
    if (ret == Status::OK) {
        playbackInfo.PutStringValue("server_ip_address", playbackInfoTmp.serverIpAddress);
        playbackInfo.PutLongValue("average_download_rate", playbackInfoTmp.averageDownloadRate);
        playbackInfo.PutLongValue("download_rate", playbackInfoTmp.downloadRate);
        playbackInfo.PutIntValue("is_downloading", playbackInfoTmp.isDownloading);
        playbackInfo.PutLongValue("buffer_duration", playbackInfoTmp.bufferDuration);
    }
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::GetPlaybackStatisticMetrics(Format &playbackStatisticMetrics)
{
    MEDIA_LOG_D("GetPlaybackStatisticMetrics in");

    DownloadInfo downloadInfo;
    FALSE_RETURN_V(demuxer_ != nullptr && dfxAgent_ != nullptr, TransStatus(Status::ERROR_NULL_POINTER));
    auto ret = demuxer_->GetDownloadInfo(downloadInfo);
    if (ret == Status::OK) {
        MetricsUpdateDuration();
        playbackStatisticMetrics.PutUintValue("prepare_duration", static_cast<uint32_t>(prepareDuration_));
        playbackStatisticMetrics.PutUintValue(
            "resource_connection_duration", static_cast<uint32_t>(downloadInfo.firstDownloadTime));
        playbackStatisticMetrics.PutUintValue(
            "first_frame_decapsulation_duration", static_cast<uint32_t>(downloadInfo.firstFrameDecapsulationTime));
        playbackStatisticMetrics.PutUintValue("total_playback_time", static_cast<uint32_t>(playTotalDuration_));
        playbackStatisticMetrics.PutUintValue(
            "loading_requests_count", static_cast<uint32_t>(downloadInfo.loadingCount));
        playbackStatisticMetrics.PutUintValue(
            "total_loading_time", static_cast<uint32_t>(downloadInfo.totalLoadingTime));
        playbackStatisticMetrics.PutLongValue("total_loading_bytes", downloadInfo.totalDownLoadBytes);
        int64_t stallingCount = 0;
        dfxAgent_->GetTotalStallingTimes(&stallingCount);
        playbackStatisticMetrics.PutUintValue("stalling_count", static_cast<uint32_t>(stallingCount));
        int64_t totalStallingTime = 0;
        dfxAgent_->GetTotalStallingDuration(&totalStallingTime);
        playbackStatisticMetrics.PutUintValue("total_stalling_time", static_cast<uint32_t>(totalStallingTime));
    }
    int64_t syncCount = 0;
    int64_t totalSyncDurationMs = 0;
    FALSE_RETURN_V(videoDecoder_ != nullptr, TransStatus(Status::OK));
    videoDecoder_->GetAVSyncInfo(syncCount, totalSyncDurationMs);
    playbackStatisticMetrics.PutLongValue("lip_async_count", syncCount);
    playbackStatisticMetrics.PutLongValue("total_lip_async_time", totalSyncDurationMs);
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::GetAudioTrackInfo(std::vector<Format>& audioTrack)
{
    MEDIA_LOG_I("GetAudioTrackInfo in");
    std::string mime;
    std::vector<std::shared_ptr<Meta>> metaInfo = demuxer_->GetStreamMetaInfo();
    for (size_t trackIndex = 0; trackIndex < metaInfo.size(); trackIndex++) {
        auto trackInfo = metaInfo[trackIndex];
        if (!(trackInfo->GetData(Tag::MIME_TYPE, mime)) || mime.find("invalid") == 0) {
            MEDIA_LOG_W("Get MIME fail");
            continue;
        }
        if (IsAudioMime(mime)) {
            playStatisticalInfo_.audioMime = mime;
            Format audioTrackInfo {};
            audioTrackInfo.PutStringValue("codec_mime", mime);
            audioTrackInfo.PutIntValue("track_type", static_cast<int32_t>(OHOS::Media::Plugins::MediaType::AUDIO));
            audioTrackInfo.PutIntValue("track_index", static_cast<int32_t>(trackIndex));
            int64_t bitRate = 0;
            trackInfo->GetData(Tag::MEDIA_BITRATE, bitRate);
            playStatisticalInfo_.audioBitrate = static_cast<int32_t>(bitRate);
            audioTrackInfo.PutLongValue("bitrate", bitRate);
            int32_t audioChannels = 0;
            trackInfo->GetData(Tag::AUDIO_CHANNEL_COUNT, audioChannels);
            playStatisticalInfo_.audioChannelCount = audioChannels;
            audioTrackInfo.PutIntValue("channel_count", audioChannels);
            int32_t audioSampleRate = 0;
            trackInfo->GetData(Tag::AUDIO_SAMPLE_RATE, audioSampleRate);
            playStatisticalInfo_.audioSampleRate = audioSampleRate;
            audioTrackInfo.PutIntValue("sample_rate", audioSampleRate);
            int32_t sampleDepth = 0;
            bool isHasData = trackInfo->GetData(Tag::AUDIO_BITS_PER_CODED_SAMPLE, sampleDepth);
            if (!isHasData || sampleDepth <= 0) {
                trackInfo->GetData(Tag::AUDIO_BITS_PER_RAW_SAMPLE, sampleDepth);
            }
            audioTrackInfo.PutIntValue("sample_depth", sampleDepth);
            std::string lang;
            trackInfo->GetData(Tag::MEDIA_LANGUAGE, lang);
            audioTrackInfo.PutStringValue("language", lang);
            audioTrackInfo.PutStringValue("track_name", "audio");
            audioTrack.emplace_back(std::move(audioTrackInfo));
        }
    }
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::GetSubtitleTrackInfo(std::vector<Format>& subtitleTrack)
{
    MEDIA_LOG_I("GetSubtitleTrackInfo in");
    std::string mime;
    std::vector<std::shared_ptr<Meta>> metaInfo = demuxer_->GetStreamMetaInfo();
    for (size_t trackIndex = 0; trackIndex < metaInfo.size(); trackIndex++) {
        auto trackInfo = metaInfo[trackIndex];
        if (!(trackInfo->GetData(Tag::MIME_TYPE, mime)) || mime.find("invalid") == 0) {
            MEDIA_LOG_W("Get MIME fail");
            continue;
        }
        if (IsSubtitleMime(mime)) {
            playStatisticalInfo_.subtitleMime = mime;
            Format subtitleTrackInfo {};
            subtitleTrackInfo.PutStringValue("codec_mime", mime);
            subtitleTrackInfo.PutIntValue("track_type",
                static_cast<int32_t>(OHOS::Media::Plugins::MediaType::SUBTITLE));
            subtitleTrackInfo.PutIntValue("track_index", static_cast<int32_t>(trackIndex));

            std::string lang;
            trackInfo->GetData(Tag::MEDIA_LANGUAGE, lang);
            subtitleTrackInfo.PutStringValue("language", lang);
            subtitleTrackInfo.PutStringValue("track_name", "subtitle");

            subtitleTrack.emplace_back(std::move(subtitleTrackInfo));
        }
    }
    return TransStatus(Status::OK);
}

void HiPlayerImpl::SetMediaKitReport(const std::string &apiCall)
{
    MEDIA_LOG_D("SetMediaKitReport in");
    nlohmann::json metaInfoJson;
    std::string videoMime = "";
    std::string audioMime = "";
    std::string subtitleMime = "";
    if (demuxer_ != nullptr && curState_ != PlayerStateId::IDLE && curState_ != PlayerStateId::INIT &&
 	    curState_ != PlayerStateId::PREPARING) {
        std::string mime;
        std::vector<std::shared_ptr<Meta>> streamMetaInfo = demuxer_->GetStreamMetaInfo();
        for (size_t trackIndex = 0; trackIndex < streamMetaInfo.size(); trackIndex++) {
            auto trackInfo = streamMetaInfo[trackIndex];
            if (!(trackInfo->GetData(Tag::MIME_TYPE, mime)) || mime.find("invalid") == 0) {
                MEDIA_LOG_W("Get MIME fail");
                continue;
            }
            MEDIA_LOG_D("DfxTrackInfo: %{public}s", mime.c_str());
            if (videoMime == "" && IsVideoMime(mime)) {
                videoMime = mime;
            }
            if (audioMime == "" && IsAudioMime(mime)) {
                audioMime = mime;
            }
            if (subtitleMime == "" && IsSubtitleMime(mime)) {
                subtitleMime = mime;
            }
        }
    }
    metaInfoJson["fileType"] = fileType_;
    metaInfoJson["sourceType"] = sourceType_;
    metaInfoJson["videoMime"] = videoMime;
    metaInfoJson["audioMime"] = audioMime;
    metaInfoJson["subtitleMime"] = subtitleMime;
    std::string events = metaInfoJson.dump();
    std::string instanceIdStr = std::to_string(instanceId_);
    MEDIA_LOG_D("SetMediaKitReport info: %{public}s", events.c_str());
    OHOS::Media::MediaEvent event;
    event.MediaKitStatistics("AVPlayer", bundleName_, instanceIdStr, apiCall, events);
}

int32_t HiPlayerImpl::GetVideoWidth()
{
#ifdef SUPPORT_VIDEO
    MEDIA_LOG_D_SHORT("GetVideoWidth in. video width: " PUBLIC_LOG_D32, videoWidth_.load());
#endif
    return videoWidth_.load();
}

int32_t HiPlayerImpl::GetVideoHeight()
{
#ifdef SUPPORT_VIDEO
    MEDIA_LOG_D_SHORT("GetVideoHeight in. video height: " PUBLIC_LOG_D32, videoHeight_.load());
#endif
    return videoHeight_.load();
}

int32_t HiPlayerImpl::SetVideoScaleType(OHOS::Media::VideoScaleType videoScaleType)
{
    MEDIA_LOG_D_SHORT("SetVideoScaleType " PUBLIC_LOG_D32, videoScaleType);
#ifdef SUPPORT_VIDEO
    auto meta = std::make_shared<Meta>();
    meta->Set<Tag::VIDEO_SCALE_TYPE>(static_cast<int32_t>(videoScaleType));
    if (videoDecoder_) {
        videoDecoder_->SetParameter(meta);
    }
    return TransStatus(Status::OK);
#else
    return TransStatus(Status::OK);
#endif
}

int32_t HiPlayerImpl::SetFrameRateForSeekPerformance(double frameRate)
{
    MEDIA_LOG_I("SetFrameRateForSeekPerformance, frameRate: %{public}f", frameRate);
#ifdef SUPPORT_VIDEO
    auto meta = std::make_shared<Meta>();
    meta->Set<Tag::VIDEO_FRAME_RATE>(frameRate);
    if (videoDecoder_) {
        videoDecoder_->SetParameter(meta);
    }
    return TransStatus(Status::OK);
#else
    return TransStatus(Status::OK);
#endif
}

int32_t HiPlayerImpl::SetAudioRendererInfo(const int32_t contentType, const int32_t streamUsage,
                                           const int32_t rendererFlag, const int32_t volumeMode)
{
    MEDIA_LOG_I("SetAudioRendererInfo in, coutentType: " PUBLIC_LOG_D32 ", streamUsage: " PUBLIC_LOG_D32
        ", rendererFlag: " PUBLIC_LOG_D32, contentType, streamUsage, rendererFlag);
    Plugins::AudioRenderInfo audioRenderInfo {contentType, streamUsage, rendererFlag, volumeMode};
    if (audioRenderInfo_ == nullptr) {
        audioRenderInfo_ = std::make_shared<Meta>();
    }
    audioRenderInfo_->SetData(Tag::AUDIO_RENDER_SET_FLAG, true);
    audioRenderInfo_->SetData(Tag::AUDIO_RENDER_INFO, audioRenderInfo);
    if (audioSink_ != nullptr) {
        audioSink_->SetParameter(audioRenderInfo_);
    }
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetPrivacyType(const int32_t privacyType)
{
    MEDIA_LOG_D("SetPrivacyType, privacyType is: %{public}d", privacyType);
    privacyType_ = std::make_shared<Meta>();

    privacyType_->SetData("PRIVACY_TYPE", privacyType);
    if (audioSink_ != nullptr) {
        audioSink_->SetParameter(privacyType_);
    }
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetAudioInterruptMode(const int32_t interruptMode)
{
    MEDIA_LOG_I("SetAudioInterruptMode in");
    audioInterruptMode_ = std::make_shared<Meta>();
    audioInterruptMode_->SetData(Tag::AUDIO_INTERRUPT_MODE, interruptMode);
    if (audioSink_ != nullptr) {
        audioSink_->SetParameter(audioInterruptMode_);
    }
    return TransStatus(Status::OK);
}

void HiPlayerImpl::OnEvent(const Event &event)
{
    MEDIA_LOG_D("OnEvent entered, event type is: %{public}d", event.type);
    switch (event.type) {
        case EventType::EVENT_IS_LIVE_STREAM: {
            HandleIsLiveStreamEvent(AnyCast<bool>(event.param));
            break;
        }
        case EventType::EVENT_ERROR: {
            OnStateChanged(PlayerStateId::ERROR);
            HandleErrorEvent(event);
            break;
        }
        case EventType::EVENT_READY: {
            OnStateChanged(PlayerStateId::READY);
            break;
        }
        case EventType::EVENT_COMPLETE: {
            HandleCompleteEvent(event);
            break;
        }
        case EventType::EVENT_AUDIO_INTERRUPT: {
            NotifyAudioInterrupt(event);
            break;
        }
        case EventType::EVENT_AUDIO_FIRST_FRAME: {
            isAudioInitialized_.store(true);
            NotifyAudioFirstFrame(event);
            HandleInitialPlayingStateChange(event.type);
            break;
        }
        case EventType::EVENT_DRM_INFO_UPDATED:
            HandleDrmInfoUpdatedEvent(event);
            break;
        case EventType::EVENT_VIDEO_RENDERING_START: {
            MEDIA_LOG_D_SHORT("video first frame reneder received");
            if (IsAppEnableRenderFirstFrame(appUid_)) {
                // if app enable render first frame, notify first frame render event at once
                Format format;
                callbackLooper_.OnInfo(INFO_TYPE_MESSAGE, PlayerMessageType::PLAYER_INFO_VIDEO_RENDERING_START, format);
            }
            HandleInitialPlayingStateChange(event.type);
            break;
        }
        case EventType::EVENT_RELEASE_VIDEO_DECODER:
            ReleaseVideoDecoderOnMuted();
            break;
        case EventType::EVENT_VIDEO_NO_NEED_INIT:
            HandleInitialPlayingStateChange(EventType::EVENT_VIDEO_RENDERING_START);
            break;
        default:
            OnEventContinue(event);
    }
    OnEventSub(event);
}

void HiPlayerImpl::OnEventContinue(const Event &event)
{
    MEDIA_LOG_D("OnEvent entered, event type is: %{public}d", event.type);
    switch (event.type) {
        case EventType::EVENT_RESOLUTION_CHANGE: {
            MEDIA_LOG_D_SHORT("resolution change event received");
            HandleResolutionChangeEvent(event);
            break;
        }
        case EventType::EVENT_SEI_INFO: {
            HandleSeiInfoEvent(event);
            break;
        }
        case EventType::EVENT_FLV_AUTO_SELECT_BITRATE: {
            HandleFlvAutoSelectBitRate(AnyCast<int32_t>(event.param));
            break;
        }
        case EventType::EVENT_VIDEO_DECODER_RESTART: {
            if (demuxer_ != nullptr) {
                demuxer_->NotifyResumeUnMute();
            }
            break;
        }
        case EventType::EVENT_HW_DECODER_UNSUPPORT_CAP: {
            OnHwDecoderSwitch();
            break;
        }
        case EventType::EVENT_NOTIFY_SEEK_CLOSEST: {
            NotifySeekClosest(AnyCast<bool>(event.param));
            break;
        }
        case EventType::EVENT_TIMED_METADATA: {
            HandleTimedMetaData(AnyCast<std::shared_ptr<MediaAVCodec::AVTimedMetaData>>(event.param));
            break;
        }
        case EventType::EVENT_ADS_CHANGE: {
            HandleAdsChange(AnyCast<std::shared_ptr<MediaAVCodec::AVAdsChangeEvent>>(event.param));
            break;
        }
        case EventType::EVENT_VIDEO_DECODER_CHANGE_END: {
            FALSE_BREAK_NOLOG(demuxer_ != nullptr);
            demuxer_->StartTask(OHOS::Media::Plugins::MediaType::VIDEO);
            break;
        }
        default:
            break;
    }
}

void HiPlayerImpl::OnHwDecoderSwitch()
{
    isNeedSwDecoder_ = true;
    notNotifyForSw_ = true;
    PrepareAsync();
}

void HiPlayerImpl::NotifySeekClosest(bool isSeekDone)
{
    FALSE_RETURN_NOLOG(videoDecoder_ != nullptr);
    videoDecoder_->ClosestSeekDone(isSeekDone);
}

void HiPlayerImpl::HandleSeiInfoEvent(const Event &event)
{
    Format format = AnyCast<Format>(event.param);

    int32_t playbackPos = 0;
    format.GetIntValue(Tag::AV_PLAYER_SEI_PLAYBACK_POSITION, playbackPos);
    format.PutIntValue(Tag::AV_PLAYER_SEI_PLAYBACK_POSITION, playbackPos - Plugins::Us2Ms(mediaStartPts_));

    callbackLooper_.OnInfo(INFO_TYPE_SEI_UPDATE_INFO, 0, format);
}

void HiPlayerImpl::HandleFlvAutoSelectBitRate(uint32_t bitRate)
{
    MEDIA_LOG_I("flv auto select bitrate");
    Format selectBitRateFormat;
    callbackLooper_.OnInfo(INFO_TYPE_FLV_AUTO_SELECT_BITRATE, bitRate, selectBitRateFormat);
}

void HiPlayerImpl::OnEventSub(const Event &event)
{
    switch (event.type) {
        case EventType::EVENT_AUDIO_DEVICE_CHANGE : {
            NotifyAudioDeviceChange(event);
            break;
        }
        case EventType::EVENT_AUDIO_SERVICE_DIED : {
            NotifyAudioServiceDied();
            break;
        }
        case EventType::EVENT_SOURCE_BITRATE_START: {
            HandleBitrateStartEvent(event);
            break;
        }
        case EventType::EVENT_SUBTITLE_TEXT_UPDATE: {
            NotifySubtitleUpdate(event);
            break;
        }
        case EventType::EVENT_CACHED_DURATION: {
            int32_t cachedDuration = AnyCast<int32_t>(event.param);
            NotifyCachedDuration(AdjustCachedDuration(cachedDuration));
            break;
        }
        case EventType::EVENT_BUFFER_PROGRESS: {
            NotifyBufferingUpdate(PlayerKeys::PLAYER_BUFFERING_PERCENT, AnyCast<int32_t>(event.param));
            break;
        }
        case EventType::EVENT_DECODE_ERROR_FRAME:
            NotifyDecoderErrorFrame(AnyCast<int64_t>(event.param));
            break;
        case EventType::EVENT_AUDIO_DECODER_CHANGE: {
            HandleAudioDecoderChangeEvent(event);
            break;
        }
        case EventType::EVENT_AUDIO_TRACK_CHANGE_REPORT: {
            HandleAudioTrackChangeReportEvent(event);
            break;
        }
        default:
            break;
    }
    OnEventSubTrackChange(event);
}

void HiPlayerImpl::OnEventSubTrackChange(const Event &event)
{
    switch (event.type) {
        case EventType::EVENT_AUDIO_TRACK_CHANGE: {
            HandleAudioTrackChangeEvent(event);
            break;
        }
        case EventType::EVENT_VIDEO_TRACK_CHANGE: {
            HandleVideoTrackChangeEvent(event);
            break;
        }
        case EventType::EVENT_SUBTITLE_TRACK_CHANGE: {
            HandleSubtitleTrackChangeEvent(event);
            break;
        }
        case EventType::EVENT_SUPER_RESOLUTION_CHANGED: {
            if (isReInitPostProcessor_) {
                isReInitPostProcessor_ = false;
                break;
            }
            NotifySuperResolutionChanged(event);
            break;
        }
        case EventType::BUFFERING_END : {
            {
                std::unique_lock<std::mutex> lock(flvLiveMutex_);
                isBufferingEnd_ = true;
            }
            flvLiveCond_.notify_all();
            if (!isBufferingStartNotified_.load() || isSeekClosest_.load()) {
                MEDIA_LOGI_LIMIT(BUFFERING_LOG_FREQUENCY, "BUFFERING_END BLOCKED");
                break;
            }
            MEDIA_LOG_I_SHORT("BUFFERING_END PLAYING");
            NotifyBufferingEnd(AnyCast<int32_t>(event.param));
            break;
        }
        case EventType::BUFFERING_START : {
            if (isBufferingStartNotified_.load()) {
                MEDIA_LOGI_LIMIT(BUFFERING_LOG_FREQUENCY, "BUFFERING_START BLOCKED");
                break;
            }
            MEDIA_LOG_I_SHORT("BUFFERING_START PAUSE");
            NotifyBufferingStart(AnyCast<int32_t>(event.param));
            break;
        }
        default:
            break;
    }
}

int32_t HiPlayerImpl::AdjustCachedDuration(int32_t cachedDuration)
{
    int32_t durationMs = durationMs_.load();
    FALSE_RETURN_V_NOLOG(durationMs > 0, cachedDuration);
    int32_t currentTime = 0;
    int32_t res = GetCurrentTime(currentTime);
    FALSE_RETURN_V_NOLOG(res == MSERR_OK && currentTime > 0, std::min(cachedDuration, durationMs));
    int64_t remaining  = static_cast<int64_t>(durationMs) - static_cast<int64_t>(currentTime);
    int32_t safeRemaining = static_cast<int32_t>(std::clamp(
        remaining,
        static_cast<int64_t>(0),
        static_cast<int64_t>(durationMs)
    ));
    return std::min(cachedDuration, safeRemaining);
}

void HiPlayerImpl::HandleInitialPlayingStateChange(const EventType& eventType)
{
    AutoLock lock(initialPlayingEventMutex_);
    MEDIA_LOG_I("HandleInitialPlayingStateChange");
    if (!isInitialPlay_) {
        return;
    }
    for (std::pair<EventType, bool>& item : initialAVStates_) {
        if (item.first == eventType) {
            MEDIA_LOG_I("HandleInitialPlayingStateChange event type received = " PUBLIC_LOG_D32,
                static_cast<int32_t>(eventType));
            item.second = true;
        }
    }

    for (auto item : initialAVStates_) {
        if (item.second == false) {
            MEDIA_LOG_I("HandleInitialPlayingStateChange another event type not received " PUBLIC_LOG_D32,
                static_cast<int32_t>(item.first));
            return;
        }
    }

    MEDIA_LOG_D("av first frame reneder all received");

    isInitialPlay_ = false;
    if (!IsAppEnableRenderFirstFrame(appUid_)) {
        // if app not enable render first frame, notify first frame render event when notify playing state
        Format format;
        callbackLooper_.OnInfoDelay(INFO_TYPE_MESSAGE, PlayerMessageType::PLAYER_INFO_VIDEO_RENDERING_START, format,
            FIRST_FRAME_FRAME_REPORT_DELAY_MS);
    }
    OnStateChanged(PlayerStateId::PLAYING);

    int64_t nowTimeMs = GetCurrentMillisecond();
    playStatisticalInfo_.startLatency = static_cast<int32_t>(nowTimeMs - playStartTime_);
}

void HiPlayerImpl::DoSetPlayStrategy(const std::shared_ptr<MediaSource> source)
{
    std::shared_ptr<PlayStrategy> playStrategy = std::make_shared<PlayStrategy>();
    playStrategy->width = preferedWidth_;
    playStrategy->height = preferedHeight_;
    playStrategy->duration = bufferDuration_;
    playStrategy->preferHDR = preferHDR_;
    playStrategy->audioLanguage = audioLanguage_;
    playStrategy->subtitleLanguage = subtitleLanguage_;
    playStrategy->bufferDurationForPlaying = bufferDurationForPlaying_;
    playStrategy->thresholdForAutoQuickPlay = maxLivingDelayTime_;
    demuxer_->SetPlayStrategy(playStrategy);
    if (source) {
        source->SetPlayStrategy(playStrategy);
        source->SetAppUid(appUid_);
    }
}

void HiPlayerImpl::DoSetPlayMediaStream(const std::shared_ptr<MediaSource>& source)
{
    FALSE_RETURN(source != nullptr);
    for (auto& mediaStream : playMediaStreamVec_) {
        std::shared_ptr<PlayMediaStream> playMediaStream = std::make_shared<PlayMediaStream>();
        FALSE_RETURN(playMediaStream != nullptr);
        playMediaStream->url = mediaStream.url;
        playMediaStream->width = mediaStream.width;
        playMediaStream->height = mediaStream.height;
        playMediaStream->bitrate = mediaStream.bitrate;
        source->AddMediaStream(playMediaStream);
    }
}

bool HiPlayerImpl::IsLivingMaxDelayTimeValid()
{
    if (maxLivingDelayTime_ < 0) {
        return true;
    }
    if (maxLivingDelayTime_ < AVPlayStrategyConstant::BUFFER_DURATION_FOR_PLAYING_SECONDS ||
        maxLivingDelayTime_ < bufferDurationForPlaying_) {
        return false;
    }
    return true;
}

Status HiPlayerImpl::DoSetSource(const std::shared_ptr<MediaSource> source)
{
    MediaTrace trace("HiPlayerImpl::DoSetSource");
    ResetIfSourceExisted();
    completeState_.clear();
    demuxer_ = FilterFactory::Instance().CreateFilter<DemuxerFilter>("builtin.player.demuxer",
        FilterType::FILTERTYPE_DEMUXER);
    FALSE_RETURN_V(demuxer_ != nullptr, Status::ERROR_NULL_POINTER);
    DoInitDemuxer();
    DoSetPlayStrategy(source);
    if (!mimeType_.empty()) {
        source->SetMimeType(mimeType_);
    }
    if (!seiMessageCbStatus_ && surface_ == nullptr && !isForceLoadVideo_ &&
        mutedMediaType_ != OHOS::Media::MediaType::MEDIA_TYPE_VID) {
        MEDIA_LOG_D("HiPlayerImpl::DisableMediaTrack");
        demuxer_->DisableMediaTrack(OHOS::Media::Plugins::MediaType::VIDEO);
    }
    if (!playMediaStreamVec_.empty()) {
        DoSetPlayMediaStream(source);
    }
    FALSE_RETURN_V(!isInterruptNeeded_, Status::OK);
    demuxer_->SetIsEnableReselectVideoTrack(true);
    Status ret = Status::OK;
    MEDIA_LOG_I("SetDataSource cost ms %{public}" PRId64, CALC_EXPR_TIME_MS(ret = demuxer_->SetDataSource(source)));
    demuxer_->SetCallerInfo(instanceId_, bundleName_);
    demuxer_->SetDumpFlag(isDump_);
    std::shared_ptr<Meta> globalMeta = demuxer_->GetGlobalMetaInfo();
    if (globalMeta != nullptr && globalMeta->GetData(Tag::MEDIA_FILE_TYPE, fileType_)) {
        MEDIA_LOG_D("DoSetSource getFileType: %{public}d", static_cast<int32_t>(fileType_));
    }
    if (ret == Status::OK && !MetaUtils::CheckFileType(globalMeta)) {
        MEDIA_LOG_W("0x%{public}06" PRIXPTR " SetSource unsupport", FAKE_POINTER(this));
        ret = Status::ERROR_INVALID_DATA;
    }
    FALSE_RETURN_V_NOLOG(ret == Status::OK, ret);
    isOnlyAudio_ = !MetaUtils::CheckHasVideo(globalMeta) && MetaUtils::CheckHasAudio(globalMeta);
    std::unique_lock<std::mutex> lock(drmMutex_);
    isDrmProtected_ = demuxer_->IsDrmProtected();
    MEDIA_LOG_I("Is the source drm-protected : %{public}d", isDrmProtected_);
    lock.unlock();
    if (hasExtSub_) {
        demuxer_->SetSubtitleSource(std::make_shared<MediaSource>(subUrl_));
    }
    SetBundleName(bundleName_);
    demuxer_->OptimizeDecodeSlow(IsEnableOptimizeDecode());
    return ret;
}

Status HiPlayerImpl::Resume()
{
    MediaTrace trace("HiPlayerImpl::Resume");
    MEDIA_LOG_I("Resume entered.");
    Status ret = Status::OK;
    syncManager_->Resume();
    ret = pipeline_->Resume();
    if (ret != Status::OK) {
        UpdateStateNoLock(PlayerStates::PLAYER_STATE_ERROR);
    }
    startTime_ = GetCurrentMillisecond();
    return ret;
}

void HiPlayerImpl::HandleIsLiveStreamEvent(bool isLiveStream)
{
    Format format;
    format.PutIntValue(PlayerKeys::PLAYER_IS_FLV_LIVE, isFlvLive_);
    callbackLooper_.OnInfo(INFO_TYPE_IS_LIVE_STREAM, isLiveStream, format);
}

PlayerErrorType HiPlayerImpl::GetPlayerErrorTypeFromDemuxerFilter(const Event& event)
{
    PlayerErrorType errorType = PlayerErrorType::PLAYER_ERROR_UNKNOWN;
    int32_t errorCode = AnyCast<int32_t>(event.param);

    switch (errorCode) {
        case MSERR_DEMUXER_FAILED:
        case MSERR_UNSUPPORT_CONTAINER_TYPE:
            errorType = PlayerErrorType::DEM_FMT_ERR;
            break;
        case MSERR_DATA_SOURCE_ERROR_UNKNOWN:
        case MSERR_DEMUXER_BUFFER_NO_MEMORY:
            errorType = PlayerErrorType::DEM_PARSE_ERR;
            break;
        case static_cast<int32_t>(NetworkClientErrorCode::ERROR_TIME_OUT):
        case static_cast<int32_t>(NetworkClientErrorCode::ERROR_NOT_RETRY):
            errorType = PlayerErrorType::NET_ERR;
            break;
        default:
            if (event.description == "server" || event.description.find("requestError: true")) {
                errorType = PlayerErrorType::NET_ERR;
            }
            break;
    }

    return errorType;
}

PlayerErrorType HiPlayerImpl::GetPlayerErrorTypeFromAudioDecoder(const Event& event)
{
    PlayerErrorType errorType = PlayerErrorType::PLAYER_ERROR_UNKNOWN;
    int32_t errorCode = AnyCast<int32_t>(event.param);

    switch (errorCode) {
        case MSERR_UNSUPPORT_AUD_DEC_TYPE:
            errorType = PlayerErrorType::AUD_DEC_ERR;
            break;
        case MSERR_DRM_VERIFICATION_FAILED:
            errorType = PlayerErrorType::DRM_ERR;
            break;
        default:
            break;
    }

    return errorType;
}

PlayerErrorType HiPlayerImpl::GetPlayerErrorTypeFromDecoderSurfaceFilter(const Event& event)
{
    PlayerErrorType errorType = PlayerErrorType::PLAYER_ERROR_UNKNOWN;
    int32_t errorCode = AnyCast<int32_t>(event.param);

    switch (errorCode) {
        case MSERR_EXT_API9_IO:
        case MSERR_UNSUPPORT_VID_SRC_TYPE:
            if (event.description == "post_processor") {
                errorType = PlayerErrorType::VPE_ERR;
            } else {
                errorType = PlayerErrorType::VID_DEC_ERR;
            }
            break;
        case MSERR_UNSUPPORT_VID_DEC_TYPE:
        case MSERR_VID_DEC_FAILED:
            errorType = PlayerErrorType::VID_DEC_ERR;
            break;
        default:
            break;
    }

    return errorType;
}

PlayerErrorType HiPlayerImpl::GetPlayerErrorTypeFromAudioSinkFilter(const Event& event)
{
    PlayerErrorType errorType = PlayerErrorType::PLAYER_ERROR_UNKNOWN;
    int32_t errorCode = AnyCast<int32_t>(event.param);

    switch (errorCode) {
        case MSERR_AUD_RENDER_FAILED:
            errorType = PlayerErrorType::AUD_OUTPUT_ERR;
            break;
        default:
            break;
    }

    return errorType;
}

PlayerErrorType HiPlayerImpl::GetPlayerErrorTypeFromAudioServerSinkPlugin(const Event& event)
{
    PlayerErrorType errorType = PlayerErrorType::PLAYER_ERROR_UNKNOWN;
    int32_t errorCode = AnyCast<int32_t>(event.param);

    switch (errorCode) {
        case MSERR_UNSUPPORT_AUD_SAMPLE_RATE:
        case MSERR_UNSUPPORT_AUD_CHANNEL_NUM:
        case MSERR_UNSUPPORT_AUD_PARAMS:
            errorType = PlayerErrorType::AUD_OUTPUT_ERR;
            break;
        default:
            break;
    }

    return errorType;
}

PlayerErrorType HiPlayerImpl::GetPlayerErrorTypeFromEngine(const Event& event)
{
    PlayerErrorType errorType = PlayerErrorType::PLAYER_ERROR_UNKNOWN;
    int32_t errorCode = AnyCast<int32_t>(event.param);

    switch (errorCode) {
        case MSERR_SEEK_CONTINUOUS_UNSUPPORTED:
        case MSERR_DATA_SOURCE_IO_ERROR:
        case MSERR_INVALID_VAL:
            errorType = PlayerErrorType::PLAY_ERR;
            break;
        case MSERR_UNSUPPORT_CONTAINER_TYPE:
            errorType = PlayerErrorType::CONTAINER_ERR;
            break;
        default:
            break;
    }

    return errorType;
}

PlayerErrorType HiPlayerImpl::GetPlayerErrorType(const Event& event)
{
    PlayerErrorType errorType = PlayerErrorType::PLAYER_ERROR_UNKNOWN;
    std::string filter = event.srcFilter;

    if (filter == "demuxer_filter") {
        errorType = GetPlayerErrorTypeFromDemuxerFilter(event);
    } else if (filter == "audioDecoder") {
        errorType = GetPlayerErrorTypeFromAudioDecoder(event);
    } else if (filter == "decoderSurface" ||
        filter == "surface_decoder_filter" ||
        filter == "DecoderSurfaceFilter") {
        errorType = GetPlayerErrorTypeFromDecoderSurfaceFilter(event);
    } else if (filter == "audio_sink_filter") {
        errorType = GetPlayerErrorTypeFromAudioSinkFilter(event);
    } else if (filter == "audioSinkPlugin" || filter == "sampleRate isn't supported" ||
               filter == "channel isn't supported" || filter == "sampleFmt isn't supported") {
        errorType = GetPlayerErrorTypeFromAudioServerSinkPlugin(event);
    } else if (filter == "engine") {
        errorType = GetPlayerErrorTypeFromEngine(event);
    }

    return errorType;
}

void HiPlayerImpl::HandleErrorEvent(const Event& event)
{
    int32_t errorCode = AnyCast<int32_t>(event.param);
    PlayerErrorType errorType = GetPlayerErrorType(event);
    SetMediaKitReport("avplayer error: " + std::to_string(errorType));
    callbackLooper_.OnError(errorType, errorCode, event.description);
}

void HiPlayerImpl::NotifyBufferingStart(int32_t param)
{
    Format format;
    isBufferingStartNotified_.store(true);
    callbackLooper_.StopReportMediaProgress();
    callbackLooper_.ManualReportMediaProgressOnce();
    (void)format.PutIntValue(std::string(PlayerKeys::PLAYER_BUFFERING_START), 1);
    callbackLooper_.OnInfo(INFO_TYPE_BUFFERING_UPDATE, param, format);
}

void HiPlayerImpl::NotifyBufferingEnd(int32_t param)
{
    MEDIA_LOG_I("NotifyBufferingEnd");
    Format format;
    isBufferingStartNotified_.store(false);
    (void)format.PutIntValue(std::string(PlayerKeys::PLAYER_BUFFERING_END), 1);
    callbackLooper_.OnInfo(INFO_TYPE_BUFFERING_UPDATE, param, format);
}

void HiPlayerImpl::NotifyCachedDuration(int32_t param)
{
    MEDIA_LOG_D("NotifyCachedDuration");
    Format format;
    (void)format.PutIntValue(std::string(PlayerKeys::PLAYER_CACHED_DURATION), param);
    callbackLooper_.OnInfo(INFO_TYPE_BUFFERING_UPDATE, param, format);
}

bool HiPlayerImpl::HandleEosFlagState(const Event& event)
{
    bool isAllEos = true;
    for (std::pair<std::string, bool>& item: completeState_) {
        if (item.first == event.srcFilter) {
            MEDIA_LOG_I("one eos event received " PUBLIC_LOG_S, item.first.c_str());
            item.second = true;
            if (item.first == "AudioSink" && videoDecoder_) {
                videoDecoder_->NotifyAudioComplete();
            }
        } else if (!item.second) {
            MEDIA_LOG_I("expect receive eos event " PUBLIC_LOG_S, item.first.c_str());
            isAllEos = false;
        }
    }
    return isAllEos;
}

void HiPlayerImpl::HandleCompleteEvent(const Event& event)
{
    MEDIA_LOG_D_SHORT("HandleCompleteEvent");
    AutoLock lock(handleCompleteMutex_);
    FALSE_RETURN_NOLOG(curState_ != PlayerStateId::STOPPED && HandleEosFlagState(event));
    FALSE_RETURN_MSG(syncManager_ != nullptr, "syncManager_ is nullptr");
    syncManager_->ReportStreamEos();
    FALSE_RETURN_MSG(!inEosPlayingSeekContinuous_, "Skip complete event in seek continous!");
    std::unique_lock<std::mutex> freezeLock(freezeMutex_);
    MEDIA_LOG_I("OnComplete looping: " PUBLIC_LOG_D32 ".", singleLoop_.load());
    isStreaming_ = false;
    Format format;
    int32_t curPosMs = 0;
    GetCurrentTime(curPosMs);
    if ((GetPlayRangeEndTime() == PLAY_RANGE_DEFAULT_VALUE) &&
        (durationMs_.load() > curPosMs && abs(durationMs_.load() - curPosMs) < AUDIO_SINK_MAX_LATENCY)) {
        MEDIA_LOG_I("OnComplete durationMs - curPosMs: " PUBLIC_LOG_D32, durationMs_.load() - curPosMs);
    }
    if (!singleLoop_.load()) {
        callbackLooper_.StopReportMediaProgress();
        StopFlvCheckLiveDelayTime();
        callbackLooper_.StopCollectMaxAmplitude();
    } else {
        inEosSeek_ = true;
        eosInLoopForFrozen_ = true;
    }
    callbackLooper_.DoReportCompletedTime();
    FALSE_RETURN_MSG(pipeline_ != nullptr, "pipeline_ is nullptr!");
    if (pipelineStates_ != PlayerStates::PLAYER_FROZEN || !singleLoop_.load()) {
        pipeline_->Pause();
    }
    if (isSetPlayRange_ && (startTimeWithMode_ == PLAY_RANGE_DEFAULT_VALUE ||
        endTimeWithMode_ == PLAY_RANGE_DEFAULT_VALUE)) {
        startTimeWithMode_ = PLAY_RANGE_DEFAULT_VALUE;
        endTimeWithMode_ = PLAY_RANGE_DEFAULT_VALUE;
        pipeline_->SetPlayRange(startTimeWithMode_, endTimeWithMode_);
    }
    callbackLooper_.ReportRemainedMaxAmplitude();
    if (!singleLoop_.load()) {
        OnStateChanged(PlayerStateId::EOS);
    } else {
        audioHapticsSyncId_++;
        ApplyAudioHapticsSyncId();
    }
    UpdatePlayTotalDuration();
    callbackLooper_.OnInfo(INFO_TYPE_EOS, static_cast<int32_t>(singleLoop_.load()), format);
    for (std::pair<std::string, bool>& item: completeState_) {
        item.second = false;
    }
}

void HiPlayerImpl::HandleDrmInfoUpdatedEvent(const Event& event)
{
    MEDIA_LOG_I("HandleDrmInfoUpdatedEvent");

    std::multimap<std::string, std::vector<uint8_t>> drmInfo =
        AnyCast<std::multimap<std::string, std::vector<uint8_t>>>(event.param);
    uint32_t infoCount = drmInfo.size();
    if (infoCount > DrmConstant::DRM_MAX_DRM_INFO_COUNT || infoCount == 0) {
        MEDIA_LOG_E("HandleDrmInfoUpdatedEvent info count is invalid");
        return;
    }
    DrmInfoItem *drmInfoArray = new(std::nothrow) DrmInfoItem[infoCount];
    if (drmInfoArray == nullptr) {
        MEDIA_LOG_E("HandleDrmInfoUpdatedEvent new drm info failed");
        return;
    }
    int32_t i = 0;
    for (auto item : drmInfo) {
        uint32_t step = 2;
        for (uint32_t j = 0; j < item.first.size(); j += step) {
            std::string byteString = item.first.substr(j, step);
            unsigned char byte = (unsigned char)strtol(byteString.c_str(), NULL, 16);
            drmInfoArray[i].uuid[j / step] = byte;
        }

        errno_t ret = memcpy_s(drmInfoArray[i].pssh, sizeof(drmInfoArray[i].pssh),
            item.second.data(), item.second.size());
        if (ret != EOK) {
            MEDIA_LOG_E("HandleDrmInfoUpdatedEvent memcpy drm info pssh failed");
            delete []drmInfoArray;
            return;
        }
        drmInfoArray[i].psshLen = item.second.size();
        i++;
    }

    // report event
    Format format;
    size_t drmInfoSize = static_cast<size_t>(infoCount) * sizeof(DrmInfoItem);
    (void) format.PutBuffer(PlayerKeys::PLAYER_DRM_INFO_ADDR,
        reinterpret_cast<const uint8_t *>(drmInfoArray), drmInfoSize);
    (void) format.PutIntValue(PlayerKeys::PLAYER_DRM_INFO_COUNT, static_cast<int32_t>(infoCount));
    callbackLooper_.OnInfo(INFO_TYPE_DRM_INFO_UPDATED, static_cast<int32_t>(singleLoop_.load()), format);

    delete []drmInfoArray;
}

void HiPlayerImpl::HandleResolutionChangeEvent(const Event& event)
{
#ifdef SUPPORT_VIDEO
    // update new video size
    std::pair<int32_t, int32_t> videoSize = AnyCast<std::pair<int32_t, int32_t>>(event.param);
    int32_t width = videoSize.first;
    int32_t height = videoSize.second;

    std::vector<std::shared_ptr<Meta>> metaInfo = demuxer_->GetStreamMetaInfo();
    if (currentVideoTrackId_ >= 0 && currentVideoTrackId_ < static_cast<int32_t>(metaInfo.size())) {
        double videoSar;
        bool ret = metaInfo[currentVideoTrackId_]->GetData(Tag::VIDEO_SAR, videoSar);
        if (ret) {
            height = (videoSar > 1) ? static_cast<int32_t>(height / videoSar) : height;
            width = (videoSar < 1) ? static_cast<int32_t>(width * videoSar) : width;
        }
    }

    videoWidth_ = !needSwapWH_.load() ? width : height;
    videoHeight_ = !needSwapWH_.load() ? height : width;
    MEDIA_LOG_I("HandleResolutionChangeEvent, width = %{public}d, height = %{public}d",
        videoWidth_.load(), videoHeight_.load());
    // notify size change
    NotifyResolutionChange();
#endif
}

void HiPlayerImpl::HandleBitrateStartEvent(const Event& event)
{
#ifdef SUPPORT_VIDEO
    uint32_t bitrate = AnyCast<uint32_t>(event.param);
    MEDIA_LOG_I("HandleBitrateStartEvent in, bitrate is " PUBLIC_LOG_U32, bitrate);
    FALSE_RETURN(videoDecoder_ != nullptr);
    videoDecoder_->SetBitrateStart();
#endif
}

void HiPlayerImpl::NotifySubtitleUpdate(const Event& event)
{
    Format format = AnyCast<Format>(event.param);
    if (needUpdateSubtitle_.load()) {
        callbackLooper_.OnInfo(INFO_TYPE_SUBTITLE_UPDATE_INFO, 0, format);
    }
}

void HiPlayerImpl::NotifyDecoderErrorFrame(int64_t pts)
{
    FALSE_RETURN_MSG(demuxer_ != nullptr, "DemuxerFilter is nullptr");
    demuxer_->HandleDecoderErrorFrame(pts);
}

void HiPlayerImpl::UpdateStateNoLock(PlayerStates newState, bool notifyUpward, bool isSystemOperation)
{
    if (pipelineStates_ == newState) {
        return;
    }
    pipelineStates_ = newState;
    if (pipelineStates_ == PlayerStates::PLAYER_IDLE || pipelineStates_ == PlayerStates::PLAYER_PREPARING) {
        MEDIA_LOG_D_SHORT("do not report idle and preparing since av player doesn't need report idle and preparing");
        return;
    }
    if (notifyUpward) {
        if (callbackLooper_.IsStarted()) {
            Format format;
            if (isSystemOperation) {
                format.PutIntValue(PlayerKeys::PLAYER_STATE_CHANGED_REASON, StateChangeReason::BACKGROUND);
            }
            while (!pendingStates_.empty()) {
                auto pendingState = pendingStates_.front();
                pendingStates_.pop();
                MEDIA_LOG_I("sending pending state change: " PUBLIC_LOG_S, StringnessPlayerState(pendingState).c_str());
                callbackLooper_.OnInfo(INFO_TYPE_STATE_CHANGE, pendingState, format);
            }
            MEDIA_LOG_I("sending newest state change: " PUBLIC_LOG_S,
                    StringnessPlayerState(pipelineStates_.load()).c_str());
            callbackLooper_.OnInfo(INFO_TYPE_STATE_CHANGE, pipelineStates_, format);
        } else {
            pendingStates_.push(newState);
        }
    }
}

void HiPlayerImpl::NotifyBufferingUpdate(const std::string_view& type, int32_t param)
{
    Format format;
    format.PutIntValue(std::string(type), param);
    MEDIA_LOG_D("NotifyBufferingUpdate param " PUBLIC_LOG_D32, param);
    callbackLooper_.OnInfo(INFO_TYPE_BUFFERING_UPDATE, durationMs_.load(), format);
}

void HiPlayerImpl::NotifyDurationUpdate(const std::string_view& type, int32_t param)
{
    Format format;
    format.PutIntValue(std::string(type), param);
    MEDIA_LOG_I("NotifyDurationUpdate " PUBLIC_LOG_D32, param);
    callbackLooper_.OnInfo(INFO_TYPE_DURATION_UPDATE, param, format);
}

void HiPlayerImpl::NotifySeekDone(int32_t seekPos)
{
    MediaTrace trace(std::string("HiPlayerImpl::NotifySeekDone, seekPos: ") + to_string(seekPos));
    Format format;
    // Report position firstly to make sure that client can get real position when seek done in playing state.
    if (curState_ == PlayerStateId::PLAYING) {
        std::unique_lock<std::mutex> lock(seekMutex_);
        syncManager_->seekCond_.wait_for(
            lock,
            std::chrono::milliseconds(PLAYING_SEEK_WAIT_TIME),
            [this]() {
                return !syncManager_->InSeeking();
            });
    }
    NotifyBufferEnd();
    
    MEDIA_LOG_D_SHORT("NotifySeekDone seekPos: %{public}d", seekPos);
    syncManager_->UpdataPausedMediaTime(seekPos * TIME_CONVERSION_UNIT);
    if (durationMs_ > 0) {
        callbackLooper_.OnInfo(INFO_TYPE_POSITION_UPDATE, seekPos, format);
    }
    callbackLooper_.OnInfo(INFO_TYPE_SEEKDONE, seekPos, format);
}

void HiPlayerImpl::NotifyBufferEnd()
{
    FALSE_RETURN(isSeekClosest_);
    isSeekClosest_.store(false);
    FALSE_RETURN(isBufferingStartNotified_);
    MEDIA_LOG_I_SHORT("SEEK_CLOSEST BUFFERING_END PLAYING");
    FALSE_RETURN(!demuxer_->IsBuffering());
    NotifyBufferingEnd(NOTIFY_BUFFERING_END_PARAM);
}

void HiPlayerImpl::NotifyAudioInterrupt(const Event& event)
{
    Format format;
    auto interruptEvent = AnyCast<AudioStandard::InterruptEvent>(event.param);
    int32_t hintType = interruptEvent.hintType;
    int32_t forceType = interruptEvent.forceType;
    int32_t eventType = interruptEvent.eventType;
    MEDIA_LOG_I("NotifyAudioInterrupt eventType: %{public}d, hintType: %{public}d, forceType: %{public}d",
        eventType, hintType, forceType);
    if (forceType == OHOS::AudioStandard::INTERRUPT_FORCE) {
        if (hintType == OHOS::AudioStandard::INTERRUPT_HINT_PAUSE
            || hintType == OHOS::AudioStandard::INTERRUPT_HINT_STOP) {
            std::unique_lock<std::mutex> freezeLock(freezeMutex_);
            isHintPauseReceived_ = true;
            Status ret = Status::OK;
            CacheBuffer();
            ret = pipeline_->Pause();
            syncManager_->Pause();
            if (ret != Status::OK) {
                UpdateStateNoLock(PlayerStates::PLAYER_STATE_ERROR);
            }
            callbackLooper_.StopReportMediaProgress();
            StopFlvCheckLiveDelayTime();
            callbackLooper_.StopCollectMaxAmplitude();
            HandleReadyAudioInterrupt();
            NotifyAudioStatusDfxEvent(hintType);
        }
    }
    {
        AutoLock lock(interruptMutex_);
        if (isSaveInterruptEventNeeded_.load() && isHintPauseReceived_
            && eventType == OHOS::AudioStandard::INTERRUPT_TYPE_END
            && forceType == OHOS::AudioStandard::INTERRUPT_SHARE
            && hintType == OHOS::AudioStandard::INTERRUPT_HINT_RESUME) {
            interruptNotifyPlay_.store(true);
            interruptEvent_ = interruptEvent;
            return;
        }
        isSaveInterruptEventNeeded_.store(true);
    }
    (void)format.PutIntValue(PlayerKeys::AUDIO_INTERRUPT_TYPE, eventType);
    (void)format.PutIntValue(PlayerKeys::AUDIO_INTERRUPT_FORCE, forceType);
    (void)format.PutIntValue(PlayerKeys::AUDIO_INTERRUPT_HINT, hintType);
    callbackLooper_.OnInfo(INFO_TYPE_INTERRUPT_EVENT, hintType, format);
    if (forceType == OHOS::AudioStandard::INTERRUPT_FORCE) {
        if (hintType == OHOS::AudioStandard::INTERRUPT_HINT_PAUSE
            || hintType == OHOS::AudioStandard::INTERRUPT_HINT_STOP) {
            callbackLooper_.OnSystemOperation(OPERATION_TYPE_PAUSE, OPERATION_REASON_AUDIO_INTERRUPT);
        }
    }
}

void HiPlayerImpl::NotifyAudioStatusDfxEvent(int32_t hintType)
{
    if (dfxAgent_ != nullptr) {
        AudioStatusInfo statusInfo {
            .stateBefore = static_cast<int32_t>(AudioStandard::RendererState::RENDERER_RUNNING),
            .stateAfter = static_cast<int32_t>(hintType == AudioStandard::INTERRUPT_HINT_PAUSE
                ? AudioStandard::RendererState::RENDERER_PAUSED
                : AudioStandard::RendererState::RENDERER_STOPPED),
            .interruptHint = hintType
        };
        dfxAgent_->OnDfxEvent({"HiPlayer", DfxEventType::DFX_EVENT_AUDIO_STATUS, statusInfo});
    }
}

void HiPlayerImpl::NotifyAudioDeviceChange(const Event& event)
{
    MEDIA_LOG_I("NotifyAudioDeviceChange");
    auto [deviceInfo, reason] = AnyCast<std::pair<AudioStandard::AudioDeviceDescriptor,
        AudioStandard::AudioStreamDeviceChangeReason>>(event.param);
    Format format;
    Parcel parcel;
    deviceInfo.Marshalling(parcel);
    auto parcelSize = parcel.GetReadableBytes();
    (void)format.PutBuffer(PlayerKeys::AUDIO_DEVICE_CHANGE,
        parcel.ReadBuffer(parcelSize), parcelSize);
    format.PutIntValue(PlayerKeys::AUDIO_DEVICE_CHANGE_REASON, static_cast<int32_t>(reason));
    callbackLooper_.OnInfo(INFO_TYPE_AUDIO_DEVICE_CHANGE, static_cast<int32_t>(reason), format);
}

void HiPlayerImpl::NotifyAudioServiceDied()
{
    Format format;
    callbackLooper_.OnInfo(INFO_TYPE_ERROR_MSG, MSERR_EXT_API9_IO, format);
}

void HiPlayerImpl::NotifyAudioFirstFrame(const Event& event)
{
    uint64_t latency = AnyCast<uint64_t>(event.param);
    MEDIA_LOG_I("Audio first frame event in latency " PUBLIC_LOG_U64, latency);
    Format format;
    (void)format.PutLongValue(PlayerKeys::AUDIO_FIRST_FRAME, latency);
    callbackLooper_.OnInfo(INFO_TYPE_AUDIO_FIRST_FRAME, 0, format);
}

void HiPlayerImpl::NotifyResolutionChange()
{
#ifdef SUPPORT_VIDEO
    Format format;
    int32_t width = videoWidth_.load();
    int32_t height = videoHeight_.load();
    (void)format.PutIntValue(std::string(PlayerKeys::PLAYER_WIDTH), width);
    (void)format.PutIntValue(std::string(PlayerKeys::PLAYER_HEIGHT), height);
    MEDIA_LOG_I("video size change, width %{public}d, height %{public}d", width, height);
    callbackLooper_.OnInfo(INFO_TYPE_RESOLUTION_CHANGE, 0, format);
#endif
}

void HiPlayerImpl::NotifyPositionUpdate()
{
    int32_t currentPosMs = 0;
    GetCurrentTime(currentPosMs);
    MEDIA_LOG_D("NotifyPositionUpdate currentPosMs: %{public}d", currentPosMs);
    Format format;
    callbackLooper_.OnInfo(INFO_TYPE_POSITION_UPDATE, currentPosMs, format);
}

void HiPlayerImpl::NotifyUpdateTrackInfo()
{
    std::vector<Format> trackInfo;
    GetVideoTrackInfo(trackInfo);
    GetAudioTrackInfo(trackInfo);
    GetSubtitleTrackInfo(trackInfo);

    Format body;
    body.PutFormatVector(std::string(PlayerKeys::PLAYER_TRACK_INFO), trackInfo);
    MEDIA_LOG_I("NotifyUpdateTrackInfo");

    callbackLooper_.OnInfo(INFO_TYPE_TRACK_INFO_UPDATE, 0, body);
}

void HiPlayerImpl::NotifySuperResolutionChanged(const Event& event)
{
#ifdef SUPPORT_VIDEO
    MEDIA_LOG_D("NotifySuperResolutionChanged");
    int32_t enabled = AnyCast<bool>(event.param);

    Format format;
    format.PutIntValue(PlayerKeys::SUPER_RESOLUTION_ENABLED, static_cast<int32_t>(enabled));
    callbackLooper_.OnInfo(INFO_TYPE_SUPER_RESOLUTION_CHANGED, 0, format);
#endif
    return;
}

void HiPlayerImpl::HandleAudioTrackChangeEvent(const Event& event)
{
    int32_t trackId = AnyCast<int32_t>(event.param);
    std::vector<std::shared_ptr<Meta>> metaInfo = demuxer_->GetStreamMetaInfo();
    std::string mime;
    FALSE_RETURN_MSG(trackId >= 0 && trackId < static_cast<int32_t>(metaInfo.size()),
        "HandleAudioTrackChangeEvent trackId invalid");
    if (!(metaInfo[trackId]->GetData(Tag::MIME_TYPE, mime))) {
        MEDIA_LOG_E("HandleAudioTrackChangeEvent trackId " PUBLIC_LOG_D32 "get mime error", trackId);
        return;
    }
    if (IsAudioMime(mime)) {
        if (currentAudioTrackId_ < 0) {
            FALSE_RETURN(Status::OK == InitAudioDefaultTrackIndex());
        }
        if (Status::OK != audioDecoder_->ChangePlugin(metaInfo[trackId])) {
            MEDIA_LOG_E("HandleAudioTrackChangeEvent audioDecoder change plugin error");
            return;
        }
        // Firstly, clear obsolete data first to avoid cacophony of noise. Then start audio decoder and audio sink.
        audioDecoder_->DoFlush();
        audioSink_->DoFlush();
        audioDecoder_->Start();
        if (IsNeedAudioSinkChangeTrack(metaInfo, trackId)) {
            MEDIA_LOG_I("AudioSink changeTrack in");
            if (Status::OK != audioSink_->ChangeTrack(metaInfo[trackId])) {
                MEDIA_LOG_E("HandleAudioTrackChangeEvent audioSink change track error");
                return;
            }
        }
        if (Status::OK != demuxer_->StartTask(trackId)) {
            MEDIA_LOG_E("HandleAudioTrackChangeEvent StartTask error. trackId is " PUBLIC_LOG_D32, trackId);
            return;
        }
        Format audioTrackInfo {};
        audioTrackInfo.PutIntValue("track_index", static_cast<int32_t>(trackId));
        audioTrackInfo.PutIntValue("track_is_select", 1);
        callbackLooper_.OnInfo(INFO_TYPE_TRACKCHANGE, 0, audioTrackInfo);
        currentAudioTrackId_ = trackId;

        NotifyUpdateTrackInfo();
    }
    return;
}

void HiPlayerImpl::HandleVideoTrackChangeEvent(const Event& event)
{
#ifdef SUPPORT_VIDEO
    int32_t trackId = AnyCast<int32_t>(event.param);
    std::vector<std::shared_ptr<Meta>> metaInfo = demuxer_->GetStreamMetaInfo();
    std::string mime;
    FALSE_RETURN_MSG(trackId >= 0 && trackId < static_cast<int32_t>(metaInfo.size()),
        "HandleVideoTrackChangeEvent trackId invalid");
    if (!(metaInfo[trackId]->GetData(Tag::MIME_TYPE, mime))) {
        MEDIA_LOG_E("HandleVideoTrackChangeEvent trackId " PUBLIC_LOG_D32 "get mime error", trackId);
        return;
    }
    if (IsVideoMime(mime)) {
        if (Status::OK != demuxer_->StartTask(trackId)) {
            MEDIA_LOG_E("HandleVideoTrackChangeEvent StartTask error. trackId is " PUBLIC_LOG_D32, trackId);
            return;
        }
        Format videoTrackInfo {};
        videoTrackInfo.PutIntValue("track_index", static_cast<int32_t>(trackId));
        videoTrackInfo.PutIntValue("track_is_select", 1);
        callbackLooper_.OnInfo(INFO_TYPE_TRACKCHANGE, 0, videoTrackInfo);
        currentVideoTrackId_ = trackId;
    }
#endif
    return;
}

void HiPlayerImpl::HandleSubtitleTrackChangeEvent(const Event& event)
{
    int32_t trackId = AnyCast<int32_t>(event.param);
    std::vector<std::shared_ptr<Meta>> metaInfo = demuxer_->GetStreamMetaInfo();
    std::string mime;
    FALSE_RETURN_MSG(trackId >= 0 && trackId < static_cast<int32_t>(metaInfo.size()),
        "HandleSubtitleTrackChangeEvent trackId invalid");
    if (!(metaInfo[trackId]->GetData(Tag::MIME_TYPE, mime))) {
        MEDIA_LOG_E("HandleSubtitleTrackChangeEvent trackId " PUBLIC_LOG_D32 "get mime error", trackId);
        return;
    }
    if (IsSubtitleMime(mime)) {
        if (Status::OK != subtitleSink_->DoFlush()) {
            MEDIA_LOG_E("HandleSubtitleTrackChangeEvent DoFlush error");
            return;
        }
        if (Status::OK != demuxer_->StartTask(trackId)) {
            MEDIA_LOG_E("HandleSubtitleTrackChangeEvent StartTask error. trackId is " PUBLIC_LOG_D32, trackId);
            return;
        }
        Format subtitleTrackInfo {};
        subtitleTrackInfo.PutIntValue("track_index", static_cast<int32_t>(trackId));
        subtitleTrackInfo.PutIntValue("track_is_select", 1);
        callbackLooper_.OnInfo(INFO_TYPE_TRACKCHANGE, 0, subtitleTrackInfo);
        currentSubtitleTrackId_ = trackId;
        needUpdateSubtitle_.store(true);
    }
    return;
}

void __attribute__((no_sanitize("cfi"))) HiPlayerImpl::OnStateChanged(PlayerStateId state, bool isSystemOperation)
{
    {
        AutoLock lockEos(stateChangeMutex_);
        if (isDoCompletedSeek_.load()) {
            isDoCompletedSeek_ = false;
        } else if ((curState_ == PlayerStateId::EOS) && (state == PlayerStateId::PAUSE)) {
            MEDIA_LOG_E("already at completed and not allow pause");
            return;
        } else if ((curState_ == PlayerStateId::ERROR) && (state == PlayerStateId::READY)) {
            MEDIA_LOG_E("already at error and not allow ready");
            return;
        }
        curState_ = state;
    }
    MEDIA_LOG_D_SHORT("OnStateChanged " PUBLIC_LOG_D32 " > " PUBLIC_LOG_D32, pipelineStates_.load(),
            TransStateId2PlayerState(state));
    UpdateStateNoLock(TransStateId2PlayerState(state), true, isSystemOperation);
    {
        AutoLock lock(stateMutex_);
        cond_.NotifyOne();
    }
}

void HiPlayerImpl::HandleTimedMetaData(std::shared_ptr<OHOS::MediaAVCodec::AVTimedMetaData> meta)
{
    FALSE_RETURN_MSG(meta != nullptr, "HandleTimedMetaData: meta is nullptr");
    FALSE_RETURN_MSG(callbackLooper_.IsStarted(), "HandleTimedMetaData: callbackLooper is not started");
    Format format;
    (void)format.PutStringValue(std::string(PlaybackTimedMetaData::PLAYER_TIMED_META_ID), meta->id);
    (void)format.PutStringValue(std::string(PlaybackTimedMetaData::PLAYER_TIMED_META_CLASSIFY), meta->classify);
    (void)format.PutLongValue(std::string(PlaybackTimedMetaData::PLAYER_TIMED_META_START), meta->start);
    (void)format.PutLongValue(std::string(PlaybackTimedMetaData::PLAYER_TIMED_META_DURATION), meta->duration);

    // Write contents map directly as key-value pairs
    for (const auto &[key, val] : meta->contents) {
        (void)format.PutStringValue(key, val);
    }
    callbackLooper_.OnInfo(INFO_TYPE_TIMED_META_DATA, 0, format);
    MEDIA_LOG_I("sending timedMetaData event: id=%{public}s, classify=%{public}s, start=%{public}" PRId64
        ", duration=%{public}" PRId64 ", contentsSize=%{public}zu",
        meta->id.c_str(), meta->classify.c_str(), meta->start, meta->duration, meta->contents.size());
}

void HiPlayerImpl::HandleAdsChange(std::shared_ptr<MediaAVCodec::AVAdsChangeEvent> event)
{
    FALSE_RETURN_MSG(event != nullptr, "HandleAdsChange: event is nullptr");
    FALSE_RETURN_MSG(callbackLooper_.IsStarted(), "HandleAdsChange: callbackLooper is not started");
    if (event->type == ADS_STARTED) {
        isAdsPlaying_.store(true);
    } else if (event->type == ADS_COMPLETED || event->type == ADS_SKIPPED || event->type == ADS_ERROR) {
        isAdsPlaying_.store(false);
    }

    Format format;
    (void)format.PutIntValue(std::string(PlaybackAds::PLAYER_ADS_TYPE), static_cast<int32_t>(event->type));
    (void)format.PutStringValue(std::string(PlaybackAds::PLAYER_ADS_EVENT_ID), event->eventId);
    (void)format.PutLongValue(std::string(PlaybackAds::PLAYER_ADS_DURATION_MS), event->durationMs);
    (void)format.PutIntValue(std::string(PlaybackAds::PLAYER_ADS_ERROR_CODE),
        TransStatus(static_cast<Status>(event->errorCode)));
    (void)format.PutStringValue(std::string(PlaybackAds::PLAYER_ADS_ERROR_MESSAGE), event->errorMessage);

    callbackLooper_.OnInfo(INFO_TYPE_ADS_CHANGE, 0, format);
    MEDIA_LOG_I("adsChange: type=%{public}d, eventId=%{public}s", static_cast<int32_t>(event->type),
        event->eventId.c_str());
}

void HiPlayerImpl::HandleLoadingBitrateEvent(const AVMetricsEvent& infoCopy)
{
    int64_t bitrateBefore = AnyCast<int64_t>(infoCopy.details.at("bitrate_before"));
    int64_t bitrateAfter = AnyCast<int64_t>(infoCopy.details.at("bitrate_after"));
    MEDIA_LOG_I("HandleLoadingBitrateEvent timestamp: %{public}" PRId64 ", playbackPosition: %{public}" PRId64 \
        ", bitrateBefore: %{public}" PRId64 ", bitrateAfter: %{public}" PRId64,
        infoCopy.timeStamp, infoCopy.playbackPosition, bitrateBefore, bitrateAfter);
    if (callbackLooper_.IsStarted()) {
        Format format;
        format.PutIntValue(PlayerKeys::PLAYER_METRICS_EVENT_TYPE,
            static_cast<int32_t>(AV_METRICS_EVENT_TYPE_LOADINGRATE_CHANGE));
        format.PutLongValue(PlayerKeys::PLAYER_TIMESTAMP, infoCopy.timeStamp);
        format.PutLongValue(PlayerKeys::PLAYER_PLAYBACK_POSITION, infoCopy.playbackPosition);
        format.PutLongValue(PlayerKeys::PLAYER_LOADING_BITRATE_BEFORE, bitrateBefore);
        format.PutLongValue(PlayerKeys::PLAYER_LOADING_BITRATE_AFTER, bitrateAfter);
        callbackLooper_.OnInfo(INFO_TYPE_METRICS_EVENT, 0, format);
    }
}

void HiPlayerImpl::HandleLoadingErrorEvent(const AVMetricsEvent& info)
{
    std::string requestStage = info.details.count("request_stage") > 0 ?
        AnyCast<std::string>(info.details.at("request_stage")) : "";
    int64_t requestTimestamp = info.details.count("request_timestamp") > 0 ?
        AnyCast<int64_t>(info.details.at("request_timestamp")) : 0;
    int64_t errorCode = info.details.count("error_code") > 0 ?
        AnyCast<int64_t>(info.details.at("error_code")) : 0;
    MEDIA_LOG_I("HandleLoadingErrorEvent timestamp: %{public}" PRId64 ", playbackPosition: %{public}" PRId64 \
        ", requestStage: %{public}s, requestTimestamp: %{public}" PRId64 \
        ", errorCode: %{public}" PRId64,
        info.timeStamp, info.playbackPosition, requestStage.c_str(), requestTimestamp, errorCode);
    if (callbackLooper_.IsStarted()) {
        Format format;
        format.PutIntValue(PlayerKeys::PLAYER_METRICS_EVENT_TYPE,
            static_cast<int32_t>(AV_METRICS_EVENT_TYPE_LOADING_ERROR));
        format.PutLongValue(PlayerKeys::PLAYER_TIMESTAMP, info.timeStamp);
        format.PutLongValue(PlayerKeys::PLAYER_PLAYBACK_POSITION, info.playbackPosition);
        format.PutStringValue(PlayerKeys::PLAYER_REQUEST_STAGE, requestStage);
        format.PutLongValue(PlayerKeys::PLAYER_REQUEST_TIMESTAMP, requestTimestamp);
        format.PutLongValue(PlayerKeys::PLAYER_ERROR_CODE, errorCode);
        callbackLooper_.OnInfo(INFO_TYPE_METRICS_EVENT, 0, format);
    }
}

void HiPlayerImpl::FillMediaChangedInfo(Format& format, const AVMetricsEvent& info)
{
    CopyBoolDetail(info.details, PlayerKeys::PLAYER_IS_LOCAL_FD, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_MEDIA_STREAM_TYPE, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_CHANGE_REASON, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_CHANGE_RESULT, format);
    CopyIntDetail(info.details, PlayerKeys::PLAYER_STREAM_ID_BEFORE, format);
    CopyIntDetail(info.details, PlayerKeys::PLAYER_STREAM_ID_AFTER, format);
    CopyLongDetail(info.details, PlayerKeys::PLAYER_BITRATE_BEFORE, format);
    CopyLongDetail(info.details, PlayerKeys::PLAYER_BITRATE_AFTER, format);
    CopyIntDetail(info.details, PlayerKeys::PLAYER_VIDEO_WIDTH_BEFORE, format);
    CopyIntDetail(info.details, PlayerKeys::PLAYER_VIDEO_HEIGHT_BEFORE, format);
    CopyIntDetail(info.details, PlayerKeys::PLAYER_VIDEO_WIDTH_AFTER, format);
    CopyIntDetail(info.details, PlayerKeys::PLAYER_VIDEO_HEIGHT_AFTER, format);
    CopyIntDetail(info.details, PlayerKeys::PLAYER_VIDEO_FRAMERATE_BEFORE, format);
    CopyIntDetail(info.details, PlayerKeys::PLAYER_VIDEO_FRAMERATE_AFTER, format);
    CopyIntDetail(info.details, PlayerKeys::PLAYER_AUDIO_CHANNELS_BEFORE, format);
    CopyIntDetail(info.details, PlayerKeys::PLAYER_AUDIO_CHANNELS_AFTER, format);
    CopyIntDetail(info.details, PlayerKeys::PLAYER_AUDIO_SAMPLE_RATE_BEFORE, format);
    CopyIntDetail(info.details, PlayerKeys::PLAYER_AUDIO_SAMPLE_RATE_AFTER, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_VIDEO_TYPE_BEFORE, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_VIDEO_TYPE_AFTER, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_AUDIO_LANG_BEFORE, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_AUDIO_LANG_AFTER, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_SUBTITLE_LANG_BEFORE, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_SUBTITLE_LANG_AFTER, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_AUDIO_MIME_TYPE_BEFORE, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_AUDIO_MIME_TYPE_AFTER, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_VIDEO_MIME_TYPE_BEFORE, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_VIDEO_MIME_TYPE_AFTER, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_CODECS_BEFORE, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_CODECS_AFTER, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_ORIGIN_CODECS_BEFORE, format);
    CopyStringDetail(info.details, PlayerKeys::PLAYER_ORIGIN_CODECS_AFTER, format);
}

void HiPlayerImpl::HandleMediaChangedEvent(const AVMetricsEvent& info)
{
    MEDIA_LOG_I("HandleMediaChangedEvent timestamp: %{public}" PRId64 ", playbackPosition: %{public}" PRId64,
        info.timeStamp, info.playbackPosition);
    if (callbackLooper_.IsStarted()) {
        Format format;
        format.PutIntValue(PlayerKeys::PLAYER_METRICS_EVENT_TYPE,
            static_cast<int32_t>(AV_METRICS_EVENT_TYPE_CONTENT_CHANGED));
        format.PutLongValue(PlayerKeys::PLAYER_TIMESTAMP, info.timeStamp);
        format.PutLongValue(PlayerKeys::PLAYER_PLAYBACK_POSITION, info.playbackPosition);
        FillMediaChangedInfo(format, info);

        auto itChangeResult = info.details.find(std::string(PlayerKeys::PLAYER_CHANGE_RESULT));
        std::string changeResultStr = (itChangeResult != info.details.end()) ?
            AnyCast<std::string>(itChangeResult->second) : "";

        auto itAudioSampleRate = info.details.find(std::string(PlayerKeys::PLAYER_AUDIO_SAMPLE_RATE_AFTER));
        int32_t audioSampleRateAfter = (itAudioSampleRate != info.details.end()) ?
            static_cast<int32_t>(AnyCast<int64_t>(itAudioSampleRate->second)) : 0;

        FillAudioSampleRateFromDemuxer(changeResultStr, audioSampleRateAfter, format);
        callbackLooper_.OnInfo(INFO_TYPE_METRICS_EVENT, 0, format);
    }
}

void HiPlayerImpl::FillAudioSampleRateFromDemuxer(const std::string& changeResultStr,
    int32_t audioSampleRateAfter, Format& format)
{
    if (changeResultStr == "FAILED" || audioSampleRateAfter != 0 || demuxer_ == nullptr) {
        return;
    }
    std::vector<std::shared_ptr<Meta>> trackMetas = demuxer_->GetStreamMetaInfo();
    int32_t audioTrackId = demuxer_->GetCurrentAudioTrackId();
    if (audioTrackId < 0 || audioTrackId >= static_cast<int32_t>(trackMetas.size())) {
        return;
    }
    const auto& trackMeta = trackMetas[audioTrackId];
    if (trackMeta == nullptr) {
        return;
    }
    int32_t sampleRate = 0;
    if (trackMeta->GetData(Tag::AUDIO_SAMPLE_RATE, sampleRate) && sampleRate > 0) {
        format.PutIntValue(PlayerKeys::PLAYER_AUDIO_SAMPLE_RATE_AFTER, sampleRate);
    }
}

void HiPlayerImpl::HandleMediaDiscontinueEvent(const AVMetricsEvent& info)
{
    MEDIA_LOG_I("HandleMediaDiscontinueEvent timestamp: %{public}" PRId64 ", playbackPosition: %{public}" PRId64,
        info.timeStamp, info.playbackPosition);
    if (callbackLooper_.IsStarted()) {
        Format format;
        format.PutIntValue(PlayerKeys::PLAYER_METRICS_EVENT_TYPE,
            static_cast<int32_t>(AV_METRICS_EVENT_TYPE_CONTENT_DISCONTINUITY));
        format.PutLongValue(PlayerKeys::PLAYER_TIMESTAMP, info.timeStamp);
        format.PutLongValue(PlayerKeys::PLAYER_PLAYBACK_POSITION, info.playbackPosition);
        CopyStringDetail(info.details, PlayerKeys::PLAYER_MEDIA_STREAM_TYPE, format);
        CopyStringDetail(info.details, PlayerKeys::PLAYER_DISCONTINUE_TYPE, format);
        std::string discontinueTypeStr = AnyCast<std::string>(info.details.at("discontinue_type"));
        if (discontinueTypeStr == "PTS") {
            format.PutLongValue(PlayerKeys::PLAYER_PTS_BEFORE,
                AnyCast<int64_t>(info.details.at("pts_before")));
            format.PutLongValue(PlayerKeys::PLAYER_PTS_AFTER,
                AnyCast<int64_t>(info.details.at("pts_after")));
        } else if (discontinueTypeStr == "AUDIO_PARAM") {
            format.PutIntValue(PlayerKeys::PLAYER_SAMPLE_RATE_BEFORE,
                AnyCast<int32_t>(info.details.at("sample_rate_before")));
            format.PutIntValue(PlayerKeys::PLAYER_SAMPLE_RATE_AFTER,
                AnyCast<int32_t>(info.details.at("sample_rate_after")));
            format.PutIntValue(PlayerKeys::PLAYER_CHANNELS_BEFORE,
                AnyCast<int32_t>(info.details.at("channels_before")));
            format.PutIntValue(PlayerKeys::PLAYER_CHANNELS_AFTER,
                AnyCast<int32_t>(info.details.at("channels_after")));
            format.PutIntValue(PlayerKeys::PLAYER_SAMPLE_FORMAT_BEFORE,
                AnyCast<int32_t>(info.details.at("sample_format_before")));
            format.PutIntValue(PlayerKeys::PLAYER_SAMPLE_FORMAT_AFTER,
                AnyCast<int32_t>(info.details.at("sample_format_after")));
        }
        callbackLooper_.OnInfo(INFO_TYPE_METRICS_EVENT, 0, format);
    }
}

void HiPlayerImpl::HandleAudioStatusEvent(const AVMetricsEvent& info)
{
    std::string stateBefore = info.details.count("state_before") > 0 ?
        AnyCast<std::string>(info.details.at("state_before")) : "UNKNOWN";
    std::string stateAfter = info.details.count("state_after") > 0 ?
        AnyCast<std::string>(info.details.at("state_after")) : "UNKNOWN";
    int32_t interruptHint = info.details.count("interrupt_hint") > 0 ?
        AnyCast<int32_t>(info.details.at("interrupt_hint")) : 0;
    MEDIA_LOG_I("HandleAudioStatusEvent timestamp: %{public}" PRId64 ", playbackPosition: %{public}" PRId64 \
        ", stateBefore: %{public}s, stateAfter: %{public}s, interruptHint: %{public}d",
        info.timeStamp, info.playbackPosition, stateBefore.c_str(), stateAfter.c_str(), interruptHint);
    if (callbackLooper_.IsStarted()) {
        Format format;
        format.PutIntValue(PlayerKeys::PLAYER_METRICS_EVENT_TYPE,
            static_cast<int32_t>(AV_METRICS_EVENT_TYPE_AUDIO_ABNORMAL));
        format.PutLongValue(PlayerKeys::PLAYER_TIMESTAMP, info.timeStamp);
        format.PutLongValue(PlayerKeys::PLAYER_PLAYBACK_POSITION, info.playbackPosition);
        format.PutStringValue(PlayerKeys::PLAYER_AUDIO_STATE_BEFORE, stateBefore);
        format.PutStringValue(PlayerKeys::PLAYER_AUDIO_STATE_AFTER, stateAfter);
        format.PutIntValue(PlayerKeys::PLAYER_AUDIO_INTERRUPT_HINT, interruptHint);
        callbackLooper_.OnInfo(INFO_TYPE_METRICS_EVENT, 0, format);
    }
}

void HiPlayerImpl::HandleCodecAbnormalEvent(const AVMetricsEvent& info)
{
    std::string decoderType = info.details.count("decoder_type") > 0 ?
        AnyCast<std::string>(info.details.at("decoder_type")) : "";
    int64_t errorCode = info.details.count("error_code") > 0 ?
        AnyCast<int64_t>(info.details.at("error_code")) : 0;
    MEDIA_LOG_I("HandleCodecAbnormalEvent timestamp: %{public}" PRId64 ", playbackPosition: %{public}" PRId64 \
        ", decoderType: %{public}s, errorCode: %{public}" PRId64,
        info.timeStamp, info.playbackPosition, decoderType.c_str(), errorCode);
    if (callbackLooper_.IsStarted()) {
        Format format;
        format.PutIntValue(PlayerKeys::PLAYER_METRICS_EVENT_TYPE,
            static_cast<int32_t>(AV_METRICS_EVENT_TYPE_CODEC_ABNORMAL));
        format.PutLongValue(PlayerKeys::PLAYER_TIMESTAMP, info.timeStamp);
        format.PutLongValue(PlayerKeys::PLAYER_PLAYBACK_POSITION, info.playbackPosition);
        format.PutStringValue(PlayerKeys::PLAYER_DECODER_TYPE, decoderType);
        format.PutLongValue(PlayerKeys::PLAYER_CODEC_ERROR_CODE, errorCode);
        callbackLooper_.OnInfo(INFO_TYPE_METRICS_EVENT, 0, format);
    }
}

void HiPlayerImpl::HandleLipAsyncEvent(const AVMetricsEvent& info)
{
    std::string asyncType = info.details.count("async_type") > 0 ?
        AnyCast<std::string>(info.details.at("async_type")) : "";
    int64_t startTime = info.details.count("start_time") > 0 ?
        AnyCast<int64_t>(info.details.at("start_time")) : 0;
    int64_t endTime = info.details.count("end_time") > 0 ?
        AnyCast<int64_t>(info.details.at("end_time")) : 0;
    MEDIA_LOG_I("HandleLipAsyncEvent timestamp: %{public}" PRId64 ", playbackPosition: %{public}" PRId64 \
        ", asyncType: %{public}s, startTime: %{public}" PRId64 ", endTime: %{public}" PRId64,
        info.timeStamp, info.playbackPosition, asyncType.c_str(), startTime, endTime);
    if (callbackLooper_.IsStarted()) {
        Format format;
        format.PutIntValue(PlayerKeys::PLAYER_METRICS_EVENT_TYPE,
            static_cast<int32_t>(AV_METRICS_EVENT_TYPE_LIP_ASYNC));
        format.PutLongValue(PlayerKeys::PLAYER_TIMESTAMP, info.timeStamp);
        format.PutLongValue(PlayerKeys::PLAYER_PLAYBACK_POSITION, info.playbackPosition);
        format.PutStringValue(PlayerKeys::PLAYER_ASYNC_TYPE, asyncType);
        format.PutLongValue(PlayerKeys::PLAYER_START_TIME, startTime);
        format.PutLongValue(PlayerKeys::PLAYER_END_TIME, endTime);
        callbackLooper_.OnInfo(INFO_TYPE_METRICS_EVENT, 0, format);
    }
}

Status HiPlayerImpl::OnCallback(std::shared_ptr<Filter> filter, const FilterCallBackCommand cmd,
    OHOS::Media::Pipeline::StreamType outType)
{
    MEDIA_LOG_D_SHORT("HiPlayerImpl::OnCallback filter, outType: %{public}d", outType);
    if (cmd == FilterCallBackCommand::NEXT_FILTER_NEEDED) {
        switch (outType) {
            case OHOS::Media::Pipeline::StreamType::STREAMTYPE_SUBTITLE:
                return LinkSubtitleSinkFilter(filter, outType);
            case OHOS::Media::Pipeline::StreamType::STREAMTYPE_RAW_AUDIO:
                return LinkAudioSinkFilter(filter, outType);
            case OHOS::Media::Pipeline::StreamType::STREAMTYPE_DOLBY:
                return LinkAudioSinkFilter(filter, outType);
            case OHOS::Media::Pipeline::StreamType::STREAMTYPE_ENCODED_AUDIO:
                return LinkAudioDecoderFilter(filter, outType);
#ifdef SUPPORT_VIDEO
            case OHOS::Media::Pipeline::StreamType::STREAMTYPE_RAW_VIDEO:
                break;
            case OHOS::Media::Pipeline::StreamType::STREAMTYPE_ENCODED_VIDEO:
                return LinkVideoDecoderFilter(filter, outType);
#endif
            default:
                break;
        }
    }
    return Status::OK;
}

void HiPlayerImpl::OnDumpInfo(int32_t fd)
{
    MEDIA_LOG_D("HiPlayerImpl::OnDumpInfo called.");
    if (audioDecoder_ != nullptr) {
        audioDecoder_->OnDumpInfo(fd);
    }
    if (demuxer_ != nullptr) {
        demuxer_->OnDumpInfo(fd);
    }
#ifdef SUPPORT_VIDEO
    if (videoDecoder_ != nullptr) {
        videoDecoder_->OnDumpInfo(fd);
    }
#endif
}

Status HiPlayerImpl::LinkAudioDecoderFilter(const std::shared_ptr<Filter>& preFilter,
    OHOS::Media::Pipeline::StreamType type)
{
    MediaTrace trace("HiPlayerImpl::LinkAudioDecoderFilter");
    MEDIA_LOG_I_SHORT("HiPlayerImpl::LinkAudioDecoderFilter");
    FALSE_RETURN_V(audioDecoder_ == nullptr, Status::OK);

    audioDecoder_ = FilterFactory::Instance().CreateFilter<AudioDecoderFilter>("player.audiodecoder",
        FilterType::FILTERTYPE_ADEC);
    FALSE_RETURN_V(audioDecoder_ != nullptr, Status::ERROR_NULL_POINTER);
    FALSE_GOON_NOEXEC(demuxer_, audioDecoder_->UpdateIsAsyncMode(demuxer_->IsAudioDemuxDecodeAsync()));
    interruptMonitor_->RegisterListener(audioDecoder_);
    audioDecoder_->Init(playerEventReceiver_, playerFilterCallback_);

    audioDecoder_->SetCallerInfo(instanceId_, bundleName_);
    audioDecoder_->SetDumpFlag(isDump_);
    // set decrypt config for drm audios
    if (isDrmProtected_) {
        MEDIA_LOG_D("HiPlayerImpl::LinkAudioDecoderFilter will SetDecryptConfig");
        std::unique_lock<std::mutex> lock(drmMutex_);
        static constexpr int32_t timeout = 5;
        bool notTimeout = drmConfigCond_.wait_for(lock, std::chrono::seconds(timeout), [this]() {
            return this->isDrmPrepared_ || this->stopWaitingDrmConfig_;
        });
        if (notTimeout && isDrmPrepared_) {
            MEDIA_LOG_I("LinkAudioDecoderFilter will SetDecryptConfig");
#ifdef SUPPORT_AVPLAYER_DRM
            bool svpFlag = svpMode_ == HiplayerSvpMode::SVP_TRUE ? true : false;
            audioDecoder_->SetDecryptionConfig(keySessionServiceProxy_, svpFlag);
#endif
        } else {
            MEDIA_LOG_E("HiPlayerImpl Drmcond wait timeout or has been stopped! Play drm protected audio failed!");
            return Status::ERROR_INVALID_OPERATION;
        }
    } else {
        MEDIA_LOG_D("HiPlayerImpl::LinkAudioDecoderFilter, and it's not drm-protected.");
    }
#ifdef SUPPORT_START_STOP_ON_DEMAND
    return pipeline_->LinkFilters(preFilter, {audioDecoder_}, type, true);
#else
    return pipeline_->LinkFilters(preFilter, {audioDecoder_}, type, isOnlyAudio_ || bundleName_ == "bootanimation");
#endif
}

Status HiPlayerImpl::LinkAudioSinkFilter(const std::shared_ptr<Filter>& preFilter,
    OHOS::Media::Pipeline::StreamType type)
{
    MediaTrace trace("HiPlayerImpl::LinkAudioSinkFilter");
    MEDIA_LOG_I("HiPlayerImpl::LinkAudioSinkFilter");
    FALSE_RETURN_V(audioSink_ == nullptr, Status::OK);

    audioSink_ = FilterFactory::Instance().CreateFilter<AudioSinkFilter>("player.audiosink",
        FilterType::FILTERTYPE_ASINK);
    FALSE_RETURN_V(audioSink_ != nullptr, Status::ERROR_NULL_POINTER);
    FALSE_GOON_NOEXEC(demuxer_, audioSink_->SetIsAudioDemuxDecodeAsync(demuxer_->IsAudioDemuxDecodeAsync()));
    audioSink_->Init(playerEventReceiver_, playerFilterCallback_, interruptMonitor_);
    audioSink_->SetMaxAmplitudeCbStatus(maxAmplitudeCbStatus_);
    audioSink_->SetPerfRecEnabled(isPerfRecEnabled_);
    audioSink_->SetIsCalledBySystemApp(isCalledBySystemApp_);
    if (type == OHOS::Media::Pipeline::StreamType::STREAMTYPE_DOLBY) {
        audioSink_->SetAudioPassFlag(true);
    }
    if (demuxer_ != nullptr && audioRenderInfo_ == nullptr) {
        std::vector<std::shared_ptr<Meta>> trackInfos = demuxer_->GetStreamMetaInfo();
        SetDefaultAudioRenderInfo(trackInfos);
    }
    SetAudioRendererParameter();
    SetPrivacyType(audioPrivacyType_);
    audioSink_->SetSyncCenter(syncManager_);
    InitPcmCallback();

    completeState_.emplace_back(std::make_pair("AudioSink", false));
    initialAVStates_.emplace_back(std::make_pair(EventType::EVENT_AUDIO_FIRST_FRAME, false));
#ifdef SUPPORT_START_STOP_ON_DEMAND
    auto res = pipeline_->LinkFilters(preFilter, {audioSink_}, type, true);
#else
    auto res = pipeline_->LinkFilters(preFilter, {audioSink_}, type, isOnlyAudio_ || bundleName_ == "bootanimation");
#endif
    if (mutedMediaType_ == OHOS::Media::MediaType::MEDIA_TYPE_AUD) {
        audioSink_->SetMuted(true);
    }
    return res;
}

void HiPlayerImpl::SetAudioRendererParameter()
{
    if (audioRenderInfo_ != nullptr) {
        audioSink_->SetParameter(audioRenderInfo_);
    }
    if (audioInterruptMode_ != nullptr) {
        audioSink_->SetParameter(audioInterruptMode_);
    }
    SetVolumeMode(volumeMode_);
    std::shared_ptr<Meta> globalMeta = std::make_shared<Meta>();
    if (demuxer_ != nullptr) {
        globalMeta = demuxer_->GetGlobalMetaInfo();
    }
    if (globalMeta != nullptr) {
        globalMeta->SetData(Tag::APP_PID, appPid_);
        globalMeta->SetData(Tag::APP_UID, appUid_);
        if (audioRenderInfo_ != nullptr) {
            for (MapIt iter = audioRenderInfo_->begin(); iter != audioRenderInfo_->end(); iter++) {
                globalMeta->SetData(iter->first, iter->second);
            }
        }
        if (audioInterruptMode_ != nullptr) {
            for (MapIt iter = audioInterruptMode_->begin(); iter != audioInterruptMode_->end(); iter++) {
                globalMeta->SetData(iter->first, iter->second);
            }
        }
        audioSink_->SetParameter(globalMeta);
    }
}

bool HiPlayerImpl::IsLiveStream()
{
    FALSE_RETURN_V_NOLOG(demuxer_ != nullptr, false);
    auto globalMeta = demuxer_->GetGlobalMetaInfo();
    FALSE_RETURN_V_NOLOG(globalMeta != nullptr, false);
    return globalMeta->Find(Tag::MEDIA_DURATION) == globalMeta->end();
}

#ifdef SUPPORT_VIDEO
Status HiPlayerImpl::LinkSeiDecoder(const std::shared_ptr<Filter>& preFilter,
    OHOS::Media::Pipeline::StreamType type)
{
    MEDIA_LOG_I("Link SeiParserFilterFilter Enter.");
    if (seiDecoder_ == nullptr) {
        seiDecoder_ = FilterFactory::Instance().CreateFilter<SeiParserFilter>("player.sei", FilterType::FILTERTYPE_SEI);
        FALSE_RETURN_V(seiDecoder_ != nullptr, Status::ERROR_NULL_POINTER);
        seiDecoder_->Init(playerEventReceiver_, playerFilterCallback_);
        seiDecoder_->SetSeiMessageCbStatus(seiMessageCbStatus_, payloadTypes_);
        seiDecoder_->SetSyncCenter(syncManager_);
        interruptMonitor_->RegisterListener(seiDecoder_);
    }
    return pipeline_->LinkFilters(preFilter, {seiDecoder_}, type);
}

Status HiPlayerImpl::LinkVideoDecoderFilter(const std::shared_ptr<Filter>& preFilter,
    OHOS::Media::Pipeline::StreamType type)
{
    MediaTrace trace("HiPlayerImpl::LinkVideoDecoderFilter");
    MEDIA_LOG_I("LinkVideoDecoderFilter");
    if (surface_ == nullptr && seiMessageCbStatus_ && IsLiveStream()) {
        return LinkSeiDecoder(preFilter, type);
    }
    if (videoDecoder_ == nullptr) {
        Status ret = InitVideoDecoder();
        FALSE_RETURN_V_NOLOG(ret == Status::OK, ret);
    }
    completeState_.emplace_back(std::make_pair("VideoSink", false));
    initialAVStates_.emplace_back(std::make_pair(EventType::EVENT_VIDEO_RENDERING_START, false));
    bool needInit = isForceLoadVideo_ || (surface_ != nullptr && !isVideoMuted_
            && mutedMediaType_ != OHOS::Media::MediaType::MEDIA_TYPE_VID);
    if (!needInit) {
        videoDecoder_->SetMediaMuted(true, false);
    }
    isVideoDecoderInited_ = needInit;
#ifdef SUPPORT_START_STOP_ON_DEMAND
    return pipeline_->LinkFilters(preFilter, {videoDecoder_}, type, true, needInit);
#else
    return pipeline_->LinkFilters(preFilter, {videoDecoder_}, type, bundleName_ == "bootanimation", needInit);
#endif
}
#endif

Status HiPlayerImpl::LinkSubtitleSinkFilter(const std::shared_ptr<Filter>& preFilter,
    OHOS::Media::Pipeline::StreamType type)
{
    MediaTrace trace("HiPlayerImpl::LinkSubtitleSinkFilter");
    FALSE_RETURN_V(subtitleSink_ == nullptr, Status::OK);
    subtitleSink_ = FilterFactory::Instance().CreateFilter<SubtitleSinkFilter>("player.subtitlesink",
        FilterType::FILTERTYPE_SSINK);
    FALSE_RETURN_V(subtitleSink_ != nullptr, Status::ERROR_NULL_POINTER);
    subtitleSink_->Init(playerEventReceiver_, playerFilterCallback_, interruptMonitor_);
    std::shared_ptr<Meta> globalMeta = std::make_shared<Meta>();
    if (demuxer_ != nullptr) {
        globalMeta = demuxer_->GetGlobalMetaInfo();
    }
    if (globalMeta != nullptr) {
        subtitleSink_->SetParameter(globalMeta);
    }
    subtitleSink_->SetSyncCenter(syncManager_);
    return pipeline_->LinkFilters(preFilter, {subtitleSink_}, type);
}

int32_t HiPlayerImpl::SetMediaMuted(OHOS::Media::MediaType mediaType, bool isMuted)
{
    MEDIA_LOG_D("SetMediaMuted %{public}d %{public}d", static_cast<int32_t>(mediaType), isMuted);
    if (mediaType == OHOS::Media::MediaType::MEDIA_TYPE_AUD) {
        FALSE_RETURN_V(audioSink_ != nullptr, MSERR_NO_MEMORY);
        auto res = audioSink_->SetMuted(isMuted);
        return res == Status::OK ? MSERR_OK : MSERR_INVALID_OPERATION;
    } else if (mediaType == OHOS::Media::MediaType::MEDIA_TYPE_VID) {
        if (demuxer_ != nullptr) {
            demuxer_->SetMediaMuted(mediaType, isMuted);
        }
        if (videoDecoder_ != nullptr) {
            videoDecoder_->SetMediaMuted(isMuted, true);
        }
        bool needReinit = !isMuted && surface_ != nullptr && (isVideoMuted_ != isMuted ||
            (!isVideoDecoderInited_ && mutedMediaType_ == OHOS::Media::MediaType::MEDIA_TYPE_VID));
        isVideoMuted_ = isMuted;
        FALSE_RETURN_V_NOLOG(needReinit, MSERR_OK);
        MEDIA_LOG_I("HiPlayerImpl::SetMediaMuted init video decoder");
        FALSE_RETURN_V_NOLOG(videoDecoder_ != nullptr, MSERR_OK);
        isReInitPostProcessor_ = true;
        videoDecoder_->ReInitAndStart();
        isVideoDecoderInited_ = true;
        return MSERR_OK;
    }
    return MSERR_INVALID_VAL;
}

int32_t HiPlayerImpl::SetPlaybackStrategy(AVPlayStrategy playbackStrategy)
{
    mutedMediaType_ = playbackStrategy.mutedMediaType;
    preferedWidth_ = playbackStrategy.preferredWidth;
    preferedHeight_ = playbackStrategy.preferredHeight;
    bufferDuration_ = playbackStrategy.preferredBufferDuration;
    preferHDR_ = playbackStrategy.preferredHdr;
    renderFirstFrame_ = playbackStrategy.showFirstFrameOnPrepare;
    audioLanguage_ = playbackStrategy.preferredAudioLanguage;
    subtitleLanguage_ = playbackStrategy.preferredSubtitleLanguage;
    videoPostProcessorType_ = playbackStrategy.enableSuperResolution ? VideoPostProcessorType::SUPER_RESOLUTION
                                : VideoPostProcessorType::NONE;
    enableCameraPostprocessing_ = playbackStrategy.enableCameraPostprocessing;
    isPostProcessorOn_ = playbackStrategy.enableSuperResolution;
    keepDecodingOnMute_ = playbackStrategy.keepDecodingOnMute;

    SetFlvLiveParams(playbackStrategy);
    FALSE_RETURN_V(IsLivingMaxDelayTimeValid(), TransStatus(Status::ERROR_INVALID_PARAMETER));
    return MSERR_OK;
}

int32_t HiPlayerImpl::SetTrackSelectionFilter(AVPlayTrackSelectionFilter avTrackFilter)
{
    MEDIA_LOG_I("SetTrackSelectionFilter");
    trackSelectionFilter_ = avTrackFilter;
    hasTrackSelectionFilter_.store(true);
    FALSE_RETURN_V_MSG_W(demuxer_ != nullptr, MSERR_OK, "demuxer_ is nullptr");
    TrackSelectionFilter trackFilter;
    trackFilter.maxVideoBitrate = avTrackFilter.maxVideoBitrate;
    trackFilter.minVideoBitrate = avTrackFilter.minVideoBitrate;
    trackFilter.maxVideoFrameRate = avTrackFilter.maxVideoFrameRate;
    trackFilter.minVideoFrameRate = avTrackFilter.minVideoFrameRate;
    trackFilter.maxVideoResolution = avTrackFilter.maxVideoResolution;
    trackFilter.minVideoResolution = avTrackFilter.minVideoResolution;
    trackFilter.preferredVideoMimeTypes = avTrackFilter.preferredVideoMimeTypes;
    trackFilter.maxAudioBitrate = avTrackFilter.maxAudioBitrate;
    trackFilter.minAudioBitrate = avTrackFilter.minAudioBitrate;
    trackFilter.maxAudioChannels = avTrackFilter.maxAudioChannels;
    trackFilter.preferredAudioMimeTypes = avTrackFilter.preferredAudioMimeTypes;
    trackFilter.preferredAudioLanguages = avTrackFilter.preferredAudioLanguages;
    trackFilter.preferredSubtitleLanguages = avTrackFilter.preferredSubtitleLanguages;
    demuxer_->SetTrackSelectionFilter(trackFilter);
    return MSERR_OK;
}

int32_t HiPlayerImpl::SetSuperResolution(bool enabled)
{
    FALSE_RETURN_V(videoPostProcessorType_ == VideoPostProcessorType::SUPER_RESOLUTION,
        MSERR_SUPER_RESOLUTION_NOT_ENABLED);
    isPostProcessorOn_ = enabled;
    FALSE_RETURN_V_NOLOG(videoDecoder_ != nullptr, MSERR_OK);
    isReInitPostProcessor_ = false;
    auto ret = videoDecoder_->SetPostProcessorOn(enabled);
    return ret == Status::ERROR_UNSUPPORTED_FORMAT ? MSERR_SUPER_RESOLUTION_UNSUPPORTED : TransStatus(ret);
}

int32_t HiPlayerImpl::SetVideoWindowSize(int32_t width, int32_t height)
{
    FALSE_RETURN_V(videoPostProcessorType_ == VideoPostProcessorType::SUPER_RESOLUTION,
        MSERR_SUPER_RESOLUTION_NOT_ENABLED);
    FALSE_RETURN_V(width >= MIN_TARGET_WIDTH && width <= MAX_TARGET_WIDTH &&
        height >= MIN_TARGET_HEIGHT && height <= MAX_TARGET_HEIGHT,
        TransStatus(Status::ERROR_INVALID_PARAMETER));
    postProcessorTargetWidth_ = width;
    postProcessorTargetHeight_ = height;
    FALSE_RETURN_V_NOLOG(videoDecoder_ != nullptr, MSERR_OK);
    auto ret = videoDecoder_->SetVideoWindowSize(width, height);
    return ret == Status::ERROR_UNSUPPORTED_FORMAT ? MSERR_SUPER_RESOLUTION_UNSUPPORTED : TransStatus(ret);
}

int32_t HiPlayerImpl::SeekContinous(int64_t mSeconds, int64_t seekContinousBatchNo)
{
    std::lock_guard<std::mutex> lock(seekContinousMutex_);
    FALSE_RETURN_V(demuxer_ && videoDecoder_, TransStatus(Status::OK));
    FALSE_RETURN_V(!isNetWorkPlay_, TransStatus(Status::OK));
    FALSE_RETURN_V(seekContinousBatchNo_.load() <= seekContinousBatchNo, TransStatus(Status::OK));
    lastSeekContinousPos_ = mSeconds;
    if (seekContinousBatchNo_.load() == seekContinousBatchNo) {
        FALSE_RETURN_V(draggingPlayerAgent_ != nullptr, TransStatus(Status::OK));
        draggingPlayerAgent_->UpdateSeekPos(mSeconds);
        MEDIA_LOG_I("HiPlayerImpl::SeekContinous in " PUBLIC_LOG_D64, mSeconds);
        return TransStatus(Status::OK);
    }
    seekContinousBatchNo_.store(seekContinousBatchNo);
    auto res = StartSeekContinous();
    FALSE_RETURN_V_MSG_E(res == Status::OK && draggingPlayerAgent_ != nullptr, TransStatus(res),
        "StartSeekContinous failed");
    draggingPlayerAgent_->UpdateSeekPos(mSeconds);
    MEDIA_LOG_I("HiPlayerImpl::SeekContinous start " PUBLIC_LOG_D64, mSeconds);
    return TransStatus(Status::OK);
}

Status HiPlayerImpl::StartSeekContinous()
{
    if (curState_ == PlayerStateId::PLAYING) {
        // pause inner when start seek continuous in playing state
        Status res = pipeline_->Pause();
        if (res != Status::OK) {
            UpdateStateNoLock(PlayerStates::PLAYER_STATE_ERROR);
        }
        syncManager_->Pause();
        callbackLooper_.StopReportMediaProgress();
        callbackLooper_.StopCollectMaxAmplitude();
    }
    FALSE_RETURN_V(!draggingPlayerAgent_, Status::OK);
    FALSE_RETURN_V(demuxer_ && videoDecoder_, Status::OK);
    videoDecoder_->DoFlush();
    draggingPlayerAgent_ = DraggingPlayerAgent::Create(pipeline_, demuxer_, videoDecoder_, playerId_);
    FALSE_RETURN_V_MSG_E(draggingPlayerAgent_ != nullptr, Status::ERROR_INVALID_OPERATION, "failed to create agent");
    Status res = draggingPlayerAgent_->Init();
    if (res != Status::OK) {
        draggingPlayerAgent_ = nullptr;
        return res;
    }
    if (draggingPlayerAgent_->GetDraggingMode() == DraggingMode::DRAGGING_CONTINUOUS) {
        FlushVideoEOS();
        // Drive the head node to start the video channel.
        res = demuxer_->ResumeDragging();
        FALSE_LOG_MSG(res == Status::OK, "ResumeDragging failed");
    } else {
        callbackLooper_.OnError(PlayerErrorType::PLAY_ERR, MSERR_SEEK_CONTINUOUS_UNSUPPORTED, "");
    }
    SetFrameRateForSeekPerformance(FRAME_RATE_FOR_SEEK_PERFORMANCE);
    return res;
}

void HiPlayerImpl::FlushVideoEOS()
{
    AutoLock lock(handleCompleteMutex_);
    bool demuxerEOS = demuxer_->HasEosTrack();
    bool decoderEOS = false;
    for (std::pair<std::string, bool>& item: completeState_) {
        if (item.second) {
            decoderEOS = true;
            break;
        }
    }
    bool playerEOS = pipelineStates_ == PlayerStates::PLAYER_PLAYBACK_COMPLETE;
    if (demuxerEOS || decoderEOS || playerEOS) {
        MEDIA_LOG_I("flush first when eos");
        pipeline_->Flush();
        if (curState_ == PlayerStateId::PLAYING) {
            inEosPlayingSeekContinuous_ = true;
        }
        curState_ = PlayerStateId::PAUSE;
        pipelineStates_ = TransStateId2PlayerState(PlayerStateId::PAUSE);
        for (std::pair<std::string, bool>& item: completeState_) {
            item.second = false;
        }
    }
}

int32_t HiPlayerImpl::ExitSeekContinous(bool align, int64_t seekContinousBatchNo)
{
    std::lock_guard<std::mutex> lock(seekContinousMutex_);
    FALSE_RETURN_V(demuxer_ && videoDecoder_, TransStatus(Status::OK));
    FALSE_RETURN_V(!isNetWorkPlay_, TransStatus(Status::OK));
    seekContinousBatchNo_.store(seekContinousBatchNo);
    FALSE_RETURN_V(draggingPlayerAgent_ != nullptr, TransStatus(Status::OK));
    draggingPlayerAgent_->Release();
    draggingPlayerAgent_ = nullptr;
    SetFrameRateForSeekPerformance(FRAME_RATE_DEFAULT);
    int64_t seekTimeUs = 0;
    FALSE_RETURN_V_MSG_E(Plugins::Us2HstTime(lastSeekContinousPos_, seekTimeUs),
        TransStatus(Status::OK), "Invalid lastSeekContinousPos_: %{public}" PRId64, lastSeekContinousPos_);
    syncManager_->Seek(seekTimeUs, true);
    if (videoDecoder_ != nullptr) {
        videoDecoder_->SetSeekTime(seekTimeUs, PlayerSeekMode::SEEK_CONTINOUS);
    }
    FALSE_RETURN_V_MSG_E(align, TransStatus(Status::OK), "dont need align");
    if (align && audioDecoder_ != nullptr && audioSink_ != nullptr) {
        audioDecoder_->DoFlush();
        audioSink_->DoFlush();
        seekAgent_ = std::make_shared<SeekAgent>(demuxer_);
        interruptMonitor_->RegisterListener(seekAgent_);
        auto res = seekAgent_->AlignAudioPosition(lastSeekContinousPos_);
        FALSE_LOG_MSG(res == Status::OK, "AlignAudioPosition failed");
        MEDIA_LOG_I_SHORT("seekAgent_ AlignAudioPosition end");
        interruptMonitor_->DeregisterListener(seekAgent_);
        seekAgent_.reset();
    }
    if (inEosPlayingSeekContinuous_) {
        curState_ = PlayerStateId::PLAYING;
        pipelineStates_ = TransStateId2PlayerState(PlayerStateId::PLAYING);
        inEosPlayingSeekContinuous_ = false;
    }
    if (curState_ == PlayerStateId::PLAYING) {
        // resume inner when exit seek continuous in playing state
        callbackLooper_.StartReportMediaProgress(REPORT_PROGRESS_INTERVAL);
        callbackLooper_.StartCollectMaxAmplitude(SAMPLE_AMPLITUDE_INTERVAL);
        syncManager_->Resume();
        Status res = pipeline_->Resume();
        if (res != Status::OK) {
            UpdateStateNoLock(PlayerStates::PLAYER_STATE_ERROR);
        }
    }
    return TransStatus(Status::OK);
}

void HiPlayerImpl::HandleDfxEvent(const DfxEvent &event)
{
    if (event.type == DfxEventType::DFX_EVENT_NEW_TRACK_RENDER_START) {
        if (Any::IsSameTypeWith<uint64_t>(event.param)) {
            uint64_t renderSeqNum = AnyCast<uint64_t>(event.param);
            if (demuxer_ != nullptr) {
                demuxer_->OnNewTrackRender(renderSeqNum);
            }
        }
        return;
    }
    FALSE_RETURN(dfxAgent_ != nullptr);
    dfxAgent_->OnDfxEvent(event);
}

int32_t HiPlayerImpl::SetMaxAmplitudeCbStatus(bool status)
{
    maxAmplitudeCbStatus_ = status;
    callbackLooper_.SetMaxAmplitudeCbStatus(status);
    if (audioSink_ != nullptr) {
        return audioSink_->SetMaxAmplitudeCbStatus(maxAmplitudeCbStatus_);
    }
    return MSERR_OK;
}

int32_t HiPlayerImpl::IsSeekContinuousSupported(bool &isSeekContinuousSupported)
{
    FALSE_RETURN_V_MSG_E(demuxer_ != nullptr && videoDecoder_ != nullptr, TransStatus(Status::ERROR_WRONG_STATE),
        "demuxer or decoder is null");
    FALSE_RETURN_V_MSG_E(pipelineStates_ != PlayerStates::PLAYER_STOPPED, TransStatus(Status::ERROR_WRONG_STATE),
        "call IsSeekContinuousSupported in stopped state");
    isSeekContinuousSupported = DraggingPlayerAgent::IsDraggingSupported(demuxer_, videoDecoder_);
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetSeiMessageCbStatus(bool status, const std::vector<int32_t> &payloadTypes)
{
    seiMessageCbStatus_ = status;
    payloadTypes_ = payloadTypes;
    MEDIA_LOG_I("SetSeiMessageCbStatus seiMessageCbStatus_  = " PUBLIC_LOG_D32, seiMessageCbStatus_);
    Status ret = SetSeiMessageListener();
    return TransStatus(ret);
}

Status HiPlayerImpl::SetSeiMessageListener()
{
    if (videoDecoder_ != nullptr && surface_ != nullptr) {
        return videoDecoder_->SetSeiMessageCbStatus(seiMessageCbStatus_, payloadTypes_);
    }
    if (seiDecoder_ != nullptr && surface_ == nullptr) {
        return seiDecoder_->SetSeiMessageCbStatus(seiMessageCbStatus_, payloadTypes_);
    }
    return Status::OK;
}

void HiPlayerImpl::SetPerfRecEnabled(bool isPerfRecEnabled)
{
    MEDIA_LOG_I("SetPerfRecEnabled %{public}d", isPerfRecEnabled);
    isPerfRecEnabled_ = isPerfRecEnabled;
}

int32_t HiPlayerImpl::EnableReportMediaProgress(bool enable)
{
    MEDIA_LOG_I("EnableReportMediaProgress %{public}d", enable);
    callbackLooper_.EnableReportMediaProgress(enable);
    return MSERR_OK;
}

bool HiPlayerImpl::IsNeedChangePlaySpeed(PlaybackRateMode &mode, bool &isXSpeedPlay)
{
    FALSE_RETURN_V(demuxer_ != nullptr && isFlvLive_, false);
    FALSE_RETURN_V(!isLiveSeek_, false);
    uint64_t cacheDuration = demuxer_->GetCachedDuration();
    MEDIA_LOG_I("current cacheDuration is " PUBLIC_LOG_U64, cacheDuration);
    if ((cacheDuration < bufferDurationForPlaying_ * TIME_CONVERSION_UNIT) && isXSpeedPlay) {
        mode = PlaybackRateMode::SPEED_FORWARD_1_00_X;
        isXSpeedPlay = false;
        MEDIA_LOG_I("below the play waterline, recover to 1x speed play");
        return true;
    } else if ((cacheDuration > (maxLivingDelayTime_ * TIME_CONVERSION_UNIT)) && !isXSpeedPlay) {
        mode = PlaybackRateMode::SPEED_FORWARD_1_20_X;
        isXSpeedPlay = true;
        MEDIA_LOG_I("exceed the max delay time, start to 1.2x speed play");
        return true;
    }
    return false;
}

bool HiPlayerImpl::IsPauseForTooLong(int64_t pauseTime)
{
    return pauseTime > (maxLivingDelayTime_ * TIME_CONVERSION_UNIT * PAUSE_LONG_TIME_FACTOR);
}

void HiPlayerImpl::DoRestartLiveLink()
{
    MediaTrace trace("HiPlayerImpl::DoRestartLiveLink");
    FALSE_RETURN_NOLOG(isFlvLive_);
    FALSE_RETURN_NOLOG(!isLiveSeek_);
    FALSE_RETURN(demuxer_ != nullptr);
    demuxer_->DoFlush();
    if (audioDecoder_ != nullptr) {
        audioDecoder_->DoFlush();
    }
    if (audioSink_ != nullptr) {
        audioSink_->DoFlush();
    }
    if (videoDecoder_ != nullptr) {
        videoDecoder_->DoFlush();
    }
    Status ret = demuxer_->RebootPlugin();
    if (audioDecoder_ != nullptr) {
        audioDecoder_->DoStart();
    }
    if (audioSink_ != nullptr) {
        audioSink_->DoStart();
    }
    if (videoDecoder_ != nullptr) {
        videoDecoder_->DoStart();
    }
    MEDIA_LOG_I("restart live link ret is %{public}d", static_cast<int32_t>(ret));
    return;
}

bool HiPlayerImpl::IsFlvLive()
{
    return isFlvLive_;
}

void HiPlayerImpl::SetFlvLiveParams(AVPlayStrategy playbackStrategy)
{
    if (playbackStrategy.preferredBufferDurationForPlaying < 0) {
        isSetBufferDurationForPlaying_ = false;
        bufferDurationForPlaying_ = 0;
    } else {
        bufferDurationForPlaying_ = playbackStrategy.preferredBufferDurationForPlaying;
        isSetBufferDurationForPlaying_ = true;
    }
    maxLivingDelayTime_ = playbackStrategy.thresholdForAutoQuickPlay;
}

void HiPlayerImpl::UpdateFlvLiveParams()
{
    maxLivingDelayTime_ = maxLivingDelayTime_ < 0 ? AVPlayStrategyConstant::START_QUICK_PLAY_THRESHOLD_SECONDS :
        maxLivingDelayTime_;
    bufferDurationForPlaying_ = isSetBufferDurationForPlaying_ ? bufferDurationForPlaying_ :
        AVPlayStrategyConstant::BUFFER_DURATION_FOR_PLAYING_SECONDS;
    MEDIA_LOG_I("maxLivingDelayTime_ is " PUBLIC_LOG_F " and  bufferDurationForPlaying_ is " PUBLIC_LOG_F,
        maxLivingDelayTime_, bufferDurationForPlaying_);
}

void HiPlayerImpl::SetFlvObs()
{
    FALSE_RETURN(demuxer_ != nullptr);
    isFlvLive_ = demuxer_->IsFlvLive();
    FALSE_RETURN(isFlvLive_);
    MEDIA_LOG_I("SetFlvObs");
    UpdateFlvLiveParams();
    liveController_.StartWithPlayerEngineObs(playerEngineObs_);

    // flv live with play water line max wait 30s.
    FALSE_RETURN_MSG(isSetBufferDurationForPlaying_ && bufferDurationForPlaying_ > 0,
        "Flv live stream and no duration water line");
    MEDIA_LOG_I("Wait flv live play water line for max 30s bufferDuration %{public}.2f", bufferDurationForPlaying_);
    std::unique_lock<std::mutex> lock(flvLiveMutex_);
    flvLiveCond_.wait_for(lock, std::chrono::milliseconds(FLV_LIVE_PREPARE_WAIT_TIME),
        [this] { return isBufferingEnd_.load() || isInterruptNeeded_.load(); });
    MEDIA_LOG_I("Wait flv live play water line for max 30s end");
}

void HiPlayerImpl::StartFlvCheckLiveDelayTime()
{
    FALSE_RETURN_NOLOG(isFlvLive_);
    FALSE_RETURN(demuxer_ != nullptr);
    MEDIA_LOG_I("StartFlvCheckLiveDelayTime");
    liveController_.StartCheckLiveDelayTime(CHECK_DELAY_INTERVAL);
}

void HiPlayerImpl::StopFlvCheckLiveDelayTime()
{
    FALSE_RETURN_NOLOG(isFlvLive_);
    FALSE_RETURN(demuxer_ != nullptr);
    MEDIA_LOG_I("StopFlvCheckLiveDelayTime");
    liveController_.StopCheckLiveDelayTime();
}

void HiPlayerImpl::SetPostProcessor()
{
    if (videoPostProcessorType_ != VideoPostProcessorType::NONE) {
        videoDecoder_->SetPostProcessorType(videoPostProcessorType_);
        videoDecoder_->SetPostProcessorOn(isPostProcessorOn_);
        videoDecoder_->SetVideoWindowSize(postProcessorTargetWidth_, postProcessorTargetHeight_);
    }
    std::lock_guard<std::mutex> lock(fdMutex_);
    FALSE_RETURN_NOLOG(enableCameraPostprocessing_.load() && fdsanFd_ && fdsanFd_->Get() >= 0);
    videoDecoder_->SetCameraPostprocessing(enableCameraPostprocessing_.load());
    videoDecoder_->SetPostProcessorFd(fdsanFd_->Get());
    fdsanFd_->Reset();
}

int32_t HiPlayerImpl::SetReopenFd(int32_t fd)
{
    FALSE_RETURN_V_MSG_E(fd >= 0, MSERR_INVALID_VAL, "Invalid input fd.");
    int32_t dupFd = dup(fd);
    FALSE_RETURN_V_MSG_E(dupFd >= 0, MSERR_INVALID_VAL, "Dup fd failed.");
    std::lock_guard<std::mutex> lock(fdMutex_);
    fdsanFd_ = std::make_unique<FdsanFd>(dupFd);
    FALSE_RETURN_V(fdsanFd_ && (fdsanFd_->Get() >= 0), MSERR_INVALID_VAL);
    return TransStatus(Status::OK);
}
 
int32_t HiPlayerImpl::EnableCameraPostprocessing()
{
    MEDIA_LOG_D("EnableCameraPostprocessing enter.");
    enableCameraPostprocessing_.store(true);
    return TransStatus(Status::OK);
}

void HiPlayerImpl::ResetEnableCameraPostProcess()
{
    enableCameraPostprocessing_.store(false);
    FALSE_RETURN_NOLOG(fdsanFd_ != nullptr);
    fdsanFd_->Reset();
}

int32_t HiPlayerImpl::SetCameraPostprocessing(bool isOpen)
{
#ifdef SUPPORT_VIDEO
    if (videoDecoder_ != nullptr) {
        MEDIA_LOG_I("SetCameraPostprocessing enter");
        videoDecoder_->SetCameraPostprocessingDirect(isOpen);
    }
#endif
    return TransStatus(Status::OK);
}

void HiPlayerImpl::HandleMemoryUsageEvent(const DfxEvent &event)
{
    lock_guard<std::mutex> lock(memoryReportMutex_);
    std::string callerName = event.callerName;
    uint32_t currentUsage = 0;
    if (callerName == DEMUXER_PLUGIN) {
        auto memoryUsages = AnyCast<std::unordered_map<uint32_t, uint32_t>>(event.param);
        for (const auto &[trackId, usage] : memoryUsages) {
        currentUsage += usage;
        }
    } else {
        currentUsage = AnyCast<uint32_t>(event.param);
    }
    currentUsage /= MEMORY_B_TO_KB;

    auto limit = MEMORY_USAGE_REPORT_LIMITS.count(callerName)
        ? MEMORY_USAGE_REPORT_LIMITS.at(callerName) : MEMORY_REPORT_LIMITE;
    MEDIA_LOG_I("caller:%{public}s,currentUsage:%{public}u", callerName.c_str(), currentUsage);

    auto oldIter = memoryUsageInfo_.find(callerName);
    uint32_t oldUsage  = (oldIter != memoryUsageInfo_.end()) ? std::min(oldIter->second, limit) : 0;
    uint32_t totalMemory = memoryUsageInfo_[TOTAL_MEMORY_SIZE];
    FALSE_RETURN_MSG(totalMemory >= oldUsage, "totalMemory:%{public}u oldUsage:%{public}u", totalMemory, oldUsage);
    totalMemory = totalMemory + std::min(currentUsage, limit) - oldUsage;
    FALSE_RETURN_MSG(totalMemory >= 0 && totalMemory < UINT32_MAX, "error totalMemory:%{public}u", totalMemory);
    memoryUsageInfo_[TOTAL_MEMORY_SIZE] = totalMemory;
    memoryUsageInfo_[callerName] = currentUsage;

    MEDIA_LOG_I("totalMemory:%{public}u", totalMemory);
    callbackLooper_.OnDfxInfo({
        .type = DfxEventType::DFX_INFO_MEMORY_USAGE,
        .param = memoryUsageInfo_[TOTAL_MEMORY_SIZE]
    });
    FALSE_RETURN_NOLOG(currentUsage >= limit);
    std::string msg = "";
    for (auto &[key, value] : memoryUsageInfo_) {
        msg += key + ":" + std::to_string(value) + ";";
    }
    MEDIA_LOG_I("memusage event reported, appName:%{public}s msg:%{public}s", bundleName_.c_str(), msg.c_str());
}

int32_t HiPlayerImpl::ForceLoadVideo(bool status)
{
    isForceLoadVideo_ = status;
    return MSERR_OK;
}

int32_t HiPlayerImpl::SetAudioHapticsSyncId(int32_t syncId)
{
    MEDIA_LOG_I("SetAHapSyncId " PUBLIC_LOG_D32, syncId);
    audioHapticsSyncId_ = syncId;
    return TransStatus(Status::OK);
}

void HiPlayerImpl::ApplyAudioHapticsSyncId()
{
    FALSE_RETURN_W(audioSink_ != nullptr);
    MEDIA_LOG_D("ApplyAHapSyncId " PUBLIC_LOG_D32, audioHapticsSyncId_);
    Status ret = audioSink_->SetAudioHapticsSyncId(audioHapticsSyncId_);
    FALSE_RETURN_MSG(ret == Status::OK,
        "ApplyAHapSyncId failed with error " PUBLIC_LOG_D32, static_cast<int32_t>(ret));
}

int32_t HiPlayerImpl::NotifyMemoryExchange(bool status)
{
    FALSE_RETURN_V_NOLOG(videoDecoder_ != nullptr, MSERR_OK);
    videoDecoder_->NotifyMemoryExchange(status);
    return MSERR_OK;
}

void HiPlayerImpl::DoInitDemuxer()
{
    demuxer_->SetPerfRecEnabled(isPerfRecEnabled_);
    demuxer_->SetApiVersion(apiVersion_);
    demuxer_->SetSyncCenter(syncManager_);
    demuxer_->SetSpeedChangeCallback([this](float speed) {
        this->doSetPlaybackSpeed(speed);
    });
    pipeline_->AddHeadFilters({demuxer_});
    {
        ScopedTimer timer("Demuxer Init", DEMUXER_INIT_WARNING_MS);
        demuxer_->Init(playerEventReceiver_, playerFilterCallback_, interruptMonitor_);
    }
    (void)demuxer_->SetPlayerMode();
    if (hasTrackSelectionFilter_.load()) {
        TrackSelectionFilter trackFilter;
        trackFilter.maxVideoBitrate = trackSelectionFilter_.maxVideoBitrate;
        trackFilter.minVideoBitrate = trackSelectionFilter_.minVideoBitrate;
        trackFilter.maxVideoFrameRate = trackSelectionFilter_.maxVideoFrameRate;
        trackFilter.minVideoFrameRate = trackSelectionFilter_.minVideoFrameRate;
        trackFilter.maxVideoResolution = trackSelectionFilter_.maxVideoResolution;
        trackFilter.minVideoResolution = trackSelectionFilter_.minVideoResolution;
        trackFilter.preferredVideoMimeTypes = trackSelectionFilter_.preferredVideoMimeTypes;
        trackFilter.maxAudioBitrate = trackSelectionFilter_.maxAudioBitrate;
        trackFilter.minAudioBitrate = trackSelectionFilter_.minAudioBitrate;
        trackFilter.maxAudioChannels = trackSelectionFilter_.maxAudioChannels;
        trackFilter.preferredAudioMimeTypes = trackSelectionFilter_.preferredAudioMimeTypes;
        trackFilter.preferredAudioLanguages = trackSelectionFilter_.preferredAudioLanguages;
        trackFilter.preferredSubtitleLanguages = trackSelectionFilter_.preferredSubtitleLanguages;
        demuxer_->SetTrackSelectionFilter(trackFilter);
    }
}

Status HiPlayerImpl::InitVideoDecoder()
{
    videoDecoder_ = FilterFactory::Instance().CreateFilter<DecoderSurfaceFilter>("player.videodecoder",
        FilterType::FILTERTYPE_VDEC);
    FALSE_RETURN_V(videoDecoder_ != nullptr, Status::ERROR_NULL_POINTER);
    videoDecoder_->Init(playerEventReceiver_, playerFilterCallback_);
    videoDecoder_->SetIsSwDecoder(isNeedSwDecoder_);
    SetPostProcessor();
    interruptMonitor_->RegisterListener(videoDecoder_);
    videoDecoder_->SetSyncCenter(syncManager_);
    videoDecoder_->SetCallingInfo(appUid_, appPid_, bundleName_, instanceId_);
    if (surface_ != nullptr) {
        videoDecoder_->SetVideoSurface(surface_);
        videoDecoder_->SetSeiMessageCbStatus(seiMessageCbStatus_  && IsLiveStream(), payloadTypes_);
    }
    if (sideOutputSurface_ != nullptr) {
        SetVideoOutput(sideOutputSurface_);
    }
    videoDecoder_->SetPerfRecEnabled(isPerfRecEnabled_);
    // set decrypt config for drm videos
    if (isDrmProtected_) {
        std::unique_lock<std::mutex> lock(drmMutex_);
        static constexpr int32_t timeout = 5;
        bool notTimeout = drmConfigCond_.wait_for(lock, std::chrono::seconds(timeout), [this]() {
            return this->isDrmPrepared_ || this->stopWaitingDrmConfig_;
        });
        if (notTimeout && isDrmPrepared_) {
            MEDIA_LOG_I("LinkVideoDecoderFilter will SetDecryptConfig");
#ifdef SUPPORT_AVPLAYER_DRM
            bool svpFlag = svpMode_ == HiplayerSvpMode::SVP_TRUE ? true : false;
            videoDecoder_->SetDecryptConfig(keySessionServiceProxy_, svpFlag);
#endif
        } else {
            MEDIA_LOG_E("HiPlayerImpl Drmcond wait timeout or has been stopped! Play drm protected video failed!");
            return Status::ERROR_INVALID_OPERATION;
        }
    } else {
        MEDIA_LOG_D("HiPlayerImpl::LinkVideoDecoderFilter, and it's not drm-protected.");
    }
    return Status::OK;
}

void HiPlayerImpl::ReleaseVideoDecoderOnMuted()
{
    if (videoDecoder_ != nullptr) {
        videoDecoder_->ReleaseOnMuted(!keepDecodingOnMute_);
    }
}

int32_t HiPlayerImpl::SetLoudnessGain(float loudnessGain)
{
    MEDIA_LOG_D("SetLoudnessGain in");
    FALSE_RETURN_V_MSG_E(audioSink_ != nullptr, (int32_t)TransStatus(Status::ERROR_INVALID_OPERATION),
        "SetLoudnessGain failed, audio sink is nullptr");
    return TransStatus(audioSink_->SetLoudnessGain(loudnessGain));
}

int32_t HiPlayerImpl::GetGlobalInfo(std::shared_ptr<Meta> &globalInfo)
{
    MEDIA_LOG_D("GetGlobalInfo in");
    FALSE_RETURN_V(demuxer_ != nullptr, TransStatus(Status::ERROR_NULL_POINTER));
    globalInfo = demuxer_->GetGlobalInfo();
    FALSE_RETURN_V(globalInfo != nullptr, TransStatus(Status::ERROR_NULL_POINTER));
    return TransStatus(Status::OK);
}

void HiPlayerImpl::CacheBuffer()
{
    FALSE_RETURN(demuxer_ != nullptr && !demuxer_->IsAudioDemuxDecodeAsync() && audioSink_ != nullptr);
    Status ret = Status::OK;
    ret = audioSink_->CacheBuffer();
    FALSE_RETURN(ret != Status::OK);
    UpdateStateNoLock(PlayerStates::PLAYER_STATE_ERROR);
}

void HiPlayerImpl::CleanUnusedListener()
{
    FALSE_RETURN(interruptMonitor_ != nullptr);
    interruptMonitor_->CleanUnusedListener();
}

int32_t HiPlayerImpl::GetMediaDescription(Format &format)
{
    FALSE_RETURN_V_MSG_E(demuxer_ != nullptr, TransStatus(Status::ERROR_NULL_POINTER), "demuxer_ is null");
    std::shared_ptr<Meta> globalMeta = demuxer_->GetGlobalMetaInfo();
    format.SetMeta(globalMeta);
    return TransStatus(Status::OK);
}

bool HiPlayerImpl::IsAudioPass(const char* mimeType)
{
    MEDIA_LOG_I("HiPlayerImpl::IsAudioPass");
    FALSE_RETURN_V(mimeType != nullptr, false);
    return callbackLooper_.IsAudioPass(mimeType);
}

std::vector<std::string> HiPlayerImpl::GetDolbyList()
{
    MEDIA_LOG_I("HiPlayerImpl::GetDolbyList");
    return callbackLooper_.GetDolbyList();
}

bool HiPlayerImpl::IsLiveSeek()
{
    return isLiveSeek_;
}

void HiPlayerImpl::ExtractStrategyParams(const AVPlayStrategy &strategy)
{
    preferedWidth_ = strategy.preferredWidth;
    preferedHeight_ = strategy.preferredHeight;
    bufferDuration_ = strategy.preferredBufferDuration;
    preferHDR_ = strategy.preferredHdr;
    renderFirstFrame_ = strategy.showFirstFrameOnPrepare;
    mutedMediaType_ = strategy.mutedMediaType;
    audioLanguage_ = strategy.preferredAudioLanguage;
    subtitleLanguage_ = strategy.preferredSubtitleLanguage;
    enableCameraPostprocessing_ = strategy.enableCameraPostprocessing;
    videoPostProcessorType_ =
        strategy.enableSuperResolution ? VideoPostProcessorType::SUPER_RESOLUTION : VideoPostProcessorType::NONE;
    isPostProcessorOn_ = strategy.enableSuperResolution;
}

int32_t HiPlayerImpl::NotifySubtitleSeek()
{
    if (!hasExtSub_ && subtitleSink_ != nullptr) {
        subtitleSink_->NotifySeek();
    }
    return TransStatus(Status::OK);
}

void HiPlayerImpl::HandleReadyAudioInterrupt()
{
    {
        AutoLock lock(stateChangeMutex_);
        FALSE_RETURN_NOLOG(curState_ == PlayerStateId::READY);
    }
    FALSE_RETURN_NOLOG(!isAudioInitialized_.load());
    isAudioInitialized_.store(true);
    HandleInitialPlayingStateChange(EventType::EVENT_AUDIO_FIRST_FRAME);
}

int32_t HiPlayerImpl::SetVideoOutput(sptr<Surface> surface)
{
    MEDIA_LOG_I("SetVideoOutput in");
#ifdef SUPPORT_VIDEO
    FALSE_RETURN_V_MSG_E(surface != nullptr, (int32_t)(Status::ERROR_INVALID_PARAMETER),
        "Set video output surface failed, surface == nullptr");
    sideOutputSurface_ = surface;
    videoPostProcessorType_ = VideoPostProcessorType::SIDE_OUTPUT;
    if (videoDecoder_ != nullptr) {
        MEDIA_LOG_I("SetPostProcessorType in");
        videoDecoder_->SetPostProcessorType(videoPostProcessorType_);
        videoDecoder_->SetVideoOutput(surface);
    }
#endif
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::GetVideoSample(int32_t &outputResult)
{
    MEDIA_LOG_I("GetVideoSample in");
    FALSE_RETURN_V_MSG_E(!isSeek_.load(), MSERR_INVALID_OPERATION,
        "Calling this interface is not supported during seeking");
#ifdef SUPPORT_VIDEO
    if (videoDecoder_ != nullptr) {
        videoDecoder_->GetVideoSample(outputResult);
    }
#endif
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetPCMCallback(const std::shared_ptr<IPCMCallback>& callback)
{
    std::lock_guard<std::mutex> lock(pcmCallbackMutex_);
    pcmCallback_ = callback;
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetPCMOutputStatus(bool isEnable)
{
    std::lock_guard<std::mutex> lock(pcmCallbackMutex_);

    // If isPcmProcessorEnable_ is true, can not set SetPCMOutputStatus
    FALSE_RETURN_V_MSG_E(!isPcmProcessorEnable_, TransStatus(Status::ERROR_INVALID_OPERATION),
        "Can not SetPCMOutputCallback because has SetPCMProcessorCallback.");
    isPcmOutputEnable_ = isEnable;
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetPCMProcessorStatus(bool isEnable)
{
    std::lock_guard<std::mutex> lock(pcmCallbackMutex_);

    // If isPcmOutputEnable_ is true, can not set SetPCMProcessorStatus
    FALSE_RETURN_V_MSG_E(!isPcmOutputEnable_, TransStatus(Status::ERROR_INVALID_OPERATION),
        "Can not SetPCMProcessorCallback because has SetPCMOutputCallback.");
    isPcmProcessorEnable_ = isEnable;
    return TransStatus(Status::OK);
}

int32_t HiPlayerImpl::SetPCMProcessorMaxLen(int32_t maxProcessedPcmLen)
{
    std::lock_guard<std::mutex> lock(pcmCallbackMutex_);
    maxProcessedPcmLen_ = maxProcessedPcmLen;
    return TransStatus(Status::OK);
}

void HiPlayerImpl::InitPcmCallback()
{
    FALSE_RETURN(audioSink_ != nullptr);

    std::lock_guard<std::mutex> lock(pcmCallbackMutex_);
    audioSink_->SetPCMCallback(pcmCallback_);
    audioSink_->SetPCMOutputStatus(isPcmOutputEnable_);
    audioSink_->SetPCMProcessorStatus(isPcmProcessorEnable_);
    audioSink_->SetPCMProcessorMaxLen(maxProcessedPcmLen_);
}

int32_t HiPlayerImpl::AddAdsMediaSource(const std::shared_ptr<AVMediaSource> &mediaSource,
    int64_t startMs, std::string &outId)
{
    FALSE_RETURN_V_MSG_E(demuxer_ != nullptr, MSERR_INVALID_OPERATION, "DemuxerFilter is nullptr");
    FALSE_RETURN_V_MSG_E(mediaSource != nullptr, MSERR_INVALID_VAL, "mediaSource is nullptr");
    auto source = std::make_shared<MediaSource>(mediaSource->url);
    return TransStatus(demuxer_->AddAdsMediaSource(source, startMs, IsLiveStream(), outId));
}

int32_t HiPlayerImpl::RemoveAdsMediaSource(const std::string &id)
{
    FALSE_RETURN_V_MSG_E(demuxer_ != nullptr, MSERR_INVALID_OPERATION, "DemuxerFilter is nullptr");
    return TransStatus(demuxer_->RemoveAdsMediaSource(id));
}

int32_t HiPlayerImpl::SkipCurrentAdsMediaSource()
{
    FALSE_RETURN_V_MSG_E(demuxer_ != nullptr, MSERR_INVALID_OPERATION, "DemuxerFilter is nullptr");
    return TransStatus(demuxer_->SkipCurrentAdsMediaSource());
}

int32_t HiPlayerImpl::DisableAllAdsMediaSource()
{
    FALSE_RETURN_V_MSG_E(demuxer_ != nullptr, MSERR_INVALID_OPERATION, "DemuxerFilter is nullptr");
    return TransStatus(demuxer_->DisableAllAdsMediaSource());
}

void HiPlayerImpl::HandleVideoCodecChange(const std::shared_ptr<Meta> &meta, bool &isCodecChanged, bool isSmoothSwitch)
{
    isCodecChanged = false;
    FALSE_RETURN(videoDecoder_ != nullptr);
    isCodecChanged = videoDecoder_->IsCodecChanged(meta);
    FALSE_RETURN_NOLOG(isCodecChanged);
    isSmoothSwitch ? videoDecoder_->SetNewMeta(meta) : videoDecoder_->ChangePlugin(meta);
}

bool HiPlayerImpl::IsNeedAudioSinkChangeTrack(std::shared_ptr<Meta> preMeta, std::shared_ptr<Meta> meta)
{
    int32_t sampleRate = -1;
    int32_t channels = -1;
    Plugins::AudioSampleFormat sampleFormat;

    int32_t currentSampleRate = -1;
    int32_t currentChannels = -1;
    Plugins::AudioSampleFormat currentSampleFormat;

    FALSE_RETURN_V(preMeta->GetData(Tag::AUDIO_SAMPLE_RATE, sampleRate), false);
    FALSE_RETURN_V(meta->GetData(Tag::AUDIO_SAMPLE_RATE, currentSampleRate), false);
    FALSE_RETURN_V(sampleRate == currentSampleRate, true);

    FALSE_RETURN_V(preMeta->GetData(Tag::AUDIO_CHANNEL_COUNT, channels), false);
    FALSE_RETURN_V(meta->GetData(Tag::AUDIO_CHANNEL_COUNT, currentChannels), false);
    FALSE_RETURN_V(channels == currentChannels, true);

    FALSE_RETURN_V(preMeta->GetData(Tag::AUDIO_SAMPLE_FORMAT, sampleFormat), false);
    FALSE_RETURN_V(meta->GetData(Tag::AUDIO_SAMPLE_FORMAT, currentSampleFormat), false);
    FALSE_RETURN_V(sampleFormat == currentSampleFormat, true);

    std::string mimeType;
    AudioStandard::AudioEncodingType encodingType;
    std::string currentMimeType;
    AudioStandard::AudioEncodingType currentEncodingType;
    FALSE_RETURN_V(preMeta->GetData(Tag::MIME_TYPE, mimeType), false);
    FALSE_RETURN_V(meta->GetData(Tag::MIME_TYPE, currentMimeType), false);
    encodingType = (mimeType == MimeType::AUDIO_AVS3DA)
                ? AudioStandard::ENCODING_AUDIOVIVID : AudioStandard::ENCODING_PCM;
    currentEncodingType = (currentMimeType == MimeType::AUDIO_AVS3DA)
                ? AudioStandard::ENCODING_AUDIOVIVID : AudioStandard::ENCODING_PCM;
    FALSE_RETURN_V(mimeType == currentMimeType, true);

    return false;
}

bool HiPlayerImpl::HandleAudioDecoderChangeEvent(const Event& event)
{
    MEDIA_LOG_I("HandleDecoderChange audio");
    auto meta = AnyCast<std::shared_ptr<Meta>>(event.param);
    FALSE_RETURN_V(meta != nullptr, false);
    std::string mime;

    if (!(meta->GetData(Tag::MIME_TYPE, mime))) {
        MEDIA_LOG_E("get mime error");
        return false;
    }

    if (IsAudioMime(mime)) {
        if (currentAudioTrackId_ < 0) {
            FALSE_RETURN_V(Status::OK == InitAudioDefaultTrackIndex(), false);
        }
        std::shared_ptr<Meta> preMeta = std::make_shared<Meta>();
        FALSE_RETURN_V(audioSink_ != nullptr, false);
        audioSink_->GetParameter(preMeta);
        FALSE_GOON_NOEXEC(audioDecoder_ != nullptr, audioDecoder_->UpdateTrackInfoSampleFormat(mime, meta));
        if (!IsNeedAudioSinkChangeTrack(preMeta, meta)) {
            demuxer_->StartTask(OHOS::Media::Plugins::MediaType::AUDIO);
            return false;
        }
        if (audioDecoder_ != nullptr && Status::OK != audioDecoder_->ChangePlugin(meta)) {
            MEDIA_LOG_E("audioDecoder change plugin error");
            Event errorEvent {"audioDecoder", EventType::EVENT_ERROR, MSERR_UNSUPPORT_AUD_DEC_TYPE, mime};
            HandleErrorEvent(errorEvent);
            return false;
        }
        FALSE_GOON_NOEXEC(audioDecoder_ != nullptr, audioDecoder_->DoFlush());
        audioSink_->DoFlush();
        FALSE_GOON_NOEXEC(audioDecoder_ != nullptr, audioDecoder_->Start());
        if (Status::OK != audioSink_->ChangeTrack(meta)) {
            MEDIA_LOG_E("audioSink change track error");
            return false;
        }
        demuxer_->StartTask(OHOS::Media::Plugins::MediaType::AUDIO);
    }
    return true;
}

bool HiPlayerImpl::HandleAudioTrackChangeReportEvent(const Event& event)
{
    int32_t innerTrackId = AnyCast<int32_t>(event.param);
    std::vector<std::shared_ptr<Meta>> metaInfo = demuxer_->GetStreamMetaInfo();
    std::string mime;
    auto iter = std::find_if(metaInfo.begin(), metaInfo.end(),
        [innerTrackId](const std::shared_ptr<Meta> &trackMeta) {
            int32_t trackIndex;
            if (trackMeta->GetData(Tag::REGULAR_TRACK_ID, trackIndex)) {
                return trackIndex == innerTrackId;
            }
            return false;
        }
    );
    FALSE_RETURN_V(iter != metaInfo.end(), false);
    auto meta = *iter;
    FALSE_RETURN_V(meta != nullptr, false);
    int32_t index = std::distance(metaInfo.begin(), iter);
    if (!(meta->GetData(Tag::MIME_TYPE, mime))) {
        MEDIA_LOG_E("HandleAudioTrackChangeReportEvent trackId " PUBLIC_LOG_D32 "get mime error.", innerTrackId);
        return false;
    }
    if (IsAudioMime(mime)) {
        if (currentAudioTrackId_ < 0) {
            FALSE_RETURN_V(Status::OK == InitAudioDefaultTrackIndex(), false);
        }
        if (Status::OK != demuxer_->StartTask(innerTrackId)) {
            MEDIA_LOG_E("HandleAudioTrackChangeReportEvent StartTask error.trackId is " PUBLIC_LOG_D32, innerTrackId);
            return false;
        }
        Format audioTrackInfo {};
        audioTrackInfo.PutIntValue("track_index", static_cast<int32_t>(index));
        audioTrackInfo.PutIntValue("track_is_select", 1);
        callbackLooper_.OnInfo(INFO_TYPE_TRACKCHANGE, 0, audioTrackInfo);
        currentAudioTrackId_ = index;
        NotifyUpdateTrackInfo();
    }
    return true;
}
}  // namespace Media
}  // namespace OHOS
