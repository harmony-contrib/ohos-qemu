/* Copyright (c) 2026 OpenHarmony QEMU contributors. SPDX-License-Identifier: Apache-2.0 */
#ifndef QEMU_HEADPOSTURE_PROTOCOL_H
#define QEMU_HEADPOSTURE_PROTOCOL_H
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>

namespace OHOS::HDI::Sensor::Qemu::HeadPosture {
constexpr size_t NONCE_SIZE = 16;
constexpr size_t HELLO_SIZE = 32;
constexpr size_t FRAME_SIZE = 52;
constexpr float UNIT_TOLERANCE = 0.0001F;
constexpr int64_t MIN_INTERVAL_NS = 1000000;
constexpr int64_t MAX_INTERVAL_NS = 1000000000;
using Nonce = std::array<uint8_t, NONCE_SIZE>;
using Frame = std::array<uint8_t, FRAME_SIZE>;
struct Posture {
    uint32_t order;
    float w;
    float x;
    float y;
    float z;
    int64_t timestamp;
};
inline uint64_t ReadLe(const uint8_t* data, size_t count)
{
    uint64_t value = 0;
    for (size_t i = 0; i < count; ++i) value |= static_cast<uint64_t>(data[i]) << (i * 8);
    return value;
}
inline void WriteLe(uint8_t* data, uint64_t value, size_t count)
{
    for (size_t i = 0; i < count; ++i) data[i] = static_cast<uint8_t>(value >> (i * 8));
}
inline std::array<uint8_t, HELLO_SIZE> MakeHello(const Nonce& nonce)
{
    std::array<uint8_t, HELLO_SIZE> hello{};
    std::memcpy(hello.data(), "QHP1", 4);
    WriteLe(hello.data() + 4, 1, 4);
    std::memcpy(hello.data() + 8, nonce.data(), nonce.size());
    WriteLe(hello.data() + 24, 268, 4);
    return hello;
}
inline bool DecodeFrame(const Frame& frame, const Nonce& nonce, uint64_t& sequence,
    uint32_t& previousOrder, Posture& result)
{
    if (std::memcmp(frame.data(), "QHF1", 4) != 0 || ReadLe(frame.data() + 4, 4) != 1 ||
        std::memcmp(frame.data() + 8, nonce.data(), nonce.size()) != 0) return false;
    const uint64_t next = ReadLe(frame.data() + 24, 8);
    const uint32_t order = static_cast<uint32_t>(ReadLe(frame.data() + 32, 4));
    // The actual HDI adapter uses float index1 -> int32 order. Keep it exact.
    if (next == 0 || next <= sequence || order == 0 || order > 16777215 || order <= previousOrder) return false;
    float values[4];
    static_assert(sizeof(float) == 4, "IEEE 754 float32 head input required");
    for (size_t i = 0; i < 4; ++i) {
        uint32_t bits = static_cast<uint32_t>(ReadLe(frame.data() + 36 + 4 * i, 4));
        std::memcpy(&values[i], &bits, sizeof(bits));
        if (!std::isfinite(values[i]) || std::fabs(values[i]) > 1.0F) return false;
    }
    const float norm = values[0]*values[0]+values[1]*values[1]+values[2]*values[2]+values[3]*values[3];
    if (std::fabs(norm - 1.0F) > UNIT_TOLERANCE) return false;
    sequence = next;
    previousOrder = order;
    result = {order, values[0], values[1], values[2], values[3], 0};
    return true;
}
} // namespace OHOS::HDI::Sensor::Qemu::HeadPosture
#endif
