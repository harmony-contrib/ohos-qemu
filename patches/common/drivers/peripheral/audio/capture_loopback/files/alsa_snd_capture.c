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

#include "alsa_soundcard.h"
#include "alsa_snd_capture.h"

#define HDF_LOG_TAG HDF_AUDIO_HAL_CAPTURE

#define AUDIO_TIMESTAMP_FREQ 8 /* Hz */
#define AUDIO_SAMPLE_FREQ    48000
#define AUDIO_PERIOD         ((AUDIO_SAMPLE_FREQ) / (AUDIO_TIMESTAMP_FREQ))
#define AUDIO_PCM_WAIT       100
#define AUDIO_RESUME_POLL    (10 * (AUDIO_PCM_WAIT)) // 1s
#define ALSA_CAP_BUFFER_SIZE (2 * 2 * 6000)        // format(S16LE) * channels(2) * period.

#define POLL_EVENT_DEF false
#define AUDIO_BUFFER_TIME_DEF 500000
#define AUDIO_PERIOD_TIME_DEF 100000
#define PCM_WAIT_TIME         5000

static struct AlsaCapture *g_alsaCaptureList = NULL;
static void RegisterCaptureImpl(struct AlsaCapture *captureIns);

void  CaptureSetPriData(struct AlsaCapture *captureIns, CapturePriData data)
{
    captureIns->priData = data;
}

CapturePriData CaptureGetPriData(struct AlsaCapture *captureIns)
{
    return captureIns->priData;
}

static int32_t CaptureFreeMemory(void)
{
    if (g_alsaCaptureList != NULL) {
        for (int32_t i = 0; i < MAX_CARD_NUM; i++) {
            if (g_alsaCaptureList[i].soundCard.cardStatus != 0) {
                AUDIO_FUNC_LOGE("refCount is not zero, Sound card in use!");
                return HDF_ERR_DEVICE_BUSY;
            }
            if (g_alsaCaptureList[i].priData != NULL) {
                OsalMemFree(g_alsaCaptureList[i].priData);
                g_alsaCaptureList[i].priData = NULL;
            }
        }
        AudioMemFree((void **)&g_alsaCaptureList);
        g_alsaCaptureList = NULL;
    }

    return HDF_SUCCESS;
}

static int32_t SetHWParamsSub(
    struct AlsaSoundCard *cardIns, snd_pcm_hw_params_t *params, snd_pcm_access_t access)
{
    snd_pcm_format_t pcmFormat;
    snd_pcm_t *handle = cardIns->pcmHandle;
    struct AlsaCapture *captureIns = (struct AlsaCapture *)cardIns;
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(params);

    int32_t ret = snd_pcm_hw_params_set_rate_resample(handle, params, captureIns->resample);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Resampling setup failed for capture: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }

    /* set the interleaved read/write format */
    ret = snd_pcm_hw_params_set_access(handle, params, access);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Access type not available for capture: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }
    ret = SndConverAlsaPcmFormat(&cardIns->hwParams, &pcmFormat);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("SndConverAlsaPcmFormat error.");
        return ret;
    }

    /* set the sample format */
    ret = snd_pcm_hw_params_set_format(handle, params, pcmFormat);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Sample format not available for capture: %{public}s", snd_strerror(ret));
        return HDF_ERR_NOT_SUPPORT;
    }

    /* set the count of channels */
    ret = snd_pcm_hw_params_set_channels(handle, params, cardIns->hwParams.channels);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Channels count (%{public}u) not available for capture: %{public}s", cardIns->hwParams.channels,
            snd_strerror(ret));
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

static int32_t SetHWRate(struct AlsaSoundCard *cardIns, snd_pcm_hw_params_t *params)
{
    int32_t dir = 0; /* dir Value range (-1,0,1) */
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(params);

    /* set the stream rate */
    uint32_t rRate = cardIns->hwParams.rate;
    int32_t ret = snd_pcm_hw_params_set_rate_near(cardIns->pcmHandle, params, &rRate, &dir);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Rate %{public}uHz not available for capture: %{public}s",
            cardIns->hwParams.rate, snd_strerror(ret));
        return HDF_FAILURE;
    }

    if (rRate != cardIns->hwParams.rate) {
        ret = snd_pcm_hw_params_set_rate_near(cardIns->pcmHandle, params, &rRate, &dir);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("Rate %{public}uHz not available for capture: %{public}s",
                cardIns->hwParams.rate, snd_strerror(ret));
            return HDF_FAILURE;
        }
    }
    /* Update to hardware supported rate */
    cardIns->hwParams.rate = rRate;

    return HDF_SUCCESS;
}

