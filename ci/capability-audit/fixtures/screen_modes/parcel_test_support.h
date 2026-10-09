// Host-only deterministic Parcel dependency for executing the real ScreenInfo
// implementation. Not an OHOS IPC implementation or guest acceptance proof.
#pragma once
#include <cstdint>
#include <cstring>
#include <memory>
#include <string>
#include <vector>
#include <utility>

namespace OHOS {
template<class T> class sptr : public std::shared_ptr<T> {
public:
    sptr() = default;
    sptr(T* value) : std::shared_ptr<T>(value) {}
};
class Parcel {
public:
    std::vector<uint8_t> bytes;
    size_t cursor = 0;
    int writesUntilFailure = -1;
    template<class T> bool write(T value)
    {
        if (writesUntilFailure == 0) return false;
        if (writesUntilFailure > 0) --writesUntilFailure;
        const auto* ptr = reinterpret_cast<const uint8_t*>(&value);
        bytes.insert(bytes.end(), ptr, ptr + sizeof(T));
        return true;
    }
    template<class T> bool read(T& value)
    {
        if (GetReadableBytes() < sizeof(T)) return false;
        std::memcpy(&value, bytes.data() + cursor, sizeof(T));
        cursor += sizeof(T);
        return true;
    }
    bool WriteUint32(uint32_t value) { return write(value); }
    bool WriteUint64(uint64_t value) { return write(value); }
    bool WriteFloat(float value) { return write(value); }
    bool WriteBool(bool value) { return write<uint32_t>(value ? 1 : 0); }
    bool ReadUint32(uint32_t& value) { return read(value); }
    bool ReadUint64(uint64_t& value) { return read(value); }
    bool ReadFloat(float& value) { return read(value); }
    bool ReadBool(bool& value)
    {
        uint32_t raw = 0;
        if (!read(raw)) return false;
        value = raw != 0;
        return true;
    }
    bool WriteString(const std::string& value)
    {
        if (!WriteUint32(static_cast<uint32_t>(value.size()))) return false;
        bytes.insert(bytes.end(), value.begin(), value.end());
        return true;
    }
    bool ReadString(std::string& value)
    {
        uint32_t length = 0;
        if (!ReadUint32(length) || length > GetReadableBytes()) return false;
        value.assign(bytes.begin() + cursor, bytes.begin() + cursor + length);
        cursor += length;
        return true;
    }
    std::string ReadString() { std::string value; ReadString(value); return value; }
    size_t GetReadableBytes() const { return bytes.size() - cursor; }
};
class Parcelable {
public:
    virtual ~Parcelable() = default;
    virtual bool Marshalling(Parcel&) const = 0;
};
namespace Rosen {
using ScreenId = uint64_t;
constexpr ScreenId SCREEN_ID_INVALID = UINT64_MAX;
enum class Rotation { ROTATION_0 };
enum class Orientation { UNSPECIFIED };
enum class ScreenSourceMode { SCREEN_MAIN, SCREEN_MIRROR, SCREEN_EXTEND, SCREEN_ALONE };
struct SupportedScreenModes {
    uint32_t id_ = 0;
    uint32_t width_ = 0;
    uint32_t height_ = 0;
    uint32_t refreshRate_ = 0;
};
} // namespace Rosen
} // namespace OHOS
#define WM_DISALLOW_COPY_AND_MOVE(Type)
// Public fixture storage permits malformed/null-mode injection; production
// visibility and actual field declarations remain in the pinned source header.
#define DEFINE_VAR_DEFAULT_FUNC_GET_SET(Type, Name, member, initial) \
    Type member##_ = initial; \
    Type Get##Name() const { return member##_; } \
    void Set##Name(Type value) { member##_ = value; }
#define DEFINE_VAR_FUNC_GET(Type, Name, member) \
    Type member##_; \
    Type Get##Name() const { return member##_; }
