// SPDX-License-Identifier: Apache-2.0
// Public AVCodec APIs only. No backend injection or fabricated callbacks.
#include <multimedia/player_framework/native_avbuffer.h>
#include <multimedia/player_framework/native_avcapability.h>
#include <multimedia/player_framework/native_avcodec_videoencoder.h>
#include <multimedia/player_framework/native_avcodec_videodecoder.h>
#include <multimedia/player_framework/native_avformat.h>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <vector>
#include <unistd.h>

namespace {
constexpr int kWidth = 64;
constexpr int kHeight = 64;
constexpr int kFrames = 4;
constexpr int64_t kPts = 123456789;
constexpr int64_t kInterval = 33333;
constexpr size_t kMaxPackets = 32;
struct Input { uint32_t index; OH_AVBuffer *buffer; };
struct Packet { OH_AVCodecBufferAttr attr; std::vector<uint8_t> data; };
struct Pixels {
    int frame = -1;
    int64_t pts = -1;
    int width = 0;
    int height = 0;
    int stride = 0;
    int format = 0;
    uint64_t error = UINT64_MAX;
    uint32_t samples = 0;
};
struct Context {
    std::mutex mutex;
    std::condition_variable condition;
    std::deque<Input> inputs;
    std::vector<Packet> packets;
    std::vector<Pixels> pixels;
    bool encoder = false;
    bool eos = false;
    int error = 0;
    int width = 0;
    int height = 0;
    int stride = 0;
    int format = 0;
    uint8_t expected[kFrames] = {};
    uint8_t inputY[kFrames] = {};
    bool callbackStorageAttached = false;
};

struct CallbackLifetime {
    void operator()(Context *context) const
    {
        // A test exception or failed Destroy must not free live callback data.
        if (!context->callbackStorageAttached) delete context;
    }
};

void Error(OH_AVCodec *, int32_t error, void *data)
{
    auto &context = *static_cast<Context *>(data);
    std::lock_guard<std::mutex> lock(context.mutex);
    context.error = error == 0 ? -1 : error;
    context.condition.notify_all();
}

void Changed(OH_AVCodec *, OH_AVFormat *format, void *data)
{
    auto &context = *static_cast<Context *>(data);
    std::lock_guard<std::mutex> lock(context.mutex);
    OH_AVFormat_GetIntValue(format, OH_MD_KEY_WIDTH, &context.width);
    OH_AVFormat_GetIntValue(format, OH_MD_KEY_HEIGHT, &context.height);
    OH_AVFormat_GetIntValue(format, OH_MD_KEY_VIDEO_STRIDE, &context.stride);
    OH_AVFormat_GetIntValue(format, OH_MD_KEY_PIXEL_FORMAT, &context.format);
}

void NeedInput(OH_AVCodec *, uint32_t index, OH_AVBuffer *buffer, void *data)
{
    auto &context = *static_cast<Context *>(data);
    std::lock_guard<std::mutex> lock(context.mutex);
    try {
        if (buffer == nullptr || context.inputs.size() >= kMaxPackets) context.error = -2;
        else context.inputs.push_back({index, buffer});
    } catch (...) { context.error = -3; }
    context.condition.notify_all();
}

Pixels ReadPixels(const Context &context, const OH_AVCodecBufferAttr &attr, const uint8_t *address, int capacity)
{
    Pixels result;
    result.pts = attr.pts;
    result.width = context.width;
    result.height = context.height;
    result.stride = context.stride;
    result.format = context.format;
    const int64_t delta = attr.pts >= kPts ? attr.pts - kPts : -1;
    if (delta >= 0 && delta % kInterval == 0 && delta / kInterval < kFrames) {
        result.frame = static_cast<int>(delta / kInterval);
    }
    if (result.frame < 0 || address == nullptr || result.width != kWidth || result.height != kHeight ||
        result.format != AV_PIXEL_FORMAT_YUVI420 || result.stride < kWidth || result.stride > 16384 ||
        static_cast<int64_t>(kHeight - 1) * result.stride + kWidth > attr.size ||
        attr.offset < 0 || attr.size > capacity - attr.offset) return result;
    result.error = 0;
    for (int row = 0; row < kHeight; ++row) {
        for (int column = 0; column < kWidth; ++column) {
            const int sample = address[attr.offset + row * result.stride + column];
            const int difference = sample - context.expected[result.frame];
            result.error += static_cast<uint64_t>(difference < 0 ? -difference : difference);
            ++result.samples;
        }
    }
    return result;
}

void Output(OH_AVCodec *codec, uint32_t index, OH_AVBuffer *buffer, void *data)
{
    auto &context = *static_cast<Context *>(data);
    OH_AVCodecBufferAttr attr = {};
    const auto attributes = OH_AVBuffer_GetBufferAttr(buffer, &attr);
    const int capacity = OH_AVBuffer_GetCapacity(buffer);
    const auto *address = OH_AVBuffer_GetAddr(buffer);
    {
        std::lock_guard<std::mutex> lock(context.mutex);
        try {
            if (attributes != AV_ERR_OK || attr.offset < 0 || attr.size < 0 ||
                attr.offset > capacity || attr.size > capacity - attr.offset ||
                (attr.size != 0 && address == nullptr)) context.error = -4;
            else if (context.encoder) {
                if (context.packets.size() >= kMaxPackets) context.error = -5;
                else {
                    Packet packet{attr, {}};
                    if (attr.size != 0) packet.data.assign(address + attr.offset, address + attr.offset + attr.size);
                    context.packets.push_back(std::move(packet));
                }
            } else if (attr.size > 0 && (attr.flags & AVCODEC_BUFFER_FLAGS_CODEC_DATA) == 0) {
                if (context.pixels.size() >= kFrames + 1) context.error = -6;
                else context.pixels.push_back(ReadPixels(context, attr, address, capacity));
            }
            if ((attr.flags & AVCODEC_BUFFER_FLAGS_EOS) != 0) context.eos = true;
        } catch (...) { context.error = -7; }
    }
    const auto released = context.encoder ? OH_VideoEncoder_FreeOutputBuffer(codec, index) :
        OH_VideoDecoder_FreeOutputBuffer(codec, index);
    if (released != AV_ERR_OK) Error(codec, released, data);
    context.condition.notify_all();
}

bool Step(FILE *out, const char *run, int profile, int mode, int cycle, const char *name, int actual, int expected)
{
    const bool passed = actual == expected;
    fprintf(out, "{\"type\":\"step\",\"run_id\":\"%s\",\"profile\":%d,\"mode\":%d,\"cycle\":%d,"
        "\"name\":\"%s\",\"actual\":%d,\"expected\":%d,\"passed\":%s}\n",
        run, profile, mode, cycle, name, actual, expected, passed ? "true" : "false");
    fflush(out);
    return passed;
}

bool InputBuffer(Context &context, Input &input)
{
    std::unique_lock<std::mutex> lock(context.mutex);
    if (!context.condition.wait_for(lock, std::chrono::seconds(3), [&] {
        return context.error != 0 || !context.inputs.empty();
    }) || context.error != 0) return false;
    input = context.inputs.front();
    context.inputs.pop_front();
    return true;
}

bool Wait(Context &context, int64_t pts, bool eos)
{
    std::unique_lock<std::mutex> lock(context.mutex);
    const bool ready = context.condition.wait_for(lock, std::chrono::seconds(5), [&] {
        if (context.error != 0 || (eos && context.eos)) return true;
        for (const auto &packet : context.packets) {
            if (!eos && packet.attr.pts == pts && packet.attr.size > 0 &&
                (packet.attr.flags & AVCODEC_BUFFER_FLAGS_CODEC_DATA) == 0) return true;
        }
        return false;
    });
    return ready && context.error == 0;
}

OH_AVFormat *Configuration(int profile, int mode, bool encoder, bool rgba = false)
{
    OH_AVFormat *format = OH_AVFormat_Create();
    if (format == nullptr) return nullptr;
    bool valid = OH_AVFormat_SetIntValue(format, OH_MD_KEY_WIDTH, kWidth) &&
        OH_AVFormat_SetIntValue(format, OH_MD_KEY_HEIGHT, kHeight) &&
        OH_AVFormat_SetIntValue(format, OH_MD_KEY_PIXEL_FORMAT, rgba ? AV_PIXEL_FORMAT_RGBA : AV_PIXEL_FORMAT_YUVI420) &&
        OH_AVFormat_SetDoubleValue(format, OH_MD_KEY_FRAME_RATE, 30);
    if (encoder) {
        // The actual OHOS CodecParamChecker rejects quality plus bitrate,
        // bitrate in CQ, and quality outside CQ. Exercise valid modes rather
        // than starting a codec whose Configure has already failed.
        valid = valid && (mode == BITRATE_MODE_CQ ?
            OH_AVFormat_SetIntValue(format, OH_MD_KEY_QUALITY, 90) :
            OH_AVFormat_SetLongValue(format, OH_MD_KEY_BITRATE, 1000000)) &&
            OH_AVFormat_SetIntValue(format, OH_MD_KEY_VIDEO_ENCODE_BITRATE_MODE, mode) &&
            OH_AVFormat_SetIntValue(format, OH_MD_KEY_PROFILE, profile) &&
            OH_AVFormat_SetIntValue(format, OH_MD_KEY_I_FRAME_INTERVAL, 10000);
    }
    if (!valid) { OH_AVFormat_Destroy(format); return nullptr; }
    return format;
}

bool FeedFrame(OH_AVCodec *codec, Context &context, int frame, bool rgba)
{
    Input input = {};
    if (!InputBuffer(context, input)) return false;
    const int size = rgba ? kWidth * kHeight * 4 : kWidth * kHeight * 3 / 2;
    uint8_t *data = OH_AVBuffer_GetAddr(input.buffer);
    if (data == nullptr || OH_AVBuffer_GetCapacity(input.buffer) < size) return false;
    if (rgba) {
        for (int pixel = 0; pixel < kWidth * kHeight; ++pixel) {
            data[pixel * 4] = context.inputY[frame];
            data[pixel * 4 + 1] = context.inputY[frame];
            data[pixel * 4 + 2] = context.inputY[frame];
            data[pixel * 4 + 3] = 255;
        }
    } else {
        std::memset(data, context.expected[frame], kWidth * kHeight);
        std::memset(data + kWidth * kHeight, 64, kWidth * kHeight / 4);
        std::memset(data + kWidth * kHeight * 5 / 4, 192, kWidth * kHeight / 4);
    }
    const OH_AVCodecBufferAttr attr = {kPts + frame * kInterval, size, 0, AVCODEC_BUFFER_FLAGS_NONE};
    return OH_AVBuffer_SetBufferAttr(input.buffer, &attr) == AV_ERR_OK &&
        OH_VideoEncoder_PushInputBuffer(codec, input.index) == AV_ERR_OK && Wait(context, attr.pts, false);
}

int SetParameter(OH_AVCodec *codec, bool idr)
{
    OH_AVFormat *format = OH_AVFormat_Create();
    if (format == nullptr) return AV_ERR_UNKNOWN;
    const bool valid = idr ? OH_AVFormat_SetIntValue(format, OH_MD_KEY_REQUEST_I_FRAME, 1) :
        OH_AVFormat_SetLongValue(format, OH_MD_KEY_BITRATE, 1500000);
    const auto result = valid ? OH_VideoEncoder_SetParameter(codec, format) : AV_ERR_UNKNOWN;
    OH_AVFormat_Destroy(format);
    return result;
}

bool EndEncoding(OH_AVCodec *codec, Context &context)
{
    Input input = {};
    if (!InputBuffer(context, input)) return false;
    const OH_AVCodecBufferAttr attr = {kPts + kFrames * kInterval, 0, 0, AVCODEC_BUFFER_FLAGS_EOS};
    return OH_AVBuffer_SetBufferAttr(input.buffer, &attr) == AV_ERR_OK &&
        OH_VideoEncoder_PushInputBuffer(codec, input.index) == AV_ERR_OK && Wait(context, 0, true);
}

bool FeedPacket(OH_AVCodec *codec, Context &context, const Packet &packet)
{
    Input input = {};
    if (!InputBuffer(context, input) || packet.data.size() > INT32_MAX) return false;
    const int capacity = OH_AVBuffer_GetCapacity(input.buffer);
    uint8_t *data = OH_AVBuffer_GetAddr(input.buffer);
    if (capacity < 0 || packet.data.size() > static_cast<size_t>(capacity) ||
        (!packet.data.empty() && data == nullptr)) return false;
    if (!packet.data.empty()) std::memcpy(data, packet.data.data(), packet.data.size());
    OH_AVCodecBufferAttr attr = packet.attr;
    attr.offset = 0;
    attr.size = static_cast<int>(packet.data.size());
    return OH_AVBuffer_SetBufferAttr(input.buffer, &attr) == AV_ERR_OK &&
        OH_VideoDecoder_PushInputBuffer(codec, input.index) == AV_ERR_OK;
}

bool Decode(FILE *out, const char *run, int profile, int mode, int cycle, const std::vector<Packet> &packets,
    const uint8_t expected[kFrames])
{
    std::unique_ptr<Context, CallbackLifetime> context(new Context);
    std::memcpy(context->expected, expected, kFrames);
    auto step = [&](const char *name, int actual, int wanted = AV_ERR_OK) {
        return Step(out, run, profile, mode, cycle, name, actual, wanted);
    };
    OH_AVCapability *capability = OH_AVCodec_GetCapability(OH_AVCODEC_MIMETYPE_VIDEO_AVC, false);
    const char *name = capability == nullptr || OH_AVCapability_IsHardware(capability) ? nullptr : OH_AVCapability_GetName(capability);
    OH_AVCodec *codec = name == nullptr ? nullptr : (cycle == 1 ?
        OH_VideoDecoder_CreateByMime(OH_AVCODEC_MIMETYPE_VIDEO_AVC) : OH_VideoDecoder_CreateByName(name));
    bool valid = step("decoder_creation_path", cycle, cycle);
    valid &= step("decoder_create", codec != nullptr, 1);
    if (codec == nullptr) return false;
    const OH_AVCodecCallback callbacks = {Error, Changed, NeedInput, Output};
    context->callbackStorageAttached = true;
    valid &= step("decoder_register", OH_VideoDecoder_RegisterCallback(codec, callbacks, context.get()));
    OH_AVFormat *format = Configuration(profile, mode, false);
    valid &= step("decoder_configure", format == nullptr ? AV_ERR_UNKNOWN : OH_VideoDecoder_Configure(codec, format));
    if (format != nullptr) OH_AVFormat_Destroy(format);
    valid &= step("decoder_prepare", OH_VideoDecoder_Prepare(codec));
    const auto started = OH_VideoDecoder_Start(codec);
    valid &= step("decoder_start", started);
    if (started == AV_ERR_OK) {
        bool fed = !packets.empty();
        for (const auto &packet : packets) { if (!(fed = FeedPacket(codec, *context, packet) && fed)) break; }
        valid &= step("decoder_feed", fed, 1);
        valid &= step("decoder_eos", fed && Wait(*context, 0, true), 1);
        valid &= step("decoder_stop", OH_VideoDecoder_Stop(codec));
    }
    const auto destroyed = OH_VideoDecoder_Destroy(codec);
    valid &= step("decoder_destroy", destroyed);
    if (destroyed != AV_ERR_OK) { (void)context.release(); return false; }
    context->callbackStorageAttached = false;
    bool seen[kFrames] = {};
    for (const auto &pixels : context->pixels) {
        const bool passed = pixels.frame >= 0 && !seen[pixels.frame] && pixels.samples == kWidth * kHeight &&
            pixels.error <= pixels.samples * 8;
        if (passed) seen[pixels.frame] = true;
        valid &= passed;
        fprintf(out, "{\"type\":\"pixels\",\"run_id\":\"%s\",\"profile\":%d,\"mode\":%d,\"cycle\":%d,"
            "\"frame\":%d,\"pts\":%lld,\"width\":%d,\"height\":%d,\"stride\":%d,\"format\":%d,"
            "\"expected_y\":%u,\"samples\":%u,\"absolute_error\":%llu,\"passed\":%s}\n",
            run, profile, mode, cycle, pixels.frame, static_cast<long long>(pixels.pts), pixels.width,
            pixels.height, pixels.stride, pixels.format, pixels.frame < 0 ? 0 : expected[pixels.frame],
            pixels.samples, static_cast<unsigned long long>(pixels.error), passed ? "true" : "false");
    }
    for (bool frame : seen) valid &= frame;
    return step("all_decoded_frames", context->pixels.size() == kFrames && valid, 1) && valid;
}

bool Cycle(FILE *out, const char *run, int profile, int mode, int cycle)
{
    std::unique_ptr<Context, CallbackLifetime> context(new Context);
    context->encoder = true;
    const bool rgba = cycle == 3;
    for (int frame = 0; frame < kFrames; ++frame) {
        context->inputY[frame] = 32 + ((static_cast<unsigned char>(run[frame]) + frame + cycle) % 16) * 8;
        // Actual default BT601/BT709 limited-range conversion has luma weights
        // summing to 220. Decode the emitted stream, never inspect input as output.
        context->expected[frame] = rgba ? 16 + ((context->inputY[frame] * 220) >> 8) : context->inputY[frame];
    }
    auto step = [&](const char *name, int actual, int wanted = AV_ERR_OK) {
        return Step(out, run, profile, mode, cycle, name, actual, wanted);
    };
    OH_AVCapability *capability = OH_AVCodec_GetCapability(OH_AVCODEC_MIMETYPE_VIDEO_AVC, true);
    const char *name = capability == nullptr ? nullptr : OH_AVCapability_GetName(capability);
    OH_AVCodec *codec = name == nullptr ? nullptr : (cycle == 1 ?
        OH_VideoEncoder_CreateByMime(OH_AVCODEC_MIMETYPE_VIDEO_AVC) : OH_VideoEncoder_CreateByName(name));
    bool valid = step("encoder_creation_path", cycle, cycle);
    valid &= step("default_encoder_create", codec != nullptr && !OH_AVCapability_IsHardware(capability), 1);
    if (codec == nullptr) return false;
    const OH_AVCodecCallback callbacks = {Error, Changed, NeedInput, Output};
    context->callbackStorageAttached = true;
    valid &= step("encoder_register", OH_VideoEncoder_RegisterCallback(codec, callbacks, context.get()));
    OH_AVFormat *format = Configuration(profile, mode, true, rgba);
    valid &= step("encoder_configure", format == nullptr ? AV_ERR_UNKNOWN : OH_VideoEncoder_Configure(codec, format));
    if (format != nullptr) OH_AVFormat_Destroy(format);
    valid &= step("encoder_prepare", OH_VideoEncoder_Prepare(codec));
    const auto started = OH_VideoEncoder_Start(codec);
    valid &= step("encoder_start", started);
    if (started == AV_ERR_OK) {
        const char *frameNames[kFrames] = {"encode_frame_0", "encode_frame_1", "encode_frame_2", "encode_frame_3"};
        for (int frame = 0; frame < kFrames; ++frame) {
            if (frame == 1) valid &= step(mode == BITRATE_MODE_CQ ? "dynamic_bitrate_cq_rejected" :
                "dynamic_bitrate", SetParameter(codec, false), mode == BITRATE_MODE_CQ ? AV_ERR_INVALID_VAL : AV_ERR_OK);
            if (frame == 2) valid &= step("request_idr", SetParameter(codec, true));
            valid &= step(frameNames[frame], FeedFrame(codec, *context, frame, rgba), 1);
        }
        valid &= step("encoder_eos", EndEncoding(codec, *context), 1);
        valid &= step("encoder_stop", OH_VideoEncoder_Stop(codec));
    }
    const auto destroyed = OH_VideoEncoder_Destroy(codec);
    valid &= step("encoder_destroy", destroyed);
    if (destroyed != AV_ERR_OK) { (void)context.release(); return false; }
    context->callbackStorageAttached = false;
    bool headers = false, seen[kFrames] = {}, idr = false;
    for (const auto &packet : context->packets) {
        headers |= packet.attr.size > 0 && (packet.attr.flags & AVCODEC_BUFFER_FLAGS_CODEC_DATA) != 0;
        const int64_t delta = packet.attr.pts >= kPts ? packet.attr.pts - kPts : -1;
        if (packet.attr.size > 0 && (packet.attr.flags & AVCODEC_BUFFER_FLAGS_CODEC_DATA) == 0) {
            const bool timestamp = delta >= 0 && delta % kInterval == 0 && delta / kInterval < kFrames;
            valid &= timestamp && !seen[delta / kInterval];
            if (timestamp) {
                seen[delta / kInterval] = true;
                if (delta / kInterval == 2) idr = (packet.attr.flags & AVCODEC_BUFFER_FLAGS_SYNC_FRAME) != 0;
            }
        }
    }
    for (bool frame : seen) valid &= frame;
    valid &= step("real_headers_and_requested_idr", headers && idr && context->error == 0 && valid, 1);
    for (const auto &packet : context->packets) {
        int spsProfile = -1;
        for (size_t index = 0; index + 4 < packet.data.size(); ++index) {
            if (packet.data[index] == 0 && packet.data[index + 1] == 0 && packet.data[index + 2] == 1 &&
                (packet.data[index + 3] & 31) == 7) spsProfile = packet.data[index + 4];
        }
        fprintf(out, "{\"type\":\"bitstream\",\"run_id\":\"%s\",\"profile\":%d,\"mode\":%d,\"cycle\":%d,"
            "\"pts\":%lld,\"bytes\":%zu,\"flags\":%u,\"sps_profile\":%d}\n",
            run, profile, mode, cycle, static_cast<long long>(packet.attr.pts), packet.data.size(), packet.attr.flags, spsProfile);
    }
    valid = Decode(out, run, profile, mode, cycle, context->packets, context->expected) && valid;
    fprintf(out, "{\"type\":\"cycle\",\"run_id\":\"%s\",\"profile\":%d,\"mode\":%d,\"cycle\":%d,"
        "\"frames\":4,\"passed\":%s}\n", run, profile, mode, cycle, valid ? "true" : "false");
    fflush(out);
    return valid;
}

bool DefaultIsSoftware(bool encoder)
{
    OH_AVCapability *capability = OH_AVCodec_GetCapability(OH_AVCODEC_MIMETYPE_VIDEO_AVC, encoder);
    const char *selected = capability == nullptr ? nullptr : OH_AVCapability_GetName(capability);
    if (selected == nullptr || OH_AVCapability_IsHardware(capability)) return false;
    const std::string name(selected);
    OH_AVCapability *software = OH_AVCodec_GetCapabilityByCategory(OH_AVCODEC_MIMETYPE_VIDEO_AVC, encoder, SOFTWARE);
    const char *softwareName = software == nullptr ? nullptr : OH_AVCapability_GetName(software);
    return softwareName != nullptr && !OH_AVCapability_IsHardware(software) && name == softwareName;
}

bool RejectName(const char *name, bool encoder)
{
    OH_AVCodec *codec = encoder ? OH_VideoEncoder_CreateByName(name) : OH_VideoDecoder_CreateByName(name);
    if (codec == nullptr) return true;
    // Always destroy an unexpected live instance, even though this boundary fails.
    if (encoder) OH_VideoEncoder_Destroy(codec);
    else OH_VideoDecoder_Destroy(codec);
    return false;
}

bool TruncatedRgba(FILE *out, const char *run)
{
    std::unique_ptr<Context, CallbackLifetime> context(new Context);
    context->encoder = true;
    auto step = [&](const char *name, int actual, int wanted = AV_ERR_OK) {
        return Step(out, run, -2, -2, -2, name, actual, wanted);
    };
    OH_AVCodec *codec = OH_VideoEncoder_CreateByMime(OH_AVCODEC_MIMETYPE_VIDEO_AVC);
    bool valid = step("truncated_rgba_create", codec != nullptr, 1);
    if (codec == nullptr) return false;
    const OH_AVCodecCallback callbacks = {Error, Changed, NeedInput, Output};
    context->callbackStorageAttached = true;
    valid &= step("truncated_rgba_register", OH_VideoEncoder_RegisterCallback(codec, callbacks, context.get()));
    OH_AVFormat *format = Configuration(AVC_PROFILE_BASELINE, BITRATE_MODE_CBR, true, true);
    valid &= step("truncated_rgba_configure", format == nullptr ? AV_ERR_UNKNOWN : OH_VideoEncoder_Configure(codec, format));
    if (format != nullptr) OH_AVFormat_Destroy(format);
    valid &= step("truncated_rgba_prepare", OH_VideoEncoder_Prepare(codec));
    const auto started = OH_VideoEncoder_Start(codec);
    valid &= step("truncated_rgba_start", started);
    int submitted = AV_ERR_UNKNOWN;
    if (started == AV_ERR_OK) {
        Input input = {};
        if (InputBuffer(*context, input)) {
            uint8_t *address = OH_AVBuffer_GetAddr(input.buffer);
            const int size = kWidth * kHeight * 4;
            if (address != nullptr && OH_AVBuffer_GetCapacity(input.buffer) >= size) {
                // Capacity is sufficient, but the declared frame is one byte
                // short. The old wrapper reads undeclared bytes and encodes it.
                std::memset(address, 128, size);
                const OH_AVCodecBufferAttr attr = {kPts, size - 1, 0, AVCODEC_BUFFER_FLAGS_NONE};
                if (OH_AVBuffer_SetBufferAttr(input.buffer, &attr) == AV_ERR_OK) {
                    submitted = OH_VideoEncoder_PushInputBuffer(codec, input.index);
                }
            }
        }
    }
    valid &= step("truncated_rgba_push", submitted);
    int error = 0;
    {
        std::unique_lock<std::mutex> lock(context->mutex);
        context->condition.wait_for(lock, std::chrono::seconds(5), [&] {
            return context->error != 0 || !context->packets.empty();
        });
        error = context->error;
    }
    valid &= step("truncated_rgba_error", error, AV_ERR_UNKNOWN);
    const auto destroyed = OH_VideoEncoder_Destroy(codec);
    valid &= step("truncated_rgba_destroy", destroyed);
    {
        std::lock_guard<std::mutex> lock(context->mutex);
        valid &= step("truncated_rgba_no_encoded_output", context->packets.empty(), 1);
    }
    if (destroyed != AV_ERR_OK) { (void)context.release(); return false; }
    context->callbackStorageAttached = false;
    return valid;
}
} // namespace

