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

#ifndef HI_PLAYER_IMPL_H
#define HI_PLAYER_IMPL_H

#include <memory>
#include <unordered_map>
#include <queue>
#include <chrono>

#include "audio_info.h"
#include "audio_decoder_filter.h"
#include "audio_sink_filter.h"
#include "common/status.h"
#include "demuxer_filter.h"
#include "filter/filter.h"
#include "filter/filter_factory.h"
#include "hiplayer_callback_looper.h"
#include "live_controller.h"
#include "media_utils.h"
#include "i_player_engine.h"
#include "media_sync_manager.h"
#include "pipeline/pipeline.h"
#include "seek_agent.h"
#include "dfx_agent.h"
#include "subtitle_sink_filter.h"
#include "meta/meta.h"
#include "meta/media_types.h"
#include "dragging_player_agent.h"
#include "interrupt_monitor.h"
#include "plugin/plugin_time.h"
#ifdef SUPPORT_VIDEO
#include "decoder_surface_filter.h"
#include "sei_parser_filter.h"
#endif
#include "common/fdsan_fd.h"

namespace OHOS {
namespace Media {
using namespace Pipeline;
struct PlayStatisticalInfo {
    int32_t errCode {0};
    std::string errMsg {};
    int32_t playDuration {0};
    int32_t sourceType {0};
    std::string sourceUrl {};
    int32_t avgDownloadRate {0};
    std::string containerMime {};
    std::string videoMime {};
    std::string videoResolution {};
    float videoFrameRate {0.0};
    int8_t videoBitdepth {0};
    int32_t videoBitrate {0};
    int8_t hdrType {0};
    std::string audioMime {};
    int32_t audioSampleRate {0};
    int32_t audioChannelCount {0};
    int32_t audioBitrate {0};
    std::string subtitleMime {};
    std::string subtitleLang {};
    bool isDrmProtected {false};
    int32_t startLatency {0};
    int32_t avgDownloadSpeed {0};
    int32_t maxSeekLatency {0};
    int32_t maxAccurateSeekLatency {0};
    int32_t lagTimes {0};
    int32_t maxLagDuration {0};
    int32_t avgLagDuration {0};
    int32_t maxSurfaceSwapLatency {0};
    uint64_t totalDownLoadBits {0};
    bool isTimeOut {false};
};

enum VideoHdrType : int32_t {
    /**
     * This option is used to mark none HDR type.
     */
    VIDEO_HDR_TYPE_NONE,
    /**
     * This option is used to mark HDR Vivid type.
     */
    VIDEO_HDR_TYPE_VIVID,
};


class HiPlayerImpl : public IPlayerEngine, public std::enable_shared_from_this<HiPlayerImpl> {
public:
    HiPlayerImpl(int32_t appUid, int32_t appPid, uint32_t appTokenId, uint64_t appFullTokenId);
    ~HiPlayerImpl() override;
    HiPlayerImpl(const HiPlayerImpl& other) = delete;
    HiPlayerImpl& operator=(const HiPlayerImpl& other) = delete;
    Status Init();
    // interface from PlayerInterface
    int32_t SetSource(const std::string& uri) override;
    int32_t SetSource(const std::shared_ptr<IMediaDataSource>& dataSrc) override;
    int32_t AddSubSource(const std::string &url) override;
    int32_t Prepare() override;
    int32_t SetRenderFirstFrame(bool display) override;
    int32_t SetPlayRange(int64_t start, int64_t end) override;
    int32_t SetPlayRangeWithMode(int64_t start, int64_t end, PlayerSeekMode mode) override;
    int32_t SetIsCalledBySystemApp(bool isCalledBySystemApp) override;
    int32_t PrepareAsync() override;
    int32_t Play() override;
    int32_t Pause(bool isSystemOperation) override;
    int32_t Stop() override;
    int32_t Reset() override;
    int32_t Freeze(bool &isNoNeedToFreeze) override;
    int32_t UnFreeze() override;
    int32_t PauseSourceDownload() override;
    int32_t ResumeSourceDownload() override;
    int32_t Seek(int64_t mSeconds, PlayerSeekMode mode) override;
    int32_t SeekToDefaultPosition() override;
    int32_t SetVolume(float leftVolume, float rightVolume) override;
    int32_t SetVolumeMode(int32_t mode) override;
    int32_t SetVideoSurface(sptr<Surface> surface) override;
    int32_t SetDecryptConfig(const sptr<OHOS::DrmStandard::IMediaKeySessionService> &keySessionProxy,
        bool svp) override;
    int32_t SetLooping(bool loop) override;
    int32_t SetParameter(const Format& params) override;
    int32_t SetObs(const std::weak_ptr<IPlayerEngineObs>& obs) override;
    int32_t GetCurrentTime(int32_t& currentPositionMs) override;
    int32_t GetPlaybackPosition(int32_t& playbackPositionMs) override;
    int32_t GetCurrentPresentationTimestamp(int64_t &currentPresentation) override;
    int32_t GetDuration(int32_t& durationMs) override;
    std::vector<Plugins::SeekRange> GetSeekableRanges() override;
    std::vector<Plugins::SeekRange> GetLoadedRanges() override;
    int32_t SetPlaybackSpeed(PlaybackRateMode mode) override;
    int32_t SetPlaybackRate(float rate) override;
    int32_t SetMediaSource(const std::shared_ptr<AVMediaSource> &mediaSource, AVPlayStrategy strategy) override;
    int32_t GetPlaybackSpeed(PlaybackRateMode& mode) override;
    int32_t GetPlaybackRate(float& rate) override;
    int32_t SelectBitRate(uint32_t bitRate, bool isAutoSelect) override;
    int32_t GetAudioEffectMode(int32_t &effectMode) override;
    int32_t SetAudioEffectMode(int32_t effectMode) override;

