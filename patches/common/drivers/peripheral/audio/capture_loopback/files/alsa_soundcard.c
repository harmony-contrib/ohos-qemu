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
#include <ctype.h>
#include <pthread.h>
#include "cJSON.h"

#define HDF_LOG_TAG HDF_AUDIO_HAL_SND

#define ALSA_CARD_CONFIG_FILE HDF_CONFIG_DIR "/alsa_adapter.json"
#define ALSA_CONFIG_FILE_MAX  (2 * 1024) // 2KB
#define SUPPORT_CAPTURE_OR_RENDER  1
#define SUPPORT_CAPTURE_AND_RENDER 2
#define MALLOC_MAX 100

/* Define structure description alsa_adapter.hson information  */
struct AlsaAdapterCfgInfo {
    char adapterName[MAX_CARD_NAME_LEN];
    int32_t cardId;
    char cardName[MAX_CARD_NAME_LEN];
    bool hasCaptureRoute;
    int32_t captureCardId;
    char captureCardName[MAX_CARD_NAME_LEN];
    int32_t captureDevice;
};
struct AlsaAdapterList {
    int32_t num;
    struct AlsaAdapterCfgInfo list[AUDIO_MAX_CARD_NUM];
};
static struct AlsaAdapterList g_alsaAdapterList[SND_CARD_MAX];

struct AlsaDevInfo {
    char cardId[MAX_CARD_NAME_LEN + 1];
    char pcmInfoId[MAX_CARD_NAME_LEN + 1];
    int32_t card;
    int32_t device;
};
struct AlsaCardsList {
    int32_t num;
    struct AlsaDevInfo alsaDevIns[MAX_CARD_NUM];
};
static struct AlsaCardsList g_alsaCardsDevList;
static pthread_mutex_t g_alsaConfigMutex = PTHREAD_MUTEX_INITIALIZER;


static char *CfgReadAdapterFile(const char *fpath)
{
    FILE *fp = NULL;
    char *pJsonStr = NULL;
    char pathBuf[PATH_MAX] = {0};

    if (fpath == NULL) {
        AUDIO_FUNC_LOGE("Parameter is null!!!");
        return NULL;
    }
    if (realpath(fpath, pathBuf) == NULL) {
        AUDIO_FUNC_LOGE("File path invalid!");
        return NULL;
    }

    fp = fopen(pathBuf, "r");
    if (fp == NULL) {
        AUDIO_FUNC_LOGE("Can not open config file [ %{public}s ].", fpath);
        return NULL;
    }
    if (fseek(fp, 0, SEEK_END) != 0) {
        AUDIO_FUNC_LOGE("fseek configuration file error!");
        (void)fclose(fp);
        return NULL;
    }
    int32_t jsonStrSize = ftell(fp);
    if (jsonStrSize <= 0) {
        AUDIO_FUNC_LOGE("The configuration file size <= 0!");
        (void)fclose(fp);
        return NULL;
    }
    rewind(fp);
    if (jsonStrSize > ALSA_CONFIG_FILE_MAX) {
        AUDIO_FUNC_LOGE("The configuration file is too large to load!");
        (void)fclose(fp);
        return NULL;
    }
    pJsonStr = (char *)OsalMemCalloc((uint32_t)jsonStrSize + 1);
    if (pJsonStr == NULL) {
        AUDIO_FUNC_LOGE("OsalMemCalloc pJsonStr failed!");
        (void)fclose(fp);
        return NULL;
    }
    if (fread(pJsonStr, jsonStrSize, 1, fp) != 1) {
        AUDIO_FUNC_LOGE("Read to config file failed!!!");
        (void)fclose(fp);
        AudioMemFree((void **)&pJsonStr);
        return NULL;
    }
    (void)fclose(fp);

    return pJsonStr;
}

static int32_t CfgGetAdapterCount()
{
    int32_t num = 0;
    for (enum SndCardType type = SND_CARD_PRIMARY; type < SND_CARD_MAX; ++type) {
        num += g_alsaAdapterList[type].num;
    }
    return num;
}

static enum SndCardType CfgGetAdapterCardType(const char* adapterName)
{
    if (adapterName == NULL) {
        return SND_CARD_UNKNOWN;
    }

    struct AlsaAdapterCfgInfo *info;
    for (enum SndCardType type = SND_CARD_PRIMARY; type < SND_CARD_MAX; ++type) {
        for (int32_t i = 0; i < g_alsaAdapterList[type].num; ++i) {
            info = &g_alsaAdapterList[type].list[i];
            if (strncmp(adapterName, info->adapterName, strlen(info->adapterName)) == 0) {
                return type;
            }
        }
    }
    return SND_CARD_UNKNOWN;
}

static struct AlsaAdapterCfgInfo *CfgGetAdapterInfo(const char* adapterName)
{
    if (adapterName == NULL) {
        return NULL;
    }

    AUDIO_FUNC_LOGI("CfgGetAdapterInfo adapterName: %{public}s", adapterName);
    struct AlsaAdapterCfgInfo *info;
    for (enum SndCardType type = SND_CARD_PRIMARY; type < SND_CARD_MAX; ++type) {
        for (int32_t i = 0; i < g_alsaAdapterList[type].num; ++i) {
            info = &g_alsaAdapterList[type].list[i];
     
            if (strncmp(adapterName, info->adapterName, strlen(info->adapterName)) == 0) {
                return info;
            }
        }
    }
    return NULL;
}

static int32_t CfgDumpAdapterInfo(struct AlsaAdapterCfgInfo *info)
{
    enum SndCardType cardType = SND_CARD_UNKNOWN;
    CHECK_NULL_PTR_RETURN_DEFAULT(info);

    if (strcmp(info->adapterName, PRIMARY) == 0) {
        cardType = SND_CARD_PRIMARY;
    } else if (strcmp(info->adapterName, HDMI) == 0) {
        cardType = SND_CARD_HDMI;
    } else if (strcmp(info->adapterName, USB) == 0) {
        cardType = SND_CARD_USB;
    } else if (strcmp(info->adapterName, A2DP) == 0) {
        cardType = SND_CARD_BT;
    }

    if (cardType == SND_CARD_UNKNOWN) {
        AUDIO_FUNC_LOGE("Error: %{public}s is unspupported adapter name", info->adapterName);
    }

    int32_t idx = g_alsaAdapterList[cardType].num;
    int32_t ret = memcpy_s((void*)&g_alsaAdapterList[cardType].list[idx], sizeof(struct AlsaAdapterCfgInfo),
        (void*)info, sizeof(struct AlsaAdapterCfgInfo));
    if (ret != EOK) {
        AUDIO_FUNC_LOGE("memcpy_s g_alsaAdapterList fail!");
        return HDF_FAILURE;
    }
    g_alsaAdapterList[cardType].num++;

    AUDIO_FUNC_LOGI("cardId:%{public}d: adapterName:%{public}s, cardName:%{public}s",
        g_alsaAdapterList[cardType].list[idx].cardId,
        g_alsaAdapterList[cardType].list[idx].adapterName,
        g_alsaAdapterList[cardType].list[idx].cardName);
    return HDF_SUCCESS;
}

