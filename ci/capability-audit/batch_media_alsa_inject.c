/* Copyright (c) 2026. Licensed under the Apache License, Version 2.0.
 * Real guest ALSA playback producer for the QemuCapture loopback capture cable.
 * This is a root diagnostic, not an AudioCapturer implementation or acceptance oracle.
 */
#define _GNU_SOURCE 1
#if defined(__APPLE__)
#define _DARWIN_C_SOURCE 1
#endif
#define _POSIX_C_SOURCE 200809L
#include <alsa/asoundlib.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define INPUT_LIMIT (16U * 1024U * 1024U)
#define CABLE_PLAYBACK "hw:CARD=QemuCapture,DEV=1,SUBDEV=0"
static volatile sig_atomic_t interrupted;

static void OnSignal(int signalNumber)
{
    (void)signalNumber;
    interrupted = 1;
}

static int64_t NowMs(void)
{
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) {
        return -1;
    }
    return (int64_t)value.tv_sec * 1000 + value.tv_nsec / 1000000;
}

static int ParseUnsigned(const char *text, unsigned int low, unsigned int high, unsigned int *value)
{
    if (text == NULL || text[0] < '0' || text[0] > '9') {
        return -1;
    }
    errno = 0;
    char *end = NULL;
    unsigned long parsed = strtoul(text, &end, 10);
    if (errno != 0 || *end != '\0' || parsed < low || parsed > high) {
        return -1;
    }
    *value = (unsigned int)parsed;
    return 0;
}

static int LoadPcm(const char *path, unsigned int frameBytes, uint8_t **bytes, size_t *length)
{
    int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) {
        perror("open PCM input");
        return -1;
    }
    struct stat info;
    if (fstat(fd, &info) != 0 || !S_ISREG(info.st_mode) || info.st_size <= 0 ||
        info.st_size > INPUT_LIMIT || info.st_size % frameBytes != 0) {
        fprintf(stderr, "PCM must be a regular, nonempty frame-aligned S16LE file <=16MiB\n");
        close(fd);
        return -1;
    }
    size_t size = (size_t)info.st_size;
    uint8_t *data = malloc(size);
    if (data == NULL) {
        close(fd);
        return -1;
    }
    size_t consumed = 0;
    while (consumed < size) {
        ssize_t count = read(fd, data + consumed, size - consumed);
        if (count < 0 && errno == EINTR && !interrupted) {
            continue;
        }
        if (count <= 0 || interrupted) {
            fprintf(stderr, "PCM input read failed or cancelled\n");
            free(data);
            close(fd);
            return -1;
        }
        consumed += (size_t)count;
    }
    if (close(fd) != 0) {
        free(data);
        return -1;
    }
    *bytes = data;
    *length = size;
    return 0;
}

static int WithinDeadline(int64_t deadline)
{
    int64_t now = NowMs();
    return !interrupted && now >= 0 && now < deadline;
}

static int FeedFailure(const char *stage, long alsaResult, uint64_t written, int64_t deadline)
{
    int savedErrno = errno;
    fprintf(stderr, "{\"event\":\"failed\",\"stage\":\"%s\",\"alsa_rc\":%ld,"
        "\"errno_snapshot\":%d,\"written_frames\":%" PRIu64 ",\"monotonic_ms\":%" PRId64 ","
        "\"deadline_ms\":%" PRId64 ",\"interrupted\":%d}\n",
        stage, alsaResult, savedErrno, written, NowMs(), deadline, (int)interrupted);
    return -1;
}

static int DrainStatus(snd_pcm_t *pcm, snd_pcm_status_t *status, int allowSetup,
    uint64_t written, int64_t deadline, snd_pcm_state_t *state)
{
    int result = snd_pcm_status(pcm, status);
    if (result < 0) return FeedFailure("drain_status", result, written, deadline);
    *state = snd_pcm_status_get_state(status);
    if (*state == SND_PCM_STATE_PREPARED || *state == SND_PCM_STATE_RUNNING ||
        *state == SND_PCM_STATE_DRAINING || (allowSetup && *state == SND_PCM_STATE_SETUP)) return 0;
    long error = *state == SND_PCM_STATE_XRUN ? -EPIPE :
        *state == SND_PCM_STATE_SUSPENDED ? -ESTRPIPE :
        *state == SND_PCM_STATE_DISCONNECTED ? -ENODEV : -EIO;
    fprintf(stderr, "ALSA drain unexpected state: %d\n", (int)*state);
    return FeedFailure("drain_state", error, written, deadline);
}

static int CompleteDrain(const snd_pcm_status_t *status, int lastDrainResult,
    uint64_t written, int64_t deadline)
{
    if (!WithinDeadline(deadline)) return FeedFailure("drain_deadline_or_signal", 0, written, deadline);
    snd_pcm_sframes_t delay = snd_pcm_status_get_delay(status);
    if (delay != 0) return FeedFailure("drain_terminal_delay", -EIO, written, deadline);
    fprintf(stderr, "{\"event\":\"drained\",\"alsa_rc\":%d,\"status_rc\":0,\"state\":%d,"
        "\"delay_frames\":%ld,\"written_frames\":%" PRIu64 "}\n",
        lastDrainResult, (int)snd_pcm_status_get_state(status), (long)delay, written);
    return 0;
}

