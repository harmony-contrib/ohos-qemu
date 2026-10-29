/* SPDX-License-Identifier: Apache-2.0 */
#ifndef OHOS_AUDIO_ONSET579_WIRE_H
#define OHOS_AUDIO_ONSET579_WIRE_H
#include <stdint.h>
#define O579_MAGIC UINT32_C(0x4f353739)
#define O579_VERSION 1U
#define O579_ARM 1U
#define O579_DISARM 2U
struct o579_request {
    uint32_t magic, version, op, pid;
    uint64_t birth;
    char run[32];
};
struct o579_ack {
    uint32_t magic, version, error, state, pid, reserved;
    uint64_t birth, produced, drained, lost;
};
#endif