static int32_t SetHWBuffer(struct AlsaSoundCard *cardIns, snd_pcm_hw_params_t *params)
{
    int32_t dir = 0; /* dir Value range (-1,0,1) */
    snd_pcm_uframes_t size = 0;
    struct AlsaCapture *captureIns = (struct AlsaCapture *)cardIns;
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(params);

    int32_t ret = snd_pcm_hw_params_set_buffer_time_near(cardIns->pcmHandle, params, &captureIns->bufferTime, &dir);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Unable to set buffer time %{public}u for capture: %{public}s",
            captureIns->bufferTime, snd_strerror(ret));
        return HDF_FAILURE;
    }

    ret = snd_pcm_hw_params_get_buffer_size(params, &size);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Unable to get buffer size for capture: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }
    captureIns->bufferSize = size;

    return HDF_SUCCESS;
}

static int32_t SetHWPeriod(struct AlsaSoundCard *cardIns, snd_pcm_hw_params_t *params)
{
    int32_t dir = 0; /* dir Value range (-1,0,1) */
    snd_pcm_uframes_t size = 0;
    struct AlsaCapture *captureIns = (struct AlsaCapture*)cardIns;
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(params);

    int32_t ret = snd_pcm_hw_params_set_period_time_near(cardIns->pcmHandle, params, &captureIns->periodTime, &dir);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Unable to set period time %{public}u for capture: %{public}s",
            captureIns->periodTime, snd_strerror(ret));
        return HDF_FAILURE;
    }

    ret = snd_pcm_hw_params_get_period_size(params, &size, &dir);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Unable to get period size for capture: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }
    captureIns->periodSize = size;

    return HDF_SUCCESS;
}

static int32_t SetHWParams(struct AlsaSoundCard *cardIns, snd_pcm_access_t access)
{
    snd_pcm_hw_params_t *hwParams = NULL;
    snd_pcm_t *handle = cardIns->pcmHandle;
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(handle);

    snd_pcm_hw_params_alloca(&hwParams);
    int32_t ret = snd_pcm_hw_params_any(handle, hwParams); // choose all parameters
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Broken configuration for capture: no configurations available: %{public}s.",
            snd_strerror(ret));
        return HDF_FAILURE;
    }

    ret = SetHWParamsSub(cardIns, hwParams, access);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("SetHWParamsSub failed!");
        return ret;
    }

    ret = SetHWRate(cardIns, hwParams);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("SetHWRate failed!");
        return ret;
    }

    ret = SetHWBuffer(cardIns, hwParams);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("SetHWBuffer failed!");
        return ret;
    }

    ret = SetHWPeriod(cardIns, hwParams);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("SetHWPeriod failed!");
        return ret;
    }

    /* write the parameters to device. */
    ret = snd_pcm_hw_params(handle, hwParams);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Unable to set hw params for capture: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }

    cardIns->canPause = snd_pcm_hw_params_can_pause(hwParams);
    AUDIO_FUNC_LOGI("hardware driver %{public}s support pause", cardIns->canPause ? "is" : "is not");

    return HDF_SUCCESS;
}

