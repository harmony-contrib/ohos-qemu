/* Source-only root-owned QEMU fixture. No platform provider is replaced.
 * Initial-netns radios keep their original hwsim netgroup when wiphy moves.
 * Peer sockets live ONLY in the isolated netns. Every wire packet is retained.
 * Fixed finite modes; no system(), shell, fork(), arbitrary exec/path/network.
 */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <ifaddrs.h>
#include <linux/genetlink.h>
#include <linux/netlink.h>
#include <linux/nl80211.h>
#include <linux/if_packet.h>
#include <net/ethernet.h>
#include <net/if.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

static char run[33], directory[128];
static FILE *journal;
static uint64_t sequence;
static uint32_t nl_sequence;
static const char *peer_if = "s579peer";
static volatile sig_atomic_t stopping;
static void signal_stop(int value) { (void)value; stopping = 1; }
static void check(int ok, const char *why) { if (!ok) { perror(why); exit(2); } }
static unsigned long ns_inode(void) { struct stat st; check(stat("/proc/self/ns/net", &st) == 0, "stat netns"); return (unsigned long)st.st_ino; }
static void event(const char *name, const void *data, size_t len) {
    check(len <= 8192, "bounded raw record");
    struct timespec now; check(clock_gettime(CLOCK_MONOTONIC, &now) == 0, "clock");
    fprintf(journal, "{\"run_id\":\"%s\",\"seq\":%llu,\"pid\":%d,\"uid\":%d,\"netns\":%lu,\"monotonic_ms\":%lld,\"event\":\"%s\",\"hex\":\"",
        run, (unsigned long long)sequence++, getpid(), getuid(), ns_inode(), (long long)now.tv_sec*1000+now.tv_nsec/1000000, name);
    const unsigned char *bytes = data;
    for (size_t i=0; i<len; ++i) fprintf(journal, "%02x", bytes[i]);
    fputs("\"}\n", journal); fflush(journal); check(fsync(fileno(journal)) == 0, "sync actual journal");
}
static void text(const char *name, const char *data) { event(name, data, strlen(data)); }
static long number(const char *value, long min, long max) {
    char *end; errno=0; long result=strtol(value,&end,10);
    check(!errno && *value && !*end && result>=min && result<=max,"bounded integer"); return result;
}
static int open_owned(const char *leaf, int flags) {
    char path[256]; check(snprintf(path,sizeof(path),"%s/%s",directory,leaf)>0,"path");
    int fd=open(path,flags|O_CLOEXEC|O_NOFOLLOW,0600); check(fd>=0,"owned regular file");
    struct stat st; check(fstat(fd,&st)==0 && S_ISREG(st.st_mode) && st.st_uid==0,"owned file identity"); return fd;
}
static void initialize(const char *nonce, const char *mode) {
    check(strlen(nonce)==32,"nonce length");
    for (int i=0;i<32;++i) check((nonce[i]>='a'&&nonce[i]<='f')||(nonce[i]>='0'&&nonce[i]<='9'),"nonce chars");
    memcpy(run,nonce,33); snprintf(directory,sizeof(directory),"/data/local/tmp/apps579_wifi_%s",run);
    struct stat st; check(lstat(directory,&st)==0 && S_ISDIR(st.st_mode) && st.st_uid==0 && (st.st_mode&0777)==0700,"fresh root-owned fixture directory");
    char leaf[64]; check(snprintf(leaf,sizeof(leaf),"%s-%d.jsonl",mode,getpid())>0,"journal name");
    journal=fdopen(open_owned(leaf,O_WRONLY|O_CREAT|O_EXCL),"w"); check(journal!=NULL,"journal stream");
    signal(SIGTERM,signal_stop); signal(SIGINT,signal_stop); signal(SIGPIPE,SIG_IGN);
    text("mode",mode);
}
static int control_stop(void) {
    static char line[80];static size_t used;
    ssize_t n=read(STDIN_FILENO,line+used,sizeof(line)-1-used);
    if (n==0) { check(!used,"no truncated owner command on EOF");return 1; }
    if(n<0) { if(errno==EINTR) return stopping; check(0,"held stdin"); }
    used+=(size_t)n;line[used]=0;char expected[64];snprintf(expected,sizeof(expected),"QUIT %s\n",run);
    check(used<=strlen(expected) && !memcmp(line,expected,used),"finite owner QUIT protocol");
    if(used<strlen(expected))return 0;text("owner-quit",line);return 1;
}
static void enter_peer(int pid) {
    char command[4096], path[64];snprintf(path,sizeof(path),"/proc/%d/cmdline",pid);
    int fd=open(path,O_RDONLY|O_CLOEXEC);check(fd>=0,"held peer cmdline");ssize_t n=read(fd,command,sizeof(command)-1);close(fd);
    check(n>0,"held namespace process");for(ssize_t i=0;i<n;++i)if(!command[i])command[i]=' ';command[n]=0;
    check(strstr(command," hold ") && strstr(command,run),"exact live namespace-holder nonce");
    snprintf(path,sizeof(path),"/proc/%d/ns/net",pid);fd=open(path,O_RDONLY|O_CLOEXEC);check(fd>=0,"held netns descriptor");
    unsigned long before=ns_inode();check(setns(fd,CLONE_NEWNET)==0,"enter actual peer netns");close(fd);
    check(ns_inode()!=before,"peer must be independent from initial network stack");text("entered-peer",command);
}
static int p2p_interface(const char *name) {
    int valid=!strcmp(name,"p2p0");
    const char *prefix="p2p-wlan0-";
    if(!strncmp(name,prefix,strlen(prefix))){const char *p=name+strlen(prefix);valid=*p!=0;for(;*p;++p)valid=valid&&*p>='0'&&*p<='9';}
    if(!valid || strlen(name)>=IFNAMSIZ)return 0;
    char path[128];snprintf(path,sizeof(path),"/sys/class/net/%s/phy80211",name);
    struct stat actual,original;
    check(stat(path,&actual)==0 && stat("/sys/class/net/wlan0/phy80211",&original)==0 && actual.st_dev==original.st_dev && actual.st_ino==original.st_ino,"P2P interface must be the OS radio's actual wiphy");
    text("actual-p2p-interface",name);return 1;
}
static int interface_socket(const char *name) {
    check(!strcmp(name,"wlan0")||!strcmp(name,"wlan1")||!strcmp(name,peer_if)||!strcmp(name,"lo")||p2p_interface(name),"finite radio interface");
    int fd=socket(AF_INET,SOCK_DGRAM|SOCK_CLOEXEC,0);check(fd>=0,"interface socket");return fd;
}
static void flags_up(const char *name) {
    int fd=interface_socket(name);struct ifreq req={0};strncpy(req.ifr_name,name,IFNAMSIZ-1);
    check(ioctl(fd,SIOCGIFFLAGS,&req)==0,"read flags");req.ifr_flags|=IFF_UP;
    check(ioctl(fd,SIOCSIFFLAGS,&req)==0,"set actual interface up");close(fd);
}
static void clear_peer_ipv4(void) {
    int fd=interface_socket(peer_if);struct ifreq req={0};strncpy(req.ifr_name,peer_if,IFNAMSIZ-1);
    ((struct sockaddr_in*)&req.ifr_addr)->sin_family=AF_INET;
    check(ioctl(fd,SIOCSIFADDR,&req)==0,"remove only peer's fixture IPv4 address");close(fd);
}
static void ipv4(const char *name, uint32_t addr, uint32_t mask) {
    int fd=interface_socket(name);struct ifreq req={0};strncpy(req.ifr_name,name,IFNAMSIZ-1);
    struct sockaddr_in *ip=(struct sockaddr_in *)&req.ifr_addr;ip->sin_family=AF_INET;ip->sin_addr.s_addr=addr;
    check(ioctl(fd,SIOCSIFADDR,&req)==0,"configure actual IPv4");ip->sin_addr.s_addr=mask;
    check(ioctl(fd,SIOCSIFNETMASK,&req)==0,"configure actual mask");close(fd);flags_up(name);
}
static uint32_t own_ip(const char *name) {
    int fd=interface_socket(name);struct ifreq req={0};strncpy(req.ifr_name,name,IFNAMSIZ-1);
    check(ioctl(fd,SIOCGIFADDR,&req)==0,"read actual interface address");close(fd);
    return ((struct sockaddr_in *)&req.ifr_addr)->sin_addr.s_addr;
}
static void inspect(void) {
    if(if_nametoindex(peer_if)){int fd=interface_socket(peer_if);struct ifreq req={0};strncpy(req.ifr_name,peer_if,IFNAMSIZ-1);check(ioctl(fd,SIOCGIFHWADDR,&req)==0,"actual peer interface MAC");
        const unsigned char *a=(const unsigned char*)req.ifr_hwaddr.sa_data;char mac[32];snprintf(mac,sizeof(mac),"%02x:%02x:%02x:%02x:%02x:%02x",a[0],a[1],a[2],a[3],a[4],a[5]);text("interface-mac",mac);close(fd);}
    struct ifaddrs *head; check(getifaddrs(&head)==0,"actual addresses");
    for(struct ifaddrs *p=head;p;p=p->ifa_next)if(p->ifa_addr && p->ifa_addr->sa_family==AF_INET) {
        char value[128],addr[INET_ADDRSTRLEN];inet_ntop(AF_INET,&((struct sockaddr_in*)p->ifa_addr)->sin_addr,addr,sizeof(addr));
        snprintf(value,sizeof(value),"%s %s flags=%u",p->ifa_name,addr,p->ifa_flags);text("interface-ipv4",value);
    }freeifaddrs(head);
    for(int kind=0;kind<3;++kind){const char *path=kind==0?"/proc/net/route":kind==1?"/proc/net/arp":"/proc/net/dev";
        int fd=open(path,O_RDONLY|O_CLOEXEC);check(fd>=0,"kernel snapshot");char buf[8192];ssize_t n=read(fd,buf,sizeof(buf));close(fd);
        check(n>=0,"kernel snapshot read");event(kind==0?"kernel-route":kind==1?"kernel-arp":"kernel-dev",buf,(size_t)n);
    }
}
static void attr(struct nlmsghdr *h,int type,const void *data,size_t len) {
    size_t offset=NLMSG_ALIGN(h->nlmsg_len),size=NLA_HDRLEN+len;check(offset+NLA_ALIGN(size)<=4096,"netlink budget");
    struct nlattr *a=(struct nlattr*)((char*)h+offset);a->nla_type=(uint16_t)type;a->nla_len=(uint16_t)size;
    memcpy((char*)a+NLA_HDRLEN,data,len);h->nlmsg_len=(uint32_t)(offset+NLA_ALIGN(size));
}
static int genl_request(int fd,int family,int cmd,const char *family_name,int phy,int pid) {
    char buffer[4096]={0};struct nlmsghdr *h=(struct nlmsghdr*)buffer;struct genlmsghdr *g=NLMSG_DATA(h);
    h->nlmsg_len=NLMSG_LENGTH(sizeof(*g));h->nlmsg_type=(uint16_t)family;h->nlmsg_flags=NLM_F_REQUEST|NLM_F_ACK;h->nlmsg_seq=++nl_sequence;uint32_t request_sequence=h->nlmsg_seq;g->cmd=(uint8_t)cmd;g->version=1;
    if(family_name) attr(h,CTRL_ATTR_FAMILY_NAME,family_name,strlen(family_name)+1);
    else { attr(h,NL80211_ATTR_WIPHY,&phy,sizeof(phy));attr(h,NL80211_ATTR_PID,&pid,sizeof(pid)); }
    struct sockaddr_nl kernel={.nl_family=AF_NETLINK};
    event("netlink-request",h,h->nlmsg_len);check(sendto(fd,h,h->nlmsg_len,0,(struct sockaddr*)&kernel,sizeof(kernel))==(ssize_t)h->nlmsg_len,"actual nl80211 send");
    for(;;){ssize_t n=recv(fd,buffer,sizeof(buffer),0);check(n>0,"actual nl80211 reply");event("netlink-response",buffer,(size_t)n);
        for(h=(struct nlmsghdr*)buffer;NLMSG_OK(h,n);h=NLMSG_NEXT(h,n)){
            if(h->nlmsg_seq!=request_sequence)continue;
            if(h->nlmsg_type==NLMSG_ERROR){struct nlmsgerr *e=NLMSG_DATA(h);check(h->nlmsg_len>=NLMSG_LENGTH(sizeof(*e)),"netlink error bounds");
                if(e->error){errno=-e->error;check(0,"kernel nl80211 rejected operation");}if(!family_name)return 0;
            } else if(family_name){int left=(int)h->nlmsg_len-(int)NLMSG_LENGTH(sizeof(*g));
                for(struct nlattr *a=(struct nlattr*)((char*)NLMSG_DATA(h)+GENL_HDRLEN);left>=(int)NLA_HDRLEN && a->nla_len>=(int)NLA_HDRLEN && a->nla_len<=left;left-=NLA_ALIGN(a->nla_len),a=(struct nlattr*)((char*)a+NLA_ALIGN(a->nla_len)))
                    if(a->nla_type==CTRL_ATTR_FAMILY_ID){uint16_t result;check(a->nla_len>=NLA_HDRLEN+sizeof(result),"family id bounds");memcpy(&result,(char*)a+NLA_HDRLEN,sizeof(result));return result;}
            }
        }
    }
}
static void move_phy(int phy,int destination) {
    int fd=socket(AF_NETLINK,SOCK_RAW|SOCK_CLOEXEC,NETLINK_GENERIC);check(fd>=0,"genl socket");
    struct timeval timeout={.tv_sec=10};check(setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout))==0,"netlink timeout");
    int family=genl_request(fd,GENL_ID_CTRL,CTRL_CMD_GETFAMILY,"nl80211",0,0);
    genl_request(fd,family,NL80211_CMD_SET_WIPHY_NETNS,NULL,phy,destination);close(fd);
}
static void move_out(int phy,int destination) {
    int fd=interface_socket("wlan1");struct ifreq req={0};strncpy(req.ifr_name,"wlan1",IFNAMSIZ-1);
    check(ioctl(fd,SIOCGIFFLAGS,&req)==0 && !(req.ifr_flags&IFF_UP),"only idle spare wlan1 may move");
    strncpy(req.ifr_newname,peer_if,IFNAMSIZ-1);check(ioctl(fd,SIOCSIFNAME,&req)==0,"rename only spare peer interface");close(fd);
    move_phy(phy,destination);text("peer-moved","wlan1 -> s579peer via actual nl80211");
}
static int bound_socket(int kind,int port,const char *name,uint32_t address) {
    int fd=socket(AF_INET,kind|SOCK_CLOEXEC,0);check(fd>=0,"wire socket");int one=1;
    check(setsockopt(fd,SOL_SOCKET,SO_REUSEADDR,&one,sizeof(one))==0,"socket reuse");
    check(setsockopt(fd,SOL_SOCKET,SO_BINDTODEVICE,name,strlen(name)+1)==0,"bind actual radio interface");
    if(kind==SOCK_DGRAM)check(setsockopt(fd,SOL_SOCKET,SO_BROADCAST,&one,sizeof(one))==0,"DHCP broadcast");
    struct sockaddr_in local={.sin_family=AF_INET,.sin_port=htons((uint16_t)port),.sin_addr={.s_addr=address}};
    check(bind(fd,(struct sockaddr*)&local,sizeof(local))==0,"bind actual endpoint");return fd;
}
struct __attribute__((packed)) bootp {
    uint8_t op,htype,hlen,hops;uint32_t xid;uint16_t secs,flags;uint32_t ciaddr,yiaddr,siaddr,giaddr;
    uint8_t chaddr[16],sname[64],file[128];uint32_t cookie;uint8_t opts[312];
};
static int option(const struct bootp *p,size_t length,int code,void *dest,size_t wanted) {
    if(length<240 || p->cookie!=htonl(0x63825363))return 0;
    for(size_t i=0;i<length-240 && i<sizeof(p->opts);){int type=p->opts[i++];if(type==255)break;if(!type)continue;
        if(i>=length-240)return 0;size_t n=p->opts[i++];if(i+n>length-240 || i+n>sizeof(p->opts))return 0;
        if(type==code){if(n!=wanted)return 0;memcpy(dest,p->opts+i,wanted);return 1;}i+=n;
    }return 0;
}
static void put_option(struct bootp *p,size_t *n,int type,const void *data,size_t len){check(*n+2+len<sizeof(p->opts),"DHCP option budget");p->opts[(*n)++]=(uint8_t)type;p->opts[(*n)++]=(uint8_t)len;memcpy(p->opts+*n,data,len);*n+=len;}
static size_t dhcp_options(struct bootp *p,int type,uint32_t server,uint32_t requested,int is_server) {
    size_t n=0;uint8_t kind=(uint8_t)type;put_option(p,&n,53,&kind,1);put_option(p,&n,54,&server,4);
    if(requested)put_option(p,&n,50,&requested,4);
    if(is_server){uint32_t mask=inet_addr("255.255.255.0"),lease=htonl(300);put_option(p,&n,1,&mask,4);put_option(p,&n,3,&server,4);put_option(p,&n,6,&server,4);put_option(p,&n,51,&lease,4);}
    p->opts[n++]=255;return 240+n;
}
static void dhcp_server(int fd) {
    struct bootp received={0};struct sockaddr_in source;socklen_t slen=sizeof(source);ssize_t length=recvfrom(fd,&received,sizeof(received),0,(struct sockaddr*)&source,&slen);
    check(length>=0,"DHCP server receive");event("dhcp-server-rx",&received,(size_t)length);uint8_t kind=0;
    if(length<240 || received.op!=1 || received.htype!=1 || received.hlen!=6 || !option(&received,(size_t)length,53,&kind,1))return;
    if(kind!=1 && kind!=3)return;
    uint32_t server=inet_addr("192.0.2.1"),address=inet_addr("192.0.2.2"),requested=0,server_id=0;
    if(kind==3){if(!option(&received,(size_t)length,50,&requested,4))requested=received.ciaddr;
        if(option(&received,(size_t)length,54,&server_id,4) && server_id!=server)return;
        if(requested!=address)return;
    }
    struct bootp reply=received;reply.op=2;reply.yiaddr=address;reply.siaddr=server;reply.cookie=htonl(0x63825363);memset(reply.opts,0,sizeof(reply.opts));
    size_t bytes=dhcp_options(&reply,kind==1?2:5,server,0,1);
    struct sockaddr_in to={.sin_family=AF_INET,.sin_port=htons(68),.sin_addr={.s_addr=INADDR_BROADCAST}};
    event("dhcp-server-tx",&reply,bytes);check(sendto(fd,&reply,bytes,0,(struct sockaddr*)&to,sizeof(to))==(ssize_t)bytes,"DHCP server actual broadcast");
    if(kind==3)text("dhcp-server-ack","192.0.2.2/24 router/dns 192.0.2.1");
}
static void dhcp_client(void) {
    /* A real independent L2 client starts without any IPv4 route. Never use
     * the prior AP address or the initial-netns DHCP SA as a shortcut. */
    clear_peer_ipv4();flags_up(peer_if);inspect();
    int fd=socket(AF_PACKET,SOCK_RAW|SOCK_CLOEXEC,htons(ETH_P_IP));check(fd>=0,"independent DHCP packet socket");
    struct sockaddr_ll radio={.sll_family=AF_PACKET,.sll_protocol=htons(ETH_P_IP),.sll_ifindex=(int)if_nametoindex(peer_if),.sll_halen=6};
    memset(radio.sll_addr,0xff,6);check(radio.sll_ifindex>0 && bind(fd,(struct sockaddr*)&radio,sizeof(radio))==0,"DHCP only on actual isolated radio");
    struct bootp request={.op=1,.htype=1,.hlen=6,.flags=htons(0x8000),.cookie=htonl(0x63825363)};
    int random=open("/dev/urandom",O_RDONLY|O_CLOEXEC);check(random>=0 && read(random,&request.xid,4)==4,"real DHCP transaction id");close(random);
    int ctl=interface_socket(peer_if);struct ifreq req={0};strncpy(req.ifr_name,peer_if,IFNAMSIZ-1);check(ioctl(ctl,SIOCGIFHWADDR,&req)==0,"actual peer MAC");memcpy(request.chaddr,req.ifr_hwaddr.sa_data,6);close(ctl);
    uint32_t server=0,address=0,mask=0,router=0,dns=0;int state=1;
    for(int attempts=0;attempts<20 && !stopping;++attempts){size_t size=dhcp_options(&request,state==1?1:3,server,address,0);
        /* DISCOVER must not contain a zero server-identifier. */
        if(state==1){size_t n=0;uint8_t kind=1;put_option(&request,&n,53,&kind,1);uint8_t want[]={1,3,6,51,54};put_option(&request,&n,55,want,sizeof(want));request.opts[n++]=255;size=240+n;}
        unsigned char frame[1536]={0};memset(frame,0xff,6);memcpy(frame+6,request.chaddr,6);frame[12]=8;frame[13]=0;
        unsigned char *ip=frame+14,*udp=ip+20;size_t ip_size=20+8+size;ip[0]=0x45;ip[2]=(unsigned char)(ip_size>>8);ip[3]=(unsigned char)ip_size;ip[8]=64;ip[9]=17;memset(ip+16,0xff,4);
        uint32_t sum=0;for(size_t i=0;i<20;i+=2)sum+=((uint32_t)ip[i]<<8)|ip[i+1];while(sum>>16)sum=(sum&0xffff)+(sum>>16);sum=(~sum)&0xffff;ip[10]=(unsigned char)(sum>>8);ip[11]=(unsigned char)sum;
        udp[1]=68;udp[3]=67;udp[4]=(unsigned char)((8+size)>>8);udp[5]=(unsigned char)(8+size);memcpy(udp+8,&request,size);
        event("dhcp-client-tx",&request,size);event("dhcp-client-radio-tx",frame,14+ip_size);
        check(sendto(fd,frame,14+ip_size,0,(struct sockaddr*)&radio,sizeof(radio))==(ssize_t)(14+ip_size),"actual DHCP client L2 broadcast");
        struct pollfd poller={.fd=fd,.events=POLLIN};int ready=poll(&poller,1,3000);if(ready<0 && errno==EINTR)continue;check(ready>=0,"DHCP client poll");if(!ready)continue;
        unsigned char wire[2048];ssize_t wire_size=recv(fd,wire,sizeof(wire),0);check(wire_size>=0,"DHCP actual radio receive");event("dhcp-client-radio-rx",wire,(size_t)wire_size);
        if(wire_size<42 || wire[12]!=8 || wire[13]!=0 || (wire[14]>>4)!=4 || wire[23]!=17)continue;
        size_t ihl=(wire[14]&15)*4;size_t offset=14+ihl;
        if(ihl<20 || offset+8>(size_t)wire_size || (wire[20]&0x3f) || wire[21] || wire[offset]!=0 || wire[offset+1]!=67 || wire[offset+2]!=0 || wire[offset+3]!=68)continue;
        size_t udp_size=((size_t)wire[offset+4]<<8)|wire[offset+5];if(udp_size<8 || offset+udp_size>(size_t)wire_size)continue;
        struct bootp response={0};ssize_t n=(ssize_t)(udp_size-8);if((size_t)n>sizeof(response))continue;memcpy(&response,wire+offset+8,(size_t)n);event("dhcp-client-rx",&response,(size_t)n);uint8_t type=0;
        if(n<240 || response.op!=2 || response.xid!=request.xid || memcmp(response.chaddr,request.chaddr,6) || !option(&response,(size_t)n,53,&type,1))continue;
        if(state==1 && type==2){check(response.yiaddr && option(&response,(size_t)n,54,&server,4),"real DHCP offer identity");address=response.yiaddr;state=3;continue;}
        if(state==3 && type==5){uint32_t ack_server;check(response.yiaddr==address && option(&response,(size_t)n,54,&ack_server,4) && ack_server==server && option(&response,(size_t)n,1,&mask,4) && option(&response,(size_t)n,3,&router,4),"real DHCP ACK contents");
            option(&response,(size_t)n,6,&dns,4);ipv4(peer_if,address,mask);char line[256],a[32],s[32],m[32],r[32],d[32];
            inet_ntop(AF_INET,&address,a,sizeof(a));inet_ntop(AF_INET,&server,s,sizeof(s));inet_ntop(AF_INET,&mask,m,sizeof(m));inet_ntop(AF_INET,&router,r,sizeof(r));inet_ntop(AF_INET,&dns,d,sizeof(d));
            snprintf(line,sizeof(line),"address=%s mask=%s server=%s router=%s dns=%s",a,m,s,r,d);text("dhcp-client-bound",line);
            int out=open_owned("dhcp-client.txt",O_WRONLY|O_CREAT|O_EXCL);check(write(out,line,strlen(line))==(ssize_t)strlen(line),"write actual DHCP lease");close(out);close(fd);return;
        }
    }check(0,"actual DHCP DORA did not finish");
}
static void dns_server(int fd) {
    unsigned char packet[1024];struct sockaddr_in from;socklen_t slen=sizeof(from);ssize_t n=recvfrom(fd,packet,sizeof(packet),0,(struct sockaddr*)&from,&slen);check(n>=0,"DNS receive");event("dns-rx",packet,(size_t)n);
    if(n<17 || packet[4]!=0 || packet[5]!=1)return;size_t end=12;
    while(end<(size_t)n && packet[end]){unsigned len=packet[end];if(len>63 || end+len+1>=(size_t)n)return;end+=len+1;}
    if(end+5>(size_t)n)return;end+=5;
    unsigned type=(packet[end-4]<<8)|packet[end-3];packet[2]=0x81;packet[3]=0x80;packet[6]=0;packet[7]=type==1?1:0;packet[8]=packet[9]=packet[10]=packet[11]=0;
    if(type==1){unsigned char answer[]={0xc0,0x0c,0,1,0,1,0,0,0,5,0,4,192,0,2,1};memcpy(packet+end,answer,sizeof(answer));end+=sizeof(answer);}
    event("dns-tx",packet,end);check(sendto(fd,packet,end,0,(struct sockaddr*)&from,slen)==(ssize_t)end,"actual DNS reply");
}
static void udp_server(int fd) {
    unsigned char packet[2048];struct sockaddr_in from;socklen_t slen=sizeof(from);ssize_t n=recvfrom(fd,packet,sizeof(packet),0,(struct sockaddr*)&from,&slen);check(n>=0,"nonce receive");event("nonce-peer-rx",packet,(size_t)n);
    char prefix[64];snprintf(prefix,sizeof(prefix),"APPS579:%s:",run);if(n<(ssize_t)strlen(prefix)||memcmp(packet,prefix,strlen(prefix)))return;
    check((size_t)n+6<sizeof(packet),"bounded nonce payload");memcpy(packet+n,":reply",6);event("nonce-peer-tx",packet,(size_t)n+6);
    check(sendto(fd,packet,(size_t)n+6,0,(struct sockaddr*)&from,slen)==n+6,"nonce actual peer reply");
}
static int authorized;
static void http_server(int listener) {
    struct sockaddr_in from;socklen_t slen=sizeof(from);int fd=accept4(listener,(struct sockaddr*)&from,&slen,SOCK_CLOEXEC);check(fd>=0,"HTTP peer accept");
    struct timeval timeout={.tv_sec=5};setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));char request[4096]={0};size_t used=0;
    while(used<sizeof(request)-1 && !strstr(request,"\r\n\r\n")){ssize_t n=recv(fd,request+used,sizeof(request)-1-used,0);if(n<=0)break;used+=(size_t)n;request[used]=0;}
    event("http-peer-request",request,used);char login[96],allow[96],probe[96];snprintf(login,sizeof(login),"GET /login/%s ",run);snprintf(allow,sizeof(allow),"GET /allow/%s ",run);snprintf(probe,sizeof(probe),"GET /probe/%s",run);
    char response[4096],body[2048];const char *status="400 Bad Request";char location[256]="";body[0]=0;
    if(!strncmp(request,allow,strlen(allow))){authorized=1;status="200 OK";snprintf(body,sizeof(body),"<html><body>Authenticated %s</body></html>",run);text("portal-user-authenticated",run);}
    else if(!strncmp(request,login,strlen(login))){status="200 OK";snprintf(body,sizeof(body),"<html><meta name=viewport content='width=device-width'><body><h1>QEMU WiFi %s</h1><a style='font-size:36px' href='/allow/%s'>Allow WiFi %s</a></body></html>",run,run,run);}
    else if(!strncmp(request,probe,strlen(probe))){if(authorized)status="204 No Content";else{status="302 Found";snprintf(location,sizeof(location),"Location: http://login.apps579.invalid/login/%s\r\n",run);}}
    int count=snprintf(response,sizeof(response),"HTTP/1.1 %s\r\n%sContent-Type: text/html; charset=utf-8\r\nContent-Length: %zu\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n%s",status,location,strlen(body),body);
    check(count>0 && count<(int)sizeof(response),"bounded HTTP response");event("http-peer-response",response,(size_t)count);
    size_t sent=0;while(sent<(size_t)count){ssize_t n=send(fd,response+sent,(size_t)count-sent,MSG_NOSIGNAL);if(n<=0)break;sent+=(size_t)n;}
    close(fd);
}
static void server(int ap) {
    if(ap)ipv4(peer_if,inet_addr("192.0.2.1"),inet_addr("255.255.255.0"));else dhcp_client();
    inspect();int udp=bound_socket(SOCK_DGRAM,36979,peer_if,own_ip(peer_if));
    int dhcp=ap?bound_socket(SOCK_DGRAM,67,peer_if,INADDR_ANY):-1;
    int dns=ap?bound_socket(SOCK_DGRAM,53,peer_if,INADDR_ANY):-1;
    int http=ap?bound_socket(SOCK_STREAM,80,peer_if,own_ip(peer_if)):-1;if(ap)check(listen(http,8)==0,"actual HTTP listener");
    int wire=socket(AF_PACKET,SOCK_RAW|SOCK_CLOEXEC,htons(ETH_P_ALL));check(wire>=0,"actual radio packet capture");
    struct sockaddr_ll link={.sll_family=AF_PACKET,.sll_protocol=htons(ETH_P_ALL),.sll_ifindex=(int)if_nametoindex(peer_if)};
    check(link.sll_ifindex>0 && bind(wire,(struct sockaddr*)&link,sizeof(link))==0,"capture only isolated actual radio");
    text("peer-ready",ap?"ap":"sta");int marker=open_owned(ap?"ap-ready":"sta-ready",O_WRONLY|O_CREAT|O_EXCL);char value[96];int len=snprintf(value,sizeof(value),"pid=%d netns=%lu",getpid(),ns_inode());check(write(marker,value,(size_t)len)==len,"ready marker");close(marker);
    while(!stopping){struct pollfd fds[]={{0,POLLIN,0},{udp,POLLIN,0},{dhcp,POLLIN,0},{dns,POLLIN,0},{http,POLLIN,0},{wire,POLLIN,0}};int ready=poll(fds,6,500);if(ready<0 && errno==EINTR)continue;check(ready>=0,"real peer poll");
        if(fds[0].revents&(POLLIN|POLLHUP)){if(control_stop())break;}
        if(fds[1].revents&POLLIN)udp_server(udp);if(fds[2].revents&POLLIN)dhcp_server(dhcp);if(fds[3].revents&POLLIN)dns_server(dns);if(fds[4].revents&POLLIN)http_server(http);
        if(fds[5].revents&POLLIN){unsigned char packet[4096];ssize_t n=recv(wire,packet,sizeof(packet),0);check(n>=0,"wire read");event("radio-frame",packet,(size_t)n);}
    }close(udp);if(ap){close(dhcp);close(dns);close(http);}close(wire);text("peer-closed","actual sockets closed");
}
static void exchange(const char *iface,const char *peer) {
    struct in_addr address;check(inet_pton(AF_INET,peer,&address)==1,"actual peer address data");uint32_t local=own_ip(iface);check(local!=address.s_addr && (ntohl(address.s_addr)>>24)!=127,"no loopback peer shortcut");
    struct ifaddrs *all;check(getifaddrs(&all)==0,"initial namespace local-address exclusion");
    for(struct ifaddrs *p=all;p;p=p->ifa_next)if(p->ifa_addr && p->ifa_addr->sa_family==AF_INET)check(((struct sockaddr_in*)p->ifa_addr)->sin_addr.s_addr!=address.s_addr,"peer address must not belong to ANY initial-netns interface");freeifaddrs(all);
    int fd=bound_socket(SOCK_DGRAM,0,iface,local);struct timeval timeout={.tv_sec=10};setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));
    struct sockaddr_in to={.sin_family=AF_INET,.sin_port=htons(36979),.sin_addr=address};check(connect(fd,(struct sockaddr*)&to,sizeof(to))==0,"actual wireless peer UDP connect");
    unsigned char challenge[16];int random=open("/dev/urandom",O_RDONLY|O_CLOEXEC);check(random>=0 && read(random,challenge,sizeof(challenge))==(ssize_t)sizeof(challenge),"fresh actual per-exchange random nonce");close(random);char hex[33];for(size_t i=0;i<sizeof(challenge);++i)snprintf(hex+2*i,3,"%02x",challenge[i]);
    char sent[160],expected[176],reply[2048];int n=snprintf(sent,sizeof(sent),"APPS579:%s:initial-to-independent-peer:%s",run,hex);snprintf(expected,sizeof(expected),"%s:reply",sent);
    event("nonce-initial-tx",sent,(size_t)n);check(send(fd,sent,(size_t)n,0)==n,"actual nonce send");ssize_t got=recv(fd,reply,sizeof(reply),0);check(got>=0,"actual nonce receive");event("nonce-initial-rx",reply,(size_t)got);
    check(got==(ssize_t)strlen(expected) && !memcmp(reply,expected,(size_t)got),"independent endpoint nonce differs");close(fd);inspect();
}
int main(int argc,char **argv) {
    check(argc>=3,"finite helper arguments");const char *mode=argv[1];
    check(!strcmp(mode,"hold")||!strcmp(mode,"move")||!strcmp(mode,"return")||!strcmp(mode,"daemon-ap")||!strcmp(mode,"daemon-sta")||!strcmp(mode,"daemon-p2p")||!strcmp(mode,"server-ap")||!strcmp(mode,"server-sta")||!strcmp(mode,"inspect")||!strcmp(mode,"inspect-initial")||!strcmp(mode,"exchange")||!strcmp(mode,"restore")||!strcmp(mode,"config-mount")||!strcmp(mode,"config-unmount"),"source-defined helper mode");
    initialize(argv[2],mode);
    if(!strcmp(mode,"config-mount")){check(argc==3,"config mount arity");char source[256];snprintf(source,sizeof(source),"%s/probe.conf",directory);
        struct stat st;check(lstat(source,&st)==0 && S_ISREG(st.st_mode) && st.st_uid==0,"actual owned probe config");
        check(mount(source,"/system/etc/netdetectionurl.conf",NULL,MS_BIND,NULL)==0,"bind only fixed actual detection config");text("probe-config-mounted",source);
    }else if(!strcmp(mode,"config-unmount")){check(argc==3,"config unmount arity");check(umount2("/system/etc/netdetectionurl.conf",0)==0,"restore original detection config mount");text("probe-config-restored","/system/etc/netdetectionurl.conf");
    }else if(!strcmp(mode,"restore")){check(argc==3,"restore arity");check(if_nametoindex("wlan1")==0 && if_nametoindex(peer_if)>0,"restore only returned spare interface after OS AP removal");
        int fd=interface_socket(peer_if);struct ifreq req={0};strncpy(req.ifr_name,peer_if,IFNAMSIZ-1);check(ioctl(fd,SIOCGIFFLAGS,&req)==0,"restore actual flags");req.ifr_flags&=(short)~IFF_UP;check(ioctl(fd,SIOCSIFFLAGS,&req)==0,"returned peer down");
        strncpy(req.ifr_newname,"wlan1",IFNAMSIZ-1);check(ioctl(fd,SIOCSIFNAME,&req)==0,"restore exact spare interface name");close(fd);text("peer-name-restored","s579peer -> wlan1");
    }else if(!strcmp(mode,"hold")){check(argc==3,"hold arity");unsigned long original=ns_inode();check(unshare(CLONE_NEWNET)==0,"actual private network namespace");check(ns_inode()!=original,"new namespace identity");flags_up("lo");
        char value[128];int n=snprintf(value,sizeof(value),"pid=%d original=%lu peer=%lu",getpid(),original,ns_inode());int out=open_owned("namespace.txt",O_WRONLY|O_CREAT|O_EXCL);check(write(out,value,(size_t)n)==n,"namespace marker");close(out);text("namespace-held",value);
        while(!stopping){struct pollfd fd={.fd=0,.events=POLLIN};int rc=poll(&fd,1,500);if(rc<0&&errno==EINTR)continue;check(rc>=0,"namespace control");if(fd.revents&(POLLIN|POLLHUP))if(control_stop())break;}
    }else if(!strcmp(mode,"move")){check(argc==5,"move arity");
        int marker=open_owned("namespace.txt",O_RDONLY);char held[128]={0},prefix[64];ssize_t n=read(marker,held,sizeof(held)-1);close(marker);snprintf(prefix,sizeof(prefix),"pid=%ld ",number(argv[3],2,4194304));check(n>0 && !strncmp(held,prefix,strlen(prefix)),"move destination must be this nonce's actual held namespace");
        move_out((int)number(argv[4],0,4096),(int)number(argv[3],2,4194304));
    }else if(!strcmp(mode,"inspect-initial")){check(argc==3,"initial inspect arity");inspect();
    }else if(!strcmp(mode,"exchange")){check(argc==5,"exchange arity");exchange(argv[3],argv[4]);
    }else {check(!strcmp(mode,"return")?argc==5:argc==4,"peer mode arity");int pid=(int)number(argv[3],2,4194304);enter_peer(pid);
        if(!strcmp(mode,"return")){clear_peer_ipv4();int fd=interface_socket(peer_if);struct ifreq req={0};strncpy(req.ifr_name,peer_if,IFNAMSIZ-1);
            check(ioctl(fd,SIOCGIFFLAGS,&req)==0,"read peer flags before netns return");req.ifr_flags&=(short)~IFF_UP;
            check(ioctl(fd,SIOCSIFFLAGS,&req)==0,"stop peer interface before netns return");close(fd);
            move_phy((int)number(argv[4],0,4096),1);text("peer-returned","actual wiphy returned to init namespace");}
        else if(!strcmp(mode,"inspect"))inspect();
        else if(!strcmp(mode,"server-ap")||!strcmp(mode,"server-sta"))server(!strcmp(mode,"server-ap"));
        else {char config[256];snprintf(config,sizeof(config),"%s/%s.conf",directory,!strcmp(mode,"daemon-ap")?"ap":!strcmp(mode,"daemon-p2p")?"p2p":"sta");text("stock-daemon",config);
            if(!strcmp(mode,"daemon-ap"))execl("/vendor/bin/hostapd","hostapd","-d",config,(char*)NULL);
            else execl("/vendor/bin/wpa_supplicant","wpa_supplicant","-Dnl80211","-i","s579peer","-c",config,"-d",(char*)NULL);
            check(0,"exec actual fixed stock radio daemon");
        }
    }text("completed",mode);fclose(journal);return 0;
}
