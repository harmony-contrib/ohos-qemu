#pragma once
#include "session_contract.h"
#include <arpa/inet.h>
#include <chrono>
#include <cstring>
#include <limits>
#include <poll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <tuple>

namespace OhosOpenvpn {
constexpr char BROKER_SOCKET[] = "/dev/unix/socket/qemu_openvpn";
constexpr char BROKER_PREFIX[] = "qemu-openvpn-broker-v2\n";
constexpr size_t MAX_BROKER_FRAME = 1024 * 1024 + 8192;
constexpr size_t MAX_BROKER_SESSIONS = 20;
constexpr uid_t BROKER_UID = 1098;
struct BrokerOwner {
    int32_t uid = -1;
    int32_t user = -1;
    std::string bundle;
    std::string vpnId;
    bool operator==(const BrokerOwner &other) const
    { return std::tie(uid, user, bundle, vpnId) == std::tie(other.uid, other.user, other.bundle, other.vpnId); }
};
struct BrokerCommand {
    bool start = false;
    BrokerOwner owner;
    std::string interfaceName;
    SessionConfig session;
};
inline bool BrokerInterface(std::string_view name)
{
    constexpr std::string_view prefix = "multitun-vpn";
    if (name.substr(0, prefix.size()) != prefix || name.size() <= prefix.size() || name.size() >= 16) return false;
    name.remove_prefix(prefix.size());
    if (name[0] == '0' || name.size() > 2) return false;
    unsigned value = 0;
    for (char c : name) { if (c < '0' || c > '9') return false; value = value * 10 + static_cast<unsigned>(c - '0'); }
    return value >= 1 && value <= MAX_BROKER_SESSIONS;
}
inline bool BrokerIdentity(const BrokerCommand &command)
{
    return command.owner.uid >= 0 && command.owner.user >= 0 && !command.owner.bundle.empty() &&
        command.owner.bundle.size() <= 1024 && command.owner.vpnId.size() <= 1024 &&
        command.owner.bundle.find('\0') == std::string::npos && command.owner.vpnId.find('\0') == std::string::npos &&
        BrokerInterface(command.interfaceName) && Token(command.session.token);
}
inline void AppendField(std::string &wire, std::string_view value)
{ wire += std::to_string(value.size()) + "\n"; wire.append(value); }
inline bool TakeField(std::string_view &wire, std::string &value, size_t maximum)
{
    const auto at = wire.find('\n');
    if (!at || at == std::string_view::npos || at > 7 || (at > 1 && wire[0] == '0')) return false;
    size_t size = 0;
    for (char c : wire.substr(0, at)) { if (c < '0' || c > '9') return false; size = size * 10 + static_cast<unsigned>(c - '0'); }
    wire.remove_prefix(at + 1);
    if (size > maximum || size > wire.size()) return false;
    value.assign(wire.substr(0, size)); wire.remove_prefix(size); return true;
}
inline bool TakeId(std::string_view &wire, int32_t &output)
{
    std::string field;
    if (!TakeField(wire, field, 10) || field.empty() || (field.size() > 1 && field[0] == '0')) return false;
    uint64_t value = 0;
    for (char c : field) {
        if (c < '0' || c > '9') return false;
        value = value * 10 + static_cast<unsigned>(c - '0');
        if (value > std::numeric_limits<int32_t>::max()) return false;
    }
    output = static_cast<int32_t>(value); return true;
}
inline std::string EncodeBroker(const BrokerCommand &command)
{
    if (!BrokerIdentity(command) || (command.start ? !ValidSession(command.session) :
        (!command.session.profile.empty() || !command.session.password.empty()))) return {};
    std::string wire = std::string(BROKER_PREFIX) + (command.start ? "start\n" : "stop\n");
    for (auto &field : {std::to_string(command.owner.uid), std::to_string(command.owner.user), command.owner.bundle,
        command.owner.vpnId, command.interfaceName, command.session.token, command.session.profile, command.session.password}) AppendField(wire, field);
    return wire;
}
inline bool DecodeBroker(std::string_view wire, BrokerCommand &output)
{
    if (wire.size() > MAX_BROKER_FRAME || wire.substr(0, sizeof(BROKER_PREFIX) - 1) != BROKER_PREFIX) return false;
    wire.remove_prefix(sizeof(BROKER_PREFIX) - 1);
    BrokerCommand command;
    if (wire.substr(0, 6) == "start\n") { command.start = true; wire.remove_prefix(6); }
    else if (wire.substr(0, 5) == "stop\n") wire.remove_prefix(5);
    else return false;
    if (!TakeId(wire, command.owner.uid) || !TakeId(wire, command.owner.user) ||
        !TakeField(wire, command.owner.bundle, 1024) || !TakeField(wire, command.owner.vpnId, 1024) ||
        !TakeField(wire, command.interfaceName, 15) || !TakeField(wire, command.session.token, 32) ||
        !TakeField(wire, command.session.profile, 1024 * 1024) || !TakeField(wire, command.session.password, 4096) ||
        !wire.empty() || !BrokerIdentity(command) || (command.start ? !ValidSession(command.session) :
        (!command.session.profile.empty() || !command.session.password.empty()))) return false;
    output = std::move(command); return true;
}
inline std::string StartReply(pid_t worker, const std::string &start)
{
    return worker > 1 && !start.empty() ? "0\n" + std::to_string(worker) + "\n" + start : std::string {};
}
inline bool DecodeStartReply(std::string_view reply, pid_t &worker, std::string &start)
{
    if (reply.substr(0, 2) != "0\n" || reply.size() > 40) return false;
    reply.remove_prefix(2);
    const auto at = reply.find('\n');
    if (!at || at == std::string_view::npos || at > 10 || reply[0] == '0') return false;
    uint64_t pid = 0;
    for (char c : reply.substr(0, at)) { if (c < '0' || c > '9') return false; pid = pid * 10 + static_cast<unsigned>(c - '0'); }
    reply.remove_prefix(at + 1);
    if (pid <= 1 || pid > 0x7fffffff || reply.empty() || reply.size() > 20 || reply == "0") return false;
    for (char c : reply) if (c < '0' || c > '9') return false;
    worker = static_cast<pid_t>(pid); start = reply; return true;
}
inline std::string StopIdentity(const BrokerCommand &command)
{
    BrokerCommand identity;
    identity.owner = command.owner; identity.interfaceName = command.interfaceName; identity.session.token = command.session.token;
    return EncodeBroker(identity);
}
class BrokerFd {
public:
    int value = -1;
    explicit BrokerFd(int fd = -1) : value(fd) {}
    BrokerFd(const BrokerFd &) = delete;
    BrokerFd &operator=(const BrokerFd &) = delete;
    ~BrokerFd() { if (value >= 0) close(value); }
};
inline bool Transfer(int fd, void *data, size_t length, bool sending, int milliseconds)
{
    auto *cursor = static_cast<unsigned char *>(data);
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(milliseconds);
    while (length) {
        const auto left = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - std::chrono::steady_clock::now()).count();
        if (left <= 0) return false;
        pollfd event {fd, static_cast<short>(sending ? POLLOUT : POLLIN), 0};
        const int ready = poll(&event, 1, static_cast<int>(left));
        if (ready < 0 && errno == EINTR) continue;
        if (ready <= 0 || !(event.revents & event.events)) return false;
        const ssize_t count = sending ? send(fd, cursor, length, MSG_NOSIGNAL | MSG_DONTWAIT) : recv(fd, cursor, length, MSG_DONTWAIT);
        if (count < 0 && (errno == EINTR || errno == EAGAIN)) continue;
        if (count <= 0) return false;
        cursor += count; length -= static_cast<size_t>(count);
    }
    return true;
}
inline int FrameRemaining(const std::chrono::steady_clock::time_point &deadline)
{
    const auto left = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - std::chrono::steady_clock::now()).count();
    return left > 0 ? static_cast<int>(left) : 0;
}
inline bool SendFrame(int fd, const std::string &frame, int milliseconds = 2000)
{
    if (frame.empty() || frame.size() > MAX_BROKER_FRAME) return false;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(milliseconds);
    uint32_t length = htonl(static_cast<uint32_t>(frame.size()));
    return Transfer(fd, &length, sizeof(length), true, FrameRemaining(deadline)) &&
        Transfer(fd, const_cast<char *>(frame.data()), frame.size(), true, FrameRemaining(deadline));
}
inline bool ReadFrame(int fd, std::string &frame, int milliseconds = 2000)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(milliseconds);
    uint32_t length = 0;
    if (!Transfer(fd, &length, sizeof(length), false, FrameRemaining(deadline))) return false;
    length = ntohl(length);
    if (!length || length > MAX_BROKER_FRAME) return false;
    std::string data(length, '\0');
    if (!Transfer(fd, data.data(), data.size(), false, FrameRemaining(deadline))) return false;
    frame = std::move(data); return true;
}
inline bool BrokerPeer(int fd, uid_t uid, const char *executable, pid_t &pid, std::string *startTime = nullptr)
{
#ifdef __linux__
    ucred peer {}; socklen_t size = sizeof(peer);
    if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &peer, &size) != 0 || size != sizeof(peer) || peer.uid != uid) return false;
    const auto start = ProcessStart(peer.pid);
    if (start.empty() || !Executable(peer.pid, executable) || ProcessStart(peer.pid) != start) return false;
    pid = peer.pid;
    if (startTime) *startTime = start;
    return true;