static int32_t CfgSaveCaptureRoute(cJSON *adapter, struct AlsaAdapterCfgInfo *info)
{
    cJSON *card = cJSON_GetObjectItem(adapter, "captureCardId");
    cJSON *name = cJSON_GetObjectItem(adapter, "captureCardName");
    cJSON *device = cJSON_GetObjectItem(adapter, "captureDevice");
    info->hasCaptureRoute = false;
    info->captureCardId = -1;
    info->captureDevice = -1;
    info->captureCardName[0] = '\0';
    if (card == NULL && name == NULL && device == NULL) {
        return HDF_SUCCESS; // Old product configurations retain their existing capture route.
    }
    if (!cJSON_IsNumber(card) || !cJSON_IsString(name) || !cJSON_IsNumber(device) ||
        name->valuestring == NULL || name->valuestring[0] == '\0' ||
        strlen(name->valuestring) >= MAX_CARD_NAME_LEN ||
        !(card->valuedouble >= 0 && card->valuedouble < MAX_CARD_NUM) ||
        !(device->valuedouble >= 0 && device->valuedouble <= MIXER_CTL_MAX_NUM)) {
        return HDF_FAILURE;
    }
    // Range checks precede conversion, including NaN/infinity rejection.
    int32_t cardId = (int32_t)card->valuedouble;
    int32_t pcmDevice = (int32_t)device->valuedouble;
    if (card->valuedouble != cardId || device->valuedouble != pcmDevice ||
        strcpy_s(info->captureCardName, sizeof(info->captureCardName), name->valuestring) != EOK) {
        return HDF_FAILURE;
    }
    info->captureCardId = cardId;
    info->captureDevice = pcmDevice;
    info->hasCaptureRoute = true;
    return HDF_SUCCESS;
}

static int32_t CfgSaveAdapterStruct(cJSON *adapter, struct AlsaAdapterCfgInfo *info)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(adapter);
    CHECK_NULL_PTR_RETURN_DEFAULT(info);

    cJSON *item = cJSON_GetObjectItem(adapter, "name");
    if (item == NULL || item->valuestring == NULL) {
        AUDIO_FUNC_LOGE("adapter name is null!");
        return HDF_FAILURE;
    }
    int32_t ret = strncpy_s(info->adapterName, MAX_CARD_NAME_LEN, item->valuestring, MAX_CARD_NAME_LEN - 1);
    if (ret != EOK) {
        AUDIO_FUNC_LOGE("strncpy_s adapterName fail!");
        return HDF_FAILURE;
    }

    item = cJSON_GetObjectItem(adapter, "cardId");
    if (item == NULL) {
        AUDIO_FUNC_LOGE("cardId not set!");
        return HDF_FAILURE;
    }
    info->cardId = item->valuedouble;

    item = cJSON_GetObjectItem(adapter, "cardName");
    if (item == NULL || item->valuestring == NULL) {
        AUDIO_FUNC_LOGE("cardName is null!");
        return HDF_FAILURE;
    }
    ret = strncpy_s(info->cardName, MAX_CARD_NAME_LEN, item->valuestring, MAX_CARD_NAME_LEN - 1);
    if (ret != EOK) {
        AUDIO_FUNC_LOGE("strncpy_s cardName fail!");
        return HDF_FAILURE;
    }

    return CfgSaveCaptureRoute(adapter, info);
}

static int32_t CfgParseAdapterItems(cJSON *adapterObj)
{
    cJSON *adapterItems = NULL;

    adapterItems = cJSON_GetObjectItem(adapterObj, "adapters");
    if (adapterItems == NULL) {
        AUDIO_FUNC_LOGE("Get adapterItems from json failed!\n");
        return HDF_FAILURE;
    }
    int32_t adapterNum = cJSON_GetArraySize(adapterItems);
    if (adapterNum <= 0) {
        AUDIO_FUNC_LOGE("Get adapter number failed!");
        return HDF_FAILURE;
    } else if (adapterNum > MAX_CARD_NUM) {
        AUDIO_FUNC_LOGE("Read adapters number is %{public}d over max num %{public}d!", adapterNum, MAX_CARD_NUM);
        return HDF_FAILURE;
    }

    for (int32_t i = 0; i < adapterNum; ++i) {
        cJSON *adapter;
        struct AlsaAdapterCfgInfo info;
        adapter = cJSON_GetArrayItem(adapterItems, i);
        if (adapter == NULL) {
            AUDIO_FUNC_LOGE("Get adapter item from array failed!");
        }

        int32_t ret = CfgSaveAdapterStruct(adapter, &info);
        if (ret != HDF_SUCCESS) {
            AUDIO_FUNC_LOGE("CfgSaveAdapterStruct failed!");
            return HDF_FAILURE;
        }

        ret = CfgDumpAdapterInfo(&info);
        if (ret != HDF_SUCCESS) {
            AUDIO_FUNC_LOGE("CfgDumpAdapterInfo failed!");
            return HDF_FAILURE;
        }
    }

    return HDF_SUCCESS;
}

int32_t CfgSaveAdapterFromFile(void)
{
    cJSON *adapterObj = NULL;
    char *configBuf = NULL;

    configBuf = CfgReadAdapterFile(ALSA_CARD_CONFIG_FILE);
    if (configBuf == NULL) {
        AUDIO_FUNC_LOGE("CfgReadAdapterFile failed!");
        return HDF_FAILURE;
    }
    adapterObj = cJSON_Parse(configBuf);
    if (adapterObj == NULL) {
        AUDIO_FUNC_LOGE("Parse json file failed!");
        AudioMemFree((void **)&configBuf);
        return HDF_FAILURE;
    }
    AudioMemFree((void **)&configBuf);

    int32_t ret = CfgParseAdapterItems(adapterObj);
    if (ret != HDF_SUCCESS) {
        cJSON_Delete(adapterObj);
        AUDIO_FUNC_LOGE("Parse adapter items failed!");
        return HDF_FAILURE;
    }

    cJSON_Delete(adapterObj);
    return HDF_SUCCESS;
}

static struct AlsaDevInfo *DevGetInfoByCardId(int32_t cardId)
{
    struct AlsaDevInfo *info = NULL;
    int num = g_alsaCardsDevList.num;
    for (int i = 0; i < num; ++i) {
        info = &g_alsaCardsDevList.alsaDevIns[i];

        if (info->card == cardId) {
            return info;
        }
    }
    return NULL;
}

static struct AlsaDevInfo *DevGetInfoByPcmInfoId(const char * name)
{
    AUDIO_FUNC_LOGI("DevGetInfoByPcmInfoId name: %{public}s", name);
    struct AlsaDevInfo *info = NULL;
    int num = g_alsaCardsDevList.num;
    for (int i = 0; i < num; ++i) {
        info = &g_alsaCardsDevList.alsaDevIns[i];
        if (strcmp(name, info->pcmInfoId) == 0) {
            return info;
        }
    }

    return NULL;
}

