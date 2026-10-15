#include <cassert>
#include <climits>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <memory>
#include <algorithm>
#include <vector>
#include <mutex>
#include <condition_variable>
#include <chrono>
#include <thread>
#define AVCODEC_LOGE(...) ((void)0)
#define AVCODEC_LOGD(...) ((void)0)
#define AVCODEC_LOGI(...) ((void)0)
#define SCOPED_TRACE_AVC(...) ((void)0)
#define CHECK_AND_RETURN_RET_LOG(c,r,...) do { if (!(c)) return (r); } while (0)
#define CHECK_AND_RETURN_LOG(c,...) do { if (!(c)) return; } while (0)
constexpr int AVCS_ERR_OK=0, AVCS_ERR_INVALID_DATA=-1, AVCS_ERR_UNSUPPORT_SOURCE=-2;
constexpr int AVCS_ERR_NO_MEMORY=-3, AVCS_ERR_INVALID_VAL=-4, AVCS_ERR_UNKNOWN=-5;
constexpr int VIDEO_MIN_SIZE=64, VIDEO_MAX_WIDTH_SIZE=2560, VIDEO_MAX_HEIGHT_SIZE=2560;
constexpr int EVEN_NUMBER_DIVISOR=2, RGBA_COLINC=4, GSERROR_OK=0, EOK=0;
constexpr int INDEX_INPUT=0, DEFAULT_TRY_ENCODE_TIME=1, DEFAULT_ENCODE_WAIT_TIME=1;
constexpr int AVCODEC_BUFFER_FLAG_EOS=1;
using GSError=int;
template<class T> using sptr=std::shared_ptr<T>;
enum class VideoPixelFormat {UNKNOWN, RGBA, YUVI420, NV12, NV21};
enum class GraphicPixelFormat {GRAPHIC_PIXEL_FMT_YCBCR_420_P, GRAPHIC_PIXEL_FMT_RGBA_8888,
    GRAPHIC_PIXEL_FMT_YCBCR_P010, GRAPHIC_PIXEL_FMT_YCBCR_420_SP, GRAPHIC_PIXEL_FMT_YCRCB_P010,
    GRAPHIC_PIXEL_FMT_YCRCB_420_SP, UNKNOWN};
