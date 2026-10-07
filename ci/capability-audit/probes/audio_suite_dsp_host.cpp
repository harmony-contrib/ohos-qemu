/* Real signal tests of current CPU DSP and pinned primary iMedia ABI. */
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string>
#include <vector>
#include "../../../patches/common/foundation/multimedia/audio_framework/audio_suite_dsp/files/qemu_audio_suite_dsp.cpp"

namespace {
int checks = 0;
int failures = 0;
std::string runId;

void Check(const char *name, bool pass, double actual = 0)
{
    ++checks;
    failures += !pass;
    std::printf("{\"run_id\":\"%s\",\"case\":\"%s\",\"pass\":%s,\"actual\":%.12g}\n",
        runId.c_str(), name, pass ? "true" : "false", actual);
}

struct Storage {
    iMedia_SWS_MEM_SIZE size {};
    std::unique_ptr<void, decltype(&std::free)> state {nullptr, &std::free};
    std::vector<unsigned char> scratch;
    Storage()
    {
        if (iMedia_Eq_GetSize(&size) != 0 || size.iStrSize <= 0 || size.iScracthSize <= 0) {
            std::exit(2);
        }
        state.reset(std::calloc(1, size.iStrSize));
        if (!state) {
            std::exit(2);
        }
        scratch.resize(size.iScracthSize);
    }
    void *Handle() { return state.get(); }
    void *Scratch() { return scratch.data(); }
    int Bytes() { return size.iScracthSize; }
};

short Pair(int left, int right)
{
    const uint16_t encoded = static_cast<uint16_t>((left << 8) | right);
    short value;
    std::memcpy(&value, &encoded, sizeof(value));
    return value;
}

iMedia_Eq_PARA Params(int band, int left, int right)
{
    iMedia_Eq_PARA params {};
    params.sFrameLen = 480;
    params.sEQLRBands = Pair(10, 10);
    for (int i = 0; i < 10; ++i) {
        params.sEQLRGain[i] = Pair(100, 100);
    }
    if (band >= 0) {
        params.sEQLRGain[band] = Pair(100 + left * 10, 100 + right * 10);
    }
    return params;
}

using ApplyFn = int (*)(void *, void *, int, iMedia_SWS_DATA *);

std::array<double, 2> Tone(Storage &storage, ApplyFn apply, double frequency, double amplitude)
{
    std::array<int32_t, 960> input {}, output {};
    iMedia_SWS_DATA data {input.data(), output.data(), 480, 1, 1, 15, 2, 0};
    std::array<double, 2> power {};
    int measured = 0;
    bool allFrames = true;
    for (int block = 0; block < 200; ++block) {
        for (int frame = 0; frame < 480; ++frame) {
            const double phase = 2 * 3.14159265358979323846 * frequency * (block * 480 + frame) / 48000;
            const int32_t sample = static_cast<int32_t>(amplitude * 2147483648.0 * std::sin(phase));
            input[frame * 2] = sample;
            input[frame * 2 + 1] = sample;
        }
        allFrames &= apply(storage.Handle(), storage.Scratch(), storage.Bytes(), &data) == 0;
        if (block >= 100) {
            for (int frame = 0; frame < 480; ++frame) {
                for (int channel = 0; channel < 2; ++channel) {
                    const double sample = output[frame * 2 + channel] / 2147483648.0;
                    power[channel] += sample * sample;
                }
                ++measured;
            }
        }
    }
    Check("all_real_signal_frames_processed", allFrames);
    for (double &value : power) {
        value = 20 * std::log10(std::sqrt(value / measured) / (amplitude / std::sqrt(2.0)));
    }
    return power;
}

void Equalizer()
{
    const double frequencies[10] = {31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000};
    for (int band = 0; band < 10; ++band) {
        Storage storage;
        auto params = Params(band, 6, -6);
        Check("eq_exact_ABI_init", iMedia_Eq_Init(storage.Handle(), storage.Scratch(), storage.Bytes(), &params) == 0);
        const auto gains = Tone(storage, iMedia_Eq_Apply, frequencies[band], 0.05);
        Check("eq_left_center_plus6dB", std::fabs(gains[0] - 6) < 0.08, gains[0]);
        Check("eq_right_center_minus6dB", std::fabs(gains[1] + 6) < 0.08, gains[1]);
        iMedia_Eq_PARA readback {};
        Check("eq_exact_parameter_roundtrip", iMedia_Eq_GetParams(storage.Handle(), &readback) == 0 &&
              std::memcmp(&params, &readback, sizeof(params)) == 0);
        params = Params(-1, 0, 0);
        Check("eq_dynamic_params", iMedia_Eq_SetParams(storage.Handle(), storage.Scratch(), storage.Bytes(), &params) == 0);
        const auto flat = Tone(storage, iMedia_Eq_Apply, frequencies[band], 0.05);
        Check("eq_dynamic_flat_actual_signal", std::fabs(flat[0]) < 0.02 && std::fabs(flat[1]) < 0.02, flat[0]);
    }
}

void Surround()
{
    Storage storage;
    std::array<int32_t, 962> input {}, output {};
    constexpr double widths[4] = {1.75, 0.5, 1, 2.25};
    input[0] = 268435456;
    input[1] = -268435456;
    output[960] = 12345;
    output[961] = 54321;
    iMedia_SWS_DATA data {input.data(), output.data(), 480, 1, 1, 15, 2, 0};
    for (int mode = 0; mode < 4; ++mode) {
        const auto selected = static_cast<iMedia_Surround_PARA>(mode);
        Check("surround_recreate", iMedia_Surround_Init(storage.Handle(), storage.Scratch(), storage.Bytes(), selected) == 0);
        Check("surround_actual_mid_side", iMedia_Surround_Apply(storage.Handle(), storage.Scratch(), storage.Bytes(), &data) == 0 &&
              output[0] == static_cast<int32_t>(input[0] * widths[mode]) && output[1] == -output[0],
              output[0] / static_cast<double>(input[0]));
        iMedia_Surround_PARA value {};
        Check("surround_mode_roundtrip", iMedia_Surround_GetParams(storage.Handle(), &value) == 0 && value == selected);
        Check("surround_canary", output[960] == 12345 && output[961] == 54321);
    }
    input[0] = INT32_MAX;
    input[1] = INT32_MIN;
    Check("surround_saturation_both_signs", iMedia_Surround_Apply(storage.Handle(), storage.Scratch(), storage.Bytes(), &data) == 0 &&
          output[0] == INT32_MAX && output[1] == INT32_MIN);
    data.iEnable_SWS = 0;
    Check("surround_disabled_fullscale_exact", iMedia_Surround_Apply(storage.Handle(), storage.Scratch(), storage.Bytes(), &data) == 0 &&
          output[0] == input[0] && output[1] == input[1]);
    data.iEnable_SWS = 1;
    data.piDataOut = input.data();
    Check("surround_inplace_safe", iMedia_Surround_Apply(storage.Handle(), storage.Scratch(), storage.Bytes(), &data) == 0 &&
          input[0] == INT32_MAX && input[1] == INT32_MIN);
}

void Environment()
{
    for (int mode = 0; mode < 4; ++mode) {
        Storage storage;
        const auto selected = static_cast<iMedia_Env_PARA>(mode);
        Check("environment_init", iMedia_Env_Init(storage.Handle(), storage.Scratch(), storage.Bytes(), selected) == 0);
        iMedia_Env_PARA value {};
        Check("environment_mode_roundtrip", iMedia_Env_GetParams(storage.Handle(), &value) == 0 && value == selected);
        const auto high = Tone(storage, iMedia_Env_Apply, 12000, 0.1);
        Check("environment_actual_high_frequency_attenuation", high[0] < -12 && high[1] < -12, high[0]);
        Check("environment_dynamic_mode", iMedia_Env_SetParams(storage.Handle(), storage.Scratch(), storage.Bytes(),
              IMEDIA_SWS_ENV_TELEPHONE_RECEIVER) == 0);
        const auto speech = Tone(storage, iMedia_Env_Apply, 1000, 0.1);
        Check("telephone_passband_actual_signal", speech[0] > -0.2 && speech[0] < 0 &&
              std::fabs(speech[0] - speech[1]) < 0.0001, speech[0]);
    }
}

void Boundaries()
{
    Storage storage;
    std::array<int32_t, 960> input {}, output {};
    output.fill(987654);
    iMedia_SWS_DATA data {input.data(), output.data(), 480, 1, 1, 15, 2, 0};
    Check("uninitialized_rejected", iMedia_Eq_Apply(storage.Handle(), storage.Scratch(), storage.Bytes(), &data) != 0);
    auto params = Params(-1, 0, 0);
    Check("boundary_valid_init", iMedia_Eq_Init(storage.Handle(), storage.Scratch(), storage.Bytes(), &params) == 0);
    params.sEQLRGain[0] = Pair(255, 100);
    Check("invalid_gain_rejected", iMedia_Eq_SetParams(storage.Handle(), storage.Scratch(), storage.Bytes(), &params) != 0);
    iMedia_Eq_PARA preserved {};
    Check("invalid_gain_preserves_params", iMedia_Eq_GetParams(storage.Handle(), &preserved) == 0 &&
          Packed(preserved.sEQLRGain[0], 0) == 100);
    Check("null_handle_rejected", iMedia_Eq_Apply(nullptr, storage.Scratch(), storage.Bytes(), &data) != 0);
    Check("short_scratch_rejected", iMedia_Eq_Apply(storage.Handle(), storage.Scratch(), storage.Bytes() - 1, &data) != 0);
    Check("wrong_kind_rejected", iMedia_Env_Apply(storage.Handle(), storage.Scratch(), storage.Bytes(), &data) != 0);
    Check("null_data_rejected", iMedia_Eq_Apply(storage.Handle(), storage.Scratch(), storage.Bytes(), nullptr) != 0);
    for (int size : {0, -1, 481, INT32_MAX}) {
        data.iSize = size;
        Check("bad_frame_size_rejected", iMedia_Eq_Apply(storage.Handle(), storage.Scratch(), storage.Bytes(), &data) != 0);
    }
    data.iSize = 480;
    data.iData_Channel = 1;
    Check("wrong_channels_rejected", iMedia_Eq_Apply(storage.Handle(), storage.Scratch(), storage.Bytes(), &data) != 0);
    data.iData_Channel = 2;
    data.iData_Format16 = 2;
    Check("wrong_format_rejected", iMedia_Eq_Apply(storage.Handle(), storage.Scratch(), storage.Bytes(), &data) != 0);
    data.iData_Format16 = 1;
    data.iEnable_SWS = 2;
    Check("wrong_enable_rejected", iMedia_Eq_Apply(storage.Handle(), storage.Scratch(), storage.Bytes(), &data) != 0);
    Check("all_rejections_preserve_output", std::all_of(output.begin(), output.end(), [](int32_t x) { return x == 987654; }));
    Check("null_sizes_rejected", iMedia_Eq_GetSize(nullptr) != 0 && iMedia_Env_GetSize(nullptr) != 0 &&
          iMedia_Surround_GetSize(nullptr) != 0);
    Check("null_readback_rejected", iMedia_Eq_GetParams(storage.Handle(), nullptr) != 0);
    Check("null_version_rejected", iMedia_Eq_GetVersion(nullptr) != 0);
}
}

int main(int argc, char **argv)
{
    if (argc != 2 || std::strlen(argv[1]) != 32 ||
        std::strspn(argv[1], "0123456789abcdef") != 32) {
        return 2;
    }
    runId = argv[1];
    for (auto getSpecs : {iMedia_Eq_GetSPECS, iMedia_Surround_GetSPECS, iMedia_Env_GetSPECS}) {
        const auto spec = getSpecs();
        Check("complete_actual_pipeline_format_specs", spec.isSupport && !spec.isRealTime &&
              spec.frameLen == 480 && spec.inSampleRate == 48000 && spec.outSampleRate == 48000 &&
              spec.inChannels == 2 && spec.outChannels == 2 && spec.inFormat == 1 && spec.outFormat == 1);
    }
    Equalizer();
    Surround();
    Environment();
    Boundaries();
    std::printf("{\"run_id\":\"%s\",\"case\":\"summary\",\"checks\":%d,\"failures\":%d,"
                "\"pass\":%s,\"scope\":\"host_real_DSP_not_guest\"}\n",
                runId.c_str(), checks, failures, failures == 0 ? "true" : "false");
    return failures == 0 ? 0 : 1;
}
