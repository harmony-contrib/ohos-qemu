#pragma once
#include <signal.h>
#include <sys/prctl.h>
#include <sys/types.h>
#include <unistd.h>

namespace OhosOpenvpn {
// init stops ordinary services with SIGKILL. Their C++ destructors cannot run,
// so every exec child must also die when its exact parent disappears. Linux
// clears this setting on fork; both the OpenVPN child and its bridge set it.
inline bool BindToParent(pid_t expectedParent)
{
    if (expectedParent <= 1 || prctl(PR_SET_PDEATHSIG, SIGKILL, 0, 0, 0) != 0) return false;
    // A parent can exit between fork/getppid and prctl. Fail before touching
    // the VPN service or TUN if that race has already reparented this process.
    return getppid() == expectedParent;
}
} // namespace OhosOpenvpn
