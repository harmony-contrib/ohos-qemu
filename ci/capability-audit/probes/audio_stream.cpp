// SPDX-License-Identifier: Apache-2.0
// Real OHAudio calls. Callback counters are atomic; no system-library injection.
#include <ohaudio/native_audiorenderer.h>
#include <ohaudio/native_audiostreambuilder.h>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <new>
#include <string>
#include <unistd.h>

namespace {
struct Counters {
    std::atomic<uint32_t> callbacks{0};
    std::atomic<uint64_t> bytes{0};
    std::atomic<uint32_t> invalidBuffers{0};
    std::atomic<int32_t> error{0};
};

OH_AudioData_Callback_Result Write(OH_AudioRenderer *, void *data, void *buffer, int32_t length)
{
    auto &counters = *static_cast<Counters *>(data);
    if (buffer == nullptr || length <= 0 || length % 4 != 0) {
        counters.invalidBuffers.fetch_add(1);
        return AUDIO_DATA_CALLBACK_RESULT_INVALID;
    }
    auto *bytes = static_cast<uint8_t *>(buffer);
    for (int32_t offset = 0; offset < length; offset += 4) {
        const int16_t sample = ((offset / 4) % 48 < 24) ? 4096 : -4096;
        // memcpy avoids assuming callback-buffer alignment. Stereo signed PCM.
        std::memcpy(bytes + offset, &sample, 2);
        std::memcpy(bytes + offset + 2, &sample, 2);
    }
    counters.bytes.fetch_add(static_cast<uint64_t>(length));
    counters.callbacks.fetch_add(1);
    return AUDIO_DATA_CALLBACK_RESULT_VALID;
}

void Error(OH_AudioRenderer *, void *data, OH_AudioStream_Result error)
{
    static_cast<Counters *>(data)->error.store(error);
}

bool Step(FILE *out, const char *run, int cycle, const char *name, int actual, int expected)
{
    const bool passed = actual == expected;
    fprintf(out, "{\"type\":\"step\",\"run_id\":\"%s\",\"cycle\":%d,"
        "\"name\":\"%s\",\"actual\":%d,\"expected\":%d,\"passed\":%s}\n",
        run, cycle, name, actual, expected, passed ? "true" : "false");
    fflush(out);
    return passed;
}

bool State(FILE *out, const char *run, int cycle, OH_AudioRenderer *renderer,
    const char *name, OH_AudioStream_State expected)
{
    OH_AudioStream_State state = AUDIOSTREAM_STATE_INVALID;
    const auto result = OH_AudioRenderer_GetCurrentState(renderer, &state);
    const bool call = Step(out, run, cycle, name, result, AUDIOSTREAM_SUCCESS);
    return Step(out, run, cycle, (std::string(name) + ".value").c_str(), state, expected) && call;
}

bool Progress(FILE *out, const char *run, int cycle, OH_AudioRenderer *renderer,
    Counters &counters, const char *phase)
{
    const auto previousCallbacks = counters.callbacks.load();
    int64_t before = -1;
    const auto beforeResult = OH_AudioRenderer_GetFramesWritten(renderer, &before);
    bool valid = Step(out, run, cycle, "frames_before", beforeResult, AUDIOSTREAM_SUCCESS);
    int64_t frames = -1;
    auto result = AUDIOSTREAM_ERROR_SYSTEM;
    // Bounded real data-path wait, not a fabricated callback or fixed sleep pass.
    for (int tick = 0; tick < 150; ++tick) {
        usleep(20000);
        result = OH_AudioRenderer_GetFramesWritten(renderer, &frames);
        if (result != AUDIOSTREAM_SUCCESS || counters.error.load() != 0) break;
        if (frames > before && counters.callbacks.load() > previousCallbacks + 2) break;
    }
    const uint32_t callbacks = counters.callbacks.load();
    const uint64_t bytes = counters.bytes.load();
    const uint32_t invalid = counters.invalidBuffers.load();
    const int error = counters.error.load();
    valid = valid && result == AUDIOSTREAM_SUCCESS && before >= 0 && frames > before &&
        callbacks > previousCallbacks + 2 && bytes > 0 && invalid == 0 && error == 0;
    fprintf(out, "{\"type\":\"progress\",\"run_id\":\"%s\",\"cycle\":%d,"
        "\"phase\":\"%s\",\"result\":%d,\"before_frames\":%lld,\"frames\":%lld,"
        "\"before_callbacks\":%u,\"callbacks\":%u,\"bytes\":%llu,"
        "\"invalid_buffers\":%u,\"callback_error\":%d,\"passed\":%s}\n",
        run, cycle, phase, result, static_cast<long long>(before), static_cast<long long>(frames),
        previousCallbacks, callbacks, static_cast<unsigned long long>(bytes), invalid, error,
        valid ? "true" : "false");
    fflush(out);
    return valid;
}

bool Cycle(FILE *out, const char *run, int cycle)
{
    std::unique_ptr<Counters> counters(new (std::nothrow) Counters);
    if (!counters) return false;
    OH_AudioStreamBuilder *builder = nullptr;
    OH_AudioRenderer *renderer = nullptr;
    bool passed = Step(out, run, cycle, "create",
        OH_AudioStreamBuilder_Create(&builder, AUDIOSTREAM_TYPE_RENDERER), AUDIOSTREAM_SUCCESS);
    if (builder == nullptr) return false;
    passed &= Step(out, run, cycle, "invalid_channels",
        OH_AudioStreamBuilder_SetChannelCount(builder, 0), AUDIOSTREAM_ERROR_INVALID_PARAM);
    passed &= Step(out, run, cycle, "rate",
        OH_AudioStreamBuilder_SetSamplingRate(builder, 48000), AUDIOSTREAM_SUCCESS);
    passed &= Step(out, run, cycle, "channels",
        OH_AudioStreamBuilder_SetChannelCount(builder, 2), AUDIOSTREAM_SUCCESS);
    passed &= Step(out, run, cycle, "format",
        OH_AudioStreamBuilder_SetSampleFormat(builder, AUDIOSTREAM_SAMPLE_S16LE), AUDIOSTREAM_SUCCESS);
    passed &= Step(out, run, cycle, "encoding",
        OH_AudioStreamBuilder_SetEncodingType(builder, AUDIOSTREAM_ENCODING_TYPE_RAW), AUDIOSTREAM_SUCCESS);
    passed &= Step(out, run, cycle, "latency",
        OH_AudioStreamBuilder_SetLatencyMode(builder, AUDIOSTREAM_LATENCY_MODE_NORMAL), AUDIOSTREAM_SUCCESS);
    passed &= Step(out, run, cycle, "usage",
        OH_AudioStreamBuilder_SetRendererInfo(builder, AUDIOSTREAM_USAGE_MUSIC), AUDIOSTREAM_SUCCESS);
    passed &= Step(out, run, cycle, "write_callback",
        OH_AudioStreamBuilder_SetRendererWriteDataCallback(builder, Write, counters.get()), AUDIOSTREAM_SUCCESS);
    passed &= Step(out, run, cycle, "error_callback",
        OH_AudioStreamBuilder_SetRendererErrorCallback(builder, Error, counters.get()), AUDIOSTREAM_SUCCESS);
    passed &= Step(out, run, cycle, "generate",
        OH_AudioStreamBuilder_GenerateRenderer(builder, &renderer), AUDIOSTREAM_SUCCESS);
    if (renderer != nullptr) {
        // Once attached, keep callback storage alive even if a later test
        // operation throws before release. Delete only after successful release.
        Counters &liveCounters = *counters.release();
        passed &= State(out, run, cycle, renderer, "prepared", AUDIOSTREAM_STATE_PREPARED);
        passed &= Step(out, run, cycle, "pause_before_start",
            OH_AudioRenderer_Pause(renderer), AUDIOSTREAM_ERROR_ILLEGAL_STATE);
        const auto started = OH_AudioRenderer_Start(renderer);
        passed &= Step(out, run, cycle, "start", started, AUDIOSTREAM_SUCCESS);
        if (started == AUDIOSTREAM_SUCCESS) {
            passed &= State(out, run, cycle, renderer, "running", AUDIOSTREAM_STATE_RUNNING);
            passed &= Progress(out, run, cycle, renderer, liveCounters, "initial");
            const auto paused = OH_AudioRenderer_Pause(renderer);
            passed &= Step(out, run, cycle, "pause", paused, AUDIOSTREAM_SUCCESS);
            if (paused == AUDIOSTREAM_SUCCESS) {
                passed &= State(out, run, cycle, renderer, "paused", AUDIOSTREAM_STATE_PAUSED);
                passed &= Step(out, run, cycle, "flush", OH_AudioRenderer_Flush(renderer), AUDIOSTREAM_SUCCESS);
                const auto resumed = OH_AudioRenderer_Start(renderer);
                passed &= Step(out, run, cycle, "resume", resumed, AUDIOSTREAM_SUCCESS);
                if (resumed == AUDIOSTREAM_SUCCESS) {
                    passed &= State(out, run, cycle, renderer, "resumed", AUDIOSTREAM_STATE_RUNNING);
                    passed &= Progress(out, run, cycle, renderer, liveCounters, "resumed");
                }
            }
            passed &= Step(out, run, cycle, "stop", OH_AudioRenderer_Stop(renderer), AUDIOSTREAM_SUCCESS);
            passed &= State(out, run, cycle, renderer, "stopped", AUDIOSTREAM_STATE_STOPPED);
        }
        const auto released = OH_AudioRenderer_Release(renderer);
        passed &= Step(out, run, cycle, "release", released, AUDIOSTREAM_SUCCESS);
        // A failed release may leave callbacks alive. Preserve their storage;
        // the failed record remains a failure, not a use-after-free or a pass.
        if (released == AUDIOSTREAM_SUCCESS) delete &liveCounters;
    } else {
        passed = false;
    }
    passed &= Step(out, run, cycle, "destroy", OH_AudioStreamBuilder_Destroy(builder), AUDIOSTREAM_SUCCESS);
    return passed;
}
}

extern "C" int RunAudioStreamProbe(FILE *out, const char *run)
{
    fprintf(out, "{\"type\":\"identity\",\"run_id\":\"%s\",\"uid\":%u,\"euid\":%u}\n",
        run, static_cast<unsigned>(getuid()), static_cast<unsigned>(geteuid()));
    const bool nullStart = Step(out, run, 0, "null_start", OH_AudioRenderer_Start(nullptr),
        AUDIOSTREAM_ERROR_INVALID_PARAM);
    const bool nullPause = Step(out, run, 0, "null_pause", OH_AudioRenderer_Pause(nullptr),
        AUDIOSTREAM_ERROR_INVALID_PARAM);
    const bool nullStop = Step(out, run, 0, "null_stop", OH_AudioRenderer_Stop(nullptr),
        AUDIOSTREAM_ERROR_INVALID_PARAM);
    const bool first = Cycle(out, run, 1);
    const bool recreated = Cycle(out, run, 2);
    const bool passed = nullStart && nullPause && nullStop && first && recreated;
    fprintf(out, "{\"type\":\"summary\",\"run_id\":\"%s\",\"cycles\":2,\"passed\":%s}\n",
        run, passed ? "true" : "false");
    fflush(out);
    return passed ? 0 : 1;
}
