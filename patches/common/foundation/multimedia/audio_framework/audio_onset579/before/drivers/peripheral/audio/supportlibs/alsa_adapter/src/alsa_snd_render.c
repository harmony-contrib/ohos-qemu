/*
 * Copyright (c) 2022 Huawei Device Co., Ltd.
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

#include <stdint.h>
#include "alsa_soundcard.h"
#include "alsa_snd_render.h"
#include "osal_time.h"

#define HDF_LOG_TAG HDF_AUDIO_HAL_RENDER

#define MAX_PERIOD_SIZE                (8 * 1024)
#define MIN_PERIOD_SIZE                (4 * 1024)
#define AUDIO_RENDER_RECOVER_DELAY     (10 * 1000)
#define POLL_EVENT_DEF false
#define AUDIO_BUFFER_TIME_DEF 500000
#define AUDIO_PERIOD_TIME_DEF 100000
#define AUDIO_PERIOD_TIME_RATIO 4
#define BIT_COUNT_OF_BYTE       8
#define PCM_WAIT_TIMEOUT_MS     100
#ifdef SUPPORT_ALSA_CHMAP
#define CHMAP_NAME_LENGHT_MAX      256

/* channel map list type */
#define CHANNEL_MAP_TYPE_FIXED    "FIXED"  /* fixed channel position */
#define CHANNEL_MAP_TYPE_VAR      "VAR"    /* freely swappable channel position */
#define CHANNEL_MAP_TYPE_PAIRED   "PAIRED" /* pair-wise swappable channel position */
#endif

static struct AlsaRender *g_alsaRenderList = NULL;
static void RegisterRenderImpl(struct AlsaRender *renderIns);

void RenderSetPriData(struct AlsaRender *renderIns, RenderPriData data)
{
    renderIns->priData = data;
}

RenderPriData RenderGetPriData(struct AlsaRender *renderIns)
{
    return renderIns->priData;
}

static int32_t CreateRenderIns(void)
{
    if (g_alsaRenderList == NULL) {
        g_alsaRenderList = (struct AlsaRender *)OsalMemCalloc(MAX_CARD_NUM * sizeof(struct AlsaRender));
        if (g_alsaRenderList == NULL) {
            AUDIO_FUNC_LOGE("Failed to allocate memory!");
            return HDF_FAILURE;
        }
    }
    return HDF_SUCCESS;
}

static int32_t RenderFreeMemory(void)
{
    if (g_alsaRenderList != NULL) {
        for (int32_t i = 0; i < MAX_CARD_NUM; i++) {
            if (g_alsaRenderList[i].soundCard.cardStatus != 0) {
                AUDIO_FUNC_LOGE("refCount is not zero, Sound card in use!");
                return HDF_ERR_DEVICE_BUSY;
            }

            if (g_alsaRenderList[i].priData != NULL) {
                OsalMemFree(g_alsaRenderList[i].priData);
                g_alsaRenderList[i].priData = NULL;
            }
        }
        AudioMemFree((void **)&g_alsaRenderList);
        g_alsaRenderList = NULL;
    }

    return HDF_SUCCESS;
}

static int32_t SetHWParamsSub(
    snd_pcm_t *handle, snd_pcm_hw_params_t *params, const struct AudioPcmHwParams *hwParams, snd_pcm_access_t access)
{
    snd_pcm_format_t pcmFormat = SND_PCM_FORMAT_S16_LE;
    CHECK_NULL_PTR_RETURN_DEFAULT(handle);
    CHECK_NULL_PTR_RETURN_DEFAULT(params);

    /* set hardware resampling,enable alsa-lib resampling */
    int32_t ret = snd_pcm_hw_params_set_rate_resample(handle, params, 1);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Resampling setup failed for playback: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }
    /* set the interleaved read/write format */
    ret = snd_pcm_hw_params_set_access(handle, params, access);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Access type not available for playback: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }
    ret = SndConverAlsaPcmFormat(hwParams, &pcmFormat);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("SndConverAlsaPcmFormat error.");
        return HDF_FAILURE;
    }
    /* set the sample format */
    ret = snd_pcm_hw_params_set_format(handle, params, pcmFormat);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Sample format not available for playback: %{public}s, format: %{public}d",
            snd_strerror(ret), pcmFormat);
        return HDF_FAILURE;
    }
    /* set the count of channels */
    ret = snd_pcm_hw_params_set_channels(handle, params, hwParams->channels);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Channels count (%{public}u) not available for playbacks: %{public}s", hwParams->channels,
            snd_strerror(ret));
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

