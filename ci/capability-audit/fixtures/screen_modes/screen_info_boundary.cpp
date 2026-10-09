// Host rejection tests of real source; dependency stand-ins are not guest proof.
#include "screen_info.h"
#include <cassert>
#include <iostream>

int main()
{
    using namespace OHOS;
    using namespace OHOS::Rosen;
    for (uint32_t count : {0U, 1U, 20U, 21U, 26U, 255U, 256U}) {
        ScreenInfo source;
        source.SetScreenId(3);
        source.SetName("real-source-boundary-test");
        source.SetModeId(count == 0 ? 0 : count - 1);
        for (uint32_t index = 0; index < count; ++index) {
            sptr<SupportedScreenModes> mode = new SupportedScreenModes();
            mode->id_ = index;
            mode->width_ = 1280;
            mode->height_ = 800;
            mode->refreshRate_ = 75;
            source.modes_.push_back(mode);
        }
        Parcel parcel;
        assert(source.Marshalling(parcel));
        std::unique_ptr<ScreenInfo> decoded(ScreenInfo::Unmarshalling(parcel));
        assert(decoded && decoded->GetScreenId() == 3 && decoded->GetModes().size() == count);
        assert(decoded->GetModeId() == source.GetModeId());
        assert(parcel.GetReadableBytes() == 0);
        if (count == 256) {
            // The pinned wire header ends with count, isExtend, serial string,
            // rsId, mirror width and mirror height (serial string is empty).
            const size_t countOffset = parcel.bytes.size() - count * 4 * sizeof(uint32_t) - 28;
            for (uint32_t declared : {257U, UINT32_MAX}) {
                Parcel hostile;
                hostile.bytes = parcel.bytes;
                std::memcpy(hostile.bytes.data() + countOffset, &declared, sizeof(declared));
                std::unique_ptr<ScreenInfo> rejected(ScreenInfo::Unmarshalling(hostile));
                assert(!rejected);
            }
        }
        for (uint32_t index = 0; index < count; ++index) {
            const auto mode = decoded->GetModes()[index];
            assert(mode->id_ == index && mode->width_ == 1280 && mode->height_ == 800 && mode->refreshRate_ == 75);
        }
        // Every truncated byte boundary must be rejected, not partially decoded.
        for (size_t length = 0; length < parcel.bytes.size(); ++length) {
            Parcel truncated;
            truncated.bytes.assign(parcel.bytes.begin(), parcel.bytes.begin() + length);
            std::unique_ptr<ScreenInfo> bad(ScreenInfo::Unmarshalling(truncated));
            assert(!bad);
        }
        for (int failAt = 0; failAt < 19 + static_cast<int>(count) * 4; ++failAt) {
            Parcel failed;
            failed.writesUntilFailure = failAt;
            assert(!source.Marshalling(failed));
        }
    }
    ScreenInfo oversized;
    for (uint32_t i = 0; i < 257; ++i) oversized.modes_.push_back(new SupportedScreenModes());
    Parcel untouched;
    assert(!oversized.Marshalling(untouched) && untouched.bytes.empty());
    ScreenInfo nullMode;
    nullMode.modes_.push_back(nullptr);
    assert(!nullMode.Marshalling(untouched) && untouched.bytes.empty());
    std::cout << "real ScreenInfo bounded serialization host tests passed\n";
}
