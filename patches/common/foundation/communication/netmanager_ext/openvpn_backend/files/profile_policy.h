#pragma once
#include <array>
#include <string>
#include <string_view>

namespace OhosOpenvpn {
// Keep process ownership, file access and the TUN/management endpoints under
// the supervisor. OpenVPN still validates the syntax and TLS/network options.
// Credentials are inline: a profile cannot make this service read another
// session's files or include a second configuration with executable options.
inline bool ValidateProfile(std::string_view profile)
{
    if (profile.empty() || profile.size() > 1024 * 1024) return false;
    for (unsigned char byte : profile) {
        if ((byte < 32 && byte != '\n' && byte != '\r' && byte != '\t') || byte == 127) return false;
    }
    constexpr std::array<std::string_view, 10> credentials {
        "ca", "cert", "key", "pkcs12", "crl-verify", "tls-auth", "tls-crypt",
        "tls-crypt-v2", "secret", "auth-user-pass",
    };
    constexpr std::string_view options[] {
        "client", "tls-client", "pull", "dev", "dev-type", "proto", "remote", "port",
        "rport", "lport", "local", "nobind", "bind", "resolv-retry", "connect-retry",
        "connect-retry-max", "connect-timeout", "server-poll-timeout", "remote-random",
        "remote-random-hostname", "float", "persist-key", "persist-tun", "persist-local-ip",
        "persist-remote-ip", "auth", "cipher", "data-ciphers", "data-ciphers-fallback",
        "tls-version-min", "tls-version-max", "tls-cipher", "tls-ciphersuites",
        "remote-cert-tls", "remote-cert-ku", "remote-cert-eku", "verify-x509-name",
        "verify-hash", "peer-fingerprint", "key-direction", "auth-nocache", "auth-retry",
        "auth-token", "reneg-sec", "reneg-bytes", "reneg-pkts", "hand-window",
        "tran-window", "tls-timeout", "key-method", "tls-exit", "tls-cert-profile",
        "tls-groups", "tls-ekm", "allow-compression", "compress", "comp-lzo",
        "tun-mtu", "tun-mtu-extra", "link-mtu", "mssfix", "fragment", "max-packet-size",
        "sndbuf", "rcvbuf", "socket-flags", "tcp-nodelay", "keepalive", "ping",
        "ping-restart", "ping-exit", "ping-timer-rem", "explicit-exit-notify",
        "inactive", "ifconfig", "ifconfig-ipv6", "ifconfig-nowarn", "topology",
        "route", "route-ipv6", "route-gateway", "route-metric", "route-delay",
        "redirect-gateway", "redirect-private", "route-nopull", "pull-filter",
        "dhcp-option", "block-ipv6", "verb", "mute", "mute-replay-warnings",
        "replay-window", "auth-gen-token", "push-peer-info",
    };
    std::string credential;
    bool connection = false;
    size_t offset = 0;
    while (offset < profile.size()) {
        size_t end = profile.find('\n', offset);
        if (end == std::string_view::npos) end = profile.size();
        auto line = profile.substr(offset, end - offset);
        offset = end + 1;
        auto first = line.find_first_not_of(" \t\r");
        if (first == std::string_view::npos) continue;
        line.remove_prefix(first);
        line = line.substr(0, line.find_last_not_of(" \t\r") + 1);
        if (!credential.empty()) {
            if (line == "</" + credential + ">") credential.clear();
            continue;
        }
        if (line.front() == '#' || line.front() == ';') continue;
        if (line == "<connection>") {
            if (connection) return false;
            connection = true;
            continue;
        }
        if (line == "</connection>") {
            if (!connection) return false;
            connection = false;
            continue;
        }
        bool inlineBlock = false;
        for (auto name : credentials) {
            if (line == "<" + std::string(name) + ">") {
                credential = name;
                inlineBlock = true;
                break;
            }
        }
        if (inlineBlock) continue;
        auto split = line.find_first_of(" \t");
        auto name = line.substr(0, split);
        if (name.substr(0, 2) == "--") name.remove_prefix(2);
        auto args = split == std::string_view::npos ? std::string_view {} : line.substr(split);
        auto argument = args.find_first_not_of(" \t");
        args = argument == std::string_view::npos ? std::string_view {} : args.substr(argument);
        bool allowed = false;
        for (auto item : options) allowed = allowed || name == item;
        // These data options otherwise select arbitrary file paths. Inline
        // certificate blocks need no matching explicit directive in OpenVPN.
        for (auto item : credentials) allowed = allowed || (name == item && args == "[inline]");
        if (!allowed || (name == "dev" && args != "tun") ||
            (name == "dev-type" && args != "tun")) return false;
    }
    return credential.empty() && !connection;
}
} // namespace OhosOpenvpn
