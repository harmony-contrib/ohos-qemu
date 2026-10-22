/* Copyright (c) 2026 OpenHarmony contributors.
 * Licensed under the Apache License, Version 2.0; see
 * http://www.apache.org/licenses/LICENSE-2.0
 * Distributed on an AS IS BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
 */
/* Included by the original normally compiled/signed Audio10 MIDI NAPI addon.
 * One real client spans actual host USB attach -> nonce transfer -> unplug ->
 * stale send -> reattach -> second transfer. The peer is a separate root-owned
 * process on the gadget raw-MIDI side, never this client or its callback.
 */
#include <midi/native_midi.h>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>
#include <thread>
#include <unistd.h>

namespace usb579midi {
constexpr uint64_t VENDOR = 0x1d6b;
constexpr uint64_t PRODUCT = 0x0104;
struct Wire {
    std::atomic<bool> ready{false};
    int kind = 0;
    int64_t id = 0;
    uint64_t vendor = 0, product = 0, timestamp = 0;
    size_t length = 0;
    std::array<uint32_t, 4> words{};
};
struct Context {
    std::array<Wire, 1024> wire{};
    std::atomic<size_t> next{0};
    std::atomic<int> error{0};
    std::atomic<int64_t> selected{-1};
    size_t emitted = 0;
    std::array<uint32_t, 64> response{};
    size_t responseCount = 0, responseOffCount = 0;
    unsigned peerReady = 0;
    unsigned connected = 0, disconnected = 0;
};
static int64_t Clock()
{
    return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
static void Number(FILE *out, const char *event, int64_t value)
{
    fprintf(out, "{\"event\":\"%s\",\"value\":%lld,\"monotonic_ms\":%lld}\n", event,
        static_cast<long long>(value), static_cast<long long>(Clock())); fflush(out);
}
static Wire *Reserve(Context &context)
{
    size_t index = context.next.fetch_add(1, std::memory_order_relaxed);
    if (index >= context.wire.size()) { context.error.store(-1); return nullptr; }
    return &context.wire[index];
}
static void Changed(void *opaque, OH_MIDIDeviceChangeAction action, OH_MIDIDeviceInformation info)
{
    auto &context = *static_cast<Context *>(opaque);
    if (!(info.vendorId == VENDOR && info.productId == PRODUCT) && info.midiDeviceId != context.selected.load()) return;
    Wire *wire = Reserve(context); if (wire == nullptr) return;
    wire->kind = action == OH_MIDI_DEVICE_CHANGE_ACTION_CONNECTED ? 1 : action == OH_MIDI_DEVICE_CHANGE_ACTION_DISCONNECTED ? 2 : 3;
    wire->id = info.midiDeviceId; wire->vendor = info.vendorId; wire->product = info.productId;
    wire->ready.store(true, std::memory_order_release);
}
static void Error(void *opaque, OH_MIDIStatusCode status)
{
    static_cast<Context *>(opaque)->error.store(status);
}
static void Received(void *opaque, const OH_MIDIEvent *events, size_t count)
{
    auto &context = *static_cast<Context *>(opaque);
    if (events == nullptr || count > 256) { context.error.store(-2); return; }
    for (size_t i = 0; i < count; ++i) {
        Wire *wire = Reserve(context); if (wire == nullptr) return;
        if (events[i].data == nullptr || events[i].length == 0 || events[i].length > 4) { context.error.store(-3); return; }
        wire->kind = 4; wire->timestamp = events[i].timestamp; wire->length = events[i].length;
        memcpy(wire->words.data(), events[i].data, wire->length * sizeof(uint32_t));
        wire->ready.store(true, std::memory_order_release);
    }
}
static bool Drain(FILE *out, Context &context)
{
    size_t count = context.next.load(std::memory_order_acquire);
    if (count > context.wire.size() || context.error.load() != 0) { Number(out, "callback-error", context.error.load()); return false; }
    while (context.emitted < count) {
        Wire &wire = context.wire[context.emitted];
        if (!wire.ready.load(std::memory_order_acquire)) break;
        ++context.emitted;
        if (wire.kind == 1 || wire.kind == 2) {
            context.connected += wire.kind == 1; context.disconnected += wire.kind == 2;
            fprintf(out, "{\"event\":\"native-device-change\",\"kind\":%d,\"id\":%lld,\"vendor\":%llu,\"product\":%llu,\"monotonic_ms\":%lld}\n",
                wire.kind, static_cast<long long>(wire.id), static_cast<unsigned long long>(wire.vendor),
                static_cast<unsigned long long>(wire.product), static_cast<long long>(Clock()));
        } else if (wire.kind == 4) {
            fprintf(out, "{\"event\":\"native-received-ump\",\"timestamp\":%llu,\"words\":[", static_cast<unsigned long long>(wire.timestamp));
            for (size_t i = 0; i < wire.length; ++i) fprintf(out, "%s%u", i == 0 ? "" : ",", wire.words[i]);
            fputs("]}\n", out);
            if (wire.length == 1 && (wire.words[0] & 0xffff0000U) == 0x20910000U) {
                if (context.responseCount >= context.response.size()) return false;
                context.response[context.responseCount++] = wire.words[0];
            }
            if (wire.length == 1 && (wire.words[0] & 0xffff0000U) == 0x20810000U) ++context.responseOffCount;
            if (wire.length == 1 && wire.words[0] == 0x20925557U) ++context.peerReady;
        } else return false;
        fflush(out);
    }
    return true;
}
static bool Catalog(FILE *out, OH_MIDIClient *client, OH_MIDIDeviceInformation &selected, bool &present)
{
    size_t count = 0, actual = 0; int status = OH_MIDIClient_GetDeviceCount(client, &count);
    if (status != 0 || count > 128) { Number(out, "native-catalog-status", status); return false; }
    std::array<OH_MIDIDeviceInformation, 128> devices{};
    status = OH_MIDIClient_GetDeviceInfos(client, devices.data(), devices.size(), &actual);
    if (status != 0 || actual > devices.size()) { Number(out, "native-device-list-status", status); return false; }
    // Hotplug may occur between the two real calls. Preserve both real counts;
    // select from the complete second snapshot, never require total == 1.
    Number(out, "native-device-count-before-list", count); Number(out, "native-device-list-count", actual);
    size_t matching = 0;
    for (size_t i = 0; i < actual; ++i) {
        const auto &value = devices[i];
        fprintf(out, "{\"event\":\"native-catalog-device\",\"id\":%lld,\"vendor\":%llu,\"product\":%llu,\"type\":%d}\n",
            static_cast<long long>(value.midiDeviceId), static_cast<unsigned long long>(value.vendorId),
            static_cast<unsigned long long>(value.productId), static_cast<int>(value.deviceType));
        if (value.vendorId == VENDOR && value.productId == PRODUCT) { selected = value; ++matching; }
    }
    Number(out, "actual-target-device-count", matching);
    present = matching == 1; return matching <= 1;
}
static bool WaitDevice(FILE *out, Context &context, OH_MIDIClient *client, bool wanted, unsigned events,
    OH_MIDIDeviceInformation &selected)
{
    const int64_t deadline = Clock() + 45000;
    do {
        bool present = false;
        if (!Drain(out, context) || !Catalog(out, client, selected, present)) return false;
        if (present == wanted && (wanted ? context.connected : context.disconnected) > events) return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    } while (Clock() < deadline);
    Number(out, "native-device-event-deadline", wanted); return false;
}
static bool Transfer(FILE *out, Context &context, OH_MIDIClient *client, const std::string &run,
    const OH_MIDIDeviceInformation &selected, OH_MIDIDevice *&device, uint32_t &input, uint32_t &output,
    bool &inputOpen, bool &outputOpen)
{
    int status = OH_MIDIClient_OpenDevice(client, selected.midiDeviceId, &device); Number(out, "open-device", status);
    if (status != 0 || device == nullptr) return false;
    context.selected.store(selected.midiDeviceId);
    size_t count = 0, actual = 0; status = OH_MIDIClient_GetPortCount(client, selected.midiDeviceId, &count);
    Number(out, "port-count-status", status); Number(out, "actual-port-count", count);
    if (status != 0 || count != 2) return false;
    std::array<OH_MIDIPortInformation, 2> ports{};
    status = OH_MIDIClient_GetPortInfos(client, selected.midiDeviceId, ports.data(), ports.size(), &actual);
    Number(out, "port-list-status", status); if (status != 0 || actual != count) return false;
    bool haveInput = false, haveOutput = false;
    for (const auto &port : ports) {
        Number(out, "actual-port-direction", port.direction); Number(out, "actual-port-index", port.portIndex);
        if (port.direction == OH_MIDI_PORT_DIRECTION_INPUT) { input = port.portIndex; haveInput = true; }
        if (port.direction == OH_MIDI_PORT_DIRECTION_OUTPUT) { output = port.portIndex; haveOutput = true; }
    }
    if (!haveInput || !haveOutput) return false;
    status = OH_MIDIDevice_OpenInputPort(device, {input, OH_MIDI_PROTOCOL_1_0}, Received, &context);
    Number(out, "open-input", status); inputOpen = status == 0; if (!inputOpen) return false;
    status = OH_MIDIDevice_OpenOutputPort(device, {output, OH_MIDI_PROTOCOL_1_0});
    Number(out, "open-output", status); outputOpen = status == 0; if (!outputOpen) return false;
    context.responseCount = 0; context.responseOffCount = 0; context.peerReady = 0;
    const int64_t readyDeadline = Clock() + 15000;
    while (context.peerReady == 0 && Clock() < readyDeadline) {
        if (!Drain(out, context)) return false;
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    if (context.peerReady == 0) return false;
    Number(out, "actual-independent-peer-ready-ump", 0x20925557U);
    std::array<uint32_t, 16> notes{};
    for (size_t i = 0; i < notes.size(); ++i) {
        unsigned byte = static_cast<unsigned>(std::stoul(run.substr(i * 2, 2), nullptr, 16));
        notes[i] = 0x20900000U | ((48U + byte % 24U) << 8U) | (20U + byte % 90U);
        OH_MIDIEvent event = {0, 1, &notes[i]}; uint32_t written = 0;
        status = OH_MIDIDevice_Send(device, output, &event, 1, &written);
        Number(out, "actual-sent-word", notes[i]); Number(out, "actual-send-status", status); Number(out, "actual-send-count", written);
        if (status != 0 || written != 1) return false;
        std::this_thread::sleep_for(std::chrono::milliseconds(30));
    }
    for (uint32_t note : notes) {
        note = (note & 0xff00ff00U) | 0x00800000U; OH_MIDIEvent event = {0, 1, &note}; uint32_t written = 0;
        status = OH_MIDIDevice_Send(device, output, &event, 1, &written);
        Number(out, "actual-noteoff-word", note); Number(out, "actual-noteoff-status", status); Number(out, "actual-noteoff-count", written);
        if (status != 0 || written != 1) return false;
    }
    const int64_t deadline = Clock() + 20000;
    while ((context.responseCount < 16 || context.responseOffCount < 16) && Clock() < deadline) {
        if (!Drain(out, context)) return false;
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    return Drain(out, context) && context.responseCount == 16 && context.responseOffCount == 16;
}
static void Close(FILE *out, OH_MIDIClient *client, OH_MIDIDevice *&device,
    uint32_t input, uint32_t output, bool &inputOpen, bool &outputOpen)
{
    if (outputOpen) { Number(out, "close-output", OH_MIDIDevice_CloseOutputPort(device, output)); outputOpen = false; }
    if (inputOpen) { Number(out, "close-input", OH_MIDIDevice_CloseInputPort(device, input)); inputOpen = false; }
    if (device != nullptr) { Number(out, "close-device", OH_MIDIClient_CloseDevice(client, device)); device = nullptr; }
}
static bool Session(FILE *out, const std::string &run, const std::string &operation)
{
    fprintf(out, "{\"event\":\"identity\",\"schema\":\"usb579-real-midi-hotplug/v1\",\"run\":\"%s\",\"operation\":\"%s\",\"uid\":%u,\"euid\":%u,\"pid\":%u}\n",
        run.c_str(), operation.c_str(), static_cast<unsigned>(getuid()), static_cast<unsigned>(geteuid()), static_cast<unsigned>(getpid())); fflush(out);
    auto context = std::make_unique<Context>(); OH_MIDIClient *client = nullptr; OH_MIDIDevice *device = nullptr;
    uint32_t input = 0, output = 0; bool inputOpen = false, outputOpen = false, complete = false;
    int status = OH_MIDIClient_Create(&client, {Changed, Error}, context.get()); Number(out, "create", status);
    if (status != 0 || client == nullptr) return false;
    do {
        OH_MIDIDeviceInformation selected{}; bool present = false;
        if (!Catalog(out, client, selected, present) || present) break;
        Number(out, "actual-client-before-usb-attach", 1);
        if (!WaitDevice(out, *context, client, true, context->connected, selected)) break;
        const unsigned connected = context->connected, disconnected = context->disconnected;
        if (!Transfer(out, *context, client, run, selected, device, input, output, inputOpen, outputOpen)) break;
        Number(out, "actual-independent-midi-round", 1);
        if (!WaitDevice(out, *context, client, false, disconnected, selected)) break;
        uint32_t note = 0x20903c40U, written = 99; OH_MIDIEvent event = {0, 1, &note};
        status = OH_MIDIDevice_Send(device, output, &event, 1, &written);
        Number(out, "actual-stale-send-status", status); Number(out, "actual-stale-send-count", written);
        if (status == 0) break;
        Close(out, client, device, input, output, inputOpen, outputOpen);
        Number(out, "actual-waiting-for-usb-rebind", 1);
        if (!WaitDevice(out, *context, client, true, connected, selected)) break;
        if (!Transfer(out, *context, client, run, selected, device, input, output, inputOpen, outputOpen)) break;
        Number(out, "actual-independent-midi-round", 2);
        complete = true;
    } while (false);
    Close(out, client, device, input, output, inputOpen, outputOpen);
    status = OH_MIDIClient_Destroy(client); Number(out, "destroy", status);
    if (!Drain(out, *context)) complete = false;
    const size_t before = context->next.load(std::memory_order_acquire);
    std::this_thread::sleep_for(std::chrono::milliseconds(1500));
    const size_t after = context->next.load(std::memory_order_acquire);
    Number(out, "quiet-before", before); Number(out, "quiet-after", after);
    Number(out, "callback-error", context->error.load());
    complete = complete && status == 0 && before == after && context->error.load() == 0;
    Number(out, "end", complete ? 1 : 0);
    /* Callback storage remains readable until the original HAP exits. This is
     * a bounded one-session diagnostic quarantine, not a live client/port. */
    (void)context.release(); return complete;
}
} // namespace usb579midi
