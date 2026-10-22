#pragma once
#include "negotiated_config.h"
#include <cctype>
#include <string_view>

namespace OhosOpenvpn {
struct DnsEndpoint { std::string address; unsigned port = 0; };
struct DnsPolicy {
    std::vector<DnsEndpoint> endpoints;
    std::vector<std::string> domains;
    std::string transport = "plain";
    std::string sni;
};
inline bool ReadDnsPolicies(const Environment &env, std::vector<DnsPolicy> &output)
{
    auto get = [&](const std::string &key) { auto it = env.find(key); return it == env.end() ? std::string {} : it->second; };
    std::set<unsigned> servers;
    for (const auto &item : env) {
        constexpr std::string_view begin = "dns_server_";
        if (item.first.compare(0, begin.size(), begin)) continue;
        const auto at = item.first.find('_', begin.size()); unsigned index = 0;
        if (at == std::string::npos || !Number(item.first.substr(begin.size(), at-begin.size()), 16, index) || !index) return false;
        servers.insert(index);
    }
    std::vector<DnsPolicy> policies;
    for (unsigned index : servers) {
        const std::string prefix = "dns_server_" + std::to_string(index) + "_";
        DnsPolicy policy;
        if (!get(prefix + "transport").empty() && get(prefix + "transport") != "unset") policy.transport = get(prefix + "transport");
        if (policy.transport != "plain" && policy.transport != "DoT" && policy.transport != "DoH") return false;
        const auto security = get(prefix + "dnssec");
        // This bridge does not claim a validating DNSSEC resolver. Never turn
        // a request for validation into an unauthenticated/plain fallback.
        if (!security.empty() && security != "unset" && security != "no") return false;
        policy.sni = get(prefix + "sni");
        if (!policy.sni.empty() && !Domain(policy.sni)) return false;
        std::set<unsigned> addresses, domains;
        for (const auto &item : env) {
            if (item.first.compare(0, prefix.size(), prefix)) continue;
            const auto field = item.first.substr(prefix.size()); unsigned n = 0;
            if (field == "transport" || field == "dnssec" || field == "sni") continue;
            if (field.compare(0,8,"address_") == 0) {
                if (!Number(field.substr(8),8,n) || !n || !IpFamily(item.second)) return false;
                addresses.insert(n);
            } else if (field.compare(0,5,"port_") == 0) {
                unsigned port = 0;
                if (!Number(field.substr(5),8,n) || !n || !Number(item.second,65535,port) || !port ||
                    !IpFamily(get(prefix + "address_" + std::to_string(n)))) return false;
            } else if (field.compare(0,15,"resolve_domain_") == 0) {
                if (!Number(field.substr(15),256,n) || !n || !Domain(item.second)) return false;
                domains.insert(n);
            } else return false;
        }
        for (unsigned n : addresses) {
            DnsEndpoint endpoint {get(prefix + "address_" + std::to_string(n)),
                policy.transport == "DoT" ? 853u : policy.transport == "DoH" ? 443u : 53u};
            const auto port = get(prefix + "port_" + std::to_string(n));
            if (!port.empty() && (!Number(port,65535,endpoint.port) || !endpoint.port)) return false;
            policy.endpoints.push_back(std::move(endpoint));
        }
        for (unsigned n : domains) {
            auto domain = get(prefix + "resolve_domain_" + std::to_string(n));
            std::transform(domain.begin(),domain.end(),domain.begin(),[](unsigned char c) { return std::tolower(c); });
            if (domain.back() == '.') domain.pop_back();
            policy.domains.push_back(std::move(domain));
        }
        if (policy.endpoints.empty()) return false;
        policies.push_back(std::move(policy));
    }
    output = std::move(policies); return true;
}
inline const DnsPolicy *ChooseDnsPolicy(const std::vector<DnsPolicy> &policies, const std::string &host)
{
    const DnsPolicy *best = nullptr; size_t longest = 0;
    // Stable priority follows OpenVPN's final exported, already merged list.
    for (const auto &policy : policies) {
        if (policy.domains.empty() && !best) best = &policy;
        for (const auto &domain : policy.domains) {
            const bool match = host == domain || (host.size() > domain.size() &&
                host.compare(host.size()-domain.size(),domain.size(),domain)==0 && host[host.size()-domain.size()-1]=='.');
            if (match && domain.size() > longest) { best=&policy; longest=domain.size(); }
        }
    }
    // Split-only configuration does not silently leak unmatched queries to a
    // matching-only server. The caller gets an actual DNS failure instead.
    return best;
}
} // namespace OhosOpenvpn