static int32_t SetSWParams(struct AlsaSoundCard *cardIns)
{
    /* The time when the application starts reading data */ 
    snd_pcm_sframes_t startThresholdSize = 1; 
    snd_pcm_sw_params_t *swParams = NULL;
    snd_pcm_t *handle = cardIns->pcmHandle;
    struct AlsaCapture *captureIns = (struct AlsaCapture *)cardIns;
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(handle);

    snd_pcm_sw_params_alloca(&swParams);
    /* get the current swparams */
    int32_t ret = snd_pcm_sw_params_current(handle, swParams);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Unable to determine current swparams for capture: %{public}s.", snd_strerror(ret));
        return HDF_FAILURE;
    }
    if (captureIns->periodSize == 0) {
        AUDIO_FUNC_LOGE("error: g_periodSize cannot be zero!");
        return HDF_FAILURE;
    }
    /* start the transfer when the buffer is 1 frames */
    ret = snd_pcm_sw_params_set_start_threshold(handle, swParams, startThresholdSize);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Unable to set start threshold mode for capture: %{public}s.", snd_strerror(ret));
        return HDF_FAILURE;
    }

    /* allow the transfer when at least period_size samples can be processed */
    /* or disable this mechanism when period event is enabled (aka interrupt like style processing) */
    ret = snd_pcm_sw_params_set_avail_min(handle, swParams,
        captureIns->periodEvent ? captureIns->bufferSize : captureIns->periodSize);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Unable to set avail min for capture: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }

    /* enable period events when requested */
    if (captureIns->periodEvent) {
        ret = snd_pcm_sw_params_set_period_event(handle, swParams, 1);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("Unable to set period event: %{public}s", snd_strerror(ret));
            return HDF_FAILURE;
        }
    }
    /* write the parameters to the capture device */
    ret = snd_pcm_sw_params(handle, swParams);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Unable to set sw params for capture: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

static int32_t ResetCaptureParams(struct AlsaSoundCard *cardIns, snd_pcm_access_t access)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns->pcmHandle);

    int32_t ret = SetHWParams(cardIns, access);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Setting of hwparams failed: %{public}d.", ret);
        return ret;
    }

    ret = SetSWParams(cardIns);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Setting of swparams failed: %{public}d.", ret);
        return ret;
    }

    return HDF_SUCCESS;
}

static int32_t UpdateSetParams(struct AlsaSoundCard *cardIns)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns->pcmHandle);

    cardIns->mmapFlag = false;
    int32_t ret = ResetCaptureParams(cardIns, SND_PCM_ACCESS_MMAP_INTERLEAVED);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("AudioSetParamsMmap failed!");
        return ret;
    }

    ret = snd_pcm_start(cardIns->pcmHandle);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_pcm_start fail. %{public}s.", snd_strerror(ret));
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

static int32_t SaveHwParams(struct AlsaSoundCard *cardIns, const struct AudioHwCaptureParam *handleData)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(handleData);

    cardIns->hwParams.streamType = AUDIO_CAPTURE_STREAM;
    cardIns->hwParams.channels = handleData->frameCaptureMode.attrs.channelCount;
    cardIns->hwParams.rate = handleData->frameCaptureMode.attrs.sampleRate;
    cardIns->hwParams.periodSize = handleData->frameCaptureMode.periodSize;
    cardIns->hwParams.periodCount = handleData->frameCaptureMode.periodCount;
    cardIns->hwParams.format = handleData->frameCaptureMode.attrs.format;
    cardIns->hwParams.period = handleData->frameCaptureMode.attrs.period;
    cardIns->hwParams.frameSize = handleData->frameCaptureMode.attrs.frameSize;
    cardIns->hwParams.isBigEndian = handleData->frameCaptureMode.attrs.isBigEndian;
    cardIns->hwParams.isSignedData = handleData->frameCaptureMode.attrs.isSignedData;
    cardIns->hwParams.startThreshold = handleData->frameCaptureMode.attrs.startThreshold;
    cardIns->hwParams.stopThreshold = handleData->frameCaptureMode.attrs.stopThreshold;
    cardIns->hwParams.silenceThreshold = handleData->frameCaptureMode.attrs.silenceThreshold;

    return HDF_SUCCESS;
}

static int32_t CaptureSetParams(struct AlsaCapture *captureIns, const struct AudioHwCaptureParam *handleData)
{
    struct AlsaSoundCard *cardIns = (struct AlsaSoundCard *)captureIns;
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(handleData);

    SaveHwParams(cardIns, handleData);
    int32_t ret = SetHWParams(cardIns, SND_PCM_ACCESS_RW_INTERLEAVED);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Setting of hwparams failed.");
        return ret;
    }

    ret = SetSWParams(cardIns);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Setting of swparams failed.");
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

static struct AlsaCapture *GetCaptureInsByName(const char *adapterName)
{
    struct AlsaCapture *captureIns = NULL;
    struct AlsaSoundCard *alsaSnd = NULL;

