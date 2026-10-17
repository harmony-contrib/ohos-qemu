// Run as init's netsysnative identity. Only the owned OpenVPN child can provide
// management events; connection publication also requires its real TUN bridge.
#include "management_protocol.h"
#include "profile_policy.h"
#include "process_lifecycle.h"
#include "session_files.h"
#include "session_contract.h"
#include "broker_runtime.h"
#include "init_socket.h"
#include "networkvpn_client.h"
#include <array>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <poll.h>
#include <signal.h>
#include <string>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

namespace {
using OHOS::NetManagerStandard::NetworkVpnClient;
constexpr uid_t NETSYS_UID = 1098;
constexpr char CLIENT[] = "/system/bin/qemu_openvpn";
constexpr char BRIDGE[] = "unix:/system/bin/qemu_openvpn_tun";
volatile sig_atomic_t stopping = 0;
std::string sessionToken;
void Stop(int) { stopping = 1; }

struct Fd {
    int value = -1;
    Fd() = default;
    Fd(const Fd &) = delete;
    Fd &operator=(const Fd &) = delete;
    ~Fd() { if (value >= 0) close(value); }
};

bool Write(int fd, const std::string &text)
{
    size_t offset = 0;
    while (offset < text.size()) {
        ssize_t count = write(fd, text.data() + offset, text.size() - offset);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) return false;
        offset += static_cast<size_t>(count);
    }
    return true;
}

bool Notify(int state)
{
    return NetworkVpnClient::GetInstance().NotifyConnectStage(
        OhosOpenvpn::Stage(sessionToken, "{\"updateState\":{\"state\":" + std::to_string(state) + "}}"), 0) == 0;
}

bool SaveSecret(int directory, const char *name, const std::string &contents)
{
    Fd file;
    file.value = openat(directory, name, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    return file.value >= 0 && Write(file.value, contents) && fsync(file.value) == 0;
}

int Listen(const std::string &path)
{
    if (path.size() >= sizeof(sockaddr_un::sun_path)) return -1;
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    if (fd < 0) return -1;
    sockaddr_un address {};
    address.sun_family = AF_UNIX;
    memcpy(address.sun_path, path.c_str(), path.size() + 1);
    if (bind(fd, reinterpret_cast<sockaddr *>(&address), sizeof(address)) != 0 ||
        chmod(path.c_str(), 0600) != 0 || listen(fd, 2) != 0) {
        close(fd);
        return -1;
    }
    return fd;
}

bool Credentials(int fd, ucred &peer)
{
    socklen_t length = sizeof(peer);
    return getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &peer, &length) == 0 &&
           length == sizeof(peer) && peer.uid == NETSYS_UID && peer.pid > 0;
}

bool IsBridgeChild(pid_t bridge, pid_t client)
{
    const auto start = OhosOpenvpn::ProcessStart(bridge);
    return !start.empty() && OhosOpenvpn::Executable(bridge, "/system/bin/qemu_openvpn_tun") &&
        OhosOpenvpn::Parent(bridge) == client && OhosOpenvpn::ProcessStart(bridge) == start;
}

struct Session {
    std::string directory;
    Fd directoryFd;
    pid_t child = -1;
    ~Session()
    {
        if (child > 0) {
            // The child remains unreaped until its entire owned process group
            // has received termination. Its PID cannot be reused during this.
            kill(child, SIGTERM);
            for (int attempt = 0; attempt < 30; ++attempt) {
                siginfo_t info {};
                if (waitid(P_PID, child, &info, WEXITED | WNOHANG | WNOWAIT) == 0 && info.si_pid) break;
                poll(nullptr, 0, 100);
            }
            kill(child, SIGKILL);
            int status = 0;
            while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
        }
        if (!directory.empty() && directoryFd.value >= 0) {
            for (const char *name : {"client.ovpn", "askpass", "management", "ready"})
                unlinkat(directoryFd.value, name, 0);
            rmdir(directory.c_str());
        }
    }
};

bool Spawn(Session &session, const std::string &config, const std::string &management,
           const std::string &ready, const std::string &interfaceName)
{
    std::vector<std::string> arguments {
        CLIENT, "--client", "--config", config, "--dev", "tun", "--dev-type", "tun",
        "--dev-node", BRIDGE, "--script-security", "2", "--ifconfig-noexec",
        "--route-noexec", "--management", management, "unix", "--management-client",
        "--management-hold", "--setenv", "OHOS_OPENVPN_READY_SOCKET", ready,
        "--setenv", "OHOS_OPENVPN_SESSION", sessionToken,
        "--setenv", "OHOS_OPENVPN_INTERFACE", interfaceName,
        "--verb", "3",
    };
    std::vector<char *> argv;
    for (auto &argument : arguments) argv.push_back(argument.data());
    argv.push_back(nullptr);
    const pid_t supervisor = getpid();
    session.child = fork();
    if (session.child < 0) return false;
    if (session.child == 0) {
        if (!OhosOpenvpn::BindToParent(supervisor)) _exit(126);
        execv(CLIENT, argv.data());
        _exit(127);
    }
    return true;
}

