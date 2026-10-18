#pragma once
#include "host_prelude.h"
namespace OHOS { namespace HiviewDFX { struct HiLogLabel { int type; int domain; const char *tag; }; } }
constexpr int LOG_CORE = 0, LOG_DOMAIN_AUDIO_NAPI = 0;
#define MEDIA_LOGI(...) ((void)0)
#define MEDIA_LOGE(...) ((void)0)
#define CHECK_AND_RETURN_LOG(condition, ...) do { if (!(condition)) return; } while (0)
#define CHECK_AND_BREAK_LOG(condition, ...) if (!(condition)) { break; }