static int FeedCable(snd_pcm_t *pcm, const uint8_t *data, size_t size,
    unsigned int channels, unsigned int repeats, int64_t deadline, uint64_t *written)
{
    size_t frameBytes = channels * sizeof(int16_t);
    snd_pcm_uframes_t totalFrames = size / frameBytes;
    *written = 0;
    for (unsigned int cycle = 0; cycle < repeats; ++cycle) {
        snd_pcm_uframes_t offset = 0;
        while (offset < totalFrames && WithinDeadline(deadline)) {
            snd_pcm_uframes_t frames = totalFrames - offset;
            if (frames > 1024) {
                frames = 1024;
            }
            snd_pcm_sframes_t count = snd_pcm_writei(pcm, data + offset * frameBytes, frames);
            if (count > 0 && (snd_pcm_uframes_t)count <= frames) {
                offset += (snd_pcm_uframes_t)count;
                *written += (uint64_t)count;
                continue;
            }
            if (count == 0 || count == -EAGAIN || count == -EINTR) {
                int ready = snd_pcm_wait(pcm, 100);
                if (ready < 0) {
                    return FeedFailure("write_wait", ready, *written, deadline);
                }
                continue;
            }
            // Never recover and hide lost challenge samples after an xrun or device error.
            fprintf(stderr, "ALSA write failed: %s (%ld)\n", snd_strerror((int)count), (long)count);
            return FeedFailure("write", count, *written, deadline);
        }
        if (offset != totalFrames) {
            fprintf(stderr, "ALSA injection timed out or cancelled\n");
            return FeedFailure("write_deadline_or_signal", 0, *written, deadline);
        }
    }
    snd_pcm_status_t *status;
    snd_pcm_status_alloca(&status);
    int reportedPending = 0;
    unsigned int attempts = 0;
    int drainPending = 0;
    int lastDrainResult = 0;
    while (WithinDeadline(deadline)) {
        snd_pcm_state_t state;
        // Inspect before drain as well: drain itself must not turn an
        // already-stopped or XRUN stream into an apparently successful one.
        if (DrainStatus(pcm, status, attempts != 0, *written, deadline, &state) != 0) return -1;
        if (attempts == 0 && state == SND_PCM_STATE_DRAINING)
            return FeedFailure("drain_initial_state", -EIO, *written, deadline);
        if (drainPending && state != SND_PCM_STATE_DRAINING && state != SND_PCM_STATE_SETUP)
            return FeedFailure("drain_state_transition", -EIO, *written, deadline);
        if (!WithinDeadline(deadline)) break;
        if (state == SND_PCM_STATE_SETUP) {
            if (!drainPending) return FeedFailure("drain_unstarted_setup", lastDrainResult, *written, deadline);
            return CompleteDrain(status, lastDrainResult, *written, deadline);
        }
        ++attempts;
        // pcm_hw drain installs silence SW_PARAMS before issuing its ioctl.
        // Do not repeatedly reinstall those while the kernel is DRAINING:
        // wait for a successful STATUS to report SETUP with no pending frames.
        // This hardware backend skips the common SETUP no-op check, and the
        // kernel's nonblocking DRAIN returns EAGAIN even in SETUP. Repeating
        // DRAIN cannot provide a terminal rc0 here; retain its actual result.
        int ret = drainPending && state == SND_PCM_STATE_DRAINING ? -EAGAIN : snd_pcm_drain(pcm);
        if (!drainPending) lastDrainResult = ret;
        if (ret != 0 && ret != -EAGAIN && ret != -EINTR) {
            fprintf(stderr, "ALSA drain failed: %s\n", snd_strerror(ret));
            return FeedFailure("drain", ret, *written, deadline);
        }
        if (DrainStatus(pcm, status, 1, *written, deadline, &state) != 0) return -1;
        if (state == SND_PCM_STATE_SETUP) {
            if (ret == -EINTR && !drainPending)
                return FeedFailure("drain_interrupt_before_start", ret, *written, deadline);
            if (ret != 0 && !reportedPending) {
                fprintf(stderr, "{\"event\":\"drain_pending\",\"alsa_rc\":%d,\"state\":%d}\n", ret, (int)state);
            }
            return CompleteDrain(status, lastDrainResult, *written, deadline);
        }
        if (ret == 0) return FeedFailure("drain_terminal_state", -EIO, *written, deadline);
        if (ret == -EAGAIN && state != SND_PCM_STATE_DRAINING && state != SND_PCM_STATE_SETUP)
            return FeedFailure("drain_not_started", -EIO, *written, deadline);
        if (state == SND_PCM_STATE_DRAINING) drainPending = 1;
        if (!reportedPending) {
            fprintf(stderr, "{\"event\":\"drain_pending\",\"alsa_rc\":%d,\"state\":%d}\n", ret, (int)state);
            reportedPending = 1;
        }
        // ALSA's hardware poll reports POLLERR when drain reaches SETUP;
        // snd_pcm_wait can therefore return -EIO for a successful terminal
        // transition. Poll status after a bounded pause without repadding the
        // drain. Only a successful SETUP status after this drain can complete.
        int64_t now = NowMs();
        if (now < 0) return FeedFailure("drain_clock", -EIO, *written, deadline);
        int64_t remaining = deadline - now;
        if (remaining <= 0 || interrupted) break;
        struct timespec pause = {.tv_sec = 0, .tv_nsec = remaining < 2 ? remaining * 1000000 : 2000000};
        if (nanosleep(&pause, NULL) != 0 && errno != EINTR)
            return FeedFailure("drain_pause", -errno, *written, deadline);
    }
    return FeedFailure("drain_deadline_or_signal", 0, *written, deadline);
}