static int32_t SetHWRate(snd_pcm_t *handle, snd_pcm_hw_params_t *params, uint32_t *rate)
{
    int dir = 0; /* dir Value range (-1,0,1) */
    CHECK_NULL_PTR_RETURN_DEFAULT(handle);
    CHECK_NULL_PTR_RETURN_DEFAULT(params);
    CHECK_NULL_PTR_RETURN_DEFAULT(rate);

    /* set the stream rate */
    uint32_t rRate = *rate;
    int32_t ret = snd_pcm_hw_params_set_rate_near(handle, params, &rRate, &dir);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Rate %{public}uHz not available for playback: %{public}s.", *rate, snd_strerror(ret));
        return HDF_FAILURE;
    }

    if (rRate != *rate) {
        ret = snd_pcm_hw_params_set_rate_near(handle, params, &rRate, &dir);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("Rate %{public}uHz not available for playback: %{public}s.", *rate, snd_strerror(ret));
            return HDF_FAILURE;
        }
    }
    /* Update to hardware supported rate */
    *rate = rRate;

    return HDF_SUCCESS;
}

static int32_t SetHWParams(struct AlsaSoundCard *cardIns, snd_pcm_access_t access)
{
    int dir = 0; /* dir Value range (-1,0,1) */
    snd_pcm_uframes_t size;
    snd_pcm_hw_params_t *hwParams = NULL;
    struct AlsaRender *renderIns = (struct AlsaRender*)cardIns;
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns->pcmHandle);

    snd_pcm_hw_params_alloca(&hwParams);
    if (snd_pcm_hw_params_any(cardIns->pcmHandle, hwParams) < 0) {
        AUDIO_FUNC_LOGE("No configurations available");
        return HDF_FAILURE;
    }
    if (SetHWParamsSub(cardIns->pcmHandle, hwParams, &cardIns->hwParams, access) != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("SetHWParamsSub failed!");
        return HDF_FAILURE;
    }
    if (SetHWRate(cardIns->pcmHandle, hwParams, &(cardIns->hwParams.rate)) != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("SetHWRate failed!");
        return HDF_FAILURE;
    }
    snd_pcm_hw_params_get_buffer_time_max(hwParams, &renderIns->bufferTime, &dir);
    if (renderIns->bufferTime > AUDIO_BUFFER_TIME_DEF) {
        renderIns->bufferTime = AUDIO_BUFFER_TIME_DEF;
    }
    renderIns->periodTime = renderIns->bufferTime / AUDIO_PERIOD_TIME_RATIO;
    if (snd_pcm_hw_params_set_buffer_time_near(cardIns->pcmHandle, hwParams, &renderIns->bufferTime, &dir) < 0) {
        AUDIO_FUNC_LOGE("Set buffer time %{public}u failed", renderIns->bufferTime);
        return HDF_FAILURE;
    }
    if (snd_pcm_hw_params_get_buffer_size(hwParams, &size) < 0) {
        AUDIO_FUNC_LOGE("Unable to get buffer size for playback");
        return HDF_FAILURE;
    }
    renderIns->bufferSize = size;
    if (snd_pcm_hw_params_set_period_time_near(cardIns->pcmHandle, hwParams, &renderIns->periodTime, &dir) < 0) {
        AUDIO_FUNC_LOGE("Set period time %{public}u failed", renderIns->bufferTime);
        return HDF_FAILURE;
    }
    if (snd_pcm_hw_params_get_period_size(hwParams, &size, &dir) < 0) {
        AUDIO_FUNC_LOGE("Unable to get period size for playback");
        return HDF_FAILURE;
    }
    renderIns->periodSize = size;
    if (snd_pcm_hw_params(cardIns->pcmHandle, hwParams) < 0) {
        AUDIO_FUNC_LOGE("Unable to set hw params for playback");
        return HDF_FAILURE;
    }

    cardIns->canPause = snd_pcm_hw_params_can_pause(hwParams);
    return HDF_SUCCESS;
}

static int32_t SetSWParams(struct AlsaSoundCard *cardIns)
{
    snd_pcm_sw_params_t *swParams = NULL;
    snd_pcm_t *handle = cardIns->pcmHandle;
    struct AlsaRender *renderIns = (struct AlsaRender *)cardIns;
    CHECK_NULL_PTR_RETURN_DEFAULT(handle);

    snd_pcm_sw_params_alloca(&swParams);

    /* get the current swparams */
    int32_t ret = snd_pcm_sw_params_current(handle, swParams);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Unable to determine current swparams for playback: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }
    /* start the transfer when the buffer is almost full: */
    /* (buffer_size / avail_min) * avail_min */
    if (renderIns->periodSize == 0) {
        AUDIO_FUNC_LOGE("g_periodSize=0");
        return HDF_FAILURE;
    }
    ret = snd_pcm_sw_params_set_start_threshold(handle, swParams,
        (renderIns->bufferSize / renderIns->periodSize) * renderIns->periodSize);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Unable to set start threshold mode for playback: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }
    /* allow the transfer when at least period_size samples can be processed */
    /* or disable this mechanism when period event is enabled (aka interrupt like style processing) */
    ret = snd_pcm_sw_params_set_avail_min(handle, swParams,
        renderIns->periodEvent ? renderIns->bufferSize : renderIns->periodSize);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Unable to set avail min for playback: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }

    /* enable period events when requested */
    if (renderIns->periodEvent) {
        int32_t val = 1; /* val 0 = disable period event, 1 = enable period event */
        ret = snd_pcm_sw_params_set_period_event(handle, swParams, val);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("Unable to set period event: %{public}s", snd_strerror(ret));
            return HDF_FAILURE;
        }
    }

    /* write the parameters to the playback device */
    ret = snd_pcm_sw_params(handle, swParams);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Unable to set sw params for playback: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

