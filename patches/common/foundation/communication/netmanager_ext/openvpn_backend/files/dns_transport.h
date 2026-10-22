#pragma once
#include "dns_policy.h"
#include "session_files.h"
#include "net_conn_client.h"
#include <openssl/err.h>
#include <openssl/pem.h>
#include <openssl/ssl.h>
#include <openssl/x509v3.h>
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <sys/stat.h>
#include <unistd.h>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <fcntl.h>
#include <list>
#include <mutex>
#include <net/if.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <thread>

namespace OhosOpenvpn {
inline uint16_t Dns16(const unsigned char *p) { return (unsigned(p[0]) << 8) | p[1]; }
inline void PutDns16(unsigned char *p, unsigned n) { p[0]=n>>8; p[1]=n; }
inline uint16_t PacketChecksum(const unsigned char *p,size_t n,unsigned sum=0)
{
    for(size_t i=0;i+1<n;i+=2) sum+=Dns16(p+i);
    if(n&1) sum+=unsigned(p[n-1])<<8;
    while(sum>>16) sum=(sum&65535)+(sum>>16);
    return static_cast<uint16_t>(~sum);
}
inline std::string HexDns(const std::vector<unsigned char> &v)
{
    constexpr char hex[]="0123456789abcdef";std::string out;out.reserve(v.size()*2);
    for(unsigned char c:v){out+=hex[c>>4];out+=hex[c&15];}return out;
}
struct DnsRequest {
    std::vector<unsigned char> packet,question;
    std::string host;
    size_t ip=0;
    unsigned family=0;
};
inline bool DnsQuestionName(const std::vector<unsigned char> &q,std::string &name)
{
    if(q.size()<17 || q.size()>4096 || q[2]&0x80 || Dns16(q.data()+4)!=1) return false;
    size_t at=12;name.clear();
    while(at<q.size() && q[at]) {
        unsigned count=q[at++];if(count>63 || at+count>=q.size())return false;
        if(!name.empty())name+='.';
        for(unsigned i=0;i<count;++i) {
            unsigned char c=q[at++];
            if(!((c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='-'||c=='_'))return false;
            name+=static_cast<char>(std::tolower(c));
        }
    }
    return name.size()<=253 && at+5<=q.size() && q[at]==0;
}

// One bounded worker belongs to the actual bridge/session. It has no listen
// socket, no global resolver edits, and binds EVERY upstream socket to the
// actual VPN netId selected by this capability's interface. The original TUN
// forwarding loop remains live while the worker awaits real upstream bytes.
class DnsForwarder {
public:
    DnsForwarder(const NegotiatedConfig &config,std::vector<DnsPolicy> policies,
        int tun,const std::string &interface,const std::string &token,const std::string &profile)
        : config_(config),policies_(std::move(policies)),tun_(tun),interface_(interface),token_(token)
    {
        if(policies_.empty()){good_=true;return;}
        std::list<int32_t> ids;
        if(OHOS::NetManagerStandard::NetConnClient::GetInstance().GetNetIdByIdentifier(interface,ids)!=0 || ids.size()!=1)return;
        netId_=ids.front();if(netId_<=0)return;
        index_=if_nametoindex(interface.c_str());if(!index_)return;
        const auto slash=profile.rfind('/');
        if(slash==std::string::npos || profile.substr(0,slash).find("/data/service/el1/public/vpn/qemu_openvpn/session-")!=0 ||
            profile.substr(slash)!="/client.ovpn" || profile.find("..")!=std::string::npos)return;
        log_=open((profile.substr(0,slash)+"/dns-wire.jsonl").c_str(),O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC|O_NOFOLLOW,0600);
        if(log_<0 || !PrivateOwned(log_,false,1098))return;
        bool encrypted=false;for(const auto &p:policies_)encrypted=encrypted||p.transport!="plain";
        if(encrypted && !TrustProfile(profile))return;
        good_=true;worker_=std::thread([this](){Run();});
    }
    DnsForwarder(const DnsForwarder &)=delete;
    DnsForwarder &operator=(const DnsForwarder &)=delete;
    ~DnsForwarder()
    {
        closing_=true;condition_.notify_all();
        if(worker_.joinable())worker_.join();
        if(context_)SSL_CTX_free(context_);
        if(log_>=0)close(log_);
    }
    bool Good()const{return good_;}
    bool Handle(const unsigned char *packet,size_t length)
    {
        if(policies_.empty() || length<20)return false;
        DnsRequest r;r.family=packet[0]>>4;
        const unsigned char *destination=nullptr;unsigned protocol=0;
        if(r.family==4) {
            r.ip=(packet[0]&15)*4;
            if(r.ip<20 || length<r.ip || static_cast<size_t>(Dns16(packet+2))!=length)return false;
            destination=packet+16;protocol=packet[9];
        }else if(r.family==6) {
            if(length<40 || static_cast<size_t>(Dns16(packet+4))+40!=length)return false;
            r.ip=40;destination=packet+24;protocol=packet[6];
        }else return false;
        char address[INET6_ADDRSTRLEN]{};
        if(!inet_ntop(r.family==4?AF_INET:AF_INET6,destination,address,sizeof(address)))return false;
        if(std::find(config_.dns.begin(),config_.dns.end(),address)==config_.dns.end())return false;
        // Do not leak fragmented or TCP DNS as plaintext when a structured
        // policy is active. Ordinary non-DNS data still uses the original path.
        if((r.family==4 && (Dns16(packet+6)&0x3fff)) || (r.family==6 && protocol==44))return true;
        if(length<r.ip+8)return true;
        if(protocol==6 && Dns16(packet+r.ip+2)==53)return true;
        if(protocol!=17 || Dns16(packet+r.ip+2)!=53)return false;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            // A live upstream UDP53 socket is identified by its actual bound
            // local port. It must pass through the TUN, not recurse here.
            if(upstreamPort_ && Dns16(packet+r.ip)==upstreamPort_)return false;
        }
        if(Dns16(packet+r.ip+4)!=length-r.ip)return true; // malformed, fail closed
        r.packet.assign(packet,packet+length);r.question.assign(packet+r.ip+8,packet+length);
        if(!DnsQuestionName(r.question,r.host)){Respond(r,Failure(r.question));return true;}
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if(queue_.size()<32 && !closing_){queue_.push_back(std::move(r));condition_.notify_one();return true;}
        }
        Log(r,nullptr,nullptr,{},"queue-limit",0,0);Respond(r,Failure(r.question));return true;
    }
private:
    struct Socket { int fd=-1;~Socket(){if(fd>=0)close(fd);} };
    using Clock=std::chrono::steady_clock;
    NegotiatedConfig config_;std::vector<DnsPolicy> policies_;
    int tun_=-1,netId_=-1,log_=-1;unsigned index_=0;std::string interface_,token_;
    bool good_=false;SSL_CTX *context_=nullptr;
    std::thread worker_;std::atomic<bool> closing_{false};
    std::mutex mutex_,writeMutex_;std::condition_variable condition_;std::deque<DnsRequest> queue_;
    uint16_t upstreamPort_=0;
    std::atomic<uint32_t> actualMark_{0};
    std::string localAddress_;unsigned localPort_=0;
    static int64_t Now(){return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();}
    bool TrustProfile(const std::string &path)
    {
        Socket f;f.fd=open(path.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW);struct stat st{};
        if(f.fd<0 || !PrivateOwned(f.fd,false,1098) || fstat(f.fd,&st)!=0 || st.st_size<=0 || st.st_size>1024*1024)return false;
        std::string text(static_cast<size_t>(st.st_size),'\0');size_t at=0;
        while(at<text.size()){ssize_t n=read(f.fd,&text[at],text.size()-at);if(n<0&&errno==EINTR)continue;if(n<=0)return false;at+=n;}
        const auto begin=text.find("<ca>\n"),end=begin==std::string::npos?begin:text.find("</ca>",begin+5);
        if(begin==std::string::npos || end==std::string::npos || text.find("<ca>\n",begin+1)!=std::string::npos)return false;
        context_=SSL_CTX_new(TLS_client_method());if(!context_)return false;
        SSL_CTX_set_verify(context_,SSL_VERIFY_PEER,nullptr);
        if(SSL_CTX_set_min_proto_version(context_,TLS1_2_VERSION)!=1)return false;
        BIO *bio=BIO_new_mem_buf(text.data()+begin+5,static_cast<int>(end-begin-5));if(!bio)return false;
        bool added=false;X509 *cert=nullptr;
        while((cert=PEM_read_bio_X509(bio,nullptr,nullptr,nullptr))) {
            if(X509_STORE_add_cert(SSL_CTX_get_cert_store(context_),cert)==1)added=true;
            X509_free(cert);
        }
        BIO_free(bio);std::fill(text.begin(),text.end(),'\0');ERR_clear_error();return added;
    }
    bool Ready(int fd,short events,Clock::time_point end)
    {
        while(!closing_ && Clock::now()<end) {
            pollfd p{fd,events,0};int n=poll(&p,1,50);
            if(n>0)return !(p.revents&(POLLERR|POLLNVAL)) && (p.revents&events);
            if(n<0 && errno!=EINTR)return false;
        }return false;
    }
    bool Connect(Socket &socket,const DnsEndpoint &endpoint,bool tcp,Clock::time_point end)
    {
        const int family=IpFamily(endpoint.address);
        socket.fd=::socket(family,(tcp?SOCK_STREAM:SOCK_DGRAM)|SOCK_CLOEXEC|SOCK_NONBLOCK,0);
        if(socket.fd<0 || OHOS::NetManagerStandard::NetConnClient::GetInstance().BindSocket(socket.fd,netId_)!=0)return false;
        // The current NetConnClient discards FwmarkClient's return. Verify the
        // real socket mark instead of treating its outer zero as a binding.
        uint32_t mark=0;socklen_t markSize=sizeof(mark);
        if(getsockopt(socket.fd,SOL_SOCKET,SO_MARK,&mark,&markSize)!=0 || markSize!=sizeof(mark) ||
            (mark&0xffffu)!=static_cast<uint32_t>(netId_))return false;
        actualMark_=mark;
        sockaddr_storage remote{};socklen_t size=0;
        if(family==AF_INET){auto &v=*reinterpret_cast<sockaddr_in *>(&remote);v.sin_family=AF_INET;v.sin_port=htons(endpoint.port);inet_pton(AF_INET,endpoint.address.c_str(),&v.sin_addr);size=sizeof(v);}
        else {auto &v=*reinterpret_cast<sockaddr_in6 *>(&remote);v.sin6_family=AF_INET6;v.sin6_port=htons(endpoint.port);inet_pton(AF_INET6,endpoint.address.c_str(),&v.sin6_addr);size=sizeof(v);}
        if(connect(socket.fd,reinterpret_cast<sockaddr *>(&remote),size)!=0) {
            if(errno!=EINPROGRESS || !Ready(socket.fd,POLLOUT,end))return false;
            int error=0;socklen_t n=sizeof(error);if(getsockopt(socket.fd,SOL_SOCKET,SO_ERROR,&error,&n)!=0 || error)return false;
        }
        sockaddr_storage local{};socklen_t n=sizeof(local);char address[INET6_ADDRSTRLEN]{};
        if(getsockname(socket.fd,reinterpret_cast<sockaddr *>(&local),&n)!=0 ||
            !inet_ntop(family,family==AF_INET?static_cast<void *>(&reinterpret_cast<sockaddr_in *>(&local)->sin_addr):
                static_cast<void *>(&reinterpret_cast<sockaddr_in6 *>(&local)->sin6_addr),address,sizeof(address)))return false;
        {std::lock_guard<std::mutex> lock(mutex_);localAddress_=address;
            localPort_=ntohs(family==AF_INET?reinterpret_cast<sockaddr_in *>(&local)->sin_port:reinterpret_cast<sockaddr_in6 *>(&local)->sin6_port);
            if(!tcp)upstreamPort_=static_cast<uint16_t>(localPort_);}
        return true;
    }
    bool TlsWait(SSL *ssl,int result,int fd,Clock::time_point end)
    {
        const int error=SSL_get_error(ssl,result);
        return error==SSL_ERROR_WANT_READ?Ready(fd,POLLIN,end):error==SSL_ERROR_WANT_WRITE?Ready(fd,POLLOUT,end):false;
    }
    bool TlsWrite(SSL *ssl,int fd,const std::vector<unsigned char> &bytes,Clock::time_point end)
    {
        size_t at=0;while(at<bytes.size()&&!closing_){int n=SSL_write(ssl,bytes.data()+at,static_cast<int>(bytes.size()-at));if(n>0)at+=n;else if(!TlsWait(ssl,n,fd,end))return false;}return at==bytes.size();
    }
    bool TlsRead(SSL *ssl,int fd,unsigned char *bytes,size_t size,Clock::time_point end)
    {
        size_t at=0;while(at<size&&!closing_){int n=SSL_read(ssl,bytes+at,static_cast<int>(size-at));if(n>0)at+=n;else if(!TlsWait(ssl,n,fd,end))return false;}return at==size;
    }
    bool Exchange(const DnsRequest &request,const DnsPolicy &policy,const DnsEndpoint &endpoint,std::vector<unsigned char> &answer,std::string &error)
    {
        const auto end=Clock::now()+std::chrono::seconds(3);Socket socket;actualMark_=0;
        {std::lock_guard<std::mutex> lock(mutex_);localAddress_.clear();localPort_=0;}
        if(!Connect(socket,endpoint,policy.transport!="plain",end)){error="bind-or-connect";return false;}
        if(policy.transport=="plain") {
            if(!Ready(socket.fd,POLLOUT,end) || send(socket.fd,request.question.data(),request.question.size(),MSG_NOSIGNAL)!=static_cast<ssize_t>(request.question.size()) || !Ready(socket.fd,POLLIN,end)){error="udp-send-or-timeout";return false;}
            std::array<unsigned char,4097> bytes{};ssize_t n=recv(socket.fd,bytes.data(),bytes.size(),0);
            if(n<12 || n>4096){error="udp-size";return false;}answer.assign(bytes.begin(),bytes.begin()+n);return true;
        }
        SSL *ssl=SSL_new(context_);if(!ssl){error="tls-context";return false;}
        auto release=[&](){SSL_free(ssl);};
        const auto name=policy.sni.empty()?endpoint.address:policy.sni;
        bool identity=IpFamily(name)?X509_VERIFY_PARAM_set1_ip_asc(SSL_get0_param(ssl),name.c_str())==1:
            SSL_set_tlsext_host_name(ssl,name.c_str())==1 && SSL_set1_host(ssl,name.c_str())==1;
        if(!identity || SSL_set_fd(ssl,socket.fd)!=1){release();error="tls-identity-setup";return false;}
        int result=0;
        while((result=SSL_connect(ssl))!=1){if(!TlsWait(ssl,result,socket.fd,end)){error="tls-handshake:"+std::to_string(SSL_get_verify_result(ssl))+":"+std::to_string(ERR_get_error());release();return false;}}
        if(SSL_get_verify_result(ssl)!=X509_V_OK){release();error="tls-certificate-verification";return false;}
        if(policy.transport=="DoT") {
            std::vector<unsigned char> frame(2);PutDns16(frame.data(),request.question.size());frame.insert(frame.end(),request.question.begin(),request.question.end());
            unsigned char size[2]{};
            if(!TlsWrite(ssl,socket.fd,frame,end)||!TlsRead(ssl,socket.fd,size,2,end)||Dns16(size)<12||Dns16(size)>4096){release();error="dot-frame";return false;}
            answer.resize(Dns16(size));bool ok=TlsRead(ssl,socket.fd,answer.data(),answer.size(),end);release();if(!ok)error="dot-read";return ok;
        }
        const std::string header="POST /dns-query HTTP/1.1\r\nHost: "+name+"\r\nContent-Type: application/dns-message\r\nAccept: application/dns-message\r\nContent-Length: "+std::to_string(request.question.size())+"\r\nConnection: close\r\n\r\n";
        std::vector<unsigned char> frame(header.begin(),header.end());frame.insert(frame.end(),request.question.begin(),request.question.end());
        if(!TlsWrite(ssl,socket.fd,frame,end)){release();error="doh-write";return false;}
        std::string response;size_t boundary=std::string::npos;unsigned length=0;
        while(response.size()<8192 && !closing_) {
            unsigned char c=0;if(!TlsRead(ssl,socket.fd,&c,1,end)){release();error="doh-header";return false;}
            response+=static_cast<char>(c);boundary=response.find("\r\n\r\n");if(boundary!=std::string::npos)break;
        }
        if(boundary==std::string::npos || response.compare(0,13,"HTTP/1.1 200 ")!=0){release();error="doh-status";return false;}
        std::string lower=response;std::transform(lower.begin(),lower.end(),lower.begin(),[](unsigned char c){return std::tolower(c);});
        const auto content=lower.find("\r\ncontent-length: ");
        if(content==std::string::npos || lower.find("\r\ncontent-type: application/dns-message\r\n")==std::string::npos ||
            lower.find("\r\ntransfer-encoding:")!=std::string::npos ||
            lower.find("\r\ncontent-length:",content+2)!=std::string::npos ||
            lower.find("\r\ncontent-type:",lower.find("\r\ncontent-type:")+2)!=std::string::npos){release();error="doh-fields";return false;}
        const auto start=content+18,stop=lower.find("\r\n",start);
        if(stop==std::string::npos || !Number(lower.substr(start,stop-start),4096,length) || length<12){release();error="doh-length";return false;}
        answer.resize(length);bool ok=TlsRead(ssl,socket.fd,answer.data(),answer.size(),end);release();if(!ok)error="doh-body";return ok;
    }
    static std::vector<unsigned char> Failure(const std::vector<unsigned char> &q)
    {
        if(q.size()<12)return {};
        auto r=q;r[2]=(r[2]&1)|0x80;r[3]=0x82;for(size_t i=6;i<12;++i)r[i]=0;return r;
    }
    void Respond(const DnsRequest &r,const std::vector<unsigned char> &answer)
    {
        if(answer.empty() || answer.size()>4096 || r.packet.size()<r.ip+8)return;
        std::vector<unsigned char> packet(r.packet.begin(),r.packet.begin()+r.ip+8);
        packet.insert(packet.end(),answer.begin(),answer.end());const unsigned total=packet.size(),udp=total-r.ip;
        if(r.family==4){for(unsigned i=0;i<4;++i)std::swap(packet[12+i],packet[16+i]);PutDns16(packet.data()+2,total);packet[10]=packet[11]=0;PutDns16(packet.data()+10,PacketChecksum(packet.data(),r.ip));}
        else {for(unsigned i=0;i<16;++i)std::swap(packet[8+i],packet[24+i]);PutDns16(packet.data()+4,total-40);}
        std::swap(packet[r.ip],packet[r.ip+2]);std::swap(packet[r.ip+1],packet[r.ip+3]);PutDns16(packet.data()+r.ip+4,udp);packet[r.ip+6]=packet[r.ip+7]=0;
        unsigned pseudo=17+udp;const size_t begin=r.family==4?12:8,end=r.family==4?20:40;
        for(size_t i=begin;i<end;i+=2)pseudo+=Dns16(packet.data()+i);
        uint16_t sum=PacketChecksum(packet.data()+r.ip,udp,pseudo);PutDns16(packet.data()+r.ip+6,sum?sum:65535);
        std::lock_guard<std::mutex> lock(writeMutex_);
        if(write(tun_,packet.data(),packet.size())!=static_cast<ssize_t>(packet.size()))closing_=true;
    }
    void Log(const DnsRequest &r,const DnsPolicy *policy,const DnsEndpoint *endpoint,const std::vector<unsigned char> &answer,const std::string &error,int64_t start,int64_t end)
    {
        if(log_<0)return;
        std::string local;unsigned port=0;
        {std::lock_guard<std::mutex> lock(mutex_);local=localAddress_;port=localPort_;}
        const std::string line="{\"kind\":\"dns\",\"generation\":\""+token_+"\",\"pid\":"+std::to_string(getpid())+
            ",\"uid\":"+std::to_string(getuid())+",\"tid\":"+std::to_string(syscall(SYS_gettid))+",\"net_id\":"+std::to_string(netId_)+",\"socket_mark\":"+std::to_string(actualMark_.load())+",\"local_address\":\""+local+"\",\"local_port\":"+std::to_string(port)+
            ",\"ifindex\":"+std::to_string(index_)+",\"transport\":\""+(policy?policy->transport:"")+"\",\"address\":\""+(endpoint?endpoint->address:"")+
            "\",\"port\":"+std::to_string(endpoint?endpoint->port:0)+",\"sni\":\""+(policy?policy->sni:"")+"\",\"question_hex\":\""+HexDns(r.question)+
            "\",\"answer_hex\":\""+HexDns(answer)+"\",\"error\":\""+error+"\",\"start_ns\":"+std::to_string(start)+",\"end_ns\":"+std::to_string(end)+"}\n";
        struct stat size{};
        if(fstat(log_,&size)!=0 || size.st_size<0 || size.st_size+static_cast<off_t>(line.size())>16*1024*1024 ||
            write(log_,line.data(),line.size())!=static_cast<ssize_t>(line.size()))closing_=true;
    }
    void Run()
    {
        while(!closing_) {
            DnsRequest r;
            {std::unique_lock<std::mutex> lock(mutex_);condition_.wait_for(lock,std::chrono::milliseconds(100),[&](){return closing_||!queue_.empty();});
                if(closing_)break;if(queue_.empty())continue;r=std::move(queue_.front());queue_.pop_front();}
            const auto *policy=ChooseDnsPolicy(policies_,r.host);const DnsEndpoint *used=nullptr;
            std::vector<unsigned char> answer;std::string error="no-matching-dns-policy";const auto started=Now();
            if(policy)for(const auto &endpoint:policy->endpoints) {
                used=&endpoint;error.clear();
                const bool exchanged=Exchange(r,*policy,endpoint,answer,error);
                {std::lock_guard<std::mutex> lock(mutex_);upstreamPort_=0;}
                size_t questionEnd=12;
                while(questionEnd<r.question.size() && r.question[questionEnd])questionEnd+=1+r.question[questionEnd];
                questionEnd+=5;
                if(exchanged && answer.size()>=questionEnd && answer[0]==r.question[0] && answer[1]==r.question[1] &&
                    (answer[2]&0x80) && Dns16(answer.data()+4)==1 &&
                    std::equal(r.question.begin()+12,r.question.begin()+questionEnd,answer.begin()+12))break;
                if(error.empty())error="foreign-dns-response";answer.clear();
                // Encrypted authentication failure must NEVER fall back to a
                // plain server or change policy; only this policy's endpoints.
            }
            Log(r,policy,used,answer,error,started,Now());Respond(r,error.empty()?answer:Failure(r.question));
        }
    }
};
} // namespace OhosOpenvpn
