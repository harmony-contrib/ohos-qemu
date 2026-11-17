/* SPDX-License-Identifier: Apache-2.0
 * One root-armed, bounded, process-local diagnostic journal. RT producers only
 * copy bounded bytes/lineage into a try-lock ring. The worker owns all IO.
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#include "audio_onset579.h"
#include "audio_onset580_wire.h"
#include "onset579_clock_domain.h"
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <sstream>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
namespace OHOS { namespace AudioStandard { namespace Onset579 {
namespace {
constexpr uint64_t RING = 128, ROWS = 12000, RAW_LIMIT = 64U * 1024U * 1024U;
struct Row {
    Kind kind {}; uint64_t seq = 0, cut = 0, renderer = 0, ringFrame = 0, before = 0, after = 0;
    int32_t uid = -1; uint32_t session = 0, frames = 0, rate = 0, channels = 0, format = 0;
    bool committed = false; Spans spans; uint32_t size = 0; std::array<uint8_t, MAX_PCM> pcm {};
};
struct ReadCut { uint64_t id = 0; int32_t uid = -1; uint32_t session = 0, frames = 0; bool committed = false; };
thread_local ReadCut readCut;
struct Journal {
    std::atomic<uint64_t> armed {0};
    std::atomic<bool> stopping {false}, busy {false};
    std::atomic_flag writer = ATOMIC_FLAG_INIT;
    std::atomic<uint64_t> head {0}, tail {0}, serial {0}, instances {0}, lost {0};
    std::array<Row, RING> rows;
    std::atomic<uint64_t> produced {0}, raw {0};
    uint64_t drained = 0, birth = 0, peerBirth = 0;
    int listener = -1, peer = -1, peerPidFd = -1, journal = -1; pid_t pid = 0, peerPid = 0;
    struct stat file {}; m579_clock_observation ownClock {}, peerClock {}; char boot[40] {}, run[33] {};
    char used[64][32] {}; unsigned epochs = 0; int error = 0;
    pthread_t thread {}; bool ready = false;
};
Journal state;
pthread_once_t once = PTHREAD_ONCE_INIT;
uint64_t Clock()
{
    struct timespec t {};
    if (clock_gettime(CLOCK_MONOTONIC, &t) || t.tv_sec < 0 || t.tv_nsec < 0 || t.tv_nsec >= 1000000000L) { return 0; }
    return static_cast<uint64_t>(t.tv_sec) * 1000000000U + static_cast<uint64_t>(t.tv_nsec);
}
uint64_t Birth(pid_t pid)
{
    char path[64], raw[4096]; snprintf(path, sizeof(path), "/proc/%ld/stat", static_cast<long>(pid));
    FILE *f = fopen(path, "r"); if (!f) { return 0; }
    bool ok = fgets(raw, sizeof(raw), f) != nullptr; int closed = fclose(f);
    if (!ok || closed) { return 0; }
    char *p = strrchr(raw, ')'); if (!p || p[1] != ' ') { return 0; } p += 2;
    for (int i = 3; i < 22; ++i) { p = strchr(p, ' '); if (!p) { return 0; } ++p; }
    char *end = nullptr; errno = 0; auto n = strtoull(p, &end, 10);
    return errno || !end || *end != ' ' ? 0 : n;
}
bool GlobalObserve(pid_t pid, uint64_t birth, int held, m579_clock_observation &out)
{
    return m579_global_clock_observe(pid,birth,held,&out) == 0;
}
std::string GlobalJson(const char *role,const m579_clock_observation &observation)
{
    char buffer[4096];
    if (m579_clock_buffer(buffer,sizeof(buffer),state.run,role,&observation)) {
        state.error = EIO; return "null";
    }
    return buffer;
}
bool RefreshClocks()
{
    return GlobalObserve(state.pid,state.birth,-1,state.ownClock) &&
        GlobalObserve(state.peerPid,state.peerBirth,state.peerPidFd,state.peerClock) &&
        m579_global_clock_pair(&state.ownClock,&state.peerClock) == 0;
}
bool Write(const std::string &line)
{
    struct stat st {};
    if (state.journal < 0 || fstat(state.journal, &st) || st.st_dev != state.file.st_dev ||
        st.st_ino != state.file.st_ino || st.st_nlink != 1 || st.st_uid != 0 || (st.st_mode & 0777) != 0600) { return false; }
    size_t offset = 0;
    while (offset < line.size()) {
        ssize_t n = write(state.journal, line.data() + offset, line.size() - offset);
        if (n < 0 && errno == EINTR) { continue; }
        if (n <= 0) { return false; } offset += static_cast<size_t>(n);
    }
    return true;
}
void Ack(int error)
{
    o580_ack a {O580_MAGIC, O580_VERSION, static_cast<uint32_t>(error), state.armed.load() ? 1U : 0U,
        static_cast<uint32_t>(state.pid), 0, state.birth, state.produced.load(), state.drained, state.lost.load()};
    if (state.peer >= 0 && send(state.peer, &a, sizeof(a), MSG_NOSIGNAL | MSG_DONTWAIT) != static_cast<ssize_t>(sizeof(a))) {
        state.error = EIO; state.armed.store(false);
    }
}
void Begin()
{
    std::ostringstream s;
    s << "{\"kind\":\"begin580\",\"protocol\":580,\"run\":\"" << state.run
      << "\",\"pid\":" << state.pid << ",\"birth\":" << state.birth << ",\"boot\":\"" << state.boot
      << "\",\"uid\":" << getuid() << ",\"euid\":" << geteuid()
      << ",\"clock_variant\":\"kernel_global_monotonic\",\"producer_clock\":" << GlobalJson("af_producer",state.ownClock)
      << ",\"peer_pid\":" << state.peerPid << ",\"peer_birth\":" << state.peerBirth
      << ",\"peer_uid\":0,\"peer_clock\":" << GlobalJson("af_client",state.peerClock)
      << ",\"journal_dev\":" << state.file.st_dev << ",\"journal_ino\":" << state.file.st_ino
      << ",\"source\":\"actual_renderer_read_and_HPAE_lineage\",\"onset_proven\":false}\n";
    if (!Write(s.str())) { state.error = EIO; }
}
void Drain()
{
    uint64_t tail = state.tail.load(std::memory_order_relaxed);
    if (tail == state.head.load(std::memory_order_acquire)) { return; }
    const Row &r = state.rows[tail % RING];
    std::ostringstream s;
    s << "{\"kind\":\"row580\",\"protocol\":580,\"run\":\"" << state.run << "\",\"seq\":" << r.seq
      << ",\"type\":" << static_cast<uint32_t>(r.kind) << ",\"cut\":" << r.cut << ",\"renderer\":" << r.renderer
      << ",\"uid\":" << r.uid << ",\"session\":" << r.session << ",\"ring_frame\":" << r.ringFrame
      << ",\"frames\":" << r.frames << ",\"rate\":" << r.rate << ",\"channels\":" << r.channels
      << ",\"format\":" << r.format << ",\"before_ns\":" << r.before << ",\"after_ns\":" << r.after
      << ",\"committed\":" << (r.committed ? "true" : "false")
      << ",\"lineage_valid\":" << (r.spans.valid ? "true" : "false") << ",\"spans\":[";
    for (uint32_t i = 0; i < r.spans.count; ++i) {
        const Span &p = r.spans.spans[i]; if (i) { s << ','; }
        s << '[' << p.cut << ',' << p.begin << ',' << p.out << ',' << p.frames << ']';
    }
    s << "],\"pcm_hex\":\"";
    static constexpr char HEX[] = "0123456789abcdef";
    for (uint32_t i = 0; i < r.size; ++i) { s << HEX[r.pcm[i] >> 4] << HEX[r.pcm[i] & 15]; }
    s << "\",\"onset_proven\":false}\n";
    if (r.seq != state.drained || !Write(s.str())) { state.error = EIO; }
    ++state.drained; state.tail.store(tail + 1, std::memory_order_release);
}
bool Seal(int reason)
{
    state.armed.store(false);
    if (state.busy.load() || state.head.load() != state.tail.load()) { return false; }
    if (state.journal < 0) { return true; }
    pollfd alive {state.peerPidFd, POLLIN, 0};
    if (state.peerPidFd < 0 || poll(&alive, 1, 0) != 0 || Birth(state.peerPid) != state.peerBirth) {
        state.error = ESTALE;
    }
    if (!RefreshClocks()) { state.error = ESTALE; }
    std::ostringstream s;
    s << "{\"kind\":\"end580\",\"protocol\":580,\"run\":\"" << state.run
      << "\",\"produced\":" << state.produced.load() << ",\"drained\":" << state.drained
      << ",\"raw_bytes\":" << state.raw.load() << ",\"lost\":" << state.lost.load()
      << ",\"error\":" << (state.error ? state.error : reason)
      << ",\"producer_clock\":" << GlobalJson("af_producer",state.ownClock)
      << ",\"peer_clock\":" << GlobalJson("af_client",state.peerClock)
      << ",\"writer_quiescent\":true,\"onset_proven\":false}\n";
    pollfd live {state.peerPidFd, POLLIN, 0};
    if (state.peerPidFd < 0 || poll(&live, 1, 0) != 0 || Birth(state.peerPid) != state.peerBirth) {
        state.error = ESTALE;
    }
    if (!Write(s.str()) || fsync(state.journal)) { state.error = EIO; }
    if (close(state.journal)) { state.error = EIO; } state.journal = -1;
    Ack(state.error ? state.error : reason);
    return true;
}
int Request()
{
    o580_request r {}; int passed = -1; char control[CMSG_SPACE(sizeof(int) * 2)] {};
    iovec iov {&r, sizeof(r)}; msghdr m {}; m.msg_iov = &iov; m.msg_iovlen = 1;
    m.msg_control = control; m.msg_controllen = sizeof(control);
    ssize_t n = recvmsg(state.peer, &m, MSG_DONTWAIT | MSG_CMSG_CLOEXEC);
    if (n < 0 && (errno == EINTR || errno == EAGAIN)) { return 0; }
    unsigned fds = 0;
    for (cmsghdr *c = CMSG_FIRSTHDR(&m); c; c = CMSG_NXTHDR(&m, c)) {
        if (c->cmsg_level != SOL_SOCKET || c->cmsg_type != SCM_RIGHTS || c->cmsg_len < CMSG_LEN(0)) { continue; }
        size_t count = (c->cmsg_len - CMSG_LEN(0)) / sizeof(int); auto values = reinterpret_cast<int *>(CMSG_DATA(c));
        for (size_t k = 0; k < count; ++k) { ++fds; if (passed < 0) { passed = values[k]; } else { close(values[k]); } }
    }
    int error = 0;
    bool header = n == static_cast<ssize_t>(sizeof(r)) && !(m.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) && r.magic == O580_MAGIC &&
        r.version == O580_VERSION && r.pid == static_cast<uint32_t>(state.pid) && r.birth == state.birth;
    if (!header) { error = EPROTO; }
    else if (r.op == O580_DISARM && fds == 0 && !memcmp(r.run, state.run, 32) && state.journal >= 0) {
        state.armed.store(false); return 1;
    } else if (r.op == O580_ARM && fds == 1 && state.journal < 0 && !state.busy.load() && state.epochs < 64) {
        for (char v : r.run) { if (!strchr("0123456789abcdef", v) || v == 0) { error = EINVAL; } }
        for (unsigned k = 0; k < state.epochs; ++k) { if (!memcmp(state.used[k], r.run, 32)) { error = EALREADY; } }
        struct stat st {}; int flags = fcntl(passed, F_GETFL);
        if (fstat(passed, &st) || !S_ISREG(st.st_mode) || st.st_uid || st.st_nlink != 1 || st.st_size ||
            (st.st_mode & 0777) != 0600 || flags < 0 || (flags & (O_APPEND | O_NONBLOCK)) ||
            (flags & O_ACCMODE) != O_RDWR || lseek(passed, 0, SEEK_CUR) != 0) { error = EACCES; }
        if (!error && !RefreshClocks()) { error = ESTALE; }
        if (!error) {
            state.journal = passed; passed = -1; state.file = st; state.error = 0;
            memcpy(state.run, r.run, 32); state.run[32] = 0;
            memcpy(state.used[state.epochs++], r.run, 32);
            state.head.store(0); state.tail.store(0); state.produced.store(0); state.drained = 0; state.raw.store(0); state.lost.store(0);
            Begin(); if (!state.error) { state.armed.store(state.epochs, std::memory_order_release); } error = state.error;
        }
    } else { error = EBUSY; }
    if (passed >= 0) { close(passed); }
    Ack(error); return header ? 0 : -1;
}
void *Worker(void *)
{
    int closing = 0;
    while (!state.stopping.load()) {
        while (state.tail.load() != state.head.load()) { Drain(); }
        if (closing && !state.busy.load() && state.head.load() == state.tail.load() &&
            Seal(closing == 1 ? 0 : closing)) { closing = 0; }
        pollfd p {state.peer < 0 ? state.listener : state.peer, POLLIN, 0};
        int rc = poll(&p, 1, 2); if (rc < 0 && errno == EINTR) { continue; }
        if (rc < 0) { state.error = errno; break; }
        if (!rc) { continue; }
        if (state.peer < 0) {
            int fd = accept4(state.listener, nullptr, nullptr, SOCK_CLOEXEC | SOCK_NONBLOCK); if (fd < 0) { continue; }
            ucred cred {}; socklen_t size = sizeof(cred); m579_clock_observation peerClock {};
            if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &cred, &size) || size != sizeof(cred) || cred.uid != 0 ||
                !Birth(cred.pid)) { close(fd); continue; }
            const uint64_t birth = Birth(cred.pid);
#ifdef SYS_pidfd_open
            int pidfd = static_cast<int>(syscall(SYS_pidfd_open, cred.pid, 0));
#else
            int pidfd = -1;
#endif
            pollfd live {pidfd, POLLIN, 0};
            if (pidfd < 0 || !birth || Birth(cred.pid) != birth || poll(&live, 1, 0) != 0) {
                if (pidfd >= 0) { close(pidfd); } close(fd); continue;
            }
            if (!GlobalObserve(cred.pid,birth,pidfd,peerClock) ||
                m579_global_clock_pair(&state.ownClock,&peerClock)) { close(pidfd); close(fd); continue; }
            state.peer = fd; state.peerPid = cred.pid; state.peerBirth = birth; state.peerClock = peerClock;
            state.peerPidFd = pidfd;
        } else if (p.revents & (POLLHUP | POLLERR | POLLNVAL)) {
            state.armed.store(false); closing = EPIPE; close(state.peer); state.peer = -1;
            if (state.peerPidFd >= 0) { close(state.peerPidFd); state.peerPidFd = -1; }
        } else if (p.revents & POLLIN) {
            int result = Request(); if (result) { closing = result > 0 ? 1 : EPROTO; state.armed.store(false); }
        }
    }
    state.armed.store(false);
    while (state.busy.load()) { timespec t {0, 1000000}; nanosleep(&t, nullptr); }
    while (state.tail.load() != state.head.load()) { Drain(); }
    Seal(ECANCELED); if (state.peerPidFd >= 0) { close(state.peerPidFd); }
    if (state.peer >= 0) { close(state.peer); } if (state.listener >= 0) { close(state.listener); }
    return nullptr;
}
void Start()
{
    if (!state.head.is_lock_free() || !state.serial.is_lock_free() || !state.instances.is_lock_free()) { return; }
    state.pid = getpid(); state.birth = Birth(state.pid);
    if (m579_global_clock_review_gate() || !state.birth || !GlobalObserve(state.pid,state.birth,-1,state.ownClock)) { return; }
    FILE *f = fopen("/proc/sys/kernel/random/boot_id", "r"); if (!f) { return; }
    bool ok = fgets(state.boot, sizeof(state.boot), f) != nullptr; int closed = fclose(f);
    state.boot[strcspn(state.boot, "\n")] = 0; if (!ok || closed || strlen(state.boot) != 36) { return; }
    state.listener = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0); if (state.listener < 0) { return; }
    sockaddr_un address {}; address.sun_family = AF_UNIX;
    int count = snprintf(address.sun_path + 1, sizeof(address.sun_path) - 1, "ohos-audio580/%ld/%llu",
        static_cast<long>(state.pid), static_cast<unsigned long long>(state.birth));
    socklen_t len = static_cast<socklen_t>(offsetof(sockaddr_un, sun_path) + 1 + count);
    if (count <= 0 || count >= static_cast<int>(sizeof(address.sun_path) - 1) ||
        bind(state.listener, reinterpret_cast<sockaddr *>(&address), len) || listen(state.listener, 1) ||
        pthread_create(&state.thread, nullptr, Worker, nullptr)) { close(state.listener); state.listener = -1; return; }
    state.ready = true;
}
Row *Loan(Kind kind)
{
    const uint64_t epoch = state.armed.load(std::memory_order_acquire);
    if (!epoch || state.pid != getpid()) { return nullptr; }
    if (state.writer.test_and_set(std::memory_order_acquire)) { state.lost.fetch_add(1); return nullptr; }
    state.busy.store(true);
    uint64_t h = state.head.load(std::memory_order_relaxed), t = state.tail.load(std::memory_order_acquire);
    if (state.armed.load() != epoch || h - t >= RING || state.produced.load() >= ROWS || state.serial.load() == UINT64_MAX) {
        state.lost.fetch_add(1); state.busy.store(false); state.writer.clear(std::memory_order_release); return nullptr;
    }
    Row *r = &state.rows[h % RING];
    r->kind = kind; r->seq = state.produced.load(); r->cut = 0; r->renderer = 0; r->ringFrame = 0;
    r->uid = -1; r->session = r->frames = r->rate = r->channels = r->format = r->size = 0;
    r->committed = false; r->spans.Clear(); r->before = Clock(); return r;
}
void Publish(Row *r)
{
    r->after = Clock();
    if (!r->before || r->after < r->before || state.raw.load() > RAW_LIMIT - r->size) { state.lost.fetch_add(1); r->size = 0; }
    state.raw.fetch_add(r->size); state.produced.fetch_add(1);
    state.head.fetch_add(1, std::memory_order_release); state.busy.store(false); state.writer.clear(std::memory_order_release);
}
struct Shutdown { ~Shutdown() { if (state.ready && state.pid == getpid()) { state.stopping.store(true); pthread_join(state.thread, nullptr); } } } shutdown;
} // namespace
void Initialize() { pthread_once(&once, Start); }
uint64_t NewInstance() { return state.instances.fetch_add(1) + 1; }
void ClearRead() { readCut = {}; }
uint64_t PrepareRead(uint64_t renderer, int32_t uid, uint32_t session, uint64_t ringFrame,
    uint32_t frames, uint32_t rate, uint32_t channels, uint32_t format,
    const void *first, size_t firstBytes, const void *second, size_t secondBytes)
{
    readCut = {};
    Row *r = Loan(Kind::READ); if (!r) { return 0; }
    if (!renderer || !first || (secondBytes && !second) || firstBytes > MAX_PCM || secondBytes > MAX_PCM - firstBytes) {
        state.lost.fetch_add(1); Publish(r); return 0;
    }
    r->cut = state.serial.fetch_add(1) + 1; r->renderer = renderer; r->uid = uid; r->session = session;
    r->ringFrame = ringFrame; r->frames = frames; r->rate = rate; r->channels = channels; r->format = format;
    r->size = static_cast<uint32_t>(firstBytes + secondBytes);
    memcpy(r->pcm.data(), first, firstBytes); if (secondBytes) { memcpy(r->pcm.data() + firstBytes, second, secondBytes); }
    uint64_t id = r->cut; readCut = {id, uid, session, frames, false}; Publish(r); return id;
}
void CommitRead(uint64_t cut, bool committed)
{
    if (!cut || readCut.id != cut) { return; }
    readCut.committed = committed; Row *r = Loan(Kind::READ_COMMIT); if (!r) { readCut = {}; return; }
    r->cut = cut; r->committed = committed; Publish(r);
}
Spans TakeRead(int32_t uid, uint32_t session, uint32_t frames)
{
    Spans result;
    if (readCut.id && readCut.committed && readCut.uid == uid && readCut.session == session && readCut.frames == frames) {
        result.Add({readCut.id, 0, 0, frames});
    }
    readCut = {}; return result;
}
void Packet(uint64_t outputInstance, uint32_t rate, uint32_t channels, uint32_t format,
    const Spans &spans, const void *bytes, size_t byteCount)
{
    Row *r = Loan(Kind::MIXED_PACKET); if (!r) { return; }
    r->renderer = outputInstance; r->rate = rate; r->channels = channels; r->format = format; r->spans = spans;
    if (!bytes || byteCount > MAX_PCM) { r->spans.Unknown(); state.lost.fetch_add(1); }
    else { r->size = static_cast<uint32_t>(byteCount); memcpy(r->pcm.data(), bytes, byteCount); }
    Publish(r);
}
} } }
