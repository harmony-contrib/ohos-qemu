"""Exact transforms for the fixed AVC wrapper; never replacement codec output."""
WRAPPER = 'services/engine/codec/video/avcencoder/avc_encoder.cpp'
UTIL = 'services/engine/codec/video/avcencoder/avc_encoder_util.cpp'


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


UV_FUNCTION = '''int32_t AvcEncoder::GetSurfaceBufferUvOffset(sptr<SurfaceBuffer> &surfaceBuffer, VideoPixelFormat format)
{
    if (format != VideoPixelFormat::YUVI420 && format != VideoPixelFormat::NV12 &&
        format != VideoPixelFormat::NV21) {
        return 0;
    }

    OH_NativeBuffer_Planes *planes = nullptr;
    GSError ret = surfaceBuffer->GetPlanesInfo(reinterpret_cast<void**>(&planes));
    if (ret != GSERROR_OK) {
        // QEMU's fixed gralloc has no GetImageLayout; validate its contiguous fallback below.
        return 0;
    }
    CHECK_AND_RETURN_RET_LOG(planes != nullptr, -1, "Missing surface plane info");
    const uint32_t count = planes->planeCount;
    const bool planar = format == VideoPixelFormat::YUVI420;
    CHECK_AND_RETURN_RET_LOG((planar && count == 3) || (!planar && (count == 2 || count == 3)),
        -1, "Unsupported surface plane count");
    const int32_t stride = surfaceBuffer->GetStride();
    CHECK_AND_RETURN_RET_LOG(stride > 0 && surfaceBuffer->GetHeight() > 0,
        -1, "Invalid surface geometry");
    const uint64_t lumaSize = static_cast<uint64_t>(stride) * surfaceBuffer->GetHeight();
    CHECK_AND_RETURN_RET_LOG(planes->planes[0].offset == 0 &&
        planes->planes[0].rowStride == static_cast<uint32_t>(stride) &&
        planes->planes[0].columnStride == 1, -1, "Unsupported surface luma layout");

    // NV12/NV21 can describe two physical planes or separate Y/U/V component views.
    const uint32_t chroma = (!planar && count == 3 && format == VideoPixelFormat::NV21) ? 2 : 1;
    const auto &uv = planes->planes[chroma];
    const uint32_t chromaStride = planar ? static_cast<uint32_t>(stride / EVEN_NUMBER_DIVISOR) : stride;
    CHECK_AND_RETURN_RET_LOG(uv.offset >= lumaSize && uv.offset <= INT32_MAX &&
        uv.rowStride == chromaStride, -1, "Unsupported surface chroma layout");
    if (planar) {
        const uint64_t chromaSize = static_cast<uint64_t>(chromaStride) *
            (surfaceBuffer->GetHeight() / EVEN_NUMBER_DIVISOR);
        CHECK_AND_RETURN_RET_LOG(uv.columnStride == 1 && planes->planes[2].columnStride == 1 &&
            planes->planes[2].rowStride == chromaStride &&
            planes->planes[2].offset == uv.offset + chromaSize, -1, "Unsupported planar V layout");
    } else if (count == 3) {
        const auto &other = planes->planes[chroma == 1 ? 2 : 1];
        CHECK_AND_RETURN_RET_LOG(uv.columnStride == 2 && other.columnStride == 2 &&
            other.rowStride == chromaStride && other.offset == uv.offset + 1,
            -1, "Unsupported interleaved component views");
    } else {
        CHECK_AND_RETURN_RET_LOG(uv.columnStride == 1 || uv.columnStride == 2,
            -1, "Unsupported interleaved chroma step");
    }
    return static_cast<int32_t>(uv.offset);
}'''

