/* Copyright (c) 2026 OpenHarmony QEMU contributors. SPDX-License-Identifier: Apache-2.0 */
#ifndef QEMU_SENSOR_PROTOCOL_H
#define QEMU_SENSOR_PROTOCOL_H
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>

namespace OHOS::HDI::Sensor::Qemu {
constexpr size_t NONCE_SIZE = 16;
constexpr size_t HELLO_SIZE = 32;
constexpr size_t FRAME_SIZE = 44;
constexpr float MAX_ACCELERATION = 156.9064F; // 16 g, metres per second squared.
constexpr int64_t MIN_INTERVAL_NS = 1000000;
constexpr int64_t MAX_INTERVAL_NS = 1000000000;
using Nonce = std::array<uint8_t, NONCE_SIZE>;
using Frame = std::array<uint8_t, FRAME_SIZE>;
struct Acceleration {
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
    std::memcpy(hello.data(), "QSN1", 4);
    WriteLe(hello.data() + 4, 1, 4);
    std::memcpy(hello.data() + 8, nonce.data(), nonce.size());
    WriteLe(hello.data() + 24, 1, 4); // Sensor type: accelerometer only.
    return hello;
}
inline bool DecodeFrame(const Frame& frame, const Nonce& nonce, uint64_t& sequence, Acceleration& result)
{
    if (std::memcmp(frame.data(), "QSF1", 4) != 0 || ReadLe(frame.data() + 4, 4) != 1 ||
        std::memcmp(frame.data() + 8, nonce.data(), nonce.size()) != 0) return false;
    uint64_t next = ReadLe(frame.data() + 24, 8);
    if (next == 0 || next <= sequence) return false;
    float values[3];
    static_assert(sizeof(float) == 4, "IEEE 754 float32 sensor input is required");
    for (size_t i = 0; i < 3; ++i) {
        uint32_t bits = static_cast<uint32_t>(ReadLe(frame.data() + 32 + 4 * i, 4));
        std::memcpy(&values[i], &bits, sizeof(bits));
        if (!std::isfinite(values[i]) || std::fabs(values[i]) > MAX_ACCELERATION) return false;
    }
    sequence = next;
    result = {values[0], values[1], values[2], 0};
    return true;
}
} // namespace OHOS::HDI::Sensor::Qemu
#endif
