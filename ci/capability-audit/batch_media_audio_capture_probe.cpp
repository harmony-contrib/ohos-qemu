// SPDX-License-Identifier: Apache-2.0
// Ordinary application public OHAudio capture only. No input file/backend/oracle access.
#include <ohaudio/native_audiocapturer.h>
#include <ohaudio/native_audiostreambuilder.h>
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <memory>
#include <mutex>
#include <string>
#include <time.h>
#include <unistd.h>
#include <vector>

namespace {
constexpr int32_t RATE = 48000;
constexpr int32_t CHANNELS = 2;
constexpr size_t FRAME_BYTES = 4;
constexpr size_t CAPACITY = RATE * FRAME_BYTES * 8;
constexpr size_t MAX_CHUNKS = 2048;
struct Chunk {size_t offset; int32_t length; int32_t phase; int64_t monotonicNs;};
struct Capture {
    std::mutex mutex;
    std::vector<uint8_t> bytes = std::vector<uint8_t>(CAPACITY);
    std::vector<Chunk> chunks;
    size_t size = 0;
    int32_t phase = 0;
    uint32_t invalid = 0;
    uint32_t unexpected = 0;
    std::atomic<int32_t> error{0};
    Capture() { chunks.reserve(MAX_CHUNKS); }
};
int64_t Now()
{
    timespec time{};
    if (clock_gettime(CLOCK_MONOTONIC, &time) != 0) return -1;
    return static_cast<int64_t>(time.tv_sec) * 1000000000 + time.tv_nsec;
}
void Read(OH_AudioCapturer *, void *user, void *audioData, int32_t length)
{
    auto &capture = *static_cast<Capture *>(user);
    std::lock_guard<std::mutex> lock(capture.mutex);
    const int64_t now = Now();
    if (audioData == nullptr || length <= 0 || length % FRAME_BYTES != 0 || now < 0 ||
        static_cast<size_t>(length) > capture.bytes.size() - capture.size || capture.chunks.size() >= MAX_CHUNKS) {
        ++capture.invalid;
        return;
    }
    if (capture.phase != 1 && capture.phase != 2) ++capture.unexpected;
    std::memcpy(capture.bytes.data() + capture.size, audioData, static_cast<size_t>(length));
    capture.chunks.push_back({capture.size, length, capture.phase, now});
    capture.size += static_cast<size_t>(length);
}
void Error(OH_AudioCapturer *, void *user, OH_AudioStream_Result error)
{
    static_cast<Capture *>(user)->error.store(error);
}
bool Step(FILE *out, const char *run, int cycle, const char *name, int actual, int expected)
{
    fprintf(out, "{\"type\":\"step\",\"run_id\":\"%s\",\"cycle\":%d,\"name\":\"%s\","
        "\"actual\":%d,\"expected\":%d,\"monotonic_ns\":%lld}\n", run, cycle, name, actual, expected,
        static_cast<long long>(Now()));
    fflush(out);
    return actual == expected;
}
bool State(FILE *out, const char *run, int cycle, OH_AudioCapturer *capturer,
    const char *name, OH_AudioStream_State expected)
{
    OH_AudioStream_State state = AUDIOSTREAM_STATE_INVALID;
    const auto result = OH_AudioCapturer_GetCurrentState(capturer, &state);
    bool valid = Step(out, run, cycle, name, result, AUDIOSTREAM_SUCCESS);
    return Step(out, run, cycle, (std::string(name) + ".value").c_str(), state, expected) && valid;
}
void Phase(Capture &capture, int32_t phase)
{
    std::lock_guard<std::mutex> lock(capture.mutex);
    capture.phase = phase;
}
bool Snapshot(FILE *out, const char *run, int cycle, OH_AudioCapturer *capturer, Capture &capture, int phase)
{
    const int64_t before = Now();
    int64_t position = -1, timestamp = -1, frames = -1;
    const auto stampResult = OH_AudioCapturer_GetTimestamp(capturer, CLOCK_MONOTONIC, &position, &timestamp);
    const auto frameResult = OH_AudioCapturer_GetFramesRead(capturer, &frames);
    const int64_t after = Now();
    std::lock_guard<std::mutex> lock(capture.mutex);
    fprintf(out, "{\"type\":\"snapshot\",\"run_id\":\"%s\",\"cycle\":%d,\"phase\":%d,"
        "\"timestamp_result\":%d,\"frames_result\":%d,\"position\":%lld,\"timestamp_ns\":%lld,"
        "\"frames_read\":%lld,\"copied_bytes\":%zu,\"before_ns\":%lld,\"after_ns\":%lld}\n",
        run, cycle, phase, stampResult, frameResult, static_cast<long long>(position),
        static_cast<long long>(timestamp), static_cast<long long>(frames), capture.size,
        static_cast<long long>(before), static_cast<long long>(after));
    fflush(out);
    return stampResult == AUDIOSTREAM_SUCCESS && frameResult == AUDIOSTREAM_SUCCESS && position >= 0 &&
        timestamp > 0 && frames >= 0 && before > 0 && after >= before && capture.error.load() == 0;
}
bool Collect(FILE *out, const char *run, int cycle, OH_AudioCapturer *capturer, Capture &capture, int phase)
{
    bool valid = true;
    for (int point = 0; point < 3; ++point) {
        for (int tick = 0; tick < 20; ++tick) usleep(20000);
        valid &= Snapshot(out, run, cycle, capturer, capture, phase);
    }
    return valid;
}
bool Quiet(FILE *out, const char *run, int cycle, Capture &capture, const char *name)
{
    size_t before;
    { std::lock_guard<std::mutex> lock(capture.mutex); before = capture.size; }
    usleep(200000);
    std::lock_guard<std::mutex> lock(capture.mutex);
    fprintf(out, "{\"type\":\"quiet\",\"run_id\":\"%s\",\"cycle\":%d,\"name\":\"%s\","
        "\"before_bytes\":%zu,\"after_bytes\":%zu,\"unexpected\":%u}\n",
        run, cycle, name, before, capture.size, capture.unexpected);
    fflush(out);
    return before == capture.size && capture.unexpected == 0;
}
bool Persist(FILE *out, const char *run, int cycle, Capture &capture)
{
    std::lock_guard<std::mutex> lock(capture.mutex);
    const std::string basename = "audio-capture-" + std::string(run) + "-cycle" + std::to_string(cycle) + ".pcm";
    const std::string path = "/data/storage/el2/base/files/" + basename;
    int fd = open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    bool valid = fd >= 0;
    size_t written = 0;
    while (valid && written < capture.size) {
        ssize_t count = write(fd, capture.bytes.data() + written, capture.size - written);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) { valid = false; break; }
        written += static_cast<size_t>(count);
    }
    if (fd >= 0) {
        if (fsync(fd) != 0) valid = false;
        if (close(fd) != 0) valid = false;
    }
    for (const auto &chunk : capture.chunks) {
        fprintf(out, "{\"type\":\"chunk\",\"run_id\":\"%s\",\"cycle\":%d,\"offset\":%zu,"
            "\"bytes\":%d,\"phase\":%d,\"monotonic_ns\":%lld}\n", run, cycle, chunk.offset,
            chunk.length, chunk.phase, static_cast<long long>(chunk.monotonicNs));
    }
    fprintf(out, "{\"type\":\"pcm_file\",\"run_id\":\"%s\",\"cycle\":%d,\"basename\":\"%s\","
        "\"bytes\":%zu,\"written_bytes\":%zu,\"invalid_buffers\":%u,\"unexpected_buffers\":%u,"
        "\"callback_error\":%d,\"persisted\":%s}\n", run, cycle, basename.c_str(), capture.size, written,
        capture.invalid, capture.unexpected, capture.error.load(), valid ? "true" : "false");
    fflush(out);
    return valid && capture.invalid == 0 && capture.unexpected == 0 && capture.error.load() == 0;
}
bool Cycle(FILE *out, const char *run, int cycle, bool denied)
{
    auto capture = std::make_unique<Capture>();
    OH_AudioStreamBuilder *builder = nullptr;
    OH_AudioCapturer *capturer = nullptr;
    bool valid = Step(out, run, cycle, "create", OH_AudioStreamBuilder_Create(&builder, AUDIOSTREAM_TYPE_CAPTURER),
        AUDIOSTREAM_SUCCESS);
    if (builder == nullptr) return false;
    valid &= Step(out, run, cycle, "invalid_channels", OH_AudioStreamBuilder_SetChannelCount(builder, 0), AUDIOSTREAM_ERROR_INVALID_PARAM);
    valid &= Step(out, run, cycle, "rate", OH_AudioStreamBuilder_SetSamplingRate(builder, RATE), AUDIOSTREAM_SUCCESS);
    valid &= Step(out, run, cycle, "channels", OH_AudioStreamBuilder_SetChannelCount(builder, CHANNELS), AUDIOSTREAM_SUCCESS);
    valid &= Step(out, run, cycle, "format", OH_AudioStreamBuilder_SetSampleFormat(builder, AUDIOSTREAM_SAMPLE_S16LE), AUDIOSTREAM_SUCCESS);
    valid &= Step(out, run, cycle, "encoding", OH_AudioStreamBuilder_SetEncodingType(builder, AUDIOSTREAM_ENCODING_TYPE_RAW), AUDIOSTREAM_SUCCESS);
    valid &= Step(out, run, cycle, "latency", OH_AudioStreamBuilder_SetLatencyMode(builder, AUDIOSTREAM_LATENCY_MODE_NORMAL), AUDIOSTREAM_SUCCESS);
    valid &= Step(out, run, cycle, "microphone", OH_AudioStreamBuilder_SetCapturerInfo(builder, AUDIOSTREAM_SOURCE_TYPE_MIC), AUDIOSTREAM_SUCCESS);
    valid &= Step(out, run, cycle, "read_callback", OH_AudioStreamBuilder_SetCapturerReadDataCallback(builder, Read, capture.get()), AUDIOSTREAM_SUCCESS);
    valid &= Step(out, run, cycle, "error_callback", OH_AudioStreamBuilder_SetCapturerErrorCallback(builder, Error, capture.get()), AUDIOSTREAM_SUCCESS);
    const auto generated = OH_AudioStreamBuilder_GenerateCapturer(builder, &capturer);
    if (denied) {
        fprintf(out, "{\"type\":\"denial_generate\",\"run_id\":\"%s\",\"cycle\":%d,\"actual\":%d,\"created\":%s}\n",
            run, cycle, generated, capturer != nullptr ? "true" : "false");
    } else valid &= Step(out, run, cycle, "generate", generated, AUDIOSTREAM_SUCCESS);
    bool rejected = generated != AUDIOSTREAM_SUCCESS && capturer == nullptr;
    if (capturer != nullptr) {
        // Preserve callback state unless the real Release confirms no more callbacks.
        Capture &live = *capture.release();
        int32_t rate = -1, channels = -1;
        OH_AudioStream_SampleFormat format = AUDIOSTREAM_SAMPLE_U8;
        valid &= Step(out, run, cycle, "get_rate", OH_AudioCapturer_GetSamplingRate(capturer, &rate), AUDIOSTREAM_SUCCESS);
        valid &= Step(out, run, cycle, "get_channels", OH_AudioCapturer_GetChannelCount(capturer, &channels), AUDIOSTREAM_SUCCESS);
        valid &= Step(out, run, cycle, "get_format", OH_AudioCapturer_GetSampleFormat(capturer, &format), AUDIOSTREAM_SUCCESS);
        fprintf(out, "{\"type\":\"format\",\"run_id\":\"%s\",\"cycle\":%d,\"rate\":%d,\"channels\":%d,\"sample_format\":%d,\"frame_bytes\":%zu}\n",
            run, cycle, rate, channels, format, FRAME_BYTES);
        valid &= rate == RATE && channels == CHANNELS && format == AUDIOSTREAM_SAMPLE_S16LE;
        valid &= State(out, run, cycle, capturer, "prepared", AUDIOSTREAM_STATE_PREPARED);
        valid &= Step(out, run, cycle, "pause_before_start", OH_AudioCapturer_Pause(capturer), AUDIOSTREAM_ERROR_ILLEGAL_STATE);
        Phase(live, 1);
        const auto started = OH_AudioCapturer_Start(capturer);
        if (denied) {
            fprintf(out, "{\"type\":\"denial_start\",\"run_id\":\"%s\",\"cycle\":%d,\"actual\":%d}\n", run, cycle, started);
            rejected = started != AUDIOSTREAM_SUCCESS;
        } else valid &= Step(out, run, cycle, "start", started, AUDIOSTREAM_SUCCESS);
        if (started == AUDIOSTREAM_SUCCESS) {
            valid &= State(out, run, cycle, capturer, "running", AUDIOSTREAM_STATE_RUNNING);
            valid &= Collect(out, run, cycle, capturer, live, 1);
            const auto paused = OH_AudioCapturer_Pause(capturer);
            valid &= Step(out, run, cycle, "pause", paused, AUDIOSTREAM_SUCCESS);
            if (paused == AUDIOSTREAM_SUCCESS) {
                Phase(live, 0);
                valid &= State(out, run, cycle, capturer, "paused", AUDIOSTREAM_STATE_PAUSED);
                valid &= Quiet(out, run, cycle, live, "paused");
                valid &= Step(out, run, cycle, "flush", OH_AudioCapturer_Flush(capturer), AUDIOSTREAM_SUCCESS);
                Phase(live, 2);
                const auto resumed = OH_AudioCapturer_Start(capturer);
                valid &= Step(out, run, cycle, "resume", resumed, AUDIOSTREAM_SUCCESS);
                if (resumed == AUDIOSTREAM_SUCCESS) {
                    valid &= State(out, run, cycle, capturer, "resumed", AUDIOSTREAM_STATE_RUNNING);
                    valid &= Collect(out, run, cycle, capturer, live, 2);
                }
            }
            valid &= Step(out, run, cycle, "stop", OH_AudioCapturer_Stop(capturer), AUDIOSTREAM_SUCCESS);
            Phase(live, 0);
            valid &= State(out, run, cycle, capturer, "stopped", AUDIOSTREAM_STATE_STOPPED);
            valid &= Quiet(out, run, cycle, live, "stopped");
        } else Phase(live, 0);
        const auto released = OH_AudioCapturer_Release(capturer);
        valid &= Step(out, run, cycle, "release", released, AUDIOSTREAM_SUCCESS);
        if (released == AUDIOSTREAM_SUCCESS) {
            valid &= Quiet(out, run, cycle, live, "released");
            valid &= Persist(out, run, cycle, live);
            if (denied) rejected = rejected && live.size == 0;
            delete &live;
        } else valid = false;
    } else if (!denied) valid = false;
    valid &= Step(out, run, cycle, "destroy", OH_AudioStreamBuilder_Destroy(builder), AUDIOSTREAM_SUCCESS);
    return valid && (denied ? rejected : generated == AUDIOSTREAM_SUCCESS);
}
}
extern "C" int RunBatchMediaAudioCaptureProbe(FILE *out, const char *run, bool denied)
{
    fprintf(out, "{\"type\":\"identity\",\"run_id\":\"%s\",\"uid\":%u,\"euid\":%u,\"mode\":\"%s\"}\n",
        run, static_cast<unsigned>(getuid()), static_cast<unsigned>(geteuid()), denied ? "denied" : "granted");
    const bool first = Cycle(out, run, 1, denied);
    const bool recreated = Cycle(out, run, 2, denied);
    fprintf(out, "{\"type\":\"summary\",\"run_id\":\"%s\",\"cycles\":2,\"candidate_ok\":%s,"
        "\"independent_pcm_verification_required\":true}\n", run, first && recreated ? "true" : "false");
    fflush(out);
    return first && recreated ? 0 : 1;
}