INPUT_FUNCTION = '''int32_t AvcEncoder::GetInputFrameFromAVBuffer(std::shared_ptr<AVBuffer> &buffer, InputFrame &inFrame)
{
    CHECK_AND_RETURN_RET_LOG(buffer != nullptr && buffer->memory_ != nullptr,
        AVCS_ERR_INVALID_DATA, "Missing input memory");
    CHECK_AND_RETURN_RET_LOG(encWidth_ >= VIDEO_MIN_SIZE && encWidth_ <= VIDEO_MAX_WIDTH_SIZE &&
        encHeight_ >= VIDEO_MIN_SIZE && encHeight_ <= VIDEO_MAX_HEIGHT_SIZE,
        AVCS_ERR_INVALID_DATA, "Invalid configured encoder dimensions");
    inFrame.format = srcPixelFmt_;
    inFrame.width = encWidth_;
    inFrame.height = encHeight_;
    inFrame.stride = srcPixelFmt_ == VideoPixelFormat::RGBA ? encWidth_ * RGBA_COLINC : encWidth_;
    inFrame.uvOffset = 0;
    inFrame.size = buffer->memory_->GetSize();
    inFrame.buffer = buffer->memory_->GetAddr();
    if (inputSurface_ != nullptr) {
        auto surfaceBuffer = buffer->memory_->GetSurfaceBuffer();
        CHECK_AND_RETURN_RET_LOG(surfaceBuffer != nullptr, AVCS_ERR_INVALID_DATA, "Get surface data failed!");
        inFrame.format =
            TranslateVideoPixelFormat(static_cast<GraphicPixelFormat>(surfaceBuffer->GetFormat()));
        inFrame.width = surfaceBuffer->GetWidth();
        inFrame.height = surfaceBuffer->GetHeight();
        CHECK_AND_RETURN_RET_LOG(inFrame.width == encWidth_ && inFrame.height == encHeight_,
            AVCS_ERR_INVALID_DATA, "Surface dimensions differ from configured encoder");
        inFrame.stride = surfaceBuffer->GetStride();
        const uint32_t surfaceSize = surfaceBuffer->GetSize();
        CHECK_AND_RETURN_RET_LOG(surfaceSize <= INT32_MAX, AVCS_ERR_INVALID_DATA, "Surface size overflow");
        inFrame.size = static_cast<int32_t>(surfaceSize);
        inFrame.buffer = reinterpret_cast<uint8_t *>(surfaceBuffer->GetVirAddr());
        inFrame.uvOffset = GetSurfaceBufferUvOffset(surfaceBuffer, inFrame.format);
        CHECK_AND_RETURN_RET_LOG(inFrame.uvOffset >= 0, AVCS_ERR_INVALID_DATA, "Invalid surface plane layout");
    } else {
        const int32_t offset = buffer->memory_->GetOffset();
        const int32_t capacity = buffer->memory_->GetCapacity();
        CHECK_AND_RETURN_RET_LOG(offset >= 0 && offset <= capacity && inFrame.size >= 0 &&
            inFrame.size <= capacity - offset, AVCS_ERR_INVALID_DATA, "Input range exceeds memory");
        CHECK_AND_RETURN_RET_LOG(inFrame.buffer != nullptr, AVCS_ERR_INVALID_DATA, "Missing input address");
        inFrame.buffer += offset;
    }
    CHECK_AND_RETURN_RET_LOG(inFrame.buffer != nullptr && inFrame.width >= VIDEO_MIN_SIZE &&
        inFrame.width <= VIDEO_MAX_WIDTH_SIZE && inFrame.height >= VIDEO_MIN_SIZE &&
        inFrame.height <= VIDEO_MAX_HEIGHT_SIZE && inFrame.width % EVEN_NUMBER_DIVISOR == 0 &&
        inFrame.height % EVEN_NUMBER_DIVISOR == 0, AVCS_ERR_INVALID_DATA, "Invalid input geometry");
    const bool rgba = inFrame.format == VideoPixelFormat::RGBA;
    CHECK_AND_RETURN_RET_LOG(rgba || inFrame.format == VideoPixelFormat::YUVI420 ||
        inFrame.format == VideoPixelFormat::NV12 || inFrame.format == VideoPixelFormat::NV21,
        AVCS_ERR_INVALID_DATA, "Unsupported input pixel format");
    const int32_t alignment = rgba ? RGBA_COLINC : EVEN_NUMBER_DIVISOR;
    const int32_t minStride = rgba ? inFrame.width * RGBA_COLINC : inFrame.width;
    CHECK_AND_RETURN_RET_LOG(inFrame.stride >= minStride && inFrame.stride % alignment == 0,
        AVCS_ERR_INVALID_DATA, "Invalid input byte stride");
    const int64_t lumaSize = static_cast<int64_t>(inFrame.stride) * inFrame.height;
    CHECK_AND_RETURN_RET_LOG(lumaSize <= INT32_MAX, AVCS_ERR_INVALID_DATA, "Input luma size overflow");
    if (inFrame.uvOffset == 0) {
        inFrame.uvOffset = static_cast<int32_t>(lumaSize);
    }
    const int64_t required = rgba ? lumaSize : static_cast<int64_t>(inFrame.uvOffset) +
        static_cast<int64_t>(inFrame.stride) * (inFrame.height / EVEN_NUMBER_DIVISOR);
    CHECK_AND_RETURN_RET_LOG(inFrame.uvOffset >= lumaSize && required <= inFrame.size,
        AVCS_ERR_INVALID_DATA, "Input planes exceed available bytes");
    inFrame.pts = buffer->pts_;
    return AVCS_ERR_OK;
}'''

ERROR_OLD = '''    if (ret != AVCS_ERR_OK) {
        AVCODEC_LOGE("convert buffer to encodec error: %{public}d", ret);
        callback_->OnError(AVCodecErrorType::AVCODEC_ERROR_INTERNAL, AVCodecServiceErrCode::AVCS_ERR_UNKNOWN);
        state_ = State::ERROR;
        return;
    }'''
ERROR_NEW = '''    if (ret != AVCS_ERR_OK) {
        AVCODEC_LOGE("convert buffer to encodec error: %{public}d", ret);
        if (inputSurface_ != nullptr) {
            ReleaseSurfaceBufferByAVBuffer(inputAVBuffer);
            inputBuffer->surfaceBuffer_ = nullptr;
            inputBuffer->fence_ = nullptr;
        }
        callback_->OnError(AVCodecErrorType::AVCODEC_ERROR_INTERNAL, AVCodecServiceErrCode::AVCS_ERR_UNKNOWN);
        state_ = State::ERROR;
        return;
    }'''


def repair_wrapper(original):
    repaired = original
    for signature, value in [('int32_t AvcEncoder::GetSurfaceBufferUvOffset(', UV_FUNCTION),
                             ('int32_t AvcEncoder::GetInputFrameFromAVBuffer(', INPUT_FUNCTION)]:
        old = function(repaired, signature)
        if repaired.count(old) != 1:
            raise ValueError('unknown fixed AVC layout function')
        repaired = repaired.replace(old, value)
    if repaired.count(ERROR_OLD) != 1:
        raise ValueError('unknown fixed AVC conversion error path')
    return repaired.replace(ERROR_OLD, ERROR_NEW)


def repair_util(original):
    repaired = original
    for line in ['        case GraphicPixelFormat::GRAPHIC_PIXEL_FMT_YCBCR_P010:\n',
                 '        case GraphicPixelFormat::GRAPHIC_PIXEL_FMT_YCRCB_P010:\n']:
        if repaired.count(line) != 1:
            raise ValueError('unknown fixed AVC P010 mapping')
        repaired = repaired.replace(line, '')
    return repaired
