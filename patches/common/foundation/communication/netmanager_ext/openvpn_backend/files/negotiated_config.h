#pragma once
#include <algorithm>
#include <arpa/inet.h>
#include <cstdlib>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

namespace OhosOpenvpn {
struct NetworkAddress { std::string address; unsigned prefix = 0; int family = 0; };
struct NetworkRoute { NetworkAddress destination; std::string gateway; bool excluded = false; };
struct NegotiatedConfig {
    unsigned mtu = 0;
    std::vector<NetworkAddress> addresses;
    std::vector<NetworkRoute> routes;
    std::vector<std::string> dns;
    std::vector<std::string> domains;
};
using Environment = std::map<std::string, std::string>;
inline bool Number(const std::string &text, unsigned maximum, unsigned &value)
{
    if (text.empty()) return false;
    value = 0;
    for (char c : text) {
        const unsigned digit = static_cast<unsigned>(c - '0');
        if (c < '0' || c > '9' || digit > maximum || value > (maximum - digit) / 10) return false;
        value = value * 10 + digit;
    }
    return true;
}
inline int IpFamily(const std::string &text)
{
    in6_addr bytes {};
    if (inet_pton(AF_INET, text.c_str(), &bytes) == 1) return AF_INET;
    return inet_pton(AF_INET6, text.c_str(), &bytes) == 1 ? AF_INET6 : 0;
}
inline bool MaskPrefix(const std::string &mask, unsigned &prefix)
{
    in_addr address {};
    if (inet_pton(AF_INET, mask.c_str(), &address) != 1) return false;
    uint32_t bits = ntohl(address.s_addr); prefix = 0; bool zero = false;
    for (int bit = 31; bit >= 0; --bit) {
        if (bits & (uint32_t(1) << bit)) { if (zero) return false; ++prefix; }
        else zero = true;
    }
    return true;
}
inline bool Cidr(const std::string &text, int family, NetworkAddress &address)
{
    const auto slash = text.find('/');
    if (slash == std::string::npos || IpFamily(text.substr(0, slash)) != family ||
        !Number(text.substr(slash + 1), family == AF_INET ? 32 : 128, address.prefix)) return false;
    address.address = text.substr(0, slash); address.family = family;
    return true;
}
inline bool Domain(const std::string &text)
{
    if (text.empty() || text.size() > 253) return false;
    size_t label = 0;
    for (unsigned char c : text) {
        if (c == '.') { if (!label || label > 63) return false; label = 0; }
        else if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                 (c >= '0' && c <= '9') || c == '-' || c == '_') ++label;
        else return false;
    }
    return label <= 63 && (label || text.back() == '.');
}
inline bool AppendUnique(std::vector<std::string> &values, const std::string &value, size_t maximum)
{
    if (std::find(values.begin(), values.end(), value) != values.end()) return true;
    if (values.size() == maximum) return false;
    values.push_back(value); return true;
}
inline bool ReadNegotiated(const Environment &env, NegotiatedConfig &output)
{
    auto get = [&](const std::string &name) { auto it = env.find(name); return it == env.end() ? std::string {} : it->second; };
    NegotiatedConfig value;
    if (get("TUNTAP_DEV_TYPE") != "tun" || !Number(get("TUNTAP_MTU"), 65535, value.mtu) || value.mtu < 576) return false;
    bool ipv4 = false, ipv6 = false;
    if (!get("ifconfig_local").empty()) {
        NetworkAddress a {get("ifconfig_local"), 32, AF_INET};
        if (IpFamily(a.address) != AF_INET) return false;
        if (!get("ifconfig_netmask").empty()) {
            if (!MaskPrefix(get("ifconfig_netmask"), a.prefix)) return false;
        } else if (IpFamily(get("ifconfig_remote")) != AF_INET) return false;
        value.addresses.push_back(a); value.routes.push_back({a, "0.0.0.0", false}); ipv4 = true;
        if (!get("ifconfig_remote").empty() && IpFamily(get("ifconfig_remote")) != AF_INET) return false;
        if (!get("ifconfig_remote").empty())
            value.routes.push_back({{get("ifconfig_remote"), 32, AF_INET}, "0.0.0.0", false});
    } else if (!get("ifconfig_netmask").empty() || !get("ifconfig_remote").empty()) return false;
    if (!get("ifconfig_ipv6_local").empty()) {
        NetworkAddress a {get("ifconfig_ipv6_local"), 0, AF_INET6};
        if (IpFamily(a.address) != AF_INET6 || !Number(get("ifconfig_ipv6_netbits"), 128, a.prefix) ||
            (!get("ifconfig_ipv6_remote").empty() && IpFamily(get("ifconfig_ipv6_remote")) != AF_INET6) || value.mtu < 1280) return false;
        value.addresses.push_back(a); value.routes.push_back({a, "::", false}); ipv6 = true;
    } else if (!get("ifconfig_ipv6_netbits").empty() || !get("ifconfig_ipv6_remote").empty()) return false;
    if (!ipv4 && !ipv6) return false;

    std::set<unsigned> routes4, routes6, foreign, servers, search;
    // Bound every relevant exported index, including gaps. Undefined OpenVPN
    // routes leave holes; stopping at the first missing index loses real routes.
    for (const auto &item : env) {
        if (item.second.size() > 4096 || item.second.find('\0') != std::string::npos) return false;
        for (const auto &prefix : {"route_network_", "route_netmask_", "route_gateway_", "route_metric_",
             "route_ipv6_network_", "route_ipv6_gateway_", "route_ipv6_metric_", "foreign_option_", "dns_search_domain_"}) {
            const std::string name(prefix);
            if (item.first.compare(0, name.size(), name)) continue;
            unsigned index = 0;
            if (!Number(item.first.substr(name.size()), 256, index) || !index) return false;
            if (name == "foreign_option_") foreign.insert(index);
            else if (name == "dns_search_domain_") search.insert(index);
            else if (name.find("ipv6") != std::string::npos) routes6.insert(index);
            else routes4.insert(index);
        }
        if (item.first.compare(0, 11, "dns_server_") == 0) {
            auto split = item.first.find('_', 11); unsigned index = 0;
            if (split == std::string::npos || !Number(item.first.substr(11, split - 11), 16, index) || !index) return false;
            servers.insert(index);
        }
    }
    for (unsigned index : routes4) {
        const auto suffix = std::to_string(index); NetworkRoute route;
        route.destination = {get("route_network_" + suffix), 0, AF_INET};
        route.gateway = get("route_gateway_" + suffix);
        if (!ipv4 || IpFamily(route.destination.address) != AF_INET || IpFamily(route.gateway) != AF_INET ||
            !MaskPrefix(get("route_netmask_" + suffix), route.destination.prefix)) return false;
        if (!get("route_metric_" + suffix).empty() && get("route_metric_" + suffix) != "0") return false;
        route.excluded = !get("route_net_gateway").empty() && route.gateway == get("route_net_gateway");
        value.routes.push_back(route);
    }
    for (unsigned index : routes6) {
        const auto suffix = std::to_string(index); NetworkRoute route;
        if (!ipv6 || !Cidr(get("route_ipv6_network_" + suffix), AF_INET6, route.destination)) return false;
        route.gateway = get("route_ipv6_gateway_" + suffix);
        if (IpFamily(route.gateway) != AF_INET6) return false;
        if (!get("route_ipv6_metric_" + suffix).empty() && get("route_ipv6_metric_" + suffix) != "0") return false;
        value.routes.push_back(route);
    }
    for (const auto &entry : {std::make_pair("route_redirect_gateway_ipv4", AF_INET),
                              std::make_pair("route_redirect_gateway_ipv6", AF_INET6)}) {
        auto flag = get(entry.first);
        if (flag.empty() || flag == "0") continue;
        // block-local requires policy rules beyond a route; never drop that flag.
        if (flag != "1" || (entry.second == AF_INET ? !ipv4 : !ipv6)) return false;
        const std::string zero = entry.second == AF_INET ? "0.0.0.0" : "::";
        value.routes.push_back({{zero, 0, entry.second}, zero, false});
    }
    if (!servers.empty()) {
        // Structured final --dns state wins over legacy foreign_option values.
        for (unsigned index : servers) {
            const std::string prefix = "dns_server_" + std::to_string(index) + "_";
            for (const auto &item : env) {
                if (item.first.compare(0, prefix.size(), prefix)) continue;
                const auto field = item.first.substr(prefix.size());
                if (field == "transport") { if (item.second != "plain") return false; }
                else if (field == "dnssec") { if (item.second != "no") return false; }
                else if (field.compare(0, 5, "port_") == 0) {
                    unsigned addressIndex = 0;
                    if (!Number(field.substr(5), 8, addressIndex) || !addressIndex || item.second != "53" ||
                        !IpFamily(get(prefix + "address_" + std::to_string(addressIndex)))) return false;
                }
                else if (field.compare(0, 8, "address_") == 0) {
                    unsigned addressIndex = 0;
                    if (!Number(field.substr(8), 8, addressIndex) || !addressIndex || !IpFamily(item.second) ||
                        !AppendUnique(value.dns, item.second, 16)) return false;
                } else return false; // SNI/resolve-domain policies are not represented by OHOS DNS lists.
            }
        }
        if (value.dns.empty()) return false;
        for (unsigned index : search) {
            const auto domain = get("dns_search_domain_" + std::to_string(index));
            if (!Domain(domain) || !AppendUnique(value.domains, domain, 16)) return false;
        }
    } else {
        for (unsigned index : foreign) {
            std::istringstream input(get("foreign_option_" + std::to_string(index)));
            std::string command, option, text, extra;
            input >> command >> option;
            if (command != "dhcp-option") continue;
            if (option == "DNS" || option == "DNS6") {
                if (!(input >> text) || (input >> extra) || IpFamily(text) != (option == "DNS" ? AF_INET : AF_INET6) ||
                    !AppendUnique(value.dns, text, 16)) return false;
            } else if (option == "DOMAIN" || option == "DOMAIN-SEARCH" || option == "ADAPTER-DOMAIN-SUFFIX") {
                bool any = false;
                while (input >> text) { if (!Domain(text) || !AppendUnique(value.domains, text, 16)) return false; any = true; }
                if (!any) return false;
            }
        }
    }
    for (const auto &dns : value.dns) if ((IpFamily(dns) == AF_INET && !ipv4) || (IpFamily(dns) == AF_INET6 && !ipv6)) return false;
    output = std::move(value); return true;
}
inline std::string NetworkJson(const NegotiatedConfig &value)
{
    std::string json = "{\"config\":{\"mtu\":" + std::to_string(value.mtu) + ",\"addresses\":[";
    for (size_t i = 0; i < value.addresses.size(); ++i) {
        const auto &a = value.addresses[i]; if (i) json += ',';
        json += "{\"address\":\"" + a.address + "\",\"prefix\":" + std::to_string(a.prefix) + "}";
    }
    json += "],\"routes\":[";
    for (size_t i = 0; i < value.routes.size(); ++i) {
        const auto &r = value.routes[i]; if (i) json += ',';
        json += "{\"network\":\"" + r.destination.address + "\",\"prefix\":" + std::to_string(r.destination.prefix) +
            ",\"gateway\":\"" + r.gateway + "\",\"excluded\":" + (r.excluded ? "true" : "false") + "}";
    }
    json += "],\"dns\":[";
    for (size_t i = 0; i < value.dns.size(); ++i) { if (i) json += ','; json += '"' + value.dns[i] + '"'; }
    json += "],\"domains\":[";
    for (size_t i = 0; i < value.domains.size(); ++i) { if (i) json += ','; json += '"' + value.domains[i] + '"'; }
    return json + "]}}";
}
} // namespace OhosOpenvpn
