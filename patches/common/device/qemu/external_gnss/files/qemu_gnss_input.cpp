/* Copyright (c) 2026 OpenHarmony QEMU contributors. SPDX-License-Identifier: Apache-2.0 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "qemu_gnss_input.h"
#include <algorithm>
#include <atomic>
#include <cerrno>
#include <condition_variable>
#include <fcntl.h>
#include <mutex>
#include <poll.h>
#include <pthread.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <thread>
#include <time.h>
#include <unistd.h>
#include <vector>

namespace OHOS::QemuGnss {
namespace {
constexpr int IO_TIMEOUT_MS = 5000;
constexpr size_t MAX_CALLBACKS = 32;
int64_t MonotonicNs()
{
    timespec time{};
    if (clock_gettime(CLOCK_MONOTONIC, &time) != 0) return -1;
    return static_cast<int64_t>(time.tv_sec) * 1000000000 + time.tv_nsec;
}
bool Nonblocking(int fd)
{
    int flags = fcntl(fd, F_GETFL);
    return flags >= 0 && fcntl(fd, F_SETFL, flags | O_NONBLOCK) == 0 && fcntl(fd, F_SETFD, FD_CLOEXEC) == 0;
}
bool Transfer(int fd, uint8_t* data, size_t size, bool writing, const std::atomic<bool>& stopping)
{
    const int64_t start = MonotonicNs();
    if (start < 0) return false;
    const int64_t deadline = start + static_cast<int64_t>(IO_TIMEOUT_MS) * 1000000;
    size_t done = 0;
    while (done < size && !stopping) {
        const int64_t now = MonotonicNs();
        if (now < 0 || now >= deadline) return false;
        pollfd item{fd, static_cast<short>(writing ? POLLOUT : POLLIN), 0};
        int ready = poll(&item, 1, 50);
        if (ready < 0) { if (errno == EINTR) continue; return false; }
        if (ready == 0) continue;
        ssize_t result;
        if (writing) {
#ifdef MSG_NOSIGNAL
            result = send(fd, data + done, size - done, MSG_NOSIGNAL);
#else
            result = send(fd, data + done, size - done, 0);
#endif
        } else {
            result = recv(fd, data + done, size - done, 0);
        }
        if (result <= 0) {
            if (result < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
            return false;
        }
        done += static_cast<size_t>(result);
    }
    return done == size;
}
bool RandomNonce(Nonce& nonce)
{
    int fd = open("/dev/urandom", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return false;
    size_t done = 0;
    while (done < nonce.size()) {
        ssize_t count = read(fd, nonce.data() + done, nonce.size() - done);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) { close(fd); return false; }
        done += static_cast<size_t>(count);
    }
    close(fd);
    return true;
}
bool Authorized(int fd, uid_t writer)
{
#ifdef __linux__
    ucred credentials{};
    socklen_t length = sizeof(credentials);
    return getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &credentials, &length) == 0 &&
        length == sizeof(credentials) && credentials.uid == writer;
#elif defined(__APPLE__)
    uid_t uid;
    gid_t gid;
    return getpeereid(fd, &uid, &gid) == 0 && uid == writer;
#else
    (void)fd;
    (void)writer;
    return false;
#endif
}
bool RemoveStaleSocket(const std::string& path, const sockaddr_un& address)
{
    struct stat before{};
    if (lstat(path.c_str(), &before) != 0) return errno == ENOENT;
    if (!S_ISSOCK(before.st_mode) || before.st_uid != geteuid()) return false;
    int probe = socket(AF_UNIX, SOCK_STREAM, 0);
    if (probe < 0) return false;
    if (!Nonblocking(probe)) { close(probe); return false; }
    int result = connect(probe, reinterpret_cast<const sockaddr*>(&address), sizeof(address));
    int error = errno;
    close(probe);
    if (result == 0 || error != ECONNREFUSED) return false;
    struct stat current{};
    return lstat(path.c_str(), &current) == 0 && current.st_dev == before.st_dev &&
        current.st_ino == before.st_ino && unlink(path.c_str()) == 0;
}
} // namespace

struct GnssInput::State {
    explicit State(InputConfig value) : config(std::move(value)) {}
    struct Entry { const void* owner; uint64_t generation; Callback callback; };
    const InputConfig config;
    std::mutex mutex;
    std::condition_variable idle;
    std::mutex lifecycle;
    std::condition_variable joined;
    std::atomic<bool> stopping{false};
    std::atomic<bool> running{false};
    pthread_t thread{};
    std::thread::id workerId;
    bool started = false;
    bool joining = false;
    bool enabled = false;
    int listener = -1;
    int client = -1;
    dev_t socketDevice{};
    ino_t socketInode{};
    uint64_t sessionGeneration = 0;
    uint64_t callbackGeneration = 0;
    size_t inFlight = 0;
    int64_t samplingInterval = 0;
    int64_t lastTimestamp = 0;
    std::vector<Entry> callbacks;
    void Invalidate()
    {
        ++sessionGeneration;
        lastTimestamp = 0;
        if (client >= 0) shutdown(client, SHUT_RDWR);
    }
    void RemoveOwnedPath()
    {
        struct stat file{};
        if (lstat(config.socketPath.c_str(), &file) == 0 && S_ISSOCK(file.st_mode) &&
            file.st_dev == socketDevice && file.st_ino == socketInode) unlink(config.socketPath.c_str());
    }
};

GnssInput::GnssInput(InputConfig config) : state_(std::make_shared<State>(std::move(config))) {}
GnssInput::~GnssInput() { Stop(); }
bool GnssInput::IsRunning() const { return state_->running && !state_->stopping; }

bool GnssInput::Start()
{
    auto state = state_;
    std::lock_guard<std::mutex> lifecycle(state->lifecycle);
    if (state->started || state->running) return state->running && !state->stopping && !state->joining;
    sockaddr_un address{};
    if (state->config.socketPath.empty() || state->config.socketPath[0] != '/' ||
        state->config.socketPath.size() >= sizeof(address.sun_path)) return false;
    address.sun_family = AF_UNIX;
#ifdef __APPLE__
    address.sun_len = sizeof(address);
#endif
    std::memcpy(address.sun_path, state->config.socketPath.c_str(), state->config.socketPath.size() + 1);
    if (!RemoveStaleSocket(state->config.socketPath, address)) return false;
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) return false;
    if (!Nonblocking(fd) || bind(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0) {
        close(fd);
        return false;
    }
    struct stat file{};
    if (lstat(state->config.socketPath.c_str(), &file) != 0) { close(fd); return false; }
    state->socketDevice = file.st_dev;
    state->socketInode = file.st_ino;
    if (chmod(state->config.socketPath.c_str(), 0600) != 0 || listen(fd, 1) != 0) {
        close(fd);
        state->RemoveOwnedPath();
        return false;
    }
    {
        std::lock_guard<std::mutex> lock(state->mutex);
        state->listener = fd;
        state->stopping = false;
        state->running = true;
    }
    auto* argument = new std::shared_ptr<State>(state);
    if (pthread_create(&state->thread, nullptr, Run, argument) != 0) {
        delete argument;
        close(fd);
        {
            std::lock_guard<std::mutex> lock(state->mutex);
            state->listener = -1;
            state->running = false;
        }
        state->RemoveOwnedPath();
        return false;
    }
    state->started = true;
    return true;
}

void GnssInput::Stop()
{
    auto state = state_;
    std::unique_lock<std::mutex> lock(state->lifecycle);
    {
        std::lock_guard<std::mutex> lock(state->mutex);
        state->stopping = true;
        state->enabled = false;
        state->callbacks.clear();
        state->Invalidate();
        if (state->listener >= 0) shutdown(state->listener, SHUT_RDWR);
    }
    if (!state->started) return;
    bool self = pthread_equal(pthread_self(), state->thread);
    if (state->joining) {
        if (!self) state->joined.wait(lock, [&] { return !state->joining; });
        return;
    }
    if (self) {
        pthread_detach(state->thread);
        state->started = false;
        return; // Run holds its own State reference, including during callback teardown.
    }
    state->joining = true;
    pthread_t thread = state->thread;
    lock.unlock();
    pthread_join(thread, nullptr);
    lock.lock();
    state->joining = false;
    state->started = false;
    state->joined.notify_all();
}

bool GnssInput::Enable()
{
    auto state = state_;
    std::lock_guard<std::mutex> lock(state->mutex);
    if (!state->running || state->stopping) return false;
    if (!state->enabled) { state->enabled = true; state->Invalidate(); }
    return true;
}
bool GnssInput::Disable()
{
    auto state = state_;
    std::unique_lock<std::mutex> lock(state->mutex);
    if (!state->running || state->stopping) return false;
    state->enabled = false;
    state->Invalidate();
    if (state->workerId != std::this_thread::get_id()) state->idle.wait(lock, [&] { return state->inFlight == 0; });
    return true;
}
bool GnssInput::SetBatch(int64_t samplingInterval, int64_t reportInterval)
{
    if (samplingInterval < MIN_INTERVAL_NS || samplingInterval > MAX_INTERVAL_NS ||
        reportInterval < 0 || reportInterval > MAX_INTERVAL_NS) return false;
    auto state = state_;
    std::lock_guard<std::mutex> lock(state->mutex);
    if (!state->running || state->stopping) return false;
    state->samplingInterval = samplingInterval;
    return true; // Immediate reporting meets the requested maximum report latency; no batching queue.
}
bool GnssInput::Register(const void* owner, Callback callback)
{
    if (!owner || !callback) return false;
    auto state = state_;
    std::lock_guard<std::mutex> lock(state->mutex);
    if (!state->running || state->stopping) return false;
    for (const auto& entry : state->callbacks) if (entry.owner == owner) return true;
    if (state->callbacks.size() >= MAX_CALLBACKS) return false;
    state->callbacks.push_back({owner, ++state->callbackGeneration, std::move(callback)});
    state->Invalidate();
    return true;
}
bool GnssInput::Unregister(const void* owner)
{
    auto state = state_;
    std::unique_lock<std::mutex> lock(state->mutex);
    auto entry = std::find_if(state->callbacks.begin(), state->callbacks.end(),
        [owner](const State::Entry& value) { return value.owner == owner; });
    if (entry == state->callbacks.end()) return false;
    state->callbacks.erase(entry);
    state->Invalidate();
    if (state->workerId != std::this_thread::get_id()) state->idle.wait(lock, [&] { return state->inFlight == 0; });
    return true;
}

void GnssInput::Dispatch(const std::shared_ptr<State>& state, Fix sample, uint64_t generation)
{
    std::vector<State::Entry> callbacks;
    {
        std::lock_guard<std::mutex> lock(state->mutex);
        if (!state->enabled || state->stopping || state->callbacks.empty() ||
            generation != state->sessionGeneration) return;
        const int64_t now = MonotonicNs();
        if (now < 0 || now - state->lastTimestamp < state->samplingInterval) return;
        sample.bootNs = BootNs();
        if (sample.bootNs == 0) return;
        state->lastTimestamp = now;
        callbacks = state->callbacks;
        ++state->inFlight;
    }
    for (const auto& entry : callbacks) {
        bool current;
        {
            std::lock_guard<std::mutex> lock(state->mutex);
            current = state->enabled && !state->stopping && generation == state->sessionGeneration &&
                std::any_of(state->callbacks.begin(), state->callbacks.end(), [&](const State::Entry& registered) {
                    return registered.generation == entry.generation;
                });
        }
        if (current) entry.callback(sample);
    }
    {
        std::lock_guard<std::mutex> lock(state->mutex);
        --state->inFlight;
        state->idle.notify_all();
    }
}

void GnssInput::Serve(const std::shared_ptr<State>& state, int fd)
{
    if (!Authorized(fd, state->config.writerUid)) return;
    uint64_t generation;
    { std::lock_guard<std::mutex> lock(state->mutex); generation = state->sessionGeneration; }
    Nonce nonce;
    if (!RandomNonce(nonce)) return;
    auto hello = MakeHello(nonce);
    if (!Transfer(fd, hello.data(), hello.size(), true, state->stopping)) return;
    uint64_t sequence = 0;
    int64_t utc = 0;
    while (!state->stopping) {
        Frame frame;
        if (!Transfer(fd, frame.data(), frame.size(), false, state->stopping)) return;
        Fix sample;
        if (!DecodeFrame(frame, nonce, sequence, utc, sample)) return;
        { std::lock_guard<std::mutex> lock(state->mutex); if (generation != state->sessionGeneration) return; }
        Dispatch(state, sample, generation);
    }
}

void* GnssInput::Run(void* argument)
{
    auto state = *static_cast<std::shared_ptr<State>*>(argument);
    delete static_cast<std::shared_ptr<State>*>(argument);
    { std::lock_guard<std::mutex> lock(state->mutex); state->workerId = std::this_thread::get_id(); }
    while (!state->stopping) {
        pollfd item{state->listener, POLLIN, 0};
        int ready = poll(&item, 1, 50);
        if (ready < 0) { if (errno == EINTR) continue; break; }
        if (ready == 0 || !(item.revents & POLLIN)) continue;
        int fd = accept(state->listener, nullptr, nullptr);
        if (fd < 0) continue;
        int bufferSize = 4096;
        if (!Nonblocking(fd) || setsockopt(fd, SOL_SOCKET, SO_RCVBUF, &bufferSize, sizeof(bufferSize)) != 0) {
            close(fd);
            continue;
        }
#ifdef SO_NOSIGPIPE
        int enabled = 1;
        if (setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &enabled, sizeof(enabled)) != 0) { close(fd); continue; }
#endif
        { std::lock_guard<std::mutex> lock(state->mutex); state->client = fd; }
        Serve(state, fd);
        { std::lock_guard<std::mutex> lock(state->mutex); state->client = -1; close(fd); }
    }
    {
        std::lock_guard<std::mutex> lock(state->mutex);
        close(state->listener);
        state->listener = -1;
        state->RemoveOwnedPath();
        state->running = false;
        state->idle.notify_all();
    }
    return nullptr;
}
} // namespace OHOS::QemuGnss
