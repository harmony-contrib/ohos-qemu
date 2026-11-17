/*
 * Copyright (c) 2026 harmony-contrib
 * Licensed under the Apache License, Version 2.0.
 *
 * Real CPU DSP for the pinned AudioSuite iMedia ABI, not a vendor algorithm
 * emulation. Biquad coefficients follow the mathematical definitions in
 * https://www.w3.org/TR/2021/NOTE-audio-eq-cookbook-20210608/ .
 */
#include <cstdint>
#include <cmath>
#include <cstring>
#include <limits>
#include <new>
#include "imedia_api.h"

namespace {
constexpr uint32_t kMagic = 0x51534450;
constexpr int kEq = 1;
constexpr int kSurround = 2;
constexpr int kEnvironment = 3;
constexpr int kBands = 10;
constexpr int kChannels = 2;
constexpr int kScratchBytes = 64;
constexpr int kFrameSamples = 480;
constexpr uint32_t kPcmS16Le = 1; // Fixed audio_stream_info.h SAMPLE_S16LE.
constexpr double kSampleRate = 48000.0;
constexpr double kPi = 3.14159265358979323846;
constexpr double kFullScale = 2147483648.0;
constexpr double kFrequencies[kBands] = {31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000};

struct Biquad {
    double b0 = 1, b1 = 0, b2 = 0, a1 = 0, a2 = 0;
    double z1 = 0, z2 = 0;

