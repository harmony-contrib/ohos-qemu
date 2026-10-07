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


def repaired_source(original):
    repaired = original
    for old, new in REPLACEMENTS:
        if repaired.count(old) != 1: raise ValueError('unknown pinned AVC wrapper EOS structure')
        repaired = repaired.replace(old, new)
    return repaired


def validate(root, require_patched=False):
    project = root / 'foundation/multimedia/av_codec'
    if subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('AVC EOS repair requires the pinned 7.0 wrapper')
    original = subprocess.check_output(['git', '-C', str(project), 'show', 'HEAD:' + FILE]).decode()
    repaired = repaired_source(original)
    actual = (project / FILE).read_bytes().decode()
    if actual != repaired and (require_patched or actual != original):
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
