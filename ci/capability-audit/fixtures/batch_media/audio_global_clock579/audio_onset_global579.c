/* SPDX-License-Identifier: Apache-2.0
 * Root-held fixed journal client; never opens/configures a PCM device.
 * All process/resource ownership remains with the original native actor broker.
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <poll.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unistd.h>
#include <time.h>
#include "onset579_clock_domain.h"
#include "audio_onset580_wire.h"
#define O579_MAGIC O580_MAGIC
#define O579_VERSION O580_VERSION
struct request579 {uint32_t magic,version,op,pid;uint64_t birth;char run[32];};
struct ack579 {uint32_t magic,version,error,state,pid,reserved;uint64_t birth,produced,drained,lost;};
_Static_assert(sizeof(struct request579)==56 && sizeof(struct ack579)==56,"fixed580 native32/64 wire ABI");
static uint64_t birth(pid_t pid)
{
    char path[64],raw[4096];snprintf(path,sizeof(path),"/proc/%ld/stat",(long)pid);
    FILE *f=fopen(path,"r");if(!f)return 0;int ok=fgets(raw,sizeof(raw),f)!=NULL;int ended=fclose(f);
    if(!ok||ended)return 0;char *p=strrchr(raw,')');if(!p||p[1]!=' ')return 0;p+=2;
    for(int k=3;k<22;++k){p=strchr(p,' ');if(!p)return 0;++p;}
    char *end=NULL;errno=0;uint64_t value=strtoull(p,&end,10);return errno||!end||*end!=' '?0:value;
}
static int boot(char raw[40])
{
    FILE *f=fopen("/proc/sys/kernel/random/boot_id","r");if(!f)return errno;
    int ok=fgets(raw,40,f)!=NULL;int closed=fclose(f);raw[strcspn(raw,"\n")]=0;
    if(!ok||closed||strlen(raw)!=36)return EIO;
    for(int k=0;k<36;++k)if((k==8||k==13||k==18||k==23)?raw[k]!='-':!strchr("0123456789abcdef",raw[k]))return EINVAL;
    return 0;
}
static int uids(pid_t pid,unsigned *uid,unsigned *gid)
{
    char path[64],line[1024];snprintf(path,sizeof(path),"/proc/%ld/status",(long)pid);
    FILE *f=fopen(path,"r");if(!f)return errno;unsigned a,b,c,d;int have_u=0,have_g=0;
    while(fgets(line,sizeof(line),f)){
        if(!strncmp(line,"Uid:",4)&&sscanf(line,"Uid: %u %u %u %u",&a,&b,&c,&d)==4&&a==b&&a==c&&a==d){*uid=a;have_u=1;}
        if(!strncmp(line,"Gid:",4)&&sscanf(line,"Gid: %u %u %u %u",&a,&b,&c,&d)==4&&a==b&&a==c&&a==d){*gid=a;have_g=1;}
    }
    int closed=fclose(f);return closed||!have_u||!have_g?EACCES:0;
}
static int pidfd_open579(pid_t pid)
{
#ifdef SYS_pidfd_open
    return (int)syscall(SYS_pidfd_open,pid,0);
#else
    errno=ENOSYS;return -1;
#endif
}
static int live(int fd,pid_t pid,uint64_t ticks)
{struct pollfd p={fd,POLLIN,0};return fd>=0&&poll(&p,1,0)==0&&birth(pid)==ticks;}
static int inventory(const char *expected,const char *run)
{
    if(m579_global_clock_review_gate())return ENOTSUP;
    char id[40];int error=boot(id);if(error||strcmp(id,expected))return error?error:ESTALE;
    FILE *f=fopen("/proc/net/unix","r");if(!f)return errno;
    char line[2048];unsigned count=0;
    uint64_t observer_birth=birth(getpid());if(!observer_birth){fclose(f);return ESTALE;}
    printf("{\"kind\":\"inventory_begin580\",\"boot\":\"%s\",\"observer_pid\":%ld,\"observer_birth\":%"PRIu64"}\n",id,(long)getpid(),observer_birth);
    while(fgets(line,sizeof(line),f)){
        char *at=strstr(line,"@ohos-audio580/");if(!at)continue;
        long pid;uint64_t ticks;int n=0;
        if(sscanf(at,"@ohos-audio580/%ld/%"SCNu64"%n",&pid,&ticks,&n)!=2||pid<=0||pid>INT_MAX||
            (at[n]!='\n'&&at[n]!=0)||birth((pid_t)pid)!=ticks){error=ESTALE;break;}
        unsigned uid=0,gid=0;struct m579_clock_observation clock;char clock_json[4096];
        error=uids((pid_t)pid,&uid,&gid);if(error)break;
        int held=pidfd_open579((pid_t)pid);if(held<0){error=errno;break;}
        error=m579_global_clock_observe((pid_t)pid,ticks,held,&clock);
        if(!error)error=m579_clock_buffer(clock_json,sizeof(clock_json),run,"af_producer",&clock);
        int closed=close(held);if(!error && closed)error=errno?errno:EIO;
        if(error)break;
        if(++count>8){error=EOVERFLOW;break;}
        printf("{\"kind\":\"producer580\",\"pid\":%ld,\"birth\":%"PRIu64",\"uid\":%u,\"gid\":%u,\"clock_domain\":%s,\"pidfd_close_rc\":%d}\n",
            pid,ticks,uid,gid,clock_json,closed);
    }
    if(fclose(f)&&!error)error=EIO;
    printf("{\"kind\":\"inventory_end580\",\"count\":%u,\"error\":%d}\n",count,error);
    return error?error:count==1?0:EBUSY;
}
static uint64_t monotonic579(int *error)
{
    struct timespec t;errno=0;int rc=clock_gettime(CLOCK_MONOTONIC,&t);int saved=errno;
    if(rc||t.tv_sec<0||t.tv_nsec<0||t.tv_nsec>=1000000000L){*error=rc?(saved?saved:EIO):ERANGE;return 0;}
    return (uint64_t)t.tv_sec*UINT64_C(1000000000)+(uint64_t)t.tv_nsec;
}
static int receive_ack(int socket,unsigned state,pid_t pid,uint64_t ticks,const char *phase)
{
    struct pollfd p={socket,POLLIN,0};int rc,clock_error=0;
    uint64_t poll_before=monotonic579(&clock_error);if(clock_error){printf("{\"kind\":\"ack_clock_error580\",\"phase\":\"%s\",\"at\":\"before_poll\",\"clock_error\":%d}\n",phase,clock_error);return clock_error;}
    do{errno=0;rc=poll(&p,1,15000);}while(rc<0&&errno==EINTR);
    int poll_errno=errno;uint64_t poll_after=monotonic579(&clock_error);
    if(rc!=1||!(p.revents&POLLIN)||clock_error){
        printf("{\"kind\":\"ack_poll_error580\",\"phase\":\"%s\",\"before_ns\":%"PRIu64",\"after_ns\":%"PRIu64",\"rc\":%d,\"errno\":%d,\"revents\":%d,\"clock_error\":%d}\n",phase,poll_before,poll_after,rc,poll_errno,p.revents,clock_error);
        return clock_error?clock_error:rc<0?(poll_errno?poll_errno:EIO):ETIMEDOUT;
    }
    struct ack579 a;unsigned char control[64];struct iovec iov={&a,sizeof(a)};struct msghdr m={0};
    m.msg_iov=&iov;m.msg_iovlen=1;m.msg_control=control;m.msg_controllen=sizeof(control);
    uint64_t before=monotonic579(&clock_error);if(clock_error){printf("{\"kind\":\"ack_clock_error580\",\"phase\":\"%s\",\"at\":\"before_recvmsg\",\"clock_error\":%d}\n",phase,clock_error);return clock_error;}
    errno=0;ssize_t n=recvmsg(socket,&m,MSG_CMSG_CLOEXEC);int saved=errno;
    uint64_t after=monotonic579(&clock_error);
    int malformed=clock_error||!before||after<before||n!=(ssize_t)sizeof(a)||(m.msg_flags&(MSG_TRUNC|MSG_CTRUNC))||CMSG_FIRSTHDR(&m)!=NULL;
    if(malformed){printf("{\"kind\":\"ack_error579\",\"phase\":\"%s\",\"bytes\":%ld,\"errno\":%d,\"before_ns\":%"PRIu64",\"after_ns\":%"PRIu64",\"clock_error\":%d}\n",phase,(long)n,saved,before,after,clock_error);return clock_error?clock_error:EPROTO;}
    printf("{\"kind\":\"ack580\",\"phase\":\"%s\",\"magic\":%u,\"version\":%u,\"error\":%u,\"state\":%u,\"pid\":%u,\"birth\":%"PRIu64",\"reserved\":%u,\"produced\":%"PRIu64",\"drained\":%"PRIu64",\"lost\":%"PRIu64",\"before_ns\":%"PRIu64",\"after_ns\":%"PRIu64",\"errno\":%d,\"clock_error\":%d,\"wire_hex\":\"",
        phase,a.magic,a.version,a.error,a.state,a.pid,a.birth,a.reserved,a.produced,a.drained,a.lost,before,after,saved,clock_error);
    for(size_t k=0;k<sizeof(a);++k)printf("%02x",((unsigned char*)&a)[k]);puts("\"}");
    if(a.magic!=O579_MAGIC||a.version!=O579_VERSION||a.error||a.state!=state||a.pid!=(unsigned)pid||a.birth!=ticks||a.reserved||a.lost||(!state&&a.produced!=a.drained))return EPROTO;
    return 0;
}
static int send_request(int socket,struct request579 *r,int fd)
{
    struct iovec iov={r,sizeof(*r)};struct msghdr m={0};unsigned char control[CMSG_SPACE(sizeof(int))];
    m.msg_iov=&iov;m.msg_iovlen=1;
    if(fd>=0){memset(control,0,sizeof(control));m.msg_control=control;m.msg_controllen=sizeof(control);
        struct cmsghdr *c=CMSG_FIRSTHDR(&m);c->cmsg_level=SOL_SOCKET;c->cmsg_type=SCM_RIGHTS;c->cmsg_len=CMSG_LEN(sizeof(int));memcpy(CMSG_DATA(c),&fd,sizeof(fd));}
    int clock_error=0;uint64_t before=monotonic579(&clock_error);
    if(clock_error){printf("{\"kind\":\"request_clock_error579\",\"op\":%u,\"before_ns\":%"PRIu64",\"clock_error\":%d}\n",r->op,before,clock_error);return clock_error;}
    errno=0;ssize_t sent=sendmsg(socket,&m,MSG_NOSIGNAL);int saved=errno;
    uint64_t after=monotonic579(&clock_error);
    printf("{\"kind\":\"request580\",\"op\":%u,\"bytes\":%ld,\"errno\":%d,\"passed_fd\":%d,\"before_ns\":%"PRIu64",\"after_ns\":%"PRIu64",\"clock_error\":%d}\n",r->op,(long)sent,saved,fd,before,after,clock_error);
    if(clock_error||!before||after<before)return clock_error?clock_error:ERANGE;
    return sent==(ssize_t)sizeof(*r)?0:saved?saved:EIO;
}
static int run(pid_t pid,uint64_t ticks,unsigned expected_uid,const char *expected_boot,const char *nonce,const char *path)
{
    int socket_fd=-1,held=-1,file=-1,error=0;unsigned uid=0,gid=0,self_uid=0,self_gid=0;struct stat st;
    struct m579_clock_observation producer_clock,client_clock;char producer_json[4096],client_json[4096];
    char id[40];uint64_t self_ticks=birth(getpid());
    if(m579_global_clock_review_gate())return ENOTSUP;
    if(boot(id)||strcmp(id,expected_boot)||!self_ticks||uids(getpid(),&self_uid,&self_gid)||self_uid||self_gid)return EACCES;
    if(!ticks||birth(pid)!=ticks||uids(pid,&uid,&gid)||uid!=expected_uid)return ESTALE;
    held=pidfd_open579(pid);if(!live(held,pid,ticks)){error=ESTALE;goto done;}
    if(m579_global_clock_observe(pid,ticks,held,&producer_clock) ||
       m579_global_clock_observe(getpid(),self_ticks,-1,&client_clock) ||
       m579_global_clock_pair(&producer_clock,&client_clock) ||
       m579_clock_buffer(producer_json,sizeof(producer_json),nonce,"af_producer",&producer_clock) ||
       m579_clock_buffer(client_json,sizeof(client_json),nonce,"af_client",&client_clock)){error=ESTALE;goto done;}
    socket_fd=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0);if(socket_fd<0){error=errno;goto done;}
    struct sockaddr_un address={0};address.sun_family=AF_UNIX;
    int size=snprintf(address.sun_path+1,sizeof(address.sun_path)-1,"ohos-audio580/%ld/%"PRIu64,(long)pid,ticks);
    if(size<=0||size>=(int)sizeof(address.sun_path)-1){error=EOVERFLOW;goto done;}
    if(connect(socket_fd,(struct sockaddr*)&address,(socklen_t)(offsetof(struct sockaddr_un,sun_path)+1+size))){error=errno;goto done;}
    struct ucred peer;socklen_t plen=sizeof(peer);
    if(getsockopt(socket_fd,SOL_SOCKET,SO_PEERCRED,&peer,&plen)||plen!=sizeof(peer)||peer.pid!=pid||peer.uid!=uid||peer.gid!=gid||!live(held,pid,ticks)){error=ESTALE;goto done;}
    // The original collector creates/checks the private parent directory. No
    // executable/path is chosen by protocol data, and no existing file is opened.
    file=open(path,O_CREAT|O_EXCL|O_RDWR|O_CLOEXEC|O_NOFOLLOW,0600);if(file<0){error=errno;goto done;}
    if(fstat(file,&st)||!S_ISREG(st.st_mode)||st.st_uid||st.st_nlink!=1||st.st_size||(st.st_mode&0777)!=0600){error=EACCES;goto done;}
    printf("{\"kind\":\"hello580\",\"boot\":\"%s\",\"run\":\"%s\",\"client_pid\":%ld,\"client_birth\":%"PRIu64",\"client_uid\":%u,\"client_gid\":%u,\"client_clock\":%s,\"producer_pid\":%ld,\"producer_birth\":%"PRIu64",\"producer_uid\":%u,\"producer_gid\":%u,\"producer_clock\":%s,\"pidfd\":%d,\"journal_fd\":%d,\"journal_dev\":%"PRIu64",\"journal_ino\":%"PRIu64"}\n",
        id,nonce,(long)getpid(),self_ticks,self_uid,self_gid,client_json,(long)pid,ticks,uid,gid,producer_json,held,file,(uint64_t)st.st_dev,(uint64_t)st.st_ino);
    struct request579 r={O579_MAGIC,O579_VERSION,1,(uint32_t)pid,ticks,{0}};memcpy(r.run,nonce,32);
    error=send_request(socket_fd,&r,file);if(error)goto done;
    error=receive_ack(socket_fd,1,pid,ticks,"arm");if(error)goto done;
    char command[160],tail;long receiver;uint64_t receiver_birth;
    if(!fgets(command,sizeof(command),stdin) ||
       sscanf(command,"CLOCK %ld %"SCNu64" %c",&receiver,&receiver_birth,&tail)!=2 ||
       receiver<=1 || receiver>INT_MAX || !receiver_birth){error=ECANCELED;goto done;}
    int receiver_fd=pidfd_open579((pid_t)receiver);if(receiver_fd<0){error=errno;goto done;}
    struct m579_clock_observation receiver_clock;char receiver_json[4096];
    int receiver_error=m579_global_clock_observe((pid_t)receiver,receiver_birth,receiver_fd,&receiver_clock);
    if(!receiver_error)receiver_error=m579_global_clock_pair(&client_clock,&receiver_clock);
    if(!receiver_error)receiver_error=m579_clock_buffer(receiver_json,sizeof(receiver_json),nonce,"renderer_receiver",&receiver_clock);
    int receiver_closed=close(receiver_fd);if(!receiver_error && receiver_closed)receiver_error=errno?errno:EIO;
    if(receiver_error){error=receiver_error;goto done;}
    printf("{\"kind\":\"receiver_clock580\",\"clock_domain\":%s,\"pidfd_close_rc\":%d}\n",receiver_json,receiver_closed);
    if(!fgets(command,sizeof(command),stdin)||strcmp(command,"DISARM\n")){error=ECANCELED;goto done;}
    if(!live(held,pid,ticks)){error=ESTALE;goto done;}
    r.op=2;error=send_request(socket_fd,&r,-1);if(error)goto done;
    error=receive_ack(socket_fd,0,pid,ticks,"disarm");if(error)goto done;
    if(!live(held,pid,ticks)||fstat(file,&st)){error=ESTALE;goto done;}
    printf("{\"kind\":\"sealed_file580\",\"dev\":%"PRIu64",\"ino\":%"PRIu64",\"bytes\":%"PRIu64",\"mode\":%u,\"uid\":%u,\"nlink\":%u}\n",
        (uint64_t)st.st_dev,(uint64_t)st.st_ino,(uint64_t)st.st_size,(unsigned)(st.st_mode&0777),(unsigned)st.st_uid,(unsigned)st.st_nlink);
done:
    {
        int fds[3]={file,socket_fd,held};const char *names[3]={"journal","socket","pidfd"};int close_error=0;
        for(int i=0;i<3;++i)if(fds[i]>=0){errno=0;int rc=close(fds[i]);int saved=errno;
            printf("{\"kind\":\"close_fd580\",\"role\":\"%s\",\"fd\":%d,\"rc\":%d,\"errno\":%d}\n",names[i],fds[i],rc,saved);
            if(rc&&!close_error)close_error=saved?saved:EIO;}
        if(!error)error=close_error;
        printf("{\"kind\":\"end_control580\",\"error\":%d,\"close_errno\":%d}\n",error,close_error);
    }
    return error;
}
static int number(const char *raw,uint64_t *out)
{char *end;errno=0;if(!raw||!*raw||*raw=='-'||*raw=='+')return EINVAL;*out=strtoull(raw,&end,10);return errno||*end?EINVAL:0;}
int main(int argc,char **argv)
{
    setvbuf(stdout,NULL,_IONBF,0);umask(077);
    if(argc==4&&!strcmp(argv[1],"--inventory") && strlen(argv[3])==32 && strspn(argv[3],"0123456789abcdef")==32)return inventory(argv[2],argv[3])?1:0;
    // Positional argv is fixed by the source-owned collector, never JSON code selection.
    if(argc!=7)return 2;
    uint64_t pid,ticks,uid;if(number(argv[1],&pid)||!pid||pid>INT_MAX||number(argv[2],&ticks)||!ticks||number(argv[3],&uid)||uid>UINT_MAX||strlen(argv[5])!=32||argv[6][0]!='/')return 2;
    for(int k=0;k<32;++k)if(!strchr("0123456789abcdef",argv[5][k]))return 2;
    return run((pid_t)pid,ticks,(unsigned)uid,argv[4],argv[5],argv[6])?1:0;
}
