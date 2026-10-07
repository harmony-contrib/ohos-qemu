// SPDX-License-Identifier: Apache-2.0
// Public AudioSuite engine -> installed DSP -> measured PCM, no private dlopen.
#include <ohaudiosuite/native_audio_suite_engine.h>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <memory>
#include <mutex>
#include <new>
#include <vector>
#include <unistd.h>

namespace {
struct Input {
    std::vector<int16_t> samples;
    std::mutex lock;
    size_t position = 0;
    std::atomic<unsigned> callbacks {0};
    std::atomic<unsigned> badCallbacks {0};
};

int32_t Read(OH_AudioNode *node, void *user, void *buffer, int32_t bytes, bool *finished)
{
    auto *input = static_cast<Input *>(user);
    if (input == nullptr) return 0;
    if (node == nullptr || buffer == nullptr || finished == nullptr || bytes <= 0 || bytes % 4 != 0) {
        input->badCallbacks.fetch_add(1);
        return 0;
    }
    std::lock_guard<std::mutex> guard(input->lock);
    const size_t total = input->samples.size() * sizeof(int16_t);
    const size_t remaining = total - input->position;
    const size_t copy = remaining < static_cast<size_t>(bytes) ? remaining : static_cast<size_t>(bytes);
    std::memcpy(buffer, reinterpret_cast<const unsigned char *>(input->samples.data()) + input->position, copy);
    input->position += copy;
    input->callbacks.fetch_add(1);
    *finished = input->position == total;
    return static_cast<int32_t>(copy);
}

bool Step(FILE *out, const char *run, int cycle, int test, const char *name, int actual, int expected = 0)
{
    const bool pass = actual == expected;
    std::fprintf(out, "{\"type\":\"step\",\"run_id\":\"%s\",\"cycle\":%d,\"test\":%d,"
        "\"name\":\"%s\",\"actual\":%d,\"expected\":%d,\"passed\":%s}\n",
        run, cycle, test, name, actual, expected, pass ? "true" : "false");
    std::fflush(out);
    return pass;
}

OH_AudioNode *Node(FILE *out, const char *run, int cycle, int test, OH_AudioSuitePipeline *pipeline,
    OH_AudioNode_Type type, Input *input, bool &pass)
{
    OH_AudioNodeBuilder *builder = nullptr;
    pass &= Step(out, run, cycle, test, "builder_create", OH_AudioSuiteNodeBuilder_Create(&builder));
    if (builder == nullptr) return nullptr;
    OH_AudioFormat format {};
    format.samplingRate = SAMPLE_RATE_48000;
    format.channelCount = 2;
    format.channelLayout = CH_LAYOUT_STEREO;
    format.encodingType = AUDIO_ENCODING_TYPE_RAW;
    format.sampleFormat = AUDIO_SAMPLE_S16LE;
    pass &= Step(out, run, cycle, test, "builder_type", OH_AudioSuiteNodeBuilder_SetNodeType(builder, type));
    // The public SDK allows formats only on input/output nodes. Setting a
    // format on an effect builder succeeds, but CreateNode must reject that
    // incompatible configuration; it is not a failed effect backend.
    if (type == INPUT_NODE_TYPE_DEFAULT || type == OUTPUT_NODE_TYPE_DEFAULT) {
        pass &= Step(out, run, cycle, test, "builder_format", OH_AudioSuiteNodeBuilder_SetFormat(builder, format));
    }
    if (input != nullptr) {
        pass &= Step(out, run, cycle, test, "input_callback",
            OH_AudioSuiteNodeBuilder_SetRequestDataCallback(builder, Read, input));
    }
    OH_AudioNode *node = nullptr;
    pass &= Step(out, run, cycle, test, "node_create", OH_AudioSuiteEngine_CreateNode(pipeline, builder, &node));
    pass &= Step(out, run, cycle, test, "builder_destroy", OH_AudioSuiteNodeBuilder_Destroy(builder));
    return node;
}

bool Configure(FILE *out, const char *run, int cycle, int test, OH_AudioNode *effect)
{
    bool pass = true;
    if (test < 10) {
        OH_EqualizerFrequencyBandGains gains {};
        gains.gains[test] = 6;
        pass &= Step(out, run, cycle, test, "eq_set", OH_AudioSuiteEngine_SetEqualizerFrequencyBandGains(effect, gains));
        OH_EqualizerFrequencyBandGains readback {};
        pass &= Step(out, run, cycle, test, "eq_get", OH_AudioSuiteEngine_GetEqualizerFrequencyBandGains(effect, &readback));
        pass &= Step(out, run, cycle, test, "eq_params", std::memcmp(&gains, &readback, sizeof(gains)) == 0 ? 0 : -1);
        gains.gains[test] = 11;
        pass &= Step(out, run, cycle, test, "eq_invalid_gain",
            OH_AudioSuiteEngine_SetEqualizerFrequencyBandGains(effect, gains), AUDIOSUITE_ERROR_INVALID_PARAM);
        readback = {};
        pass &= Step(out, run, cycle, test, "eq_get_after_reject", OH_AudioSuiteEngine_GetEqualizerFrequencyBandGains(effect, &readback));
        pass &= Step(out, run, cycle, test, "eq_reject_preserves_gain", readback.gains[test], 6);
    } else if (test < 14) {
        const auto mode = static_cast<OH_SoundFieldType>(test - 9);
        pass &= Step(out, run, cycle, test, "field_set", OH_AudioSuiteEngine_SetSoundFieldType(effect, mode));
        OH_SoundFieldType readback {};
        pass &= Step(out, run, cycle, test, "field_get", OH_AudioSuiteEngine_GetSoundFieldType(effect, &readback));
        pass &= Step(out, run, cycle, test, "field_params", readback, mode);
    } else {
        const auto mode = static_cast<OH_EnvironmentType>(test - 13);
        pass &= Step(out, run, cycle, test, "environment_set", OH_AudioSuiteEngine_SetEnvironmentType(effect, mode));
        OH_EnvironmentType readback {};
        pass &= Step(out, run, cycle, test, "environment_get", OH_AudioSuiteEngine_GetEnvironmentType(effect, &readback));
        pass &= Step(out, run, cycle, test, "environment_params", readback, mode);
    }
    return pass;
}

bool Pipeline(FILE *out, const char *run, int cycle, int test, double phase)
{
    const OH_AudioNode_Type type = test < 10 ? EFFECT_NODE_TYPE_EQUALIZER :
        test < 14 ? EFFECT_NODE_TYPE_SOUND_FIELD : EFFECT_NODE_TYPE_ENVIRONMENT_EFFECT;
    bool supported = false;
    bool pass = Step(out, run, cycle, test, "is_supported", OH_AudioSuiteEngine_IsNodeTypeSupported(type, &supported));
    pass &= Step(out, run, cycle, test, "supported_value", supported ? 1 : 0, 1);
    OH_AudioSuiteEngine *engine = nullptr;
    pass &= Step(out, run, cycle, test, "engine_create", OH_AudioSuiteEngine_Create(&engine));
    if (engine == nullptr) return false;
    OH_AudioSuitePipeline *pipeline = nullptr;
    pass &= Step(out, run, cycle, test, "pipeline_create",
        OH_AudioSuiteEngine_CreatePipeline(engine, &pipeline, AUDIOSUITE_PIPELINE_EDIT_MODE));
    if (pipeline == nullptr) {
        Step(out, run, cycle, test, "engine_destroy", OH_AudioSuiteEngine_Destroy(engine));
        return false;
    }
    // Once attached, callback storage is retained until successful node
    // destruction, including exception/failure paths of the test itself.
    std::unique_ptr<Input> owned(new (std::nothrow) Input);
    if (!owned) return false;
    Input *input = owned.get();
    input->samples.resize(192000); // two seconds, stereo.
    constexpr double frequencies[10] = {31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000};
    const double frequency = test < 10 ? frequencies[test] : test < 14 ? 1000 : 12000;
    for (size_t frame = 0; frame < input->samples.size() / 2; ++frame) {
        const int16_t sample = static_cast<int16_t>(2000 * std::sin(phase +
            2 * 3.14159265358979323846 * frequency * frame / 48000));
        input->samples[frame * 2] = sample;
        input->samples[frame * 2 + 1] = test >= 10 && test < 14 ? -sample : sample;
    }
    std::vector<int16_t> output(input->samples.size() + 1920, 0);
    OH_AudioNode *source = Node(out, run, cycle, test, pipeline, INPUT_NODE_TYPE_DEFAULT, input, pass);
    if (source != nullptr) owned.release();
    OH_AudioNode *effect = Node(out, run, cycle, test, pipeline, type, nullptr, pass);
    OH_AudioNode *destination = Node(out, run, cycle, test, pipeline, OUTPUT_NODE_TYPE_DEFAULT, nullptr, pass);
    if (source == nullptr || effect == nullptr || destination == nullptr) {
        Step(out, run, cycle, test, "pipeline_destroy_after_create_failure", OH_AudioSuiteEngine_DestroyPipeline(pipeline));
        Step(out, run, cycle, test, "engine_destroy", OH_AudioSuiteEngine_Destroy(engine));
        return false;
    }
    pass &= Configure(out, run, cycle, test, effect);
    pass &= Step(out, run, cycle, test, "connect_source", OH_AudioSuiteEngine_ConnectNodes(source, effect));
    pass &= Step(out, run, cycle, test, "connect_destination", OH_AudioSuiteEngine_ConnectNodes(effect, destination));
    int32_t response = -1;
    bool finished = false;
    pass &= Step(out, run, cycle, test, "render_before_start",
        OH_AudioSuiteEngine_RenderFrame(pipeline, output.data(), 1920, &response, &finished), AUDIOSUITE_ERROR_INVALID_STATE);
    const auto started = OH_AudioSuiteEngine_StartPipeline(pipeline);
    pass &= Step(out, run, cycle, test, "pipeline_start", started);
    size_t bytes = 0;
    bool renders = started == AUDIOSUITE_SUCCESS;
    for (int block = 0; renders && !finished && block < 210; ++block) {
        if (bytes + 1920 > output.size() * 2) { renders = false; break; }
        response = -1;
        const auto result = OH_AudioSuiteEngine_RenderFrame(pipeline,
            reinterpret_cast<unsigned char *>(output.data()) + bytes, 1920, &response, &finished);
        if (result != 0 || response < 0 || response > 1920 || response % 4 != 0 || (response == 0 && !finished)) {
            renders = false;
            break;
        }
        bytes += static_cast<size_t>(response);
    }
    size_t consumed;
    {
        std::lock_guard<std::mutex> guard(input->lock);
        consumed = input->position;
    }
    bool signal = renders && finished && consumed == input->samples.size() * 2 &&
        bytes >= input->samples.size() * 2 && input->callbacks.load() > 0 && input->badCallbacks.load() == 0;
    double before[2] {}, after[2] {};
    for (size_t frame = 48000; frame < 96000; ++frame) {
        for (int channel = 0; channel < 2; ++channel) {
            const double original = input->samples[frame * 2 + channel];
            const double actual = output[frame * 2 + channel];
            before[channel] += original * original;
            after[channel] += actual * actual;
        }
    }
    double gain[2] {};
    for (int channel = 0; channel < 2; ++channel) {
        gain[channel] = before[channel] > 0 && after[channel] > 0 ? 10 * std::log10(after[channel] / before[channel]) : -999;
        if (test < 10) signal &= std::fabs(gain[channel] - 6) < .15;
        else if (test < 14) {
            constexpr double widths[4] = {.5, 2.25, 1, 1.75};
            signal &= std::fabs(gain[channel] - 20 * std::log10(widths[test - 10])) < .15;
        } else signal &= gain[channel] < -12 && gain[channel] > -100;
    }
    std::fprintf(out, "{\"type\":\"signal\",\"run_id\":\"%s\",\"cycle\":%d,\"test\":%d,"
        "\"frequency\":%.0f,\"phase\":%.12g,\"input_bytes\":%zu,\"consumed_bytes\":%zu,\"output_bytes\":%zu,"
        "\"callbacks\":%u,\"bad_callbacks\":%u,\"finished\":%s,"
        "\"left_input_energy\":%.17g,\"right_input_energy\":%.17g,"
        "\"left_output_energy\":%.17g,\"right_output_energy\":%.17g,"
        "\"left_dB\":%.9g,\"right_dB\":%.9g,\"passed\":%s}\n",
        run, cycle, test, frequency, phase, input->samples.size() * 2, consumed, bytes,
        input->callbacks.load(), input->badCallbacks.load(), finished ? "true" : "false",
        before[0], before[1], after[0], after[1], gain[0], gain[1], signal ? "true" : "false");
    std::fflush(out);
    pass &= signal;
    pass &= Step(out, run, cycle, test, "pipeline_stop", OH_AudioSuiteEngine_StopPipeline(pipeline));
    pass &= Step(out, run, cycle, test, "disconnect_source", OH_AudioSuiteEngine_DisconnectNodes(source, effect));
    pass &= Step(out, run, cycle, test, "disconnect_destination", OH_AudioSuiteEngine_DisconnectNodes(effect, destination));
    const auto destroyedSource = OH_AudioSuiteEngine_DestroyNode(source);
    pass &= Step(out, run, cycle, test, "destroy_source", destroyedSource);
    if (destroyedSource == 0) delete input;
    pass &= Step(out, run, cycle, test, "destroy_effect", OH_AudioSuiteEngine_DestroyNode(effect));
    pass &= Step(out, run, cycle, test, "destroy_destination", OH_AudioSuiteEngine_DestroyNode(destination));
    pass &= Step(out, run, cycle, test, "pipeline_destroy", OH_AudioSuiteEngine_DestroyPipeline(pipeline));
    pass &= Step(out, run, cycle, test, "engine_destroy", OH_AudioSuiteEngine_Destroy(engine));
    return pass;
}
}