    double Process(double input)
    {
        const double output = b0 * input + z1;
        z1 = b1 * input - a1 * output + z2;
        z2 = b2 * input - a2 * output;
        return output;
    }
};

struct State {
    uint32_t magic = kMagic;
    int kind = 0;
    int mode = 0;
    iMedia_Eq_PARA equalizer {};
    Biquad filters[kChannels][kBands] {};
};

bool Aligned(void *handle)
{
    return handle != nullptr && reinterpret_cast<uintptr_t>(handle) % alignof(State) == 0;
}

State *GetState(void *handle, int kind)
{
    if (!Aligned(handle)) {
        return nullptr;
    }
    uint32_t magic = 0;
    std::memcpy(&magic, handle, sizeof(magic));
    if (magic != kMagic) {
        return nullptr;
    }
    auto *state = static_cast<State *>(handle);
    return state->kind == kind ? state : nullptr;
}

bool ScratchValid(void *scratch, int bytes)
{
    return scratch != nullptr && bytes >= kScratchBytes;
}

int GetSize(iMedia_SWS_MEM_SIZE *size)
{
    if (size == nullptr) {
        return -1;
    }
    *size = {};
    size->iStrSize = sizeof(State);
    size->iScracthSize = kScratchBytes;
    return 0;
}

iMedia_Support_SPECS GetSpecs()
{
    // The wrapper converts these S16LE pipeline frames to/from Q31 words.
    // Describe only the actual implemented editing format; no hard realtime
    // or absent AI/other-format support is advertised.
    return {true, false, kFrameSamples, static_cast<uint32_t>(kSampleRate), kChannels, kPcmS16Le,
            static_cast<uint32_t>(kSampleRate), kChannels, kPcmS16Le};
}

Biquad Peak(double frequency, double gain)
{
    const double w = 2 * kPi * frequency / kSampleRate;
    const double amplitude = std::pow(10.0, gain / 40.0);
    const double alpha = std::sin(w) / (2 * std::sqrt(2.0));
    const double a0 = 1 + alpha / amplitude;
    Biquad filter;
    filter.b0 = (1 + alpha * amplitude) / a0;
    filter.b1 = -2 * std::cos(w) / a0;
    filter.b2 = (1 - alpha * amplitude) / a0;
    filter.a1 = filter.b1;
    filter.a2 = (1 - alpha / amplitude) / a0;
    return filter;
}

Biquad Cut(double frequency, bool highPass)
{
    const double w = 2 * kPi * frequency / kSampleRate;
    const double cosine = std::cos(w);
    const double alpha = std::sin(w) / std::sqrt(2.0);
    const double a0 = 1 + alpha;
    const double edge = highPass ? 1 + cosine : 1 - cosine;
    Biquad filter;
    filter.b0 = edge / (2 * a0);
    filter.b1 = (highPass ? -edge : edge) / a0;
    filter.b2 = filter.b0;
    filter.a1 = -2 * cosine / a0;
    filter.a2 = (1 - alpha) / a0;
    return filter;
}

unsigned Packed(short value, int channel)
{
    return (static_cast<uint16_t>(value) >> (channel == 0 ? 8 : 0)) & 0xff;
}

bool EqValid(const iMedia_Eq_PARA *params)
{
    if (params == nullptr || params->sFrameLen != kFrameSamples) {
        return false;
    }
    for (int channel = 0; channel < kChannels; ++channel) {
        if (Packed(params->sEQLRBands, channel) != kBands) {
            return false;
        }
        for (int band = 0; band < kBands; ++band) {
            if (Packed(params->sEQLRGain[band], channel) > 200 ||
                Packed(params->sEQLRType[band], channel) != 0) {
                return false;
            }
        }
    }
    return true;
}

void ConfigureEq(State &state, const iMedia_Eq_PARA &params)
{
    state.equalizer = params;
    for (int channel = 0; channel < kChannels; ++channel) {
        for (int band = 0; band < kBands; ++band) {
            const double gain = (static_cast<int>(Packed(params.sEQLRGain[band], channel)) - 100) / 10.0;
            state.filters[channel][band] = Peak(kFrequencies[band], gain);
        }
    }
}

void ConfigureEnvironment(State &state, int mode)
{
    state.mode = mode;
    for (int channel = 0; channel < kChannels; ++channel) {
        state.filters[channel][0] = Biquad {};
        state.filters[channel][1] = Biquad {};
        if (mode == IMEDIA_SWS_ENV_UNDER_WATER) {
            state.filters[channel][1] = Cut(500, false);
        } else {
            state.filters[channel][0] = Cut(mode == IMEDIA_SWS_ENV_PHONOGRAPH ? 250 : 300, true);
            const double cutoff = mode == IMEDIA_SWS_ENV_BROADCAST ? 6000 :
                mode == IMEDIA_SWS_ENV_TELEPHONE_RECEIVER ? 3400 : 4500;
            state.filters[channel][1] = Cut(cutoff, false);
        }
    }
}

bool DataValid(const iMedia_SWS_DATA *data)
{
    return data != nullptr && data->piDataIn != nullptr && data->piDataOut != nullptr &&
        data->iSize > 0 && data->iSize <= kFrameSamples && data->iData_Channel == kChannels &&
        data->iData_Format16 == 1 && data->iMasterVolume == 15 &&
        (data->iEnable_SWS == 0 || data->iEnable_SWS == 1);
}

int32_t Saturate(double value)
{
    const double scaled = value * kFullScale;
    if (scaled >= std::numeric_limits<int32_t>::max()) {
        return std::numeric_limits<int32_t>::max();
    }
    if (scaled <= std::numeric_limits<int32_t>::min()) {
        return std::numeric_limits<int32_t>::min();
    }
    return static_cast<int32_t>(std::llround(scaled));
}

int Apply(void *handle, void *scratch, int bytes, iMedia_SWS_DATA *data, int kind)
{
    State *state = GetState(handle, kind);
    if (state == nullptr || !ScratchValid(scratch, bytes) || !DataValid(data)) {
        return -1;
    }
    constexpr double widths[4] = {1.75, 0.5, 1.0, 2.25};
    for (int frame = 0; frame < data->iSize; ++frame) {
        double samples[kChannels] = {data->piDataIn[frame * 2] / kFullScale,
                                    data->piDataIn[frame * 2 + 1] / kFullScale};
        if (data->iEnable_SWS == 1) {
            if (kind == kSurround) {
                const double mid = (samples[0] + samples[1]) / 2;
                const double side = (samples[0] - samples[1]) / 2 * widths[state->mode];
                samples[0] = mid + side;
                samples[1] = mid - side;
            } else {
                const int filters = kind == kEq ? kBands : 2;
                for (int channel = 0; channel < kChannels; ++channel) {
                    for (int band = 0; band < filters; ++band) {
                        samples[channel] = state->filters[channel][band].Process(samples[channel]);
                    }
                    if (kind == kEnvironment && state->mode == IMEDIA_SWS_ENV_PHONOGRAPH) {
                        samples[channel] = std::tanh(2 * samples[channel]) / 2;
                    }
                }
            }
        }
        if (!std::isfinite(samples[0]) || !std::isfinite(samples[1])) {
            return -1;
        }
        data->piDataOut[frame * 2] = Saturate(samples[0]);
        data->piDataOut[frame * 2 + 1] = Saturate(samples[1]);
    }
    return 0;
}
} // namespace