static int32_t ResetRenderParams(struct AlsaSoundCard *cardIns, snd_pcm_access_t access)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);

    int32_t ret = SetHWParams(cardIns, access);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Setting of hwparams failed.");
        return ret;
    }

    ret = SetSWParams(cardIns);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Setting of swparams failed.");
        return ret;
    }

    return HDF_SUCCESS;
}

static struct AlsaRender *GetRenderInsByName(const char *adapterName)
{
    struct AlsaRender *renderIns = NULL;
    struct AlsaSoundCard *alsaSnd = NULL;

    /*
    fine the instance with the corresponding adapter name, or create one if none.
    */
    for (int32_t i = 0; i < MAX_CARD_NUM; i++) {
        alsaSnd = (struct AlsaSoundCard *)&g_alsaRenderList[i];
        if (alsaSnd->cardStatus) {
            if (0 == strcmp(alsaSnd->adapterName, adapterName)) {
                return &g_alsaRenderList[i];
            }
        }
    }

    for (int32_t i = 0; i < MAX_CARD_NUM; i++) {
        renderIns = &g_alsaRenderList[i];
        alsaSnd = (struct AlsaSoundCard *)&g_alsaRenderList[i];
        if (alsaSnd->cardStatus == 0) {
            (void)memset_s(renderIns, sizeof(struct AlsaRender), 0, sizeof(struct AlsaRender));
            int32_t ret = strncpy_s(alsaSnd->adapterName, MAX_CARD_NAME_LEN + 1, adapterName, strlen(adapterName));
            if (ret != 0) {
                AUDIO_FUNC_LOGE("strncpy_s failed!");
                return NULL;
            }
            alsaSnd->cardStatus++;
            renderIns->periodEvent = POLL_EVENT_DEF;
            renderIns->periodTime = AUDIO_PERIOD_TIME_DEF;
            renderIns->bufferTime = AUDIO_BUFFER_TIME_DEF;
            renderIns->descPins = PIN_NONE;
            renderIns->resample = 1;
            return renderIns;
        }
    }
    AUDIO_FUNC_LOGE("Failed to AddCardIns!");
    return NULL;
}

struct AlsaRender *RenderCreateInstance(const char* adapterName, enum AudioCategory scene)
{
    struct AlsaRender *renderIns = NULL;
    int32_t dev;
    if (adapterName == NULL || strlen(adapterName) == 0) {
        AUDIO_FUNC_LOGE("Invalid adapterName!");
        return NULL;
    }

    if (scene < AUDIO_IN_MEDIA || scene > AUDIO_MMAP_NOIRQ) {
        scene = AUDIO_IN_MEDIA;
    }

    int32_t ret = CreateRenderIns();
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Failed to create render instance.");
        return NULL;
    }

    renderIns = GetRenderInsByName(adapterName);
    if (renderIns == NULL) {
        AUDIO_FUNC_LOGE("get render instance failed.");
        return NULL;
    }
    struct AlsaSoundCard *cardIns = (struct AlsaSoundCard *)renderIns;
    if (cardIns == NULL) {
        AUDIO_FUNC_LOGE("cardIns is NULL.");
        return NULL;
    }

    RegisterRenderImpl(renderIns);

    dev = RenderGetSceneDev(scene);
    AUDIO_FUNC_LOGI("RenderCreateInstance RenderGetSceneDev dev:%{public}d", dev);
    if (dev > MIXER_CTL_MAX_NUM || dev < -1) {
        dev = -1;
    }
    ret = SndSaveCardListInfo(SND_PCM_STREAM_PLAYBACK, dev);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Failed to save card device info.");
        return NULL;
    }

    ret = SndMatchSelAdapter(&renderIns->soundCard, adapterName);
    if (ret != HDF_SUCCESS) {
        SndCloseHandle(&renderIns->soundCard);
        RenderFreeMemory();
        return NULL;
    }

    RenderOverrideFunc(renderIns);
    return renderIns;
}

