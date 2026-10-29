#if defined(__arm__) && !defined(__aarch64__)
#include "media598_onset.h"
#else
/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Include in pcm_hw.c. Fixed process-local diagnostic, enabled only by398 macro.
 * WRITEI side: bounded memory snapshot/copy + lock-free atomics + native clocks.
 * No file IO, allocation, mutex, poll, socket, fstat, kcmp or added PCM ioctl.
 * NON-RT worker: actual credentials/pidfd/FD proof, control and bounded drain.
 * This NEW write398 protocol is intentionally rejected by unchanged379 verifier.
 */
#ifndef MEDIA398_ONSET_H
#define MEDIA398_ONSET_H
#include "media398_wire.h"
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <poll.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
#ifdef __linux__
#include <sys/syscall.h>
#ifndef MSG_CMSG_CLOEXEC
#error Linux398 requires native atomic SCM_RIGHTS CLOEXEC support
#endif
#endif

struct m398_credential { pid_t pid; uid_t uid; gid_t gid; unsigned seen; };
struct m398_snapshot { uint64_t appl, hw; int state, coherent; };
struct m398_hw {
    _Atomic int live;
    _Atomic unsigned users;
    _Atomic uint64_t instance;
    _Atomic uint64_t clock579_epoch, reset579_epoch;
    _Atomic int clock579_type, clock579_mode;
    int fd, card, device, subdevice;
    struct stat file;
};
struct m398_record {
    uint64_t epoch, instance, seq, offset, before_ns, after_ns, returned_ns;
    struct m398_snapshot before, after;
    int64_t accepted;
    uint64_t requested;
    uint64_t clock579_epoch, reset579_epoch, clock579_after_epoch, reset579_after_epoch;
    int clock579_type, clock579_mode;
    int error, empty_eagain, snapshot_valid;
    unsigned bytes;
    unsigned char pcm[M398_PCM_BYTES];
};
struct m398_loan {
    int active;
    struct m398_hw *hw;
    struct m398_record *record;
};
struct m398_state {
    pthread_mutex_t control, registry;
    pthread_t thread;
    _Atomic int stopping, armed, busy, failed, poisoned;
    atomic_flag writer;
    _Atomic uint64_t head, tail;
    struct m398_hw hw[M398_HW_MAX];
    struct m398_record ring[M398_RING];
    pid_t pid, peer_pid;
    uid_t peer_uid; gid_t peer_gid;
    uint64_t ticks, peer_ticks, next_instance, epoch, instance;
    struct stat time_ns, peer_time_ns, journal_stat, tap_stat;
    char boot[40], run[33], seen[M398_RUN_MAX][32];
    unsigned used;
    int listener, peer, peer_pidfd, journal, tap, initialized;
    _Atomic int selected;
    int closing, close_error;
    uint64_t produced_rows, produced_bytes, drained_rows, drained_bytes, journal_bytes;
};
static struct m398_state m398;
static pthread_once_t m398_once = PTHREAD_ONCE_INIT;
static _Atomic int m398_forked; /* Not reset by an interrupted pthread_once initializer. */

