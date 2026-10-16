#include <assert.h>
#include <alloca.h>
#include <errno.h>
#ifndef EBADFD
#define EBADFD 77
#endif
#ifndef ESTRPIPE
#define ESTRPIPE 86
#endif
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#define HDF_SUCCESS 0
#define HDF_FAILURE -1
#define HDF_ERR_NOT_SUPPORT -2
#define HDF_ERR_DEVICE_BUSY -3
#define EOK 0
#define CHECK_NULL_PTR_RETURN_DEFAULT(p) do {if((p)==NULL)return HDF_FAILURE;}while(0)
#define AUDIO_FUNC_LOGE(...)
#define AUDIO_FUNC_LOGI(...)
#define MAX_CARD_NAME_LEN 64
#define MAX_CARD_NUM 32
#define AUDIO_MAX_CARD_NUM 8
#define MIXER_CTL_MAX_NUM 64
#define AUDIO_ALSALIB_RETYR 3
#define ALSA_CAP_BUFFER_SIZE 24000
#define PRIMARY "primary"
#define HDMI "hdmi"
#define USB "usb"
#define A2DP "a2dp"
#define SND_PCM_STREAM_CAPTURE 1
#define SND_PCM_STREAM_PLAYBACK 0
#define SND_PCM_NONBLOCK 1
#define SND_PCM_STATE_OPEN 0
#define SND_PCM_STATE_PREPARED 2
#define SND_PCM_STATE_RUNNING 3
#define SND_PCM_STATE_SETUP 1
#define SND_PCM_ACCESS_RW_INTERLEAVED 0
#define SND_NUMID_DACL_CAPTURE_VOL 1
#define SND_NUMID_DACR_CAPTURE_VOL 2
#define SND_NUMID_CAPUTRE_MIC_PATH 3
#define SND_ELEM_DACL_CAPTURE_VOL "left"
#define SND_ELEM_DACR_CAPTURE_VOL "right"
#define SND_ELEM_CAPUTRE_MIC_PATH "mic"
#define SND_IN_CARD_MAIN_MIC "main"
#define SND_IN_CARD_MIC_OFF "off"
typedef int snd_pcm_stream_t;
typedef unsigned long snd_pcm_uframes_t;
typedef long snd_pcm_sframes_t;
typedef struct {int state;} snd_pcm_t;
typedef struct {int card;} snd_ctl_t;
typedef struct {const char *id;} snd_ctl_card_info_t;
typedef struct {unsigned int device,subdevice;int stream;} snd_pcm_info_t;
enum SndCardType {SND_CARD_UNKNOWN=-1,SND_CARD_PRIMARY,SND_CARD_HDMI,SND_CARD_USB,SND_CARD_BT,SND_CARD_MAX};
struct AlsaSoundCard {enum SndCardType cardType;char adapterName[65],devName[65],alsaCardId[65],ctrlName[65];snd_pcm_t *pcmHandle;bool mmapFlag,pauseState;};
struct AlsaMixerCtlElement {int numid;const char *name;const char *value;};
struct AudioHwCaptureParam {struct {struct {struct {int pins;} deviceDescript;} hwInfo;} captureMode;};
typedef void *CapturePriData;
struct AlsaCapture {struct AlsaSoundCard soundCard;void *priData;int descPins;bool muteState;
 int32_t(*Init)(struct AlsaCapture*);int32_t(*SelectScene)(struct AlsaCapture*,const struct AudioHwCaptureParam*);
 int32_t(*Start)(struct AlsaCapture*,const struct AudioHwCaptureParam*);int32_t(*Stop)(struct AlsaCapture*);
 int32_t(*GetVolThreshold)(struct AlsaCapture*,long*,long*);int32_t(*GetVolume)(struct AlsaCapture*,long*);
 int32_t(*SetVolume)(struct AlsaCapture*,long);int32_t(*SetMute)(struct AlsaCapture*,bool);bool(*GetMute)(struct AlsaCapture*);
 int32_t(*GetGainThreshold)(struct AlsaCapture*,float*,float*);int32_t(*GetGain)(struct AlsaCapture*,float*);int32_t(*SetGain)(struct AlsaCapture*,float);
};
enum AudioCategory {AUDIO_CATEGORY_MEDIA};
static int closeCalls,ctlCalls,mixerCalls,prepareCalls,startCalls,dropCalls,waitCalls;
static int ctlOpenResult,cardInfoResult,pcmInfoResult,prepareResult,startResult,dropResult,waitResult,recoverResult;
static const char *actualCardId="QemuCapture";
static long readValues[16];static int readCount,readIndex;
static snd_ctl_t fakeCtl;
static snd_pcm_t fakePcm;
static int snprintf_s(char *dst,size_t cap,size_t max,const char *fmt,...){(void)max;va_list ap;va_start(ap,fmt);int n=vsnprintf(dst,cap,fmt,ap);va_end(ap);return n<0||(size_t)n>=cap?-1:n;}
static int strcpy_s(char *dst,size_t cap,const char *s){if(!s||strlen(s)>=cap)return -1;memcpy(dst,s,strlen(s)+1);return 0;}
static int strncpy_s(char *dst,size_t cap,const char *s,size_t n){if(!s||strlen(s)>n||strlen(s)>=cap)return -1;return strcpy_s(dst,cap,s);}
#define snd_ctl_card_info_alloca(p) do {*(p)=alloca(sizeof(snd_ctl_card_info_t));memset(*(p),0,sizeof(snd_ctl_card_info_t));}while(0)
#define snd_pcm_info_alloca(p) do {*(p)=alloca(sizeof(snd_pcm_info_t));memset(*(p),0,sizeof(snd_pcm_info_t));}while(0)
static int snd_ctl_open(snd_ctl_t **p,const char *name,int mode){(void)mode;++ctlCalls;assert(strcmp(name,"hw:1")==0);if(ctlOpenResult<0)return ctlOpenResult;fakeCtl.card=1;*p=&fakeCtl;return 0;}
static int snd_ctl_card_info(snd_ctl_t *c,snd_ctl_card_info_t *i){assert(c->card==1);i->id=actualCardId;return cardInfoResult;}
static const char *snd_ctl_card_info_get_id(snd_ctl_card_info_t *i){return i->id;}
static void snd_pcm_info_set_device(snd_pcm_info_t *i,unsigned int n){i->device=n;}
static void snd_pcm_info_set_subdevice(snd_pcm_info_t *i,unsigned int n){i->subdevice=n;}
static void snd_pcm_info_set_stream(snd_pcm_info_t *i,int n){i->stream=n;}
static int snd_ctl_pcm_info(snd_ctl_t *c,snd_pcm_info_t *i){assert(c->card==1);assert(i->device==0&&i->subdevice==0&&i->stream==SND_PCM_STREAM_CAPTURE);return pcmInfoResult;}
static int snd_ctl_close(snd_ctl_t *c){assert(c);++closeCalls;return 0;}
static int snd_pcm_state(snd_pcm_t *p){return p->state;}
static int snd_pcm_prepare(snd_pcm_t *p){++prepareCalls;if(prepareResult<0)return prepareResult;if(p->state==SND_PCM_STATE_OPEN)return -EBADFD;p->state=SND_PCM_STATE_PREPARED;return 0;}
static int snd_pcm_start(snd_pcm_t *p){++startCalls;if(startResult<0)return startResult;p->state=SND_PCM_STATE_RUNNING;return 0;}
static int snd_pcm_drop(snd_pcm_t *p){++dropCalls;if(dropResult<0)return dropResult;p->state=SND_PCM_STATE_SETUP;return 0;}
static long snd_pcm_readi(snd_pcm_t *p,void *data,snd_pcm_uframes_t count){(void)p;(void)data;(void)count;assert(readIndex<readCount);return readValues[readIndex++];}
static int snd_pcm_wait(snd_pcm_t *p,int ms){(void)p;assert(ms==100);++waitCalls;return waitResult;}
static int snd_pcm_recover(snd_pcm_t *p,int n,int silent){(void)p;(void)n;(void)silent;return recoverResult;}
static void *OsalMemCalloc(size_t n){return calloc(1,n);}
static void SndElementItemInit(struct AlsaMixerCtlElement *m){memset(m,0,sizeof(*m));}
static void *CaptureGetPriData(struct AlsaCapture *c){return c?c->priData:NULL;}
static void CaptureSetPriData(struct AlsaCapture *c,void *p){c->priData=p;}
static int SndElementReadRange(struct AlsaSoundCard*c,const struct AlsaMixerCtlElement*m,long*a,long*b){(void)c;(void)m;(void)a;(void)b;++mixerCalls;return -1;}
static int SndElementReadInt(struct AlsaSoundCard*c,const struct AlsaMixerCtlElement*m,long*a){(void)c;(void)m;(void)a;++mixerCalls;return -1;}
static int SndElementWriteInt(struct AlsaSoundCard*c,const struct AlsaMixerCtlElement*m,long n){(void)c;(void)m;(void)n;++mixerCalls;return -1;}
static int SndElementWrite(struct AlsaSoundCard*c,const struct AlsaMixerCtlElement*m){(void)c;(void)m;++mixerCalls;return -1;}
static int SndisBusy(struct AlsaSoundCard*c){(void)c;return 0;}
static void SndCloseHandle(struct AlsaSoundCard*c){(void)c;}
static void CaptureFreeMemory(void){}
static const char *snd_strerror(int n){(void)n;return "actual error";}
static int snd_pcm_open(snd_pcm_t **p,const char *name,int stream,int mode){(void)name;assert(stream==SND_PCM_STREAM_CAPTURE&&mode==SND_PCM_NONBLOCK);*p=&fakePcm;return 0;}
static int snd_pcm_nonblock(snd_pcm_t *p,int flag){(void)p;assert(flag==1);return 0;}
static int SndOpenMixer(struct AlsaSoundCard*c){(void)c;++mixerCalls;return -1;}
static int ResetCaptureParams(struct AlsaSoundCard*c,int n){(void)c;(void)n;return -1;}

static long frameBytes=4;
static snd_pcm_sframes_t snd_pcm_frames_to_bytes(snd_pcm_t*p,snd_pcm_sframes_t frames){(void)p;return frameBytes*frames;}