    int32_t GetCurrentTrack(int32_t trackType, int32_t &index) override;
    int32_t SelectTrack(int32_t trackId, PlayerSwitchMode mode) override;
    int32_t DeselectTrack(int32_t trackId) override;
    int32_t GetVideoTrackInfo(std::vector<Format>& videoTrack) override;
    int32_t GetPlaybackInfo(Format& playbackInfo) override;
    int32_t GetPlaybackStatisticMetrics(Format& playbackStatisticMetrics) override;
    int32_t GetAudioTrackInfo(std::vector<Format>& audioTrack) override;
    int32_t GetSubtitleTrackInfo(std::vector<Format>& subtitleTrack) override;
    int32_t GetVideoWidth() override;
    int32_t GetVideoHeight() override;
    int32_t SetVideoScaleType(VideoScaleType videoScaleType) override;
    int32_t SetAudioRendererInfo(const int32_t contentType, const int32_t streamUsage,
                                 const int32_t rendererFlag, const int32_t volumeMode) override;
    int32_t SetAudioInterruptMode(const int32_t interruptMode) override;
    int32_t SeekToCurrentTime(int32_t mSeconds, PlayerSeekMode mode) override;
    int32_t SetStartFrameRateOptEnabled(bool enabled) override;
    void SetInterruptState(bool isInterruptNeeded) override;
    void OnDumpInfo(int32_t fd) override;
    void SetInstancdId(uint64_t instanceId) override;
    void SetApiVersion(int32_t apiVersion) override;
    int64_t GetPlayRangeStartTime() override;
    int64_t GetPlayRangeEndTime() override;
    int32_t GetPlayRangeSeekMode() override;
    bool IsNeedChangePlaySpeed(PlaybackRateMode &mode, bool &isXSpeedPlay) override;
    bool IsPauseForTooLong(int64_t pauseTime) override;
    bool IsLivingMaxDelayTimeValid() override;
    bool IsFlvLive() override;
    void DoRestartLiveLink() override;

