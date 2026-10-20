// Actual platform-linked fixture. No manufactured AbilityRecord or token.
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <dlfcn.h>
#include <string>
#include <map>
#include <memory>
#include <limits>
#include <unistd.h>
#include "context.h"
#include "ipc_skeleton.h"
#include "iservice_registry.h"
#include "message_option.h"
#include "message_parcel.h"
#include "napi_base_context.h"
#include "napi_remote_object.h"
#include "napi/native_api.h"
#include "napi/native_node_api.h"
#include "system_ability_definition.h"

namespace {
constexpr uint32_t STOP_CODE = 6179;
constexpr const char *DESCRIPTOR = "ohos.aafwk.AbilityManager";
using namespace OHOS;

napi_value Fail(napi_env env, const char *message)
{
    napi_throw_error(env, nullptr, message);
    return nullptr;
}
napi_value String(napi_env env, const std::string &text)
{
    napi_value result = nullptr;
    napi_create_string_utf8(env, text.c_str(), text.size(), &result);
    return result;
}
void Put(napi_env env, napi_value object, const char *key, napi_value value)
{
    napi_set_named_property(env, object, key, value);
}
void Number(napi_env env, napi_value object, const char *key, double value)
{
    napi_value number = nullptr;
    napi_create_double(env, value, &number);
    Put(env, object, key, number);
}
void Boolean(napi_env env, napi_value object, const char *key, bool value)
{
    napi_value boolean = nullptr;
    napi_get_boolean(env, value, &boolean);
    Put(env, object, key, boolean);
}
std::string Hex(const MessageParcel &parcel)
{
    constexpr char digits[] = "0123456789abcdef";
    const auto *data = reinterpret_cast<const uint8_t *>(parcel.GetData());
    std::string out;
    for (size_t i = 0; i < parcel.GetDataSize(); ++i) {
        out.push_back(digits[data[i] >> 4]);
        out.push_back(digits[data[i] & 15]);
    }
    return out;
}
void Identity(napi_env env, napi_value out)
{
    Number(env, out, "pid", getpid());
    Number(env, out, "uid", getuid());
    char token[17] = {};
    std::snprintf(token, sizeof(token), "%016llx",
        static_cast<unsigned long long>(IPCSkeleton::GetSelfTokenID()));
    Put(env, out, "selfTokenHex", String(env, token));
    Dl_info info {};
    if (dladdr(reinterpret_cast<void *>(&Identity), &info) != 0 && info.dli_fname != nullptr) {
        Put(env, out, "library", String(env, info.dli_fname));
    }
}
napi_value SelfToken(napi_env env, napi_callback_info info)
{
    napi_value args[2] = {};
    size_t argc = 2;
    if (napi_get_cb_info(env, info, &argc, args, nullptr, nullptr) != napi_ok || argc != 1) {
        return Fail(env, "one actual Stage Context required");
    }
    auto context = AbilityRuntime::GetStageModeContext(env, args[0]);
    if (context == nullptr || context->GetToken() == nullptr) {
        return Fail(env, "actual Context/token absent");
    }
    return NAPI_ohos_rpc_CreateJsRemoteObject(env, context->GetToken());
}
napi_value IdentityContext(napi_env env, napi_callback_info info)
{
    napi_value args[2] = {};
    size_t argc = 2;
    if (napi_get_cb_info(env, info, &argc, args, nullptr, nullptr) != napi_ok || argc != 1) {
        return Fail(env, "one actual Stage Context required");
    }
    auto context = AbilityRuntime::GetStageModeContext(env, args[0]);
    if (context == nullptr || context->GetToken() == nullptr) {
        return Fail(env, "actual Context/token absent");
    }
    napi_value out = nullptr;
    napi_create_object(env, &out);
    Identity(env, out);
    Put(env, out, "bundle", String(env, context->GetBundleName()));
    return out;
}
napi_value Attempt(napi_env env, napi_callback_info info)
{
    napi_value args[4] = {};
    size_t argc = 4;
    double expected = 0;
    size_t length = 0;
    char mode[40] = {};
    if (napi_get_cb_info(env, info, &argc, args, nullptr, nullptr) != napi_ok || argc != 3 ||
        napi_get_value_double(env, args[1], &expected) != napi_ok || !std::isfinite(expected) ||
        expected != std::floor(expected) || expected < 1 || expected > std::numeric_limits<int32_t>::max() ||
        napi_get_value_string_utf8(env, args[2], mode, sizeof(mode), &length) != napi_ok ||
        length >= sizeof(mode) - 1) {
        return Fail(env, "real token, positive int32 and finite fixture mode required");
    }
    const std::string variant(mode);
    if (variant != "normal" && variant != "missing-token" && variant != "missing-id" &&
        variant != "extra" && variant != "zero" && variant != "negative" &&
        variant != "wrong-descriptor" && variant != "truncated-1" && variant != "truncated-2" &&
        variant != "truncated-3") {
        return Fail(env, "unlisted parcel mutation");
    }
    auto token = NAPI_ohos_rpc_getNativeRemoteObject(env, args[0]);
    if (token == nullptr) { return Fail(env, "actual RPC-wrapped Context token required"); }
    auto samgr = SystemAbilityManagerClient::GetInstance().GetSystemAbilityManager();
    auto manager = samgr == nullptr ? nullptr : samgr->GetSystemAbility(ABILITY_MGR_SERVICE_ID);
    if (manager == nullptr) { return Fail(env, "real AMS system ability unavailable"); }
    MessageParcel data;
    MessageParcel reply;
    MessageOption option(MessageOption::TF_SYNC);
    const std::u16string descriptor = variant == "wrong-descriptor" ? u"settings_idle579.invalid" :
        u"ohos.aafwk.AbilityManager";
    if (!data.WriteInterfaceToken(descriptor)) { return Fail(env, "descriptor write failed"); }
    if (variant != "missing-token" && !data.WriteRemoteObject(token)) {
        return Fail(env, "real token parcel write failed");
    }
    const size_t beforeId = data.GetDataSize();
    if (variant != "missing-token" && variant != "missing-id") {
        const int32_t value = variant == "zero" ? 0 : variant == "negative" ? -1 :
            static_cast<int32_t>(expected);
        if (!data.WriteInt32(value)) { return Fail(env, "id write failed"); }
    }
    if (variant == "extra" && !data.WriteInt32(0x579)) { return Fail(env, "extra write failed"); }
    if (variant.compare(0, 10, "truncated-") == 0 &&
        !data.SetDataSize(beforeId + static_cast<size_t>(variant.back() - '0'))) {
        return Fail(env, "actual parcel truncation failed");
    }
    napi_value out = nullptr;
    napi_create_object(env, &out);
    Identity(env, out);
    Put(env, out, "mode", String(env, variant));
    Put(env, out, "descriptor", String(env, variant == "wrong-descriptor" ?
        "settings_idle579.invalid" : DESCRIPTOR));
    Number(env, out, "code", STOP_CODE);
    Number(env, out, "expectedStartId", expected);
    Number(env, out, "requestBytes", data.GetDataSize());
    Number(env, out, "requestObjects", data.GetOffsetsSize());
    Put(env, out, "clientParcelHex", String(env, Hex(data)));
    const int32_t transport = manager->SendRequest(STOP_CODE, data, reply, option);
    Number(env, out, "transport", transport);
    Number(env, out, "replyBytes", reply.GetDataSize());
    Put(env, out, "replyHex", String(env, Hex(reply)));
    int32_t result = 0;
    bool stopped = false;
    const bool readResult = reply.ReadInt32(result);
    const bool readStopped = reply.ReadBool(stopped);
    Boolean(env, out, "readResult", readResult);
    Boolean(env, out, "readStopped", readStopped);
    Number(env, out, "result", result);
    Boolean(env, out, "stopped", stopped);
    Number(env, out, "remaining", reply.GetReadableBytes());
    return out;
}
napi_value Init(napi_env env, napi_value exports)
{
    const napi_property_descriptor properties[] = {
        {"selfToken", nullptr, SelfToken, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"identity", nullptr, IdentityContext, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"attempt", nullptr, Attempt, nullptr, nullptr, nullptr, napi_default, nullptr},
    };
    napi_define_properties(env, exports, sizeof(properties) / sizeof(properties[0]), properties);
    return exports;
}
napi_module module = {1, 0, nullptr, Init, "settings_idle579", nullptr, {0}};
__attribute__((constructor)) void Register() { napi_module_register(&module); }
}