extern "C" int RunAvcMediaProbe(FILE *out, const char *run)
{
    fprintf(out, "{\"type\":\"identity\",\"run_id\":\"%s\",\"uid\":%u,\"euid\":%u}\n",
        run, static_cast<unsigned>(getuid()), static_cast<unsigned>(geteuid()));
    bool passed = Step(out, run, -1, -1, -1, "null_encoder_start", OH_VideoEncoder_Start(nullptr), AV_ERR_INVALID_VAL);
    passed &= Step(out, run, -1, -1, -1, "null_decoder_start", OH_VideoDecoder_Start(nullptr), AV_ERR_INVALID_VAL);
    passed &= Step(out, run, -1, -1, -1, "null_encoder_configure", OH_VideoEncoder_Configure(nullptr, nullptr), AV_ERR_INVALID_VAL);
    auto boundary = [&](const char *name, bool actual) {
        passed &= Step(out, run, -1, -1, -1, name, actual, 1);
    };
    boundary("avc_encoder_default_is_software", DefaultIsSoftware(true));
    boundary("avc_decoder_default_is_software", DefaultIsSoftware(false));
    boundary("avc_encoder_hardware_absent", OH_AVCodec_GetCapabilityByCategory(OH_AVCODEC_MIMETYPE_VIDEO_AVC, true, HARDWARE) == nullptr);
    boundary("avc_decoder_hardware_absent", OH_AVCodec_GetCapabilityByCategory(OH_AVCODEC_MIMETYPE_VIDEO_AVC, false, HARDWARE) == nullptr);
    boundary("hevc_encoder_unadvertised", OH_AVCodec_GetCapability(OH_AVCODEC_MIMETYPE_VIDEO_HEVC, true) == nullptr);
    boundary("hevc_encoder_hardware_absent", OH_AVCodec_GetCapabilityByCategory(OH_AVCODEC_MIMETYPE_VIDEO_HEVC, true, HARDWARE) == nullptr);
    boundary("hevc_decoder_hardware_absent", OH_AVCodec_GetCapabilityByCategory(OH_AVCODEC_MIMETYPE_VIDEO_HEVC, false, HARDWARE) == nullptr);
    boundary("legacy_rk_encoder_avc_rejected", RejectName("OMX.rk.video_encoder.avc", true));
    boundary("legacy_rk_encoder_hevc_rejected", RejectName("OMX.rk.video_encoder.hevc", true));
    boundary("legacy_rk_decoder_avc_rejected", RejectName("OMX.rk.video_decoder.avc", false));
    boundary("legacy_rk_decoder_hevc_rejected", RejectName("OMX.rk.video_decoder.hevc", false));
    OH_AVCodec *unsupported = OH_VideoEncoder_CreateByMime(OH_AVCODEC_MIMETYPE_VIDEO_HEVC);
    boundary("hevc_create_by_mime_unsupported", unsupported == nullptr);
    if (unsupported != nullptr) OH_VideoEncoder_Destroy(unsupported);
    passed = TruncatedRgba(out, run) && passed;
    const int profiles[] = {AVC_PROFILE_BASELINE, AVC_PROFILE_MAIN};
    const int modes[] = {BITRATE_MODE_CBR, BITRATE_MODE_VBR, BITRATE_MODE_CQ};
    for (int profile : profiles) for (int mode : modes) for (int cycle = 1; cycle <= 3; ++cycle) {
        passed = Cycle(out, run, profile, mode, cycle) && passed;
    }
    fprintf(out, "{\"type\":\"summary\",\"run_id\":\"%s\",\"cycles\":18,\"frames\":72,\"passed\":%s}\n",
        run, passed ? "true" : "false");
    fflush(out);
    return passed ? 0 : 1;
}