    // internal interfaces
    void EnableStartFrameRateOpt(Format &videoTrack);
    void OnEvent(const Event &event);
    void OnEventContinue(const Event &event);
    void OnEventSub(const Event &event);
    void OnEventSubTrackChange(const Event &event);
    void HandleDfxEvent(const DfxEvent &event);
    void HandleMemoryUsageEvent(const DfxEvent &event);
    void OnStateChanged(PlayerStateId state, bool isSystemOperation = false);
    void HandleLoadingBitrateEvent(const AVMetricsEvent& infoCopy);
    void HandleLoadingErrorEvent(const AVMetricsEvent& info);
    void HandleMediaChangedEvent(const AVMetricsEvent& info);
    void FillAudioSampleRateFromDemuxer(const std::string& changeResultStr,
        int32_t audioSampleRateAfter, Format& format);
    void HandleMediaDiscontinueEvent(const AVMetricsEvent& info);
    void HandleAudioStatusEvent(const AVMetricsEvent& info);
    void HandleCodecAbnormalEvent(const AVMetricsEvent& info);
    void HandleLipAsyncEvent(const AVMetricsEvent& info);
    void FillMediaChangedInfo(Format& format, const AVMetricsEvent& info);
    Status OnCallback(std::shared_ptr<Filter> filter, const FilterCallBackCommand cmd,
        OHOS::Media::Pipeline::StreamType outType);
    int32_t SeekContinous(int64_t mSeconds, int64_t seekContinousBatchNo) override;
    int32_t ExitSeekContinous(bool align, int64_t seekContinousBatchNo) override;
    int32_t PauseDemuxer() override;
    int32_t ResumeDemuxer() override;
    int32_t SetPlaybackStrategy(AVPlayStrategy playbackStrategy) override;
    int32_t SetTrackSelectionFilter(AVPlayTrackSelectionFilter trackFilter) override;
    int32_t SetMediaMuted(OHOS::Media::MediaType mediaType, bool isMuted) override;
    int32_t SetSuperResolution(bool enabled) override;
    int32_t SetVideoWindowSize(int32_t width, int32_t height) override;
    float GetMaxAmplitude() override;
    int32_t SetMaxAmplitudeCbStatus(bool status) override;
    int32_t IsSeekContinuousSupported(bool &isSeekContinuousSupported) override;
    int32_t SetSeiMessageCbStatus(bool status, const std::vector<int32_t> &payloadTypes) override;
    void SetPerfRecEnabled(bool isPerfRecEnabled) override;
    int32_t SetReopenFd(int32_t fd) override;
    int32_t EnableCameraPostprocessing() override;
    int32_t SetCameraPostprocessing(bool isOpen) override;
    int32_t EnableReportMediaProgress(bool enable) override;
    int32_t ForceLoadVideo(bool status) override;
    int32_t NotifyMemoryExchange(bool status) override;
    void SetEosInLoopForFrozen(bool status) override;
    int32_t SetLoudnessGain(float loudnessGain) override;
    int32_t GetGlobalInfo(std::shared_ptr<Meta> &globalInfo) override;
    void CleanUnusedListener();
    int32_t SetBuffering(bool isBuffering);
    int32_t GetMediaDescription(Format &format) override;
    bool IsAudioPass(const char* mimeType) override;
    std::vector<std::string> GetDolbyList() override;
    int32_t NotifySubtitleSeek();
    bool IsLiveSeek() override;
    int32_t SetVideoOutput(sptr<Surface> surface) override;
    int32_t GetVideoSample(int32_t &outputResult) override;
    int32_t SetPCMCallback(const std::shared_ptr<IPCMCallback> &callback) override;
    int32_t SetPCMOutputStatus(bool isEnable) override;
    int32_t SetPCMProcessorStatus(bool isEnable) override;
    int32_t SetPCMProcessorMaxLen(int32_t maxProcessedPcmLen) override;
    int32_t AddAdsMediaSource(const std::shared_ptr<AVMediaSource> &mediaSource,
        int64_t startMs, std::string &outId) override;
    int32_t RemoveAdsMediaSource(const std::string &id) override;
    int32_t SkipCurrentAdsMediaSource() override;
    int32_t DisableAllAdsMediaSource() override;
    void HandleVideoCodecChange(const std::shared_ptr<Meta> &meta, bool &isCodecChanged, bool isSmoothSwitch);

private:
    enum HiplayerSvpMode : int32_t {
        SVP_CLEAR = -1, /* it's not a protection video */
        SVP_FALSE, /* it's a protection video but not secure decoder */
        SVP_TRUE, /* it's a protection video and need secure decoder */
    };

