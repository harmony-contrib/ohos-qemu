/*
 * Copyright (c) 2025 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef MULTI_VPN_MANAGER_H
#define MULTI_VPN_MANAGER_H

#include <cstdint>
#include <linux/if.h>
#include <string>
#include <mutex>
#include <atomic>
#include <memory>
#include <unordered_map>

namespace OhosOpenvpn { struct BrokerCommand; }

namespace OHOS {
namespace NetManagerStandard {
constexpr const char *XFRM_CARD_NAME = "xfrm-vpn";
constexpr const char *PPP_CARD_NAME = "ppp-vpn";
constexpr const char *MULTI_TUN_CARD_NAME = "multitun-vpn";
constexpr const char *INNER_CHL_NAME = "inner-chl";
constexpr const char *PPP_DEVICE_PATH = "/dev/ppp";
constexpr const char *TUN_DEVICE_PATH = "/dev/tun";
constexpr const char *L2TP_NAME = "l2tp";

class MultiVpnManager : public std::enable_shared_from_this<MultiVpnManager> {
private:
    MultiVpnManager(const MultiVpnManager &) = delete;
    MultiVpnManager &operator=(const MultiVpnManager &) = delete;

public:
    MultiVpnManager() = default;
    ~MultiVpnManager() = default;
    static MultiVpnManager &GetInstance()
    {
        static std::shared_ptr<MultiVpnManager> instance = std::make_shared<MultiVpnManager>();
        return *instance;
    }

public:
    int32_t CreateVpnInterface(const std::string &ifName);
    int32_t DestroyVpnInterface(const std::string &ifName);
    int32_t SetVpnAddress(const std::string &ifName, const std::string &vpnAddr, int32_t prefix);
    int32_t SetVpnMtu(const std::string &ifName, int32_t mtu);
    int32_t SetVpnCallMode(const std::string &message);
    void CreatePppFd(const std::string &ifName);
    void SetXfrmPhyIfName(const std::string &phyName);
    void SetVpnRemoteAddress(const std::string &remoteIp);
    void ClearPppFd(const std::string &connectName);
    int32_t BindQemuSession(const OhosOpenvpn::BrokerCommand &command, int32_t broker, const std::string &startTime, int32_t worker, const std::string &workerStart);
    void UnbindQemuSession(const std::string &generation);
    bool HasQemuSession(const std::string &generation);
    bool QemuRecoveryReady(const OhosOpenvpn::BrokerCommand &command);
    bool QemuCanStartBroker();


private:
    int32_t SendVpnInterfaceFdToClient(int32_t clientFd, int32_t tunFd);
    int32_t SetVpnResult(std::atomic_int &fd, unsigned long cmd, ifreq &ifr);
    int32_t InitIfreq(ifreq &ifr, const std::string &ifName);
    int32_t SetVpnDown(const std::string &ifName);
    int32_t SetVpnUp(const std::string &ifName, bool isIpv6);
    int32_t AddVpnRemoteAddress(const std::string &ifName, std::atomic_int &net4Sock, ifreq &ifr);
    int32_t CreatePppInterface(const std::string &ifName);
    int32_t GetMultiVpnFd(const std::string &ifName, int32_t &multiVpnFd);
    int32_t DestroyMultiVpnFd(const std::string &ifName);
    int32_t CreateMultiTunInterface(const std::string &ifName);
    int32_t SetVpnAddressIPv6(const std::string &ifName, const std::string &vpnAddr, int32_t prefix);
    int32_t SetVpnAddressIPv4(const std::string &ifName, const std::string &vpnAddr, int32_t prefix);
    void StartMultiVpnSocketListen();
    void StartMultiVpnInterfaceFdListen();

private:
    struct QemuBinding {
        std::string interfaceName;
        int32_t broker;
        std::string brokerStartTime;
        int32_t worker;
        std::string workerStartTime;
        std::string stopIdentity;
    };
    std::unordered_map<std::string, QemuBinding> qemuBindings_;
    bool qemuListening_ = false;
    void StartQemuSocketListen(int32_t server);
    std::atomic_bool multiVpnListeningFlag_ = false;
    std::unordered_map<std::string, std::atomic_int> multiVpnFdMap_;
    std::string phyName_;
    std::string multiVpnListeningName_;
    std::string remoteIpv4Addr_;
    std::mutex mutex_;
};
} // namespace NetManagerStandard
} // namespace OHOS
#endif // MULTI_VPN_MANAGER_H