struct AlsaRender *RenderGetInstance(const char *adapterName)
{
    if (adapterName == NULL || strlen(adapterName) == 0) {
        AUDIO_FUNC_LOGE("Invalid adapterName!");
        return NULL;
    }

    if (g_alsaRenderList == NULL) {
        AUDIO_FUNC_LOGE("g_alsaRenderList is NULL!");
        return NULL;
    }

    for (int32_t i = 0; i < MAX_CARD_NUM; i++) {
        if (strcmp(g_alsaRenderList[i].soundCard.adapterName, adapterName) == 0) {
            return &(g_alsaRenderList[i]);
        }
    }

    return NULL;
}

#ifdef SUPPORT_ALSA_CHMAP
static int32_t GetChannelsNameFromUser(struct AlsaSoundCard *cardIns, const char *channelsName)
{
    if (channelsName == NULL) {
        AUDIO_FUNC_LOGE("channelsName is NULL!");
        return HDF_ERR_INVALID_PARAM;
    }

    if (cardIns->hwParams.channelsName == NULL) {
        cardIns->hwParams.channelsName = (char *)OsalMemCalloc(CHMAP_NAME_LENGHT_MAX);
        if (cardIns->hwParams.channelsName == NULL) {
            AUDIO_FUNC_LOGE("Failed to allocate memory!");
            return HDF_ERR_MALLOC_FAIL;
        }
    }

    (void)memset_s(cardIns->hwParams.channelsName, CHMAP_NAME_LENGHT_MAX, 0, CHMAP_NAME_LENGHT_MAX);
    int32_t ret = strncpy_s(cardIns->hwParams.channelsName, CHMAP_NAME_LENGHT_MAX - 1,
        channelsName, strlen(channelsName));
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("strncpy_s failed!");
        AudioMemFree((void **)&(cardIns->hwParams.channelsName));
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}
#endif

 static int32_t SaveHwParams(struct AlsaSoundCard *cardIns, const struct AudioHwRenderParam *handleData)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(handleData);

    cardIns->hwParams.streamType = AUDIO_RENDER_STREAM;
    cardIns->hwParams.channels = handleData->frameRenderMode.attrs.channelCount;
    cardIns->hwParams.rate = handleData->frameRenderMode.attrs.sampleRate;
    cardIns->hwParams.periodSize = handleData->frameRenderMode.periodSize;
    cardIns->hwParams.periodCount = handleData->frameRenderMode.periodCount;
    cardIns->hwParams.format = handleData->frameRenderMode.attrs.format;
    cardIns->hwParams.period = handleData->frameRenderMode.attrs.period;
    cardIns->hwParams.frameSize = handleData->frameRenderMode.attrs.frameSize;
    cardIns->hwParams.isBigEndian = handleData->frameRenderMode.attrs.isBigEndian;
    cardIns->hwParams.isSignedData = handleData->frameRenderMode.attrs.isSignedData;
    cardIns->hwParams.startThreshold = handleData->frameRenderMode.attrs.startThreshold;
    cardIns->hwParams.stopThreshold = handleData->frameRenderMode.attrs.stopThreshold;
    cardIns->hwParams.silenceThreshold = handleData->frameRenderMode.attrs.silenceThreshold;
#ifdef SUPPORT_ALSA_CHMAP
    /* param 2 by handleData->frameRenderMode.attrs.channelsName, sample channelsName is "FL, FR" */
    if (GetChannelsNameFromUser(cardIns, "FL, FR") != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("GetChannelsNameFromUser failed");
        return HDF_FAILURE;
    }
#endif

    return HDF_SUCCESS;
}

#ifdef SUPPORT_ALSA_CHMAP
static void PrintChannels(const snd_pcm_chmap_t *map)
{
    char tmp[CHMAP_NAME_LENGHT_MAX] = {0};
    if (snd_pcm_chmap_print(map, sizeof(tmp), tmp) > 0) {
        HDF_LOGI("print_channels: %{public}s.", tmp);
    }
}

static int32_t QueryChmaps(snd_pcm_t *pcm)
{
    snd_pcm_chmap_query_t **pChmap = NULL;
    snd_pcm_chmap_query_t *chmap = NULL;
    const char *champType = NULL;
    snd_pcm_chmap_query_t **hwChmap = snd_pcm_query_chmaps(pcm);
    if (hwChmap == NULL) {
        AUDIO_FUNC_LOGE("This sound card has no chmap component, cannot query maps.");
        return HDF_FAILURE;
    }

    for (pChmap = hwChmap; (chmap = *pChmap) != NULL; pChmap++) {
        champType = snd_pcm_chmap_type_name(chmap->type);
        HDF_LOGI("Channel Type = %{public}s, Channels = %{public}d.", champType, chmap->map.channels);
        if (strncmp(champType, CHANNEL_MAP_TYPE_FIXED, strlen(CHANNEL_MAP_TYPE_FIXED)) == 0) {
            HDF_LOGW("Fixed channel type does not support modification temporarily!");
        }
        PrintChannels(&chmap->map);
    }

    snd_pcm_free_chmaps(hwChmap);
    return HDF_SUCCESS;
}

