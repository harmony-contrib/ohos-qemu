// Candidate native bridge: observations originate from OpenVPN's negotiated
// configuration and real TUN FD. No test entry point can synthesize CONNECTED.
#include "networkvpn_client.h"
#include "received_descriptor.h"
#include "process_lifecycle.h"
#include "session_contract.h"
#include "broker_protocol.h"
#include "negotiated_config.h"
#include "route_metrics.h"
#include "dns_transport.h"
#include <arpa/inet.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <array>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <linux/if_tun.h>
#include <net/if.h>
#include <sys/ioctl.h>
#include <string>

extern char **environ;

namespace {
std::string sessionToken;
using OHOS::NetManagerStandard::NetworkVpnClient;
volatile sig_atomic_t stopped = 0;
void Stop(int) { stopped = 1; }
struct Fd {
    int value = -1;
    Fd() = default;
    Fd(const Fd &) = delete;
    Fd &operator=(const Fd &) = delete;
    ~Fd() { if (value >= 0) close(value); }
};
int Decimal(const char *text, int minimum, int maximum)
{
    if (!text || !*text) return -1;
    errno = 0;
    char *end = nullptr;
    long value = strtol(text, &end, 10);
    return errno || *end || value < minimum || value > maximum ? -1 : static_cast<int>(value);
}
bool Notify(const std::string &body)
{
    return NetworkVpnClient::GetInstance().NotifyConnectStage(OhosOpenvpn::Stage(sessionToken, body), 0) == 0;
}
int ReceiveTun(const OhosOpenvpn::NegotiatedConfig &negotiated, bool clear = false)
{
    Fd control;
    control.value = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (control.value < 0) return -1;
    sockaddr_un address {};
    address.sun_family = AF_UNIX;
    const char path[] = "/dev/unix/socket/qemu_openvpn_tunfd";
    memcpy(address.sun_path, path, sizeof(path));
    if (connect(control.value, reinterpret_cast<sockaddr *>(&address), sizeof(address)) < 0) return -1;
    if (!OhosOpenvpn::SendFrame(control.value, std::string("qemu-openvpn-tun-v3\n") + sessionToken + "\n" + (clear ? "clear\n" : "tun\n" + OhosOpenvpn::MetricWire(negotiated)))) return -1;
    if (clear) {
        std::string reply; return OhosOpenvpn::ReadFrame(control.value, reply) && reply == "0" ? 0 : -1;
    }
    pollfd ready { control.value, POLLIN, 0 };
    if (poll(&ready, 1, 2000) <= 0) return -1;
    char byte = 0;
    iovec data { &byte, 1 };
    alignas(cmsghdr) std::array<char, CMSG_SPACE(4 * sizeof(int))> rights {};
    msghdr message {};
    message.msg_iov = &data; message.msg_iovlen = 1;
    message.msg_control = rights.data(); message.msg_controllen = rights.size();
    ssize_t received = recvmsg(control.value, &message, MSG_CMSG_CLOEXEC);
    return OhosOpenvpn::TakeSingleDescriptor(message, received, rights.size());
}
int ConnectReady(char state = 'R')
{
    const char *path = getenv("OHOS_OPENVPN_READY_SOCKET");
    constexpr char prefix[] = "/data/service/el1/public/vpn/qemu_openvpn/session-";
    if (!path || strncmp(path, prefix, sizeof(prefix) - 1) ||
        strlen(path) >= sizeof(sockaddr_un::sun_path) || strstr(path, "..")) return -1;
    Fd socketFd;
    socketFd.value = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (socketFd.value < 0) return -1;
    sockaddr_un remote {};
    remote.sun_family = AF_UNIX;
    memcpy(remote.sun_path, path, strlen(path) + 1);
    if (connect(socketFd.value, reinterpret_cast<sockaddr *>(&remote), sizeof(remote)) != 0 ||
        send(socketFd.value, &state, 1, MSG_NOSIGNAL) != 1) return -1;
    int fd = socketFd.value;
    socketFd.value = -1;
    return fd;
}
int Bridge()
{
    if (getuid() != 1098 || geteuid() != 1098) return 2;
    if (!OhosOpenvpn::BindToParent(getppid())) return 2;
    const int peer = Decimal(getenv("TUNTAP_SOCKET_FD"), 0, std::numeric_limits<int>::max());
    const char *token = getenv("OHOS_OPENVPN_SESSION");
    if (!token || !OhosOpenvpn::Token(token) || peer < 0) return 2;
    sessionToken = token;
    OhosOpenvpn::Environment environment;
    for (char **entry = environ; entry && *entry; ++entry) {
        const char *split = strchr(*entry, '=');
        if (!split) return 2;
        if (!environment.emplace(std::string(*entry, static_cast<size_t>(split - *entry)), std::string(split + 1)).second) return 2;
    }
    OhosOpenvpn::NegotiatedConfig negotiated;
    std::vector<OhosOpenvpn::DnsPolicy> policies;
    if (!OhosOpenvpn::ReadNegotiated(environment, negotiated) || !OhosOpenvpn::ReadDnsPolicies(environment, policies)) return 2;
    int socketType = 0;
    socklen_t socketTypeSize = sizeof(socketType);
    if (getsockopt(peer, SOL_SOCKET, SO_TYPE, &socketType, &socketTypeSize) != 0 ||
        socketType != SOCK_DGRAM) return 2;
    if (ReceiveTun(negotiated, true) != 0) return 3;
    struct MetricsFinally {
        const OhosOpenvpn::NegotiatedConfig &config;
        ~MetricsFinally() { (void)ReceiveTun(config, true); }
    } metricsFinally {negotiated};
    if (!Notify(OhosOpenvpn::NetworkJson(negotiated)) || !Notify("{\"setupVpnTun\":{}}")) return 3;
    Fd tun;
    tun.value = ReceiveTun(negotiated);
    if (tun.value < 0) return 4;
    ifreq request {};
    const char *interfaceName = getenv("OHOS_OPENVPN_INTERFACE");
    if (!interfaceName || !OhosOpenvpn::BrokerInterface(interfaceName) ||
        ioctl(tun.value, TUNGETIFF, &request) < 0 || !(request.ifr_flags & IFF_TUN) || !(request.ifr_flags & IFF_NO_PI) ||
        strnlen(request.ifr_name, IFNAMSIZ) == IFNAMSIZ || strcmp(request.ifr_name, interfaceName)) return 4;
    const char *profile = getenv("OHOS_OPENVPN_PROFILE");
    if (!profile) return 4;
    OhosOpenvpn::DnsForwarder dns(negotiated, std::move(policies), tun.value, interfaceName, sessionToken, profile);
    if (!dns.Good()) return 4;
    Fd ready;
    ready.value = ConnectReady();
    if (ready.value < 0) return 4;
    std::array<unsigned char, 65536> bytes {};
    while (!stopped) {
        pollfd descriptors[3] {{peer, POLLIN, 0}, {tun.value, POLLIN, 0}, {ready.value, POLLIN, 0}};
        int result = poll(descriptors, 3, 1000);
        if (result < 0) { if (errno == EINTR) continue; return 5; }
        if (descriptors[2].revents) return 6;
        for (int i = 0; i < 2; ++i) {
            if (descriptors[i].revents & (POLLERR | POLLHUP | POLLNVAL)) return 6;
            if (!(descriptors[i].revents & POLLIN)) continue;
            ssize_t length = read(descriptors[i].fd, bytes.data(), bytes.size());
            if (length < 0 && (errno == EAGAIN || errno == EINTR)) continue;
            if (length < 20 || (bytes[0] >> 4 != 4 && bytes[0] >> 4 != 6) ||
                (bytes[0] >> 4 == 6 && length < 40)) return 7;
            if (i == 1 && dns.Handle(bytes.data(), static_cast<size_t>(length))) continue;
            int target = i == 0 ? tun.value : peer;
            if (write(target, bytes.data(), length) != length) return 8;
        }
    }
    return 0; // DNS joins before this bridge closes its fd; the manager retains the session TUN until STOP.
}
}
int main()
{
    // Service identity is provided by init/netsys, never changed by this helper.
    signal(SIGTERM, Stop); signal(SIGINT, Stop); signal(SIGHUP, Stop);
    const int result = Bridge();
    if (result != 0 && getuid() == 1098 && geteuid() == 1098 && OhosOpenvpn::Token(sessionToken)) {
        // An authenticated negative readiness byte reports negotiation/config/
        // controller failure promptly; it never substitutes for a real TUN.
        Fd failed; failed.value = ConnectReady('F');
    }
    return result;
}