    /*
    fine the instance with the corresponding adapter name, or create one if none.
    */
    for (int32_t i = 0; i < MAX_CARD_NUM; i++) {
        alsaSnd = (struct AlsaSoundCard *)&g_alsaCaptureList[i];
        if (alsaSnd->cardStatus) {
            if (0 == strcmp(alsaSnd->adapterName, adapterName)) {
                return &g_alsaCaptureList[i];
            }
        }
    }

    for (int32_t i = 0; i < MAX_CARD_NUM; i++) {
        captureIns = &g_alsaCaptureList[i];
        alsaSnd = (struct AlsaSoundCard *)&g_alsaCaptureList[i];
        if (alsaSnd->cardStatus == 0) {
            (void)memset_s(captureIns, sizeof(struct AlsaCapture), 0, sizeof(struct AlsaCapture));
            int32_t ret = strncpy_s(alsaSnd->adapterName, MAX_CARD_NAME_LEN + 1, adapterName, strlen(adapterName));
            if (ret != 0) {
                AUDIO_FUNC_LOGE("strncpy_s failed!");
                return NULL;
            }
            alsaSnd->cardStatus++;
            captureIns->periodEvent = POLL_EVENT_DEF;
            captureIns->periodTime = AUDIO_PERIOD_TIME_DEF;
            captureIns->bufferTime = AUDIO_BUFFER_TIME_DEF;
            captureIns->descPins = PIN_NONE;
            captureIns->resample = 1;
            return captureIns;
        }
    }
    AUDIO_FUNC_LOGE("Failed to AddCardIns!");
    return NULL;
}

struct AlsaCapture *CaptureCreateInstance(const char* adapterName, enum AudioCategory scene)
{
    struct AlsaCapture *captureIns = NULL;
    int32_t dev;
    int32_t ret;
    if (adapterName == NULL || strlen(adapterName) == 0) {
        AUDIO_FUNC_LOGE("Invalid adapterName!");
        return NULL;
    }

    if (g_alsaCaptureList == NULL) {
        g_alsaCaptureList = (struct AlsaCapture *)OsalMemCalloc(MAX_CARD_NUM * sizeof(struct AlsaCapture));
        if (g_alsaCaptureList == NULL) {
            AUDIO_FUNC_LOGE("Failed to allocate memory!");
            return NULL;
        }
    }

    captureIns = GetCaptureInsByName(adapterName);
    if (captureIns == NULL) {
        AUDIO_FUNC_LOGE("Get capture instance failed.");
        return NULL;
    }
    RegisterCaptureImpl(captureIns);

    // new add
    dev = CaptureGetSceneDev(scene);
    if (dev > MIXER_CTL_MAX_NUM || dev < -1) {
        dev = -1;
    }
    ret = SndSaveCardListInfo(SND_PCM_STREAM_CAPTURE, dev);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Failed to save card device info.");
        return NULL;
    }

    ret = SndMatchSelCaptureAdapter(&captureIns->soundCard, adapterName);
    if (ret != HDF_SUCCESS) {
        SndCloseHandle(&captureIns->soundCard);
        CaptureFreeMemory();
        return NULL;
    }
    CaptureOverrideFunc(captureIns);

    return captureIns;
}

struct AlsaCapture *CaptureGetInstance(const char *adapterName)
{
    if (adapterName == NULL || strlen(adapterName) == 0) {
        AUDIO_FUNC_LOGE("Invalid cardName!");
        return NULL;
    }

    if (g_alsaCaptureList == NULL) {
        AUDIO_FUNC_LOGE("g_alsaCaptureList is NULL!");
        return NULL;
    }

    for (int32_t i = 0; i < MAX_CARD_NUM; i++) {
        if (strcmp(g_alsaCaptureList[i].soundCard.adapterName, adapterName) == 0) {
            return &(g_alsaCaptureList[i]);
        }
    }

    return NULL;
}