    Status DoSetSource(const std::shared_ptr<MediaSource> source);
    void DoSetPlayStrategy(const std::shared_ptr<MediaSource> source);
    void DoSetPlayMediaStream(const std::shared_ptr<MediaSource>& source);
    void HandleMetricsEventByType(const AVMetricsEvent& infoCopy);
    void HandleStallingEvent(const AVMetricsEvent& infoCopy);
    Status Resume();
    void GetDumpFlag();
    void HandleCompleteEvent(const Event& event);
    void HandleInitialPlayingStateChange(const EventType& eventType);
    void HandleDrmInfoUpdatedEvent(const Event& event);
    void HandleIsLiveStreamEvent(bool isLiveStream);
    void HandleErrorEvent(const Event& event);
    void HandleResolutionChangeEvent(const Event& event);
    void HandleBitrateStartEvent(const Event& event);
    void HandleAudioTrackChangeEvent(const Event& event);
    void HandleVideoTrackChangeEvent(const Event& event);
    void HandleSubtitleTrackChangeEvent(const Event& event);
    void HandleFlvAutoSelectBitRate(uint32_t bitRate);
    void HandleSeiInfoEvent(const Event &event);
    void HandleTimedMetaData(std::shared_ptr<MediaAVCodec::AVTimedMetaData> meta);
    void HandleAdsChange(std::shared_ptr<MediaAVCodec::AVAdsChangeEvent> event);
    void NotifyBufferingStart(int32_t param);
    void NotifyBufferingEnd(int32_t param);
    void NotifyCachedDuration(int32_t param);
    void UpdateStateNoLock(PlayerStates newState, bool notifyUpward = true, bool isSystemOperation = false);
    void NotifyBufferingUpdate(const std::string_view& type, int32_t param);
    void NotifyDurationUpdate(const std::string_view& type, int32_t param);
    void NotifySeekDone(int32_t seekPos);
    void NotifyAudioInterrupt(const Event& event);
    void NotifyAudioStatusDfxEvent(int32_t hintType);
    void NotifyAudioDeviceChange(const Event& event);
    void NotifyAudioServiceDied();
    void NotifyAudioFirstFrame(const Event& event);
    void NotifyResolutionChange();
    void NotifyPositionUpdate();
    void NotifySuperResolutionChanged(const Event& event);
    Status LinkAudioDecoderFilter(const std::shared_ptr<Filter>& preFilter, OHOS::Media::Pipeline::StreamType type);
    Status LinkAudioSinkFilter(const std::shared_ptr<Filter>& preFilter, OHOS::Media::Pipeline::StreamType type);
    Status LinkSubtitleSinkFilter(const std::shared_ptr<Filter>& preFilter, OHOS::Media::Pipeline::StreamType type);
    void SetAudioRendererParameter();
    void NotifySubtitleUpdate(const Event& event);
    void NotifyDecoderErrorFrame(int64_t pts);
    void DoInitializeForHttp();
    bool EnableBufferingBySysParam() const;
    bool IsFileUrl(const std::string &url) const;
    bool IsNetworkUrl(const std::string &url) const;
    bool IsValidPlayRange(int64_t start, int64_t end) const;
    int32_t GetRealPath(const std::string &url, std::string &realUrlPath) const;
    int32_t HandleErrorRet(Status ret, const std::string& errMsg);
    int32_t SetPrivacyType(const int32_t privacyType);
    void SetDefaultAudioRenderInfo(const std::vector<std::shared_ptr<Meta>> &trackInfos);
    void AppendPlayerMediaInfo();
    void AppendPlaybackStatisticsInfo();
    int64_t GetCurrentMillisecond();
    void UpdatePlayStatistics();
    void DoSetMediaSource(Status& ret);
    bool ValidateAndInitMediaSource(const std::shared_ptr<AVMediaSource> &mediaSource);
    bool HandleDataSource(const std::shared_ptr<AVMediaSource> &mediaSource);
    void HandleFileDescriptor(const std::shared_ptr<AVMediaSource> &mediaSource);
    int32_t HandleFileUrl();
    void DetermineSourceType();
    void UpdatePlayerStateAndNotify();
    void UpdateMediaFirstPts();
    void UpdateMaxSeekLatency(PlayerSeekMode mode, int64_t seekStartTime);
#ifdef SUPPORT_VIDEO
    Status LinkVideoDecoderFilter(const std::shared_ptr<Filter>& preFilter, OHOS::Media::Pipeline::StreamType type);
    Status LinkSeiDecoder(const std::shared_ptr<Filter>& preFilter, OHOS::Media::Pipeline::StreamType type);
    bool IsVideoMime(const std::string& mime);
    Status InitVideoDecoder();
#endif
    bool IsAudioMime(const std::string& mime);
    bool IsSubtitleMime(const std::string& mime);
    bool IsNeedAudioSinkChangeTrack(std::vector<std::shared_ptr<Meta>>& metaInfo, int32_t newAudioTrackId);
    Status Seek(int64_t mSeconds, PlayerSeekMode mode, bool notifySeekDone, bool isUnFreezeSeek = false);
    Status LiveSeek(int64_t mSeconds, PlayerSeekMode mode, bool notifySeekDone, bool isUnFreezeSeek);
    Status HandleSeek(int64_t seekPos, PlayerSeekMode mode, bool isUnFreezeSeek = false);
    
