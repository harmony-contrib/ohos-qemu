/* SPDX-License-Identifier: Apache-2.0
 * Real upstream AudioSuite PCM pipeline, not just create/destroy or ABI presence.
 * Algorithm plug-ins, cloud download and realtime device nodes need separate tests.
 */
#include <ohaudiosuite/native_audio_suite_engine.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define REQUIRE(condition) do { if (!(condition)) { \
    fprintf(stderr, "failed line %d: %s\n", __LINE__, #condition); exit(1); \
} } while (0)
#define SUITE_OK(call) REQUIRE((call) == AUDIOSUITE_SUCCESS)

template <typename T> static T resolve(void *library, const char *name)
{
    void *symbol = dlsym(library, name);
    if (!symbol) {
        fprintf(stderr, "missing AudioSuite export %s: %s\n", name, dlerror());
        exit(1);
    }
    return reinterpret_cast<T>(symbol);
}

struct Input {
    int16_t samples[1920]; // 20 ms, 48 kHz, two channels.
    size_t position;
    unsigned callbacks;
};

static int32_t request_data(OH_AudioNode *node, void *user, void *data, int32_t size, bool *finished)
{
    REQUIRE(node && user && data && size > 0 && finished);
    Input *input = static_cast<Input *>(user);
    const size_t remaining = sizeof(input->samples) - input->position;
    const size_t copy = remaining < static_cast<size_t>(size) ? remaining : static_cast<size_t>(size);
    memcpy(data, reinterpret_cast<const uint8_t *>(input->samples) + input->position, copy);
    input->position += copy;
    input->callbacks++;
    *finished = input->position == sizeof(input->samples);
    return static_cast<int32_t>(copy);
}

int main()
{
    // dlsym allows the probe to report a stub library instead of dying in the
    // dynamic linker before any diagnostic is printed.
    void *library = dlopen("libohaudiosuite.so", RTLD_NOW | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "AudioSuite load failed: %s\n", dlerror()); return 1; }
#define LOAD(name) auto fn_##name = resolve<decltype(&::name)>(library, #name)
    LOAD(OH_AudioSuiteEngine_Create);
    LOAD(OH_AudioSuiteEngine_Destroy);
    LOAD(OH_AudioSuiteEngine_CreatePipeline);
    LOAD(OH_AudioSuiteEngine_DestroyPipeline);
    LOAD(OH_AudioSuiteEngine_StartPipeline);
    LOAD(OH_AudioSuiteEngine_StopPipeline);
    LOAD(OH_AudioSuiteEngine_GetPipelineState);
    LOAD(OH_AudioSuiteEngine_RenderFrame);
    LOAD(OH_AudioSuiteEngine_CreateNode);
    LOAD(OH_AudioSuiteEngine_DestroyNode);
    LOAD(OH_AudioSuiteEngine_ConnectNodes);
    LOAD(OH_AudioSuiteEngine_DisconnectNodes);
    LOAD(OH_AudioSuiteNodeBuilder_Create);
    LOAD(OH_AudioSuiteNodeBuilder_Destroy);
    LOAD(OH_AudioSuiteNodeBuilder_SetNodeType);
    LOAD(OH_AudioSuiteNodeBuilder_SetFormat);
    LOAD(OH_AudioSuiteNodeBuilder_SetRequestDataCallback);
