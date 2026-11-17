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

#include "multi_vpn_manager.h"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/ioctl.h>
#include <thread>
#include <linux/ppp_defs.h>
#include <linux/if_ppp.h>
#include <linux/if_tun.h>
#include <linux/ipv6.h>
#include "init_socket.h"
#include "net_manager_constants.h"
#include "netmanager_base_common_utils.h"
#include "netnative_log_wrapper.h"
#include "securec.h"
#include "netlink_socket.h"
#include "route_manager.h"
#ifdef OHOS_QEMU_OPENVPN
#include "../../../../../netmanager_ext/qemu_openvpn/broker_protocol.h"
#endif

namespace OHOS {
namespace NetManagerStandard {

namespace {
constexpr uint32_t DEFAULT_MTU = 1500;
constexpr int32_t NET_MASK_MAX_LENGTH = 32;
constexpr int32_t MAX_UNIX_SOCKET_CLIENT = 5;
constexpr int32_t IPV6_MAX_LENGTH = 128;
} // namespace

int32_t MultiVpnManager::SendVpnInterfaceFdToClient(int32_t clientFd, int32_t tunFd)
{
    char buf[1] = {0};
    iovec iov;
    iov.iov_base = buf;
    iov.iov_len = sizeof(buf);
    union {
        cmsghdr align;
        char cmsg[CMSG_SPACE(sizeof(int32_t))];
    } cmsgu;
    if (memset_s(cmsgu.cmsg, sizeof(cmsgu.cmsg), 0, sizeof(cmsgu.cmsg)) != EOK) {
        NETNATIVE_LOGE("memset_s cmsgu.cmsg failed!");
        return NETMANAGER_ERROR;
    }
    msghdr message;
    if (memset_s(&message, sizeof(message), 0, sizeof(message)) != EOK) {
        NETNATIVE_LOGE("memset_s message failed!");
        return NETMANAGER_ERROR;
    }

    message.msg_iov = &iov;
    message.msg_iovlen = 1;
    message.msg_control = cmsgu.cmsg;
    message.msg_controllen = sizeof(cmsgu.cmsg);
    cmsghdr *cmsgh = CMSG_FIRSTHDR(&message);
    cmsgh->cmsg_len = CMSG_LEN(sizeof(tunFd));
    cmsgh->cmsg_level = SOL_SOCKET;
    cmsgh->cmsg_type = SCM_RIGHTS;
    if (memcpy_s(CMSG_DATA(cmsgh), sizeof(tunFd), &tunFd, sizeof(tunFd)) != EOK) {
        NETNATIVE_LOGE("memcpy_s cmsgu failed!");
        return NETMANAGER_ERROR;
    }
    if (sendmsg(clientFd, &message, 0) < 0) {
        NETNATIVE_LOGE("sendmsg error: %{public}d, clientfd[%{public}d], tunfd[%{public}d]", errno, clientFd, tunFd);
        return NETMANAGER_ERROR;
    }
    return NETMANAGER_SUCCESS;
}

int32_t MultiVpnManager::InitIfreq(ifreq &ifr, const std::string &ifName)
{
    if (memset_s(&ifr, sizeof(ifr), 0, sizeof(ifr)) != EOK) {
        NETNATIVE_LOGE("memset_s ifr failed!");
        return NETMANAGER_ERROR;
    }
    if (strncpy_s(ifr.ifr_name, IFNAMSIZ, ifName.c_str(), strlen(ifName.c_str())) != EOK) {
        NETNATIVE_LOGE("strcpy_s ifr name fail");
        return NETMANAGER_ERROR;
    }
    return NETMANAGER_SUCCESS;
}

int32_t MultiVpnManager::SetVpnResult(std::atomic_int &fd, unsigned long cmd, ifreq &ifr)
{
    if (fd > 0) {
        if (ioctl(fd, cmd, &ifr) < 0) {
            NETNATIVE_LOGE("set vpn error, errno:%{public}d", errno);
            return NETMANAGER_ERROR;
        }
    }
    return NETMANAGER_SUCCESS;
}

// LCOV_EXCL_START
int32_t MultiVpnManager::SetVpnMtu(const std::string &ifName, int32_t mtu)
{
    if (mtu <= 0) {
        NETNATIVE_LOGE("invalid mtu value");
        return NETMANAGER_ERROR;
    }

    ifreq ifr;
    if (InitIfreq(ifr, ifName) != NETMANAGER_SUCCESS) {
        return NETMANAGER_ERROR;
    }
    ifr.ifr_mtu = mtu;

    bool ipv4Success = false;
    bool ipv6Success = false;
    std::atomic_int net4Sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (net4Sock >= 0) {
        if (SetVpnResult(net4Sock, SIOCSIFMTU, ifr) == NETMANAGER_SUCCESS) {
            ipv4Success = true;
        } else {
            NETNATIVE_LOGE("set MTU failed for IPv4: %{public}d", errno);
        }
        close(net4Sock);
    } else {
        NETNATIVE_LOGE("create IPv4 socket failed: %{public}d", errno);
    }

    std::atomic_int net6Sock = socket(AF_INET6, SOCK_DGRAM, 0);
    if (net6Sock >= 0) {
        if (SetVpnResult(net6Sock, SIOCSIFMTU, ifr) == NETMANAGER_SUCCESS) {
            ipv6Success = true;
        } else {
            NETNATIVE_LOGE("set MTU failed for IPv6: %{public}d", errno);
        }
        close(net6Sock);
    } else {
        NETNATIVE_LOGE("create IPv6 socket failed: %{public}d", errno);
    }

    if (!ipv4Success || !ipv6Success) {
        NETNATIVE_LOGE("set MTU failed");
        return NETMANAGER_ERROR;
    }
    NETNATIVE_LOGE("set MTU success");
    return NETMANAGER_SUCCESS;
}
// LCOV_EXCL_STOP

int32_t MultiVpnManager::AddVpnRemoteAddress(const std::string &ifName, std::atomic_int &net4Sock, ifreq &ifr)
{
    /* ppp need set dst ip */
    if (strstr(ifName.c_str(), PPP_CARD_NAME) != NULL) {
        in_addr remoteIpv4Addr = {};
        if (inet_aton(remoteIpv4Addr_.c_str(), &remoteIpv4Addr) == 0) {
            NETNATIVE_LOGE("addr inet_aton error");
            return NETMANAGER_ERROR;
        }
        auto remoteAddr = reinterpret_cast<sockaddr_in *>(&ifr.ifr_dstaddr);
        remoteAddr->sin_family = AF_INET;
        remoteAddr->sin_addr = remoteIpv4Addr;
        if (ioctl(net4Sock, SIOCSIFDSTADDR, &ifr) < 0) {
            NETNATIVE_LOGE("ioctl set ipv4 address failed: %{public}d", errno);
            return NETMANAGER_ERROR;
        }
    }
    return NETMANAGER_SUCCESS;
}

int32_t MultiVpnManager::SetVpnAddress(const std::string &ifName, const std::string &vpnAddr, int32_t prefix)
{
    bool isIpv6 = CommonUtils::IsValidIPV6(vpnAddr);
    bool isIpv4 = CommonUtils::IsValidIPV4(vpnAddr);
    if (!isIpv4 && !isIpv6) {
        NETNATIVE_LOGE("invalid ip address format");
        return NETMANAGER_ERROR;
    }

    if (isIpv6) {
        return SetVpnAddressIPv6(ifName, vpnAddr, prefix);
    } else {
        return SetVpnAddressIPv4(ifName, vpnAddr, prefix);
    }
}

int32_t MultiVpnManager::SetVpnUp(const std::string &ifName, bool isIpv6)
{
    ifreq ifr = {};
    if (InitIfreq(ifr, ifName) != NETMANAGER_SUCCESS) {
        return NETMANAGER_ERROR;
    }
    ifr.ifr_flags = IFF_UP | IFF_NOARP;

    int32_t addressFamily = isIpv6 ? AF_INET6 : AF_INET;
    std::atomic_int sock = socket(addressFamily, SOCK_DGRAM, 0);
    if (sock < 0) {
        NETNATIVE_LOGE("create SOCK_DGRAM failed for %{public}s", isIpv6 ? "IPv6" : "IPv4");
        return NETMANAGER_ERROR;
    }

    int32_t ret = SetVpnResult(sock, SIOCSIFFLAGS, ifr);
    close(sock);
    if (ret == NETMANAGER_ERROR) {
        NETNATIVE_LOGE("set interface up failed for %{public}s", isIpv6 ? "IPv6" : "IPv4");
        return NETMANAGER_ERROR;
    }
    return NETMANAGER_SUCCESS;
}

// LCOV_EXCL_START
int32_t MultiVpnManager::SetVpnDown(const std::string &ifName)
{
    ifreq ifr = {};
    if (InitIfreq(ifr, ifName) != NETMANAGER_SUCCESS) {
        return NETMANAGER_ERROR;
    }
    ifr.ifr_flags &= ~IFF_UP;
    bool ipv4Success = false;
    bool ipv6Success = false;

    std::atomic_int net4Sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (net4Sock >= 0) {
        if (SetVpnResult(net4Sock, SIOCSIFFLAGS, ifr) == NETMANAGER_SUCCESS) {
            ipv4Success = true;
        } else {
            NETNATIVE_LOGE("set interface down failed for IPv4");
        }
        close(net4Sock);
    } else {
        NETNATIVE_LOGE("create IPv4 socket failed");
    }

    std::atomic_int net6Sock = socket(AF_INET6, SOCK_DGRAM, 0);
    if (net6Sock >= 0) {
        if (SetVpnResult(net6Sock, SIOCSIFFLAGS, ifr) == NETMANAGER_SUCCESS) {
            ipv6Success = true;
        } else {
            NETNATIVE_LOGE("set interface down failed for IPv6");
        }
        close(net6Sock);
    } else {
        NETNATIVE_LOGE("create IPv6 socket failed");
    }

    if (ipv4Success || ipv6Success) {
        return NETMANAGER_SUCCESS;
    }

    NETNATIVE_LOGE("set interface down failed for both IPv4 and IPv6");
    return NETMANAGER_ERROR;
}
// LCOV_EXCL_STOP

int32_t MultiVpnManager::CreateVpnInterface(const std::string &ifName)
{
    int32_t ret = NETMANAGER_SUCCESS;
    if (strstr(ifName.c_str(), XFRM_CARD_NAME) != NULL) {
        uint32_t ifNameId = CommonUtils::StrToUint(ifName.substr(strlen(XFRM_CARD_NAME)));
        ret = nmd::CreateVpnIfByNetlink(ifName.c_str(), ifNameId, phyName_.c_str(), DEFAULT_MTU);
    } else if (strstr(ifName.c_str(), PPP_CARD_NAME) != NULL) {
        ret = CreatePppInterface(ifName);
    } else if ((strstr(ifName.c_str(), MULTI_TUN_CARD_NAME) != NULL) ||
        (strstr(ifName.c_str(), INNER_CHL_NAME) != NULL)) {
        ret = CreateMultiTunInterface(ifName);
    } else {
        NETNATIVE_LOGE("CreateVpnInterface failed, invalid ifName");
        return NETMANAGER_ERROR;
    }
    return ret;
}

int32_t MultiVpnManager::DestroyVpnInterface(const std::string &ifName)
{
    NETNATIVE_LOGI("destroy vpn interface:%{public}s", ifName.c_str());
    bool isXfrm = strstr(ifName.c_str(), XFRM_CARD_NAME) != NULL;
    bool isPpp = strstr(ifName.c_str(), PPP_CARD_NAME) != NULL;
    bool isMultiTun = strstr(ifName.c_str(), MULTI_TUN_CARD_NAME) != NULL;
    bool isVic = strstr(ifName.c_str(), INNER_CHL_NAME) != NULL;
    if (!isXfrm && !isPpp && !isMultiTun && !isVic) {
        NETNATIVE_LOGE("DestroyVpnInterface failed, invalid ifName");
        return NETMANAGER_ERROR;
    }
    SetVpnDown(ifName);
    nmd::DeleteVpnIfByNetlink(ifName.c_str());
    if (isPpp || isMultiTun || isVic) {
        DestroyMultiVpnFd(ifName);
    }
    return NETMANAGER_SUCCESS;
}

int32_t MultiVpnManager::CreatePppInterface(const std::string &ifName)
{
    auto it = multiVpnFdMap_.find(ifName);
    if (it == multiVpnFdMap_.end()) {
        NETNATIVE_LOGE("ifName not exist");
        return NETMANAGER_ERROR;
    }
    ifreq ifr = {};
    if (memset_s(&ifr, sizeof(ifr), 0, sizeof(ifr)) != EOK) {
        NETNATIVE_LOGE("memset_s ifr failed!");
        return NETMANAGER_ERROR;
    }
    int32_t currentIfunit = 0;
    if (ioctl(multiVpnFdMap_[ifName], PPPIOCGUNIT, &currentIfunit) < 0) {
        NETNATIVE_LOGE("ioctl PPPIOCDISCONN failed errno: %{public}d", errno);
    }
    NETNATIVE_LOGI("Created PPP interface: currentIfunit:%{public}d\n", currentIfunit);
    std::string oldName = "ppp" + std::to_string(currentIfunit);
    SetVpnDown(oldName);
    if (strncpy_s(ifr.ifr_name, IFNAMSIZ, oldName.c_str(), strlen(oldName.c_str())) != EOK) {
        NETNATIVE_LOGE("strcpy_s ifr name fail");
        return NETMANAGER_ERROR;
    }
    ifr.ifr_name[IFNAMSIZ - 1] = '\0';
    if (strncpy_s(ifr.ifr_newname, IFNAMSIZ, ifName.c_str(), strlen(ifName.c_str())) != EOK) {
        NETNATIVE_LOGE("strcpy_s ifr name fail");
        return NETMANAGER_ERROR;
    }
    ifr.ifr_newname[IFNAMSIZ - 1] = '\0';
    std::atomic_int net4Sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (net4Sock < 0) {
        NETNATIVE_LOGE("create SOCK_DGRAM ipv4 failed: %{public}d", errno);
        return NETMANAGER_ERROR;
    }
    int32_t ioRet = ioctl(net4Sock, SIOCSIFNAME, &ifr);
    close(net4Sock);
    if (ioRet < 0) {
        NETNATIVE_LOGE("ioctl failed errno: %{public}d", errno);
        return NETMANAGER_ERROR;
    }
    NETNATIVE_LOGI("Created PPP interface");
    return NETMANAGER_SUCCESS;
}

void MultiVpnManager::CreatePppFd(const std::string &ifName)
{
    if (strstr(ifName.c_str(), PPP_CARD_NAME) == NULL) {
        NETNATIVE_LOGE("CreatePppFd failed");
        return;
    }
    multiVpnListeningName_ = ifName;
    StartMultiVpnInterfaceFdListen();
}

void MultiVpnManager::ClearPppFd(const std::string &connectName)
{
    if (strstr(connectName.c_str(), L2TP_NAME) == NULL ||
        connectName.substr(0, strlen(L2TP_NAME)) != L2TP_NAME) {
        NETNATIVE_LOGE("ClearPppFd failed, not valid l2tp connection");
        return;
    }
    std::string ifNameId = connectName.substr(strlen(L2TP_NAME));
    if (ifNameId.empty()) {
        NETNATIVE_LOGE("ClearPppFd failed, no ifNameId");
        return;
    }
    for (char c : ifNameId) {
        if (!std::isdigit(static_cast<unsigned char>(c))) {
            NETNATIVE_LOGE("ClearPppFd failed, invalid ifNameId");
            return;
        }
    }
    std::string ifName = PPP_CARD_NAME + ifNameId;
    DestroyMultiVpnFd(ifName);
}

int32_t MultiVpnManager::CreateMultiTunInterface(const std::string &ifName)
{
    int32_t multiVpnFd = 0;
    if (GetMultiVpnFd(ifName, multiVpnFd) != NETMANAGER_SUCCESS) {
        return NETMANAGER_ERROR;
    }

    ifreq ifr = {};
    if (InitIfreq(ifr, ifName) != NETMANAGER_SUCCESS) {
        return NETMANAGER_ERROR;
    }

    ifr.ifr_flags = IFF_TUN | IFF_NO_PI;
    if (ioctl(multiVpnFd, TUNSETIFF, &ifr) < 0) {
        NETNATIVE_LOGE("multi tun set iff error: %{public}d", errno);
        return NETMANAGER_ERROR;
    }
#ifdef OHOS_QEMU_OPENVPN
    {
        std::lock_guard<std::mutex> lock(mutex_);
        for (const auto &entry : qemuBindings_)
            if (entry.second.interfaceName == ifName) return NETMANAGER_SUCCESS;
    }
#endif
    multiVpnListeningName_ = ifName;
    StartMultiVpnInterfaceFdListen();
    return NETMANAGER_SUCCESS;
}

int32_t MultiVpnManager::GetMultiVpnFd(const std::string &ifName, int32_t &multiVpnFd)
{
    std::lock_guard<std::mutex> autoLock(mutex_);
    auto it = multiVpnFdMap_.find(ifName);
    if (it != multiVpnFdMap_.end()) {
        NETNATIVE_LOGE("ifName already exist");
        multiVpnFd = it->second.load();
        return NETMANAGER_SUCCESS;
    }
    if (strstr(ifName.c_str(), PPP_CARD_NAME) != NULL) {
        multiVpnFd = open(PPP_DEVICE_PATH, O_RDWR | O_NONBLOCK | O_CLOEXEC);
    } else if ((strstr(ifName.c_str(), MULTI_TUN_CARD_NAME) != NULL) ||
        (strstr(ifName.c_str(), INNER_CHL_NAME) != NULL)) {
        multiVpnFd = open(TUN_DEVICE_PATH, O_RDWR | O_NONBLOCK | O_CLOEXEC);
    } else {
        NETNATIVE_LOGE("GetMultiVpnFd faild, IfName err");
        return NETMANAGER_ERROR;
    }
    if (multiVpnFd <= 0) {
        NETNATIVE_LOGE("open virtual device failed: %{public}d", errno);
        return NETMANAGER_ERROR;
    }
    multiVpnFdMap_[ifName] = multiVpnFd;
    return NETMANAGER_SUCCESS;
}

void MultiVpnManager::SetVpnRemoteAddress(const std::string &remoteIp)
{
    remoteIpv4Addr_ = remoteIp;
}

int32_t MultiVpnManager::DestroyMultiVpnFd(const std::string &ifName)
{
    std::lock_guard<std::mutex> autoLock(mutex_);
    if (strstr(ifName.c_str(), PPP_CARD_NAME) == NULL &&
        strstr(ifName.c_str(), MULTI_TUN_CARD_NAME) == NULL &&
        strstr(ifName.c_str(), INNER_CHL_NAME) == NULL) {
        NETNATIVE_LOGE("DestroyMultiVpnFd faild, IfName err");
        return NETMANAGER_ERROR;
    }
    auto it = multiVpnFdMap_.find(ifName);
    if (it == multiVpnFdMap_.end()) {
        NETNATIVE_LOGE("ifName not exist");
        return NETMANAGER_ERROR;
    }
    auto multiVpnFd = it->second.load();
    if (multiVpnFd != 0) {
        close(multiVpnFd);
    }
    multiVpnFdMap_.erase(it);
    return NETMANAGER_SUCCESS;
}

void MultiVpnManager::StartMultiVpnInterfaceFdListen()
{
    if (multiVpnListeningFlag_) {
        NETNATIVE_LOGI("MultiVpnInterface fd is listening...");
        return;
    }
    NETNATIVE_LOGI("StartMultiVpnInterfaceFdListen...");
    multiVpnListeningFlag_ = true;
    std::thread t([sp = shared_from_this()]() { sp->StartMultiVpnSocketListen(); });
    t.detach();
    pthread_setname_np(t.native_handle(), "unix_socket_multivpnfd");
}

void MultiVpnManager::StartMultiVpnSocketListen()
{
    NETNATIVE_LOGI("StartMultiVpnSocketListen...");
    int32_t serverfd = GetControlSocket("multivpnfd");
    if (listen(serverfd, MAX_UNIX_SOCKET_CLIENT) < 0) {
        multiVpnListeningFlag_ = false;
        NETNATIVE_LOGE("listen socket error: %{public}d", errno);
        return;
    }

    sockaddr_in clientAddr;
    socklen_t len = sizeof(clientAddr);
    int32_t clientFd = accept(serverfd, reinterpret_cast<sockaddr *>(&clientAddr), &len);
    if (clientFd < 0) {
        NETNATIVE_LOGE("accept socket error: %{public}d", errno);
        multiVpnListeningFlag_ = false;
        return;
    }
    int32_t multiVpnFd = -1;
    if (GetMultiVpnFd(multiVpnListeningName_, multiVpnFd) == NETMANAGER_SUCCESS) {
        SendVpnInterfaceFdToClient(clientFd, multiVpnFd);
    }
    multiVpnListeningFlag_ = false;
    close(clientFd);
}

#ifdef OHOS_QEMU_OPENVPN
int32_t MultiVpnManager::BindQemuSession(const OhosOpenvpn::BrokerCommand &command, int32_t broker,
    const std::string &startTime, int32_t worker, const std::string &workerStart)
{
    if (!command.start || !OhosOpenvpn::BrokerIdentity(command) || broker <= 1 || startTime.empty() ||
        OhosOpenvpn::ProcessStart(broker) != startTime || worker <= 1 || workerStart.empty() ||
        OhosOpenvpn::ProcessStart(worker) != workerStart || OhosOpenvpn::Parent(worker) != broker ||
        !OhosOpenvpn::Executable(worker, "/system/bin/qemu_openvpn_service")) return NETMANAGER_ERROR;
    std::lock_guard<std::mutex> lock(mutex_);
    if (qemuBindings_.size() >= OhosOpenvpn::MAX_BROKER_SESSIONS || qemuBindings_.count(command.session.token)) return NETMANAGER_ERROR;
    for (const auto &entry : qemuBindings_)
        if (entry.second.interfaceName == command.interfaceName) return NETMANAGER_ERROR;
    if (!qemuListening_) {
        const int server = GetControlSocket("qemu_openvpn_tunfd");
        if (!OhosOpenvpn::InitBrokerListener(server, "/dev/unix/socket/qemu_openvpn_tunfd") ||
            listen(server, MAX_UNIX_SOCKET_CLIENT) != 0) return NETMANAGER_ERROR;
        std::thread worker([sp = shared_from_this(), server]() { sp->StartQemuSocketListen(server); });
        worker.detach();
        qemuListening_ = true;
    }
    qemuBindings_.emplace(command.session.token, QemuBinding {command.interfaceName, broker, startTime, worker, workerStart, OhosOpenvpn::StopIdentity(command)});
    return NETMANAGER_SUCCESS;
}

bool MultiVpnManager::QemuRecoveryReady(const OhosOpenvpn::BrokerCommand &command)
{
    std::lock_guard<std::mutex> lock(mutex_);
    const auto found = qemuBindings_.find(command.session.token);
    if (found == qemuBindings_.end() || found->second.stopIdentity != OhosOpenvpn::StopIdentity(command)) return false;
    const auto &binding = found->second;
    if (OhosOpenvpn::ProcessStart(binding.broker) == binding.brokerStartTime ||
        OhosOpenvpn::ProcessStart(binding.worker) == binding.workerStartTime) return false;
    // A killed broker cannot acknowledge its old jobs. Before starting a new
    // cleanup broker, prove the actual owned group is empty, not just PID gone.
    return kill(-binding.worker, 0) < 0 && errno == ESRCH;
}

bool MultiVpnManager::QemuCanStartBroker()
{
    std::lock_guard<std::mutex> lock(mutex_);
    for (const auto &item : qemuBindings_) {
        const auto &binding = item.second;
        if (OhosOpenvpn::ProcessStart(binding.broker) == binding.brokerStartTime) continue;
        if (OhosOpenvpn::ProcessStart(binding.worker) == binding.workerStartTime ||
            kill(-binding.worker, 0) == 0 || errno != ESRCH) return false;
    }
    return true;
}

bool MultiVpnManager::HasQemuSession(const std::string &generation)
{
    std::lock_guard<std::mutex> lock(mutex_);
    return qemuBindings_.find(generation) != qemuBindings_.end();
}

void MultiVpnManager::UnbindQemuSession(const std::string &generation)
{
    std::lock_guard<std::mutex> lock(mutex_);
    qemuBindings_.erase(generation);
}

void MultiVpnManager::StartQemuSocketListen(int32_t server)
{
    for (;;) {
        OhosOpenvpn::BrokerFd connection(accept4(server, nullptr, nullptr, SOCK_CLOEXEC | SOCK_NONBLOCK));
        if (connection.value < 0) { if (errno == EINTR) continue; poll(nullptr, 0, 100); continue; }
        pid_t bridge = -1;
        std::string bridgeStart;
        if (!OhosOpenvpn::BrokerPeer(connection.value, OhosOpenvpn::BROKER_UID,
            "/system/bin/qemu_openvpn_tun", bridge, &bridgeStart)) continue;
        std::string request;
        constexpr std::string_view prefix = "qemu-openvpn-tun-v2\n";
        if (!OhosOpenvpn::ReadFrame(connection.value, request) || request.size() != prefix.size() + 32 ||
            request.compare(0, prefix.size(), prefix) || !OhosOpenvpn::Token(std::string_view(request).substr(prefix.size()))) continue;
        std::lock_guard<std::mutex> lock(mutex_);
        const auto binding = qemuBindings_.find(request.substr(prefix.size()));
        if (binding == qemuBindings_.end()) continue;
        const auto &owner = binding->second;
        const pid_t client = OhosOpenvpn::Parent(bridge);
        const pid_t worker = OhosOpenvpn::Parent(client);
        const auto clientStart = OhosOpenvpn::ProcessStart(client);
        const auto workerStart = OhosOpenvpn::ProcessStart(worker);
        if (clientStart.empty() || workerStart.empty() || worker != owner.worker || workerStart != owner.workerStartTime ||
            !OhosOpenvpn::Executable(client, "/system/bin/qemu_openvpn") ||
            !OhosOpenvpn::Executable(worker, "/system/bin/qemu_openvpn_service") ||
            !OhosOpenvpn::Executable(owner.broker, "/system/bin/qemu_openvpn_service") ||
            OhosOpenvpn::Parent(worker) != owner.broker || OhosOpenvpn::ProcessStart(owner.broker) != owner.brokerStartTime ||
            OhosOpenvpn::ProcessStart(worker) != workerStart || OhosOpenvpn::ProcessStart(client) != clientStart ||
            OhosOpenvpn::ProcessStart(bridge) != bridgeStart) continue;
        const auto tun = multiVpnFdMap_.find(owner.interfaceName);
        if (tun == multiVpnFdMap_.end() || tun->second.load() < 0) continue;
        ifreq requestIf {};
        if (ioctl(tun->second.load(), TUNGETIFF, &requestIf) != 0 ||
            strnlen(requestIf.ifr_name, IFNAMSIZ) == IFNAMSIZ || owner.interfaceName != requestIf.ifr_name ||
            !(requestIf.ifr_flags & IFF_TUN) || !(requestIf.ifr_flags & IFF_NO_PI)) continue;
        SendVpnInterfaceFdToClient(connection.value, tun->second.load());
    }
}
#endif

void MultiVpnManager::SetXfrmPhyIfName(const std::string &phyName)
{
    phyName_ = phyName;
}

int32_t MultiVpnManager::SetVpnCallMode(const std::string &message)
{
    if (message.empty()) {
        NETNATIVE_LOGE("message is empty");
        return NETMANAGER_ERROR;
    }
    return nmd::RouteManager::SetVpnCallMode(message);
}

int32_t MultiVpnManager::SetVpnAddressIPv6(const std::string &ifName, const std::string &vpnAddr, int32_t prefix)
{
    if (prefix < 0 || prefix > IPV6_MAX_LENGTH) {
        NETNATIVE_LOGE("ipv6 prefix: %{public}d error", prefix);
        return NETMANAGER_ERROR;
    }

    std::atomic_int net6Sock = socket(AF_INET6, SOCK_DGRAM, 0);
    if (net6Sock < 0) {
        NETNATIVE_LOGE("create SOCK_DGRAM ipv6 failed: %{public}d", errno);
        return NETMANAGER_ERROR;
    }

    ifreq ifr = {};
    if (InitIfreq(ifr, ifName) != NETMANAGER_SUCCESS) {
        close(net6Sock);
        return NETMANAGER_ERROR;
    }

    int32_t ifindex = 0;
    if (ioctl(net6Sock, SIOCGIFINDEX, &ifr) < 0) {
        NETNATIVE_LOGE("get ifindex failed: %{public}d", errno);
        close(net6Sock);
        return NETMANAGER_ERROR;
    }
// LCOV_EXCL_START
    ifindex = ifr.ifr_ifindex;

    struct in6_ifreq ifr6 = {};
    ifr6.ifr6_prefixlen = static_cast<uint32_t>(prefix);
    ifr6.ifr6_ifindex = ifindex;

    if (inet_pton(AF_INET6, vpnAddr.c_str(), &ifr6.ifr6_addr) != 1) {
        NETNATIVE_LOGE("inet_pton ipv6 address failed");
        close(net6Sock);
        return NETMANAGER_ERROR;
    }

    if (ioctl(net6Sock, SIOCSIFADDR, &ifr6) < 0) {
        NETNATIVE_LOGE("ioctl set ipv6 address failed: %{public}d", errno);
        close(net6Sock);
        return NETMANAGER_ERROR;
    }

    int32_t ret = SetVpnUp(ifName, true);
    close(net6Sock);

    if (ret != NETMANAGER_SUCCESS) {
        NETNATIVE_LOGE("SetVpnUp failed after setting ipv6 address");
        return ret;
    }

    NETNATIVE_LOGI("set ipv6 address success");
    return NETMANAGER_SUCCESS;
}
// LCOV_EXCL_STOP

int32_t MultiVpnManager::SetVpnAddressIPv4(const std::string &ifName, const std::string &vpnAddr, int32_t prefix)
{
    if (prefix < 0 || prefix > NET_MASK_MAX_LENGTH) return NETMANAGER_ERROR;
    ifreq ifr = {};
    if (InitIfreq(ifr, ifName) != NETMANAGER_SUCCESS) {
        return NETMANAGER_ERROR;
    }
// LCOV_EXCL_START
    std::atomic_int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        NETNATIVE_LOGE("create SOCK_DGRAM ipv4 failed: %{public}d", errno);
        return NETMANAGER_ERROR;
    }