static int32_t DevSaveCardPcmInfo(snd_ctl_t *handle, snd_pcm_stream_t stream,
    int card, const char *deviceName, int32_t device)
{
    int pcmDev = device;
    snd_ctl_card_info_t *info = NULL;
    snd_pcm_info_t *pcminfo = NULL;
    snd_ctl_card_info_alloca(&info);
    snd_pcm_info_alloca(&pcminfo);

    if (snd_ctl_card_info(handle, info) != 0) {
        AUDIO_FUNC_LOGE("snd_ctl_card_info failed.");
        return HDF_FAILURE;
    }
    if (snd_ctl_pcm_next_device(handle, &pcmDev) < 0 || pcmDev < 0) {
        AUDIO_FUNC_LOGE("No pcm device found");
        return HDF_FAILURE;
    }
    while (pcmDev >= 0) {
        snd_pcm_info_set_device(pcminfo, pcmDev);
        snd_pcm_info_set_subdevice(pcminfo, 0);
        snd_pcm_info_set_stream(pcminfo, stream);
        int32_t ret = snd_ctl_pcm_info(handle, pcminfo);
        if (ret < 0) {
            if (ret != -ENOENT) {
                AUDIO_FUNC_LOGE("control digital audio info (%{public}d)", pcmDev);
            }
        } else {
            struct AlsaDevInfo *devInfo = &g_alsaCardsDevList.alsaDevIns[g_alsaCardsDevList.num];
            const char *cardId = snd_ctl_card_info_get_id(info);
            const char *pcmInfoId = snd_pcm_info_get_id(pcminfo);
            AUDIO_FUNC_LOGD("alsa cardName: %{public}s, pcmInfoId %{public}s", cardId, pcmInfoId);
            devInfo->card = card;
            devInfo->device = pcmDev;
            if (strncpy_s(devInfo->cardId, MAX_CARD_NAME_LEN + 1, cardId, strlen(cardId)) != 0) {
                AUDIO_FUNC_LOGE("strncpy_s failed!");
                return HDF_FAILURE;
            }
            if (strncpy_s(devInfo->pcmInfoId, MAX_CARD_NAME_LEN + 1, pcmInfoId, strlen(pcmInfoId)) != 0) {
                AUDIO_FUNC_LOGE("strncpy_s failed!");
                return HDF_FAILURE;
            }
            g_alsaCardsDevList.num++;
        }

        if (snd_ctl_pcm_next_device(handle, &pcmDev) < 0) {
            AUDIO_FUNC_LOGE("snd_ctl_pcm_next_device error!");
            return HDF_FAILURE;
        }
        AUDIO_FUNC_LOGI("soundcard pcm device number: %{public}d.", pcmDev);
    }
    return HDF_SUCCESS;
}

static int32_t DevSaveDriverInfo(snd_pcm_stream_t stream, int32_t device)
{
    snd_ctl_t *handle = NULL;
    int card = -1;
    char deviceName[MAX_CARD_NAME_LEN] = {0};

    int32_t ret = snd_card_next(&card);
    if (ret < 0 || card < 0) {
        AUDIO_FUNC_LOGE("No soundcards found: %{public}s.", snd_strerror(ret));
        return HDF_FAILURE;
    }

    while (card >= 0) {
        (void)memset_s(deviceName, MAX_CARD_NAME_LEN, 0, MAX_CARD_NAME_LEN);
        ret = snprintf_s(deviceName, MAX_CARD_NAME_LEN, MAX_CARD_NAME_LEN - 1, "hw:%d", card);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("snprintf_s failed");
            snd_ctl_close(handle);
            return HDF_FAILURE;
        }

        ret = snd_ctl_open(&handle, deviceName, 0);
        if (ret != 0) {
            AUDIO_FUNC_LOGE("snd_ctl_open failed.");
            return HDF_FAILURE;
        }

        ret = DevSaveCardPcmInfo(handle, stream, card, deviceName, device);
        if (ret != HDF_SUCCESS) {
            AUDIO_FUNC_LOGE("save alsa sound cards %{public}s pcm info failed!", deviceName);
        }

        ret = snd_ctl_close(handle);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("snd_ctl_close error: %{public}s.", snd_strerror(ret));
            return HDF_FAILURE;
        }

        ret = snd_card_next(&card);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("snd_card_next error: %{public}s", snd_strerror(ret));
            return HDF_FAILURE;
        }
    }

    return HDF_SUCCESS;
}

static int32_t SndSaveCardListInfoUnlocked(snd_pcm_stream_t stream, int32_t device)
{
    (void)memset_s(&g_alsaAdapterList, sizeof(struct AlsaAdapterList) * SND_CARD_MAX,
        0, sizeof(struct AlsaAdapterList) * SND_CARD_MAX);
    (void)memset_s(&g_alsaCardsDevList, sizeof(struct AlsaCardsList),
        0, sizeof(struct AlsaCardsList));

    /* Parse sound card from configuration file */
    int32_t ret = CfgSaveAdapterFromFile();
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("parse config file failed! ret = %{public}d", ret);
        return HDF_FAILURE;
    }

    if (device > MIXER_CTL_MAX_NUM || device < -1) {
        device = -1;
    }

    /* Read sound card list from alsa hardware */
    ret = DevSaveDriverInfo(stream, device);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("failed to save alsa sound cards driver info");
        return HDF_FAILURE;
    }

    /* if the alsa hardware include usb then add to adapter list */
    struct AlsaDevInfo *devInfo = DevGetInfoByPcmInfoId(USB);
    if (devInfo != NULL) {
        g_alsaAdapterList[SND_CARD_USB].num = 1;
        ret = memcpy_s((void*)&g_alsaAdapterList[SND_CARD_USB].list[0].adapterName, MAX_CARD_NAME_LEN,
        USB, sizeof(USB));
        if (ret != EOK) {
            AUDIO_FUNC_LOGE("memcpy_s adapterName fail!");
            return HDF_FAILURE;
        }
    }

    return HDF_SUCCESS;
}

static int32_t SndMatchSelAdapterUnlocked(struct AlsaSoundCard *cardIns, const char *adapterName)
{
    struct AlsaDevInfo *devInfo = NULL;
    struct AlsaAdapterCfgInfo *info = NULL;
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(adapterName);

    enum SndCardType  cardType = CfgGetAdapterCardType(adapterName);
    if (cardType == SND_CARD_UNKNOWN) {
        AUDIO_FUNC_LOGE("unknow card type error.");
        return HDF_FAILURE;
    }
    cardIns->cardType = cardType;

    info = CfgGetAdapterInfo(adapterName);
    if (info == NULL) {
        AUDIO_FUNC_LOGE("adapter %{public}s is not exits.", cardIns->adapterName);
        return HDF_FAILURE;
    }

    AUDIO_FUNC_LOGI("SndMatchSelAdapter cardId: %{public}d", info->cardId);
    devInfo = DevGetInfoByCardId(info->cardId);
    if (devInfo == NULL) {
        AUDIO_FUNC_LOGE("adapter %{public}s cant not find sound card device.", cardIns->adapterName);
        return HDF_FAILURE;
    }

    int32_t ret = snprintf_s(cardIns->devName, MAX_CARD_NAME_LEN, MAX_CARD_NAME_LEN - 1,
        "hw:%d,%d", devInfo->card, devInfo->device);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("%{public}s snprintf_s devName failed", cardIns->adapterName);
        return HDF_FAILURE;
    }
    ret = snprintf_s(cardIns->ctrlName, MAX_CARD_NAME_LEN, MAX_CARD_NAME_LEN - 1, "hw:%d", devInfo->card);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("%{public}s snprintf_s ctrlName failed", cardIns->adapterName);
        return HDF_FAILURE;
    }
    ret = snprintf_s(cardIns->alsaCardId, MAX_CARD_NAME_LEN, MAX_CARD_NAME_LEN - 1, "%s", devInfo->cardId);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("%{public}s snprintf_s alsaCardId failed", cardIns->adapterName);
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

