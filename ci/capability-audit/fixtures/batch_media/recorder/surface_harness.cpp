// Controlled native-window allocation; executes actual producer copy/validation functions only.
#include <multimedia/player_framework/avrecorder.h>
#include <native_buffer/native_buffer.h>
#include <native_window/external_window.h>
#include <algorithm>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <cstdarg>
#include <fcntl.h>
#include <poll.h>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>
#include <iostream>
struct NativeWindow{};struct NativeWindowBuffer{};struct OH_NativeBuffer{};
static NativeWindow window;static NativeWindowBuffer native;static OH_NativeBuffer buffer;
static OH_NativeBuffer_Config config{};static BufferHandle handle{};static int fault=0,aborts=0,unmaps=0,flushes=0;static uint64_t stamp=0;
static std::vector<uint8_t> memory;
int32_t OH_NativeWindow_NativeWindowHandleOpt(OHNativeWindow*,int operation,...){assert(operation==SET_UI_TIMESTAMP);va_list args;va_start(args,operation);stamp=va_arg(args,uint64_t);va_end(args);return fault==1?-1:0;}
int32_t OH_NativeWindow_NativeWindowRequestBuffer(OHNativeWindow*,OHNativeWindowBuffer **out,int *fence){*out=fault==2?nullptr:&native;*fence=-1;return fault==3?-1:0;}
int32_t OH_NativeWindow_NativeWindowAbortBuffer(OHNativeWindow*,OHNativeWindowBuffer*){++aborts;return 0;}
int32_t OH_NativeBuffer_FromNativeWindowBuffer(OHNativeWindowBuffer*,OH_NativeBuffer **out){*out=&buffer;return fault==4?-1:0;}
void OH_NativeBuffer_GetConfig(OH_NativeBuffer*,OH_NativeBuffer_Config *out){*out=config;}
BufferHandle *OH_NativeWindow_GetBufferHandleFromNative(OHNativeWindowBuffer*){return fault==5?nullptr:&handle;}
int32_t OH_NativeBuffer_Map(OH_NativeBuffer*,void **out){*out=fault==7?nullptr:memory.data();return fault==6?-1:0;}
int32_t OH_NativeBuffer_Unmap(OH_NativeBuffer*){++unmaps;return fault==8?-1:0;}
int32_t OH_NativeWindow_NativeWindowFlushBuffer(OHNativeWindow*,OHNativeWindowBuffer*,int fence,Region region){assert(fence==-1&&region.rectNumber==1);++flushes;return fault==9?-1:0;}
static std::string challengePath;
static int TestOpen(const char *path,int flags){assert(std::string(path)=="/data/storage/el2/base/files/recorder-0123456789abcdef0123456789abcdef-video.bin");return ::open(challengePath.c_str(),flags);}
// ACTUAL_CONSTANTS
#define open TestOpen
// ACTUAL_FUNCTIONS
#undef open
static void Reset(){fault=0;aborts=unmaps=flushes=0;config.width=64;config.height=64;config.stride=272;config.format=NATIVEBUFFER_PIXEL_FMT_RGBA_8888;handle.size=config.stride*64;memory.assign(handle.size,0x5a);}
int main(int argc,char **argv)
{
 assert(argc==2);challengePath=argv[1];assert(FPS==30);std::vector<uint8_t> input;
 assert(ReadChallenge("0123456789abcdef0123456789abcdef",input));assert(input.size()==7680);
 assert(chmod(challengePath.c_str(),0644)==0);assert(!ReadChallenge("0123456789abcdef0123456789abcdef",input));assert(chmod(challengePath.c_str(),0600)==0);
 uint8_t tiles[64];for(int i=0;i<64;++i)tiles[i]=48+i%14*12;
 Reset();assert(Surface(&window,tiles,2026101612345678));assert(stamp==2026101612345678ULL&&flushes==1&&aborts==0&&unmaps==1);
 for(int y=0;y<64;++y){for(int x=0;x<64;++x){size_t at=y*config.stride+x*4;for(int c=0;c<3;++c)assert(memory[at+c]==tiles[(y/8)*8+x/8]);assert(memory[at+3]==255);}for(int x=256;x<config.stride;++x)assert(memory[y*config.stride+x]==0x5a);}
 Reset();handle.size-=1;assert(!Surface(&window,tiles,1)&&aborts==1&&unmaps==0);
 for(int value:{0,63,255,16385}){Reset();config.stride=value;assert(!Surface(&window,tiles,1)&&aborts==1&&flushes==0);}
 for(int value:{0,63,65}){Reset();config.width=value;assert(!Surface(&window,tiles,1)&&aborts==1);}
 for(int value:{0,63,65}){Reset();config.height=value;assert(!Surface(&window,tiles,1)&&aborts==1);}
 for(int fail=1;fail<=9;++fail){Reset();fault=fail;assert(!Surface(&window,tiles,1));assert(aborts==(fail==1||fail==2?0:1));}
 Reset();assert(!Surface(nullptr,tiles,1));assert(!Surface(&window,tiles,-1));
 std::cout<<"actual recorder surface tiles/stride/last byte and rejection/abort/unmap + private challenge bounds passed\n";
}
