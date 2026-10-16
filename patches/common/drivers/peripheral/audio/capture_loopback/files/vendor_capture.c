/*
 * Copyright (c) 2024 Huawei Device Co., Ltd.
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

#include "alsa_snd_capture.h"
#include "common.h"

#define HDF_LOG_TAG HDF_AUDIO_HAL_CAPTURE

typedef struct CaptureData {
    struct AlsaMixerCtlElement ctrlLeftVolume;
    struct AlsaMixerCtlElement ctrlRightVolume;
    long tempVolume;
} CaptureData;

static bool IsQemuLoopbackCapture(const struct AlsaCapture *captureIns)
{
    return captureIns != NULL && strcmp(captureIns->soundCard.alsaCardId, "QemuCapture") == 0;
}

static int32_t StartQemuLoopbackCapture(struct AlsaCapture *captureIns)
{
    struct AlsaSoundCard *card = &captureIns->soundCard;
    CHECK_NULL_PTR_RETURN_DEFAULT(card->pcmHandle);
    if (snd_pcm_state(card->pcmHandle) != SND_PCM_STATE_RUNNING) {
        if (snd_pcm_prepare(card->pcmHandle) < 0 || snd_pcm_start(card->pcmHandle) < 0) {
            return HDF_FAILURE;
        }
    }
    card->mmapFlag = true;
    card->pauseState = false;
    return HDF_SUCCESS;
}

static int32_t StopQemuLoopbackCapture(struct AlsaCapture *captureIns)
{
    struct AlsaSoundCard *card = &captureIns->soundCard;
    CHECK_NULL_PTR_RETURN_DEFAULT(card->pcmHandle);
    if (snd_pcm_drop(card->pcmHandle) < 0) {
        return HDF_FAILURE;
    }
    card->mmapFlag = false;
    card->pauseState = true;
    return HDF_SUCCESS;
}

static int32_t CaptureInitImpl(struct AlsaCapture* captureIns)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    if (IsQemuLoopbackCapture(captureIns)) {
        return HDF_SUCCESS; // No mixer exists; PCM open/parameters/start each perform their own checks.
    }
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    if (captureIns->priData != NULL) {
        return HDF_SUCCESS;
    }

    CaptureData *priData = (CaptureData *)OsalMemCalloc(sizeof(CaptureData));
    if (priData == NULL) {
        AUDIO_FUNC_LOGE("Failed to allocate memory!");
        return HDF_FAILURE;
    }

    SndElementItemInit(&priData->ctrlLeftVolume);
    SndElementItemInit(&priData->ctrlRightVolume);
    priData->ctrlLeftVolume.numid = SND_NUMID_DACL_CAPTURE_VOL;
    priData->ctrlLeftVolume.name = SND_ELEM_DACL_CAPTURE_VOL;
    priData->ctrlRightVolume.numid = SND_NUMID_DACR_CAPTURE_VOL;
    priData->ctrlRightVolume.name = SND_ELEM_DACR_CAPTURE_VOL;
    CaptureSetPriData(captureIns, (CapturePriData)priData);

    return HDF_SUCCESS;
}

static int32_t CaptureSelectSceneImpl(struct AlsaCapture *captureIns, const struct AudioHwCaptureParam *handleData)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(handleData);
    captureIns->descPins = handleData->captureMode.hwInfo.deviceDescript.pins;
    return HDF_SUCCESS;
}

static int32_t CaptureGetVolThresholdImpl(struct AlsaCapture *captureIns, long *volMin, long *volMax)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    if (IsQemuLoopbackCapture(captureIns)) {
        return HDF_ERR_NOT_SUPPORT;
    }
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(volMin);
    CHECK_NULL_PTR_RETURN_DEFAULT(volMax);
    int32_t ret = HDF_SUCCESS;
    long volMinTmp = 0;
    long volMaxTmp = 0;
    struct AlsaSoundCard *cardIns = (struct AlsaSoundCard *)captureIns;
    CaptureData *priData = CaptureGetPriData(captureIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(priData);

    ret = SndElementReadRange(cardIns, &priData->ctrlLeftVolume, &volMinTmp, &volMaxTmp);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("SndElementReadRange fail!");
        return HDF_FAILURE;
    }
    *volMin = volMinTmp;
    *volMax = volMaxTmp;
    
    return HDF_SUCCESS;
}

static int32_t CaptureGetVolumeImpl(struct AlsaCapture *captureIns, long *volume)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    if (IsQemuLoopbackCapture(captureIns)) {
        return HDF_ERR_NOT_SUPPORT;
    }
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(volume);
    int32_t ret = HDF_SUCCESS;
    long volLeft = 0;
    long volRight = 0;
    struct AlsaSoundCard *cardIns = (struct AlsaSoundCard *)captureIns;
    CaptureData *priData = CaptureGetPriData(captureIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(priData);

    ret = SndElementReadInt(cardIns, &priData->ctrlLeftVolume, &volLeft);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Read left volume fail!");
        return HDF_FAILURE;
    }
    ret = SndElementReadInt(cardIns, &priData->ctrlRightVolume, &volRight);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Read right volume fail!");
        return HDF_FAILURE;
    }
    *volume = (volLeft + volRight) >> 1;
    
    return HDF_SUCCESS;
}

static int32_t CaptureSetVolumeImpl(struct AlsaCapture *captureIns, long volume)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    if (IsQemuLoopbackCapture(captureIns)) {
        return HDF_ERR_NOT_SUPPORT;
    }
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    int32_t ret = HDF_SUCCESS;
    struct AlsaSoundCard *cardIns = (struct AlsaSoundCard *)captureIns;
    CaptureData *priData = CaptureGetPriData(captureIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(priData);
    ret = SndElementWriteInt(cardIns, &priData->ctrlLeftVolume, volume);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Write left volume fail!");
        return HDF_FAILURE;
    }
    ret = SndElementWriteInt(cardIns, &priData->ctrlRightVolume, volume);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Write right volume fail!");
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

static int32_t CaptureSetMuteImpl(struct AlsaCapture *captureIns, bool muteFlag)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    if (IsQemuLoopbackCapture(captureIns)) {
        return HDF_ERR_NOT_SUPPORT;
    }
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    int32_t ret = HDF_SUCCESS;
    long vol = 0;
    long setVol = 0;
    CaptureData *priData = CaptureGetPriData(captureIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(priData);
    ret = captureIns->GetVolume(captureIns, &vol);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("GetVolume failed!");
        return HDF_FAILURE;
    }
    
    if (muteFlag) {
        priData->tempVolume = vol;
        setVol = 0;
    } else {
        setVol = priData->tempVolume;
    }
    ret = captureIns->SetVolume(captureIns, setVol);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("SetVolume failed!");
        return HDF_FAILURE;
    }
    captureIns->muteState = muteFlag;
    return HDF_SUCCESS;
}

static int32_t CaptureStartImpl(struct AlsaCapture *captureIns, const struct AudioHwCaptureParam *handleData)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    if (IsQemuLoopbackCapture(captureIns)) {
        return StartQemuLoopbackCapture(captureIns);
    }
    return HDF_SUCCESS;
}

static int32_t CaptureStopImpl(struct AlsaCapture *captureIns)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    if (IsQemuLoopbackCapture(captureIns)) {
        return StopQemuLoopbackCapture(captureIns);
    }
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    snd_pcm_drop(captureIns->soundCard.pcmHandle);
    return HDF_SUCCESS;
}

static int32_t CaptureGetGainThresholdImpl(struct AlsaCapture *captureIns, float *gainMin, float *gainMax)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    if (IsQemuLoopbackCapture(captureIns)) {
        return HDF_ERR_NOT_SUPPORT;
    }
    AUDIO_FUNC_LOGE("emulator not support gain operation");
    return HDF_SUCCESS;
}

static int32_t CaptureGetGainImpl(struct AlsaCapture *captureIns, float *volume)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    if (IsQemuLoopbackCapture(captureIns)) {
        return HDF_ERR_NOT_SUPPORT;
    }
    AUDIO_FUNC_LOGE("emulator not support gain operation");
    return HDF_SUCCESS;
}

static int32_t CaptureSetGainImpl(struct AlsaCapture *captureIns, float volume)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    if (IsQemuLoopbackCapture(captureIns)) {
        return HDF_ERR_NOT_SUPPORT;
    }
    AUDIO_FUNC_LOGE("emulator not support gain operation");
    return HDF_SUCCESS;
}

static bool CaptureGetMuteImpl(struct AlsaCapture *captureIns)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(captureIns);
    return captureIns->muteState;
}

int32_t CaptureOverrideFunc(struct AlsaCapture *captureIns)
{
    if (captureIns == NULL) {
        return HDF_FAILURE;
    }
    struct AlsaSoundCard *cardIns = (struct AlsaSoundCard *)captureIns;

    if (cardIns->cardType == SND_CARD_PRIMARY) {
        captureIns->Init = CaptureInitImpl;
        captureIns->SelectScene = CaptureSelectSceneImpl;
        captureIns->Start = CaptureStartImpl;
        captureIns->Stop = CaptureStopImpl;
        captureIns->GetVolThreshold = CaptureGetVolThresholdImpl;
        captureIns->GetVolume = CaptureGetVolumeImpl;
        captureIns->SetVolume = CaptureSetVolumeImpl;
        captureIns->GetGainThreshold = CaptureGetGainThresholdImpl;
        captureIns->GetGain = CaptureGetGainImpl;
        captureIns->SetGain = CaptureSetGainImpl;
        captureIns->GetMute = CaptureGetMuteImpl;
        captureIns->SetMute = CaptureSetMuteImpl;
    }
    
    return HDF_SUCCESS;
}

int32_t CaptureGetSceneDev(enum AudioCategory scene)
{
    (void)scene;
    return -1;
}