int32_t SndSaveCardListInfo(snd_pcm_stream_t stream, int32_t device)
{
    pthread_mutex_lock(&g_alsaConfigMutex);
    int32_t ret = SndSaveCardListInfoUnlocked(stream, device);
    pthread_mutex_unlock(&g_alsaConfigMutex);
    return ret;
}

int32_t SndMatchSelAdapter(struct AlsaSoundCard *cardIns, const char *adapterName)
{
    pthread_mutex_lock(&g_alsaConfigMutex);
    int32_t ret = SndMatchSelAdapterUnlocked(cardIns, adapterName);
    pthread_mutex_unlock(&g_alsaConfigMutex);
    return ret;
}

static int32_t SndMatchExplicitCapture(struct AlsaSoundCard *cardIns,
    const struct AlsaAdapterCfgInfo *info, enum SndCardType cardType)
{
    snd_ctl_t *ctl = NULL;
    snd_ctl_card_info_t *cardInfo;
    snd_pcm_info_t *pcmInfo;
    snd_ctl_card_info_alloca(&cardInfo);
    snd_pcm_info_alloca(&pcmInfo);
    char control[MAX_CARD_NAME_LEN] = {0};
    if (snprintf_s(control, sizeof(control), sizeof(control) - 1, "hw:%d", info->captureCardId) < 0 ||
        snd_ctl_open(&ctl, control, 0) < 0) {
        return HDF_FAILURE;
    }
    int32_t ret = HDF_FAILURE;
    if (snd_ctl_card_info(ctl, cardInfo) < 0 ||
        strcmp(snd_ctl_card_info_get_id(cardInfo), info->captureCardName) != 0) {
        goto done;
    }
    // A fresh direction-specific PCM query cannot accidentally select a render enumeration.
    snd_pcm_info_set_device(pcmInfo, (unsigned int)info->captureDevice);
    snd_pcm_info_set_subdevice(pcmInfo, 0);
    snd_pcm_info_set_stream(pcmInfo, SND_PCM_STREAM_CAPTURE);
    if (snd_ctl_pcm_info(ctl, pcmInfo) < 0) {
        goto done;
    }
    if (snprintf_s(cardIns->devName, MAX_CARD_NAME_LEN, MAX_CARD_NAME_LEN - 1,
        "hw:%d,%d,0", info->captureCardId, info->captureDevice) < 0 ||
        strcpy_s(cardIns->ctrlName, MAX_CARD_NAME_LEN, control) != EOK ||
        strcpy_s(cardIns->alsaCardId, MAX_CARD_NAME_LEN, snd_ctl_card_info_get_id(cardInfo)) != EOK) {
        goto done;
    }
    cardIns->cardType = cardType;
    ret = HDF_SUCCESS;
done:
    snd_ctl_close(ctl);
    return ret;
}

int32_t SndMatchSelCaptureAdapter(struct AlsaSoundCard *cardIns, const char *adapterName)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(adapterName);
    pthread_mutex_lock(&g_alsaConfigMutex);
    struct AlsaAdapterCfgInfo *info = CfgGetAdapterInfo(adapterName);
    enum SndCardType type = CfgGetAdapterCardType(adapterName);
    int32_t ret = HDF_FAILURE;
    if (info != NULL && type != SND_CARD_UNKNOWN) {
        if (info->hasCaptureRoute) {
            ret = SndMatchExplicitCapture(cardIns, info, type);
        } else {
            ret = SndMatchSelAdapterUnlocked(cardIns, adapterName);
        }
    }
    pthread_mutex_unlock(&g_alsaConfigMutex);
    return ret;
}

int32_t SndConverAlsaPcmFormat(const struct AudioPcmHwParams *hwParams, snd_pcm_format_t *alsaPcmFormat)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(hwParams);
    CHECK_NULL_PTR_RETURN_DEFAULT(alsaPcmFormat);
    enum AudioFormat audioFormat = hwParams->format;
    bool isBigEndian = hwParams->isBigEndian;

    /** Little Endian */
    if (!isBigEndian) {
        switch (audioFormat) {
            case AUDIO_FORMAT_TYPE_PCM_8_BIT:
                *alsaPcmFormat = SND_PCM_FORMAT_S8; /** Signed 8 bit */
                break;
            case AUDIO_FORMAT_TYPE_PCM_16_BIT:
                *alsaPcmFormat = SND_PCM_FORMAT_S16_LE; /** Signed 16 bit Little Endian */
                break;
            case AUDIO_FORMAT_TYPE_PCM_24_BIT:
                *alsaPcmFormat = SND_PCM_FORMAT_S24_LE; /** Signed 24 bit Little Endian */
                break;
            case AUDIO_FORMAT_TYPE_PCM_32_BIT:
                *alsaPcmFormat = SND_PCM_FORMAT_S32_LE; /** Signed 32 bit Little Endian */
                break;
            default:
                AUDIO_FUNC_LOGE("not support format %{public}d", audioFormat);
                return HDF_ERR_NOT_SUPPORT;
        }
    } else { /** Big Endian */
        switch (audioFormat) {
            case AUDIO_FORMAT_TYPE_PCM_8_BIT:
                *alsaPcmFormat = SND_PCM_FORMAT_S8; /** Signed 8 bit */
                break;
            case AUDIO_FORMAT_TYPE_PCM_16_BIT:
                *alsaPcmFormat = SND_PCM_FORMAT_S16_BE; /** Signed 16 bit Big Endian */
                break;
            case AUDIO_FORMAT_TYPE_PCM_24_BIT:
                *alsaPcmFormat = SND_PCM_FORMAT_S24_BE; /** Signed 24 bit Big Endian */
                break;
            case AUDIO_FORMAT_TYPE_PCM_32_BIT:
                *alsaPcmFormat = SND_PCM_FORMAT_S32_BE; /** Signed 32 bit Big Endian */
                break;
            default:
                AUDIO_FUNC_LOGE("not support format %{public}d", audioFormat);
                return HDF_ERR_NOT_SUPPORT;
        }
    }

    return HDF_SUCCESS;
}

