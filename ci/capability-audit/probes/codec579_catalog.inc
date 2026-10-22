// Actual public C API enumeration, kept separate from the original 968 AVC rows.
// Included by the existing AVC caller; no dlopen, fake codec, backend or callback.
#include <multimedia/player_framework/native_avcodec_audiocodec.h>

namespace codec579 {
static void Text(FILE *out, const char *value)
{
    fputc('"', out);
    if (value != nullptr) {
        for (size_t i = 0; value[i] != '\0' && i < 512; ++i) {
            const unsigned char c = static_cast<unsigned char>(value[i]);
            if (c == '"' || c == '\\') { fputc('\\', out); fputc(c, out); }
            else if (c < 32 || c > 126) fprintf(out, "\\u%04x", c);
            else fputc(c, out);
        }
    }
    fputc('"', out);
}

static OH_AVCodec *Create(const char *name, int kind)
{
    if (name == nullptr) return nullptr;
    if (kind == 0) return OH_VideoEncoder_CreateByName(name);
    if (kind == 1) return OH_VideoDecoder_CreateByName(name);
    return OH_AudioCodec_CreateByName(name);
}

static int Destroy(OH_AVCodec *codec, int kind)
{
    if (codec == nullptr) return -1;
    if (kind == 0) return OH_VideoEncoder_Destroy(codec);
    if (kind == 1) return OH_VideoDecoder_Destroy(codec);
    return OH_AudioCodec_Destroy(codec);
}

static bool Catalog(const char *run)
{
    const std::string path = std::string("/data/storage/el2/base/files/codec-base-") + run + "-catalog.jsonl";
    FILE *out = fopen(path.c_str(), "wx");
    if (out == nullptr) return false;
    bool complete = true;
    fprintf(out, "{\"type\":\"identity\",\"run_id\":\"%s\",\"uid\":%u,\"euid\":%u,\"pid\":%u}\n", run,
        static_cast<unsigned>(getuid()), static_cast<unsigned>(geteuid()), static_cast<unsigned>(getpid()));
    const OH_AVCodecType types[] = {OH_AVCODEC_TYPE_VIDEO_ENCODER, OH_AVCODEC_TYPE_VIDEO_DECODER,
        OH_AVCODEC_TYPE_AUDIO_ENCODER, OH_AVCODEC_TYPE_AUDIO_DECODER};
    const char *kinds[] = {"video-encoder", "video-decoder", "audio-encoder", "audio-decoder"};
    for (int kind = 0; kind < 4; ++kind) {
        uint32_t count = 0;
        OH_AVCapability **caps = OH_AVCodec_GetCapabilityList(types[kind], &count);
        fprintf(out, "{\"type\":\"list\",\"run_id\":\"%s\",\"kind\":\"%s\",\"count\":%u,\"present\":%s}\n",
            run, kinds[kind], count, caps != nullptr ? "true" : "false");
        if (caps == nullptr || count == 0 || count > 128) { complete = false; continue; }
        for (uint32_t i = 0; i < count; ++i) {
            const char *name = caps[i] == nullptr ? nullptr : OH_AVCapability_GetName(caps[i]);
            const char *mime = caps[i] == nullptr ? nullptr : OH_AVCapability_GetMimeType(caps[i]);
            const bool hardware = caps[i] != nullptr && OH_AVCapability_IsHardware(caps[i]);
            OH_AVCodec *codec = Create(name, kind);
            const bool created = codec != nullptr;
            const int destroyed = Destroy(codec, kind);
            fprintf(out, "{\"type\":\"codec\",\"run_id\":\"%s\",\"kind\":\"%s\",\"index\":%u,\"name\":", run, kinds[kind], i);
            Text(out, name); fputs(",\"mime\":", out); Text(out, mime);
            fprintf(out, ",\"hardware\":%s,\"created_by_name\":%s,\"destroy_result\":%d}\n",
                hardware ? "true" : "false", created ? "true" : "false", destroyed);
            complete = complete && name != nullptr && mime != nullptr && created && destroyed == 0;
        }
    }
    for (int kind = 0; kind < 2; ++kind) {
        OH_AVCapability *cap = OH_AVCodec_GetCapability(OH_AVCODEC_MIMETYPE_VIDEO_AVC, kind == 0);
        const char *name = cap == nullptr ? nullptr : OH_AVCapability_GetName(cap);
        const bool hardware = cap != nullptr && OH_AVCapability_IsHardware(cap);
        OH_AVCodec *codec = kind == 0 ? OH_VideoEncoder_CreateByMime(OH_AVCODEC_MIMETYPE_VIDEO_AVC) :
            OH_VideoDecoder_CreateByMime(OH_AVCODEC_MIMETYPE_VIDEO_AVC);
        const bool created = codec != nullptr;
        const int destroyed = Destroy(codec, kind);
        fprintf(out, "{\"type\":\"default\",\"run_id\":\"%s\",\"kind\":\"%s\",\"mime\":\"video/avc\",\"name\":", run, kinds[kind]);
        Text(out, name);
        fprintf(out, ",\"hardware\":%s,\"created_by_mime\":%s,\"destroy_result\":%d}\n",
            hardware ? "true" : "false", created ? "true" : "false", destroyed);
        complete = complete && name != nullptr && !hardware && created && destroyed == 0;
    }
    fprintf(out, "{\"type\":\"end\",\"run_id\":\"%s\",\"complete\":%s}\n", run, complete ? "true" : "false");
    const bool written = ferror(out) == 0 && fflush(out) == 0;
    return fclose(out) == 0 && written && complete;
}
} // namespace codec579
