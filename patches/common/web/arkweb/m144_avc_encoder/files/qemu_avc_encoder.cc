// Copyright (c) 2026 Harmony Contrib
// SPDX-License-Identifier: Apache-2.0
// Adapter for the fixed OHOS 7.0 AVC wrapper, using pinned M144 OpenH264.
#include <cstdint>
#include <climits>
#include <cstdlib>
#include <cstring>
#include <pthread.h>

#include "AvcEnc_Typedef.h"
#include "wels/codec_api.h"

namespace {
constexpr uint32_t kSuccess = 0;
constexpr uint32_t kError = 1;
constexpr uint32_t kMinDimension = 64;
constexpr uint32_t kMaxDimension = 2560;
constexpr uint32_t kMinBitrate = 10000;
constexpr uint32_t kMaxBitrate = 30000000;
constexpr uint32_t kMaxFrameRate = 60;
constexpr uint32_t kMaxBlocksPerSecond = 983040;
constexpr uint32_t kMaxQp = 51;
constexpr uint32_t kIFrame = 3;
constexpr uint32_t kPFrame = 1;
constexpr uint32_t kCodecData = 0;

struct Encoder {
    ISVCEncoder *codec;
    pthread_mutex_t mutex;
    uint32_t width;
    uint32_t height;
    uint32_t bitrate;
    bool headerSent;
    bool ended;
};

bool ValidInit(const AVC_ENC_INIT_PARAM &param)
{
    const uint64_t blocks = ((static_cast<uint64_t>(param.width) + 15) / 16) *
        ((static_cast<uint64_t>(param.height) + 15) / 16);
    return param.width >= kMinDimension && param.width <= kMaxDimension && param.width % 2 == 0 &&
        param.height >= kMinDimension && param.height <= kMaxDimension && param.height % 2 == 0 &&
        param.frameRate >= 1 && param.frameRate <= kMaxFrameRate &&
        blocks * param.frameRate <= kMaxBlocksPerSecond &&
        param.bitrate >= kMinBitrate && param.bitrate <= kMaxBitrate &&
        param.qp <= kMaxQp && param.qpMin <= param.qpMax && param.qpMax <= kMaxQp &&
        (param.encMode == MODE_CQP || param.encMode == MODE_CBR || param.encMode == MODE_VBR) &&
        (param.profile == PROFILE_BASE || param.profile == PROFILE_MAIN) && param.colorFmt == YUV_420P &&
        param.range <= 1;
}

void Configure(const AVC_ENC_INIT_PARAM &input, SEncParamExt &params)
{
    params.iUsageType = CAMERA_VIDEO_REAL_TIME;
    params.iPicWidth = static_cast<int>(input.width);
    params.iPicHeight = static_cast<int>(input.height);
    params.fMaxFrameRate = static_cast<float>(input.frameRate);
    params.iTargetBitrate = static_cast<int>(input.bitrate);
    params.iMaxBitrate = static_cast<int>(kMaxBitrate);
    params.iRCMode = input.encMode == MODE_CQP ? RC_OFF_MODE :
        (input.encMode == MODE_CBR ? RC_BITRATE_MODE : RC_QUALITY_MODE);
    params.iTemporalLayerNum = 1;
    params.iSpatialLayerNum = 1;
    params.uiIntraPeriod = input.iperiod == 0 ? 1 : input.iperiod;
    params.iEntropyCodingModeFlag = input.profile == PROFILE_MAIN ? 1 : 0;
    params.bEnableFrameSkip = false;
    params.bEnableSSEI = false;
    params.bPrefixNalAddingCtrl = false;
    params.iMultipleThreadIdc = 1;
    params.iMinQp = static_cast<int>(input.qpMin);
    params.iMaxQp = static_cast<int>(input.qpMax);
    auto &layer = params.sSpatialLayers[0];
    layer.iVideoWidth = params.iPicWidth;
    layer.iVideoHeight = params.iPicHeight;
    layer.fFrameRate = params.fMaxFrameRate;
    layer.iSpatialBitrate = params.iTargetBitrate;
    layer.iMaxSpatialBitrate = params.iMaxBitrate;
    layer.uiProfileIdc = input.profile == PROFILE_MAIN ? PRO_MAIN : PRO_BASELINE;
    layer.uiLevelIdc = static_cast<ELevelIdc>(input.level);
    layer.iDLayerQp = static_cast<int>(input.qp);
    layer.sSliceArgument.uiSliceMode = SM_SINGLE_SLICE;
    layer.bVideoSignalTypePresent = true;
    layer.uiVideoFormat = 5; // H.264 unspecified video format.
    layer.bFullRange = input.range != 0;
    layer.bColorDescriptionPresent = true;
    layer.uiColorPrimaries = input.primaries;
    layer.uiTransferCharacteristics = input.transfer;
    layer.uiColorMatrix = input.matrix;
}

bool CopyAccessUnit(const SFrameBSInfo &frame, AVC_ENC_OUTARGS &output)
{
    if (frame.iLayerNum <= 0 || frame.iLayerNum > MAX_LAYER_NUM_OF_FRAME) {
        return false;
    }
    uint64_t total = 0;
    for (int index = 0; index < frame.iLayerNum; ++index) {
        const auto &layer = frame.sLayerInfo[index];
        if (layer.iNalCount <= 0 || layer.iNalCount > MAX_NAL_UNITS_IN_LAYER ||
            layer.pNalLengthInByte == nullptr || layer.pBsBuf == nullptr) {
            return false;
        }
        for (int nal = 0; nal < layer.iNalCount; ++nal) {
            if (layer.pNalLengthInByte[nal] <= 0) return false;
            total += static_cast<uint32_t>(layer.pNalLengthInByte[nal]);
            if (total > output.size) return false;
        }
    }
    if (total == 0 || total > UINT32_MAX) return false;
    auto *destination = static_cast<uint8_t *>(output.streamBuf);
    uint32_t offset = 0;
    for (int index = 0; index < frame.iLayerNum; ++index) {
        const auto &layer = frame.sLayerInfo[index];
        uint32_t length = 0;
        for (int nal = 0; nal < layer.iNalCount; ++nal) {
            length += static_cast<uint32_t>(layer.pNalLengthInByte[nal]);
        }
        std::memcpy(destination + offset, layer.pBsBuf, length);
        offset += length;
    }
    output.bytes = offset;
    return true;
}

bool EmptyInput(const AVC_ENC_INARGS &input)
{
    for (uint32_t plane = 0; plane < IV_MAX_RAW_COMPONENTS; ++plane) {
        if (input.inputBufs[plane] != nullptr || input.width[plane] != 0 || input.height[plane] != 0 ||
            input.stride[plane] != 0) return false;
    }
    return true;
}

bool ValidPicture(const Encoder &encoder, const AVC_ENC_INARGS &input)
{
    if (input.colorFmt != YUV_420P || input.configArgs.idrRequest > 1 ||
        input.configArgs.bitrate < kMinBitrate || input.configArgs.bitrate > kMaxBitrate) return false;
    for (uint32_t plane = 0; plane < 3; ++plane) {
        const uint32_t width = plane == 0 ? encoder.width : encoder.width / 2;
        const uint32_t height = plane == 0 ? encoder.height : encoder.height / 2;
        if (input.inputBufs[plane] == nullptr || input.width[plane] != width || input.height[plane] != height ||
            input.stride[plane] < width || input.stride[plane] > INT32_MAX ||
            static_cast<uint64_t>(input.stride[plane]) * height > SIZE_MAX) return false;
    }
    return input.inputBufs[3] == nullptr;
}

bool EncodePicture(Encoder &encoder, const AVC_ENC_INARGS &input, AVC_ENC_OUTARGS &output)
{
    if (!ValidPicture(encoder, input)) return false;
    if (input.configArgs.bitrate != encoder.bitrate) {
        SBitrateInfo bitrate = {SPATIAL_LAYER_ALL, static_cast<int>(input.configArgs.bitrate)};
        if (encoder.codec->SetOption(ENCODER_OPTION_BITRATE, &bitrate) != cmResultSuccess) return false;
        encoder.bitrate = input.configArgs.bitrate;
    }
    if (input.configArgs.idrRequest != 0 && encoder.codec->ForceIntraFrame(true) != cmResultSuccess) return false;
    SSourcePicture picture = {};
    picture.iColorFormat = videoFormatI420;
    picture.iPicWidth = static_cast<int>(encoder.width);
    picture.iPicHeight = static_cast<int>(encoder.height);
    picture.uiTimeStamp = static_cast<long long>(input.timestamp / 1000);
    for (uint32_t plane = 0; plane < 3; ++plane) {
        picture.pData[plane] = static_cast<uint8_t *>(input.inputBufs[plane]);
        picture.iStride[plane] = static_cast<int>(input.stride[plane]);
    }
    SFrameBSInfo frame = {};
    if (encoder.codec->EncodeFrame(&picture, &frame) != cmResultSuccess ||
        frame.eFrameType == videoFrameTypeSkip || !CopyAccessUnit(frame, output)) return false;
    output.encodedFrameType = frame.eFrameType == videoFrameTypeIDR || frame.eFrameType == videoFrameTypeI ?
        kIFrame : kPFrame;
    output.timestamp = input.timestamp;
    return true;
}

bool Encode(Encoder &encoder, const AVC_ENC_INARGS &input, AVC_ENC_OUTARGS &output)
{
    if (encoder.ended) return false;
    if (EmptyInput(input)) {
        if (encoder.headerSent) {
            // The pinned encoder uses no delayed/B frames. This is the wrapper's EOS call.
            encoder.ended = true;
            output.isLast = 1;
            return true;
        }
        SFrameBSInfo headers = {};
        if (encoder.codec->EncodeParameterSets(&headers) != cmResultSuccess || !CopyAccessUnit(headers, output)) {
            return false;
        }
        encoder.headerSent = true;
        output.encodedFrameType = kCodecData;
        return true;
    }
    return encoder.headerSent && EncodePicture(encoder, input, output);
}
} // namespace

