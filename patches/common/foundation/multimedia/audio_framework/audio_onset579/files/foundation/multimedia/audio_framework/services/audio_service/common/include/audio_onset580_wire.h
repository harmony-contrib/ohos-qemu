/* SPDX-License-Identifier: Apache-2.0 */
#ifndef OHOS_AUDIO_ONSET580_WIRE_H
#define OHOS_AUDIO_ONSET580_WIRE_H
#include <stdint.h>
#include <stddef.h>
#define O580_MAGIC UINT32_C(0x4f353830)
#define O580_VERSION 1U
#define O580_ARM 1U
#define O580_DISARM 2U
struct o580_request {
    uint32_t magic, version, op, pid;
    uint64_t birth;
    char run[32];
};
struct o580_ack {
    uint32_t magic, version, error, state, pid, reserved;
    uint64_t birth, produced, drained, lost;
};
#if defined(__cplusplus)
static_assert(sizeof(o580_request)==56 && sizeof(o580_ack)==56 && offsetof(o580_request,run)==24 && offsetof(o580_ack,birth)==24,"actual580 wire ABI");
#else
_Static_assert(sizeof(struct o580_request)==56 && sizeof(struct o580_ack)==56 && offsetof(struct o580_request,run)==24 && offsetof(struct o580_ack,birth)==24,"actual580 wire ABI");
#endif
#endif
