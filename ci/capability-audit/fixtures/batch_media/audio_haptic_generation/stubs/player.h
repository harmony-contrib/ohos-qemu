#pragma once
#include "host_prelude.h"
#include "media_errors.h"
namespace OHOS { namespace Media {
enum PlayerOnInfoType { INFO_TYPE_STATE_CHANGE,INFO_TYPE_INTERRUPT_EVENT,INFO_TYPE_AUDIO_FIRST_FRAME,INFO_TYPE_EOS };
enum PlayerStates { PLAYER_STATE_ERROR=-1,PLAYER_IDLE=0,PLAYER_INITIALIZED,PLAYER_PREPARING,PLAYER_PREPARED,
 PLAYER_STARTED,PLAYER_PAUSED,PLAYER_STOPPED,PLAYER_PLAYBACK_COMPLETE };
struct PlayerKeys { static constexpr const char *CONTENT_TYPE="content",*STREAM_USAGE="usage",*RENDERER_FLAG="flag",
 *PLAYER_AUDIO_HAPTICS_SYNC_ID="sync",*AUDIO_FIRST_FRAME="latency",*AUDIO_INTERRUPT_TYPE="interrupt",
 *AUDIO_INTERRUPT_FORCE="force",*AUDIO_INTERRUPT_HINT="hint"; };
class Format { public:
 void PutIntValue(const std::string &key,int value){values[key]=value;}
 void PutLongValue(const std::string &key,int64_t value){values[key]=value;}
 bool GetIntValue(const std::string &key,int &out)const{int64_t val=0;if(!GetLongValue(key,val))return false;out=int(val);return true;}
 bool GetLongValue(const std::string &key,int64_t &out)const{auto p=values.find(key);if(p==values.end())return false;out=p->second;return true;}
 std::map<std::string,int64_t> values;
};
class PlayerCallback { public: virtual ~PlayerCallback()=default;virtual void OnError(int,const std::string&)=0;
 virtual void OnInfo(PlayerOnInfoType,int,const Format&)=0; };
// Controlled dependency surface only. The component's class declarations and both CPPs are real.
class Player { public: virtual ~Player()=default; virtual int SetPlayerCallback(const std::shared_ptr<PlayerCallback>&)=0;
 virtual int Reset()=0;virtual int SetSource(int,int64_t,int64_t)=0;virtual int SetParameter(const Format&)=0;
 virtual int PrepareAsync()=0;virtual int Play()=0;virtual int Stop()=0;virtual int Release()=0;
 virtual int SetVolume(float,float)=0;virtual int SetLooping(bool)=0;virtual int GetCurrentTime(int&)=0;
};
class PlayerFactory { public: static std::shared_ptr<Player> CreatePlayer(); };
} }
