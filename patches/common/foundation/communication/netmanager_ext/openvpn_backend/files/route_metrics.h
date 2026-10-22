#pragma once
#include "negotiated_config.h"
#include <sstream>

namespace OhosOpenvpn {
// Private authenticated bridge -> netsys data only. No public parcel/IPC ABI.
struct RouteMetric { std::string destination; std::string gateway; unsigned metric = 0; };
inline bool operator==(const RouteMetric &a, const RouteMetric &b)
{ return a.destination == b.destination && a.gateway == b.gateway && a.metric == b.metric; }
inline std::string MetricWire(const NegotiatedConfig &config)
{
    std::string out;
    for (const auto &route : config.routes) {
        if (!route.metric) continue;
        out += route.destination.address + "/" + std::to_string(route.destination.prefix) + " " +
            route.gateway + " " + std::to_string(route.metric) + "\n";
    }
    return out;
}
inline bool ReadMetrics(const std::string &text, std::vector<RouteMetric> &out)
{
    if (text.size() > 96 * 1024) return false;
    std::istringstream input(text); std::string line;
    std::vector<RouteMetric> value;
    std::set<std::string> destinations;
    while (std::getline(input, line)) {
        std::istringstream fields(line); RouteMetric row; std::string metric, extra;
        if (!(fields >> row.destination >> row.gateway >> metric) || fields >> extra) return false;
        const int family = IpFamily(row.gateway); NetworkAddress address;
        if (!family || !Cidr(row.destination, family, address) ||
            !Number(metric, 0x7fffffff, row.metric) || !row.metric ||
            !destinations.insert(row.destination).second || value.size() >= 520) return false;
        value.push_back(std::move(row));
    }
    out = std::move(value); return true;
}
} // namespace OhosOpenvpn
