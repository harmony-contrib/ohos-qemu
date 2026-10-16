#pragma once
#include <array>
#include <cerrno>
#include <cstdlib>
#include <fstream>
#include <string>
#include <string_view>
#include <sys/types.h>
#include <unistd.h>

namespace OhosOpenvpn {
// Reserved private IPC request. Public signatures and legacy cert types stay
// unchanged. Config, credentials and generation are read in one service lock.
constexpr int SESSION_REQUEST = 0x51455631;
constexpr std::string_view STAGE_PREFIX = "qemu-openvpn ";
struct SessionConfig { std::string token; std::string profile; std::string password; };
inline bool Token(std::string_view value)
{
    if (value.size() != 32) return false;
    for (char c : value) if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
    return true;
}
inline bool ValidSession(const SessionConfig &value)
{
    return Token(value.token) && !value.profile.empty() && value.profile.size() <= 1024 * 1024 &&
        value.password.size() <= 4096 && value.profile.find('\0') == std::string::npos &&
        value.password.find_first_of("\0\r\n", 0, 3) == std::string::npos;
}
inline std::string EncodeSession(const SessionConfig &value)
{
    if (!ValidSession(value)) return {};
    return value.token + "\n" + std::to_string(value.profile.size()) + "\n" +
        std::to_string(value.password.size()) + "\n" + value.profile + value.password;
}
inline bool DecodeSession(std::string_view wire, SessionConfig &output)
{
    if (wire.size() > 1024 * 1024 + 4200) return false;
    std::array<std::string_view, 3> fields {};
    for (auto &field : fields) {
        const auto end = wire.find('\n');
        if (end == std::string_view::npos) return false;
        field = wire.substr(0, end); wire.remove_prefix(end + 1);
    }
    std::array<size_t, 2> lengths {};
    for (size_t i = 0; i < 2; ++i) {
        if (fields[i + 1].empty() || fields[i + 1].size() > 7) return false;
        for (char c : fields[i + 1]) {
            if (c < '0' || c > '9') return false;
            lengths[i] = lengths[i] * 10 + static_cast<unsigned>(c - '0');
        }
    }
    if (lengths[0] > 1024 * 1024 || lengths[1] > 4096 || lengths[0] + lengths[1] != wire.size()) return false;
    SessionConfig value {std::string(fields[0]), std::string(wire.substr(0, lengths[0])),
                         std::string(wire.substr(lengths[0]))};
    if (!ValidSession(value)) return false;
    output = std::move(value);
    return true;
}
inline std::string Stage(const std::string &token, const std::string &body)
{
    return Token(token) ? std::string(STAGE_PREFIX) + token + " " + body : std::string {};
}
inline bool DecodeStage(std::string_view stage, std::string &token, std::string &body)
{
    if (stage.substr(0, STAGE_PREFIX.size()) != STAGE_PREFIX || stage.size() > 128 * 1024) return false;
    stage.remove_prefix(STAGE_PREFIX.size());
    if (stage.size() < 34 || stage[32] != ' ' || !Token(stage.substr(0, 32))) return false;
    token = stage.substr(0, 32); body = stage.substr(33);
    return !body.empty() && body.find('\0') == std::string::npos;
}
inline bool Executable(pid_t pid, const char *expected)
{
    if (pid <= 1) return false;
    std::array<char, 512> path {};
    const std::string link = "/proc/" + std::to_string(pid) + "/exe";
    const ssize_t size = readlink(link.c_str(), path.data(), path.size());
    return size > 0 && static_cast<size_t>(size) < path.size() &&
        std::string_view(path.data(), static_cast<size_t>(size)) == expected;
}
inline pid_t Parent(pid_t pid)
{
    std::ifstream input("/proc/" + std::to_string(pid) + "/status");
    std::string line;
    while (std::getline(input, line)) {
        if (line.compare(0, 5, "PPid:")) continue;
        char *end = nullptr; errno = 0;
        const long value = strtol(line.c_str() + 5, &end, 10);
        while (end && (*end == ' ' || *end == '\t')) ++end;
        if (errno || !end || *end || value <= 1 || value > 0x7fffffff) return -1;
        return static_cast<pid_t>(value);
    }
    return -1;
}
enum class SessionRole { Invalid, Supervisor, Bridge };
inline SessionRole CallerRole(pid_t caller, pid_t supervisor)
{
    if (supervisor <= 1 || !Executable(supervisor, "/system/bin/qemu_openvpn_service")) return SessionRole::Invalid;
    if (caller == supervisor) return SessionRole::Supervisor;
    if (!Executable(caller, "/system/bin/qemu_openvpn_tun")) return SessionRole::Invalid;
    const pid_t client = Parent(caller);
    return Executable(client, "/system/bin/qemu_openvpn") && Parent(client) == supervisor ?
        SessionRole::Bridge : SessionRole::Invalid;
}
} // namespace OhosOpenvpn