extern "C" __attribute__((visibility("default")))
uint32_t InitEncoder(AVC_ENC_HANDLE *handle, AVC_ENC_INIT_PARAM *input)
{
    if (handle == nullptr || input == nullptr || !ValidInit(*input)) return kError;
    *handle = nullptr;
    auto *encoder = static_cast<Encoder *>(std::calloc(1, sizeof(Encoder)));
    if (encoder == nullptr) return kError;
    if (pthread_mutex_init(&encoder->mutex, nullptr) != 0) {
        std::free(encoder);
        return kError;
    }
    SEncParamExt params = {};
    bool initialized = WelsCreateSVCEncoder(&encoder->codec) == cmResultSuccess && encoder->codec != nullptr &&
        encoder->codec->GetDefaultParams(&params) == cmResultSuccess;
    if (initialized) {
        Configure(*input, params);
        initialized = encoder->codec->InitializeExt(&params) == cmResultSuccess;
    }
    if (!initialized) {
        if (encoder->codec != nullptr) WelsDestroySVCEncoder(encoder->codec);
        pthread_mutex_destroy(&encoder->mutex);
        std::free(encoder);
        return kError;
    }
    encoder->width = input->width;
    encoder->height = input->height;
    encoder->bitrate = input->bitrate;
    *handle = encoder;
    return kSuccess;
}

