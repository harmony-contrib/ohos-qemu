/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Local native protocol v398. NOT the old377 synchronous-query journal.
 * Root must compile/verify these exact native layouts on the actual target. */
#ifndef MEDIA398_WIRE_H
#define MEDIA398_WIRE_H
#include <stdint.h>
#define M398_MAGIC UINT32_C(0x4d333938)
#define M398_HELLO 0U
#define M398_ARM 1U
#define M398_DISARM 2U
#define M398_HW_MAX 4U
#define M398_RUN_MAX 64U
#define M398_RING 64U
#define M398_PCM_BYTES 65536U
#define M398_TAP_MAX UINT64_C(16777216)
#define M398_ROWS_MAX UINT64_C(6000)
struct m398_request {
    uint64_t epoch, instance, holder_ticks;
    uint32_t magic, op, holder_pid, reserved;
    char boot[40], run[32];
};
struct m398_ack {
    uint64_t epoch, instance, holder_ticks, rows, tap_bytes;
    int32_t error, hw_fd, holder_pid;
    uint32_t magic, state, failed;
};
_Static_assert(sizeof(struct m398_request) == 112, "actual target request layout must be112");
_Static_assert(sizeof(struct m398_ack) == 64, "actual target ACK layout must be64");
#endif