    Status doPreparedSeek(int64_t seekPos, PlayerSeekMode mode);
    Status doStartedSeek(int64_t seekPos, PlayerSeekMode mode);
    Status doPausedSeek(int64_t seekPos, PlayerSeekMode mode);
    Status doFrozenSeek(int64_t seekPos, PlayerSeekMode mode, bool isUnFreezeSeek = false);
    Status doCompletedSeek(int64_t seekPos, PlayerSeekMode mode);
    Status doSeek(int64_t seekPos, PlayerSeekMode mode);
    Status doSetPlaybackSpeed(float speed);
    Status HandleSeekClosest(int64_t seekPos, int64_t seekTimeUs);
    void NotifySeek(Status rtv, bool flag, int64_t seekPos);
    void ResetIfSourceExisted();
    void ReleaseInner();
    int32_t InitDuration();
    int32_t InitVideoWidthAndHeight();
    int32_t SetFrameRateForSeekPerformance(double frameRate);
    void SetBundleName(std::string bundleName);
    Status InitAudioDefaultTrackIndex();
    Status InitVideoDefaultTrackIndex();
    Status InitSubtitleDefaultTrackIndex();
    void DoPausedPlay(int32_t &ret);
    bool BreakIfInterruptted();
    void CollectionErrorInfo(int32_t errCode, const std::string& errMsg);
    void NotifyUpdateTrackInfo();
    Status SelectSeekType(int64_t seekPos, PlayerSeekMode mode);
    Status DoSetPlayRange();
    void ResetPlayRangeParameter();
    bool IsInValidSeekTime(int64_t seekPos);
    int64_t GetPlayStartTime();
    Status StartSeekContinous();
    void FlushVideoEOS();
    int32_t InnerSelectTrack(std::string mime, int32_t trackId, PlayerSwitchMode mode);
    bool NeedSeekClosest();
    bool HandleEosFlagState(const Event& event);
    int32_t GetSarVideoWidth(std::shared_ptr<Meta> trackInfo);
    int32_t GetSarVideoHeight(std::shared_ptr<Meta> trackInfo);
    bool IsLiveStream();
    Status SetSeiMessageListener();
    void UpdatePlayTotalDuration();
    inline bool IsStatisticalInfoValid();
    void ReportAudioInterruptEvent();
    int32_t AdjustCachedDuration(int32_t cachedDuration);
    bool IsLivingMaxDelyTimeValid();
    void SetFlvObs();
    void StartFlvCheckLiveDelayTime();
    void StopFlvCheckLiveDelayTime();
    void UpdateFlvLiveParams();
    void SetFlvLiveParams(AVPlayStrategy playbackStrategy);
    void SetPostProcessor();
    void ResetEnableCameraPostProcess();
    int32_t SetAudioHapticsSyncId(int32_t syncId);
    void ApplyAudioHapticsSyncId();
    void DoInitDemuxer();
    void ReleaseVideoDecoderOnMuted();
    void CacheBuffer();
    void NotifyBufferEnd();
    void OnHwDecoderSwitch();
    void NotifySeekClosest(bool isSeekDone);
    PlayerErrorType GetPlayerErrorType(const Event& event);
    PlayerErrorType GetPlayerErrorTypeFromDemuxerFilter(const Event& event);
    PlayerErrorType GetPlayerErrorTypeFromAudioDecoder(const Event& event);
    PlayerErrorType GetPlayerErrorTypeFromDecoderSurfaceFilter(const Event& event);
    PlayerErrorType GetPlayerErrorTypeFromAudioSinkFilter(const Event& event);
    PlayerErrorType GetPlayerErrorTypeFromAudioServerSinkPlugin(const Event& event);
    PlayerErrorType GetPlayerErrorTypeFromEngine(const Event& event);
    bool IsPrepareStateValid() const;
    void MetricsUpdateDuration();
    void SetMediaKitReport(const std::string &apiCall);
    void ExtractStrategyParams(const AVPlayStrategy& strategy);
    void HandleReadyAudioInterrupt();
    void InitPcmCallback();
    bool IsNeedAudioSinkChangeTrack(std::shared_ptr<Meta> preMeta, std::shared_ptr<Meta> meta);
    bool HandleAudioDecoderChangeEvent(const Event& event);
    bool HandleAudioTrackChangeReportEvent(const Event& event);

