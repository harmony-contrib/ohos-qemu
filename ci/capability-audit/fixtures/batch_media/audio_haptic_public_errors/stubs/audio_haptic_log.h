#pragma once
#include "host_prelude.h"
namespace OHOS { namespace HiviewDFX { struct HiLogLabel { int type; int domain; const char *tag; }; } }
constexpr int LOG_CORE = 0, LOG_DOMAIN_AUDIO_NAPI = 0;
namespace AudioHapticHostLog {
template<class... Args> inline void Consume(Args&&... values) { (static_cast<void>(values), ...); }
}
#define MEDIA_LOGI(...) ::AudioHapticHostLog::Consume(__VA_ARGS__)
#define MEDIA_LOGE(...) ::AudioHapticHostLog::Consume(__VA_ARGS__)
#define CHECK_AND_RETURN_LOG(condition, ...) do { if (!(condition)) return; } while (0)
#define CHECK_AND_BREAK_LOG(condition, ...) if (!(condition)) { break; }

#define CHECK_AND_RETURN_RET_LOG(condition, result, ...) do { if (!(condition)) return (result); } while (0)