extern "C" int RunAudioSuiteEffectsProbe(FILE *out, const char *run)
{
    std::fprintf(out, "{\"type\":\"identity\",\"run_id\":\"%s\",\"uid\":%u,\"euid\":%u}\n",
        run, static_cast<unsigned>(getuid()), static_cast<unsigned>(geteuid()));
    unsigned seed = 0;
    for (int i = 0; i < 8; ++i) seed = seed * 16 + (run[i] <= '9' ? run[i] - '0' : run[i] - 'a' + 10);
    const double phase = (seed % 10000) / 10000.0;
    bool pass = Step(out, run, 0, -1, "null_create", OH_AudioSuiteEngine_Create(nullptr), AUDIOSUITE_ERROR_INVALID_PARAM);
    int pipelines = 0;
    for (int cycle = 1; cycle <= 2; ++cycle) {
        for (int test = 0; test < 18; ++test) {
            const bool actual = Pipeline(out, run, cycle, test, phase);
            pass &= actual;
            pipelines += actual;
        }
    }
    std::fprintf(out, "{\"type\":\"summary\",\"run_id\":\"%s\",\"cycles\":2,\"pipelines\":%d,"
        "\"passed\":%s,\"scope\":\"public_AudioSuite_three_DSP_effects_not_AI_or_download\"}\n",
        run, pipelines, pass ? "true" : "false");
    return pass ? 0 : 1;
}