int32_t SndPcmPrepare(struct AlsaSoundCard *cardIns)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    int32_t ret = snd_pcm_prepare(cardIns->pcmHandle);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_pcm_prepare fail: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }
    return HDF_SUCCESS;
}

bool SndisBusy(struct AlsaSoundCard *cardIns)
{
    if (cardIns == NULL) {
        return false;
    }
    return (cardIns->pcmHandle == NULL) ? false : true;
}

int32_t SndOpenMixer(struct AlsaSoundCard *cardIns)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);

    if (strlen(cardIns->ctrlName) == 0) {
        AUDIO_FUNC_LOGE("The soundcard ctrname is null.");
        return HDF_FAILURE;
    }

    int32_t ret = snd_mixer_open(&cardIns->mixerHandle, 0);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Failed to open mixer: %{public}s.", snd_strerror(ret));
        return HDF_FAILURE;
    }

    ret = snd_mixer_attach(cardIns->mixerHandle, cardIns->ctrlName);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Failed to attach mixer: %{public}s.", snd_strerror(ret));
        ret = snd_mixer_close(cardIns->mixerHandle);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("mixer close error: %{public}s.", snd_strerror(ret));
        }
        cardIns->mixerHandle = NULL;
        return HDF_FAILURE;
    }

    ret = snd_mixer_selem_register(cardIns->mixerHandle, NULL, NULL);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Failed to register mixer element: %{public}s.", snd_strerror(ret));
        ret = snd_mixer_close(cardIns->mixerHandle);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("mixer close error: %{public}s.", snd_strerror(ret));
        }
        cardIns->mixerHandle = NULL;
        return HDF_FAILURE;
    }

    ret = snd_mixer_load(cardIns->mixerHandle);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Failed to load mixer element: %{public}s.", snd_strerror(ret));
        ret = snd_mixer_close(cardIns->mixerHandle);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("mixer close error: %{public}s.", snd_strerror(ret));
        }
        cardIns->mixerHandle = NULL;
        return HDF_FAILURE;
    }
    return HDF_SUCCESS;
}

snd_pcm_state_t SndGetRunState(struct AlsaSoundCard * cardIns)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    return snd_pcm_state(cardIns->pcmHandle);
}

void SndCloseHandle(struct AlsaSoundCard *cardIns)
{
    if (cardIns == NULL) {
        AUDIO_FUNC_LOGE("cardIns is NULL");
        return;
    }
    if (cardIns->cardStatus > 0) {
        cardIns->cardStatus -= 1;
    }
    if (cardIns->cardStatus == 0) {
        int32_t ret;
        if (cardIns->pcmHandle != NULL) {
            ret = snd_pcm_close(cardIns->pcmHandle);
            if (ret < 0) {
                AUDIO_FUNC_LOGE("snd_pcm_close fail: %{public}s", snd_strerror(ret));
            }
            cardIns->pcmHandle = NULL;
        }
        if (cardIns->mixerHandle != NULL) {
            ret = snd_mixer_close(cardIns->mixerHandle);
            if (ret < 0) {
                AUDIO_FUNC_LOGE("mixer close error: %{public}s.", snd_strerror(ret));
            }
            cardIns->mixerHandle = NULL;
        }
        (void)memset_s(cardIns, sizeof(struct AlsaSoundCard), 0, sizeof(struct AlsaSoundCard));
    }
}

static void AudioInitPortOut(struct AudioPort *audioPort)
{
    audioPort->dir = PORT_OUT;
    audioPort->portId = 0;
    audioPort->portName = strdup("AOP");
}

static void AudioInitPortIn(struct AudioPort *audioPort)
{
    audioPort->dir = PORT_IN;
    audioPort->portId = 0;
    audioPort->portName = strdup("AIP");
}

static void AudioInitPortOutAndIn(struct AudioPort *audioPort)
{
    audioPort->dir = PORT_OUT_IN;
    audioPort->portId = 0;
    audioPort->portName = strdup("AIOP");
}

