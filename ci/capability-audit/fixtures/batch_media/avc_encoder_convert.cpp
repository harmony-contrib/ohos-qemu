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

#include "securec.h"
#include "avcodec_errors.h"
#include "avcodec_log.h"
#include "avcodec_trace.h"
#include "avc_encoder_convert.h"

#if defined(ARMV8)
#include <arm_neon.h>
#endif

namespace OHOS {
namespace MediaAVCodec {
namespace Codec {

#ifdef __cplusplus
extern "C" {
#endif

namespace {
constexpr OHOS::HiviewDFX::HiLogLabel LABEL = {LOG_CORE, LOG_DOMAIN_FRAMEWORK, "AvcEncoder"};
} // namespace

// Matrix coefficient to convert RGB to planar YUV data
// Each sub-array represents to 3x3 coeff use with R G B
static const int16_t BT601_MATRIX[2][3][3] = {
    {{76, 150, 29}, {-43, -85, 128}, {128, -107, -21}},     // RANGE_FULL
    {{66, 129, 25}, {-38, -74, 112}, {112, -94, -18}},      // RANGE_LIMITED
};

static const int16_t BT709_MATRIX[2][3][3] = {
    {{54, 183, 18}, {-29, -99, 128}, {128, -116, -12}},     // RANGE_FULL
    {{47, 157, 16}, {-26, -86, 112}, {112, -102, -10}},     // RANGE_LIMITED
};

inline uint8_t Clip3(uint8_t min, uint8_t value, uint8_t max)
{
    if (value < min) {
        return min;
    }
    if (value > max) {
        return max;
    }
    return value;
}

#if defined(ARMV8)
int32_t ConvertRgbToYuv420Neon(uint8_t *dstData, int32_t width, int32_t height,
    int32_t bufferSize, RgbImageData &rgbData)
{
    const uint8_t *srcData = rgbData.data;
    int32_t srcStride = rgbData.stride;
    int32_t bytesPerPixel = rgbData.bytesPerPixel;
    COLOR_MATRIX colorMatrix = rgbData.matrix;
    COLOR_RANGE colorRange = rgbData.range;
    int32_t dstStride = width;

    if (dstData == nullptr || srcData == nullptr) {
        return AVCS_ERR_INVALID_VAL;
    }
    if ((dstStride * height * 3 / 2) > bufferSize) {  // yuv bufferSize dstStride * height * 3 / 2
        AVCODEC_LOGE("conversion buffer is too small for converting from RGB to YUV");
        return AVCS_ERR_NO_MEMORY;
    }
    colorRange = (colorRange != RANGE_FULL && colorRange != RANGE_LIMITED) ? RANGE_LIMITED : colorRange;
    const int16_t(*weights)[3] =
        (colorMatrix == MATRIX_BT709) ? BT709_MATRIX[colorRange - 1] : BT601_MATRIX[colorRange - 1];

    uint8_t zeroLvl = colorRange == RANGE_FULL ? 0 : 16;

    const uint8x16_t u8_16 = vdupq_n_u8(zeroLvl);

    const uint16x8_t mask = vdupq_n_s16(255);

    const int8x8_t s8_rounding = vdup_n_s8(-128);

    uint8x8_t scalar_Yr = vdup_n_u8((uint8_t)weights[0][0]);    // 0: Y
    uint8x8_t scalar_Yg = vdup_n_u8((uint8_t)weights[0][1]);    // 1: U
    uint8x8_t scalar_Yb = vdup_n_u8((uint8_t)weights[0][2]);    // 2: V

    int16x8_t u2_scalar = vdupq_n_s16(weights[1][1]);   // u scalar = -74
    int16x8_t v2_scalar = vdupq_n_s16(weights[2][1]);   // v scalar = -94

    int16x8_t u3_scalar = vdupq_n_s16(weights[1][2]);   // u scalar = 112
    int16x8_t v3_scalar = vdupq_n_s16(weights[2][2]);   // v saclar = -18

    int patch = width >> 4;                 // each 16 pixel for a patch.rigth shift 4 bits
    int widthLess = width - (patch << 4);   // left shift 4 bits to get patch width
    const int isPad = (widthLess > 0);

    const uint8_t *rgbaBuf = srcData;
    int rgbaOffset = 0;

    int stridePadding = srcStride - width;

    int yStride = 0;
    int uStride = yStride >> 1;

    int lumaOffset = 0;
    int chromaUOffset = dstStride * height;
    int chromaVOffset = chromaUOffset + (dstStride >> 1) * (height >> 1);
    const int batchOffset = 16;            // each time process 16 pixels

    for (int j = 0; j < height; ++j) {
        for (int i = 0; i < patch + isPad; ++i) {
            uint8x16x3_t pixelRgbOri;
            if (bytesPerPixel == RGBA_COLINC) {
                uint8x16x4_t pixelRgbaOri = vld4q_u8(rgbaBuf + rgbaOffset);
                pixelRgbOri.val[0] = pixelRgbaOri.val[0];   // get val[0] from rgba buf
                pixelRgbOri.val[1] = pixelRgbaOri.val[1];   // get val[1] from rgba buf
                pixelRgbOri.val[2] = pixelRgbaOri.val[2];   // get val[2] from rgba buf
            } else {
                pixelRgbOri = vld3q_u8(rgbaBuf + rgbaOffset);
            }

            uint8x8x2_t rOri;
            uint8x8x2_t gOri;
            uint8x8x2_t bOri;
            rOri.val[0] = vget_low_u8(pixelRgbOri.val[0]);     // val[0]: r value
            rOri.val[1] = vget_high_u8(pixelRgbOri.val[0]);    // val[0]: r value
            gOri.val[0] = vget_low_u8(pixelRgbOri.val[1]);     // val[1]: g value
            gOri.val[1] = vget_high_u8(pixelRgbOri.val[1]);    // val[1]: g value
            bOri.val[0] = vget_low_u8(pixelRgbOri.val[2]);     // val[2]: b value
            bOri.val[1] = vget_high_u8(pixelRgbOri.val[2]);    // val[2]: b value

            uint16x8x2_t yTemp;
            uint8x16_t pixelY;

            yTemp.val[0] = vmull_u8(rOri.val[0], scalar_Yr);
            yTemp.val[1] = vmull_u8(rOri.val[1], scalar_Yr);      // Y = R * 66

            yTemp.val[0] = vmlal_u8(yTemp.val[0], gOri.val[0], scalar_Yg);
            yTemp.val[1] = vmlal_u8(yTemp.val[1], gOri.val[1], scalar_Yg);

            yTemp.val[0] = vmlal_u8(yTemp.val[0], bOri.val[0], scalar_Yb);
            yTemp.val[1] = vmlal_u8(yTemp.val[1], bOri.val[1], scalar_Yb);

            pixelY = vcombine_u8(vqshrn_n_u16(yTemp.val[0], 8), vqshrn_n_u16(yTemp.val[1], 8));  // 8 bits
            pixelY = vaddq_u8(pixelY, u8_16);

            vst1q_u8(dstData + lumaOffset, pixelY);

            if (j % 2 == 0) {   // calc 2 components: u, v
                int16x8_t rUpdate = vreinterpretq_s16_u16(vandq_u16(vreinterpretq_u16_u8(pixelRgbOri.val[0]), mask));
                int16x8_t gUpdate = vreinterpretq_s16_u16(vandq_u16(vreinterpretq_u16_u8(pixelRgbOri.val[1]), mask));
                int16x8_t bUpdate = vreinterpretq_s16_u16(vandq_u16(vreinterpretq_u16_u8(pixelRgbOri.val[2]), mask));

                int16x8_t signedU;
                int16x8_t signedV;
                uint8x8_t outputUV[2]; // 2 row for u & v
                signedU = vmulq_n_s16(rUpdate, weights[1][0]);   // u coeff = -28
                signedV = vmulq_n_s16(rUpdate, weights[2][0]);   // v coeff = 112

                signedU = vmlaq_s16(signedU, gUpdate, u2_scalar);
                signedV = vmlaq_s16(signedV, gUpdate, v2_scalar);

                signedU = vmlaq_s16(signedU, bUpdate, u3_scalar);
                signedV = vmlaq_s16(signedV, bUpdate, v3_scalar);

                outputUV[0] = vreinterpret_u8_s8(vadd_s8(vqshrn_n_s16(signedU, 8), s8_rounding));  // 8 bits
                outputUV[1] = vreinterpret_u8_s8(vadd_s8(vqshrn_n_s16(signedV, 8), s8_rounding));  // 8 bits

                vst1_u8(dstData + chromaUOffset, outputUV[0]);
                vst1_u8(dstData + chromaVOffset, outputUV[1]);

                chromaUOffset += (i == 0 && isPad) ? (widthLess >> 1) : (batchOffset >> 1);
                chromaVOffset += (i == 0 && isPad) ? (widthLess >> 1) : (batchOffset >> 1);
            }
            if (i == 0 && isPad) {
                rgbaOffset += bytesPerPixel * widthLess;
                lumaOffset += widthLess;
            } else {
                rgbaOffset += bytesPerPixel * batchOffset;
                lumaOffset += batchOffset;
            }
        }

        if ((j & 1) == 0) {
            chromaUOffset += uStride;
            chromaVOffset += uStride;
        }

        lumaOffset += yStride;
        rgbaOffset += stridePadding * bytesPerPixel;
    }
    return AVCS_ERR_OK;
}
#endif

int32_t ConvertRgbToYuv420(uint8_t *dstData, int32_t width, int32_t height,
    int32_t bufferSize, RgbImageData &rgbData)
{
    const uint8_t *srcData = rgbData.data;
    int32_t srcStride = rgbData.stride;
    int32_t bytesPerPixel = rgbData.bytesPerPixel;
    COLOR_MATRIX colorMatrix = rgbData.matrix;
    COLOR_RANGE colorRange = rgbData.range;
    int32_t dstStride = width;

    if (dstData == nullptr || srcData == nullptr) {
        return AVCS_ERR_INVALID_VAL;
    }
    if ((dstStride * height * 3 / 2) > bufferSize) {    // yuv bufferSize dstStride * height * 3 / 2
        AVCODEC_LOGE("conversion buffer is too small for converting from RGB to YUV");
        return AVCS_ERR_NO_MEMORY;
    }

    uint8_t *dstU = dstData + dstStride * height;
    uint8_t *dstV = dstU + (dstStride >> 1) * (height >> 1);

    const uint8_t *pRed = srcData;          // r data 0
    const uint8_t *pGreen = srcData + 1;    // g data 1
    const uint8_t *pBlue = srcData + 2;     // b data 2

    colorRange = (colorRange != RANGE_FULL && colorRange != RANGE_LIMITED) ? RANGE_LIMITED : colorRange;
    const int16_t(*weights)[3] =
        (colorMatrix == MATRIX_BT709) ? BT709_MATRIX[colorRange - 1] : BT601_MATRIX[colorRange - 1];

    uint8_t zeroLvl = colorRange == RANGE_FULL ? 0 : 16;
    uint8_t maxLvlLuma = colorRange == RANGE_FULL ? 255 : 235;
    uint8_t maxLvlChroma = colorRange == RANGE_FULL ? 255 : 240;

    for (int32_t y = 0; y < height; ++y) {
        for (int32_t x = 0; x < width; ++x) {
            uint8_t r = *pRed;
            uint8_t g = *pGreen;
            uint8_t b = *pBlue;

            uint8_t luma = ((r * weights[0][0] + g * weights[0][1] + b * weights[0][2]) >> 8) + zeroLvl;
            dstData[x] = Clip3(zeroLvl, luma, maxLvlLuma);

            if ((x & 1) == 0 && (y & 1) == 0) {
                uint8_t u = ((r * weights[1][0] + g * weights[1][1] + b * weights[1][2]) >> 8) + 128;
                uint8_t v = ((r * weights[2][0] + g * weights[2][1] + b * weights[2][2]) >> 8) + 128;
                dstU[x >> 1] = Clip3(zeroLvl, u, maxLvlChroma);
                dstV[x >> 1] = Clip3(zeroLvl, v, maxLvlChroma);
            }
            pRed += bytesPerPixel;
            pGreen += bytesPerPixel;
            pBlue += bytesPerPixel;
        }

        if ((y & 1) == 0) {
            dstU += dstStride >> 1;
            dstV += dstStride >> 1;
        }

        pRed -= bytesPerPixel * width;
        pGreen -= bytesPerPixel * width;
        pBlue -= bytesPerPixel * width;
        pRed += bytesPerPixel * srcStride;
        pGreen += bytesPerPixel * srcStride;
        pBlue += bytesPerPixel * srcStride;

        dstData += dstStride;
    }
    return AVCS_ERR_OK;
}

int32_t ConvertNv12ToYuv420(uint8_t *dstData, int32_t width, int32_t height,
    int32_t bufferSize, YuvImageData &yuvData)
{
    if (bufferSize < (width * height * 3 / 2)) {    // yuv bufferSize dstStride * height * 3 / 2
        AVCODEC_LOGE("conversion buffer is too small for converting from NV12 to YUV");
        return AVCS_ERR_NO_MEMORY;
    }

    int32_t dstStride = width;
    uint8_t *dstY = dstData;
    uint8_t *dstU = dstData + dstStride * height;
    uint8_t *dstV = dstU + (dstStride >> 1) * (height >> 1);

    int32_t srcStride = yuvData.stride;
    const uint8_t *srcY = yuvData.data;
    const uint8_t *srcU = srcY + yuvData.uvOffset;
    const uint8_t *srcV = srcY + yuvData.uvOffset + 1;

    int32_t x;
    int32_t y;
    for (y = 0; y < height; y++) {
        errno_t ret = memcpy_s(dstY, width, srcY, width);
        CHECK_AND_RETURN_RET_LOG(ret == EOK, AVCS_ERR_UNKNOWN, "memcpy_s failed");
        dstY += dstStride;
        srcY += srcStride;
    }

    height = height >> 1;
    width = width >> 1;
    dstStride = dstStride >> 1;
    for (y = 0; y < height; y++) {
        for (x = 0; x < width; x++) {
            dstU[x] = srcU[x << 1];
            dstV[x] = srcV[x << 1];
        }

        dstU += dstStride;
        dstV += dstStride;
        srcU += srcStride;
        srcV += srcStride;
    }

    return AVCS_ERR_OK;
}

int32_t ConvertNv21ToYuv420(uint8_t *dstData, int32_t width, int32_t height,
    int32_t bufferSize, YuvImageData &yuvData)
{
    if (bufferSize < (width * height * 3 / 2)) {    // yuv bufferSize dstStride * height * 3 / 2
        AVCODEC_LOGE("conversion buffer is too small for converting from NV21 to YUV");
        return AVCS_ERR_NO_MEMORY;
    }

    int32_t dstStride = width;
    uint8_t *dstY = dstData;
    uint8_t *dstU = dstData + dstStride * height;
    uint8_t *dstV = dstU + (dstStride >> 1) * (height >> 1);

    int32_t srcStride = yuvData.stride;
    const uint8_t *srcY = yuvData.data;
    const uint8_t *srcU = srcY + yuvData.uvOffset + 1;
    const uint8_t *srcV = srcY + yuvData.uvOffset;

    int32_t x;
    int32_t y;
    for (y = 0; y < height; y++) {
        errno_t ret = memcpy_s(dstY, width, srcY, width);
        CHECK_AND_RETURN_RET_LOG(ret == EOK, AVCS_ERR_UNKNOWN, "memcpy_s failed");
        dstY += dstStride;
        srcY += srcStride;
    }

    height = height >> 1;
    width = width >> 1;
    dstStride = dstStride >> 1;
    for (y = 0; y < height; y++) {
        for (x = 0; x < width; x++) {
            dstU[x] = srcU[x << 1];
            dstV[x] = srcV[x << 1];
        }

        dstU += dstStride;
        dstV += dstStride;
        srcU += srcStride;
        srcV += srcStride;
    }

    return AVCS_ERR_OK;
}

#ifdef __cplusplus
}
#endif

} // namespace Codec
} // namespace MediaAVCodec
} // namespace OHOS