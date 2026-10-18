/* Copyright (c) 2026. Licensed under the Apache License, Version 2.0.
 * Measurement-only digital-zero stream on the independent ES1370 DAC1.
 * No AudioFramework API/focus, source challenge, or synthetic WAV samples.
 */
#include <alsa/asoundlib.h>
#include <array>
#include <cerrno>
#include <cinttypes>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <time.h>
#include <unistd.h>

namespace {
constexpr const char *DEVICE = "hw:CARD=AudioPCI,DEV=1,SUBDEV=0";
volatile sig_atomic_t stopped = 0;
void Stop(int signal) { if (signal == SIGTERM) stopped = 1; }
int64_t NowMs()
{
    timespec value {};
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) return -1;
    return static_cast<int64_t>(value.tv_sec) * 1000 + value.tv_nsec / 1000000;
}
int Failure(const char *stage, long code)
{
    std::fprintf(stderr, "{\"event\":\"clock_failed\",\"stage\":\"%s\",\"alsa_rc\":%ld}\n", stage, code);
    return 1;
}
}

int main(int argc, char **argv)
{
    if (argc != 3 || std::strcmp(argv[1], "--seconds") != 0 || argv[2][0] < '1' || argv[2][0] > '9') return 2;
    errno = 0; char *end = nullptr;
    unsigned long seconds = std::strtoul(argv[2], &end, 10);
    if (errno || *end != '\0' || seconds < 1 || seconds > 180) return 2;
    struct sigaction action {};
    action.sa_handler = Stop; sigemptyset(&action.sa_mask);
    if (sigaction(SIGTERM, &action, nullptr) != 0) return Failure("signal", -errno);
    int64_t began = NowMs();
    if (began < 0) return Failure("clock", -errno);
    snd_pcm_t *pcm = nullptr;
    int code = snd_pcm_open(&pcm, DEVICE, SND_PCM_STREAM_PLAYBACK, SND_PCM_NONBLOCK);
    if (code < 0) return Failure("open", code);
    int result = 0;
    code = snd_pcm_set_params(pcm, SND_PCM_FORMAT_S16_LE, SND_PCM_ACCESS_RW_INTERLEAVED, 2, 44100, 0, 100000);
    if (code < 0) result = Failure("params", code);
    snd_pcm_hw_params_t *params;
    snd_pcm_hw_params_alloca(&params);
    unsigned int rate = 0, channels = 0;
    snd_pcm_format_t format = SND_PCM_FORMAT_UNKNOWN; int direction = 0;
    if (!result && (snd_pcm_hw_params_current(pcm, params) < 0 ||
        snd_pcm_hw_params_get_rate(params, &rate, &direction) < 0 ||
        snd_pcm_hw_params_get_channels(params, &channels) < 0 ||
        snd_pcm_hw_params_get_format(params, &format) < 0 || rate != 44100 || direction != 0 ||
        channels != 2 || format != SND_PCM_FORMAT_S16_LE)) result = Failure("exact_format", -EIO);
    std::array<int16_t, 2048> zero {};
    uint64_t written = 0; bool ready = false; bool elapsed = false;
    while (!result && !stopped) {
        int64_t now = NowMs();
        if (now < 0) { result = Failure("clock", -errno); break; }
        if (now - began >= static_cast<int64_t>(seconds) * 1000) { elapsed = true; break; }
        snd_pcm_sframes_t frames = snd_pcm_writei(pcm, zero.data(), zero.size() / 2);
        if (frames > 0 && frames <= static_cast<snd_pcm_sframes_t>(zero.size() / 2)) {
            written += static_cast<uint64_t>(frames);
            if (!ready && written >= 8192) {
                // std::__h::string is part of the actual product C++ ABI proof.
                std::string identity = std::to_string(getpid()) + ",\"uid\":" + std::to_string(getuid());
                std::fprintf(stderr, "{\"event\":\"clock_ready\",\"pid\":%s,\"device\":\"%s\",\"rate\":44100,\"channels\":2}\n",
                    identity.c_str(), DEVICE);
                ready = true;
            }
            continue;
        }
        if (stopped && frames == -EINTR) break;
        if (frames == 0 || frames == -EAGAIN || frames == -EINTR) {
            code = snd_pcm_wait(pcm, 100);
            if (code < 0 && !(code == -EINTR && stopped)) result = Failure("write_wait", code);
            continue;
        }
        result = Failure("write", frames);
    }
    int dropped = snd_pcm_drop(pcm);
    if (dropped < 0) result = Failure("drop", dropped);
    int closed = snd_pcm_close(pcm);
    if (closed < 0) result = Failure("close", closed);
    if (!ready) result = Failure("never_ready", -EIO);
    if (!result) {
        std::fprintf(stderr, "{\"event\":\"clock_end\",\"reason\":\"%s\",\"written_frames\":%" PRIu64
            ",\"drop_rc\":%d,\"close_rc\":%d}\n", stopped ? "owned_sigterm" : elapsed ? "time_bound" : "invalid", written, dropped, closed);
    }
    return result;
}