static int32_t SetChmap(snd_pcm_t *pcm, struct AudioPcmHwParams *hwRenderParams)
{
    if (hwRenderParams == NULL || hwRenderParams->channelsName == NULL) {
        AUDIO_FUNC_LOGE("Parameter is NULL!");
        return HDF_FAILURE;
    }

    snd_pcm_chmap_t *chmap = snd_pcm_chmap_parse_string(hwRenderParams->channelsName);
    if (chmap == NULL) {
        AUDIO_FUNC_LOGE("parse chmap error!");
        return HDF_FAILURE;
    }

    if (snd_pcm_set_chmap(pcm, chmap) < 0) {
        AUDIO_FUNC_LOGE("Cannot set chmap!");
        free((void *)chmap);
        return HDF_ERR_NOT_SUPPORT;
    }
    free((void *)chmap);

    chmap = snd_pcm_get_chmap(pcm);
    if (chmap == NULL) {
        AUDIO_FUNC_LOGE("Cannot get chmap!");
        return HDF_ERR_NOT_SUPPORT;
    }

    PrintChannels(chmap);
    free((void *)chmap);
    return HDF_SUCCESS;
}

static int32_t RenderHwParamsChmaps(struct AlsaSoundCard *cardIns)
{
    if (QueryChmaps(cardIns->pcmHandle) != HDF_SUCCESS) {
        AUDIO_FUNC_LOGW("QueryChmaps failed.");
        return HDF_SUCCESS;
    }
    if (SetChmap(cardIns->pcmHandle, &cardIns->hwParams) != HDF_SUCCESS) {
        AUDIO_FUNC_LOGW("SetChmap failed.");
    }

    return HDF_SUCCESS;
}
#endif

static int32_t RenderSetParams(struct AlsaRender *renderIns, const struct AudioHwRenderParam *handleData)
{
    struct AlsaSoundCard *cardIns = (struct AlsaSoundCard *)renderIns;
    CHECK_NULL_PTR_RETURN_DEFAULT(renderIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(handleData);

    SaveHwParams(&renderIns->soundCard, handleData);
    int32_t ret = SetHWParams(cardIns, SND_PCM_ACCESS_RW_INTERLEAVED);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Setting of hwparams failed.");
        return HDF_FAILURE;
    }

    ret = SetSWParams(cardIns);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Setting of swparams failed.");
        return HDF_FAILURE;
    }

#ifdef SUPPORT_ALSA_CHMAP
    ret = RenderHwParamsChmaps(&renderIns->soundCard);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Setting of chmaps failed.");
    }
#endif
    snd_pcm_format_t fmt;
    SndConverAlsaPcmFormat(&cardIns->hwParams, &fmt);
    int bitsPerSample = snd_pcm_format_physical_width(fmt);
    cardIns->hwParams.bitsPerFrame = bitsPerSample * cardIns->hwParams.channels;

    return HDF_SUCCESS;
}

