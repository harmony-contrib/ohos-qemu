// SPDX-License-Identifier: Apache-2.0
// Ordinary-HAP syscall diagnostic only. It never creates or changes tokens.
#include "napi/native_api.h"
#include <algorithm>
#include <cerrno>
#include <fcntl.h>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

namespace {
constexpr size_t DEVICE_PREFIX_LENGTH = 6;
constexpr size_t DEVICE_NAME_CAPACITY = 64;
constexpr uid_t SERIAL_UID = 1025;
constexpr gid_t SERIAL_GID = 1025;
constexpr uid_t ORDINARY_APP_UID_MIN = 10000;
constexpr mode_t SERIAL_DEVICE_MODE = 0660;
constexpr mode_t PERMISSION_BITS = 0777;

bool ReadName(napi_env env, napi_callback_info info, std::string& name) {
    size_t count = 1;
    napi_value argument = nullptr;
    if (napi_get_cb_info(env, info, &count, &argument, nullptr, nullptr) != napi_ok || count != 1) {
        return false;
    }
    char buffer[DEVICE_NAME_CAPACITY] = {};
    size_t length = 0;
    if (napi_get_value_string_utf8(env, argument, buffer, sizeof(buffer), &length) != napi_ok || length <= DEVICE_PREFIX_LENGTH || length >= sizeof(buffer) - 1) {
        return false;
    }
    name.assign(buffer, length);
    if (name.compare(0, DEVICE_PREFIX_LENGTH, "ttyUSB") != 0 && name.compare(0, DEVICE_PREFIX_LENGTH, "ttyACM") != 0) {
        return false;
    }
    return std::all_of(name.begin() + DEVICE_PREFIX_LENGTH, name.end(), [](char value) {
        return value >= '0' && value <= '9';
    });
}

std::string CheckDevice(const std::string& name) {
    const std::string path = "/dev/" + name;
    struct stat metadata {};
    int statResult = stat(path.c_str(), &metadata);
    int statError = statResult == 0 ? 0 : errno;
    int descriptor = open(path.c_str(), O_RDWR | O_NOCTTY | O_NONBLOCK | O_CLOEXEC);
    int openError = descriptor < 0 ? errno : 0;
    if (descriptor >= 0) {
        close(descriptor);
    }
    bool passed = statResult == 0 && S_ISCHR(metadata.st_mode) && (metadata.st_mode & PERMISSION_BITS) == SERIAL_DEVICE_MODE && metadata.st_uid == SERIAL_UID && metadata.st_gid == SERIAL_GID && geteuid() >= ORDINARY_APP_UID_MIN && descriptor < 0 && openError == EACCES;
    std::ostringstream result;
    result << "{\"passed\":" << (passed ? "true" : "false") << ",\"port_name\":\"" << name
           << "\",\"stat_errno\":" << statError << ",\"open_errno\":" << openError
           << ",\"mode\":" << (metadata.st_mode & PERMISSION_BITS) << ",\"node_uid\":" << metadata.st_uid
           << ",\"node_gid\":" << metadata.st_gid << ",\"app_uid\":" << geteuid() << "}";
    return result.str();
}

napi_value Check(napi_env env, napi_callback_info info) {
    std::string name;
    if (!ReadName(env, info, name)) {
        napi_throw_type_error(env, nullptr, "A dedicated ttyUSB/ttyACM basename is required");
        return nullptr;
    }
    const std::string checked = CheckDevice(name);
    napi_value result = nullptr;
    if (napi_create_string_utf8(env, checked.data(), checked.size(), &result) != napi_ok) {
        return nullptr;
    }
    return result;
}

napi_value UnauthorizedGrant(napi_env env, napi_callback_info) {
    // Exercise the actual service's caller-role boundary via public Node-API
    // loading. Never create a token, forge an IPC caller or grant a right.
    napi_value serial = nullptr;
    napi_value authorize = nullptr;
    napi_value arguments[2] = {nullptr, nullptr};
    napi_value result = nullptr;
    if (napi_load_module(env, "@ohos.busManager.serial", &serial) != napi_ok ||
        napi_get_named_property(env, serial, "addPortAuthorization", &authorize) != napi_ok ||
        napi_create_string_utf8(env, "0", NAPI_AUTO_LENGTH, &arguments[0]) != napi_ok ||
        napi_create_string_utf8(env, "qemu-unprivileged-grant-must-be-rejected", NAPI_AUTO_LENGTH,
            &arguments[1]) != napi_ok) {
        napi_throw_error(env, nullptr, "Cannot load actual Serial authorization entry point");
        return nullptr;
    }
    napi_status status = napi_call_function(env, serial, authorize, 2, arguments, &result);
    if (status == napi_pending_exception) {
        return nullptr; // Preserve the real module's synchronous BusinessError.
    }
    bool promise = false;
    if (status != napi_ok || napi_is_promise(env, result, &promise) != napi_ok || !promise) {
        napi_throw_error(env, nullptr, "Actual Serial authorization did not return its promise");
        return nullptr;
    }
    return result;
}

napi_value Init(napi_env env, napi_value exports) {
    const napi_property_descriptor descriptors[] = {
        { "check", nullptr, Check, nullptr, nullptr, nullptr, napi_default, nullptr },
        { "unauthorizedGrant", nullptr, UnauthorizedGrant, nullptr, nullptr, nullptr, napi_default, nullptr }
    };
    if (napi_define_properties(env, exports, sizeof(descriptors) / sizeof(descriptors[0]), descriptors) != napi_ok) {
        return nullptr;
    }
    return exports;
}

napi_module module = { 1, 0, nullptr, Init, "serialaclprobe", nullptr, { 0 } };
__attribute__((constructor)) void Register() {
    napi_module_register(&module);
}
}
