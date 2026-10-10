// Actual source functions are inserted by check_qemu_display_modes.py.
// Mock DRM boundaries only; this is not actual kernel modesetting evidence.
#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>
#include <map>
#include <memory>

#define DISPLAY_LOGD(...) ((void)0)
#define DISPLAY_LOGE(...) ((void)0)
#define DISPLAY_CHK_RETURN(condition, result, log) do { if (condition) { log; return result; } } while (0)
enum { DISPLAY_SUCCESS = 0, DISPLAY_FAILURE = -1, DISPLAY_NULL_PTR = -2, DISPLAY_PARAM_ERR = -3,
       DRM_INVALID_ID = 0, DRM_MODE_ATOMIC_ALLOW_MODESET = 0x400 };

struct DrmMode {};
struct DrmModeBlock {
    int block = 42;
    int GetBlockId() const { return block; }
};
struct DrmCrtc {
    int mActiveModeId = -1;
    bool mNeedModeSet = false;
    int32_t SetActivieMode(int32_t id);
    int GetActiveModeId() const { return mActiveModeId; }
    bool NeedModeSet() const { return mNeedModeSet; }
    void ClearModeSet() { mNeedModeSet = false; }
    int GetId() const { return 11; }
    int GetActivePropId() const { return 12; }
    int GetModePropId() const { return 13; }
};
struct DrmConnector {
    std::map<int, DrmMode> modes{{0, {}}, {12, {}}, {13, {}}};
    int blob = 42;
    int32_t GetModeFromId(int id, DrmMode &mode) {
        auto found = modes.find(id);
        if (found == modes.end()) return DISPLAY_FAILURE;
        mode = found->second;
        return DISPLAY_SUCCESS;
    }
    std::unique_ptr<DrmModeBlock> GetModeBlockFromId(int id) {
        if (blob < 0 || modes.count(id) == 0) return nullptr;
        auto result = std::unique_ptr<DrmModeBlock>(new DrmModeBlock);
        result->block = blob;
        return result;
    }
    int GetId() const { return 21; }
    int GetPropCrtcId() const { return 22; }
};
struct DrmDevice { int GetDrmFd() const { return 31; } };
struct DrmDisplay {
    std::shared_ptr<DrmConnector> mConnector;
    std::shared_ptr<DrmCrtc> mCrtc;
    int32_t SetDisplayMode(uint32_t id);
};
struct HdiDrmComposition {
    std::shared_ptr<DrmConnector> mConnector;
    std::shared_ptr<DrmCrtc> mCrtc;
    std::shared_ptr<DrmDevice> mDrmDevice;
    int32_t UpdateMode(std::unique_ptr<DrmModeBlock> &mode);
};

struct drmModeAtomicReq {};
using drmModeAtomicReqPtr = drmModeAtomicReq*;
static int allocated, freed, properties, commits, failProperty;
static bool failAllocation, failCommit;
static drmModeAtomicReqPtr drmModeAtomicAlloc() {
    if (failAllocation) return nullptr;
    ++allocated;
    return new drmModeAtomicReq;
}
static void drmModeAtomicFree(drmModeAtomicReqPtr request) {
    assert(request != nullptr);
    ++freed;
    delete request;
}
static int drmModeAtomicAddProperty(drmModeAtomicReqPtr request, int, int, int) {
    assert(request != nullptr);
    ++properties;
    return properties == failProperty ? -1 : properties;
}
static int drmModeAtomicCommit(int fd, drmModeAtomicReqPtr request, uint32_t flags, void*) {
    assert(fd == 31 && request != nullptr && flags == DRM_MODE_ATOMIC_ALLOW_MODESET);
    ++commits;
    return failCommit ? -1 : 0;
}

// __ACTUAL_FUNCTIONS__

int main()
{
    auto connector = std::make_shared<DrmConnector>();
    auto crtc = std::make_shared<DrmCrtc>();
    DrmDisplay display{connector, crtc};
    assert(display.SetDisplayMode(0) == DISPLAY_SUCCESS);
    crtc->ClearModeSet();
#ifdef EXPECT_ORIGINAL_FAILURE
    assert(display.SetDisplayMode(13) == DISPLAY_PARAM_ERR);
    assert(crtc->GetActiveModeId() == 0 && !crtc->NeedModeSet());
    std::cout << "original rejects its advertised nonzero mode\n";
#else
    for (uint32_t id : {1U, 14U, 2147483648U, 4294967295U}) {
        assert(display.SetDisplayMode(id) == DISPLAY_PARAM_ERR);
        assert(crtc->GetActiveModeId() == 0 && !crtc->NeedModeSet());
    }
    assert(crtc->SetActivieMode(-1) == DISPLAY_PARAM_ERR);
    display.mConnector.reset();
    assert(display.SetDisplayMode(0) == DISPLAY_NULL_PTR);
    display.mConnector = connector;
    display.mCrtc.reset();
    assert(display.SetDisplayMode(0) == DISPLAY_NULL_PTR);
    display.mCrtc = crtc;
    HdiDrmComposition composition{connector, crtc, std::make_shared<DrmDevice>()};
    std::unique_ptr<DrmModeBlock> block;
    for (int cycle = 0; cycle < 100; ++cycle) {
        for (uint32_t id : {13U, 12U, 0U}) {
            assert(display.SetDisplayMode(id) == DISPLAY_SUCCESS && crtc->NeedModeSet());
            properties = 0;
            assert(composition.UpdateMode(block) == DISPLAY_SUCCESS);
            assert(!crtc->NeedModeSet() && allocated == freed && properties == 3);
            int previous = allocated;
            assert(display.SetDisplayMode(id) == DISPLAY_SUCCESS && !crtc->NeedModeSet());
            assert(composition.UpdateMode(block) == DISPLAY_SUCCESS && allocated == previous);
        }
    }
    for (int failure = 0; failure < 7; ++failure) {
        crtc->mNeedModeSet = true;
        properties = 0;
        int previousCommits = commits;
        failAllocation = failure == 0;
        connector->blob = failure == 1 ? -1 : failure == 2 ? 0 : 42;
        failProperty = failure >= 3 && failure <= 5 ? failure - 2 : 0;
        failCommit = failure == 6;
        assert(composition.UpdateMode(block) == DISPLAY_FAILURE);
        assert(crtc->NeedModeSet() && allocated == freed);
        assert(commits == previousCommits + (failCommit ? 1 : 0));
    }
    failAllocation = failCommit = false;
    failProperty = properties = 0;
    connector->blob = 42;
    assert(composition.UpdateMode(block) == DISPLAY_SUCCESS && !crtc->NeedModeSet());
    assert(allocated == freed);
    std::cout << "candidate: 300 switches, idempotence, invalid IDs, allocation/blob/property/commit failures pass\n";
#endif
}
