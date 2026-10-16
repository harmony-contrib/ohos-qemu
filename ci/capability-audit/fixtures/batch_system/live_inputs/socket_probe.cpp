// Ordinary application UID only. Does not send input, change IDs or permissions.
#include <napi/native_api.h>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

namespace {
napi_value String(napi_env env, const char* value)
{
    napi_value result;
    if (napi_create_string_utf8(env, value, NAPI_AUTO_LENGTH, &result) != napi_ok) {
        napi_throw_error(env, nullptr, "cannot return actual native observation");
        return nullptr;
    }
    return result;
}
napi_value Clock(napi_env env, napi_callback_info)
{
    timespec value{};
    if (clock_gettime(CLOCK_BOOTTIME, &value) != 0) {
        napi_throw_error(env, nullptr, "CLOCK_BOOTTIME unavailable"); return nullptr;
    }
    char result[32];
    std::snprintf(result, sizeof(result), "%llu", static_cast<unsigned long long>(value.tv_sec) * 1000000000ULL + value.tv_nsec);
    return String(env, result);
}
int Try(const char* path)
{
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    if (fd < 0) return errno;
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    std::strncpy(address.sun_path, path, sizeof(address.sun_path) - 1);
    int error = connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) == 0 ? 0 : errno;
    close(fd);
    return error;
}
napi_value Denials(napi_env env, napi_callback_info)
{
    int gnss = Try("/dev/unix/socket/qemu_gnss/input");
    int sensor = Try("/dev/unix/socket/qemu_sensor/input");
    char value[200];
    std::snprintf(value, sizeof(value), "{\"uid\":%u,\"pid\":%d,\"gnss_errno\":%d,\"sensor_errno\":%d}",
        static_cast<unsigned>(getuid()), static_cast<int>(getpid()), gnss, sensor);
    return String(env, value);
}
napi_value Init(napi_env env, napi_value exports)
{
    napi_property_descriptor properties[] = {
        {"clock", nullptr, Clock, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"denials", nullptr, Denials, nullptr, nullptr, nullptr, napi_default, nullptr},
    };
    if (napi_define_properties(env, exports, sizeof(properties) / sizeof(properties[0]), properties) != napi_ok) {
        napi_throw_error(env, nullptr, "native observation exports unavailable"); return nullptr;
    }
    return exports;
}
napi_module module = {1, 0, nullptr, Init, "liveinputaudit", nullptr, {nullptr}};
__attribute__((constructor)) void Register() { napi_module_register(&module); }
}