extern "C" __attribute__((visibility("default")))
uint32_t EncodeProcess(AVC_ENC_HANDLE handle, AVC_ENC_INARGS *input, AVC_ENC_OUTARGS *output)
{
    if (handle == nullptr || input == nullptr || output == nullptr || output->streamBuf == nullptr || output->size == 0) {
        return kError;
    }
    output->bytes = 0;
    output->isLast = 0;
    output->timestamp = 0;
    output->encodedFrameType = kCodecData;
    auto &encoder = *static_cast<Encoder *>(handle);
    if (pthread_mutex_lock(&encoder.mutex) != 0) return kError;
    const bool success = Encode(encoder, *input, *output);
    pthread_mutex_unlock(&encoder.mutex);
    return success ? kSuccess : kError;
}

extern "C" __attribute__((visibility("default")))
uint32_t ReleaseEncoder(AVC_ENC_HANDLE handle)
{
    if (handle == nullptr) return kError;
    auto *encoder = static_cast<Encoder *>(handle);
    // The OHOS wrapper serializes encoding/release with encRunMutex_.
    if (pthread_mutex_lock(&encoder->mutex) != 0) return kError;
    encoder->codec->Uninitialize();
    WelsDestroySVCEncoder(encoder->codec);
    pthread_mutex_unlock(&encoder->mutex);
    pthread_mutex_destroy(&encoder->mutex);
    std::free(encoder);
    return kSuccess;
}
