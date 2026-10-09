// Execute the exact proxy method with injected transport failures. This is
// host-only failure-path testing, never real Binder or guest success evidence.
#include <cassert>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>
#include <utility>

template<class T> using sptr = std::shared_ptr<T>;
enum class DMError { DM_OK = 0, DM_ERROR_NULLPTR = -1,
    DM_ERROR_WRITE_INTERFACE_TOKEN_FAILED = -2, DM_ERROR_IPC_FAILED = -3 };
enum class DisplayManagerMessage { TRANS_ID_GET_ALL_SCREEN_INFOS = 1 };
constexpr int ERR_NONE = 0;
struct ScreenInfo { int id; };
struct MessageOption {};
bool missingRemote = false;
bool tokenAccepted = true;
bool resultPresent = true;
bool decodedComplete = true;
int transportResult = 0;
int serviceResult = 0;
struct MessageParcel {
    bool WriteInterfaceToken(const std::string&) { return tokenAccepted; }
    bool ReadInt32(int32_t& value) { value = serviceResult; return resultPresent; }
};
struct IRemoteObject {
    int SendRequest(uint32_t, MessageParcel&, MessageParcel&, MessageOption&) { return transportResult; }
};
struct MarshallingHelper {
    template<class T> static bool UnmarshallingVectorParcelableObj(MessageParcel&, std::vector<sptr<T>>& output)
    {
        output.push_back(std::make_shared<T>(T {42}));
        return decodedComplete;
    }
};
struct ScreenSessionManagerProxy {
    sptr<IRemoteObject> Remote() { return missingRemote ? nullptr : std::make_shared<IRemoteObject>(); }
    std::string GetDescriptor() { return "host-test-only"; }
    DMError GetAllScreenInfos(std::vector<sptr<ScreenInfo>>&);
};
#define TLOGW(...)
#define TLOGE(...)
#include "screen_proxy_method.inc"

int main()
{
    for (int repeat = 0; repeat < 64; ++repeat) {
        for (int fault = 0; fault < 7; ++fault) {
            missingRemote = fault == 1;
            tokenAccepted = fault != 2;
            transportResult = fault == 3 ? -10 : 0;
            resultPresent = fault != 4;
            serviceResult = fault == 5 ? 202 : 0;
            decodedComplete = fault != 6;
            std::vector<sptr<ScreenInfo>> actual {std::make_shared<ScreenInfo>(ScreenInfo {99})};
            ScreenSessionManagerProxy proxy;
            DMError result = proxy.GetAllScreenInfos(actual);
            if (fault == 0) {
                assert(result == DMError::DM_OK && actual.size() == 1 && actual[0]->id == 42);
            } else {
                assert(result != DMError::DM_OK && actual.size() == 1 && actual[0]->id == 99);
                if (fault == 5) assert(static_cast<int>(result) == 202);
                if (fault == 4 || fault == 6) assert(result == DMError::DM_ERROR_IPC_FAILED);
            }
        }
    }
}
