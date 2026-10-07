// SPDX-License-Identifier: Apache-2.0
// Real pinned OpenH264 encode/decode. HOST ONLY, not image/HAP acceptance.
#include <cstddef>
#include <cstdio>
#include <vector>
#include "qemu_avc_encoder.cc"

namespace {
const char *challenge = nullptr;
int failed = 0;
int cases = 0;
int decoded = 0;

void Check(const char *name, bool passed, int profile = -1, int mode = -1, int cycle = -1, int frame = -1)
{
    ++cases;
    if (!passed) ++failed;
    printf("{\"run_id\":\"%s\",\"type\":\"case\",\"name\":\"%s\",\"profile\":%d,"
        "\"mode\":%d,\"cycle\":%d,\"frame\":%d,\"passed\":%s}\n",
        challenge, name, profile, mode, cycle, frame, passed ? "true" : "false");
}

AVC_ENC_INIT_PARAM Params(int profile, int mode)
{
    AVC_ENC_INIT_PARAM params = {};
    params.width = 64;
    params.height = 64;
    params.frameRate = 30;
    params.bitrate = 1000000;
    params.encMode = static_cast<ENC_MODE>(mode);
    params.profile = static_cast<ENC_PROFILE>(profile);
    params.qp = 20;
    params.qpMin = 4;
    params.qpMax = 51;
    params.iperiod = 10;
    params.colorFmt = YUV_420P;
    params.level = 41;
    params.primaries = 1;
    params.transfer = 1;
    params.matrix = 1;
    return params;
}

bool HasProfile(const uint8_t *data, uint32_t size, uint8_t profile)
{
    for (uint32_t index = 0; index + 5 < size; ++index) {
        if (data[index] == 0 && data[index + 1] == 0 && data[index + 2] == 0 && data[index + 3] == 1 &&
            (data[index + 4] & 31) == 7 && data[index + 5] == profile) return true;
    }
    return false;
}

void DecodedFrame(const SBufferInfo &info, uint8_t *const planes[3], const uint8_t expected[8],
    bool seen[8], int profile, int mode, int cycle)
{
    if (info.iBufferStatus != 1) return;
    const uint64_t timestamp = info.uiOutYuvTimeStamp;
    const uint64_t start = 123456789ULL;
    const bool validTime = timestamp >= start && (timestamp - start) % 33333 == 0 &&
        (timestamp - start) / 33333 < 8;
    const int frame = validTime ? static_cast<int>((timestamp - start) / 33333) : -1;
    bool pixels = validTime && !seen[frame] && info.UsrData.sSystemBuffer.iWidth == 64 &&
        info.UsrData.sSystemBuffer.iHeight == 64 && planes[0] != nullptr &&
        info.UsrData.sSystemBuffer.iStride[0] >= 64;
    uint64_t error = 0;
    if (pixels) {
        for (int row = 0; row < 64; ++row) {
            for (int column = 0; column < 64; ++column) {
                error += abs(static_cast<int>(planes[0][row * info.UsrData.sSystemBuffer.iStride[0] + column]) - expected[frame]);
            }
        }
        pixels = error <= 64 * 64 * 8;
    }
    if (pixels) { ++decoded; seen[frame] = true; }
    if (!pixels) {
        fprintf(stderr, "DECODE profile=%d mode=%d cycle=%d frame=%d output_timestamp=%llu error=%llu\n",
            profile, mode, cycle, frame, static_cast<unsigned long long>(timestamp),
            static_cast<unsigned long long>(error));
    }
    Check("real_decoded_pixels", pixels, profile, mode, cycle, frame);
}

void Boundaries()
{
    AVC_ENC_HANDLE handle = nullptr;
    auto params = Params(PROFILE_BASE, MODE_CQP);
    Check("init_null_output", InitEncoder(nullptr, &params) != 0);
    Check("init_null_config", InitEncoder(&handle, nullptr) != 0 && handle == nullptr);
    Check("release_null", ReleaseEncoder(nullptr) != 0);
    for (int variant = 0; variant < 8; ++variant) {
        auto invalid = params;
        if (variant == 0) invalid.width = UINT32_MAX;
        if (variant == 1) invalid.height = 65;
        if (variant == 2) invalid.frameRate = 0;
        if (variant == 3) invalid.bitrate = UINT32_MAX;
        if (variant == 4) invalid.qpMin = invalid.qpMax + 1;
        if (variant == 5) invalid.profile = PROFILE_HIGH;
        if (variant == 6) invalid.colorFmt = YUV_420SP_UV;
        if (variant == 7) invalid.range = 2;
        Check("invalid_config", InitEncoder(&handle, &invalid) != 0 && handle == nullptr, variant);
    }
    uint8_t destination[16];
    memset(destination, 0xA5, sizeof(destination));
    AVC_ENC_OUTARGS output = {};
    output.streamBuf = destination;
    output.size = sizeof(destination);
    SFrameBSInfo malformed = {};
    Check("empty_access_unit", !CopyAccessUnit(malformed, output));
    malformed.iLayerNum = 1;
    int length = -1;
    uint8_t payload[] = {0, 0, 0, 1};
    malformed.sLayerInfo[0].iNalCount = 1;
    malformed.sLayerInfo[0].pNalLengthInByte = &length;
    malformed.sLayerInfo[0].pBsBuf = payload;
    Check("negative_nal_length", !CopyAccessUnit(malformed, output));
    length = 4;
    malformed.sLayerInfo[0].iNalCount = INT_MAX;
    Check("oversized_nal_count", !CopyAccessUnit(malformed, output));
    malformed.sLayerInfo[0].iNalCount = 1;
    output.size = 1;
    Check("access_unit_capacity", !CopyAccessUnit(malformed, output));
    bool intact = true;
    for (uint8_t byte : destination) intact &= byte == 0xA5;
    Check("capacity_canary", intact);
}

void Cycle(int profile, int mode, int cycle)
{
    auto params = Params(profile, mode);
    AVC_ENC_HANDLE handle = nullptr;
    const auto created = InitEncoder(&handle, &params);
    Check("create", created == 0 && handle != nullptr, profile, mode, cycle);
    if (created != 0 || handle == nullptr) return;
    ISVCDecoder *decoder = nullptr;
    SDecodingParam decoding = {};
    decoding.sVideoProperty.eVideoBsType = VIDEO_BITSTREAM_AVC;
    const bool decoderReady = WelsCreateDecoder(&decoder) == 0 && decoder != nullptr &&
        decoder->Initialize(&decoding) == 0;
    Check("decoder_create", decoderReady, profile, mode, cycle);
    std::vector<uint8_t> stream(16384, 0xA5);
    AVC_ENC_OUTARGS output = {};
    output.streamBuf = stream.data();
    output.size = static_cast<uint32_t>(stream.size()) - 16;
    AVC_ENC_INARGS input = {};
    output.size = 1;
    Check("header_capacity", EncodeProcess(handle, &input, &output) != 0 && output.bytes == 0 &&
        stream[0] == 0xA5 && stream[1] == 0xA5, profile, mode, cycle);
    output.size = static_cast<uint32_t>(stream.size()) - 16;
    const bool header = EncodeProcess(handle, &input, &output) == 0 && output.bytes > 0 &&
        output.bytes <= output.size && output.encodedFrameType == 0 && output.isLast == 0 &&
        HasProfile(stream.data(), output.bytes, profile == PROFILE_MAIN ? 77 : 66);
    Check("real_parameter_sets", header, profile, mode, cycle);
    uint8_t *planes[3] = {};
    SBufferInfo info = {};
    if (decoderReady && header) decoder->DecodeFrameNoDelay(stream.data(), output.bytes, planes, &info);
    std::vector<uint8_t> y(80 * 64, 0xA5), u(40 * 32, 0xA5), v(40 * 32, 0xA5);
    input.colorFmt = YUV_420P;
    input.inputBufs[0] = y.data(); input.inputBufs[1] = u.data(); input.inputBufs[2] = v.data();
    input.width[0] = 64; input.height[0] = 64; input.stride[0] = 80;
    input.width[1] = input.width[2] = 32; input.height[1] = input.height[2] = 32;
    input.stride[1] = input.stride[2] = 40;
    input.configArgs.bitrate = params.bitrate;
    input.stride[0] = 63;
    Check("invalid_plane_stride", EncodeProcess(handle, &input, &output) != 0 && output.bytes == 0,
        profile, mode, cycle);
    input.stride[0] = 80;
    uint8_t expected[8] = {};
    bool seen[8] = {};
    for (int frame = 0; frame < 8; ++frame) {
        const uint8_t luminance = 32 + ((static_cast<unsigned char>(challenge[frame]) + frame + cycle) % 16) * 8;
        expected[frame] = luminance;
        for (int row = 0; row < 64; ++row) memset(y.data() + row * 80, luminance, 64);
        for (int row = 0; row < 32; ++row) {
            memset(u.data() + row * 40, 64, 32); memset(v.data() + row * 40, 192, 32);
        }
        input.timestamp = 123456789ULL + static_cast<uint64_t>(frame) * 33333;
        input.configArgs.idrRequest = frame == 3 ? 1 : 0;
        input.configArgs.bitrate = frame >= 2 ? 1500000 : params.bitrate;
        const bool encoded = EncodeProcess(handle, &input, &output) == 0 && output.bytes > 0 &&
            output.bytes <= output.size && output.isLast == 0 && output.timestamp == input.timestamp &&
            (output.encodedFrameType == 1 || output.encodedFrameType == 3);
        Check("encode_timestamp", encoded, profile, mode, cycle, frame);
        if (frame == 3) Check("requested_idr", encoded && output.encodedFrameType == 3, profile, mode, cycle, frame);
        memset(&info, 0, sizeof(info));
        info.uiInBsTimeStamp = input.timestamp;
        const auto decoderResult = decoderReady && encoded ?
            decoder->DecodeFrameNoDelay(stream.data(), output.bytes, planes, &info) : dsInitialOptExpected;
        Check("decoder_submit", decoderReady && encoded && decoderResult == dsErrorFree &&
            (info.iBufferStatus == 0 || info.iBufferStatus == 1), profile, mode, cycle, frame);
        if (decoderResult == dsErrorFree) DecodedFrame(info, planes, expected, seen, profile, mode, cycle);
        bool intact = true;
        for (size_t offset = output.size; offset < stream.size(); ++offset) intact &= stream[offset] == 0xA5;
        Check("output_canary", intact, profile, mode, cycle, frame);
    }
    if (decoderReady) {
        // Main profile can be buffered by the decoder, even with no B frames.
        // Require every actual output timestamp/pixel, including the drain.
        for (int attempt = 0; attempt < 8; ++attempt) {
            memset(&info, 0, sizeof(info));
            if (decoder->FlushFrame(planes, &info) != dsErrorFree || info.iBufferStatus == 0) break;
            DecodedFrame(info, planes, expected, seen, profile, mode, cycle);
        }
    }
    bool complete = true;
    for (bool observed : seen) complete &= observed;
    Check("all_decoded_frames", complete, profile, mode, cycle);
    AVC_ENC_INARGS eos = {};
    Check("eos", EncodeProcess(handle, &eos, &output) == 0 && output.isLast == 1 && output.bytes == 0,
        profile, mode, cycle);
    Check("after_eos_rejected", EncodeProcess(handle, &input, &output) != 0 && output.bytes == 0,
        profile, mode, cycle);
    Check("release", ReleaseEncoder(handle) == 0, profile, mode, cycle);
    if (decoder != nullptr) { decoder->Uninitialize(); WelsDestroyDecoder(decoder); }
}
} // namespace

int main(int argc, char **argv)
{
    if (argc != 2 || strlen(argv[1]) != 32) return 2;
    challenge = argv[1];
    for (size_t index = 0; index < 32; ++index) {
        if (!((challenge[index] >= '0' && challenge[index] <= '9') ||
              (challenge[index] >= 'a' && challenge[index] <= 'f'))) return 2;
    }
    Boundaries();
    for (int profile = PROFILE_BASE; profile <= PROFILE_MAIN; ++profile) {
        for (int mode = MODE_CQP; mode <= MODE_VBR; ++mode) {
            for (int cycle = 1; cycle <= 2; ++cycle) Cycle(profile, mode, cycle);
        }
    }
    const bool passed = failed == 0 && decoded == 96;
    printf("{\"run_id\":\"%s\",\"type\":\"summary\",\"scope\":\"host_real_codec_not_guest_acceptance\","
        "\"cases\":%d,\"decoded_frames\":%d,\"passed\":%s}\n", challenge, cases, decoded, passed ? "true" : "false");
    return passed ? 0 : 1;
}
