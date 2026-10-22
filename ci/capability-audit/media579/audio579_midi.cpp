/* Copyright (c) 2026 OpenHarmony contributors.
 * Licensed under the Apache License, Version 2.0; see
 * http://www.apache.org/licenses/LICENSE-2.0
 * Distributed on an AS IS BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
 */
#include <napi/native_api.h>
#include "usb579_midi_session.inc"

namespace {
std::atomic<bool> running{false};
napi_value Run(napi_env env, napi_callback_info info)
{
    size_t count = 3; napi_value args[3]{};
    char run[33]{}, operation[33]{}, directory[257]{}; size_t length = 0;
    bool accepted = napi_get_cb_info(env, info, &count, args, nullptr, nullptr) == napi_ok && count == 3;
    char *identifiers[] = {run, operation};
    for (size_t i = 0; accepted && i < 2; ++i) {
        accepted = napi_get_value_string_utf8(env, args[i], identifiers[i], 33, &length) == napi_ok && length == 32;
        for (size_t j = 0; accepted && j < length; ++j) accepted =
            (identifiers[i][j] >= '0' && identifiers[i][j] <= '9') || (identifiers[i][j] >= 'a' && identifiers[i][j] <= 'f');
    }
    accepted = accepted && napi_get_value_string_utf8(env, args[2], directory, sizeof(directory), &length) == napi_ok &&
        length > 0 && length < sizeof(directory) &&
        (strcmp(directory, "/data/storage/el2/base/files") == 0 || strcmp(directory, "/data/storage/el2/base/haps/entry/files") == 0);
    accepted = accepted && !running.exchange(true);
    if (accepted) {
        try {
            std::thread([run = std::string(run), op = std::string(operation), directory = std::string(directory)] {
                const std::string path = directory + "/audio579-midi-" + run + "-" + op + ".jsonl";
                FILE *out = fopen(path.c_str(), "wx");
                if (out != nullptr) {
                    try { (void)usb579midi::Session(out, run, op); }
                    catch (...) { usb579midi::Number(out, "native-exception", -1); usb579midi::Number(out, "end", 0); }
                    fclose(out);
                }
                running.store(false);
            }).detach();
        } catch (...) { running.store(false); accepted = false; }
    }
    napi_value value = nullptr; napi_get_boolean(env, accepted, &value); return value;
}
napi_value Init(napi_env env, napi_value exports)
{
    const napi_property_descriptor method = {"run", nullptr, Run, nullptr, nullptr, nullptr, napi_default, nullptr};
    napi_define_properties(env, exports, 1, &method); return exports;
}
napi_module module = {1, 0, nullptr, Init, "audio579midi", nullptr, {0}};
} // namespace
extern "C" __attribute__((constructor)) void RegisterAudio579Midi() { napi_module_register(&module); }