    in_addr ipv4Addr = {};
    if (inet_aton(vpnAddr.c_str(), &ipv4Addr) == 0) {
        NETNATIVE_LOGE("addr inet_aton error");
        close(sock);
        return NETMANAGER_ERROR;
    }

    auto sin = reinterpret_cast<sockaddr_in *>(&ifr.ifr_addr);
    sin->sin_family = AF_INET;
    sin->sin_addr = ipv4Addr;
    if (ioctl(sock, SIOCSIFADDR, &ifr) < 0) {
        NETNATIVE_LOGE("ioctl set ipv4 address failed: %{public}d", errno);
        close(sock);
        return NETMANAGER_ERROR;
    }

    if (AddVpnRemoteAddress(ifName, sock, ifr) != NETMANAGER_SUCCESS) {
        close(sock);
        return NETMANAGER_ERROR;
    }

    in_addr_t mask = prefix ? (0xffffffffu << (NET_MASK_MAX_LENGTH - prefix)) : 0;
    sin = reinterpret_cast<sockaddr_in *>(&ifr.ifr_netmask);
    sin->sin_family = AF_INET;
    sin->sin_addr.s_addr = htonl(mask);
    if (ioctl(sock, SIOCSIFNETMASK, &ifr) < 0) {
        NETNATIVE_LOGE("ioctl set ip mask failed: %{public}d", errno);
        close(sock);
        return NETMANAGER_ERROR;
    }

    int32_t ret = SetVpnUp(ifName, false);
    close(sock);

    if (ret != NETMANAGER_SUCCESS) {
        NETNATIVE_LOGE("SetVpnUp failed after setting ipv4 address");
        return ret;
    }

    NETNATIVE_LOGI("set ipv4 address success");
    return NETMANAGER_SUCCESS;
}
// LCOV_EXCL_STOP
} // namespace NetManagerStandard
} // namespace OHOS