    bool isNetWorkPlay_ = false;
    bool isDump_ = false;
    int32_t appUid_{0};
    int32_t appPid_{0};
    int32_t appTokenId_{0};
    int64_t appFullTokenId_{0};
    OHOS::Media::Mutex stateMutex_{};
    OHOS::Media::Mutex initialPlayingEventMutex_{};
    OHOS::Media::ConditionVariable cond_{};
    std::atomic<bool> renderFirstFrame_ {false};
    std::atomic<bool> singleLoop_ {false};
    std::atomic<bool> isSeek_ {false};
    std::atomic<bool> isSeekClosest_ {false};
    std::atomic<PlaybackRateMode> playbackRateMode_ {PlaybackRateMode::SPEED_FORWARD_1_00_X};
    std::atomic<float> playbackRate_ {1.0f};

    std::shared_ptr<EventReceiver> playerEventReceiver_;
    std::shared_ptr<FilterCallback> playerFilterCallback_;
    std::vector<std::weak_ptr<Meta>> streamMeta_{};
    std::atomic<PlayerStates> pipelineStates_ {PlayerStates::PLAYER_IDLE}; // only update in UpdateStateNoLock()
    std::queue<PlayerStates> pendingStates_ {};
    std::shared_ptr<OHOS::Media::Pipeline::Pipeline> pipeline_;
    std::shared_ptr<DemuxerFilter> demuxer_;
    std::shared_ptr<AudioDecoderFilter> audioDecoder_;
    std::shared_ptr<AudioSinkFilter> audioSink_;
    std::shared_ptr<SubtitleSinkFilter> subtitleSink_;
    std::shared_ptr<InterruptMonitor> interruptMonitor_;
#ifdef SUPPORT_VIDEO
    std::shared_ptr<DecoderSurfaceFilter> videoDecoder_;
    std::shared_ptr<SeiParserFilter> seiDecoder_;
#endif
    std::shared_ptr<MediaSyncManager> syncManager_;
    std::atomic<PlayerStateId> curState_;
    HiPlayerCallbackLooper callbackLooper_{};
    LiveController liveController_ {};
    std::weak_ptr<IPlayerEngineObs> playerEngineObs_{};
    sptr<Surface> surface_ {nullptr};
    sptr<Surface> sideOutputSurface_ {nullptr};
    std::string url_;
    std::string subUrl_;
    bool hasExtSub_ {false};
    std::atomic<int32_t> durationMs_{-1};
    std::atomic<int32_t> playWindowDurationMs_{-1};
    int64_t mediaStartPts_{0};
    std::shared_ptr<IMediaDataSource> dataSrc_{nullptr};
    std::shared_ptr<IMediaSourceLoader> sourceLoader_{nullptr};
    FileDescriptor fileDescriptor_ {};
    std::atomic<int32_t> videoWidth_{0};
    std::atomic<int32_t> videoHeight_{0};
    std::atomic<bool> needSwapWH_{false};
    std::atomic<bool> isInterruptNeeded_{false};
    bool isEnableStartFrameRateOpt_ {true};
    std::atomic<bool> isBufferingEnd_{false};

