// Copyright 2026. Apache-2.0. OpenAL remains under its original LGPL license.
// Normal AudioEffect ABI plugin; every output sample comes from real input PCM.
#include "audio_effect.h"
#ifdef SENSOR_ENABLE
#include "sensor_agent.h"
#endif
#include <AL/al.h>
#include <AL/alc.h>
#include <AL/alext.h>
#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <mutex>
#include <new>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <vector>
using namespace OHOS::AudioStandard;
namespace {
std::atomic<uint64_t> nextId{0};
std::mutex contextMutex;
constexpr const char *TRACE_DIR = "/data/data/hvs/qemu_spatial";
constexpr uint64_t TRACE_LIMIT = 64 * 1024 * 1024;
bool WriteAll(int fd, const void *data, size_t size)
{
    auto *p = static_cast<const uint8_t *>(data);
    while (size) {
        ssize_t n = write(fd, p, size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return false;
        p += n; size -= static_cast<size_t>(n);
    }
    return true;
}
struct Spatial {
    AudioEffectInterface *api;
    AudioEffectConfig cfg{};
    ALCdevice *device = nullptr;
    ALCcontext *context = nullptr;
    ALuint source[2]{};
    uint64_t id = ++nextId, frames = 0, traceBytes = 0, seq = 0;
    bool enabled = false, spatial = false;
    float yaw = 0, pitch = 0, qw = 1, qx = 0, qy = 0, qz = 0;
    uint32_t order = 0;
    std::string traceRun;
    void EnsureTrace();
    int input = -1, output = -1, journal = -1;
    Spatial();
    ~Spatial();
    void Log(const char *event, int result);
    int Configure(const AudioEffectConfig &config);
    void Close();
    int Process(AudioBuffer *in, AudioBuffer *out);
    int Command(uint32_t code, AudioEffectTransInfo *cmd, AudioEffectTransInfo *reply);
};
Spatial *Self(AudioEffectHandle h) { return reinterpret_cast<Spatial *>(h); }
int32_t Process(AudioEffectHandle h, AudioBuffer *in, AudioBuffer *out)
{
    if (!h) return -EINVAL;
    std::lock_guard<std::mutex> lock(contextMutex);
    return Self(h)->Process(in, out);
}
int32_t Command(AudioEffectHandle h, uint32_t code, AudioEffectTransInfo *cmd, AudioEffectTransInfo *reply)
{
    if (!h) return -EINVAL;
    std::lock_guard<std::mutex> lock(contextMutex);
    return Self(h)->Command(code, cmd, reply);
}
AudioEffectInterface interface = {Process, Command, nullptr, nullptr};
Spatial::Spatial() : api(&interface) { EnsureTrace(); Log("created", 0); }
void Spatial::EnsureTrace()
{
    char raw[34]{}; struct stat metadata{};
    int control = open("/data/data/hvs/qemu_spatial/control", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    bool allowed = control >= 0 && fstat(control, &metadata) == 0 && S_ISREG(metadata.st_mode) &&
        metadata.st_uid == 0 && metadata.st_nlink == 1 && metadata.st_size == 33 && read(control, raw, sizeof(raw)) == 33 && raw[32] == '\n';
    if (control >= 0) close(control);
    for (int i = 0; i < 32 && allowed; ++i) allowed = (raw[i] >= '0' && raw[i] <= '9') || (raw[i] >= 'a' && raw[i] <= 'f');
    std::string next = allowed ? std::string(raw, 32) : "";
    if (next == traceRun) return;
    for (int *fd : {&input, &output, &journal}) { if (*fd >= 0) close(*fd); *fd = -1; }
    traceRun = next; if (next.empty()) return;
    // Root-only diagnostic opt-in affects observation only, never the algorithm.
    id = ++nextId; frames = traceBytes = seq = 0;
    char path[256]; const char *suffix[] = {"in.f32", "out.f32", "events.jsonl"};
    int *fds[] = {&input, &output, &journal};
    for (int i = 0; i < 3; ++i) {
        std::snprintf(path, sizeof(path), "%s/%s-%d-%llu-%s", TRACE_DIR, traceRun.c_str(), getpid(), static_cast<unsigned long long>(id), suffix[i]);
        *fds[i] = open(path, O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC | O_NOFOLLOW, 0600);
    }
    Log("actual-diagnostic-generation", 0);
}
void Spatial::Log(const char *event, int result)
{
    timespec now{}; clock_gettime(CLOCK_BOOTTIME, &now);
    char text[768];
    int n = std::snprintf(text, sizeof(text), "{\"schema\":\"qemu-cpu-spatial/v1\",\"pid\":%d,\"uid\":%d,\"generation\":%llu,\"seq\":%llu,\"frames\":%llu,\"monotonicNs\":%llu,\"event\":\"%s\",\"result\":%d,\"enabled\":%s,\"spatial\":%s,\"order\":%u,\"w\":%.9g,\"x\":%.9g,\"y\":%.9g,\"z\":%.9g,\"yaw\":%.9g,\"pitch\":%.9g,\"rate\":%u,\"inputChannels\":%u,\"outputChannels\":%u}\n", getpid(), static_cast<int>(geteuid()), static_cast<unsigned long long>(id), static_cast<unsigned long long>(++seq), static_cast<unsigned long long>(frames), static_cast<unsigned long long>(now.tv_sec)*1000000000ULL+now.tv_nsec, event, result, enabled?"true":"false", spatial?"true":"false", order, qw, qx, qy, qz, yaw, pitch, cfg.inputCfg.samplingRate, cfg.inputCfg.channels, cfg.outputCfg.channels);
    if (journal >= 0 && n > 0 && static_cast<size_t>(n) < sizeof(text)) WriteAll(journal, text, static_cast<size_t>(n));
}
void Spatial::Close()
{
    if (context) {
        alcMakeContextCurrent(context);
        if (source[0]) alDeleteSources(2, source);
        source[0] = source[1] = 0;
        alcMakeContextCurrent(nullptr); alcDestroyContext(context); context = nullptr;
    }
    if (device) { alcCloseDevice(device); device = nullptr; }
}
Spatial::~Spatial()
{
    Close(); Log("released", 0);
    for (int fd : {input, output, journal}) if (fd >= 0) close(fd);
}
int Spatial::Configure(const AudioEffectConfig &config)
{
    if (config.inputCfg.channels < 1 || config.inputCfg.channels > 2 || config.outputCfg.channels != 2 ||
        config.inputCfg.format != DATA_FORMAT_F32 || config.outputCfg.format != DATA_FORMAT_F32 ||
        config.inputCfg.samplingRate != config.outputCfg.samplingRate ||
        (config.inputCfg.samplingRate != 48000 && config.inputCfg.samplingRate != 44100)) return -ENOTSUP;
    Close(); cfg = config;
    device = alcLoopbackOpenDeviceSOFT(nullptr);
    if (!device || !alcIsExtensionPresent(device, "ALC_SOFT_HRTF")) { Close(); return -ENODEV; }
    const ALCint attributes[] = {ALC_FORMAT_CHANNELS_SOFT, ALC_STEREO_SOFT, ALC_FORMAT_TYPE_SOFT, ALC_FLOAT_SOFT,
        ALC_FREQUENCY, static_cast<ALCint>(cfg.inputCfg.samplingRate), ALC_HRTF_SOFT, ALC_TRUE, 0};
    context = alcCreateContext(device, attributes);
    if (!context || !alcMakeContextCurrent(context)) { Close(); return -ENODEV; }
    ALCint status = 0; alcGetIntegerv(device, ALC_HRTF_STATUS_SOFT, 1, &status);
    if (status != ALC_HRTF_ENABLED_SOFT && status != ALC_HRTF_HEADPHONES_DETECTED_SOFT && status != ALC_HRTF_REQUIRED_SOFT) { Close(); return -ENODEV; }
    alGenSources(2, source);
    for (int i = 0; i < 2; ++i) {
        alSourcei(source[i], AL_SOURCE_RELATIVE, AL_FALSE); alSourcef(source[i], AL_ROLLOFF_FACTOR, 0);
        alSource3f(source[i], AL_POSITION, i ? 0.7F : -0.7F, 0, -1);
        alSourcef(source[i], AL_GAIN, config.inputCfg.channels == 1 ? 0.5F : 1.0F);
    }
    int result = alGetError() == AL_NO_ERROR ? 0 : -EIO; Log("actual-loopback-hrtf-configured", result); return result;
}
int Spatial::Process(AudioBuffer *in, AudioBuffer *out)
{
    EnsureTrace();
    if (!in || !out || !in->f32 || !out->f32 || in->frameLength == 0 || in->frameLength > 8192 ||
        out->frameLength != in->frameLength || !context) return -EINVAL;
    size_t count = in->frameLength;
    for (size_t i = 0; i < count * cfg.inputCfg.channels; ++i) if (!std::isfinite(in->f32[i])) return -EINVAL;
    if (!enabled || !spatial) {
        for (size_t i = 0; i < count; ++i) for (size_t ch = 0; ch < 2; ++ch) out->f32[2*i+ch] = in->f32[cfg.inputCfg.channels*i+std::min(ch, static_cast<size_t>(cfg.inputCfg.channels-1))];
    } else {
        alcMakeContextCurrent(context);
        const float direction[] = {-std::sin(yaw)*std::cos(pitch), std::sin(pitch), -std::cos(yaw)*std::cos(pitch), 0, 1, 0};
        alListenerfv(AL_ORIENTATION, direction);
        std::vector<float> mono(count);
        for (int ch = 0; ch < 2; ++ch) {
            ALint processed = 0; alGetSourcei(source[ch], AL_BUFFERS_PROCESSED, &processed);
            while (processed-- > 0) { ALuint old = 0; alSourceUnqueueBuffers(source[ch], 1, &old); alDeleteBuffers(1, &old); }
            ALint queued = 0; alGetSourcei(source[ch], AL_BUFFERS_QUEUED, &queued); if (queued > 8) return -EOVERFLOW;
            for (size_t i = 0; i < count; ++i) mono[i] = in->f32[cfg.inputCfg.channels*i+std::min(static_cast<size_t>(ch), static_cast<size_t>(cfg.inputCfg.channels-1))];
            ALuint buffer = 0; alGenBuffers(1, &buffer);
            alBufferData(buffer, AL_FORMAT_MONO_FLOAT32, mono.data(), static_cast<ALsizei>(count*sizeof(float)), static_cast<ALsizei>(cfg.inputCfg.samplingRate));
            alSourceQueueBuffers(source[ch], 1, &buffer);
            ALint state = 0; alGetSourcei(source[ch], AL_SOURCE_STATE, &state); if (state != AL_PLAYING) alSourcePlay(source[ch]);
        }
        alcRenderSamplesSOFT(device, out->f32, static_cast<ALCsizei>(count));
        if (alGetError() != AL_NO_ERROR || alcGetError(device) != ALC_NO_ERROR) { Log("actual-render-error", -EIO); return -EIO; }
    }
    size_t inSize = count*cfg.inputCfg.channels*sizeof(float), outSize = count*2*sizeof(float);
    if (!traceRun.empty() && (input < 0 || output < 0 || traceBytes + inSize + outSize > TRACE_LIMIT ||
        !WriteAll(input, in->f32, inSize) || !WriteAll(output, out->f32, outSize))) Log("trace-incomplete", -EIO);
    else traceBytes += inSize + outSize;
    frames += count; Log("actual-input-output-PCM", 0); return 0;
}
int Spatial::Command(uint32_t code, AudioEffectTransInfo *cmd, AudioEffectTransInfo *reply)
{
    EnsureTrace();
    int status = 0;
    switch (code) {
        case EFFECT_CMD_INIT: break;
        case EFFECT_CMD_SET_CONFIG:
            if (!cmd || !cmd->data || cmd->size != sizeof(AudioEffectConfig)) return -EINVAL;
            status = Configure(*static_cast<AudioEffectConfig *>(cmd->data)); break;
        case EFFECT_CMD_GET_CONFIG:
            if (!reply || !reply->data || reply->size < sizeof(cfg)) return -EINVAL;
            std::memcpy(reply->data, &cfg, sizeof(cfg)); return 0;
        case EFFECT_CMD_ENABLE: enabled = true; break;
        case EFFECT_CMD_DISABLE: enabled = false; break;
        case EFFECT_CMD_SET_PARAM: {
            if (!cmd || !cmd->data || cmd->size < sizeof(AudioEffectParam)+sizeof(int32_t)*MAX_PARAM_INDEX) return -EINVAL;
            const auto *p = static_cast<AudioEffectParam *>(cmd->data);
            if (p->data[COMMAND_CODE_INDEX] != EFFECT_SET_PARAM) return -ENOTSUP;
            spatial = p->data[SPATIALIZATION_ENABLED_INDEX] != 0;
            yaw = static_cast<float>(p->data[ROTATION_INDEX])*3.14159265358979323846F/180.0F;
            Log("actual-spatial-parameter", 0); break;
        }
        case EFFECT_CMD_SET_IMU: {
#ifdef SENSOR_ENABLE
            if (!cmd || !cmd->data || cmd->size != sizeof(HeadPostureData)) return -EINVAL;
            const auto &p = *static_cast<HeadPostureData *>(cmd->data);
            double norm = p.w*p.w+p.x*p.x+p.y*p.y+p.z*p.z;
            if (!std::isfinite(norm) || std::abs(norm-1.0) > 0.05) return -EINVAL;
            order = p.order; qw = p.w; qx = p.x; qy = p.y; qz = p.z;
            yaw = static_cast<float>(std::atan2(2*(p.w*p.y+p.x*p.z),1-2*(p.y*p.y+p.z*p.z)));
            pitch = static_cast<float>(std::asin(std::clamp(static_cast<double>(2*(p.w*p.x-p.z*p.y)),-1.0,1.0)));
            Log("actual-framework-head-posture", 0); break;
#else
            return -ENOTSUP;
#endif
        }
        case EFFECT_CMD_FLUSH:
        case EFFECT_CMD_STOP_STREAM:
            if (context) status = Configure(cfg);
            break;
        case EFFECT_CMD_SET_PROPERTY: return -ENOTSUP;
        default: return -ENOTSUP;
    }
    if (reply && reply->data && reply->size >= sizeof(int32_t)) *static_cast<int32_t *>(reply->data) = status;
    Log("actual-command", status); return status;
}
bool Check(const AudioEffectDescriptor d) { return d.libraryName == "QemuSpatial" && d.effectName == "qemu_hrtf"; }
int32_t Create(const AudioEffectDescriptor d, AudioEffectHandle *h)
{
    if (!h || !Check(d)) return -EINVAL;
    auto *s = new(std::nothrow) Spatial(); if (!s) return -ENOMEM;
    *h = reinterpret_cast<AudioEffectHandle>(s); return 0;
}
int32_t Release(AudioEffectHandle h)
{
    if (!h) return -EINVAL;
    std::lock_guard<std::mutex> lock(contextMutex); delete Self(h); return 0;
}
void Support(AlgoSupportConfig *c)
{
    if (!c) return;
    c->isSupport = c->inChannels > 0 && c->inChannels <= 2 && c->inFormat == DATA_FORMAT_F32 &&
        (c->inSampleRate == 48000 || c->inSampleRate == 44100);
    c->isRealTime = true; c->outChannels = 2; c->outFormat = DATA_FORMAT_F32; c->outSampleRate = c->inSampleRate;
}
}
extern "C" {
__attribute__((visibility("default"))) AudioEffectLibrary AELI = {1, "QemuSpatial", "OpenAL Soft 1.24.3 CPU loopback HRTF", Check, Create, Release, Support};
}