static int32_t AudioInitPorts(struct AudioAdapterDescriptor *desc, enum SndCardType type)
{
    uint8_t portNum = 0;
    CHECK_NULL_PTR_RETURN_DEFAULT(desc);

    switch (type) {
        case SND_CARD_PRIMARY:
            portNum = PORT_OUT_IN;
            break;
        case SND_CARD_HDMI:
            portNum = PORT_OUT;
            break;
        case SND_CARD_USB:
            portNum = PORT_IN;
            break;
        default:
            AUDIO_FUNC_LOGE("Unknown sound card type does not support this sound card temporarily!");
            return HDF_FAILURE;
    }

#ifndef AUDIO_HDI_SERVICE_MODE
        desc->portNum = portNum;
#else
        desc->portsLen = portNum;
#endif
    if (portNum == 0) {
        AUDIO_FUNC_LOGE("portNum is zero");
        return HDF_FAILURE;
    }
    desc->ports = (struct AudioPort *)OsalMemCalloc(sizeof(struct AudioPort) * portNum);
    if (desc->ports == NULL) {
        AUDIO_FUNC_LOGE("OsalMemCalloc failed!");
        return HDF_ERR_MALLOC_FAIL;
    }

    if (type == SND_CARD_PRIMARY) {
        AudioInitPortOut(&desc->ports[0]);
        AudioInitPortIn(&desc->ports[SUPPORT_CAPTURE_OR_RENDER]);
        AudioInitPortOutAndIn(&desc->ports[SUPPORT_CAPTURE_AND_RENDER]);
    } else if (type == SND_CARD_HDMI) {
        AudioInitPortOut(&desc->ports[0]);
    } else if (type == SND_CARD_USB) {
        AudioInitPortOut(&desc->ports[0]);
        AudioInitPortIn(&desc->ports[SUPPORT_CAPTURE_OR_RENDER]);
    } else {
        AUDIO_FUNC_LOGE("adapter list not support sound card type %{public}d", type);
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

int32_t AudioGetAllCardInfo(struct AudioAdapterDescriptor **descs, int32_t *sndCardNum)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(descs);
    CHECK_NULL_PTR_RETURN_DEFAULT(sndCardNum);

    int32_t dev = -1;
    int32_t ret = SndSaveCardListInfo(SND_PCM_STREAM_PLAYBACK, dev);
    if (ret != HDF_SUCCESS) {
        return HDF_FAILURE;
    }

    int32_t adapterNum = CfgGetAdapterCount();
    if (*descs == NULL && adapterNum > 0 && adapterNum < MALLOC_MAX) {
        AUDIO_FUNC_LOGW("*descs is null, need memcalloc.");
        *descs = (struct AudioAdapterDescriptor *)OsalMemCalloc(sizeof(struct AudioAdapterDescriptor) * adapterNum);
        if (*descs == NULL) {
            AUDIO_FUNC_LOGE("OsalMemCalloc descs is NULL");
            return HDF_ERR_MALLOC_FAIL;
        }
    }
    *sndCardNum = adapterNum;

    int32_t idx = 0;
    for (enum SndCardType type = SND_CARD_PRIMARY; type < SND_CARD_MAX; ++type) {
        for (int32_t i = 0; i < g_alsaAdapterList[type].num; ++i) {
            (*descs)[idx].adapterName = strdup(g_alsaAdapterList[type].list[i].adapterName);
            AudioInitPorts(&(*descs)[idx], type);
            AUDIO_FUNC_LOGI("adapter name : %{public}s", (*descs)[idx].adapterName);
            idx++;
        }
    }

    return HDF_SUCCESS;
}

struct HdfIoService *HdfIoServiceBindName(const char *serviceName)
{
    (void)serviceName;
    /* Nothing to do */
    static struct HdfIoService hdfIoService;
    return &hdfIoService;
}

struct DevHandle *AudioBindService(const char *name)
{
    struct DevHandle *handle = NULL;

    if (name == NULL) {
        AUDIO_FUNC_LOGE("service name NULL!");
        return NULL;
    }

    handle = (struct DevHandle *)OsalMemCalloc(sizeof(struct DevHandle));
    if (handle == NULL) {
        AUDIO_FUNC_LOGE("OsalMemCalloc handle failed!!!");
        return NULL;
    }

    AUDIO_FUNC_LOGI("BIND SERVICE SUCCESS!");
    return handle;
}

void AudioCloseService(const struct DevHandle *handle)
{
    if (handle != NULL) {
        AudioMemFree((void **)&handle);
    }
}

void SndElementItemInit(struct AlsaMixerCtlElement *m)
{
    m->iface = IFACE_MIXER;
    m->index = 0;
    m->device = 0;
    m->subdevice = 0;
}

static snd_ctl_elem_iface_t ConvertIfaceType(enum SndIfaceType iface)
{
    snd_ctl_elem_iface_t snd_iface;
    switch (iface) {
        case IFACE_CARD:
            snd_iface = SND_CTL_ELEM_IFACE_CARD;
            break;
        case IFACE_MIXER:
            snd_iface = SND_CTL_ELEM_IFACE_MIXER;
            break;
        case IFACE_PCM:
            snd_iface = SND_CTL_ELEM_IFACE_PCM;
            break;
        case IFACE_RAWMIDI:
            snd_iface = SND_CTL_ELEM_IFACE_RAWMIDI;
            break;
        case IFACE_TIMER:
            snd_iface = SND_CTL_ELEM_IFACE_TIMER;
            break;
        case IFACE_SEQUENCER:
            snd_iface = SND_CTL_ELEM_IFACE_SEQUENCER;
            break;
        default:
            snd_iface = SND_CTL_ELEM_IFACE_MIXER;
            break;
    }
    return snd_iface;
}

static int32_t SetElementInfo(snd_ctl_t *alsaHandle, const struct AlsaMixerCtlElement *ctlElem,
    snd_ctl_elem_info_t *info, snd_ctl_elem_id_t *id)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(alsaHandle);
    CHECK_NULL_PTR_RETURN_DEFAULT(ctlElem);
    CHECK_NULL_PTR_RETURN_DEFAULT(info);
    CHECK_NULL_PTR_RETURN_DEFAULT(id);

    if (ctlElem->numid >= 0) {
        snd_ctl_elem_id_set_numid(id, ctlElem->numid);
    }
    if (ctlElem->index >= 0) {
        snd_ctl_elem_id_set_index(id, ctlElem->index);
    }
    if (ctlElem->device >= 0) {
        snd_ctl_elem_id_set_device(id, ctlElem->device);
    }
    if (ctlElem->subdevice >= 0) {
        snd_ctl_elem_id_set_subdevice(id, ctlElem->subdevice);
    }

    snd_ctl_elem_iface_t ifaceType = ConvertIfaceType(ctlElem->iface);
    snd_ctl_elem_id_set_interface(id, ifaceType);
    if (ctlElem->name) {
        snd_ctl_elem_id_set_name(id, ctlElem->name);
    }
    snd_ctl_elem_info_set_id(info, id);
    int32_t ret = snd_ctl_elem_info(alsaHandle, info);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Cannot find the given element from elem_value ret: %{public}d, reson: %{public}s",
            ret, snd_strerror(ret));
        return HDF_FAILURE;
    }
    snd_ctl_elem_info_get_id(info, id);

    return HDF_SUCCESS;
}

