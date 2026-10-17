// HDI -> actual AudioOutputCaptureRead -> actual ALSA ReadImpl -> actual copy.
// Only the external PCM/lib, allocation and logging are controlled dependencies.
static struct AlsaCapture routeCapture;
static struct AlsaCapture *CaptureGetInstance(const char *name){assert(strcmp(name,"primary")==0);return &routeCapture;}
static int32_t CheckPcmStatus(snd_pcm_t *p){(void)p;return 0;}
// ACTUAL_LOWER_METHODS
static int Bridge(void *handle,struct AudioHwCaptureParam *p,int command){
 if(command==AUDIO_DRV_PCM_IOCTL_READ)return AudioOutputCaptureRead((const struct DevHandle*)handle,command,p);
 if(command==AUDIO_DRV_PCM_IOCTRL_STOP_CAPTURE){routeCapture.soundCard.mmapFlag=false;fakePcm.state=SND_PCM_STATE_SETUP;return 0;}
 return -1;
}
// ACTUAL_HDI_METHODS
static void Pattern(long first,long second,long third){readValues[0]=first;readValues[1]=second;readValues[2]=third;readIndex=0;readCount=3;}
static void AssertPattern(const unsigned char *p,size_t frames,uint64_t first){for(size_t f=0;f<frames;++f)for(size_t b=0;b<4;++b)assert(p[f*4+b]==(unsigned char)((first+f)>>(b*8)));}
int main(void){
 struct AudioHwCapture h={0};pthread_mutex_init(&h.captureParam.frameCaptureMode.mutex,NULL);
 h.devDataHandle=&routeCapture;h.captureParam.frameCaptureMode.buffer=calloc(1,FRAME_DATA);
 h.captureParam.frameCaptureMode.attrs.sampleRate=48000;h.captureParam.frameCaptureMode.attrs.channelCount=2;h.captureParam.frameCaptureMode.attrs.format=2;
 strcpy(h.captureParam.captureMode.hwInfo.adapterName,"primary");
 routeCapture.soundCard.pcmHandle=&fakePcm;strcpy(routeCapture.soundCard.alsaCardId,"QemuCapture");routeCapture.soundCard.mmapFlag=true;routeCapture.Read=CaptureReadImpl;fakePcm.state=SND_PCM_STATE_RUNNING;
 libraryCapture=Bridge;waitResult=1;
 unsigned char output[FRAME_DATA+16];uint32_t capacity=8192;uint64_t reply=99;memset(output,0xA5,sizeof(output));Pattern(2048,0,0);
 assert(AudioCaptureCaptureFrame(&h.capture,(int8_t*)output,&capacity,&reply)==0);assert(reply==8192&&requestedFrames==2048&&capacity==8192);AssertPattern(output,2048,0);for(size_t n=8192;n<sizeof(output);++n)assert(output[n]==0xA5);
 // A short real read is returned as such; the remaining frames are not padded or discarded.
 memset(output,0xA5,sizeof(output));Pattern(127,0,0);assert(AudioCaptureCaptureFrame(&h.capture,(int8_t*)output,&capacity,&reply)==0);assert(reply==508);AssertPattern(output,127,2048);assert(output[508]==0xA5);
 capacity=1031;Pattern(257,0,0);assert(AudioCaptureCaptureFrame(&h.capture,(int8_t*)output,&capacity,&reply)==0);assert(requestedFrames==257&&reply==1028);AssertPattern(output,257,2175);
 uint64_t frames=h.captureParam.frameCaptureMode.frames;struct AudioTimeStamp timestamp=h.captureParam.frameCaptureMode.time;
 // Invalid capacity, no frame, backend error, overreport and post-read timestamp/copy errors publish no bytes/clock.
 capacity=3;Pattern(1,0,0);assert(AudioCaptureCaptureFrame(&h.capture,(int8_t*)output,&capacity,&reply)<0&&reply==0&&readIndex==0);
 capacity=8192;
 long cases[][3]={{0,0,0},{-EIO,0,0},{2049,0,0}};
 for(size_t n=0;n<3;++n){Pattern(cases[n][0],cases[n][1],cases[n][2]);reply=99;assert(AudioCaptureCaptureFrame(&h.capture,(int8_t*)output,&capacity,&reply)<0&&reply==0);assert(h.captureParam.frameCaptureMode.frames==frames);assert(memcmp(&timestamp,&h.captureParam.frameCaptureMode.time,sizeof(timestamp))==0);}
 Pattern(8,0,0);timestampResult=-1;assert(AudioCaptureCaptureFrame(&h.capture,(int8_t*)output,&capacity,&reply)<0&&reply==0);timestampResult=0;
 Pattern(8,0,0);copyResult=-1;assert(AudioCaptureCaptureFrame(&h.capture,(int8_t*)output,&capacity,&reply)<0&&reply==0);copyResult=0;
 assert(h.captureParam.frameCaptureMode.frames==frames&&memcmp(&timestamp,&h.captureParam.frameCaptureMode.time,sizeof(timestamp))==0);
 allocFail=1;Pattern(8,0,0);assert(AudioCaptureCaptureFrame(&h.capture,(int8_t*)output,&capacity,&reply)<0&&reply==0&&readIndex==0);allocFail=0;
 assert(AudioCaptureCaptureFrame(NULL,(int8_t*)output,&capacity,&reply)==AUDIO_ERR_INVALID_PARAM&&reply==0);
 assert(AudioCaptureCaptureFrame(&h.capture,NULL,&capacity,&reply)==AUDIO_ERR_INVALID_PARAM&&reply==0);
 assert(AudioCaptureCaptureFrame(&h.capture,(int8_t*)output,&capacity,NULL)==AUDIO_ERR_INVALID_PARAM);
 capacity=0;assert(AudioCaptureCaptureFrame(&h.capture,(int8_t*)output,&capacity,&reply)==AUDIO_ERR_INVALID_PARAM&&reply==0);
 // The actual Stop frees the shared HDI buffer. A late Read must unlock on the error branch.
 assert(AudioCaptureStop(&h.capture)==0);capacity=8192;reply=99;
 assert(AudioCaptureCaptureFrame(&h.capture,(int8_t*)output,&capacity,&reply)==AUDIO_ERR_INVALID_PARAM&&reply==0);
 assert(pthread_mutex_trylock(&h.captureParam.frameCaptureMode.mutex)==0);pthread_mutex_unlock(&h.captureParam.frameCaptureMode.mutex);
 pthread_mutex_destroy(&h.captureParam.frameCaptureMode.mutex);
 puts("actual HDI/ALSA chain: capacity8192 vs period4096, real short reads, no padding/overflow/stale output, stopped-read unlock");
}