static int m398_same_file(const struct stat *a, const struct stat *b)
{
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino && a->st_rdev == b->st_rdev &&
        a->st_mode == b->st_mode && a->st_uid == b->st_uid && a->st_gid == b->st_gid && a->st_nlink == b->st_nlink;
}
static uint64_t m398_clock(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t) || t.tv_sec < 0 || t.tv_nsec < 0 || t.tv_nsec >= 1000000000L) return 0;
    if ((uint64_t)t.tv_sec > (UINT64_MAX - (uint64_t)t.tv_nsec) / UINT64_C(1000000000)) return 0;
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}
static uint64_t m398_birth(pid_t pid)
{
    char path[80], raw[4096]; snprintf(path, sizeof(path), "/proc/%ld/stat", (long)pid);
    FILE *f = fopen(path, "r"); if (!f) return 0;
    int ok = fgets(raw, sizeof(raw), f) != NULL; if (fclose(f) || !ok) return 0;
    char *p = strrchr(raw, ')'); if (!p || p[1] != ' ') return 0; p += 2;
    for (int field = 3; field < 22; ++field) { p = strchr(p, ' '); if (!p) return 0; ++p; }
    char *end; errno = 0; unsigned long long ticks = strtoull(p, &end, 10);
    return errno || !end || *end != ' ' ? 0 : (uint64_t)ticks;
}
static int m398_boot(char boot[40])
{
    memset(boot, 0, 40); FILE *f = fopen("/proc/sys/kernel/random/boot_id", "r"); if (!f) return errno;
    int ok = fgets(boot, 40, f) != NULL; if (fclose(f) || !ok) return EIO;
    boot[strcspn(boot, "\n")] = 0;
    if (strlen(boot) != 36) return EINVAL;
    for (int i = 0; i < 36; ++i)
        if ((i == 8 || i == 13 || i == 18 || i == 23) ? boot[i] != '-' :
            !boot[i] || !strchr("0123456789abcdef", boot[i])) return EINVAL;
    return 0;
}
static int m398_time_ns(pid_t pid, struct stat *st)
{
    char path[80]; snprintf(path, sizeof(path), "/proc/%ld/ns/time", (long)pid);
    return stat(path, st) ? errno : 0; /* Absent is not silently same clock domain. */
}
static int m398_root_uids(pid_t pid)
{
    char path[80], line[1024]; unsigned a,b,c,d; int found = 0;
    snprintf(path, sizeof(path), "/proc/%ld/status", (long)pid);
    FILE *f = fopen(path, "r"); if (!f) return errno;
    while (fgets(line, sizeof(line), f)) if (!strncmp(line, "Uid:", 4)) {
        found = sscanf(line, "Uid: %u %u %u %u", &a,&b,&c,&d) == 4 && !a && !b && !c && !d;
        break;
    }
    if (fclose(f)) return EIO;
    return found ? 0 : EACCES;
}
static int m398_pidfd(pid_t pid)
{
#if defined(__linux__) && defined(SYS_pidfd_open)
    int fd=(int)syscall(SYS_pidfd_open, pid, 0);
    if(fd>=0) {
        int flags=fcntl(fd,F_GETFD);
        if(flags<0 || !(flags&FD_CLOEXEC)){close(fd);errno=EPROTO;return -1;}
    }
    return fd;
#else
    (void)pid; errno = ENOTSUP; return -1;
#endif
}
static int m398_kcmp(int a, int b)
{
#if defined(__linux__) && defined(SYS_kcmp)
    long rc = syscall(SYS_kcmp, getpid(), getpid(), 0, a, b);
    return rc < 0 ? errno : rc ? ESTALE : 0;
#else
    (void)a; (void)b; return ENOTSUP;
#endif
}
static int m398_cloexec_nonblock(int fd)
{
    int flags = fcntl(fd, F_GETFL);
    return flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0 || fcntl(fd, F_SETFD, FD_CLOEXEC) < 0 ? errno : 0;
}
static int m398_close_one(int *fd)
{
    int owned = *fd; *fd = -1; /* Close once; never retry a potentially reused number. */
    return owned >= 0 && close(owned) ? errno : 0;
}
static void m398_fail(struct m398_state *s, int poison)
{
    atomic_store_explicit(&s->failed, 1, memory_order_release);
    atomic_store(&s->armed, 0);
    if (poison) atomic_store(&s->poisoned, 1);
}
static int m398_holder_live(struct m398_state *s)
{
    struct stat ns;
    return getpid()!=s->pid || m398_birth(s->pid)!=s->ticks || m398_time_ns(s->pid,&ns) ||
        ns.st_dev!=s->time_ns.st_dev || ns.st_ino!=s->time_ns.st_ino ? ESTALE : 0;
}
static int m398_peer_live(struct m398_state *s)
{
    if (s->peer < 0 || s->peer_pidfd < 0) return EPIPE;
    struct pollfd p[2] = {{s->peer, POLLIN, 0}, {s->peer_pidfd, POLLIN, 0}};
    int rc = poll(p, 2, 0); if (rc < 0) return errno;
    if (p[0].revents & (POLLERR|POLLHUP|POLLNVAL) || p[1].revents) return EPIPE;
    if (m398_birth(s->peer_pid) != s->peer_ticks || m398_root_uids(s->peer_pid)) return ESTALE;
    struct stat ns;
    if (m398_time_ns(s->peer_pid, &ns) || ns.st_dev != s->peer_time_ns.st_dev || ns.st_ino != s->peer_time_ns.st_ino)
        return ESTALE;
    return 0;
}
static int m398_peer_admit(struct m398_state *s, int fd)
{
#ifdef __linux__
    int passcred=1;
    if(setsockopt(fd,SOL_SOCKET,SO_PASSCRED,&passcred,sizeof(passcred)))return errno;
    struct ucred peer; socklen_t size = sizeof(peer);
    if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &peer, &size) || size != sizeof(peer) || peer.uid || peer.pid <= 1)
        return EACCES;
    uint64_t ticks = m398_birth(peer.pid); struct stat ns;
    if (!ticks || m398_root_uids(peer.pid) || m398_time_ns(peer.pid, &ns)) return EACCES;
    int pidfd = m398_pidfd(peer.pid); if (pidfd < 0) return errno;
    if (fcntl(pidfd, F_SETFD, FD_CLOEXEC) || m398_birth(peer.pid) != ticks) { close(pidfd); return ESTALE; }
    s->peer = fd; s->peer_pidfd = pidfd; s->peer_pid = peer.pid;
    s->peer_uid = peer.uid; s->peer_gid = peer.gid; s->peer_ticks = ticks; s->peer_time_ns = ns;
    return m398_peer_live(s);
#else
    (void)s; (void)fd; return ENOTSUP;