int main(int argc, char **argv)
{
    const char *input = NULL;
    unsigned int rate = 48000, channels = 2, repeats = 10, timeoutMs = 30000;
    for (int i = 1; i < argc; i += 2) {
        if (i + 1 == argc) {
            return 2;
        }
        const char *key = argv[i], *value = argv[i + 1];
        if (strcmp(key, "--input") == 0) {
            input = value;
        } else if (strcmp(key, "--rate") == 0) {
            if (ParseUnsigned(value, 8000, 192000, &rate) != 0) return 2;
        } else if (strcmp(key, "--channels") == 0) {
            if (ParseUnsigned(value, 1, 2, &channels) != 0) return 2;
        } else if (strcmp(key, "--repeat") == 0) {
            if (ParseUnsigned(value, 1, 100, &repeats) != 0) return 2;
        } else if (strcmp(key, "--timeout-ms") == 0) {
            if (ParseUnsigned(value, 100, 120000, &timeoutMs) != 0) return 2;
        } else {
            fprintf(stderr, "usage: batch_media_alsa_inject --input FILE [--rate 48000] "
                "[--channels 2] [--repeat 10] [--timeout-ms 30000]\n");
            return 2;
        }
    }
    if (input == NULL) return 2;
    struct sigaction action = {0};
    action.sa_handler = OnSignal;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGTERM, &action, NULL) != 0 || sigaction(SIGINT, &action, NULL) != 0) return 1;
    uint8_t *data = NULL;
    size_t length = 0;
    if (LoadPcm(input, channels * sizeof(int16_t), &data, &length) != 0) return 1;
    int64_t begin = NowMs();
    if (begin < 0) { free(data); return 1; }
    snd_pcm_t *pcm = NULL;
    int ret = snd_pcm_open(&pcm, CABLE_PLAYBACK, SND_PCM_STREAM_PLAYBACK, SND_PCM_NONBLOCK);
    if (ret < 0) { fprintf(stderr, "ALSA open: %s\n", snd_strerror(ret)); free(data); return 1; }
    ret = snd_pcm_set_params(pcm, SND_PCM_FORMAT_S16_LE, SND_PCM_ACCESS_RW_INTERLEAVED,
        channels, rate, 0, 100000);
    if (ret < 0) { fprintf(stderr, "ALSA parameters: %s\n", snd_strerror(ret)); snd_pcm_close(pcm); free(data); return 1; }
    snd_pcm_hw_params_t *params;
    snd_pcm_hw_params_alloca(&params);
    unsigned int actualRate = 0, actualChannels = 0;
    snd_pcm_format_t actualFormat = SND_PCM_FORMAT_UNKNOWN;
    int direction = 0;
    if (snd_pcm_hw_params_current(pcm, params) < 0 || snd_pcm_hw_params_get_rate(params, &actualRate, &direction) < 0 ||
        snd_pcm_hw_params_get_channels(params, &actualChannels) < 0 ||
        snd_pcm_hw_params_get_format(params, &actualFormat) < 0 || actualRate != rate || direction != 0 ||
        actualChannels != channels || actualFormat != SND_PCM_FORMAT_S16_LE) {
        fprintf(stderr, "ALSA did not negotiate exact requested raw PCM format\n");
        snd_pcm_close(pcm); free(data); return 1;
    }
    fprintf(stderr, "{\"event\":\"feeding\",\"device\":\"%s\",\"rate\":%u,\"channels\":%u,\"bytes\":%zu}\n",
        CABLE_PLAYBACK, rate, channels, length);
    uint64_t frames = 0;
    int result = FeedCable(pcm, data, length, channels, repeats, begin + timeoutMs, &frames);
    if (result != 0) snd_pcm_drop(pcm);
    ret = snd_pcm_close(pcm);
    if (ret < 0) result = FeedFailure("close", ret, frames, begin + timeoutMs);
    free(data);
    if (result != 0) return 1;
    printf("{\"event\":\"played\",\"frames\":%" PRIu64 ",\"rate\":%u,\"channels\":%u,\"repeats\":%u,\"source_bytes\":%zu}\n",
        frames, rate, channels, repeats, length);
    return 0;
}