int Observe(Session &session, int managementListener, int readyListener)
{
    Fd management;
    Fd bridgeReady;
    bool tunReady = false;
    bool tlsConnected = false;
    bool published = false;
    std::string pending;
    auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(90);
    while (!stopping) {
        siginfo_t exited {};
        if (waitid(P_PID, session.child, &exited, WEXITED | WNOHANG | WNOWAIT) < 0 || exited.si_pid) return 5;
        if (!published && std::chrono::steady_clock::now() >= deadline) return 6;
        pollfd descriptors[4] {{managementListener, POLLIN, 0}, {readyListener, POLLIN, 0},
                              {management.value, POLLIN, 0}, {bridgeReady.value, POLLIN, 0}};
        int result = poll(descriptors, 4, 500);
        if (result < 0) { if (errno == EINTR) continue; return 7; }
        if (descriptors[0].revents & POLLIN) {
            Fd incoming;
            incoming.value = accept4(managementListener, nullptr, nullptr, SOCK_CLOEXEC | SOCK_NONBLOCK);
            ucred peer {};
            if (incoming.value < 0 || management.value >= 0 ||
                !Credentials(incoming.value, peer) || peer.pid != session.child) return 8;
            management.value = incoming.value;
            incoming.value = -1;
            // The peer is our exact exec child. No externally supplied state
            // channel or test flag can turn this session into CONNECTED.
            if (!Write(management.value, "state on\nhold release\n")) return 9;
        }
        if (descriptors[1].revents & POLLIN) {
            Fd incoming;
            incoming.value = accept4(readyListener, nullptr, nullptr, SOCK_CLOEXEC | SOCK_NONBLOCK);
            ucred peer {};
            if (incoming.value < 0 || !Credentials(incoming.value, peer) ||
                !IsBridgeChild(peer.pid, session.child) || tunReady) return 10;
            pollfd response {incoming.value, POLLIN, 0};
            char ready = 0;
            if (poll(&response, 1, 2000) <= 0 || read(incoming.value, &ready, 1) != 1 || ready != 'R') return 11;
            bridgeReady.value = incoming.value;
            incoming.value = -1;
            tunReady = true;
        }
        // A one-time readiness byte must not outlive the real TUN bridge. Its
        // private peer connection stays open for the entire forwarding loop.
        if (descriptors[2].revents & (POLLERR | POLLHUP | POLLNVAL)) return 12;
        if (descriptors[2].revents & POLLIN) {
            std::array<char, 1024> bytes {};
            ssize_t count = read(management.value, bytes.data(), bytes.size());
            if (count < 0 && (errno == EAGAIN || errno == EINTR)) continue;
            if (count <= 0) return 13;
            for (ssize_t i = 0; i < count; ++i) {
                if (bytes[i] == '\0' || pending.size() >= 4096) return 14;
                pending += bytes[i];
                if (bytes[i] != '\n') continue;
                auto event = OhosOpenvpn::ParseState(pending);
                pending.clear();
                if (event == OhosOpenvpn::Event::Connected) tlsConnected = true;
                else if (event == OhosOpenvpn::Event::Reconnecting) {
                    if (NetworkVpnClient::GetInstance().NotifyConnectStage(
                        OhosOpenvpn::Stage(sessionToken, "{\"reconnecting\":{}}"), 0) != 0) return 15;
                    tlsConnected = published = tunReady = false;
                    if (bridgeReady.value >= 0) close(bridgeReady.value);
                    bridgeReady.value = -1;
                    deadline = std::chrono::steady_clock::now() + std::chrono::seconds(90);
                } else if (event != OhosOpenvpn::Event::Ignore) return 15;
            }
        }
        if (tunReady && descriptors[3].revents) return 17;
        if (!published && tlsConnected && tunReady) {
            pollfd live {bridgeReady.value, POLLIN, 0};
            if (poll(&live, 1, 0) != 0) return 17;
            if (!Notify(4)) return 16;
            published = true;
        }
    }
    return 0;
}