    std::shared_ptr<Meta> audioRenderInfo_{nullptr};
    std::shared_ptr<Meta> audioInterruptMode_{nullptr};
    std::shared_ptr<Meta> privacyType_{nullptr};
    int32_t audioPrivacyType_ = 0;
    int32_t volumeMode_ = 0;
    bool isStreaming_{false};

    int32_t rotation90 = 90;
    int32_t rotation270 = 270;

    std::shared_ptr<SeekAgent> seekAgent_;

    std::mutex drmMutex_;
    std::mutex flvLiveMutex_;
    std::mutex pipelineMutex_;
    std::condition_variable drmConfigCond_;
    std::condition_variable flvLiveCond_;
    bool isDrmProtected_ = false;
    bool isDrmPrepared_ = false;
    bool stopWaitingDrmConfig_ = false;
#ifdef SUPPORT_AVPLAYER_DRM
    sptr<DrmStandard::IMediaKeySessionService> keySessionServiceProxy_{nullptr};
#endif
    int32_t svpMode_ = HiplayerSvpMode::SVP_CLEAR;

    bool isInitialPlay_ = true;
    std::vector<std::pair<EventType, bool>> initialAVStates_;
    std::vector<std::pair<std::string, bool>> completeState_;
    std::mutex seekMutex_;
    std::string bundleName_ {};

    std::map<std::string, std::string> header_;
    uint32_t preferedWidth_ = 0;
    uint32_t preferedHeight_ = 0;
    uint32_t bufferDuration_ = 0;
    double bufferDurationForPlaying_ = 0;
    double maxLivingDelayTime_ = -1;
    bool isSetBufferDurationForPlaying_ {false};
    bool isFlvLive_ {false};
    bool preferHDR_ = false;
    std::atomic<bool> isAdsPlaying_ {false};

    OHOS::Media::MediaType mutedMediaType_ = OHOS::Media::MediaType::MEDIA_TYPE_MAX_COUNT;
    std::string audioLanguage_;
    std::string subtitleLanguage_;
    std::vector<AVPlayMediaStream> playMediaStreamVec_;

    std::string playerId_;
    std::string mimeType_;
    int32_t currentAudioTrackId_ = -1;
    int32_t defaultAudioTrackId_ = -1;
    int32_t currentVideoTrackId_ = -1;
    int32_t defaultVideoTrackId_ = -1;
    int32_t currentSubtitleTrackId_ = -1;
    int32_t defaultSubtitleTrackId_ = -1;
    PlayStatisticalInfo playStatisticalInfo_;
    std::atomic<int64_t> startTime_ = 0;
    int64_t maxSeekLatency_ = 0;
    int64_t maxAccurateSeekLatency_ = 0;
    uint64_t instanceId_ = 0;
    int32_t apiVersion_ = 0;
    int64_t maxSurfaceSwapLatency_ = 0;
    int64_t playTotalDuration_ = 0;
    bool inEosSeek_ = false;
    std::atomic<bool> isDoCompletedSeek_{false};
    OHOS::Media::Mutex stateChangeMutex_{};
    int64_t playRangeStartTime_ = -1;
    int64_t playRangeEndTime_ = -1;
    bool isSetPlayRange_ = false;
    int64_t startTimeWithMode_ = -1;
    int64_t endTimeWithMode_ = -1;
    PlayerSeekMode playRangeSeekMode_ = PlayerSeekMode::SEEK_PREVIOUS_SYNC;