static int32_t RenderWritei(snd_pcm_t *pcm, const struct AudioHwRenderParam *handleData,
    const struct AudioPcmHwParams *hwParams, uint64_t *acceptedBytes)
{
    if (acceptedBytes == NULL) {
        return HDF_FAILURE;
    }
    *acceptedBytes = 0;
    if (pcm == NULL || handleData == NULL || hwParams == NULL || hwParams->bitsPerFrame <= 0 ||
        hwParams->bitsPerFrame % BIT_COUNT_OF_BYTE != 0) {
        return HDF_FAILURE;
    }
    uint64_t frameBytes = (uint64_t)hwParams->bitsPerFrame / BIT_COUNT_OF_BYTE;
    uint64_t requestedFrames = handleData->frameRenderMode.bufferFrameSize;
    uint64_t requestedBytes = handleData->frameRenderMode.bufferSize;
    if (requestedFrames > SIZE_MAX / frameBytes || requestedFrames * frameBytes != requestedBytes ||
        (requestedBytes != 0 && handleData->frameRenderMode.buffer == NULL)) {
        return HDF_FAILURE;
    }
    if (requestedFrames == 0) {
        return HDF_SUCCESS;
    }

    snd_pcm_state_t state = snd_pcm_state(pcm);
    if (state == SND_PCM_STATE_SETUP) {
        int32_t ret = snd_pcm_prepare(pcm);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("snd_pcm_prepare fail: %{public}s", snd_strerror(ret));
            return HDF_FAILURE;
        }
    }

    size_t remaining = (size_t)requestedFrames;
    char *dataBuf = handleData->frameRenderMode.buffer;
    int32_t tryNum = AUDIO_ALSALIB_RETYR;
    while (remaining > 0) {
        snd_pcm_sframes_t frames = snd_pcm_writei(pcm, dataBuf, remaining);
        if (frames > 0) {
            if ((uint64_t)frames > remaining) {
                AUDIO_FUNC_LOGE("snd_pcm_writei returned more frames than requested");
                return HDF_FAILURE;
            }
            size_t bytes = (size_t)frames * (size_t)frameBytes;
            *acceptedBytes += (uint64_t)bytes;
            remaining -= (size_t)frames;
            dataBuf += bytes;
            continue;
        }
        if (frames == 0) {
            AUDIO_FUNC_LOGE("snd_pcm_writei made no progress");
            return ALSA_RENDER_WRITE_RETRYABLE;
        }
        if (frames == -EBADFD) {
            AUDIO_FUNC_LOGE("render PCM is not in the right state: %{public}s", snd_strerror(frames));
            (void)snd_pcm_prepare(pcm);
            return HDF_FAILURE;
        }
        if (frames == -EAGAIN) {
            if (snd_pcm_wait(pcm, PCM_WAIT_TIMEOUT_MS) < 0) {
                return HDF_FAILURE;
            }
        } else {
            int32_t ret = snd_pcm_recover(pcm, (int)frames, 0);
            if (ret < 0) {
                AUDIO_FUNC_LOGE("snd_pcm_writei recovery failed: %{public}s", snd_strerror(ret));
                return HDF_FAILURE;
            }
        }
        if (--tryNum == 0) {
            AUDIO_FUNC_LOGE("snd_pcm_writei retry budget exhausted");
            return frames == -EAGAIN ? ALSA_RENDER_WRITE_RETRYABLE : HDF_FAILURE;
        }
    }
    return HDF_SUCCESS;
}

static int32_t RenderWriteiMmap(struct AlsaSoundCard *cardIns, const struct AudioHwRenderParam *handleData)
{
    uint32_t looper = 0;
    int32_t count = 0;
    struct AudioMmapBufferDescriptor *mmapBufDesc = NULL;
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(handleData);

    cardIns->mmapFlag = false;
    int32_t ret = ResetRenderParams(cardIns, SND_PCM_ACCESS_MMAP_INTERLEAVED);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("AudioSetParamsMmap failed!");
        return HDF_FAILURE;
    }

    uint32_t frameSize = cardIns->hwParams.channels * cardIns->hwParams.format;
    if (frameSize == 0) {
        AUDIO_FUNC_LOGE("frame size = 0!");
        return HDF_FAILURE;
    }
    mmapBufDesc = (struct AudioMmapBufferDescriptor *)&(handleData->frameRenderMode.mmapBufDesc);
    uint32_t totalSize = (uint32_t)mmapBufDesc->totalBufferFrames * frameSize;
    uint32_t lastBuffSize = ((totalSize % MIN_PERIOD_SIZE) == 0) ? MIN_PERIOD_SIZE : (totalSize % MIN_PERIOD_SIZE);
    uint32_t loopTimes = (lastBuffSize == MIN_PERIOD_SIZE) ?
        (totalSize / MIN_PERIOD_SIZE) : (totalSize / MIN_PERIOD_SIZE + 1);
    while (looper < loopTimes) {
        uint32_t copyLen = (looper < (loopTimes - 1)) ? MIN_PERIOD_SIZE : lastBuffSize;
        snd_pcm_uframes_t frames = (snd_pcm_uframes_t)(copyLen / frameSize);
        ret = snd_pcm_mmap_writei(
            cardIns->pcmHandle, (char *)mmapBufDesc->memoryAddress + mmapBufDesc->offset, frames);
        if (ret == -EAGAIN) {
            count++;
            if (count > AUDIO_ALSALIB_MMAP_MAX) {
                AUDIO_FUNC_LOGE("loop > max !");
                return HDF_FAILURE;
            }
            continue;
        }
        count = 0;
        if (ret < 0) {
            AUDIO_FUNC_LOGE("Write error: %{public}s\n", snd_strerror(ret));
            return HDF_FAILURE;
        }
        looper++;
        mmapBufDesc->offset += copyLen;
        cardIns->mmapFrames += (uint64_t)frames;
    }

    return HDF_SUCCESS;
}

