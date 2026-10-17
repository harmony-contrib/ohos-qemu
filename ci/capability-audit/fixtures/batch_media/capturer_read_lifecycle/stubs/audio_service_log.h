#pragma once
#define AUDIO_ERR_LOG(...)
#define AUDIO_WARNING_LOG(...)
#define AUDIO_DEBUG_LOG(...)
#define AUDIO_INFO_LOG(...)
#define CHECK_AND_RETURN_RET_LOG(c,r,...) do { if (!(c)) return (r); } while (0)