extern "C" {
iMedia_Support_SPECS iMedia_Eq_GetSPECS() { return GetSpecs(); }
iMedia_Support_SPECS iMedia_Surround_GetSPECS() { return GetSpecs(); }
iMedia_Support_SPECS iMedia_Env_GetSPECS() { return GetSpecs(); }
int iMedia_Eq_GetSize(iMedia_SWS_MEM_SIZE *size) { return GetSize(size); }
int iMedia_Surround_GetSize(iMedia_SWS_MEM_SIZE *size) { return GetSize(size); }
int iMedia_Env_GetSize(iMedia_SWS_MEM_SIZE *size) { return GetSize(size); }

int iMedia_Eq_Init(void *handle, void *scratch, int bytes, const iMedia_Eq_PARA *params)
{
    if (!Aligned(handle) || !ScratchValid(scratch, bytes) || !EqValid(params)) {
        return -1;
    }
    const iMedia_Eq_PARA copy = *params;
    State *state = new (handle) State {};
    state->kind = kEq;
    ConfigureEq(*state, copy);
    return 0;
}

int iMedia_Eq_SetParams(void *handle, void *scratch, int bytes, const iMedia_Eq_PARA *params)
{
    State *state = GetState(handle, kEq);
    if (state == nullptr || !ScratchValid(scratch, bytes) || !EqValid(params)) {
        return -1;
    }
    ConfigureEq(*state, *params);
    return 0;
}

int iMedia_Eq_GetParams(void *handle, iMedia_Eq_PARA *params)
{
    State *state = GetState(handle, kEq);
    if (state == nullptr || params == nullptr) {
        return -1;
    }
    *params = state->equalizer;
    return 0;
}

int iMedia_Eq_GetVersion(iMedia_SWS_PST_VERSION *version)
{
    static iMedia_SWS_STRU_VERSION value = {{}, {'Q', 'E', 'M', 'U', ' ', 'C', 'P', 'U', ' ', 'D', 'S', 'P', ' ', '1'}, {}};
    if (version == nullptr) {
        return -1;
    }
    *version = &value;
    return 0;
}

int iMedia_Surround_Init(void *handle, void *scratch, int bytes, iMedia_Surround_PARA mode)
{
    if (!Aligned(handle) || !ScratchValid(scratch, bytes) || mode < 0 || mode > 3) {
        return -1;
    }
    State *state = new (handle) State {};
    state->kind = kSurround;
    state->mode = mode;
    return 0;
}

int iMedia_Surround_SetParams(void *handle, void *scratch, int bytes, iMedia_Surround_PARA mode)
{
    State *state = GetState(handle, kSurround);
    if (state == nullptr || !ScratchValid(scratch, bytes) || mode < 0 || mode > 3) {
        return -1;
    }
    state->mode = mode;
    return 0;
}

int iMedia_Surround_GetParams(void *handle, iMedia_Surround_PARA *mode)
{
    State *state = GetState(handle, kSurround);
    if (state == nullptr || mode == nullptr) {
        return -1;
    }
    *mode = static_cast<iMedia_Surround_PARA>(state->mode);
    return 0;
}

int iMedia_Env_Init(void *handle, void *scratch, int bytes, iMedia_Env_PARA mode)
{
    if (!Aligned(handle) || !ScratchValid(scratch, bytes) || mode < 0 || mode >= IMEDIA_SWS_ENV_TYPE_NUM) {
        return -1;
    }
    State *state = new (handle) State {};
    state->kind = kEnvironment;
    ConfigureEnvironment(*state, mode);
    return 0;
}

int iMedia_Env_SetParams(void *handle, void *scratch, int bytes, iMedia_Env_PARA mode)
{
    State *state = GetState(handle, kEnvironment);
    if (state == nullptr || !ScratchValid(scratch, bytes) || mode < 0 || mode >= IMEDIA_SWS_ENV_TYPE_NUM) {
        return -1;
    }
    ConfigureEnvironment(*state, mode);
    return 0;
}

int iMedia_Env_GetParams(void *handle, iMedia_Env_PARA *mode)
{
    State *state = GetState(handle, kEnvironment);
    if (state == nullptr || mode == nullptr) {
        return -1;
    }
    *mode = static_cast<iMedia_Env_PARA>(state->mode);
    return 0;
}

int iMedia_Eq_Apply(void *handle, void *scratch, int bytes, iMedia_SWS_DATA *data)
{
    return Apply(handle, scratch, bytes, data, kEq);
}
int iMedia_Surround_Apply(void *handle, void *scratch, int bytes, iMedia_SWS_DATA *data)
{
    return Apply(handle, scratch, bytes, data, kSurround);
}
int iMedia_Env_Apply(void *handle, void *scratch, int bytes, iMedia_SWS_DATA *data)
{
    return Apply(handle, scratch, bytes, data, kEnvironment);
}
}
