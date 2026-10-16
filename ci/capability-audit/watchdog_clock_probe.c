/* Copyright (c) 2026 HarmonyContrib. Licensed under the Apache License, Version 2.0. */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>

#ifndef CLOCK_BOOTTIME
#error "The actual CLOCK_BOOTTIME clock is required; no fallback is permitted"
#endif

static int ValidNonce(const char *nonce)
{
    for (unsigned int i = 0; i < 32; ++i) {
        if (!((nonce[i] >= '0' && nonce[i] <= '9') || (nonce[i] >= 'a' && nonce[i] <= 'f'))) {
            return 0;
        }
    }
    return nonce[32] == '\0';
}

static int Nanoseconds(const struct timespec *value, uint64_t *result)
{
    if (value->tv_sec < 0 || value->tv_nsec < 0 || value->tv_nsec >= 1000000000L) {
        return -1;
    }
    uint64_t seconds = (uint64_t)value->tv_sec;
    uint64_t nanos = (uint64_t)value->tv_nsec;
    if (seconds > (UINT64_MAX - nanos) / UINT64_C(1000000000)) {
        return -1;
    }
    *result = seconds * UINT64_C(1000000000) + nanos;
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 2 || !ValidNonce(argv[1])) {
        fputs("usage: watchdog_clock_probe 32-lowercase-hex-nonce\n", stderr);
        return 2;
    }
    struct timespec before;
    struct timespec boottime;
    struct timespec after;
    /* Sequenced short-circuit evaluation: no fallback or extra clock sample. */
    if (clock_gettime(CLOCK_MONOTONIC, &before) != 0 ||
        clock_gettime(CLOCK_BOOTTIME, &boottime) != 0 ||
        clock_gettime(CLOCK_MONOTONIC, &after) != 0) {
        perror("clock_gettime");
        return 1;
    }
    uint64_t beforeNs;
    uint64_t boottimeNs;
    uint64_t afterNs;
    if (Nanoseconds(&before, &beforeNs) != 0 || Nanoseconds(&boottime, &boottimeNs) != 0 ||
        Nanoseconds(&after, &afterNs) != 0 || beforeNs > afterNs) {
        fputs("invalid or overflowing actual clock sample\n", stderr);
        return 1;
    }
    if (printf("{\"schema_version\":1,\"nonce\":\"%s\",\"monotonic_before_ns\":%" PRIu64
        ",\"boottime_ns\":%" PRIu64 ",\"monotonic_after_ns\":%" PRIu64 "}\n",
        argv[1], beforeNs, boottimeNs, afterNs) < 0 || fflush(stdout) == EOF) {
        return 1;
    }
    return 0;
}
