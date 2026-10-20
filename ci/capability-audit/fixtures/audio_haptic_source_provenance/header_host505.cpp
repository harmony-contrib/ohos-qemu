#include "qemu_audio_provenance505.h"
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <vector>
#include <thread>
#include <set>
static std::vector<std::string> rows;
static void Emit(const std::string &row){rows.push_back(row);}
static void Need(bool okay,const char*message){if(!okay){std::cerr<<message<<'\n';std::exit(1);}}
int main(int argc,char**argv)
{
    if(argc==2&&std::string(argv[1])=="hashes"){
        uint8_t bytes[Qap505::MAX_PREFIX];for(size_t i=0;i<sizeof(bytes);++i)bytes[i]=static_cast<uint8_t>(i);
        for(size_t size:{0u,1u,3u,55u,56u,63u,64u,65u,127u,128u})
            std::cout<<size<<' '<<Qap505::SampleSha256(bytes,size)<<'\n';
        Need(Qap505::SampleSha256(reinterpret_cast<const uint8_t*>("abc"),3)=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","NIST abc");
        Need(Qap505::SampleSha256(nullptr,0)=="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","NIST empty");
        return 0;
    }
    Need(argc==3,"WAV and embedded WAV paths required");int fd=::open(argv[1],O_RDONLY|O_CLOEXEC);Need(fd>=0,"actual test file");
    struct stat st{};Need(::fstat(fd,&st)==0,"stat test file");Need(::lseek(fd,7,SEEK_SET)==7,"set independent OFD offset");
    auto source=Qap505::Probe(fd,0,st.st_size);Need(source.wav==1&&source.generation>0,"real WAV probe");
    Need(::lseek(fd,0,SEEK_CUR)==7,"pread must not change source OFD offset");
    Need(source.dataOffset==44&&source.dataBytes==512&&source.rate==48000&&source.channels==2&&source.sampleBytes==2,"actual WAV declaration fields");
    int embedded=::open(argv[2],O_RDONLY|O_CLOEXEC);Need(embedded>=0&&::lseek(embedded,5,SEEK_SET)==5,"embedded source FD");
    auto window=Qap505::Probe(embedded,7,st.st_size);Need(window.wav==1&&window.offset==7&&window.length==static_cast<uint64_t>(st.st_size)&&window.dataOffset==44&&window.prefix==source.prefix,"nonzero pinned source window declaration");
    Need(::lseek(embedded,0,SEEK_CUR)==5,"embedded source OFD offset unchanged");::close(embedded);
    auto second=Qap505::Probe(fd,0,st.st_size);Need(second.generation>source.generation,"independent native generation");
    auto bad=Qap505::Probe(fd,st.st_size-1,10);Need(bad.wav==0,"out-of-window remains unknown");
    auto negative=Qap505::Probe(fd,-1,10);Need(negative.wav==0,"negative offset remains unknown");
    auto descriptor=Qap505::Encode(source);Qap505::Source decoded;
    Need(Qap505::Decode(descriptor,decoded)&&Qap505::Encode(decoded)==descriptor,"canonical descriptor roundtrip");
    Need(!Qap505::Decode(descriptor+":0",decoded),"descriptor extra field");
    Need(!Qap505::Decode("qap505v1:18446744073709551616:0",decoded),"overflow descriptor");
    std::string statText="101 (a name ) with )) S ";for(unsigned i=4;i<22;++i)statText+="0 ";statText+="12345 0\n";
    Need(Qap505::ParseBirthTicks(statText.data(),statText.size())==12345,"comm with spaces and right parentheses");
    auto overflow=statText.substr(0,statText.find("12345"))+"18446744073709551616 0\n";
    Need(Qap505::ParseBirthTicks(overflow.data(),overflow.size())==0,"birth overflow unknown");
    auto truncated=statText.substr(0,statText.find("12345")+2);
    Need(Qap505::ParseBirthTicks(truncated.data(),truncated.size())==0,"birth truncation unknown");
    Qap505::Ledger ledger(Emit);ledger.Bind(descriptor,0,71);uint8_t pcm[16]={1,2,3,4};
    auto input=ledger.Input(pcm,sizeof(pcm));Need(input.snapshot&&input.begin==0&&input.bytes==16,"real ingress interval");
    ledger.Write(input,16,4,4,0,71);Need(input.snapshot->accepted==4,"partial Write only advances accepted bytes");
    auto remaining=input.Subspan(4);Need(remaining.begin==4&&remaining.bytes==12,"remainder byte interval");
    ledger.Write(remaining,12,-1,4,0,71);Need(input.snapshot->accepted==4,"negative Write does not advance");
    ledger.Write(remaining,12,0,4,0,71);Need(input.snapshot->accepted==4,"zero Write does not advance");
    ledger.Write(remaining,12,16,4,0,71);Need(input.snapshot->accepted==4&&input.snapshot->invalid,"overlarge return not accepted");
    Qap505::Cached cached(std::vector<uint8_t>(pcm+4,pcm+16),remaining);Need(cached.provenance.cacheId>0,"native cache ID");
    auto split=cached.provenance.Subspan(8);Need(split.begin==12&&split.bytes==4&&split.cacheId==cached.provenance.cacheId,"cache split retains identity");
    ledger.Bind(Qap505::Encode(second),0,71);ledger.Write(cached.provenance,12,12,4,0,71);
    Need(cached.provenance.snapshot->source.generation==source.generation,"old cache never relabeled to later generation");
    Need(rows.back().find("\"old_generation\":true")!=std::string::npos,"old generation is explicit");
    ledger.Reset("flush");Need(!ledger.Input(pcm,sizeof(pcm)).snapshot,"flush must not invent new source identity");
    Need(input.Subspan(17).snapshot==nullptr,"invalid subspan unknown");
    for(const auto&row:rows){Need(row.find("\"accepted\":false")!=std::string::npos,"raw rows cannot claim acceptance");Need(row.find("\"onset_proven\":false")!=std::string::npos,"raw rows cannot claim onset");}
    rows.clear();Qap505::Ledger concurrent(Emit);concurrent.Bind(descriptor,0,71);std::vector<Qap505::Slice> intervals(512);std::vector<std::thread> workers;
    for(size_t thread=0;thread<4;++thread)workers.emplace_back([&,thread]{for(size_t i=0;i<128;++i)intervals[thread*128+i]=concurrent.Input(pcm,sizeof(pcm));});
    for(auto &worker:workers)worker.join();std::set<uint64_t> starts;
    for(const auto &slice:intervals){Need(slice.snapshot&&slice.bytes==16,"concurrent real ledger ingress slice");starts.insert(slice.begin);}
    Need(starts.size()==512&&*starts.begin()==0&&*starts.rbegin()==511*16,"concurrent ingress must serialize without duplicate or lost intervals");
    rows.clear();Qap505::Ledger limited(Emit);limited.Bind(descriptor,0,71);
    for(unsigned i=0;i<Qap505::MAX_ROWS+2;++i)(void)limited.Input(pcm,sizeof(pcm));
    Need(rows.size()==Qap505::MAX_ROWS&&rows.back().find("observation_limit")!=std::string::npos,"bounded observation explicitly unknown");
    ::close(fd);std::cout<<"{\"scope\":\"actual header real host FD plus software interval edges ONLY\",\"rows\":"<<rows.size()<<",\"source_generation\":"<<source.generation<<",\"source_prefix_sha256\":\""<<source.prefix<<"\",\"source_prefix_bytes\":"<<source.prefixBytes<<",\"accepted\":false,\"onset_proven\":false}\n";
    return 0;
}