static int32_t CheckCapFrameBufferSize(struct AudioHwCaptureParam *handleData, snd_pcm_uframes_t *periodSize)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(handleData);
    CHECK_NULL_PTR_RETURN_DEFAULT(periodSize);

    uint32_t capFrameSize = handleData->frameCaptureMode.attrs.channelCount * handleData->frameCaptureMode.attrs.format;
    if (capFrameSize == 0) {
        AUDIO_FUNC_LOGE("Capture frame size is zero!");
        return HDF_FAILURE;
    }
    uint64_t capReqBufferSize = capFrameSize * (*periodSize);
    if (capReqBufferSize > FRAME_DATA) {
        *periodSize = FRAME_DATA / capFrameSize;
    }

    return HDF_SUCCESS;
}

static int32_t CheckPcmStatus(snd_pcm_t *capturePcmHandle)
{
    int32_t ret = HDF_SUCCESS;
    CHECK_NULL_PTR_RETURN_DEFAULT(capturePcmHandle);
#ifndef EMULATOR_ENABLED
    ret = snd_pcm_wait(capturePcmHandle, -1); /* -1 for timeout, Waiting forever */
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_pcm_wait failed: %{public}s.", snd_strerror(ret));
        return HDF_FAILURE;
    }
#endif
    if (snd_pcm_state(capturePcmHandle) == SND_PCM_STATE_SETUP) {
        ret = snd_pcm_prepare(capturePcmHandle);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("snd_pcm_prepare fail: %{public}s", snd_strerror(ret));
            return HDF_FAILURE;
        }
    }
#ifdef EMULATOR_ENABLED
    ret = snd_pcm_wait(capturePcmHandle, PCM_WAIT_TIME); /* -1 for timeout, Waiting forever */
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_pcm_wait failed: %{public}s.", snd_strerror(ret));
        return HDF_FAILURE;
    }
#endif
    return HDF_SUCCESS;
}

static int32_t CapturePcmReadi(snd_pcm_t *pcm, uint64_t *frameCnt, char *dataBuf, snd_pcm_uframes_t bufSize)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(pcm);
    CHECK_NULL_PTR_RETURN_DEFAULT(frameCnt);
    CHECK_NULL_PTR_RETURN_DEFAULT(dataBuf);
    *frameCnt = 0;
    if (bufSize == 0) {
        return HDF_FAILURE;
    }
    for (int32_t attempt = 0; attempt < AUDIO_ALSALIB_RETYR; ++attempt) {
        snd_pcm_sframes_t frames = snd_pcm_readi(pcm, dataBuf, bufSize);
        if (frames > 0) {
            if ((snd_pcm_uframes_t)frames > bufSize) {
                return HDF_FAILURE;
            }
            *frameCnt = (uint64_t)frames;
            return HDF_SUCCESS;
        }
        if (frames == 0 || frames == -EAGAIN || frames == -EINTR) {
            // Nonblocking capture may have no frames yet; wait only a bounded interval.
            if (snd_pcm_wait(pcm, 100) < 0) {
                return HDF_FAILURE;
            }
            continue;
        }
        if (frames != -EPIPE && frames != -ESTRPIPE) {
            return HDF_FAILURE;
        }
        int32_t ret = snd_pcm_recover(pcm, (int)frames, 0);
        if (ret < 0 || snd_pcm_start(pcm) < 0) {
            return HDF_FAILURE;
        }
    }
    // Never claim that an empty retry sequence filled the caller's buffer.
    return HDF_FAILURE;
}

static int32_t CaptureDataCopy(struct AudioHwCaptureParam *handleData, char *buffer, uint64_t frames)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(handleData);
    CHECK_NULL_PTR_RETURN_DEFAULT(buffer);
    if (frames == 0) {
        AUDIO_FUNC_LOGE("Capture buffer size is empty!");
        return HDF_FAILURE;
    }

    if (handleData->frameCaptureMode.buffer == NULL) {
        AUDIO_FUNC_LOGE("frameCaptureMode.buffer is NULL!");
        return HDF_FAILURE;
    }
    uint32_t channels = handleData->frameCaptureMode.attrs.channelCount;
    uint32_t format = (uint32_t)handleData->frameCaptureMode.attrs.format;
    uint64_t recvDataSize = (uint64_t)(frames * channels * format);
    int32_t ret = memcpy_s(handleData->frameCaptureMode.buffer, FRAME_DATA, buffer, recvDataSize);
    if (ret != EOK) {
        AUDIO_FUNC_LOGE("memcpy frame data failed!");
        return HDF_FAILURE;
    }
    handleData->frameCaptureMode.bufferSize = recvDataSize;
    handleData->frameCaptureMode.bufferFrameSize = frames;

    return HDF_SUCCESS;
}

