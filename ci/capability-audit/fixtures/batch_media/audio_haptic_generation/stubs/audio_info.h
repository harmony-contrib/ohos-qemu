#pragma once
#include "host_prelude.h"
namespace OHOS { namespace AudioStandard {
enum StreamUsage { STREAM_USAGE_UNKNOWN=0, STREAM_USAGE_MEDIA=1, STREAM_USAGE_RINGTONE=6,
 STREAM_USAGE_VOICE_RINGTONE=20, STREAM_USAGE_VOICE_TRANSFER_RINGTONE=26 };
enum InterruptType { INTERRUPT_TYPE_BEGIN=1, INTERRUPT_TYPE_END=2 };
enum InterruptForceType { INTERRUPT_FORCE=1 };
enum InterruptHint { INTERRUPT_HINT_STOP=1 };
struct InterruptEvent { InterruptType eventType{}; InterruptForceType forceType{}; InterruptHint hintType{}; };
constexpr int CONTENT_TYPE_UNKNOWN=0, AUDIO_FLAG_NORMAL=0, AUDIO_FLAG_VKB_ALL_RING=1;
} }