    std::mutex seekContinousMutex_;
    std::atomic<int64_t> seekContinousBatchNo_ {-1};
    std::shared_ptr<DraggingPlayerAgent> draggingPlayerAgent_ {nullptr};
    int64_t lastSeekContinousPos_ {-1};
    bool inEosPlayingSeekContinuous_ = false;
    std::atomic<bool> needUpdateSubtitle_ {true};
    std::shared_ptr<DfxAgent> dfxAgent_{};
    bool maxAmplitudeCbStatus_ {false};
    OHOS::Media::Mutex handleCompleteMutex_{};
    int64_t playStartTime_ = 0;
    int64_t prepareDuration_ = 0;
    std::atomic<bool> isBufferingStartNotified_ {false};
    std::atomic<bool> needUpdateSei_ {true};
    bool seiMessageCbStatus_ {false};
    std::vector<int32_t> payloadTypes_{};
    bool isPerfRecEnabled_ { false };
    OHOS::Media::Mutex interruptMutex_{};
    bool isHintPauseReceived_ { false };
    std::atomic<bool> interruptNotifyPlay_ {false};
    std::atomic<bool> isSaveInterruptEventNeeded_ {true};
    OHOS::AudioStandard::InterruptEvent interruptEvent_ = OHOS::AudioStandard::InterruptEvent(
        OHOS::AudioStandard::INTERRUPT_TYPE_END,
        OHOS::AudioStandard::INTERRUPT_SHARE,
        OHOS::AudioStandard::INTERRUPT_HINT_RESUME);
    bool isCalledBySystemApp_ { false };

    std::atomic<bool> isOnlyAudio_ {false};

    // post processor
    static constexpr int32_t MAX_TARGET_WIDTH = 1920;
    static constexpr int32_t MAX_TARGET_HEIGHT = 1080;
    static constexpr int32_t MIN_TARGET_WIDTH = 320;
    static constexpr int32_t MIN_TARGET_HEIGHT = 320;
    static constexpr int32_t DEFAULT_SYNC_ID = 0;
    int32_t audioHapticsSyncId_ {DEFAULT_SYNC_ID};
    int32_t postProcessorTargetWidth_ = MAX_TARGET_WIDTH;
    int32_t postProcessorTargetHeight_ = MAX_TARGET_HEIGHT;
    VideoPostProcessorType videoPostProcessorType_ {VideoPostProcessorType::NONE};
    std::atomic<bool> isPostProcessorOn_ {false};
    // memory usage
    std::unordered_map<std::string, uint32_t> memoryUsageInfo_ {};
    std::mutex memoryReportMutex_;
    std::mutex fdMutex_ {};
    std::unique_ptr<FdsanFd> fdsanFd_ = nullptr;
    std::atomic<bool> enableCameraPostprocessing_ {false};
    bool isForzenSeekRecv_ = false;
    bool eosInLoopForFrozen_ = false;
    int64_t frozenSeekTime_ = 0;
    PlayerSeekMode frozenSeekMode_ = PlayerSeekMode::SEEK_NEXT_SYNC;
    bool isDownloadPaused_ = false;
    std::mutex freezeMutex_;
    bool isForceLoadVideo_ {false};
    bool keepDecodingOnMute_ = false;
    bool isVideoMuted_ = false;
    bool isNeedSwDecoder_ = false;
    bool notNotifyForSw_ = false;
    bool isReInitPostProcessor_ = false;
    bool isVideoDecoderInited_ = false;
    bool enable_ = false;
    AVPlayTrackSelectionFilter trackSelectionFilter_;
    std::atomic<bool> hasTrackSelectionFilter_ {false};
    PlayerDfxSourceType sourceType_ = PlayerDfxSourceType::DFX_SOURCE_TYPE_UNKNOWN;
    FileType fileType_ = FileType::UNKNOW;
    bool isLiveSeek_ = false;
    std::atomic<bool> isAudioInitialized_ {false};
    std::mutex pcmCallbackMutex_;
    std::shared_ptr<IPCMCallback> pcmCallback_ {};
    bool isPcmOutputEnable_ {false};
    bool isPcmProcessorEnable_ {false};
    int32_t maxProcessedPcmLen_ {0};
};
} // namespace Media
} // namespace OHOS
#endif // HI_PLAYER_IMPL_H
