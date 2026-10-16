/* Copyright (c) 2026 OpenHarmony QEMU contributors. SPDX-License-Identifier: Apache-2.0 */
#ifndef QEMU_GNSS_PROTOCOL_H
#define QEMU_GNSS_PROTOCOL_H
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <time.h>

namespace OHOS::QemuGnss {
constexpr size_t NONCE_SIZE = 16;
constexpr size_t HELLO_SIZE = 32;
constexpr size_t FRAME_SIZE = 88;
constexpr int64_t MIN_INTERVAL_NS = 0;
constexpr int64_t MAX_INTERVAL_NS = 3600000000000LL;
using Nonce = std::array<uint8_t, NONCE_SIZE>;
using Frame = std::array<uint8_t, FRAME_SIZE>;
struct Fix {
    double latitude, longitude, altitude;
    float horizontalAccuracy, verticalAccuracy, speed, bearing;
    int64_t utcMs;
    uint64_t bootNs;
    uint32_t optionalFields;
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
template<class T> inline T ReadNumber(const uint8_t* data)
{
    static_assert(sizeof(T) == 4 || sizeof(T) == 8);
    auto bits = ReadLe(data, sizeof(T));
    T value;
    if constexpr (sizeof(T) == 4) { uint32_t small = static_cast<uint32_t>(bits); std::memcpy(&value, &small, 4); }
    else std::memcpy(&value, &bits, 8);
    return value;
}
inline uint64_t BootNs()
{
    timespec time{};
#ifdef CLOCK_BOOTTIME
    if (clock_gettime(CLOCK_BOOTTIME, &time) != 0) return 0;
#else
    if (clock_gettime(CLOCK_MONOTONIC, &time) != 0) return 0;
#endif
    return static_cast<uint64_t>(time.tv_sec) * 1000000000ULL + static_cast<uint64_t>(time.tv_nsec);
}
inline int64_t UtcMs()
{
    timespec time{};
    if (clock_gettime(CLOCK_REALTIME, &time) != 0) return 0;
    return static_cast<int64_t>(time.tv_sec) * 1000 + time.tv_nsec / 1000000;
}
inline std::array<uint8_t, HELLO_SIZE> MakeHello(const Nonce& nonce)
{
    std::array<uint8_t, HELLO_SIZE> hello{};
    std::memcpy(hello.data(), "QGN1", 4); WriteLe(hello.data() + 4, 1, 4);
    std::memcpy(hello.data() + 8, nonce.data(), nonce.size());
    WriteLe(hello.data() + 24, FRAME_SIZE, 4);
    return hello;
}
inline bool DecodeFrame(const Frame& frame, const Nonce& nonce, uint64_t& sequence, int64_t& utc, Fix& result)
{
    if (std::memcmp(frame.data(), "QGF1", 4) != 0 || ReadLe(frame.data() + 4, 4) != 1 ||
        std::memcmp(frame.data() + 8, nonce.data(), nonce.size()) != 0 || ReadLe(frame.data() + 84, 4) != 0) return false;
    uint64_t next = ReadLe(frame.data() + 24, 8), stamp = ReadLe(frame.data() + 32, 8);
    int64_t now = UtcMs();
    if (next == 0 || next <= sequence || now <= 0 || stamp < 1577836800000ULL || stamp > 4102444800000ULL ||
        stamp <= static_cast<uint64_t>(utc) || static_cast<int64_t>(stamp) < now - 10000 ||
        static_cast<int64_t>(stamp) > now + 1000) return false;
    Fix fix{ReadNumber<double>(frame.data()+40), ReadNumber<double>(frame.data()+48),
        ReadNumber<double>(frame.data()+56), ReadNumber<float>(frame.data()+64),
        ReadNumber<float>(frame.data()+68), ReadNumber<float>(frame.data()+72),
        ReadNumber<float>(frame.data()+76), static_cast<int64_t>(stamp), 0,
        static_cast<uint32_t>(ReadLe(frame.data()+80, 4))};
    constexpr uint32_t OPTIONAL = 4 | 8 | 16 | 64;
    if ((fix.optionalFields & ~OPTIONAL) || !std::isfinite(fix.latitude) || !std::isfinite(fix.longitude) ||
        !std::isfinite(fix.altitude) || !std::isfinite(fix.horizontalAccuracy) ||
        !std::isfinite(fix.verticalAccuracy) || !std::isfinite(fix.speed) || !std::isfinite(fix.bearing) ||
        fix.latitude < -90 || fix.latitude > 90 || fix.longitude < -180 || fix.longitude > 180 ||
        fix.altitude < -12000 || fix.altitude > 100000 || fix.horizontalAccuracy <= 0 || fix.horizontalAccuracy > 100000 ||
        fix.verticalAccuracy < 0 || fix.verticalAccuracy > 100000 || ((fix.optionalFields & 64) && fix.verticalAccuracy == 0) ||
        fix.speed < 0 || fix.speed > 1500 || fix.bearing < 0 || fix.bearing >= 360) return false;
    sequence = next; utc = fix.utcMs; result = fix;
    return true;
}
} // namespace OHOS::QemuGnss
#endif