static int32_t CaptureOpenImpl(struct AlsaCapture *captureIns)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);

    if (SndisBusy(&captureIns->soundCard)) {
        AUDIO_FUNC_LOGE("Resource busy!!");
        SndCloseHandle(&captureIns->soundCard);
        return HDF_ERR_DEVICE_BUSY;
    }

    AUDIO_FUNC_LOGI("capture snd_pcm_open devName: %{public}s!", captureIns->soundCard.devName);
    int32_t ret = snd_pcm_open(&captureIns->soundCard.pcmHandle, captureIns->soundCard.devName,
        SND_PCM_STREAM_CAPTURE, SND_PCM_NONBLOCK);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_pcm_open fail: %{public}s!", snd_strerror(ret));
        CaptureFreeMemory();
        return HDF_FAILURE;
    }

    ret = snd_pcm_nonblock(captureIns->soundCard.pcmHandle, 1);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_pcm_nonblock fail: %{public}s!", snd_strerror(ret));
        SndCloseHandle(&captureIns->soundCard);
        CaptureFreeMemory();
        return HDF_FAILURE;
    }

    // The verified ALSA loopback card exposes a PCM cable, not physical mixer controls.
    if (strcmp(captureIns->soundCard.alsaCardId, "QemuCapture") == 0) {
        return HDF_SUCCESS;
    }
    ret = SndOpenMixer(&captureIns->soundCard);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("SndOpenMixer failed");
        SndCloseHandle(&captureIns->soundCard);
        CaptureFreeMemory();
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

static int32_t CaptureCloseImpl(struct AlsaCapture *captureIns)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    SndCloseHandle(&captureIns->soundCard);
    CaptureFreeMemory();
    return HDF_SUCCESS;
}

static int32_t CaptureCheckMmapMode(struct AlsaSoundCard *cardIns)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    if (strcmp(cardIns->alsaCardId, "QemuCapture") == 0) {
        // Only explicit Start may start this PCM; an old read must not undo Stop/drop.
        return !cardIns->pauseState && cardIns->mmapFlag && cardIns->pcmHandle != NULL &&
            snd_pcm_state(cardIns->pcmHandle) == SND_PCM_STATE_RUNNING ? HDF_SUCCESS : HDF_FAILURE;
    }


    if (!cardIns->mmapFlag) {
        int32_t ret = ResetCaptureParams(cardIns, SND_PCM_ACCESS_RW_INTERLEAVED);
        if (ret != HDF_SUCCESS) {
            AUDIO_FUNC_LOGE("AudioSetParamsMmap failed!");
            return ret;
        }

        ret = snd_pcm_start(cardIns->pcmHandle);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("snd_pcm_start fail. %{public}s", snd_strerror(ret));
            return HDF_FAILURE;
        }
        cardIns->mmapFlag = true;
    }
    return HDF_SUCCESS;
}

static int32_t CheckCapturePeriodCapacity(snd_pcm_t *pcm, snd_pcm_uframes_t frames)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(pcm);
    snd_pcm_sframes_t bytesPerFrame = snd_pcm_frames_to_bytes(pcm, 1);
    if (bytesPerFrame <= 0 || bytesPerFrame > ALSA_CAP_BUFFER_SIZE || frames == 0 ||
        frames > ALSA_CAP_BUFFER_SIZE / (snd_pcm_uframes_t)bytesPerFrame) {
        return HDF_FAILURE;
    }
    return HDF_SUCCESS;
}

