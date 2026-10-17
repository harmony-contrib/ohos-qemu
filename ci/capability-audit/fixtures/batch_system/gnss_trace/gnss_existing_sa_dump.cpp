// Diagnostic client of the existing SA Dump API, never an HDI observer/owner.
#include "iservice_registry.h"
#include "iremote_object.h"
#include "system_ability_definition.h"

#include <cstdio>
#include <string>
#include <type_traits>
#include <unistd.h>
#include <vector>
#ifdef __EXCEPTIONS
#error Preserve actual product fno-exceptions
#endif
static_assert(std::is_same<std::string, std::__h::basic_string<char>>::value,
    "Use actual system libc++ __h ABI, never an SDK namespace override");

int main(int argc, char**)
{
    if (argc != 1) return 64; // No owner assertion, SA id, or arbitrary Dump args accepted.
    const uid_t uid = getuid();
    const uid_t euid = geteuid();
    if (uid != 0 || euid != 0) {
        std::fprintf(stderr, "GNSS diagnostic Dump requires actual uid/euid 0\n");
        return 77;
    }
    auto manager = OHOS::SystemAbilityManagerClient::GetInstance().GetSystemAbilityManager();
    if (manager == nullptr) return 69;
    // Exactly the existing/nonblocking one-int overload. The bool& overload can
    // load on-demand SAs; it is deliberately not used by this diagnostic client.
    auto remote = manager->CheckSystemAbility(OHOS::LOCATION_GNSS_SA_ID);
    if (remote == nullptr || !remote->IsProxyObject() || remote->IsObjectDead()) return 69;
    const std::vector<std::u16string> args{u"--qemu-gnss-hdi-raw-trace"};
    const int result = remote->Dump(STDOUT_FILENO, args);
    std::fprintf(stderr,
        "{\"schema\":\"qemu-gnss-dump-client/v1\",\"uid\":%u,\"euid\":%u,"
        "\"pid\":%ld,\"saId\":%d,\"dumpResult\":%d,\"runtimeVerdict\":false}\n",
        static_cast<unsigned>(uid), static_cast<unsigned>(euid), static_cast<long>(getpid()),
        static_cast<int>(OHOS::LOCATION_GNSS_SA_ID), result);
    // Success only means the synchronous IPC returned. The actual trace schema,
    // same-process window and expected source fields must all be checked separately.
    return result == 0 ? 0 : 1;
}