int32_t SndElementReadInt(struct AlsaSoundCard *cardIns,
    const struct AlsaMixerCtlElement *ctlElem, long *value)
{
    int ret;
    static snd_ctl_t *alsaHandle = NULL;
    snd_ctl_elem_id_t *elem_id = NULL;
    snd_ctl_elem_info_t *elem_info = NULL;
    snd_ctl_elem_value_t *elem_value = NULL;

    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(ctlElem);

    if (alsaHandle == NULL) {
        ret = snd_ctl_open(&alsaHandle, cardIns->ctrlName, 0);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("snd_ctl_open error: %{public}s", snd_strerror(ret));
            return HDF_FAILURE;
        }
    }

    snd_ctl_elem_id_alloca(&elem_id);
    snd_ctl_elem_info_alloca(&elem_info);
    snd_ctl_elem_value_alloca(&elem_value);
    ret = SetElementInfo(alsaHandle, ctlElem, elem_info, elem_id);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Set element %{public}s elem_info failed!\n", ctlElem->name);
        return HDF_FAILURE;
    }
    snd_ctl_elem_value_set_id(elem_value, elem_id);

    if (!snd_ctl_elem_info_is_readable(elem_info)) {
        AUDIO_FUNC_LOGE("Element read enable\n");
        return HDF_FAILURE;
    }
    ret = snd_ctl_elem_read(alsaHandle, elem_value);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Cannot read the given element from elem_value \n");
        return HDF_FAILURE;
    }

    snd_ctl_elem_type_t type = snd_ctl_elem_info_get_type(elem_info);
    if (type == SND_CTL_ELEM_TYPE_INTEGER) {
        *value = snd_ctl_elem_value_get_integer(elem_value, 0);
    } else if (type == SND_CTL_ELEM_TYPE_INTEGER64) {
        *value = (long)snd_ctl_elem_value_get_integer64(elem_value, 0);
    } else {
        AUDIO_FUNC_LOGE("Element type is not interger\n");
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

int32_t SndElementReadEnum(
    struct AlsaSoundCard *cardIns, const struct AlsaMixerCtlElement *ctlElem, unsigned int *item)
{
    snd_ctl_t *alsaHandle = NULL;
    snd_ctl_elem_id_t *elem_id = NULL;
    snd_ctl_elem_info_t *elem_info = NULL;
    snd_ctl_elem_value_t *elem_value = NULL;

    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(ctlElem);

    int ret = snd_ctl_open(&alsaHandle, cardIns->ctrlName, 0);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_ctl_open error: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }

    snd_ctl_elem_id_alloca(&elem_id);
    snd_ctl_elem_info_alloca(&elem_info);
    snd_ctl_elem_value_alloca(&elem_value);
    ret = SetElementInfo(alsaHandle, ctlElem, elem_info, elem_id);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Set element %{public}s elem_info failed!\n", ctlElem->name);
        return HDF_FAILURE;
    }
    snd_ctl_elem_value_set_id(elem_value, elem_id);

    if (!snd_ctl_elem_info_is_readable(elem_info)) {
        AUDIO_FUNC_LOGE("Element read enable\n");
        return HDF_FAILURE;
    }
    ret = snd_ctl_elem_read(alsaHandle, elem_value);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Cannot read the given element from elem_value \n");
        return HDF_FAILURE;
    }

    snd_ctl_elem_type_t type = snd_ctl_elem_info_get_type(elem_info);
    if (type == SND_CTL_ELEM_TYPE_ENUMERATED) {
        *item = snd_ctl_elem_value_get_enumerated(elem_value, 0);
    } else {
        AUDIO_FUNC_LOGE("Element type is not enumerated\n");
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

int32_t SndElementReadRange(
    struct AlsaSoundCard * cardIns, const struct AlsaMixerCtlElement * ctlElem, long * mix, long * max)
{
    snd_ctl_t *alsaHandle = NULL;
    snd_ctl_elem_id_t *elem_id = NULL;
    snd_ctl_elem_info_t *elem_info = NULL;
    snd_ctl_elem_value_t *elem_value = NULL;

    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(ctlElem);

    int ret = snd_ctl_open(&alsaHandle, cardIns->ctrlName, 0);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_ctl_open error: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }

    snd_ctl_elem_id_alloca(&elem_id);
    snd_ctl_elem_info_alloca(&elem_info);
    snd_ctl_elem_value_alloca(&elem_value);
    ret = SetElementInfo(alsaHandle, ctlElem, elem_info, elem_id);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Set element %{public}s elem_info failed!\n", ctlElem->name);
        return HDF_FAILURE;
    }
    snd_ctl_elem_value_set_id(elem_value, elem_id);

    if (!snd_ctl_elem_info_is_readable(elem_info)) {
        AUDIO_FUNC_LOGE("Element read enable\n");
        return HDF_FAILURE;
    }
    ret = snd_ctl_elem_read(alsaHandle, elem_value);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Cannot read the given element from elem_value \n");
        return HDF_FAILURE;
    }

    snd_ctl_elem_type_t type = snd_ctl_elem_info_get_type(elem_info);
    if (type == SND_CTL_ELEM_TYPE_INTEGER) {
        *mix = snd_ctl_elem_info_get_min(elem_info);
        *max = snd_ctl_elem_info_get_max(elem_info);
    } else if (type == SND_CTL_ELEM_TYPE_INTEGER64) {
        *mix = (long)snd_ctl_elem_info_get_min64(elem_info);
        *max = (long)snd_ctl_elem_info_get_max64(elem_info);
    } else {
        AUDIO_FUNC_LOGE("Element value is not integer type!\n");
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

int32_t SndElementReadSwitch(
    struct AlsaSoundCard *cardIns, const struct AlsaMixerCtlElement *ctlElem, bool *on)
{
    snd_ctl_t *alsaHandle = NULL;
    snd_ctl_elem_id_t *elem_id = NULL;
    snd_ctl_elem_info_t *elem_info = NULL;
    snd_ctl_elem_value_t *elem_value = NULL;

    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(ctlElem);

    int ret = snd_ctl_open(&alsaHandle, cardIns->ctrlName, 0);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_ctl_open error: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }

    snd_ctl_elem_id_alloca(&elem_id);
    snd_ctl_elem_info_alloca(&elem_info);
    snd_ctl_elem_value_alloca(&elem_value);
    ret = SetElementInfo(alsaHandle, ctlElem, elem_info, elem_id);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Set element %{public}s elem_info failed!\n", ctlElem->name);
        return HDF_FAILURE;
    }
    snd_ctl_elem_value_set_id(elem_value, elem_id);

    if (!snd_ctl_elem_info_is_readable(elem_info)) {
        AUDIO_FUNC_LOGE("Element read enable\n");
        return HDF_FAILURE;
    }
    ret = snd_ctl_elem_read(alsaHandle, elem_value);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Cannot read the given element from elem_value \n");
        return HDF_FAILURE;
    }

    snd_ctl_elem_type_t type = snd_ctl_elem_info_get_type(elem_info);
    if (type == SND_CTL_ELEM_TYPE_BOOLEAN) {
        ret = snd_ctl_elem_value_get_boolean(elem_value, 0);
        *on = (ret > 0) ? true : false;
    } else {
        AUDIO_FUNC_LOGE("Element type is not boolean\n");
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

int32_t SndElementWriteInt(
    struct AlsaSoundCard *cardIns, const struct AlsaMixerCtlElement *ctlElem, long value)
{
    snd_ctl_t *alsaHandle = NULL;
    snd_ctl_elem_id_t *elem_id = NULL;
    snd_ctl_elem_info_t *elem_info = NULL;
    snd_ctl_elem_value_t *elem_value = NULL;

    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(ctlElem);

    int ret = snd_ctl_open(&alsaHandle, cardIns->ctrlName, 0);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_ctl_open error: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }

    snd_ctl_elem_id_alloca(&elem_id);
    snd_ctl_elem_info_alloca(&elem_info);
    snd_ctl_elem_value_alloca(&elem_value);
    ret = SetElementInfo(alsaHandle, ctlElem, elem_info, elem_id);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Set element %{public}s elem_info failed!\n", ctlElem->name);
        return HDF_FAILURE;
    }

    if (!snd_ctl_elem_info_is_writable(elem_info)) {
        AUDIO_FUNC_LOGE("Element write enable\n");
        return HDF_FAILURE;
    }

    snd_ctl_elem_value_set_id(elem_value, elem_id);
    snd_ctl_elem_type_t type = snd_ctl_elem_info_get_type(elem_info);
    if (type == SND_CTL_ELEM_TYPE_INTEGER) {
        snd_ctl_elem_value_set_integer(elem_value, 0, value);
    } else if (type == SND_CTL_ELEM_TYPE_INTEGER64) {
        snd_ctl_elem_value_set_integer64(elem_value, 0, (long long)value);
    } else {
        AUDIO_FUNC_LOGE("Element value is not integer type!\n");
        return HDF_FAILURE;
    }

    ret = snd_ctl_elem_write(alsaHandle, elem_value);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_ctl_elem_write failed!\n");
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

int32_t SndElementWriteEnum(
    struct AlsaSoundCard *cardIns, const struct AlsaMixerCtlElement *ctlElem, unsigned int item)
{
    snd_ctl_t *alsaHandle = NULL;
    snd_ctl_elem_id_t *elem_id = NULL;
    snd_ctl_elem_info_t *elem_info = NULL;
    snd_ctl_elem_value_t *elem_value = NULL;

    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(ctlElem);