static int32_t RenderOpenImpl(struct AlsaRender *renderIns)
{
    struct AlsaSoundCard *cardIns = (struct AlsaSoundCard *)renderIns;
    CHECK_NULL_PTR_RETURN_DEFAULT(renderIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);

    if (SndisBusy(&renderIns->soundCard)) {
        AUDIO_FUNC_LOGE("Resource busy!!");
        return HDF_ERR_DEVICE_BUSY;
    }

    int32_t ret = snd_pcm_open(&cardIns->pcmHandle, cardIns->devName,
        SND_PCM_STREAM_PLAYBACK, SND_PCM_NONBLOCK);
    AUDIO_FUNC_LOGI("snd_pcm_open devName: %{public}s!", cardIns->devName);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_pcm_open fail: %{public}s!", snd_strerror(ret));
        RenderFreeMemory();
        return HDF_FAILURE;
    }

    ret = snd_pcm_nonblock(cardIns->pcmHandle, 1);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_pcm_nonblock fail: %{public}s!", snd_strerror(ret));
        SndCloseHandle(&renderIns->soundCard);
        RenderFreeMemory();
        return HDF_FAILURE;
    }

    ret = SndOpenMixer(&renderIns->soundCard);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("SndOpenMixer failed");
        SndCloseHandle(&renderIns->soundCard);
        RenderFreeMemory();
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

static int32_t RenderCloseImpl(struct AlsaRender *renderIns)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(renderIns);
#ifdef SUPPORT_ALSA_CHMAP
    AudioMemFree((void **)&renderIns->soundCard.hwParams.channelsName);
#endif
    SndCloseHandle(&renderIns->soundCard);
    RenderFreeMemory();
    return HDF_SUCCESS;
}

static int32_t RenderWriteAcceptedDefault(struct AlsaRender *renderIns,
    const struct AudioHwRenderParam *handleData, uint64_t *acceptedBytes)
{
    struct AlsaSoundCard *cardIns = (struct AlsaSoundCard *)renderIns;
    if (cardIns->pauseState) {
        AUDIO_FUNC_LOGE("Currently in pause, please check!");
        return HDF_FAILURE;
    }
    if (!cardIns->mmapFlag) {
        int32_t ret = ResetRenderParams(cardIns, SND_PCM_ACCESS_RW_INTERLEAVED);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("ResetRenderParams failed!");
            return HDF_FAILURE;
        }
        cardIns->mmapFlag = true;
    }
    return RenderWritei(cardIns->pcmHandle, handleData, &cardIns->hwParams, acceptedBytes);
}

int32_t RenderWriteImpl(struct AlsaRender *renderIns, const struct AudioHwRenderParam *handleData)
{
    uint64_t acceptedBytes = 0;
    if (renderIns == NULL || handleData == NULL) {
        return HDF_FAILURE;
    }
    int32_t ret = RenderWriteAcceptedDefault(renderIns, handleData, &acceptedBytes);
    return ret == HDF_SUCCESS ? HDF_SUCCESS : HDF_FAILURE;
}

int32_t RenderWriteAccepted(struct AlsaRender *renderIns, const struct AudioHwRenderParam *handleData,
    uint64_t *acceptedBytes)
{
    if (acceptedBytes == NULL) {
        return HDF_FAILURE;
    }
    *acceptedBytes = 0;
    if (renderIns == NULL || handleData == NULL || renderIns->Write == NULL) {
        return HDF_FAILURE;
    }
    if (renderIns->Write == RenderWriteImpl) {
        return RenderWriteAcceptedDefault(renderIns, handleData, acceptedBytes);
    }
    /* Preserve the pre-existing all-or-error contract of a vendor Write override.
     * This compatibility branch is not a raw ALSA writei observation. */
    int32_t ret = renderIns->Write(renderIns, handleData);
    if (ret == HDF_SUCCESS) {
        *acceptedBytes = handleData->frameRenderMode.bufferSize;
    }
    return ret == HDF_SUCCESS ? HDF_SUCCESS : HDF_FAILURE;
}

int32_t RenderGetMmapPositionImpl(struct AlsaRender *renderIns)
{
    return renderIns->soundCard.mmapFrames;
}

int32_t RenderMmapWriteImpl(struct AlsaRender *renderIns, const struct AudioHwRenderParam *handleData)
{
    struct AlsaSoundCard *cardIns = (struct AlsaSoundCard *)renderIns;
    CHECK_NULL_PTR_RETURN_DEFAULT(renderIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(handleData);

    if (cardIns->pauseState) {
        AUDIO_FUNC_LOGE("Currently in pause, please check!");
        return HDF_FAILURE;
    }

    cardIns->mmapFlag = false;
    int32_t ret = ResetRenderParams(cardIns, SND_PCM_ACCESS_MMAP_INTERLEAVED);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("ResetRenderParams failed!");
        return HDF_FAILURE;
    }

    ret = RenderWriteiMmap(cardIns, handleData);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("RenderWriteiMmap error!");
        return HDF_FAILURE;
    }
    return HDF_SUCCESS;
}