#undef LOAD
    REQUIRE(fn_OH_AudioSuiteEngine_Create(nullptr) == AUDIOSUITE_ERROR_INVALID_PARAM);
    unsigned total_callbacks = 0;
    for (int cycle = 0; cycle < 2; ++cycle) {
        OH_AudioSuiteEngine *engine = nullptr;
        SUITE_OK(fn_OH_AudioSuiteEngine_Create(&engine));
        REQUIRE(engine);
        OH_AudioSuitePipeline *pipeline = nullptr;
        SUITE_OK(fn_OH_AudioSuiteEngine_CreatePipeline(engine, &pipeline, AUDIOSUITE_PIPELINE_EDIT_MODE));
        REQUIRE(pipeline);
        Input input = {};
        for (size_t i = 0; i < 1920; i += 2) {
            input.samples[i] = static_cast<int16_t>(1000 + (i / 2) % 1000);
            input.samples[i + 1] = static_cast<int16_t>(-input.samples[i]);
        }
        OH_AudioFormat format = {};
        format.samplingRate = SAMPLE_RATE_48000;
        format.channelCount = 2;
        format.channelLayout = CH_LAYOUT_STEREO;
        format.encodingType = AUDIO_ENCODING_TYPE_RAW;
        format.sampleFormat = AUDIO_SAMPLE_S16LE;
        auto make_node = [&](OH_AudioNode_Type type) {
            OH_AudioNodeBuilder *builder = nullptr;
            SUITE_OK(fn_OH_AudioSuiteNodeBuilder_Create(&builder));
            SUITE_OK(fn_OH_AudioSuiteNodeBuilder_SetNodeType(builder, type));
            SUITE_OK(fn_OH_AudioSuiteNodeBuilder_SetFormat(builder, format));
            if (type == INPUT_NODE_TYPE_DEFAULT) {
                SUITE_OK(fn_OH_AudioSuiteNodeBuilder_SetRequestDataCallback(builder, request_data, &input));
            }
            OH_AudioNode *node = nullptr;
            SUITE_OK(fn_OH_AudioSuiteEngine_CreateNode(pipeline, builder, &node));
            REQUIRE(node);
            SUITE_OK(fn_OH_AudioSuiteNodeBuilder_Destroy(builder));
            return node;
        };
        OH_AudioNode *source = make_node(INPUT_NODE_TYPE_DEFAULT);
        OH_AudioNode *destination = make_node(OUTPUT_NODE_TYPE_DEFAULT);
        SUITE_OK(fn_OH_AudioSuiteEngine_ConnectNodes(source, destination));
        int16_t output[4096] = {};
        int32_t response = 0;
        bool finished = false;
        REQUIRE(fn_OH_AudioSuiteEngine_RenderFrame(pipeline, output, 1024, &response, &finished)
                == AUDIOSUITE_ERROR_INVALID_STATE);
        SUITE_OK(fn_OH_AudioSuiteEngine_StartPipeline(pipeline));
        OH_AudioSuite_PipelineState state;
        SUITE_OK(fn_OH_AudioSuiteEngine_GetPipelineState(pipeline, &state));
        REQUIRE(state == AUDIOSUITE_PIPELINE_RUNNING);
        size_t bytes = 0;
        for (int frame = 0; frame < 32 && !finished; ++frame) {
            REQUIRE(bytes + 1024 <= sizeof(output));
            response = -1;
            SUITE_OK(fn_OH_AudioSuiteEngine_RenderFrame(pipeline,
                reinterpret_cast<uint8_t *>(output) + bytes, 1024, &response, &finished));
            REQUIRE(response >= 0 && response <= 1024 && response % 4 == 0);
            REQUIRE(response > 0 || finished);
            bytes += static_cast<size_t>(response);
        }
        REQUIRE(finished && bytes >= sizeof(input.samples) && input.position == sizeof(input.samples));
        REQUIRE(input.callbacks > 0);
        for (size_t i = 0; i < 1920; ++i) REQUIRE(abs(output[i] - input.samples[i]) <= 1);
        // Frame rounding may append silence, but never unknown tail samples.
        for (size_t i = 1920; i < bytes / 2; ++i) REQUIRE(abs(output[i]) <= 1);
        total_callbacks += input.callbacks;
        SUITE_OK(fn_OH_AudioSuiteEngine_StopPipeline(pipeline));
        finished = false;
        REQUIRE(fn_OH_AudioSuiteEngine_RenderFrame(pipeline, output, 1024, &response, &finished)
                == AUDIOSUITE_ERROR_INVALID_STATE);
        SUITE_OK(fn_OH_AudioSuiteEngine_DisconnectNodes(source, destination));
        SUITE_OK(fn_OH_AudioSuiteEngine_DestroyNode(source));
        SUITE_OK(fn_OH_AudioSuiteEngine_DestroyNode(destination));
        SUITE_OK(fn_OH_AudioSuiteEngine_DestroyPipeline(pipeline));
        SUITE_OK(fn_OH_AudioSuiteEngine_Destroy(engine));
    }
    printf("{\"scope\":\"AudioSuite PCM passthrough, not algorithm plugins/download\","
           "\"cycles\":2,\"verified_samples\":3840,\"input_callbacks\":%u,"
           "\"invalid_state_boundary\":true,\"pass\":true}\n", total_callbacks);
    // Retain the library until process exit: upstream worker lifetime is not
    // part of this probe's plugin unloading contract.
    return 0;
}