static int32_t CaptureReadImpl(struct AlsaCapture *captureIns, struct AudioHwCaptureParam *handleData)
{
    uint64_t frames = 0;
    char *buffer = NULL;
    snd_pcm_uframes_t bufferSize = 0;
    snd_pcm_uframes_t periodSize = 0;
    struct AlsaSoundCard *cardIns = (struct AlsaSoundCard *)captureIns;
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(handleData);
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns->pcmHandle);

    if (cardIns->pauseState) {
        AUDIO_FUNC_LOGE("Currently in pause, please check!");
        return HDF_FAILURE;
    }

    int32_t ret = snd_pcm_get_params(cardIns->pcmHandle, &bufferSize, &periodSize);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Get capture params error: %{public}s.", snd_strerror(ret));
        return HDF_FAILURE;
    }
    if (CaptureCheckMmapMode(cardIns) != HDF_SUCCESS) {
        return HDF_FAILURE;
    }

    if (CheckCapFrameBufferSize(handleData, &periodSize) != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("CheckCapFrameBufferSize failed.");
        return HDF_FAILURE;
    }
    if (CheckCapturePeriodCapacity(cardIns->pcmHandle, periodSize) != HDF_SUCCESS) {
        return HDF_FAILURE;
    }
    if (strcmp(cardIns->alsaCardId, "QemuCapture") == 0) {
        // No unbounded ARM wait or implicit prepare after Stop for the explicit PCM cable.
        if (snd_pcm_wait(cardIns->pcmHandle, 100) <= 0) {
            return HDF_FAILURE;
        }
    } else if (CheckPcmStatus(cardIns->pcmHandle) != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("CheckPcmStatus failed.");
        return HDF_FAILURE;
    }
    buffer = OsalMemCalloc(ALSA_CAP_BUFFER_SIZE);
    if (buffer == NULL) {
        AUDIO_FUNC_LOGE("Failed to Calloc buffer");
        return HDF_FAILURE;
    }
    ret = CapturePcmReadi(cardIns->pcmHandle, &frames, buffer, periodSize);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("CapturePcmReadi is error!");
        AudioMemFree((void **)&buffer);
        return ret;
    }
    ret = CaptureDataCopy(handleData, buffer, frames);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Failed to copy data. It may be paused. Check the status!");
        AudioMemFree((void **)&buffer);
        return ret;
    }

    AudioMemFree((void **)&buffer);
    return HDF_SUCCESS;
}

static int32_t CaptureGetMmapPositionImpl(struct AlsaCapture *captureIns)
{
    return captureIns->soundCard.mmapFrames;
}

static int32_t CaptureMmapReadImpl(struct AlsaCapture *captureIns, const struct AudioHwCaptureParam *handleData)
{
    struct AlsaSoundCard *cardIns = (struct AlsaSoundCard *)captureIns;
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(handleData);

    if (cardIns->pauseState) {
        AUDIO_FUNC_LOGE("Currently in pause, please check!");
        return HDF_FAILURE;
    }

    if (UpdateSetParams(cardIns) != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Update set params failed!");
        return HDF_FAILURE;
    }

    char *mmapAddr = (char *)handleData->frameCaptureMode.mmapBufDesc.memoryAddress;
    if (mmapAddr == NULL) {
        AUDIO_FUNC_LOGE("mmapAddr is NULL!");
        return HDF_FAILURE;
    }
    snd_pcm_uframes_t size = (snd_pcm_sframes_t)handleData->frameCaptureMode.mmapBufDesc.totalBufferFrames;
    uint32_t frameSize = handleData->frameCaptureMode.attrs.channelCount * handleData->frameCaptureMode.attrs.format;
    while (size > 0) {
        snd_pcm_sframes_t xfer = snd_pcm_mmap_readi(cardIns->pcmHandle, mmapAddr, size);
        if (xfer < 0) {
            if (xfer == -EAGAIN) {
                snd_pcm_wait(cardIns->pcmHandle, AUDIO_PCM_WAIT);
                continue;
            }
            AUDIO_FUNC_LOGE("snd_pcm_mmap_readi: %{public}s", snd_strerror(xfer));
            return HDF_FAILURE;
        }

        if (xfer > 0) {
            mmapAddr += xfer * frameSize;
            size -= xfer;
            cardIns->mmapFrames += xfer;
        }
    }

    return HDF_SUCCESS;
}

