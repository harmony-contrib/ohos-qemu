#include <cerrno>
#include <cstdio>
#include <selinux/selinux.h>

// Ask the loaded kernel policy for its access vector. Unlike an AVC wrapper
// that honors global permissive mode, inspect the actual allowed bit directly.
// This never changes a process label, a parameter value, or enforcing mode.
int main()
{
    const security_class_t klass = string_to_security_class("parameter_service");
    const access_vector_t permission = string_to_av_perm(klass, "set");
    if (klass == 0 || permission == 0) {
        std::puts("{\"error\":\"parameter_service.set is absent from the loaded policy\"}");
        return 1;
    }
    struct Entry { const char *domain; bool expected; };
    const Entry entries[] = {
        {"init", true}, {"partner_device_agent", true},
        {"fusion_ranging", false}, {"samgr", false}, {"normal_hap", false},
        {"system_basic_hap", false}, {"system_core_hap", false},
    };
    bool passed = true;
    for (const auto &entry : entries) {
        char source[128];
        std::snprintf(source, sizeof(source), "u:r:%s:s0", entry.domain);
        av_decision decision {};
        errno = 0;
        const int rc = security_compute_av_raw(source, "u:object_r:fusion_partner_enable_param:s0",
                                              klass, permission, &decision);
        const int error = errno;
        const bool allowed = rc == 0 && (decision.allowed & permission) == permission;
        std::printf("{\"domain\":\"%s\",\"compute_rc\":%d,\"errno\":%d,\"allowed\":%s,\"expected\":%s}\n",
                    entry.domain, rc, error, allowed ? "true" : "false", entry.expected ? "true" : "false");
        passed = passed && rc == 0 && allowed == entry.expected;
    }
    return passed ? 0 : 1;
}