static int32_t RenderInitImpl(struct AlsaRender* renderIns)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderSelectSceneImpl(struct AlsaRender *renderIns,
    const struct AudioHwRenderParam *handleData)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderStartImpl(struct AlsaRender *renderIns,
    const struct AudioHwRenderParam *handleData)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderStopImpl(struct AlsaRender *renderIns)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderGetVolThresholdImpl(struct AlsaRender *renderIns, long *volMin, long *volMax)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderGetVolumeImpl(struct AlsaRender *renderIns, long *volume)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderSetVolumeImpl(struct AlsaRender *renderIns, long volume)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderGetGainThresholdImpl(struct AlsaRender *renderIns, float *gainMin, float *gainMax)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderGetGainImpl(struct AlsaRender *renderIns, float *volume)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderSetGainImpl(struct AlsaRender *renderIns, float volume)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static bool RenderGetMuteImpl(struct AlsaRender *renderIns)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return false;
}

static int32_t RenderSetMuteImpl(struct AlsaRender *renderIns, bool muteFlag)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderSetPauseStateImpl(struct AlsaRender *renderIns, bool pauseFlag)
{
    int enable = pauseFlag ? AUDIO_ALSALIB_IOCTRL_PAUSE : AUDIO_ALSALIB_IOCTRL_RESUME;
    struct AlsaSoundCard *cardIns = (struct AlsaSoundCard *)renderIns;
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns->pcmHandle);

    if (cardIns->canPause) {
        int32_t ret = snd_pcm_pause(cardIns->pcmHandle, enable);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("snd_pcm_pause failed!");
            return HDF_FAILURE;
        }
    } else {
        if (enable == AUDIO_ALSALIB_IOCTRL_PAUSE) {
            snd_pcm_drain(cardIns->pcmHandle);
        } else {
            snd_pcm_prepare(cardIns->pcmHandle);
        }
    }
    cardIns->pauseState = pauseFlag;

    return HDF_SUCCESS;
}

static int32_t RenderGetChannelModeImpl(struct AlsaRender *renderIns, enum AudioChannelMode *mode)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderSetChannelModeImpl(struct AlsaRender *renderIns, enum AudioChannelMode mode)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderSetHwParamsImpl(struct AlsaRender *renderIns, const struct AudioHwRenderParam *handleData)
{
    int32_t ret;
    CHECK_NULL_PTR_RETURN_DEFAULT(renderIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(handleData);
    ret = RenderSetParams(renderIns, handleData);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Render set parameters failed!");
        return HDF_FAILURE;
    }
    return HDF_SUCCESS;
}

static int32_t RenderSetTurningImpl()
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderReadFromVoiceImpl(struct AlsaRender *renderIns, const char *adapterName)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderCloseVoiceImpl(struct AlsaRender *renderIns)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderSetVoiceVolumeImpl(struct AlsaRender *renderIns, float volume)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t RenderUpdateRouterImpl(struct AlsaRender *renderIns, const struct AudioHwRenderParam *handleData)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static void RegisterRenderImpl(struct AlsaRender *renderIns)
{
    if (renderIns == NULL) {
        AUDIO_FUNC_LOGE("renderIns is NULL!");
        return;
    }

    renderIns->Init = RenderInitImpl;
    renderIns->Open = RenderOpenImpl;
    renderIns->SelectScene = RenderSelectSceneImpl;
    renderIns->Start = RenderStartImpl;
    renderIns->Stop = RenderStopImpl;
    renderIns->Close = RenderCloseImpl;
    renderIns->Write = RenderWriteImpl;
    renderIns->MmapWrite = RenderMmapWriteImpl;
    renderIns->GetMmapPosition = RenderGetMmapPositionImpl;
    renderIns->GetVolThreshold = RenderGetVolThresholdImpl;
    renderIns->GetVolume = RenderGetVolumeImpl;
    renderIns->SetVolume = RenderSetVolumeImpl;
    renderIns->GetGainThreshold = RenderGetGainThresholdImpl;
    renderIns->GetGain = RenderGetGainImpl;
    renderIns->SetGain = RenderSetGainImpl;
    renderIns->GetMute = RenderGetMuteImpl;
    renderIns->SetMute = RenderSetMuteImpl;
    renderIns->SetPauseState = RenderSetPauseStateImpl;
    renderIns->GetChannelMode = RenderGetChannelModeImpl;
    renderIns->SetChannelMode = RenderSetChannelModeImpl;

    renderIns->SetParams = RenderSetHwParamsImpl;
    renderIns->SetTurning = RenderSetTurningImpl;
    renderIns->ReadFromVoice = RenderReadFromVoiceImpl;
    renderIns->CloseVoice = RenderCloseVoiceImpl;
    renderIns->SetVoiceVolume = RenderSetVoiceVolumeImpl;
    renderIns->UpdateRouter = RenderUpdateRouterImpl;
}