#endif
}
static int m398_receive(int socket, struct m398_request *r, int fds[16], unsigned *count,struct m398_credential *credential)
{
    union { struct cmsghdr align; char bytes[CMSG_SPACE(253 * sizeof(int)) + CMSG_SPACE(64)]; } control;
    memset(&control, 0, sizeof(control)); memset(r, 0, sizeof(*r));
    struct iovec io = {r, sizeof(*r)}; struct msghdr message; memset(&message, 0, sizeof(message));
    for (unsigned i=0;i<16;++i) fds[i]=-1;
    if(credential)memset(credential,0,sizeof(*credential));
    *count=0; message.msg_iov=&io; message.msg_iovlen=1;
    message.msg_control=control.bytes; message.msg_controllen=sizeof(control.bytes);
    int flags=MSG_DONTWAIT;
#ifdef MSG_CMSG_CLOEXEC
    flags |= MSG_CMSG_CLOEXEC;
#endif
    ssize_t n=recvmsg(socket,&message,flags); if(n<0)return errno;
    int bad=n!=(ssize_t)sizeof(*r) || (message.msg_flags & (MSG_TRUNC|MSG_CTRUNC)); unsigned rights=0;
    size_t cap=message.msg_controllen<sizeof(control.bytes)?message.msg_controllen:sizeof(control.bytes);
    message.msg_controllen=cap;
    for(struct cmsghdr *c=CMSG_FIRSTHDR(&message);c;c=CMSG_NXTHDR(&message,c)) {
        size_t off=(size_t)((char*)c-control.bytes);
        if(off>cap || cap-off<sizeof(*c)) {bad=1;break;}
#if defined(__linux__) && defined(SCM_CREDENTIALS)
        if(c->cmsg_level==SOL_SOCKET && c->cmsg_type==SCM_CREDENTIALS) {
            size_t data=(size_t)((char*)CMSG_DATA(c)-control.bytes);
            if(c->cmsg_len!=CMSG_LEN(sizeof(struct ucred)) || data>cap || cap-data<sizeof(struct ucred)) {bad=1;continue;}
            if(credential) {
                struct ucred actual;memcpy(&actual,CMSG_DATA(c),sizeof(actual));
                credential->pid=actual.pid;credential->uid=actual.uid;credential->gid=actual.gid;++credential->seen;
            }
            continue;
        }
#endif
        if(c->cmsg_level!=SOL_SOCKET || c->cmsg_type!=SCM_RIGHTS || c->cmsg_len<CMSG_LEN(0)) {bad=1;continue;}
        ++rights;size_t bytes=c->cmsg_len-CMSG_LEN(0), data=(size_t)((char*)CMSG_DATA(c)-control.bytes);
        if(data>cap) {bad=1;break;}
        int clipped=bytes>cap-data;if(clipped){bytes=cap-data;bad=1;}
        if(bytes%sizeof(int))bad=1;
        for(size_t i=0;i<bytes/sizeof(int);++i) {
            int got;memcpy(&got,(char*)CMSG_DATA(c)+i*sizeof(int),sizeof(got));
            if(*count<16)fds[(*count)++]=got;else {close(got);bad=1;}
        }
        if(clipped)break;
    }
    if(rights>1)bad=1;
    if(credential && credential->seen!=1)bad=1;
    for(unsigned i=0;i<*count;++i)if(fcntl(fds[i],F_SETFD,FD_CLOEXEC)<0)bad=1;
    return bad?EPROTO:0;
}
static int m398_close_received(int fds[16])
{
    int error=0;for(unsigned i=0;i<16;++i)if(m398_close_one(&fds[i]))error=EIO;return error;
}
static int m398_file(int fd, struct stat *st, uint64_t size)
{
    int flags=fcntl(fd,F_GETFL);
    if(flags<0 || fstat(fd,st) || !S_ISREG(st->st_mode) || st->st_uid || st->st_nlink!=1 ||
        (st->st_mode&0777)!=0600 || (flags&O_APPEND) || (flags&O_ACCMODE)==O_RDONLY ||
        st->st_size<0 || (uint64_t)st->st_size!=size || lseek(fd,0,SEEK_CUR)!=0)return EINVAL;
    return 0;
}
static int m398_sink_identity(struct m398_state *s)
{
    struct stat j,t;
    return m398_file(s->journal,&j,s->journal_bytes) || m398_file(s->tap,&t,s->drained_bytes) ||
        !m398_same_file(&j,&s->journal_stat) || !m398_same_file(&t,&s->tap_stat) ? ESTALE : 0;
}
static int m398_line(struct m398_state *s,const char *line,int bytes)
{
    if(bytes<=0 || bytes>4095 || m398_sink_identity(s))return EIO;
    if(pwrite(s->journal,line,(size_t)bytes,(off_t)s->journal_bytes)!=bytes)return EIO;
    s->journal_bytes+=(uint64_t)bytes;
    return m398_sink_identity(s);
}
static int m398_unique(struct m398_state *s)
{
    int chosen=-1;for(unsigned i=0;i<M398_HW_MAX;++i)if(atomic_load(&s->hw[i].live)) {
        if(chosen>=0)return -1;chosen=(int)i;
    }
    return chosen;
}
static int m398_header(struct m398_state *s,const struct m398_request *r)
{
    if(m398_holder_live(s) || r->magic!=M398_MAGIC || r->reserved || r->holder_pid!=(uint32_t)s->pid ||
        r->holder_ticks!=s->ticks || memcmp(r->boot,s->boot,40))return EACCES;
    for(unsigned i=0;i<32;++i)if(!r->run[i] || !strchr("0123456789abcdef",r->run[i]))return EINVAL;
    return m398_peer_live(s);
}
static int m398_ack(struct m398_state *s,int error)
{
    struct m398_ack reply={0};
    /* NON-RT snapshot: register cannot reuse the chosen slot between these
     * tuple reads. Retirement may invalidate it; ARM still proves the live OFD. */
    pthread_mutex_lock(&s->registry);
    int chosen=m398_unique(s);
    reply.instance=chosen<0?0:atomic_load(&s->hw[chosen].instance);
    reply.hw_fd=chosen<0?-1:s->hw[chosen].fd;
    pthread_mutex_unlock(&s->registry);
    reply.epoch=s->epoch;
    reply.holder_ticks=s->ticks;reply.rows=s->drained_rows;reply.tap_bytes=s->drained_bytes;
    reply.error=error;reply.holder_pid=s->pid;
    reply.magic=M398_MAGIC;reply.state=atomic_load(&s->armed)?1U:s->closing?2U:0U;reply.failed=(uint32_t)atomic_load(&s->failed);
#ifdef MSG_NOSIGNAL
    int flags=MSG_DONTWAIT|MSG_NOSIGNAL;
#else
    int flags=MSG_DONTWAIT;
#endif
    return send(s->peer,&reply,sizeof(reply),flags)==(ssize_t)sizeof(reply)?0:EIO;
}
static int m398_begin_line(struct m398_state *s)
{
    const struct m398_hw *h=&s->hw[s->selected];char line[2048];
    int n=snprintf(line,sizeof(line),"{\"kind\":\"begin398\",\"protocol\":398,\"snapshot_source\":\"existing_pcm_hw_shared_status_control_no_added_SYNC_PTR\","
        "\"pid\":%ld,\"start_ticks\":%"PRIu64",\"boot\":\"%s\",\"run\":\"%s\",\"epoch\":%"PRIu64",\"instance\":%"PRIu64","
        "\"fd\":%d,\"dev\":%"PRIu64",\"ino\":%"PRIu64",\"rdev\":%"PRIu64",\"card\":%d,\"device\":%d,\"subdevice\":%d,"
        "\"peer_pid\":%ld,\"peer_uid\":%ld,\"peer_gid\":%ld,\"peer_start_ticks\":%"PRIu64","
        "\"holder_time_dev\":%"PRIu64",\"holder_time_ino\":%"PRIu64",\"peer_time_dev\":%"PRIu64",\"peer_time_ino\":%"PRIu64","
        "\"clock579_epoch\":%"PRIu64",\"reset579_epoch\":%"PRIu64",\"clock579_type\":%d,\"clock579_mode\":%d,"
        "\"arm_kcmp_rc\":0,\"arm_witness_closed_before_publish\":true,\"onset_proven\":false}\n",
        (long)s->pid,s->ticks,s->boot,s->run,s->epoch,s->instance,h->fd,(uint64_t)h->file.st_dev,(uint64_t)h->file.st_ino,(uint64_t)h->file.st_rdev,
        h->card,h->device,h->subdevice,(long)s->peer_pid,(long)s->peer_uid,(long)s->peer_gid,s->peer_ticks,
        (uint64_t)s->time_ns.st_dev,(uint64_t)s->time_ns.st_ino,(uint64_t)s->peer_time_ns.st_dev,(uint64_t)s->peer_time_ns.st_ino,
        atomic_load(&h->clock579_epoch),atomic_load(&h->reset579_epoch),atomic_load(&h->clock579_type),atomic_load(&h->clock579_mode));
    return n>0 && n<(int)sizeof(line)?m398_line(s,line,n):EOVERFLOW;
}
static void m398_reset_epoch(struct m398_state *s,const struct m398_request *r,int chosen,uint64_t instance,
    int fds[16],const struct stat *j,const struct stat *t)
{
    /* Called only after the actual kernel/file/header gates in m398_arm_pinned.
     * Tests call it directly ONLY as an explicitly labeled state model. */
    atomic_store(&s->failed,0);atomic_store(&s->armed,-1);
    s->epoch=r->epoch;s->instance=instance;s->selected=chosen;
    memcpy(s->run,r->run,32);s->run[32]=0;memcpy(s->seen[s->used++],r->run,32);
    s->journal=fds[0];s->tap=fds[1];fds[0]=fds[1]=-1;s->journal_stat=*j;s->tap_stat=*t;
    s->produced_rows=s->produced_bytes=s->drained_rows=s->drained_bytes=s->journal_bytes=0;
    atomic_store(&s->head,0);atomic_store(&s->tail,0);
}
static int m398_arm_pinned(struct m398_state *s,const struct m398_request *r,int fds[16],unsigned n,int chosen,uint64_t instance)
{
    if(n!=3 || r->op!=M398_ARM)return EPROTO;
    if(atomic_load(&s->poisoned) || s->selected>=0 || s->closing || atomic_load(&s->armed) || atomic_load(&s->busy) ||
        atomic_load(&s->head)!=atomic_load(&s->tail) || s->used==M398_RUN_MAX || chosen<0 || chosen!=m398_unique(s) ||
        s->epoch==UINT64_MAX || r->epoch!=s->epoch+1)return EBUSY;
    struct m398_hw *h=&s->hw[chosen];
    if(!atomic_load(&h->live) || r->instance!=instance || atomic_load(&h->instance)!=instance)return ESTALE;
    for(unsigned i=0;i<s->used;++i)if(!memcmp(s->seen[i],r->run,32))return EALREADY;
    struct stat j,t,actual,witness;
    if(m398_file(fds[0],&j,0) || m398_file(fds[1],&t,0) || (j.st_dev==t.st_dev && j.st_ino==t.st_ino) ||
        fstat(h->fd,&actual) || !S_ISCHR(actual.st_mode) || !m398_same_file(&actual,&h->file) ||
        fstat(fds[2],&witness) || !m398_same_file(&actual,&witness))return ESTALE;
    int error=m398_kcmp(h->fd,fds[2]);if(error)return error;
    if(!atomic_load(&h->live) || atomic_load(&h->instance)!=instance || m398_peer_live(s))return ESTALE;
    /* No steady-state HW duplicate: diagnostic files must not extend Stop/close.
     * Independent root sampler retains its own verified duplicate only within
     * the separately controlled pre-Stop sampling interval. */
    error=m398_close_one(&fds[2]);if(error){m398_fail(s,1);return error;}
    m398_reset_epoch(s,r,chosen,instance,fds,&j,&t);
    error=m398_begin_line(s);
    if(error || !atomic_load(&h->live) || m398_unique(s)!=chosen || m398_peer_live(s)) {
        m398_fail(s,1);s->closing=1;s->close_error=error?error:ESTALE;return s->close_error;
    }
    int preparing=-1;
    if(atomic_load(&s->failed) || !atomic_compare_exchange_strong(&s->armed,&preparing,(int)s->epoch)) {
        m398_fail(s,1);s->closing=1;s->close_error=ESTALE;return ESTALE;
    }
    return 0;
}
static int m398_arm(struct m398_state *s,const struct m398_request *r,int fds[16],unsigned n)
{
    /* Select and pin under the same mutex as register's users==0 test and
     * metadata replacement. Only the non-RT control thread takes this lock. */
    pthread_mutex_lock(&s->registry);
    int chosen=m398_unique(s);
    if(chosen<0){pthread_mutex_unlock(&s->registry);return EBUSY;}
    struct m398_hw *h=&s->hw[chosen];
    atomic_fetch_add(&h->users,1);
    uint64_t instance=atomic_load(&h->instance);
    pthread_mutex_unlock(&s->registry);
    int error=!atomic_load(&h->live)?ESTALE:m398_arm_pinned(s,r,fds,n,chosen,instance);
    atomic_fetch_sub(&h->users,1);return error;
}
static int m398_drain_one(struct m398_state *s)
{
    uint64_t tail=atomic_load_explicit(&s->tail,memory_order_relaxed);
    if(tail==atomic_load_explicit(&s->head,memory_order_acquire))return 0;
    struct m398_record *r=&s->ring[tail%M398_RING];struct m398_hw *h=&s->hw[s->selected];
    struct stat actual;int stat_rc=fstat(h->fd,&actual),stat_error=stat_rc?errno:0;
    int drain_identity=!stat_rc && atomic_load(&h->live) && atomic_load(&h->instance)==r->instance && m398_same_file(&actual,&h->file);
    if(r->epoch!=s->epoch || r->instance!=s->instance || r->seq!=s->drained_rows || r->offset!=s->drained_bytes ||
        r->bytes>M398_PCM_BYTES || !drain_identity || !r->snapshot_valid || m398_sink_identity(s))m398_fail(s,0);
    /* Raw failure remains a failure; do not publish partial/invalid PCM as good. */
    int wrote=0;
    if(!atomic_load(&s->failed) && r->bytes) {
        wrote=pwrite(s->tap,r->pcm,r->bytes,(off_t)s->drained_bytes)==(ssize_t)r->bytes;
        if(!wrote)m398_fail(s,1);
    }
    if(!r->bytes)wrote=1;
    if(wrote)s->drained_bytes+=r->bytes;
    char line[2048];int n=snprintf(line,sizeof(line),
        "{\"kind\":\"write398\",\"protocol\":398,\"snapshot_source\":\"existing_pcm_hw_shared_status_control_no_added_SYNC_PTR\","
        "\"run\":\"%s\",\"epoch\":%"PRIu64",\"instance\":%"PRIu64",\"seq\":%"PRIu64",\"pid\":%ld,\"fd\":%d,"
        "\"before_ns\":%"PRIu64",\"after_ns\":%"PRIu64",\"returned_ns\":%"PRIu64",\"appl_before\":%"PRIu64",\"appl_after\":%"PRIu64","
        "\"hw_before\":%"PRIu64",\"hw_after\":%"PRIu64",\"state_before\":%d,\"state_after\":%d,\"accepted\":%"PRId64","
        "\"requested\":%"PRIu64",\"tap_offset\":%"PRIu64",\"pcm_bytes\":%u,\"error\":%d,\"empty_eagain\":%d,"
        "\"clock579_epoch\":%"PRIu64",\"reset579_epoch\":%"PRIu64",\"clock579_type\":%d,\"clock579_mode\":%d,"
        "\"clock579_unchanged\":%d,"
        "\"snapshot_valid\":%d,\"drain_fd_stat_rc\":%d,\"drain_fd_stat_errno\":%d,\"drain_identity\":%d,\"failed\":%d,\"onset_proven\":false}\n",
        s->run,r->epoch,r->instance,r->seq,(long)s->pid,h->fd,r->before_ns,r->after_ns,r->returned_ns,
        r->before.appl,r->after.appl,r->before.hw,r->after.hw,r->before.state,r->after.state,r->accepted,r->requested,r->offset,r->bytes,
        r->error,r->empty_eagain,r->clock579_epoch,r->reset579_epoch,r->clock579_type,r->clock579_mode,
        r->clock579_epoch!=0 && !(r->clock579_epoch&1) &&
          r->clock579_epoch==r->clock579_after_epoch && r->reset579_epoch==r->reset579_after_epoch,
        r->snapshot_valid,stat_rc,stat_error,drain_identity,atomic_load(&s->failed));
    /* sink identity uses the actual post-tap size, including a failed short write.
     * A short write causes the next identity check to fail; no success footer. */
    if(n<=0 || n>=(int)sizeof(line) || m398_line(s,line,n))m398_fail(s,1);
    ++s->drained_rows;atomic_store_explicit(&s->tail,tail+1,memory_order_release);return 1;
}
static void m398_seal(struct m398_state *s)
{
    if(s->selected<0 || atomic_load(&s->busy) || atomic_load(&s->head)!=atomic_load(&s->tail))return;
    const struct m398_hw *h=&s->hw[s->selected];
    char line[1536];int n=snprintf(line,sizeof(line),
        "{\"kind\":\"end398\",\"protocol\":398,\"run\":\"%s\",\"epoch\":%"PRIu64",\"instance\":%"PRIu64","
        "\"produced_rows\":%"PRIu64",\"drained_rows\":%"PRIu64",\"produced_pcm_bytes\":%"PRIu64",\"drained_pcm_bytes\":%"PRIu64","
        "\"clock579_epoch\":%"PRIu64",\"reset579_epoch\":%"PRIu64",\"clock579_type\":%d,\"clock579_mode\":%d,"
        "\"failed\":%d,\"reason_errno\":%d,\"writer_quiescent\":true,\"onset_proven\":false}\n",
        s->run,s->epoch,s->instance,s->produced_rows,s->drained_rows,s->produced_bytes,s->drained_bytes,
        atomic_load(&h->clock579_epoch),atomic_load(&h->reset579_epoch),atomic_load(&h->clock579_type),atomic_load(&h->clock579_mode),
        atomic_load(&s->failed),s->close_error);
    if(n<=0 || n>=(int)sizeof(line) || m398_line(s,line,n))m398_fail(s,1);
    int error=m398_close_one(&s->tap);if(m398_close_one(&s->journal))error=EIO;
    if(error)m398_fail(s,1);
    s->selected=-1;s->closing=0;
    if(s->peer>=0 && m398_ack(s,atomic_load(&s->failed)?EIO:0))m398_fail(s,1);
}
static void m398_disconnect(struct m398_state *s,int error)
{
    if(s->selected>=0) {m398_fail(s,1);s->closing=1;s->close_error=error;}
    int one=m398_close_one(&s->peer),two=m398_close_one(&s->peer_pidfd);
    if(one || two)m398_fail(s,1);
}
static void m398_control(struct m398_state *s)
{
    struct m398_request r;struct m398_credential credential;int fds[16];unsigned n=0;
    int error=m398_receive(s->peer,&r,fds,&n,&credential);
    if(!error && (credential.pid!=s->peer_pid || credential.uid!=0 || credential.gid!=s->peer_gid))error=EACCES;
    if(error==EAGAIN || error==EWOULDBLOCK)return;
    if(!error)error=m398_header(s,&r);
    int deferred=0;
    if(!error && r.op==M398_HELLO) {
        if(n || r.epoch || r.instance || s->selected>=0 || atomic_load(&s->poisoned) || m398_unique(s)<0)error=EBUSY;
    } else if(!error && r.op==M398_ARM)error=m398_arm(s,&r,fds,n);
    else if(!error && r.op==M398_DISARM) {
        if(n || s->selected<0 || s->closing || r.epoch!=s->epoch || r.instance!=s->instance || memcmp(r.run,s->run,32))error=ESTALE;
        else {atomic_store(&s->armed,0);s->closing=1;s->close_error=0;deferred=1;}
    } else if(!error)error=EPROTO;
    if(m398_close_received(fds)){error=EIO;m398_fail(s,1);}
    if(error) {if(!deferred)m398_ack(s,error);m398_disconnect(s,error);return;}
    if(!deferred && m398_ack(s,0)){m398_disconnect(s,EIO);return;}
}
static void *m398_worker(void *argument)
{
    struct m398_state *s=argument;
    while(!atomic_load(&s->stopping)) {
        struct pollfd p[3]={{s->listener,POLLIN,0},{s->peer,POLLIN,0},{s->peer_pidfd,POLLIN,0}};
        int rc=poll(p,3,5);if(rc<0 && errno!=EINTR){m398_fail(s,1);break;}
        pthread_mutex_lock(&s->control); /* Never taken by WRITEI or close/retire. */
        if(m398_holder_live(s)){m398_fail(s,1);m398_disconnect(s,ESTALE);}
        if(s->peer>=0 && m398_peer_live(s))m398_disconnect(s,ESTALE);
        if(p[0].revents&POLLIN) {
#ifdef __linux__
            int incoming=accept4(s->listener,NULL,NULL,SOCK_NONBLOCK|SOCK_CLOEXEC);
#else
            int incoming=accept(s->listener,NULL,NULL); /* Host parser models never start this worker. */
#endif
            if(incoming>=0) {
                if(m398_cloexec_nonblock(incoming) || s->peer>=0 || m398_peer_admit(s,incoming)) {
                    if(s->peer==incoming){s->peer=-1;m398_close_one(&s->peer_pidfd);}close(incoming);
                }
            }
        }
        if(s->peer>=0 && p[1].fd==s->peer && (p[1].revents&POLLIN))m398_control(s);
        if(s->selected>=0 && atomic_load(&s->failed)){atomic_store(&s->armed,0);s->closing=1;if(!s->close_error)s->close_error=EIO;}
        for(unsigned i=0;i<8 && s->selected>=0;++i)if(!m398_drain_one(s))break; /* <=8 rows/512KiB/tick. */
        if(s->closing)m398_seal(s);
        pthread_mutex_unlock(&s->control);
    }
    pthread_mutex_lock(&s->control);m398_disconnect(s,ECANCELED);atomic_store(&s->armed,0);
    /* Unload is NON-RT. In-flight WRITEI must already be quiescent at dlclose.
     * A caller violating that precondition gets a failed diagnostic, not a loan
     * silently closed underneath an active writer. */
    if(!atomic_load(&s->busy)) {
        for(unsigned i=0;i<M398_RING && s->selected>=0;++i)if(!m398_drain_one(s))break;
        m398_seal(s);
    }
    m398_close_one(&s->listener);pthread_mutex_unlock(&s->control);return NULL;
}
static void m398_fork_prepare(void)
{
    int saved=errno;
    /* Serialize the non-RT worker's accept/SCM_RIGHTS/publish/close transactions
     * and initializer endpoint creation with fork. No product/RT path uses it. */
    if(!atomic_load(&m398_forked))pthread_mutex_lock(&m398.control);
    errno=saved;
}
static void m398_fork_parent(void)
{
    int saved=errno;if(!atomic_load(&m398_forked))pthread_mutex_unlock(&m398.control);errno=saved;
}
static void m398_fork_child(void)
{
    int saved=errno;
    atomic_store(&m398_forked,1);
    atomic_store(&m398.armed,0);atomic_store(&m398.poisoned,1);m398.initialized=0;
    /* Async-signal-safe close once; no inherited mutex or product hw.fd access.
     * Parent owns all further diagnostics. This child never reinitializes them. */
    (void)m398_close_one(&m398.listener);(void)m398_close_one(&m398.peer);
    (void)m398_close_one(&m398.peer_pidfd);(void)m398_close_one(&m398.journal);
    (void)m398_close_one(&m398.tap);
    errno=saved;
}
static void m398_initialize(void)
{
    struct m398_state *s=&m398;memset(s,0,sizeof(*s));
    s->pid=getpid();s->listener=s->peer=s->peer_pidfd=s->journal=s->tap=-1;atomic_init(&s->selected,-1);
    atomic_init(&s->stopping,0);atomic_init(&s->armed,0);atomic_init(&s->busy,0);atomic_init(&s->failed,0);atomic_init(&s->poisoned,0);
    atomic_init(&s->head,0);atomic_init(&s->tail,0);atomic_flag_clear(&s->writer);
    for(unsigned i=0;i<M398_HW_MAX;++i){atomic_init(&s->hw[i].live,0);atomic_init(&s->hw[i].users,0);atomic_init(&s->hw[i].instance,0);}
    if(!atomic_is_lock_free(&m398_forked) || !atomic_is_lock_free(&s->armed) || !atomic_is_lock_free(&s->busy) || !atomic_is_lock_free(&s->failed) ||
        !atomic_is_lock_free(&s->poisoned) || !atomic_is_lock_free(&s->head) || !atomic_is_lock_free(&s->tail) ||
        !atomic_is_lock_free(&s->selected) || !atomic_is_lock_free(&s->hw[0].live) || !atomic_is_lock_free(&s->hw[0].users) || !atomic_is_lock_free(&s->hw[0].instance))return;
#ifdef __linux__
    s->ticks=m398_birth(s->pid);
    if(!s->ticks || m398_boot(s->boot) || m398_time_ns(s->pid,&s->time_ns) || pthread_mutex_init(&s->control,NULL) || pthread_mutex_init(&s->registry,NULL) ||
        pthread_atfork(m398_fork_prepare,m398_fork_parent,m398_fork_child))return;
    pthread_mutex_lock(&s->control);
    s->listener=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC|SOCK_NONBLOCK,0);if(s->listener<0)goto initialized;
    int passcred=1;
    if(setsockopt(s->listener,SOL_SOCKET,SO_PASSCRED,&passcred,sizeof(passcred))){m398_close_one(&s->listener);goto initialized;}
    struct sockaddr_un name;memset(&name,0,sizeof(name));name.sun_family=AF_UNIX;
    int n=snprintf(name.sun_path+1,sizeof(name.sun_path)-1,"ohos-audio398/%ld/%"PRIu64,(long)s->pid,s->ticks);
    if(n<=0 || n>=(int)sizeof(name.sun_path)-1 ||
        bind(s->listener,(struct sockaddr*)&name,(socklen_t)(offsetof(struct sockaddr_un,sun_path)+1+(size_t)n)) || listen(s->listener,4) ||
        pthread_create(&s->thread,NULL,m398_worker,s)) {m398_close_one(&s->listener);goto initialized;}
    s->initialized=1;
