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

#ifndef ALSA_SOUNDCARD_H
#define ALSA_SOUNDCARD_H

#include "audio_common.h"
#include "audio_if_lib_common.h"
#include "hdf_io_service_if.h"
#include "asoundlib.h"
#include "osal_mem.h"
#include "osal_time.h"
#include "hdf_sbuf.h"
#include "audio_uhdf_log.h"
#include "securec.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SERVIC_NAME_MAX_LEN         32
#define MAX_VOLUME                  100
#define MIN_VOLUME                  0
#define AUDIO_MIN_CARD_NUM          1
#define AUDIO_MAX_CARD_NUM          8
#define CARD_ID_LEN_MAX             32
#define MAX_CARD_NAME_LEN           64
#define MAX_CARD_NUM                (4 * (AUDIO_MAX_CARD_NUM))
#define MAX_CTL_NAME_LEN            64
#define MAX_CTL_VALUE_LEN           32
#define AUDIO_ALSALIB_IOCTRL_RESUME 0
#define AUDIO_ALSALIB_IOCTRL_PAUSE  1
#define AUDIO_ALSALIB_MMAP_MAX      10
#define AUDIO_ALSALIB_RETYR         3
#define ALSA_CTL_NAME_LEN           64
#define MIXER_CTL_MAX_NUM           64

enum SndCardType {
    SND_CARD_UNKNOWN = -1,
    SND_CARD_PRIMARY = 0,
    SND_CARD_HDMI,
    SND_CARD_USB,
    SND_CARD_BT,
    SND_CARD_MAX
};

enum SndIfaceType {
    IFACE_CARD = 0,
    IFACE_MIXER,
    IFACE_PCM,
    IFACE_RAWMIDI,
    IFACE_TIMER,
    IFACE_SEQUENCER
};

struct AlsaMixerCtlElement {
    unsigned int numid;
    enum SndIfaceType iface;
    const char *name;
    char *value;
    unsigned int index;
    unsigned int device;
    unsigned int subdevice;
};

struct AlsaSoundCard {
    /*
        save alsa soundcard base info and hardware params
    */
    enum SndCardType cardType;
    char adapterName[MAX_CARD_NAME_LEN + 1];  //save adapterName
    char devName[MAX_CARD_NAME_LEN + 1];   //device name hw:x
    char alsaCardId[MAX_CARD_NAME_LEN + 1];
    char ctrlName[MAX_CARD_NAME_LEN + 1];
    struct AudioPcmHwParams hwParams;

    /*
        alsa soundcard driver handle
    */
    snd_pcm_t *pcmHandle;
    snd_mixer_t *mixerHandle;

    /*
        alsa soundcard public variable
    */
    uint8_t cardStatus;
    bool canPause;
    bool pauseState;
    int32_t muteValue;
    bool mmapFlag;
    uint64_t mmapFrames;
};

struct DevHandle *AudioBindService(const char *name);
void AudioCloseService(const struct DevHandle *handle);
struct HdfIoService *HdfIoServiceBindName(const char *serviceName);

int32_t SndMatchSelAdapter(struct AlsaSoundCard *cardIns, const char *adapterName);
int32_t SndMatchSelCaptureAdapter(struct AlsaSoundCard *cardIns, const char *adapterName);
int32_t SndConverAlsaPcmFormat(const struct AudioPcmHwParams *hwParams,
    snd_pcm_format_t *alsaPcmFormat);
int32_t SndSaveCardListInfo(snd_pcm_stream_t stream, int32_t device);
bool  SndisBusy(struct AlsaSoundCard *cardIns);
int32_t SndOpenMixer(struct AlsaSoundCard *cardIns);
int32_t SndPcmPrepare(struct AlsaSoundCard *cardIns);
snd_pcm_state_t SndGetRunState(struct AlsaSoundCard *cardIns);
void  SndCloseHandle(struct AlsaSoundCard *cardIns);

void SndElementItemInit(struct AlsaMixerCtlElement *m);
int32_t SndElementReadInt(struct AlsaSoundCard *cardIns,
    const struct AlsaMixerCtlElement *ctlElem, long *value);
int32_t SndElementReadEnum(struct AlsaSoundCard *cardIns,
    const struct AlsaMixerCtlElement *ctlElem, unsigned int *item);
int32_t SndElementReadRange(struct AlsaSoundCard *cardIns,
    const struct AlsaMixerCtlElement *ctlElem, long *mix, long *max);
int32_t SndElementReadSwitch(struct AlsaSoundCard *cardIns,
    const struct AlsaMixerCtlElement *ctlElem, bool *on);
int32_t SndElementWriteInt(struct AlsaSoundCard *cardIns,
    const struct AlsaMixerCtlElement *ctlElem, long value);
int32_t SndElementWriteEnum(struct AlsaSoundCard *cardIns,
    const struct AlsaMixerCtlElement *ctlElem, unsigned int item);
int32_t SndElementWriteSwitch(struct AlsaSoundCard *cardIns,
    const struct AlsaMixerCtlElement *ctlElem, bool on);
int32_t SndElementWrite(struct AlsaSoundCard *cardIns,
    const struct AlsaMixerCtlElement *ctlElem);
int32_t SndElementGroupWrite(struct AlsaSoundCard *cardIns,
    const struct AlsaMixerCtlElement* elemGroup, int32_t groupSize);
int32_t SndTraversalMixerElement(struct AlsaSoundCard *cardIns,
    bool (*callback)(void *data, snd_ctl_elem_id_t *elem_id), void *data);

#ifdef __cplusplus
}
#endif

#endif /* ALSA_SOUNDCARD_H */
