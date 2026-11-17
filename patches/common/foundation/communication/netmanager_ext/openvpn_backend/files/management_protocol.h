// Candidate only. Field layout is bound to the pinned OpenVPN log_entry_print.
#pragma once
#include <array>
#include <arpa/inet.h>
#include <cstdint>
#include <string>
#include <string_view>

namespace OhosOpenvpn {
enum class Event { Ignore, Connected, Reconnecting, Disconnected, Failure, Malformed };

inline bool Unsigned(std::string_view text, uint32_t maximum, bool zero = true)
{
    if (text.empty()) return false;
    uint32_t value = 0;
    for (char c : text) {
        if (c < '0' || c > '9' || value > (maximum - static_cast<unsigned>(c - '0')) / 10)
            return false;
        value = value * 10 + static_cast<unsigned>(c - '0');
    }
    return zero || value != 0;
}

inline bool Address(std::string_view text, int family, bool scope = false)
{
    auto percent = text.find('%');
    if (percent != std::string_view::npos) {
        if (!scope || family != AF_INET6 || !Unsigned(text.substr(percent + 1), UINT32_MAX, false))
            return false;
        text = text.substr(0, percent);
    }
    in6_addr result {};
    return !text.empty() && inet_pton(family, std::string(text).c_str(), &result) == 1;
}

inline bool Transport(std::string_view address, std::string_view port)
{
    return (Address(address, AF_INET) || Address(address, AF_INET6, true)) &&
           Unsigned(port, 65535, false);
}

inline Event ParseState(std::string_view line)
{
    if (line.size() > 4096 || line.find('\0') != std::string_view::npos) return Event::Malformed;
    if (line.size() >= 2 && line.substr(line.size() - 2) == "\r\n") line.remove_suffix(2);
    if (line.find_first_of("\r\n") != std::string_view::npos) return Event::Malformed;
    if (line.substr(0, 7) == ">FATAL:") return Event::Failure;
    constexpr std::string_view prefix = ">STATE:";
    if (line.substr(0, prefix.size()) != prefix) return Event::Ignore;
    line.remove_prefix(prefix.size());
    auto first = line.find(',');
    if (first == std::string_view::npos || !Unsigned(line.substr(0, first), UINT32_MAX))
        return Event::Malformed;
    auto second = line.find(',', first + 1);
    if (second == std::string_view::npos) return Event::Malformed;
    auto state = line.substr(first + 1, second - first - 1);
    if (state == "EXITING") return Event::Disconnected;
    if (state == "RECONNECTING") return Event::Reconnecting;
    for (auto pending : {"CONNECTING", "WAIT", "AUTH", "GET_CONFIG", "ASSIGN_IP",
                         "ADD_ROUTES", "RESOLVE", "TCP_CONNECT", "AUTH_PENDING"})
        if (state == pending) return Event::Ignore;
    if (state != "CONNECTED") return Event::Malformed;

    std::array<std::string_view, 9> fields {};
    size_t count = 0;
    while (true) {
        if (count == fields.size()) return Event::Malformed;
        auto split = line.find(',');
        fields[count++] = line.substr(0, split);
        if (split == std::string_view::npos) break;
        line.remove_prefix(split + 1);
    }
    if (count < 3 || fields[2] != "SUCCESS") return Event::Failure;
    // The formatter emits eight fields for IPv4, adding field nine only for
    // a defined tunnel IPv6 address. It does not emit a trailing empty field.
    if (count != 8 && count != 9) return Event::Malformed;
    if ((!fields[3].empty() && !Address(fields[3], AF_INET)) ||
        (count == 9 && !Address(fields[8], AF_INET6)) ||
        (fields[3].empty() && count != 9) ||
        !Transport(fields[4], fields[5]) || !Transport(fields[6], fields[7]))
        return Event::Malformed;
    return Event::Connected;
}
}
