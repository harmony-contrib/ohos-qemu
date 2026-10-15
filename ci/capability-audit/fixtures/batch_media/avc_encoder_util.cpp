/*
 * Copyright (C) 2025 Huawei Device Co., Ltd.
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

#include "avcodec_log.h"
#include "avcodec_trace.h"
#include "avc_encoder_util.h"

namespace OHOS {
namespace MediaAVCodec {
namespace Codec {

namespace {
constexpr OHOS::HiviewDFX::HiLogLabel LABEL = {LOG_CORE, LOG_DOMAIN_FRAMEWORK, "AvcEncoder"};

std::map<AVCLevel, H264Level> g_encodeLevelMap = {
    { AVCLevel::AVC_LEVEL_1,  H264Level::H264_LEVEL_10 },
    { AVCLevel::AVC_LEVEL_1b, H264Level::H264_LEVEL_1B },
    { AVCLevel::AVC_LEVEL_11, H264Level::H264_LEVEL_11 },
    { AVCLevel::AVC_LEVEL_12, H264Level::H264_LEVEL_12 },
    { AVCLevel::AVC_LEVEL_13, H264Level::H264_LEVEL_13 },
    { AVCLevel::AVC_LEVEL_2,  H264Level::H264_LEVEL_20 },
    { AVCLevel::AVC_LEVEL_21, H264Level::H264_LEVEL_21 },
    { AVCLevel::AVC_LEVEL_22, H264Level::H264_LEVEL_22 },
    { AVCLevel::AVC_LEVEL_3,  H264Level::H264_LEVEL_30 },
    { AVCLevel::AVC_LEVEL_31, H264Level::H264_LEVEL_31 },
    { AVCLevel::AVC_LEVEL_32, H264Level::H264_LEVEL_32 },
    { AVCLevel::AVC_LEVEL_4,  H264Level::H264_LEVEL_40 },
    { AVCLevel::AVC_LEVEL_41, H264Level::H264_LEVEL_41 },
    { AVCLevel::AVC_LEVEL_42, H264Level::H264_LEVEL_42 },
    { AVCLevel::AVC_LEVEL_5,  H264Level::H264_LEVEL_50 },
    { AVCLevel::AVC_LEVEL_51, H264Level::H264_LEVEL_51 },
    { AVCLevel::AVC_LEVEL_52, H264Level::H264_LEVEL_52 },
    { AVCLevel::AVC_LEVEL_6,  H264Level::H264_LEVEL_60 },
    { AVCLevel::AVC_LEVEL_61, H264Level::H264_LEVEL_61 },
    { AVCLevel::AVC_LEVEL_62, H264Level::H264_LEVEL_62 },
};
} // namespace

const uint32_t AVC_ENCODER_P_FRAMETYPE = 1;
const uint32_t AVC_ENCODER_I_FRAMETYPE = 3;

using namespace OHOS::Media;

AVCodecBufferFlag AvcFrameTypeToBufferFlag(uint32_t frameType)
{
    AVCodecBufferFlag flag = AVCodecBufferFlag::AVCODEC_BUFFER_FLAG_NONE;
    switch (frameType) {
        case AVC_ENCODER_P_FRAMETYPE:
            flag = AVCodecBufferFlag::AVCODEC_BUFFER_FLAG_NONE;
            break;
        case AVC_ENCODER_I_FRAMETYPE:
            flag = AVCodecBufferFlag::AVCODEC_BUFFER_FLAG_SYNC_FRAME;
            break;
        default:
            flag = AVCodecBufferFlag::AVCODEC_BUFFER_FLAG_CODEC_DATA;
            break;
    }
    return flag;
}

VideoPixelFormat TranslateVideoPixelFormat(GraphicPixelFormat surfaceFormat)
{
    switch (surfaceFormat) {
        case GraphicPixelFormat::GRAPHIC_PIXEL_FMT_YCBCR_420_P: {
            return VideoPixelFormat::YUVI420;
        }
        case GraphicPixelFormat::GRAPHIC_PIXEL_FMT_RGBA_8888: {
            return VideoPixelFormat::RGBA;
        }
        case GraphicPixelFormat::GRAPHIC_PIXEL_FMT_YCBCR_P010:
        case GraphicPixelFormat::GRAPHIC_PIXEL_FMT_YCBCR_420_SP: {
            return VideoPixelFormat::NV12;
        }
        case GraphicPixelFormat::GRAPHIC_PIXEL_FMT_YCRCB_P010:
        case GraphicPixelFormat::GRAPHIC_PIXEL_FMT_YCRCB_420_SP: {
            return VideoPixelFormat::NV21;
        }
        default:
            AVCODEC_LOGE("Invalid graphic pixel format:%{public}d", static_cast<int32_t>(surfaceFormat));
    }
    return VideoPixelFormat::UNKNOWN;
}

GraphicPixelFormat TranslateSurfacePixFormat(const VideoPixelFormat &pixelFormat)
{
    switch (pixelFormat) {
        case VideoPixelFormat::YUVI420: {
            return GraphicPixelFormat::GRAPHIC_PIXEL_FMT_YCBCR_420_P;
        }
        case VideoPixelFormat::RGBA: {
            return GraphicPixelFormat::GRAPHIC_PIXEL_FMT_RGBA_8888;
        }
        case VideoPixelFormat::NV12: {
            return GraphicPixelFormat::GRAPHIC_PIXEL_FMT_YCBCR_420_SP;
        }
        case VideoPixelFormat::NV21: {
            return GraphicPixelFormat::GRAPHIC_PIXEL_FMT_YCRCB_420_SP;
        }
        default:
            return GraphicPixelFormat::GRAPHIC_PIXEL_FMT_BUTT;
    }
}

COLOR_MATRIX TranslateMatrix(MatrixCoefficient matrixFormat)
{
    switch (matrixFormat) {
        case MatrixCoefficient::MATRIX_COEFFICIENT_UNSPECIFIED: {
            return COLOR_MATRIX::MATRIX_UNSPECIFIED;
        }
        case MatrixCoefficient::MATRIX_COEFFICIENT_BT709: {
            return COLOR_MATRIX::MATRIX_BT709;
        }
        case MatrixCoefficient::MATRIX_COEFFICIENT_FCC: {
            return COLOR_MATRIX::MATRIX_FCC47_73_682;
        }
        case MatrixCoefficient::MATRIX_COEFFICIENT_BT601_525:
        case MatrixCoefficient::MATRIX_COEFFICIENT_BT601_625: {
            return COLOR_MATRIX::MATRIX_BT601;
        }
        case MatrixCoefficient::MATRIX_COEFFICIENT_SMPTE_ST240: {
            return COLOR_MATRIX::MATRIX_240M;
        }
        case MatrixCoefficient::MATRIX_COEFFICIENT_BT2020_NCL: {
            return COLOR_MATRIX::MATRIX_BT2020;
        }
        case MatrixCoefficient::MATRIX_COEFFICIENT_BT2020_CL: {
            return COLOR_MATRIX::MATRIX_BT2020_CONSTANT;
        }
        default:
            AVCODEC_LOGE("Invalid matrix format:%{public}d", static_cast<int32_t>(matrixFormat));
    }
    return COLOR_MATRIX::MATRIX_UNSPECIFIED;
}

COLOR_RANGE TranslateRange(uint8_t range)
{
    switch (range) {
        case 0: {
            return COLOR_RANGE::RANGE_LIMITED;
        }
        case 1: {
            return COLOR_RANGE::RANGE_FULL;
        }
        default:
            AVCODEC_LOGE("Invalid range format:%{public}d", range);
    }
    return COLOR_RANGE::RANGE_UNSPECIFIED;
}

ENC_MODE TranslateEncMode(VideoEncodeBitrateMode mode)
{
    switch (mode) {
        case VideoEncodeBitrateMode::CBR :
        case VideoEncodeBitrateMode::CBR_VIDEOCALL : {
            return ENC_MODE::MODE_CBR;
        }
        case VideoEncodeBitrateMode::VBR: {
            return ENC_MODE::MODE_VBR;
        }
        case VideoEncodeBitrateMode::CQ: {
            return ENC_MODE::MODE_CQP;
        }
        default:
            AVCODEC_LOGE("Invalid bitrate mode format:%{public}d", static_cast<int32_t>(mode));
    }
    return ENC_MODE::MODE_CBR;
}


COLOR_FORMAT TranslateVideoFormatToAvc(const VideoPixelFormat &pixelFormat)
{
    switch (pixelFormat) {
        case VideoPixelFormat::YUVI420: {
            return COLOR_FORMAT::YUV_420P;
        }
        case VideoPixelFormat::RGBA: {
            return COLOR_FORMAT::YUV_420SP_VU;
        }
        case VideoPixelFormat::NV12: {
            return COLOR_FORMAT::YUV_420SP_UV;
        }
        case VideoPixelFormat::NV21: {
            return COLOR_FORMAT::YUV_420SP_VU;
        }
        default:
            AVCODEC_LOGE("Invalid video pixel format:%{public}d", static_cast<int32_t>(pixelFormat));
    }
    return COLOR_FORMAT::YUV_420P;
}

ENC_PROFILE TranslateEncProfile(AVCProfile profile)
{
    switch (profile) {
        case AVCProfile::AVC_PROFILE_BASELINE :
        case AVCProfile::AVC_PROFILE_CONSTRAINED_BASELINE: {
            return ENC_PROFILE::PROFILE_BASE;
        }
        case AVCProfile::AVC_PROFILE_CONSTRAINED_HIGH :
        case AVCProfile::AVC_PROFILE_EXTENDED :
        case AVCProfile::AVC_PROFILE_HIGH :
        case AVCProfile::AVC_PROFILE_HIGH_10 :
        case AVCProfile::AVC_PROFILE_HIGH_422 :
        case AVCProfile::AVC_PROFILE_HIGH_444 : {
            return ENC_PROFILE::PROFILE_HIGH;
        }
        case AVCProfile::AVC_PROFILE_MAIN : {
            return ENC_PROFILE::PROFILE_MAIN;
        }
        default:
            AVCODEC_LOGE("Invalid profile format:%{public}d", static_cast<int32_t>(profile));
    }
    return ENC_PROFILE::PROFILE_BASE;
}

H264Level TranslateEncLevel(AVCLevel level)
{
    auto iter = std::find_if(
        g_encodeLevelMap.begin(), g_encodeLevelMap.end(),
        [&](const std::pair<AVCLevel, H264Level> &tmp) -> bool { return tmp.first == level; });
    return iter == g_encodeLevelMap.end() ? H264Level::H264_LEVEL_41 : iter->second;
}
} // namespace Codec
} // namespace MediaAVCodec
} // namespace OHOS