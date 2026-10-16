// Controlled inner Recorder scheduling/failure dependencies. Actual public config and function bodies below.
#include <multimedia/player_framework/avrecorder.h>
#include <algorithm>
#include <cassert>
#include <climits>
#include <cstdlib>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>
#include <iostream>
#define CHECK_AND_RETURN_RET_LOG(condition,result,...) do {if(!(condition))return result;} while(0)
#define MEDIA_LOGD(...)
#define MEDIA_LOGI(...)
#define MEDIA_LOGE(...)
constexpr int MSERR_OK=0,MSERR_PARAMETER_VERIFICATION_FAILED=-7;
constexpr float MIN_LATITUDE=-90,MAX_LATITUDE=90,MIN_LONGITUDE=-180,MAX_LONGITUDE=180;
using OutputFormatType=int;using AudioCodecFormat=int;using VideoCodecFormat=int;using AudioSourceType=int;using VideoSourceType=int;
enum class FileGenerationMode {APP_CREATE=0,AUTO_CREATE_CAMERA_SCENE=1};
static bool StrToInt(const std::string &s,int &out) {char *end=nullptr;long value=strtol(s.c_str(),&end,10);if(s.empty()||*end||value<INT_MIN||value>INT_MAX)return false;out=static_cast<int>(value);return true;}
struct OH_AVRecorder {};
struct Recorder {
 std::vector<std::string> calls;std::string failure;int Call(const std::string &name){calls.push_back(name);return failure==name?-91:0;}
#define METHOD(name,arguments) int name arguments {return Call(#name);}
 METHOD(SetOutputFormat,(OutputFormatType)) METHOD(SetAudioSource,(AudioSourceType,int&)) METHOD(SetVideoSource,(VideoSourceType,int&))
 METHOD(SetAudioEncoder,(int,AudioCodecFormat)) METHOD(SetAudioSampleRate,(int,int)) METHOD(SetAudioChannels,(int,int)) METHOD(SetAudioEncodingBitRate,(int,int))
 METHOD(SetVideoEncoder,(int,VideoCodecFormat)) METHOD(SetVideoSize,(int,int,int)) METHOD(SetVideoFrameRate,(int,int)) METHOD(SetVideoEncodingBitRate,(int,int))
 METHOD(SetVideoIsHdr,(int,bool)) METHOD(SetVideoEnableTemporalScale,(int,bool)) METHOD(SetMaxDuration,(int)) METHOD(SetGenre,(const std::string&))
 METHOD(SetFileGenerationMode,(FileGenerationMode)) METHOD(SetOutputFile,(int)) METHOD(Prepare,())
#undef METHOD
 void SetOrientationHint(int){Call("SetOrientationHint");} void SetLocation(float,float){Call("SetLocation");}
};
struct Callback {int prepared=0;void OnStateChange(OH_AVRecorder_State state,OH_AVRecorder_StateChangeReason reason){assert(state==AVRECORDER_PREPARED&&reason==AVRECORDER_USER);++prepared;}};
struct RecorderObject:OH_AVRecorder {
 std::shared_ptr<Recorder> recorder_=std::make_shared<Recorder>();std::shared_ptr<Callback> callback_=std::make_shared<Callback>();
 int audioSourceId_=-1,videoSourceId_=-1;bool withAudio_=true,withVideo_=true,hasConfigured_=false;
};
// ACTUAL_FUNCTIONS
static OH_AVRecorder_Config Config(bool audio=true,bool video=true,bool automatic=false)
{
 OH_AVRecorder_Config c{};c.audioSourceType=AVRECORDER_MIC;c.videoSourceType=AVRECORDER_SURFACE_YUV;
 c.profile.audioBitrate=audio?192000:0;c.profile.audioChannels=audio?2:0;c.profile.audioSampleRate=48000;c.profile.audioCodec=AVRECORDER_AUDIO_AAC;
 c.profile.fileFormat=AVRECORDER_CFT_MPEG_4;c.profile.videoFrameWidth=video?64:0;c.profile.videoFrameHeight=video?64:0;c.profile.videoFrameRate=30;
 c.profile.videoCodec=AVRECORDER_VIDEO_AVC;c.profile.videoBitrate=500000;c.url=const_cast<char*>("fd://7");c.metadata.genre=const_cast<char*>("external challenge");
 c.fileGenerationMode=automatic?AVRECORDER_AUTO_CREATE_CAMERA_SCENE:AVRECORDER_APP_CREATE;return c;
}
int main()
{
 const std::vector<std::string> failures={"SetAudioSource","SetVideoSource","SetOutputFormat","SetAudioEncoder","SetAudioSampleRate","SetAudioChannels","SetAudioEncodingBitRate","SetVideoEncoder","SetVideoSize","SetVideoFrameRate","SetVideoEncodingBitRate","SetVideoIsHdr","SetVideoEnableTemporalScale","SetMaxDuration","SetGenre","SetOutputFile","SetFileGenerationMode"};
 for(const auto &failure:failures) {
  RecorderObject o;auto c=Config(true,true,failure=="SetFileGenerationMode");o.recorder_->failure=failure;
  const auto r=OH_AVRecorder_Prepare(&o,&c);
#ifdef EXPECT_OLD
  if(failure=="SetAudioSource") {assert(r==AV_ERR_OK&&o.callback_->prepared==1&&o.recorder_->calls.back()=="Prepare");std::cout<<"old actual Configure failure reproduced as false prepared success\n";return 0;}
#else
  assert(r==AV_ERR_INVALID_VAL);assert(o.recorder_->calls.back()==failure);assert(!o.hasConfigured_&&o.callback_->prepared==0);
  assert(std::find(o.recorder_->calls.begin(),o.recorder_->calls.end(),"Prepare")==o.recorder_->calls.end());
#endif
 }
#ifndef EXPECT_OLD
 for(bool audio:{false,true})for(bool video:{false,true}) {if(!audio&&!video)continue;RecorderObject o;auto c=Config(audio,video);assert(OH_AVRecorder_Prepare(&o,&c)==AV_ERR_OK);assert(o.callback_->prepared==1&&o.hasConfigured_);assert(o.recorder_->calls.back()=="Prepare");assert(c.maxDuration==INT32_MAX);assert(o.withAudio_==audio&&o.withVideo_==video);}
 for(int variant=0;variant<7;++variant) {
  RecorderObject o;auto c=Config();
  if(variant==0)c.url=nullptr;if(variant==1)c.url=const_cast<char*>("");if(variant==2)c.url=const_cast<char*>("fd://-1");if(variant==3)c.url=const_cast<char*>("fd://bad");
  if(variant==4)c.metadata.videoOrientation=const_cast<char*>("45");if(variant==5)c.metadata.location.latitude=91;if(variant==6)c.metadata.location.longitude=181;
  assert(OH_AVRecorder_Prepare(&o,&c)==AV_ERR_INVALID_VAL);assert(!o.hasConfigured_&&o.callback_->prepared==0);assert(std::find(o.recorder_->calls.begin(),o.recorder_->calls.end(),"Prepare")==o.recorder_->calls.end());
 }
 RecorderObject o;auto c=Config();assert(OH_AVRecorder_Prepare(nullptr,&c)==AV_ERR_INVALID_VAL);assert(OH_AVRecorder_Prepare(&o,nullptr)==AV_ERR_INVALID_VAL);
 o.recorder_->failure="Prepare";assert(OH_AVRecorder_Prepare(&o,&c)==AV_ERR_INVALID_VAL);assert(o.callback_->prepared==0);
 o.recorder_.reset();assert(OH_AVRecorder_Prepare(&o,&c)==AV_ERR_INVALID_VAL);
 std::cout<<"actual SetProfile/ConfigureUrl/Configure/Prepare: 17 error steps, 3 source modes, invalid inputs, native Prepare failure passed\n";
#endif
}