struct OH_NativeBuffer_Plane { uint64_t offset=0; uint32_t rowStride=0, columnStride=0; };
struct OH_NativeBuffer_Planes { uint32_t planeCount=0; OH_NativeBuffer_Plane planes[4]; };
struct SurfaceBuffer {
    int width=64, height=64, stride=64;
    uint32_t size=6144;
    GraphicPixelFormat format=GraphicPixelFormat::GRAPHIC_PIXEL_FMT_YCBCR_420_SP;
    std::vector<uint8_t> bytes=std::vector<uint8_t>(6144,0);
    OH_NativeBuffer_Planes planes{};
    int planeResult=-1;
    bool nullPlane=false, nullAddress=false;
    int GetWidth() { return width; } int GetHeight() { return height; }
    int GetStride() { return stride; } uint32_t GetSize() { return size; }
    int GetFormat() { return static_cast<int>(format); }
    void *GetVirAddr() { return nullAddress ? nullptr : bytes.data(); }
    int GetPlanesInfo(void **result) { *result=nullPlane ? nullptr : &planes; return planeResult; }
};
struct Memory {
    std::vector<uint8_t> bytes=std::vector<uint8_t>(6144,0);
    int size=6144, offset=0, capacity=6144;
    bool nullAddress=false;
    sptr<SurfaceBuffer> surface;
    int GetSize() {return size;} int GetCapacity() {return capacity;} int GetOffset(){return offset;}
    uint8_t *GetAddr(){return nullAddress ? nullptr : bytes.data();}
    sptr<SurfaceBuffer> GetSurfaceBuffer(){return surface;}
};
struct AVBuffer { std::shared_ptr<Memory> memory_=std::make_shared<Memory>(); int64_t pts_=125; int flag_=0; };
struct InputFrame {
    uint8_t *buffer=nullptr;
    int32_t width=0, height=0, stride=0, size=0, uvOffset=0;
    VideoPixelFormat format=VideoPixelFormat::UNKNOWN;
    int64_t pts=0;
};
struct Surface { int releases=0; int ReleaseBuffer(sptr<SurfaceBuffer>, int){++releases;return 0;} };
struct FBuffer {
    enum class Owner { OWNED_BY_USER, OWNED_BY_CODEC };
    Owner owner_=Owner::OWNED_BY_CODEC;
    sptr<SurfaceBuffer> surfaceBuffer_;
    std::shared_ptr<int> fence_=std::make_shared<int>(1);
    std::shared_ptr<AVBuffer> avBuffer_=std::make_shared<AVBuffer>();
};
struct Queue { unsigned Front(){return 0;} void Pop(){} };
struct Callback {int errors=0; void OnError(int,int){++errors;}};
struct AVCodecErrorType {static constexpr int AVCODEC_ERROR_INTERNAL=1;};
struct AVCodecServiceErrCode {static constexpr int AVCS_ERR_UNKNOWN=-5;};
class AvcEncoder {
public:
    enum class State {RUNNING, STOPPING, FLUSHING, ERROR, EOS};
    State state_=State::RUNNING;
    VideoPixelFormat srcPixelFmt_=VideoPixelFormat::NV12;
    int encWidth_=64,encHeight_=64;
    sptr<Surface> inputSurface_;
    bool isSendEos_=false,isFirstFrame_=false,enableIdrAppendXps_=false;
    int gopFrmIdx_=0, avcEncInputArgs_=0,avcEncOutputArgs_=0;
    int encodeCalls=0;
    std::mutex sendMutex_; std::condition_variable sendCv_;
    std::vector<std::shared_ptr<FBuffer>> buffers_[1]={{std::make_shared<FBuffer>()}};
    std::shared_ptr<Queue> inputAvailQue_=std::make_shared<Queue>();
    std::shared_ptr<Callback> callback_=std::make_shared<Callback>();
    int32_t GetSurfaceBufferUvOffset(sptr<SurfaceBuffer> &buffer, VideoPixelFormat format);
    int32_t GetInputFrameFromAVBuffer(std::shared_ptr<AVBuffer> &buffer, InputFrame &frame);
    int32_t CheckBufferSize(int32_t,int32_t,int32_t,VideoPixelFormat);
    void SendFrame();
    void ReleaseSurfaceBufferByAVBuffer(std::shared_ptr<AVBuffer> &buffer);
    std::shared_ptr<AVBuffer> GetAvBuffer(std::shared_ptr<FBuffer> buffer) {return buffer->avBuffer_;}
    void EncoderAvcTailer(){} void WaitForFence(std::shared_ptr<FBuffer>){} void ResetGopFrmIdx(){}
    void EncoderAvcHeader(){} void NotifyUserToFillBuffer(unsigned,std::shared_ptr<AVBuffer>&){}
    int FillAvcEncoderInArgs(std::shared_ptr<AVBuffer> &buffer,int&) {
        InputFrame frame; return GetInputFrameFromAVBuffer(buffer,frame);
    }
    int EncoderAvcFrame(int&,int&) {++encodeCalls;return 0;}
};
// @ACTUAL_FUNCTIONS@
static int checked=0;
#define EXPECT(c) do { assert(c); ++checked; } while(0)
static std::shared_ptr<AVBuffer> makeSurface(AvcEncoder &encoder, GraphicPixelFormat fmt,
                                          int stride, uint32_t size) {
    encoder.inputSurface_=std::make_shared<Surface>();
    auto buffer=std::make_shared<AVBuffer>();
    auto surface=std::make_shared<SurfaceBuffer>();
    surface->format=fmt;surface->stride=stride;surface->size=size;
    surface->bytes.resize(size);
    buffer->memory_->surface=surface;
    return buffer;
}
static void setTwoPlanes(sptr<SurfaceBuffer> surface, uint64_t chroma) {
    surface->planeResult=0;surface->planes.planeCount=2;
    surface->planes.planes[0]={0,static_cast<uint32_t>(surface->stride),1};
    surface->planes.planes[1]={chroma,static_cast<uint32_t>(surface->stride),1};
}
static void fillNv(sptr<SurfaceBuffer> surface, uint32_t chroma, bool nv21) {
    for(int y=0;y<64;++y) for(int x=0;x<64;++x)
        surface->bytes[y*surface->stride+x]=static_cast<uint8_t>(16+(x+y)%180);
    for(int y=0;y<32;++y) for(int x=0;x<32;++x) {
        surface->bytes[chroma+y*surface->stride+2*x+(nv21?1:0)]=static_cast<uint8_t>(70+(x+y)%30);
        surface->bytes[chroma+y*surface->stride+2*x+(nv21?0:1)]=static_cast<uint8_t>(150+(x+y)%30);
    }
}
static void checkNvPixels(InputFrame &frame, bool nv21) {
    std::vector<uint8_t> output(6144+16,0xde);
    YuvImageData data{frame.buffer,frame.stride,frame.uvOffset};
    int ret=nv21 ? ConvertNv21ToYuv420(output.data(),64,64,6144,data) :
                    ConvertNv12ToYuv420(output.data(),64,64,6144,data);
    EXPECT(ret==0);
    for(int y=0;y<64;++y) for(int x=0;x<64;++x) EXPECT(output[y*64+x]==16+(x+y)%180);
    for(int y=0;y<32;++y) for(int x=0;x<32;++x) {
        EXPECT(output[4096+y*32+x]==70+(x+y)%30);
        EXPECT(output[5120+y*32+x]==150+(x+y)%30);
    }
    for(size_t i=6144;i<output.size();++i) EXPECT(output[i]==0xde);
}
int main() {
    using P=VideoPixelFormat;using G=GraphicPixelFormat;
    AvcEncoder fixed; LegacyEncoder legacy; InputFrame frame;
    auto buffer=std::make_shared<AVBuffer>();
    buffer->memory_->bytes.assign(6144+17,0xff);
    buffer->memory_->offset=17;buffer->memory_->capacity=6161;
    for(int i=0;i<6144;++i)buffer->memory_->bytes[i+17]=static_cast<uint8_t>(i%251);
    EXPECT(legacy.GetInputFrameFromAVBuffer(buffer,frame)==0 && frame.buffer==buffer->memory_->bytes.data());
    EXPECT(fixed.GetInputFrameFromAVBuffer(buffer,frame)==0 && frame.buffer==buffer->memory_->bytes.data()+17);
    EXPECT(frame.buffer[0]==0 && frame.buffer[6143]==6143%251 && frame.pts==125);
    for(int y=0;y<64;++y) for(int x=0;x<64;++x) frame.buffer[y*64+x]=static_cast<uint8_t>(16+(x+y)%180);
    for(int y=0;y<32;++y) for(int x=0;x<32;++x) {
        frame.buffer[4096+y*64+x*2]=static_cast<uint8_t>(70+(x+y)%30);
        frame.buffer[4096+y*64+x*2+1]=static_cast<uint8_t>(150+(x+y)%30);
    }
    checkNvPixels(frame,false); // Actual conversion reads the challenged frame after the prefix.
    fixed.encWidth_=INT_MAX;
    EXPECT(fixed.GetInputFrameFromAVBuffer(buffer,frame)==-1);
    fixed.encWidth_=64;
    for(int bad: {-1,18,INT_MAX}) {buffer->memory_->offset=bad;EXPECT(fixed.GetInputFrameFromAVBuffer(buffer,frame)==-1);}
    buffer->memory_->offset=17;buffer->memory_->size=6143;
    EXPECT(fixed.GetInputFrameFromAVBuffer(buffer,frame)==-1);
    buffer->memory_->size=6144;buffer->memory_->nullAddress=true;
    EXPECT(fixed.GetInputFrameFromAVBuffer(buffer,frame)==-1);
    buffer->memory_->nullAddress=false;auto savedMemory=buffer->memory_;buffer->memory_=nullptr;
    EXPECT(fixed.GetInputFrameFromAVBuffer(buffer,frame)==-1);
    buffer->memory_=savedMemory;std::shared_ptr<AVBuffer> empty;
    EXPECT(fixed.GetInputFrameFromAVBuffer(empty,frame)==-1);

    for(bool nv21: {false,true}) for(int stride: {64,80}) for(int padding: {0,128}) {
        uint32_t uv=stride*64+padding,size=uv+stride*32;
        auto input=makeSurface(fixed,nv21?G::GRAPHIC_PIXEL_FMT_YCRCB_420_SP:G::GRAPHIC_PIXEL_FMT_YCBCR_420_SP,stride,size);
        auto surface=input->memory_->surface;setTwoPlanes(surface,uv);fillNv(surface,uv,nv21);
        EXPECT(fixed.GetInputFrameFromAVBuffer(input,frame)==0 && frame.uvOffset==static_cast<int>(uv));
        checkNvPixels(frame,nv21);
        if(nv21 && padding) {
            legacy.inputSurface_=fixed.inputSurface_;
            EXPECT(legacy.GetInputFrameFromAVBuffer(input,frame)==0 && frame.uvOffset==stride*64);
        }
        surface->size=size-1;
        EXPECT(fixed.GetInputFrameFromAVBuffer(input,frame)==-1);
        surface->size=size;surface->planes.planes[1].offset=uv+1;
        EXPECT(fixed.GetInputFrameFromAVBuffer(input,frame)==-1);
        surface->planes.planes[1].offset=UINT64_MAX;
        EXPECT(fixed.GetInputFrameFromAVBuffer(input,frame)==-1);
        surface->planes.planes[1].offset=static_cast<uint64_t>(INT_MAX)+1;
        EXPECT(fixed.GetInputFrameFromAVBuffer(input,frame)==-1);
        setTwoPlanes(surface,uv);surface->planes.planes[1].rowStride=stride+2;
        EXPECT(fixed.GetInputFrameFromAVBuffer(input,frame)==-1);
        setTwoPlanes(surface,uv);surface->planes.planes[0].offset=2;
        EXPECT(fixed.GetInputFrameFromAVBuffer(input,frame)==-1);
        setTwoPlanes(surface,uv);surface->planes.planeCount=1;
        EXPECT(fixed.GetInputFrameFromAVBuffer(input,frame)==-1);
        surface->planes.planeCount=5;
        EXPECT(fixed.GetInputFrameFromAVBuffer(input,frame)==-1);
        setTwoPlanes(surface,uv);surface->planes.planeCount=3;
        surface->planes.planes[nv21?2:1]={uv,static_cast<uint32_t>(stride),2};
        surface->planes.planes[nv21?1:2]={uv+1,static_cast<uint32_t>(stride),2};
        EXPECT(fixed.GetInputFrameFromAVBuffer(input,frame)==0);
        checkNvPixels(frame,nv21);
        surface->planes.planes[nv21?1:2].offset=uv+2;
        EXPECT(fixed.GetInputFrameFromAVBuffer(input,frame)==-1);
        setTwoPlanes(surface,uv);surface->nullPlane=true;
        EXPECT(fixed.GetInputFrameFromAVBuffer(input,frame)==-1);
    }
    for(bool nv21: {false,true}) {
        auto input=makeSurface(fixed,nv21?G::GRAPHIC_PIXEL_FMT_YCRCB_420_SP:G::GRAPHIC_PIXEL_FMT_YCBCR_420_SP,64,6144);
        fillNv(input->memory_->surface,4096,nv21);
        EXPECT(fixed.GetInputFrameFromAVBuffer(input,frame)==0 && frame.uvOffset==4096);
        checkNvPixels(frame,nv21); // Real QEMU no-layout contiguous fallback.
    }
    auto planar=makeSurface(fixed,G::GRAPHIC_PIXEL_FMT_YCBCR_420_P,80,80*96+128);
    auto surface=planar->memory_->surface;
    surface->planeResult=0;surface->planes.planeCount=3;
    surface->planes.planes[0]={0,80,1};surface->planes.planes[1]={80*64+128,40,1};
    surface->planes.planes[2]={80*64+128+40*32,40,1};
    EXPECT(fixed.GetInputFrameFromAVBuffer(planar,frame)==0 && frame.uvOffset==80*64+128);
    surface->planes.planes[2].offset++;
    EXPECT(fixed.GetInputFrameFromAVBuffer(planar,frame)==-1);
    surface->planes.planes[2].offset--;surface->size--;
    EXPECT(fixed.GetInputFrameFromAVBuffer(planar,frame)==-1);

    auto rgb=makeSurface(fixed,G::GRAPHIC_PIXEL_FMT_RGBA_8888,256,16384);
    for(int i=0;i<4096;++i){auto &b=rgb->memory_->surface->bytes;b[i*4]=255;b[i*4+1]=0;b[i*4+2]=0;b[i*4+3]=255;}
    EXPECT(fixed.GetInputFrameFromAVBuffer(rgb,frame)==0 && frame.stride==256);
    RgbImageData rgbData{frame.buffer,frame.stride/4,MATRIX_BT601,RANGE_LIMITED,4};
    std::vector<uint8_t> rgbOutput(6144+16,0xde);
    EXPECT(ConvertRgbToYuv420(rgbOutput.data(),64,64,6144,rgbData)==0);
    for(int i=0;i<4096;++i) EXPECT(rgbOutput[i]==81);
    for(int i=4096;i<5120;++i) EXPECT(rgbOutput[i]==90);
    for(int i=5120;i<6144;++i) EXPECT(rgbOutput[i]==239);
    for(size_t i=6144;i<rgbOutput.size();++i) EXPECT(rgbOutput[i]==0xde);
    rgb->memory_->surface->stride=64;rgb->memory_->surface->size=4096;
    legacy.inputSurface_=fixed.inputSurface_;
    EXPECT(legacy.GetInputFrameFromAVBuffer(rgb,frame)==0 && legacy.CheckBufferSize(frame.size,frame.stride,frame.height,frame.format)==0);
    EXPECT(fixed.GetInputFrameFromAVBuffer(rgb,frame)==-1);
    for(int stride: {255,257,INT_MAX-3}) {rgb->memory_->surface->stride=stride;EXPECT(fixed.GetInputFrameFromAVBuffer(rgb,frame)==-1);}
    rgb->memory_->surface->stride=256;rgb->memory_->surface->size=16383;
    EXPECT(fixed.GetInputFrameFromAVBuffer(rgb,frame)==-1);
    rgb->memory_->surface->size=UINT32_MAX;
    EXPECT(fixed.GetInputFrameFromAVBuffer(rgb,frame)==-1);
    rgb->memory_->surface->size=16384;rgb->memory_->surface->width=66;
    EXPECT(fixed.GetInputFrameFromAVBuffer(rgb,frame)==-1);
    rgb->memory_->surface->width=64;rgb->memory_->surface->height=63;
    EXPECT(fixed.GetInputFrameFromAVBuffer(rgb,frame)==-1);
    rgb->memory_->surface->height=64;rgb->memory_->surface->nullAddress=true;
    EXPECT(fixed.GetInputFrameFromAVBuffer(rgb,frame)==-1);
    for(G fmt: {G::GRAPHIC_PIXEL_FMT_YCBCR_P010,G::GRAPHIC_PIXEL_FMT_YCRCB_P010,G::UNKNOWN}) {
        auto p010=makeSurface(fixed,fmt,128,12288);
        EXPECT(fixed.GetInputFrameFromAVBuffer(p010,frame)==-1);
    }
    EXPECT(LegacyTranslateVideoPixelFormat(G::GRAPHIC_PIXEL_FMT_YCBCR_P010)==P::NV12);
    EXPECT(LegacyTranslateVideoPixelFormat(G::GRAPHIC_PIXEL_FMT_YCRCB_P010)==P::NV21);
    EXPECT(TranslateVideoPixelFormat(G::GRAPHIC_PIXEL_FMT_YCBCR_P010)==P::UNKNOWN);
    EXPECT(TranslateVideoPixelFormat(G::GRAPHIC_PIXEL_FMT_YCRCB_P010)==P::UNKNOWN);

    AvcEncoder rejected;
    auto invalid=makeSurface(rejected,G::GRAPHIC_PIXEL_FMT_RGBA_8888,64,4096);
    auto acquired=rejected.buffers_[0][0];acquired->avBuffer_=invalid;acquired->surfaceBuffer_=invalid->memory_->surface;
    rejected.SendFrame();
    EXPECT(rejected.state_==AvcEncoder::State::ERROR && rejected.callback_->errors==1);
    EXPECT(rejected.inputSurface_->releases==1 && !acquired->surfaceBuffer_ && !acquired->fence_);
    EXPECT(rejected.encodeCalls==0);
    rejected.SendFrame();
    EXPECT(rejected.inputSurface_->releases==1 && rejected.callback_->errors==1 && rejected.encodeCalls==0);
    AvcEncoder recreated;
    auto valid=makeSurface(recreated,G::GRAPHIC_PIXEL_FMT_RGBA_8888,256,16384);
    recreated.buffers_[0][0]->avBuffer_=valid;recreated.SendFrame();
    EXPECT(recreated.state_==AvcEncoder::State::RUNNING && recreated.callback_->errors==0 && recreated.encodeCalls==1);
    std::cout << "actual_function_checks=" << checked << "\n";
}
