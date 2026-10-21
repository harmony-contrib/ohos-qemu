/* SPDX-License-Identifier: Apache-2.0
 * Source-only Linux root native client for the EXACT398 server wire.
 * Never opens a PCM path, issues PCM ioctls, forks or changes product behavior.
 * Root must verify/build this on actual target libc/kernel. Native host models
 * compile control404_core.h only; they are NOT target-ABI/kernel/audio success. */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "control_global579_core.h"
#include "onset579_clock_domain.h"
#ifndef __linux__
#error CONTROL404 requires actual Linux headers; no host ABI substitute
#endif
#include <fcntl.h>
#include <inttypes.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
#if !defined(SYS_pidfd_open) || !defined(SYS_pidfd_getfd) || !defined(SYS_kcmp) || !defined(MSG_CMSG_CLOEXEC)
#error Actual target syscall/SCM declarations required, no guessed syscall numbers
#endif
struct client {
    struct c404_state state;
    pid_t self, sampler; uint64_t self_ticks, sampler_ticks;
    uid_t holder_uid; gid_t holder_gid,self_gid; unsigned holder_uids[4],holder_gids[4];
    int socket, holder_pfd, sampler_pfd, directory, journal, tap, ledger;
    uint64_t dev,ino,rdev, seq, ledger_bytes;
    struct stat journal_stat, tap_stat;
    struct m579_clock_observation self_clock,holder_clock;
    char boot[40], run[33];
};
static struct client c;
static uint64_t number(const char *s, uint64_t max)
{
    if(!s || !*s || strspn(s,"0123456789")!=strlen(s)){errno=EINVAL;return UINT64_MAX;}
    char *end=NULL;errno=0;uint64_t n=strtoull(s,&end,10);
    if(errno || !end || *end || n>max){errno=ERANGE;return UINT64_MAX;}return n;
}
static uint64_t clock_ns(clockid_t id)
{
    struct timespec t;if(clock_gettime(id,&t) || t.tv_sec<0 || t.tv_nsec<0 || t.tv_nsec>=1000000000L)return 0;
    if((uint64_t)t.tv_sec>(UINT64_MAX-(uint64_t)t.tv_nsec)/UINT64_C(1000000000))return 0;
    return (uint64_t)t.tv_sec*UINT64_C(1000000000)+(uint64_t)t.tv_nsec;
}
static uint64_t birth(pid_t pid)
{
    char path[80],raw[4096];snprintf(path,sizeof(path),"/proc/%ld/stat",(long)pid);
    FILE *f=fopen(path,"r");if(!f)return 0;
    int ok=fgets(raw,sizeof(raw),f)!=NULL;if(fclose(f) || !ok)return 0;
    char *p=strrchr(raw,')');if(!p || p[1]!=' ')return 0;p+=2;
    for(int i=3;i<22;++i){p=strchr(p,' ');if(!p)return 0;++p;}
    char *end=strchr(p,' ');if(!end)return 0;*end=0;return number(p,UINT64_MAX-1);
}
static int ids(pid_t pid, unsigned uid[4],unsigned gid[4])
{
    char p[80],line[1024];int got=0;snprintf(p,sizeof(p),"/proc/%ld/status",(long)pid);
    FILE *f=fopen(p,"r");if(!f)return errno;
    while(fgets(line,sizeof(line),f)) {
        if(!strncmp(line,"Uid:",4) && sscanf(line,"Uid: %u %u %u %u",uid,uid+1,uid+2,uid+3)==4)got|=1;
        if(!strncmp(line,"Gid:",4) && sscanf(line,"Gid: %u %u %u %u",gid,gid+1,gid+2,gid+3)==4)got|=2;
    }
    int rc=fclose(f);return rc?EIO:got==3?0:EPROTO;
}
static int close_one(int *fd){int n=*fd;*fd=-1;return n>=0 && close(n)?errno:0;}
static int same(const struct stat *a,const struct stat *b)
{
    return a->st_dev==b->st_dev && a->st_ino==b->st_ino && a->st_rdev==b->st_rdev &&
      a->st_mode==b->st_mode && a->st_uid==b->st_uid && a->st_gid==b->st_gid && a->st_nlink==b->st_nlink;
}
static int live(void)
{
    struct pollfd p={c.holder_pfd,POLLIN,0};unsigned u[4],g[4],su[4],sg[4];
    if(poll(&p,1,0)<0 || p.revents || birth(c.state.pid)!=c.state.ticks || birth(c.self)!=c.self_ticks ||
        m579_global_clock_observe(c.self,c.self_ticks,-1,&c.self_clock) ||
        m579_global_clock_observe(c.state.pid,c.state.ticks,c.holder_pfd,&c.holder_clock) ||
        m579_global_clock_pair(&c.self_clock,&c.holder_clock) || ids(c.state.pid,u,g) || ids(c.self,su,sg) ||
        memcmp(u,c.holder_uids,sizeof(u)) || memcmp(g,c.holder_gids,sizeof(g)) ||
        u[1]!=c.holder_uid || g[1]!=c.holder_gid || su[0] || su[1] || su[2] || su[3] ||
        sg[0]!=c.self_gid || sg[1]!=c.self_gid || sg[2]!=c.self_gid || sg[3]!=c.self_gid)return ESTALE;
    return 0;
}
static int row(const char *kind,const char *fields)
{
    char out[12288],self_json[4096],holder_json[4096];
    if(m579_clock_buffer(self_json,sizeof(self_json),c.run,"control_client",&c.self_clock) ||
       m579_clock_buffer(holder_json,sizeof(holder_json),c.run,"alsa_holder",&c.holder_clock))return ESTALE;
    uint64_t m=clock_ns(CLOCK_MONOTONIC),r=clock_ns(CLOCK_REALTIME);
    int n=snprintf(out,sizeof(out),"{\"kind\":\"%s\",\"protocol\":604,\"seq\":%"PRIu64",\"run\":\"%s\",\"boot\":\"%s\","
      "\"monotonic_ns\":%"PRIu64",\"realtime_ns\":%"PRIu64",\"client_pid\":%ld,\"client_ticks\":%"PRIu64","
      "\"holder_pid\":%d,\"holder_ticks\":%"PRIu64",\"holder_uid\":%u,\"holder_gid\":%u,\"fd\":%d,"
      "\"clock_variant\":\"kernel_global_monotonic\",\"client_clock\":%s,\"holder_clock\":%s,%s,\"onset_proven\":false}\n",
      kind,c.seq++,c.run,c.boot,m,r,(long)c.self,c.self_ticks,c.state.pid,c.state.ticks,(unsigned)c.holder_uid,
      (unsigned)c.holder_gid,c.state.fd,self_json,holder_json,fields);
    if(!m || !r || n<=0 || n>=(int)sizeof(out) || c.ledger_bytes>UINT64_C(131072) ||
      pwrite(c.ledger,out,(size_t)n,(off_t)c.ledger_bytes)!=n || write(STDOUT_FILENO,out,(size_t)n)!=n)return EIO;
    c.ledger_bytes+=(uint64_t)n;return 0;
}
static void hex(const void *bytes,size_t n,char *out)
{
    static const char alphabet[]="0123456789abcdef";const unsigned char *b=bytes;
    for(size_t i=0;i<n;++i){out[2*i]=alphabet[b[i]>>4];out[2*i+1]=alphabet[b[i]&15];}out[2*n]=0;
}
static int wait_socket(short events)
{
    uint64_t until=clock_ns(CLOCK_MONOTONIC)+UINT64_C(5000000000);
    while(clock_ns(CLOCK_MONOTONIC)<until) {
        if(live())return ESTALE;
        struct pollfd p={c.socket,events,0};int r=poll(&p,1,10);
        if(r<0){if(errno==EINTR)continue;return errno;}
        if(p.revents&(POLLERR|POLLHUP|POLLNVAL))return EPIPE;
        if(p.revents&events)return 0;
    }return ETIMEDOUT;
}
static int send_request(unsigned op,const int *fds,unsigned n)
{
    struct m398_request q={0};q.epoch=op==M398_HELLO?0:c.state.epoch;q.instance=op==M398_HELLO?0:c.state.instance;
    q.holder_ticks=c.state.ticks;q.magic=M398_MAGIC;q.op=op;q.holder_pid=(uint32_t)c.state.pid;
    memcpy(q.boot,c.boot,40);memcpy(q.run,c.run,32);
    union {struct cmsghdr align;char data[CMSG_SPACE(sizeof(struct ucred))+CMSG_SPACE(3*sizeof(int))];} control={0};
    struct iovec io={&q,sizeof(q)};struct msghdr m={0};m.msg_iov=&io;m.msg_iovlen=1;m.msg_control=control.data;
    m.msg_controllen=CMSG_SPACE(sizeof(struct ucred))+(n?CMSG_SPACE(n*sizeof(int)):0);
    struct cmsghdr *a=CMSG_FIRSTHDR(&m);a->cmsg_level=SOL_SOCKET;a->cmsg_type=SCM_CREDENTIALS;a->cmsg_len=CMSG_LEN(sizeof(struct ucred));
    struct ucred credentials={getpid(),getuid(),getgid()};memcpy(CMSG_DATA(a),&credentials,sizeof(credentials));
    if(n){a=CMSG_NXTHDR(&m,a);if(!a || n!=3)return EINVAL;a->cmsg_level=SOL_SOCKET;a->cmsg_type=SCM_RIGHTS;a->cmsg_len=CMSG_LEN(n*sizeof(int));memcpy(CMSG_DATA(a),fds,n*sizeof(int));}
    int error=wait_socket(POLLOUT);if(error)return error;
    if(sendmsg(c.socket,&m,MSG_DONTWAIT|MSG_NOSIGNAL)!=(ssize_t)sizeof(q))return errno?errno:EIO;
    char raw[sizeof(q)*2+1],fields[640];hex(&q,sizeof(q),raw);
    snprintf(fields,sizeof(fields),"\"op\":%u,\"wire_hex\":\"%s\",\"sent_fd_count\":%u,\"scm_pid\":%ld,\"scm_uid\":%u,\"scm_gid\":%u",op,raw,n,(long)credentials.pid,(unsigned)credentials.uid,(unsigned)credentials.gid);
    return row("request404",fields);
}
static int receive_ack(unsigned op,struct m398_ack *ack)
{
    union {struct cmsghdr align;char data[CMSG_SPACE(sizeof(struct ucred))+CMSG_SPACE(253*sizeof(int))];} control={0};
    unsigned char bytes[sizeof(*ack)+1];struct iovec io={bytes,sizeof(bytes)};struct msghdr m={0};
    m.msg_iov=&io;m.msg_iovlen=1;m.msg_control=control.data;m.msg_controllen=sizeof(control.data);
    int error=wait_socket(POLLIN);if(error)return error;
    ssize_t size=recvmsg(c.socket,&m,MSG_DONTWAIT|MSG_CMSG_CLOEXEC);unsigned credentials=0;struct ucred peer={0};int bad=0;
    if(size!=(ssize_t)sizeof(*ack) || m.msg_flags&(MSG_TRUNC|MSG_CTRUNC) || m.msg_controllen>sizeof(control.data))bad=1;
    if(m.msg_controllen>sizeof(control.data))m.msg_controllen=sizeof(control.data);
    for(struct cmsghdr *a=CMSG_FIRSTHDR(&m);a;a=CMSG_NXTHDR(&m,a)) {
        if(a->cmsg_len<CMSG_LEN(0) || a->cmsg_len>m.msg_controllen || (char *)a+(size_t)a->cmsg_len>control.data+m.msg_controllen){bad=1;break;}
        if(a->cmsg_level==SOL_SOCKET && a->cmsg_type==SCM_CREDENTIALS && a->cmsg_len==CMSG_LEN(sizeof(peer))) {memcpy(&peer,CMSG_DATA(a),sizeof(peer));++credentials;}
        else if(a->cmsg_level==SOL_SOCKET && a->cmsg_type==SCM_RIGHTS) {
            if((a->cmsg_len-CMSG_LEN(0))%sizeof(int))bad=1;
            size_t count=(a->cmsg_len-CMSG_LEN(0))/sizeof(int);int *f=(int *)CMSG_DATA(a);for(size_t i=0;i<count;++i)if(close(f[i]))bad=1;bad=1;
        }else bad=1;
    }
    if(bad || credentials!=1 || peer.pid!=c.state.pid || peer.uid!=c.holder_uid || peer.gid!=c.holder_gid || live())return EPROTO;
    memcpy(ack,bytes,sizeof(*ack));error=c404_ack(&c.state,ack,op);
    char raw[sizeof(*ack)*2+1],fields[640];hex(ack,sizeof(*ack),raw);
    snprintf(fields,sizeof(fields),"\"op\":%u,\"wire_hex\":\"%s\",\"credential_count\":%u,\"scm_pid\":%ld,\"scm_uid\":%u,\"scm_gid\":%u,\"validation_errno\":%d",op,raw,credentials,(long)peer.pid,(unsigned)peer.uid,(unsigned)peer.gid,error);
    int logged=row("ack404",fields);return error?error:logged;
}
static int borrowed(pid_t pid,int pfd,int fd,int *result)
{
    int n=(int)syscall(SYS_pidfd_getfd,pfd,fd,0);if(n<0)return errno;
    struct stat st;int flags=fcntl(n,F_GETFD);int error=fstat(n,&st)?errno:0;
    if(!error && (flags<0 || !(flags&FD_CLOEXEC) || !S_ISCHR(st.st_mode) || (uint64_t)st.st_dev!=c.dev || (uint64_t)st.st_ino!=c.ino || (uint64_t)st.st_rdev!=c.rdev))error=ESTALE;
    if(!error){long rc=syscall(SYS_kcmp,pid,getpid(),0,(unsigned long)fd,(unsigned long)n);if(rc)error=rc<0?errno:ESTALE;}
    if(error){if(close(n))return EIO;return error;}*result=n;return 0;
}
static int command(char line[160])
{
    size_t used=0;uint64_t until=clock_ns(CLOCK_MONOTONIC)+UINT64_C(65000000000);
    while(used<159 && clock_ns(CLOCK_MONOTONIC)<until) {
        if(live())return ESTALE;struct pollfd p={STDIN_FILENO,POLLIN,0};int rc=poll(&p,1,10);
        if(rc<0){if(errno==EINTR)continue;return errno;}
        if(p.revents&(POLLERR|POLLNVAL))return EPIPE;
        if(p.revents&POLLIN){ssize_t n=read(STDIN_FILENO,line+used,1);if(n!=1)return EPIPE;if(line[used++]=='\n'){line[used]=0;return 0;}}
        else if(p.revents&POLLHUP)return EPIPE;
    }return ETIMEDOUT;
}
static int private_directory(const char *path)
{
    if(!path || path[0]!='/' || strlen(path)>=PATH_MAX || strstr(path,"//")){errno=EINVAL;return -1;}
    char copy[PATH_MAX];memcpy(copy,path,strlen(path)+1);
    int directory=open("/",O_RDONLY|O_DIRECTORY|O_CLOEXEC);if(directory<0)return -1;
    char *save=NULL,*part=strtok_r(copy+1,"/",&save);
    if(!part){close(directory);errno=EINVAL;return -1;}
    while(part) {
        if(!strcmp(part,".") || !strcmp(part,"..")){close(directory);errno=EINVAL;return -1;}
        int next=openat(directory,part,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
        int error=errno;if(close(directory) || next<0){if(next>=0)close(next);errno=error;return -1;}
        directory=next;part=strtok_r(NULL,"/",&save);
    }return directory;
}
static int run_client(const char *directory)
{
    if(m579_global_clock_review_gate())return ENOTSUP;
    c.directory=private_directory(directory);struct stat st;
    if(c.directory<0 || fstat(c.directory,&st) || !S_ISDIR(st.st_mode) || st.st_uid || (st.st_mode&0777)!=0700)return EACCES;
    int *out[3]={&c.ledger,&c.journal,&c.tap};const char *names[3]={"control.jsonl","journal.jsonl","tap.pcm"};
    for(unsigned i=0;i<3;++i){*out[i]=openat(c.directory,names[i],O_RDWR|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);if(*out[i]<0)return errno;}
    if(fstat(c.journal,&c.journal_stat) || fstat(c.tap,&c.tap_stat))return errno;
    for(unsigned i=0;i<3;++i) {
        if(fstat(*out[i],&st) || !S_ISREG(st.st_mode) || st.st_uid || st.st_nlink!=1 ||
            (st.st_mode&0777)!=0600 || st.st_size || lseek(*out[i],0,SEEK_CUR)!=0)return EACCES;
    }
    if(c.journal_stat.st_dev==c.tap_stat.st_dev && c.journal_stat.st_ino==c.tap_stat.st_ino)return ESTALE;
    c.self=getpid();c.self_ticks=birth(c.self);
    unsigned u[4],g[4];if(c.self<=1 || !c.self_ticks || ids(c.state.pid,c.holder_uids,c.holder_gids) ||
      c.holder_uids[1]!=c.holder_uid || c.holder_gids[1]!=c.holder_gid || ids(c.self,u,g) || u[0] || u[1] || u[2] || u[3] ||
      g[0]!=g[1] || g[1]!=g[2] || g[2]!=g[3])return EACCES;
    c.self_gid=(gid_t)g[0];
    char boot[40]={0};FILE *bf=fopen("/proc/sys/kernel/random/boot_id","r");if(!bf)return errno;
    int got=fgets(boot,sizeof(boot),bf)!=NULL;if(fclose(bf) || !got)return EIO;boot[strcspn(boot,"\n")]=0;if(strcmp(boot,c.boot))return ESTALE;
    c.holder_pfd=(int)syscall(SYS_pidfd_open,c.state.pid,0);if(c.holder_pfd<0)return errno;
    int holder_flags=fcntl(c.holder_pfd,F_GETFD);if(holder_flags<0 || !(holder_flags&FD_CLOEXEC) || live())return ESTALE;
    c.socket=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC|SOCK_NONBLOCK,0);if(c.socket<0)return errno;
    int pass=1;if(setsockopt(c.socket,SOL_SOCKET,SO_PASSCRED,&pass,sizeof(pass)))return errno;
    struct sockaddr_un address={0};address.sun_family=AF_UNIX;
    int n=snprintf(address.sun_path+1,sizeof(address.sun_path)-1,"ohos-audio598/%d/%"PRIu64,c.state.pid,c.state.ticks);
    if(n<=0 || n>=(int)sizeof(address.sun_path)-1)return EOVERFLOW;
    if(connect(c.socket,(struct sockaddr *)&address,(socklen_t)(offsetof(struct sockaddr_un,sun_path)+1+n))) {
        if(errno!=EINPROGRESS)return errno;
        int error=wait_socket(POLLOUT),pending=0;socklen_t pending_size=sizeof(pending);
        if(error)return error;
        if(getsockopt(c.socket,SOL_SOCKET,SO_ERROR,&pending,&pending_size) || pending_size!=sizeof(pending) || pending)return pending?pending:EIO;
    }
    struct ucred peer;socklen_t size=sizeof(peer);
    if(getsockopt(c.socket,SOL_SOCKET,SO_PEERCRED,&peer,&size) || size!=sizeof(peer) || peer.pid!=c.state.pid || peer.uid!=c.holder_uid || peer.gid!=c.holder_gid || live())return EACCES;
    const uint16_t endian=1;if(*(const unsigned char *)&endian!=1)return ENOTSUP;
    char fields[512];snprintf(fields,sizeof(fields),"\"byte_order\":\"little\",\"request_bytes\":%zu,\"ack_bytes\":%zu,\"dev\":%"PRIu64",\"ino\":%"PRIu64",\"rdev\":%"PRIu64",\"self_uids\":[%u,%u,%u,%u],\"self_gid\":%u,\"peer_pid\":%ld,\"peer_uid\":%u,\"peer_gid\":%u",sizeof(struct m398_request),sizeof(struct m398_ack),c.dev,c.ino,c.rdev,u[0],u[1],u[2],u[3],g[0],(long)peer.pid,(unsigned)peer.uid,(unsigned)peer.gid);
    int error=row("identity404",fields);if(error)return error;
    struct m398_ack a;error=send_request(M398_HELLO,NULL,0);if(!error)error=receive_ack(M398_HELLO,&a);if(error)return error;
    int witness=-1;error=borrowed(c.state.pid,c.holder_pfd,c.state.fd,&witness);if(error)return error;
    snprintf(fields,sizeof(fields),"\"source_pid\":%d,\"source_fd\":%d,\"duplicate_fd\":%d,\"pidfd_getfd_rc\":0,\"kcmp_rc\":0,\"dev\":%"PRIu64",\"ino\":%"PRIu64",\"rdev\":%"PRIu64,c.state.pid,c.state.fd,witness,c.dev,c.ino,c.rdev);
    error=row("witness404",fields);int fds[3]={c.journal,c.tap,witness};if(!error)error=send_request(M398_ARM,fds,3);
    int closed=close_one(&witness);if(row("witness_close404",closed?"\"close_rc\":-1":"\"close_rc\":0"))return EIO;if(error || closed)return error?error:closed;
    error=receive_ack(M398_ARM,&a);if(error)return error;
    char line[160],tail;unsigned long pid,fd;unsigned long long ticks;
    error=command(line);if(error)return error;
    if(sscanf(line,"SAMPLER %lu %llu %lu %c",&pid,&ticks,&fd,&tail)!=3 || pid<=1 || pid>INT_MAX || fd>INT_MAX || !ticks)return EINVAL;
    c.sampler=(pid_t)pid;c.sampler_ticks=(uint64_t)ticks;
    if(birth(c.sampler)!=c.sampler_ticks || ids(c.sampler,u,g) || u[0] || u[1] || u[2] || u[3])return EACCES;
    c.sampler_pfd=(int)syscall(SYS_pidfd_open,c.sampler,0);if(c.sampler_pfd<0)return errno;
    int sampler_flags=fcntl(c.sampler_pfd,F_GETFD);if(sampler_flags<0 || !(sampler_flags&FD_CLOEXEC) || birth(c.sampler)!=c.sampler_ticks)return ESTALE;
    struct m579_clock_observation sampler_clock;
    if(m579_global_clock_observe(c.sampler,c.sampler_ticks,c.sampler_pfd,&sampler_clock) ||
       m579_global_clock_pair(&c.self_clock,&sampler_clock))return ESTALE;
    int sample_witness=-1;error=borrowed(c.sampler,c.sampler_pfd,(int)fd,&sample_witness);if(error)return error;
    long same_ofd=syscall(SYS_kcmp,c.state.pid,getpid(),0,(unsigned long)c.state.fd,(unsigned long)sample_witness);
    int sample_closed=close_one(&sample_witness);if(same_ofd || sample_closed)return same_ofd<0?errno:ESTALE;
    snprintf(fields,sizeof(fields),"\"sampler_pid\":%ld,\"sampler_ticks\":%"PRIu64",\"sampler_fd\":%lu,\"pidfd_getfd_rc\":0,\"holder_sampler_kcmp_rc\":0,\"duplicate_close_rc\":0",(long)c.sampler,c.sampler_ticks,fd);
    if(row("sampler_registered404",fields))return EIO;
    error=command(line);if(error)return error;if(strcmp(line,"DISARM\n"))return EINVAL;
    struct pollfd finished={c.sampler_pfd,POLLIN,0};if(poll(&finished,1,0)!=1 || finished.revents!=POLLIN)return EBUSY;
    char proc[80];snprintf(proc,sizeof(proc),"/proc/%ld/stat",(long)c.sampler);
    errno=0;if(fstatat(AT_FDCWD,proc,&st,0)==0 || errno!=ENOENT)return EBUSY;
    snprintf(fields,sizeof(fields),"\"sampler_pid\":%ld,\"sampler_ticks\":%"PRIu64",\"pidfd_revents\":%d,\"proc_stat_errno\":%d",(long)c.sampler,c.sampler_ticks,finished.revents,ENOENT);
    if(row("sampler_exit404",fields))return EIO;
    error=send_request(M398_DISARM,NULL,0);if(!error)error=receive_ack(M398_DISARM,&a);if(error)return error;
    struct stat j,t;if(fstat(c.journal,&j) || fstat(c.tap,&t) || !same(&j,&c.journal_stat) || !same(&t,&c.tap_stat) ||
      j.st_size<0 || j.st_size>25000000 || t.st_size<0 || (uint64_t)t.st_size!=a.tap_bytes || fsync(c.journal) || fsync(c.tap))return ESTALE;
    snprintf(fields,sizeof(fields),"\"journal_dev\":%"PRIu64",\"journal_ino\":%"PRIu64",\"journal_bytes\":%"PRIu64",\"tap_dev\":%"PRIu64",\"tap_ino\":%"PRIu64",\"tap_bytes\":%"PRIu64",\"rows\":%"PRIu64,(uint64_t)j.st_dev,(uint64_t)j.st_ino,(uint64_t)j.st_size,(uint64_t)t.st_dev,(uint64_t)t.st_ino,(uint64_t)t.st_size,a.rows);
    if(row("files404",fields))return EIO;
    if(close_one(&c.sampler_pfd) || close_one(&c.holder_pfd) || close_one(&c.socket) || close_one(&c.journal) || close_one(&c.tap) || close_one(&c.directory))return EIO;
    return row("complete404","\"control_integrity_only\":true,\"accepted\":false");
}
int main(int argc,char **argv)
{
    memset(&c,0,sizeof(c));c.socket=c.holder_pfd=c.sampler_pfd=c.directory=c.journal=c.tap=c.ledger=-1;
    if(argc!=13 || getuid() || geteuid()){fprintf(stderr,"usage(root): CONTROL404 PID TICKS UID GID FD DEV INO RDEV BOOT RUN32 --directory PRIVATE_DIR\n");return 2;}
    uint64_t values[8];for(unsigned i=0;i<8;++i){values[i]=number(argv[i+1],i==0 || i==4?INT_MAX:UINT64_MAX-1);if(values[i]==UINT64_MAX)return 2;}
    if(values[0]<=1 || !values[1] || values[2]>UINT_MAX || values[3]>UINT_MAX || c404_boot(argv[9]) || c404_hex(argv[10],32) || strcmp(argv[11],"--directory") || argv[12][0]!='/')return 2;
    c.state.pid=(int)values[0];c.state.ticks=values[1];c.holder_uid=(uid_t)values[2];c.holder_gid=(gid_t)values[3];c.state.fd=(int)values[4];c.dev=values[5];c.ino=values[6];c.rdev=values[7];
    memcpy(c.boot,argv[9],36);memcpy(c.run,argv[10],32);
    int error=run_client(argv[12]);if(error){char field[80];snprintf(field,sizeof(field),"\"error_errno\":%d",error);if(c.ledger>=0)(void)row("failure404",field);fprintf(stderr,"CONTROL404 failed errno=%d\n",error);}
    int close_error=0;int *fds[]={&c.socket,&c.holder_pfd,&c.sampler_pfd,&c.directory,&c.journal,&c.tap};for(unsigned i=0;i<6;++i)if(close_one(fds[i]))close_error=1;
    if(c.ledger>=0 && fsync(c.ledger))close_error=1;
    if(close_one(&c.ledger))close_error=1;
    return error || close_error ? 1 : 0;
}