static int32_t CaptureInitImpl(struct AlsaCapture* captureIns)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t CaptureSelectSceneImpl(struct AlsaCapture *captureIns, const struct AudioHwCaptureParam *handleData)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t CaptureStartImpl(struct AlsaCapture *captureIns, const struct AudioHwCaptureParam *handleData)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t CaptureStopImpl(struct AlsaCapture *captureIns)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t CaptureGetVolThresholdImpl(struct AlsaCapture *captureIns, long *volMin, long *volMax)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t CaptureGetVolumeImpl(struct AlsaCapture *captureIns, long *volume)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t CaptureSetVolumeImpl(struct AlsaCapture *captureIns, long volume)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t CaptureGetGainThresholdImpl(struct AlsaCapture *captureIns, float *gainMin, float *gainMax)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t CaptureGetGainImpl(struct AlsaCapture *captureIns, float *gain)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t CaptureSetGainImpl(struct AlsaCapture *captureIns, float gain)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static bool CaptureGetMuteImpl(struct AlsaCapture *captureIns)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return false;
}

static int32_t CaptureSetMuteImpl(struct AlsaCapture *captureIns, bool muteFlag)
{
    AUDIO_FUNC_LOGE("Not yet realized");
    return HDF_SUCCESS;
}

static int32_t CaptureSetPauseStateImpl(struct AlsaCapture *captureIns, bool pauseFlag)
{
    int32_t ret = HDF_SUCCESS;
    int pause = pauseFlag ? AUDIO_ALSALIB_IOCTRL_PAUSE : AUDIO_ALSALIB_IOCTRL_RESUME;
    struct AlsaSoundCard *cardIns = (struct AlsaSoundCard *)captureIns;
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns->pcmHandle);

    if (cardIns->canPause) {
        ret = snd_pcm_pause(cardIns->pcmHandle, pause);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("snd_pcm_pause failed!");
            return HDF_FAILURE;
        }
    } else {
        if (pause == AUDIO_ALSALIB_IOCTRL_RESUME) {
            ret = snd_pcm_prepare(cardIns->pcmHandle);
            if (ret < 0) {
                AUDIO_FUNC_LOGE("snd_pcm_prepare fail: %{public}s", snd_strerror(ret));
                return HDF_FAILURE;
            }
            ret = snd_pcm_start(cardIns->pcmHandle);
            if (ret < 0) {
                AUDIO_FUNC_LOGE("snd_pcm_start fail. %{public}s", snd_strerror(ret));
                return HDF_FAILURE;
            }
        }
        if (pause == AUDIO_ALSALIB_IOCTRL_PAUSE) {
            ret = snd_pcm_drop(cardIns->pcmHandle);
            if (ret < 0) {
                AUDIO_FUNC_LOGE("Pause fail: %{public}s", snd_strerror(ret));
                return HDF_FAILURE;
            }
        }
    }
    cardIns->pauseState = pauseFlag;

    return ret;
}

static int32_t CaptureSetHwParamsImpl(struct AlsaCapture *captureIns, const struct AudioHwCaptureParam *handleData)
{
    int32_t ret;
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(handleData);
    ret = CaptureSetParams(captureIns, handleData);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Render set parameters failed!");
        return ret;
    }
    return HDF_SUCCESS;
}

static void RegisterCaptureImpl(struct AlsaCapture *captureIns)
{
    if (captureIns == NULL) {
        AUDIO_FUNC_LOGE("captureIns is NULL!");
        return;
    }

    captureIns->Init = CaptureInitImpl;
    captureIns->Open = CaptureOpenImpl;
    captureIns->Close = CaptureCloseImpl;
    captureIns->SelectScene = CaptureSelectSceneImpl;
    captureIns->Start = CaptureStartImpl;
    captureIns->Stop = CaptureStopImpl;
    captureIns->Read = CaptureReadImpl;
    captureIns->GetMmapPosition = CaptureGetMmapPositionImpl;
    captureIns->MmapRead = CaptureMmapReadImpl;
    captureIns->GetVolThreshold = CaptureGetVolThresholdImpl;
    captureIns->GetVolume = CaptureGetVolumeImpl;
    captureIns->SetVolume = CaptureSetVolumeImpl;
    captureIns->GetGainThreshold = CaptureGetGainThresholdImpl;
    captureIns->GetGain = CaptureGetGainImpl;
    captureIns->SetGain = CaptureSetGainImpl;
    captureIns->GetMute = CaptureGetMuteImpl;
    captureIns->SetMute = CaptureSetMuteImpl;
    captureIns->SetPauseState = CaptureSetPauseStateImpl;

    captureIns->SetParams = CaptureSetHwParamsImpl;
}
