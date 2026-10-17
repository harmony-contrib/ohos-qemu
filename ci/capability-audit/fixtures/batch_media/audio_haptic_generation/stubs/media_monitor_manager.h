#pragma once
#include "host_prelude.h"
namespace OHOS { namespace Media { namespace MediaMonitor {
enum class ModuleId { AUDIO }; enum class EventId { HAPTIC_PLAYER }; enum class EventType { HAPTIC_PLAYER_EVENT };
struct EventBean { EventBean(ModuleId,EventId,EventType){} template<class T> void Add(const char *,T){} };
class MediaMonitorManager { public: static MediaMonitorManager &GetInstance(){static MediaMonitorManager x;return x;}
 void WriteLogMsg(const std::shared_ptr<EventBean>&){} };
} } }