initialized: pthread_mutex_unlock(&s->control);
#else
    /* Production never invents Linux credentials/syscalls on another host. */
    atomic_store(&s->poisoned,1);
#endif
}
static struct m398_hw *m398_register_hw(int fd,int card,int device,int subdevice)
{
    int saved=errno;
    if(atomic_load(&m398_forked)){errno=saved;return NULL;}
    pthread_once(&m398_once,m398_initialize);struct m398_state *s=&m398;struct m398_hw *result=NULL;
    if(!s->initialized || s->pid!=getpid())goto done; /* Forked inherited instance cannot be reused. */
    pthread_mutex_lock(&s->registry); /* NON-RT open/control only; never WRITEI or retire. */
    if(atomic_load(&s->poisoned) || s->next_instance==UINT64_MAX)goto unlock;
    for(unsigned i=0;i<M398_HW_MAX;++i)if((int)i!=s->selected && !atomic_load(&s->hw[i].live) && !atomic_load(&s->hw[i].users)) {
        struct m398_hw *h=&s->hw[i];struct stat st;
        if(fstat(fd,&st) || !S_ISCHR(st.st_mode))break;
        h->fd=fd;h->card=card;h->device=device;h->subdevice=subdevice;h->file=st;
        atomic_store(&h->clock579_epoch,0); atomic_store(&h->reset579_epoch,0);
        atomic_store(&h->clock579_type,-1); atomic_store(&h->clock579_mode,-1);
        atomic_store(&h->instance,++s->next_instance);atomic_store_explicit(&h->live,1,memory_order_release);result=h;
        if(s->selected>=0)m398_fail(s,1);break;
    }
    if(!result)m398_fail(s,1);
unlock: pthread_mutex_unlock(&s->registry);
done: errno=saved;return result;
}
static void m398_clock579(struct m398_hw *hw,int type,int mode)
{
    if(!hw)return;
    uint64_t old=atomic_fetch_add_explicit(&hw->clock579_epoch,1,memory_order_acq_rel);
    atomic_store(&hw->clock579_type,type); atomic_store(&hw->clock579_mode,mode);
    atomic_fetch_add_explicit(&hw->clock579_epoch,1,memory_order_release);
    if(old>UINT64_MAX-2 || (old&1))m398_fail(&m398,1);
}
static void m398_reset579(struct m398_hw *hw)
{
    if(hw && atomic_fetch_add_explicit(&hw->reset579_epoch,1,memory_order_acq_rel)==UINT64_MAX)
        m398_fail(&m398,1);
}
/* RT region begins. Includes no IO/control primitive other than native clock. */
static void m398_retire_hw(struct m398_hw *hw)
{
    if(!hw)return;
    atomic_store_explicit(&hw->live,0,memory_order_release);
    /* No wait, close or mutation of product FD. Worker emits failed end398 if
     * root did not first DISARM and close its independent sampler duplicate. */
    if(atomic_load(&m398.selected)>=0)m398_fail(&m398,1);
}
static int m398_try_loan(struct m398_hw *hw,uint64_t expected,struct m398_loan *loan)
{
    struct m398_state *s=&m398;loan->active=0;
    int observed=atomic_load(&s->armed);
    if(!hw || observed<=0)return 0;
    if(atomic_flag_test_and_set_explicit(&s->writer,memory_order_acquire)){m398_fail(s,0);return 0;}
    atomic_store(&s->busy,1);atomic_fetch_add_explicit(&hw->users,1,memory_order_acquire);
    uint64_t head=atomic_load_explicit(&s->head,memory_order_relaxed),tail=atomic_load_explicit(&s->tail,memory_order_acquire);
    if(atomic_load(&s->armed)!=observed) {
        atomic_fetch_sub(&hw->users,1);atomic_store(&s->busy,0);atomic_flag_clear_explicit(&s->writer,memory_order_release);return 0;
    }
    if(atomic_load(&s->failed) || !atomic_load_explicit(&hw->live,memory_order_acquire) ||
        atomic_load(&hw->instance)!=expected || s->instance!=expected || head-tail>=M398_RING || s->produced_rows>=M398_ROWS_MAX) {
        m398_fail(s,0);atomic_fetch_sub_explicit(&hw->users,1,memory_order_release);atomic_store(&s->busy,0);atomic_flag_clear_explicit(&s->writer,memory_order_release);return 0;
    }
    struct m398_record *r=&s->ring[head%M398_RING];
    r->epoch=s->epoch;r->instance=expected;r->seq=s->produced_rows;r->offset=s->produced_bytes;
    r->clock579_epoch=atomic_load_explicit(&hw->clock579_epoch,memory_order_acquire);
    r->reset579_epoch=atomic_load_explicit(&hw->reset579_epoch,memory_order_acquire);
    r->clock579_type=atomic_load(&hw->clock579_type); r->clock579_mode=atomic_load(&hw->clock579_mode);
    r->bytes=0;r->snapshot_valid=0;loan->active=1;loan->hw=hw;loan->record=r;return 1;
}
static void m398_publish(struct m398_loan *loan,struct m398_snapshot after,const void *pcm,
    uint64_t requested,int64_t accepted,int original_error,uint64_t returned_ns)
{
    if(!loan->active)return;
    struct m398_state *s=&m398;struct m398_record *r=loan->record;
    r->clock579_after_epoch=atomic_load_explicit(&loan->hw->clock579_epoch,memory_order_acquire);
    r->reset579_after_epoch=atomic_load_explicit(&loan->hw->reset579_epoch,memory_order_acquire);
    r->after=after;r->requested=requested;r->accepted=accepted;r->error=original_error;r->returned_ns=returned_ns;
    r->empty_eagain=original_error==-EAGAIN && accepted==0 && after.appl==r->before.appl;
    int positive=original_error==0 && accepted>0;
    int valid=(positive || r->empty_eagain) && requested>0 && accepted>=0 && (uint64_t)accepted<=requested &&
        (uint64_t)accepted<=M398_PCM_BYTES/4 && r->before.coherent && after.coherent && r->before_ns &&
        r->after_ns>=r->before_ns && returned_ns>=r->after_ns &&
        r->before.appl<=INT64_MAX && r->before.hw<=INT64_MAX && after.appl<=INT64_MAX && after.hw<=INT64_MAX &&
        after.appl>=r->before.appl && after.appl-r->before.appl==(uint64_t)accepted && after.hw>=r->before.hw && after.hw<=after.appl &&
        (r->before.state==2 || r->before.state==3) && (after.state==2 || after.state==3) &&
        atomic_load_explicit(&loan->hw->live,memory_order_acquire) && atomic_load(&loan->hw->instance)==r->instance &&
        r->epoch==s->epoch && r->instance==s->instance && !atomic_load(&s->failed) &&
        s->produced_bytes+(uint64_t)accepted*4<=M398_TAP_MAX;
    if(valid){r->bytes=(unsigned)accepted*4;if(r->bytes)memcpy(r->pcm,pcm,r->bytes);r->snapshot_valid=1;s->produced_bytes+=r->bytes;}
    else m398_fail(s,0);
    ++s->produced_rows;
    uint64_t head=atomic_load_explicit(&s->head,memory_order_relaxed);
    atomic_store_explicit(&s->head,head+1,memory_order_release);
    atomic_fetch_sub_explicit(&loan->hw->users,1,memory_order_release);
    atomic_store(&s->busy,0);atomic_flag_clear_explicit(&s->writer,memory_order_release);loan->active=0;
}
/* RT region ends. */
static void __attribute__((destructor)) m398_unload(void)
{
    struct m398_state *s=&m398;
    if(!s->initialized || s->pid!=getpid())return;
    atomic_store(&s->stopping,1);pthread_join(s->thread,NULL);
    /* No product FD is ever closed here. Actual process unload with active
     * audio writes violates ALSA object lifetime and cannot yield proof. */
}
#endif
#endif