#else
    (void)fd; (void)uid; (void)executable; (void)pid; (void)startTime; return false;
#endif
}
inline bool NativeBrokerPeer(int fd)
{
    pid_t pid = -1; std::string start;
    if (!BrokerPeer(fd, BROKER_UID, "/system/bin/sa_main", pid, &start)) return false;
    std::ifstream input("/proc/" + std::to_string(pid) + "/cmdline", std::ios::binary);
    constexpr char expected[] = "/system/bin/sa_main\0/system/profile/netsysnative.json\0";
    std::array<char, sizeof(expected) + 1> bytes {};
    input.read(bytes.data(), bytes.size());
    return input.eof() && input.gcount() == static_cast<std::streamsize>(sizeof(expected) - 1) &&
        std::string_view(bytes.data(), sizeof(expected) - 1) == std::string_view(expected, sizeof(expected) - 1) &&
        ProcessStart(pid) == start;
}
inline bool InitBrokerListener(int fd, const char *path)
{
    struct stat st {};
    int type = 0; socklen_t typeSize = sizeof(type);
    sockaddr_un address {}; socklen_t addressSize = sizeof(address);
    return fd >= 0 && path && lstat(path, &st) == 0 && S_ISSOCK(st.st_mode) && st.st_uid == BROKER_UID &&
        (st.st_mode & 0777) == 0600 && getsockopt(fd, SOL_SOCKET, SO_TYPE, &type, &typeSize) == 0 &&
        typeSize == sizeof(type) && type == SOCK_STREAM && getsockname(fd, reinterpret_cast<sockaddr *>(&address), &addressSize) == 0 &&
        address.sun_family == AF_UNIX && strnlen(address.sun_path, sizeof(address.sun_path)) < sizeof(address.sun_path) &&
        std::string_view(address.sun_path) == path;
}
inline int ConnectBroker(pid_t &pid)
{
#ifndef __linux__
    (void)pid; return -1;
#else
    struct stat st {};
    if (lstat(BROKER_SOCKET, &st) != 0 || !S_ISSOCK(st.st_mode) || st.st_uid != BROKER_UID || (st.st_mode & 0777) != 0600) return -1;
    BrokerFd fd(socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0));
    if (fd.value < 0) return -1;
    sockaddr_un address {}; address.sun_family = AF_UNIX; memcpy(address.sun_path, BROKER_SOCKET, sizeof(BROKER_SOCKET));
    if (connect(fd.value, reinterpret_cast<sockaddr *>(&address), sizeof(address)) != 0) return -1;
    if (!BrokerPeer(fd.value, BROKER_UID, "/system/bin/qemu_openvpn_service", pid)) return -1;
    const int result = fd.value; fd.value = -1; return result;
#endif
}
} // namespace OhosOpenvpn
