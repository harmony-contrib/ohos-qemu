#!/usr/bin/env python3
"""Accept only the exact fixed wrapper or its explicit EOS repair, never unknown edits."""
import argparse
from pathlib import Path
import subprocess

REVISION = 'e5c525670d1f6622d441c9e5bf975ea0579ea177'
FILE = 'services/engine/codec/video/avcencoder/avc_encoder.cpp'
REPLACEMENTS = (
    ('    if (isSendEos_) {\n        outputAVBuffer->flag_ = AVCODEC_BUFFER_FLAG_EOS;\n',
     '    if (isSendEos_) {\n        CHECK_AND_RETURN_RET_LOG(ret == 0, AVCS_ERR_VID_ENC_FAILED,\n'
     '            "Cannot encode AVC EOS: %{public}u", ret);\n'
     '        outputAVBuffer->memory_->SetSize(outArgs.bytes);\n'
     '        outputAVBuffer->pts_ = static_cast<int64_t>(outArgs.timestamp);\n'
     '        outputAVBuffer->flag_ = AVCODEC_BUFFER_FLAG_EOS;\n'),
    ('    CHECK_AND_RETURN_LOG(ret == AVCS_ERR_OK, "Avc Encoder tailer error: %{public}d", ret);\n',
     '    if (ret != AVCS_ERR_OK) {\n        AVCODEC_LOGE("Avc Encoder tailer error: %{public}d", ret);\n'
     '        callback_->OnError(AVCodecErrorType::AVCODEC_ERROR_INTERNAL, AVCodecServiceErrCode::AVCS_ERR_UNKNOWN);\n'
     '        state_ = State::ERROR;\n    }\n'),
    ('        EncoderAvcTailer();\n        state_ = State::EOS;\n',
     '        EncoderAvcTailer();\n        CHECK_AND_RETURN_LOG(state_ != State::ERROR, "AVC EOS encoding failed");\n'
     '        state_ = State::EOS;\n'),
)


INPUT_REPLACEMENTS = (
    ('''int32_t AvcEncoder::CheckBufferSize(int32_t bufferSize, int32_t stride, int32_t height, VideoPixelFormat pixelFormat)
{
    int32_t expect = 0;
    switch (pixelFormat) {
        case VideoPixelFormat::RGBA: {
            expect = stride * height;                //  rgba origin stride already * 4
            break;
        }
        case VideoPixelFormat::YUVI420:
        case VideoPixelFormat::NV12:
        case VideoPixelFormat::NV21: {
            expect = stride * height * 3 / 2;        //  * 3 / 2: yuv size
            break;
        }
        default:
            AVCODEC_LOGE("Invalid buffer size %{public}d %{public}dX%{public}d for format:%{public}d",
                bufferSize, stride, height, static_cast<int32_t>(pixelFormat));
            return AVCS_ERR_UNSUPPORT_SOURCE;
    }
    if (bufferSize >= expect && expect > 0) {
        return AVCS_ERR_OK;
    }
    return AVCS_ERR_UNSUPPORT_SOURCE;
}
''',
     '''int32_t AvcEncoder::CheckBufferSize(int32_t bufferSize, int32_t stride, int32_t height, VideoPixelFormat pixelFormat)
{
    if (bufferSize <= 0 || stride <= 0 || height <= 0 || height % EVEN_NUMBER_DIVISOR != 0) {
        return AVCS_ERR_UNSUPPORT_SOURCE;
    }
    const int64_t rowBytes = stride;
    int64_t expect = 0;
    switch (pixelFormat) {
        case VideoPixelFormat::RGBA: {
            if (stride % RGBA_COLINC != 0) {
                return AVCS_ERR_UNSUPPORT_SOURCE;
            }
            expect = rowBytes * height;
            break;
        }
        case VideoPixelFormat::YUVI420:
        case VideoPixelFormat::NV12:
        case VideoPixelFormat::NV21: {
            if (stride % EVEN_NUMBER_DIVISOR != 0) {
                return AVCS_ERR_UNSUPPORT_SOURCE;
            }
            expect = rowBytes * height + rowBytes * (height / EVEN_NUMBER_DIVISOR);
            break;
        }
        default:
            AVCODEC_LOGE("Invalid buffer size %{public}d %{public}dX%{public}d for format:%{public}d",
                bufferSize, stride, height, static_cast<int32_t>(pixelFormat));
            return AVCS_ERR_UNSUPPORT_SOURCE;
    }
    if (bufferSize >= expect) {
        return AVCS_ERR_OK;
    }
    return AVCS_ERR_UNSUPPORT_SOURCE;
}
'''),
    ('''    int32_t stride = inFrame.stride;

    if (inputSurface_ != nullptr) {
        stride = inFrame.stride / RGBA_COLINC;   // surface buffer rgba stride has * 4
    }
''',
     '''    int32_t stride = inFrame.stride / RGBA_COLINC; // InputFrame strides are bytes in both modes.
'''),
    ('''    inFrame.stride = encWidth_;
''',
     '''    inFrame.stride = srcPixelFmt_ == VideoPixelFormat::RGBA ? encWidth_ * RGBA_COLINC : encWidth_;
'''),
)


def repaired_source(original, include_input=True):
    repaired = original
    for old, new in REPLACEMENTS + (INPUT_REPLACEMENTS if include_input else ()):
        if repaired.count(old) != 1: raise ValueError('unknown pinned AVC wrapper EOS structure')
        repaired = repaired.replace(old, new)
    return repaired


def validate(root, require_patched=False):
    project = root / 'foundation/multimedia/av_codec'
    if subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('AVC EOS repair requires the pinned 7.0 wrapper')
    original = subprocess.check_output(['git', '-C', str(project), 'show', 'HEAD:' + FILE]).decode()
    repaired = repaired_source(original)
    target = project / FILE
    if target.is_symlink() or not target.is_file():
        raise ValueError('regular fixed AVC wrapper required')
    for parent in target.parents:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError('linked AVC wrapper input rejected')
    actual = target.read_bytes().decode()
    accepted = (repaired,) if require_patched else (original, repaired_source(original, False), repaired)
    if actual not in accepted:
        raise ValueError('unknown/incomplete AVC wrapper changes; preserve edits and refuse this backend')
    return actual == repaired


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('AVC EOS patch present: ' + str(validate(args.source_root, args.require_patched)))


if __name__ == '__main__':
    main()