    int ret = snd_ctl_open(&alsaHandle, cardIns->ctrlName, 0);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_ctl_open error: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }

    snd_ctl_elem_id_alloca(&elem_id);
    snd_ctl_elem_info_alloca(&elem_info);
    snd_ctl_elem_value_alloca(&elem_value);
    ret = SetElementInfo(alsaHandle, ctlElem, elem_info, elem_id);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Set element %{public}s elem_info failed!\n", ctlElem->name);
        return HDF_FAILURE;
    }

    if (!snd_ctl_elem_info_is_writable(elem_info)) {
        AUDIO_FUNC_LOGE("Element write enable\n");
        return HDF_FAILURE;
    }

    snd_ctl_elem_value_set_id(elem_value, elem_id);
    snd_ctl_elem_type_t type = snd_ctl_elem_info_get_type(elem_info);
    if (type == SND_CTL_ELEM_TYPE_ENUMERATED) {
        snd_ctl_elem_value_set_enumerated(elem_value, 0, item);
    } else {
        AUDIO_FUNC_LOGE("Element value is not enum type!\n");
        return HDF_FAILURE;
    }

    ret = snd_ctl_elem_write(alsaHandle, elem_value);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_ctl_elem_write failed!\n");
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

int32_t SndElementWriteSwitch(
    struct AlsaSoundCard *cardIns, const struct AlsaMixerCtlElement *ctlElem, bool on)
{
    snd_ctl_t *alsaHandle = NULL;
    snd_ctl_elem_id_t *elem_id;
    snd_ctl_elem_info_t *elem_info;
    snd_ctl_elem_value_t *elem_value;

    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(ctlElem);

    int ret = snd_ctl_open(&alsaHandle, cardIns->ctrlName, 0);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_ctl_open error: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }

    snd_ctl_elem_id_alloca(&elem_id);
    snd_ctl_elem_info_alloca(&elem_info);
    snd_ctl_elem_value_alloca(&elem_value);
    ret = SetElementInfo(alsaHandle, ctlElem, elem_info, elem_id);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Set element %{public}s elem_info failed!\n", ctlElem->name);
        return HDF_FAILURE;
    }

    if (!snd_ctl_elem_info_is_writable(elem_info)) {
        AUDIO_FUNC_LOGE("Element write enable\n");
        return HDF_FAILURE;
    }

    snd_ctl_elem_value_set_id(elem_value, elem_id);
    snd_ctl_elem_type_t type = snd_ctl_elem_info_get_type(elem_info);
    if (type == SND_CTL_ELEM_TYPE_BOOLEAN) {
        int value = on ? 1 : 0;
        snd_ctl_elem_value_set_boolean(elem_value, 0, value);
    } else {
        AUDIO_FUNC_LOGE("Element value is not boolean type!\n");
        return HDF_FAILURE;
    }

    ret = snd_ctl_elem_write(alsaHandle, elem_value);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_ctl_elem_write failed!\n");
        return HDF_FAILURE;
    }

    return HDF_SUCCESS;
}

int32_t SndElementWrite(
    struct AlsaSoundCard *cardIns, const struct AlsaMixerCtlElement *ctlElem)
{
    snd_ctl_t *alsaHandle = NULL;
    snd_ctl_elem_id_t *elem_id = NULL;
    snd_ctl_elem_info_t *elem_info = NULL;
    snd_ctl_elem_value_t *elem_value = NULL;

    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(ctlElem);

    int ret = snd_ctl_open(&alsaHandle, cardIns->ctrlName, 0);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("snd_ctl_open error: %{public}s", snd_strerror(ret));
        return HDF_FAILURE;
    }

    snd_ctl_elem_id_alloca(&elem_id);
    snd_ctl_elem_info_alloca(&elem_info);
    snd_ctl_elem_value_alloca(&elem_value);
    ret = SetElementInfo(alsaHandle, ctlElem, elem_info, elem_id);
    if (ret != HDF_SUCCESS) {
        AUDIO_FUNC_LOGE("Set element %{public}s elem_info failed!\n", ctlElem->name);
        return HDF_FAILURE;
    }

    snd_ctl_elem_value_set_id(elem_value, elem_id);
    ret = snd_ctl_elem_read(alsaHandle, elem_value);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Control parse error: %s, ret : %{public}d", snd_strerror(ret), ret);
        return HDF_FAILURE;
    }

    ret = snd_ctl_ascii_value_parse(alsaHandle, elem_value, elem_info, ctlElem->value);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Control parse error: %s\n", snd_strerror(ret));
        (void)snd_ctl_close(alsaHandle);
        alsaHandle = NULL;
        return HDF_FAILURE;
    }
    ret = snd_ctl_elem_write(alsaHandle, elem_value);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Control element write error: %s\n", snd_strerror(ret));
        AUDIO_FUNC_LOGE("Control element write error: %{public}s\n", snd_strerror(ret));
        (void)snd_ctl_close(alsaHandle);
        alsaHandle = NULL;
        return HDF_FAILURE;
    }

    (void)snd_ctl_close(alsaHandle);
    alsaHandle = NULL;

    return HDF_SUCCESS;
}

int32_t SndElementGroupWrite(
    struct AlsaSoundCard *cardIns, const struct AlsaMixerCtlElement* elemGroup, int32_t groupSize)
{
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);

    for (int i = 0; i < groupSize; ++i) {
        int err = SndElementWrite(cardIns, &elemGroup[i]);
        if (err < 0) {
            AUDIO_FUNC_LOGE("Cant't set element %{public}s", elemGroup[i].name);
        }
    }

    return HDF_SUCCESS;
}

int32_t SndTraversalMixerElement(struct AlsaSoundCard *cardIns,
    bool (*callback)(void *data, snd_ctl_elem_id_t *elem_id), void *data)
{
    snd_hctl_t *handle = NULL;
    snd_hctl_elem_t *elem = NULL;
    snd_ctl_elem_id_t *elem_id = NULL;
    snd_ctl_elem_info_t *elem_info = NULL;
    CHECK_NULL_PTR_RETURN_DEFAULT(cardIns);
    CHECK_NULL_PTR_RETURN_DEFAULT(callback);

    int ret = snd_hctl_open(&handle, cardIns->ctrlName, 0);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Control %{public}s open error: %{public}s",
            cardIns->ctrlName, snd_strerror(ret));
        return HDF_FAILURE;
    }
    ret = snd_hctl_load(handle);
    if (ret < 0) {
        AUDIO_FUNC_LOGE("Control %{public}s local error: %{public}s\n",
            cardIns->ctrlName, snd_strerror(ret));
        return HDF_FAILURE;
    }

    snd_ctl_elem_id_alloca(&elem_id);
    snd_ctl_elem_info_alloca(&elem_info);
    for (elem = snd_hctl_first_elem(handle); elem; elem = snd_hctl_elem_next(elem)) {
        ret = snd_hctl_elem_info(elem, elem_info);
        if (ret < 0) {
            AUDIO_FUNC_LOGE("Control %{public}s snd_hctl_elem_info error: %{public}s\n",
                cardIns->ctrlName, snd_strerror(ret));
            return HDF_FAILURE;
        }
        if (snd_ctl_elem_info_is_inactive(elem_info)) {
            continue;
        }
        snd_hctl_elem_get_id(elem, elem_id);
        if (callback(data, elem_id)) {
            (void)snd_hctl_close(handle);
            return HDF_SUCCESS;
        }
    }
    (void)snd_hctl_close(handle);
    return HDF_FAILURE;
}