int RunWorkerBody(const OhosOpenvpn::BrokerCommand &command, const std::string &directory)
{
    sessionToken = command.session.token;
    stopping = 0;
    Session session;
    session.directory = directory;
    session.directoryFd.value = open(directory.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (session.directoryFd.value < 0 || !OhosOpenvpn::PrivateOwned(session.directoryFd.value, true, NETSYS_UID)) return 3;
    // The token was generated by the VPN service and supplied through the
    // authenticated netsys broker transport, never argv or a test parameter.
    if (NetworkVpnClient::GetInstance().NotifyConnectStage(
        OhosOpenvpn::Stage(sessionToken, "{\"claim\":{}}"), 0) != 0) return 3;
    std::string config = command.session.profile;
    std::string password = command.session.password;
    if (!OhosOpenvpn::ValidateProfile(config)) return 3;
    if (!password.empty()) {
        if (!SaveSecret(session.directoryFd.value, "askpass", password + "\n")) return 3;
        config += "\naskpass " + session.directory + "/askpass\n";
    }
    OhosOpenvpn::EraseSecret(password);
    if (!SaveSecret(session.directoryFd.value, "client.ovpn", config)) return 3;
    OhosOpenvpn::EraseSecret(config);
    Fd management;
    Fd ready;
    management.value = Listen(session.directory + "/management");
    ready.value = Listen(session.directory + "/ready");
    if (management.value < 0 || ready.value < 0 ||
        !Spawn(session, session.directory + "/client.ovpn", session.directory + "/management",
               session.directory + "/ready", command.interfaceName)) return 4;
    return Observe(session, management.value, ready.value);
}

int RunWorker(const OhosOpenvpn::BrokerCommand &command, const std::string &directory)
{
    const int result = RunWorkerBody(command, directory);
    if (!stopping) Notify(5);
    return result;
}

int Run()
{
    if (getuid() != NETSYS_UID || geteuid() != NETSYS_UID) return 2;
    // init owns this listener; no pathname unlink/rebind or unauthenticated
    // command-line activation can impersonate the privileged broker endpoint.
    const int listener = GetControlSocket("qemu_openvpn");
    if (!OhosOpenvpn::InitBrokerListener(listener, OhosOpenvpn::BROKER_SOCKET) || listen(listener, 8) != 0) return 3;
    OhosOpenvpn::BrokerRuntime broker("/data/service/el1/public/vpn/qemu_openvpn", NETSYS_UID, RunWorker);
    if (!broker.Open()) return 3;
    while (!stopping) {
        broker.Reap();
        pollfd ready {listener, POLLIN, 0};
        const int available = poll(&ready, 1, 200);
        if (available < 0 && errno == EINTR) continue;
        if (available < 0 || ready.revents & (POLLERR | POLLHUP | POLLNVAL)) return 4;
        if (available == 0) continue;
        OhosOpenvpn::BrokerFd connection(accept4(listener, nullptr, nullptr, SOCK_CLOEXEC | SOCK_NONBLOCK));
        if (connection.value < 0) { if (errno == EINTR || errno == EAGAIN) continue; return 4; }
        if (!OhosOpenvpn::NativeBrokerPeer(connection.value)) continue;
        std::string wire;
        OhosOpenvpn::BrokerCommand command;
        if (!OhosOpenvpn::ReadFrame(connection.value, wire) || !OhosOpenvpn::DecodeBroker(wire, command)) continue;
        OhosOpenvpn::EraseSecret(wire);
        const int result = command.start && !OhosOpenvpn::ValidateProfile(command.session.profile) ? EINVAL :
            broker.Apply(command, listener, connection.value);
        OhosOpenvpn::EraseSecret(command.session.profile);
        OhosOpenvpn::EraseSecret(command.session.password);
        // Delivery failure leaves a real accepted worker owned by its token;
        // the caller reports failure and rolls it back with that same token.
        pid_t worker = -1; std::string workerStart;
        const std::string reply = result == 0 && command.start ?
            (broker.Identity(command.session.token, worker, workerStart) ? OhosOpenvpn::StartReply(worker, workerStart) : std::to_string(EIO)) :
            std::to_string(result);
        OhosOpenvpn::SendFrame(connection.value, reply);
    }
    return broker.Shutdown() ? 0 : 5;
}
}

int main()
{
    signal(SIGTERM, Stop);
    signal(SIGINT, Stop);
    signal(SIGHUP, Stop);
    signal(SIGPIPE, SIG_IGN);
    signal(SIGCHLD, SIG_DFL);
    return Run();
}
