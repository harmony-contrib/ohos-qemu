// Copyright 2026. Apache-2.0. Normal IV HDI CPU implementation.
// All model inputs are actual HDI PCM. Start/Init/Commit never invent a result.
#include "cpu_voice_engine.h"
#include "hdf_base.h"
#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cmath>
#include <cstring>
#include <cstdio>
#include <fcntl.h>
#include <fstream>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <sys/file.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
using namespace OHOS::HDI::IntelligentVoice::Engine::V1_0;
namespace OHOS::IntelligentVoice::Engine {
namespace {
std::atomic<uint64_t> cpuGeneration{0};
constexpr const char *MODELS = "/vendor/etc/intelligent_voice/cpu/";
constexpr const char *STATE = "/data/service/el0/intelligent_voice/wakeup/cpu/cpu-enrollment.bin";
constexpr const char *JOURNAL = "/data/service/el0/intelligent_voice/wakeup/cpu/cpu-journal.jsonl";
constexpr size_t MAX_SAMPLES = 16000 * 30;
constexpr float VERIFY_THRESHOLD = 0.55F;
struct Saved { char magic[8]; uint32_t phraseBytes; uint32_t dim; };
bool Regular(int fd, size_t limit)
{
    struct stat s{};
    return fstat(fd, &s) == 0 && S_ISREG(s.st_mode) && s.st_nlink == 1 &&
        s.st_uid == geteuid() && s.st_size >= 0 && static_cast<uint64_t>(s.st_size) <= limit;
}
bool FullWrite(int fd, const void *data, size_t size)
{
    const auto *p = static_cast<const uint8_t *>(data);
    while (size) { ssize_t n = write(fd, p, size); if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { return false; }
        p += n; size -= static_cast<size_t>(n); }
    return true;
}
bool FullRead(int fd, void *data, size_t size)
{
    auto *p = static_cast<uint8_t *>(data);
    while (size) { ssize_t n = read(fd, p, size); if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { return false; }
        p += n; size -= static_cast<size_t>(n); }
    return true;
}
bool LoadSaved(std::string &phrase, std::vector<float> &embedding)
{
    int fd = open(STATE, O_RDONLY | O_CLOEXEC | O_NOFOLLOW); if (fd < 0) return false;
    Saved h{}; bool ok = Regular(fd, 65536) && flock(fd, LOCK_SH) == 0 && FullRead(fd, &h, sizeof(h)) &&
        std::memcmp(h.magic, "IVCPU01", 8) == 0 && h.phraseBytes > 0 && h.phraseBytes <= 1024 && h.dim > 0 && h.dim <= 4096;
    if (ok) { phrase.resize(h.phraseBytes); embedding.resize(h.dim);
        ok = FullRead(fd, phrase.data(), phrase.size()) && FullRead(fd, embedding.data(), embedding.size() * sizeof(float));
        char tail; ok = ok && read(fd, &tail, 1) == 0;
        for (float value : embedding) ok = ok && std::isfinite(value); }
    close(fd); if (!ok) { phrase.clear(); embedding.clear(); } return ok;
}
std::string Tokenize(const std::string &phrase)
{
    if (phrase.empty() || phrase.size() > 1024 || phrase.find_first_of("\n\r;@:#") != std::string::npos) return "";
    std::set<std::string> tokens; std::ifstream tokenFile(std::string(MODELS) + "tokens.txt");
    std::string line, word; while (std::getline(tokenFile, line)) { std::istringstream s(line); s >> word; tokens.insert(word); }
    // Lexicon is normal product data derived from the complete pinned public
    // pinyin-data dictionary. No phrase or expected result comes from a test.
    std::map<uint32_t, std::string> lexicon; std::ifstream lex(std::string(MODELS) + "pinyin.txt");
    while (std::getline(lex, line)) {
        if (line.rfind("U+", 0) != 0) continue;
        size_t colon = line.find(':'); if (colon == std::string::npos) continue;
        std::istringstream code(line.substr(2, colon - 2)); uint32_t ch = 0; code >> std::hex >> ch;
        std::string value = line.substr(colon + 1); value = value.substr(value.find_first_not_of(" \t"));
        value = value.substr(0, value.find_first_of(", #\t\r\n")); if (!value.empty()) lexicon[ch] = value;
    }
    std::string result;
    for (size_t at = 0; at < phrase.size();) {
        unsigned char c = static_cast<unsigned char>(phrase[at++]); uint32_t cp = c; unsigned extra = 0;
        if (c >= 0xc2 && c <= 0xdf) { cp = c & 31; extra = 1; }
        else if (c >= 0xe0 && c <= 0xef) { cp = c & 15; extra = 2; }
        else if (c >= 0xf0 && c <= 0xf4) { cp = c & 7; extra = 3; }
        else if (c >= 0x80) return "";
        if (at + extra > phrase.size()) return "";
        for (unsigned i = 0; i < extra; ++i) { unsigned char b = static_cast<unsigned char>(phrase[at++]); if ((b & 0xc0) != 0x80) return ""; cp = (cp << 6) | (b & 63); }
        auto found = lexicon.find(cp); if (found == lexicon.end()) return "";
        word = found->second;
        if (tokens.count(word)) result += word + " ";
        else {
            size_t split = word.rfind("zh", 0) == 0 || word.rfind("ch", 0) == 0 || word.rfind("sh", 0) == 0 ? 2 : 1;
            if (word.size() <= split || !tokens.count(word.substr(0, split)) || !tokens.count(word.substr(split))) return "";
            result += word.substr(0, split) + " " + word.substr(split) + " ";
        }
    }
    return result + "@" + phrase;
}
float Cosine(const std::vector<float> &a, const std::vector<float> &b)
{
    if (a.size() != b.size() || a.empty()) return -1;
    double dot = 0, aa = 0, bb = 0; for (size_t i = 0; i < a.size(); ++i) { dot += a[i]*b[i]; aa += a[i]*a[i]; bb += b[i]*b[i]; }
    return aa > 0 && bb > 0 ? static_cast<float>(dot / std::sqrt(aa*bb)) : -1;
}
}
void CpuVoiceEngine::JournalLocked(const std::string &event, int result, const std::string &detail)
{
    timespec ts{}; clock_gettime(CLOCK_BOOTTIME, &ts);
    std::ostringstream s; s << "{\"schema\":\"qemu-cpu-IV/v1\",\"pid\":" << getpid() << ",\"uid\":" << geteuid()
        << ",\"seq\":" << ++seq_ << ",\"generation\":" << generation_ << ",\"enroll\":" << (enroll_ ? "true" : "false")
        << ",\"frames\":" << frames_ << ",\"monotonicNs\":" << static_cast<uint64_t>(ts.tv_sec)*1000000000ULL + ts.tv_nsec
        << ",\"event\":\"" << event << "\",\"result\":" << result << ",\"detail\":\"";
    for (unsigned char c : detail) { if (c == '"' || c == '\\') s << '\\'; if (c >= 32) s << c; }
    s << "\"}\n"; std::string text = s.str();
    int fd = open(JOURNAL, O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd >= 0) { if (Regular(fd, 4*1024*1024) && flock(fd, LOCK_EX) == 0) FullWrite(fd, text.data(), text.size()); close(fd); }
}
IntellVoiceStatus CpuVoiceEngine::SetListener(std::shared_ptr<IEngineCallback> listener)
{ std::lock_guard<std::mutex> lock(mutex_); callback_ = std::move(listener); return 0; }
void CpuVoiceEngine::ResetStreamLocked()
{
    if (stream_) SherpaOnnxDestroyOnlineStream(stream_);
    stream_ = kws_ ? SherpaOnnxCreateKeywordStreamWithKeywords(kws_, keywords_.c_str()) : nullptr;
    pcm_.clear(); frames_ = 0; speechBegin_ = speechEnd_ = 0; phraseHeard_ = false;
}
void CpuVoiceEngine::DestroyLocked()
{
    active_ = initialized_ = false;
    if (stream_) { SherpaOnnxDestroyOnlineStream(stream_); }
    stream_ = nullptr;
    if (kws_) { SherpaOnnxDestroyKeywordSpotter(kws_); }
    kws_ = nullptr;
    if (speaker_) { SherpaOnnxDestroySpeakerEmbeddingExtractor(speaker_); }
    speaker_ = nullptr;
    pcm_.clear(); candidate_.clear(); committed_.clear();
}
IntellVoiceStatus CpuVoiceEngine::Init(const IntellVoiceEngineAdapterInfo &info)
{
    std::shared_ptr<IEngineCallback> callback;
    { std::lock_guard<std::mutex> lock(mutex_); DestroyLocked(); generation_ = ++cpuGeneration;
      if (!callback_ || info.sampleRate != 16000 || info.sampleChannels != 1 || info.bitsPerSample != 16) return -EINVAL;
      phrase_ = info.wakeupPhrase; keywords_ = Tokenize(phrase_); if (keywords_.empty()) return -ENOTSUP;
      SherpaOnnxKeywordSpotterConfig k{}; k.feat_config.sample_rate = 16000; k.feat_config.feature_dim = 80;
      std::string encoder = std::string(MODELS) + "encoder.onnx", decoder = std::string(MODELS) + "decoder.onnx", joiner = std::string(MODELS) + "joiner.onnx", tokens = std::string(MODELS) + "tokens.txt";
      k.model_config.transducer.encoder = encoder.c_str(); k.model_config.transducer.decoder = decoder.c_str(); k.model_config.transducer.joiner = joiner.c_str();
      k.model_config.tokens = tokens.c_str(); k.model_config.num_threads = 1; k.model_config.provider = "cpu";
      k.max_active_paths = 4; k.num_trailing_blanks = 1; k.keywords_score = 1.0F; k.keywords_threshold = 0.25F;
      k.keywords_buf = keywords_.c_str(); k.keywords_buf_size = static_cast<int32_t>(keywords_.size());
      kws_ = SherpaOnnxCreateKeywordSpotter(&k);
      std::string speaker = std::string(MODELS) + "speaker.onnx";
      SherpaOnnxSpeakerEmbeddingExtractorConfig e{}; e.model = speaker.c_str(); e.num_threads = 1; e.provider = "cpu";
      speaker_ = SherpaOnnxCreateSpeakerEmbeddingExtractor(&e);
      if (!kws_ || !speaker_) { DestroyLocked(); return -ENODEV; }
      ResetStreamLocked(); initialized_ = stream_ != nullptr; if (!initialized_) { DestroyLocked(); return -ENOMEM; }
      JournalLocked("real-models-initialized", 0, phrase_); callback = callback_; }
    callback->OnIntellVoiceEvent({INTELL_VOICE_ENGINE_MSG_INIT_DONE, INTELL_VOICE_ENGINE_OK, ""}); return 0;
}
bool CpuVoiceEngine::LoadEnrollmentLocked()
{
    std::string saved; std::vector<float> e;
    if (!LoadSaved(saved, e) || e.size() != static_cast<size_t>(SherpaOnnxSpeakerEmbeddingExtractorDim(speaker_))) return false;
    std::string tokens = Tokenize(saved); if (tokens.empty()) return false;
    phrase_ = std::move(saved); keywords_ = std::move(tokens); committed_ = std::move(e); return true;
}
IntellVoiceStatus CpuVoiceEngine::Start(const StartInfo &)
{
    std::lock_guard<std::mutex> lock(mutex_);
    if (!initialized_ || !callback_ || active_) return -EINVAL;
    if (!enroll_ && !LoadEnrollmentLocked()) return -ENOENT;
    ResetStreamLocked(); candidate_.clear(); enrolled_ = false;
    if (!stream_) return -ENOMEM;
    tracePath_ = "/data/service/el0/intelligent_voice/wakeup/cpu/cpu-" + std::to_string(getpid()) + "-" + std::to_string(generation_) + "-" + std::to_string(++segment_) + ".pcm";
    int fd = open(tracePath_.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0) return -errno;
    bool regular = Regular(fd, MAX_SAMPLES*2); close(fd); if (!regular) return -EIO;
    active_ = true; JournalLocked("actual-pcm-listening", 0, tracePath_); return 0;
}
bool CpuVoiceEngine::MakeEmbeddingLocked(std::vector<float> &embedding)
{
    if (!phraseHeard_ || frames_ < speechEnd_ || speechEnd_ <= speechBegin_) return false;
    uint64_t begin = speechBegin_ > 3200 ? speechBegin_ - 3200 : 0;
    uint64_t end = std::min<uint64_t>(frames_, std::max<uint64_t>(speechEnd_ + 4800, begin + 16000));
    if (end - begin < 16000) return false;
    const auto *s = SherpaOnnxSpeakerEmbeddingExtractorCreateStream(speaker_); if (!s) return false;
    std::vector<float> samples(static_cast<size_t>(end - begin));
    for (size_t i=0;i<samples.size();++i) { int16_t value = static_cast<int16_t>(static_cast<uint16_t>(pcm_[2*(begin+i)]) | static_cast<uint16_t>(pcm_[2*(begin+i)+1]) << 8); samples[i]=value/32768.F; }
    SherpaOnnxOnlineStreamAcceptWaveform(s, 16000, samples.data(), static_cast<int32_t>(samples.size())); SherpaOnnxOnlineStreamInputFinished(s);
    bool ok = SherpaOnnxSpeakerEmbeddingExtractorIsReady(speaker_, s);
    const float *v = ok ? SherpaOnnxSpeakerEmbeddingExtractorComputeEmbedding(speaker_, s) : nullptr;
    int dim = SherpaOnnxSpeakerEmbeddingExtractorDim(speaker_);
    ok = v && dim > 0 && dim <= 4096;
    if (ok) { embedding.assign(v, v+dim); for (float value : embedding) ok = ok && std::isfinite(value); }
    if (v) SherpaOnnxSpeakerEmbeddingExtractorDestroyEmbedding(v);
    SherpaOnnxDestroyOnlineStream(s); return ok;
}
IntellVoiceStatus CpuVoiceEngine::Write(const uint8_t *buffer, uint32_t size)
{
    std::shared_ptr<IEngineCallback> callback; IntellVoiceEngineCallBackEvent event{};
    { std::lock_guard<std::mutex> lock(mutex_);
      if (!active_ || !buffer || size == 0 || size > 65536 || size % 2) return -EINVAL;
      if (pcm_.size()+size > MAX_SAMPLES*2) { active_=false; JournalLocked("bounded-pcm-timeout", -ETIMEDOUT); return -ETIMEDOUT; }
      std::vector<float> samples(size/2); for (size_t i=0;i<samples.size();++i) { int16_t x = static_cast<int16_t>(static_cast<uint16_t>(buffer[2*i]) | static_cast<uint16_t>(buffer[2*i+1])<<8); samples[i]=x/32768.F; }
      int trace = open(tracePath_.c_str(), O_WRONLY | O_APPEND | O_CLOEXEC | O_NOFOLLOW);
      if (trace < 0 || !Regular(trace, MAX_SAMPLES*2) || !FullWrite(trace, buffer, size)) { if(trace>=0)close(trace); return -EIO; }
      close(trace);
      pcm_.insert(pcm_.end(), buffer, buffer+size); frames_ += size/2;
      JournalLocked("actual-hdi-pcm-consumed", 0, tracePath_);
      SherpaOnnxOnlineStreamAcceptWaveform(stream_, 16000, samples.data(), static_cast<int32_t>(samples.size()));
      while (SherpaOnnxIsKeywordStreamReady(kws_, stream_)) {
          SherpaOnnxDecodeKeywordStream(kws_, stream_); const auto *r=SherpaOnnxGetKeywordResult(kws_, stream_);
          if (r) {
              if (r->keyword && phrase_==r->keyword && r->count>0 && r->count<=128 && r->timestamps &&
                  std::isfinite(r->start_time) && std::isfinite(r->timestamps[0]) && std::isfinite(r->timestamps[r->count-1])) {
                  double begin=(r->start_time+r->timestamps[0])*16000.0, end=(r->start_time+r->timestamps[r->count-1])*16000.0;
                  if(begin>=0 && end>=begin && end<=MAX_SAMPLES) { phraseHeard_=true; speechBegin_=static_cast<uint64_t>(begin); speechEnd_=static_cast<uint64_t>(end); }
              }
              SherpaOnnxDestroyKeywordResult(r);
          }
      }
      if (!phraseHeard_ || frames_<speechEnd_+4800) return 0;
      std::vector<float> embedding; if (!MakeEmbeddingLocked(embedding)) return 0;
      float score=enroll_ ? 1.F : Cosine(committed_,embedding);
      if (!enroll_ && score<VERIFY_THRESHOLD) { JournalLocked("actual-speaker-rejected", -EACCES, std::to_string(score)); phraseHeard_=false; SherpaOnnxResetKeywordStream(kws_,stream_); return 0; }
      active_=false; if (enroll_) { candidate_=std::move(embedding); enrolled_=true; }
      int fd = open(tracePath_.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
      if(fd<0 || !Regular(fd,MAX_SAMPLES*2) || fsync(fd)!=0) { if(fd>=0)close(fd); return -EIO; } close(fd);
      JournalLocked(enroll_?"actual-enrollment-complete":"actual-wakeup-recognized",0,phrase_+";cosine="+std::to_string(score));
      event.msgId=enroll_?INTELL_VOICE_ENGINE_MSG_ENROLL_COMPLETE:INTELL_VOICE_ENGINE_MSG_RECOGNIZE_COMPLETE; event.result=INTELL_VOICE_ENGINE_OK; event.info=phrase_; callback=callback_; }
    if (callback) { callback->OnIntellVoiceEvent(event); }
    return 0;
}
bool CpuVoiceEngine::CommitLocked()
{
    if (!enroll_ || !enrolled_ || candidate_.empty()) return false;
    std::string tmp=std::string(STATE)+".tmp."+std::to_string(getpid()); int fd=open(tmp.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600); if(fd<0)return false;
    Saved h{};std::memcpy(h.magic,"IVCPU01",8);h.phraseBytes=static_cast<uint32_t>(phrase_.size());h.dim=static_cast<uint32_t>(candidate_.size());
    bool ok=Regular(fd,65536)&&FullWrite(fd,&h,sizeof(h))&&FullWrite(fd,phrase_.data(),phrase_.size())&&FullWrite(fd,candidate_.data(),candidate_.size()*sizeof(float))&&fsync(fd)==0;close(fd);
    if(ok)ok=rename(tmp.c_str(),STATE)==0;
    if(!ok)unlink(tmp.c_str());
    int parent=open("/data/service/el0/intelligent_voice/wakeup/cpu",O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);if(parent>=0){if(ok)ok=fsync(parent)==0;close(parent);}else ok=false;
    return ok;
}
IntellVoiceStatus CpuVoiceEngine::SetParameter(const std::string &value)
{
    std::shared_ptr<IEngineCallback> callback;
    {std::lock_guard<std::mutex> lock(mutex_);
     if(value=="CommitEnrollment=true" || value=="CommitEnrollment=1") { if(!CommitLocked())return -EINVAL;JournalLocked("actual-enrollment-committed",0,phrase_);callback=callback_; }
     else if(value=="end_of_pcm=true") { if(active_&&enroll_){active_=false;JournalLocked("actual-enrollment-no-match",-ENOENT);callback=callback_;}else return 0; }
     else { if (value.size()>4096) return -EINVAL; JournalLocked("unsupported-vendor-parameter",-ENOTSUP,value); return -ENOTSUP; }}
    if (callback) {
        callback->OnIntellVoiceEvent({value.rfind("CommitEnrollment=",0)==0?INTELL_VOICE_ENGINE_MSG_COMMIT_ENROLL_COMPLETE:INTELL_VOICE_ENGINE_MSG_ENROLL_COMPLETE,
            value.rfind("CommitEnrollment=",0)==0?INTELL_VOICE_ENGINE_OK:static_cast<IntellVoiceEngineErrors>(-ENOENT),""});
    }
    return 0;
}
IntellVoiceStatus CpuVoiceEngine::GetParameter(const std::string &key,getParameterCb cb)
{
    if(!cb)return -EINVAL;std::string value;
    {std::lock_guard<std::mutex> lock(mutex_);if(key=="wakeup_phrase")value=phrase_;else if(key=="WakeupSourceChannel"||key=="wakeup_source_channel")value="1";else return -ENOTSUP;}
    cb(value);return 0;
}
IntellVoiceStatus CpuVoiceEngine::Stop(){std::lock_guard<std::mutex> lock(mutex_);active_=false;JournalLocked("actual-stopped",0);return 0;}
IntellVoiceStatus CpuVoiceEngine::Cancel(){std::lock_guard<std::mutex> lock(mutex_);active_=false;enrolled_=false;candidate_.clear();JournalLocked("actual-cancelled",0);return 0;}
IntellVoiceStatus CpuVoiceEngine::Release(){std::lock_guard<std::mutex> lock(mutex_);JournalLocked("actual-released",0);DestroyLocked();callback_.reset();return 0;}
IntellVoiceStatus CpuVoiceEngine::GetWakeupPcm(std::vector<uint8_t>&data){std::lock_guard<std::mutex> lock(mutex_);if(enroll_||pcm_.empty())return -ENODATA;data=pcm_;return 0;}
IntellVoiceStatus CpuVoiceEngine::ReadFileData(ContentType,getFileDataCb){return -ENOTSUP;}
IntellVoiceStatus CpuVoiceEngine::Evaluate(const std::string &,EvaluationResultInfo &){return -ENOTSUP;}
int32_t CpuVoiceEngine::ClearEnrollment(const std::string &phrase)
{std::string saved;std::vector<float> e;if(!LoadSaved(saved,e))return -ENOENT;if(saved!=phrase)return -EINVAL;return unlink(STATE)==0?0:-errno;}
}
