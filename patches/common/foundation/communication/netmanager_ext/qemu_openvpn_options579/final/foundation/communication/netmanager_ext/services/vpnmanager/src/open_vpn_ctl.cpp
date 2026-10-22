/*
 * Copyright (c) 2024 Huawei Device Co., Ltd.
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

#include "open_vpn_ctl.h"

#include <fstream>
#include <array>
#include <cerrno>
#include <unistd.h>
#include <cmath>
#include <sys/random.h>
#include "../../../qemu_openvpn/session_contract.h"
#include "../../../qemu_openvpn/broker_protocol.h"
#include "multi_vpn_helper.h"
#include "../../../qemu_openvpn/negotiated_config.h"
#include "../../../qemu_openvpn/profile_policy.h"

#include "base64_utils.h"
#include "netmanager_base_common_utils.h"
#include "netmgr_ext_log_wrapper.h"

namespace OHOS {
namespace NetManagerStandard {

OpenvpnCtl::OpenvpnCtl(sptr<VpnConfig> config, const std::string &pkg, int32_t userId,
    std::vector<int32_t> &activeUserIds) : NetVpnImpl(config, pkg, userId, activeUserIds)
{
}

int32_t OpenvpnCtl::SetUp(bool isInternalChannel)
{
    UpdateOpenvpnState(OPENVPN_STATE_SETUP);
    return StartOpenvpn();
}

int32_t OpenvpnCtl::StartOpenvpn()
{
    if (openvpnConfig_ == nullptr) {
        NETMGR_EXT_LOG_E("StartOpenvpn openvpnConfig_ is null");
        UpdateOpenvpnState(OPENVPN_STATE_DISCONNECTED);
        return NETMANAGER_EXT_ERR_INTERNAL;
    }
    if (!std::filesystem::exists(VPN_PIDDIR) || !std::filesystem::is_directory(VPN_PIDDIR)) {
        NETMGR_EXT_LOG_E("StartOpenvpn config dir check error.");
        UpdateOpenvpnState(OPENVPN_STATE_DISCONNECTED);
        return NETMANAGER_EXT_ERR_INTERNAL;
    }
    if (!InitQemuSession()) {
        UpdateOpenvpnState(OPENVPN_STATE_DISCONNECTED);
        return NETMANAGER_EXT_ERR_INTERNAL;
    }
    const std::string request = HasQemuSession() ? QemuBrokerMessage(true) : std::string {};
    if (HasQemuSession() && request.empty()) return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
    int32_t result = NetsysController::GetInstance().ProcessVpnStage(SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART, request);
    if (result != NETMANAGER_EXT_SUCCESS) {
        NETMGR_EXT_LOG_E("StartOpenvpn backend request failed: %{public}d", result);
        UpdateOpenvpnState(OPENVPN_STATE_DISCONNECTED);
        return NETMANAGER_EXT_ERR_INTERNAL;
    }
    // A successful request is still asynchronous. CONNECTED comes only from
    // the authenticated backend after TLS negotiation and real TUN setup.
    UpdateOpenvpnState(OPENVPN_STATE_STARTED);
    return NETMANAGER_EXT_SUCCESS;
}

int32_t OpenvpnCtl::NotifyConnectStage(const std::string &stage, const int32_t &result)
{
    // Native QEMU sessions only accept generation- and process-bound events.
    if (HasQemuSession()) return NETMANAGER_EXT_ERR_NOT_SYSTEM_CALL;
    if (stage.empty()) {
        NETMGR_EXT_LOG_E("stage is empty");
        return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
    }
    if (result != NETMANAGER_EXT_SUCCESS) {
        NETMGR_EXT_LOG_E("vpn stage failed, result: %{public}d", result);
        return NETMANAGER_EXT_ERR_INTERNAL;
    }
    return HandleClientMessage(stage);
}

int32_t OpenvpnCtl::SetUpVpnTun()
{
    if (multiVpnInfo_ != nullptr) {
        int32_t modeResult = NetsysController::GetInstance().ProcessVpnStage(SysVpnStageCode::VPN_STAGE_SET_VPN_CALL_MODE,
            multiVpnInfo_->isVpnExtCall ? "0" : "1");
        if (modeResult != NETMANAGER_EXT_SUCCESS) return NETMANAGER_EXT_ERR_INTERNAL;
    }
    int result = NetVpnImpl::SetUp();
    if (result != NETMANAGER_EXT_SUCCESS) {
        NETMGR_EXT_LOG_W("openvpn SetUp failed");
        StopOpenvpn();
        UpdateOpenvpnState(OPENVPN_STATE_DISCONNECTED);
    }
    NETMGR_EXT_LOG_I("openvpn SetUp %{public}d", result);
    return result;
}

int32_t OpenvpnCtl::HandleClientMessage(const std::string &msg)
{
    int result = NETMANAGER_EXT_SUCCESS;
    if (msg.empty()) {
        NETMGR_EXT_LOG_E("msg is empty");
        return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
    }
    NETMGR_EXT_LOG_I("Process Request  message:  %{public}s", MaskOpenvpnMessage(msg).c_str());
    if (strstr(msg.c_str(), OPENVPN_NODE_ROOT) != 0) {
        const char *ret = strstr(msg.c_str(), "{");
        if (ret == nullptr) {
            NETMGR_EXT_LOG_E("client message format error");
            return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
        }
        cJSON* message = cJSON_Parse(ret);
        if (message == nullptr) {
            NETMGR_EXT_LOG_E("not json string");
            return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
        }
        // is config message
        cJSON* config = cJSON_GetObjectItem(message, OPENVPN_NODE_CONFIG);
        if (config != nullptr && cJSON_IsObject(config)) {
            UpdateConfig(config);
        }
        // is state message
        cJSON* state = cJSON_GetObjectItem(message, OPENVPN_NODE_UPDATE_STATE);
        if (state != nullptr && cJSON_IsObject(state)) {
            UpdateState(state);
        }
        // is setup message
        cJSON* vpnSetUp = cJSON_GetObjectItem(message, OPENVPN_NODE_SETUP_VPN_TUN);
        if (vpnSetUp != nullptr && cJSON_IsObject(vpnSetUp)) {
            result = SetUpVpnTun();
        }
        cJSON_Delete(message);
    }
    return result;
}

void OpenvpnCtl::UpdateState(cJSON* state)
{
    cJSON* updateState = cJSON_GetObjectItem(state, OPENVPN_NODE_STATE);
    if (updateState != nullptr && cJSON_IsNumber(updateState)) {
        int32_t openVpnState = static_cast<int32_t>(cJSON_GetNumberValue(updateState));
        UpdateOpenvpnState(openVpnState);
        if (openVpnState == OPENVPN_STATE_DISCONNECTED || openVpnState >= OPENVPN_STATE_ERROR_PRIVATE_KEY) {
            NETMGR_EXT_LOG_I("UpdatesState:  %{public}d", openVpnState);
            if (multiVpnInfo_ != nullptr) {
                VpnHisysEvent::SetFaultVpnEvent(multiVpnInfo_->userId, multiVpnInfo_->bundleName,
                    VpnOperatorType::OPERATION_SETUP_VPN,
                    VpnOperatorErrorType::ERROR_CFG_INCORRECT, VpnType::OPENVPN);
            }
            StopOpenvpn();
        }
    }
}

void OpenvpnCtl::UpdateConfig(cJSON *jConfig)
{
    if (vpnConfig_ == nullptr) {
        NETMGR_EXT_LOG_E("UpdateConfig vpnConfig_ is null");
        return;
    }
    cJSON *mtu = cJSON_GetObjectItem(jConfig, OPENVPN_NODE_MTU);
    if (mtu != nullptr && cJSON_IsNumber(mtu)) {
        int32_t openVpnMtu = static_cast<int32_t>(cJSON_GetNumberValue(mtu));
        vpnConfig_->mtu_ = openVpnMtu;
        NETMGR_EXT_LOG_I("UpdateConfig mtu %{public}d", openVpnMtu);
    }
    INetAddr iNetAddr;
    INetAddr destination;
    INetAddr gateway;
    Route iRoute;
    cJSON *address = cJSON_GetObjectItem(jConfig, OPENVPN_NODE_ADDRESS);
    if (address != nullptr && cJSON_IsString(address)) {
        std::string openVpnAddress = cJSON_GetStringValue(address);
        iNetAddr.address_ = openVpnAddress;
        gateway.address_ = openVpnAddress;
        destination.address_ = openVpnAddress;
    }
    cJSON *netmask = cJSON_GetObjectItem(jConfig, OPENVPN_NODE_NETMASK);
    if (netmask != nullptr && cJSON_IsString(netmask)) {
        std::string openVpnNetmask = cJSON_GetStringValue(netmask);
        iNetAddr.netMask_ = openVpnNetmask;
        destination.prefixlen_ = CommonUtils::GetMaskLength(openVpnNetmask);
        NETMGR_EXT_LOG_I("UpdateConfig prefixlen %{public}d", destination.prefixlen_);
    }
    vpnConfig_->addresses_.emplace_back(iNetAddr);
    if (openvpnConfig_ != nullptr && openvpnConfig_->localAddresses_.empty()) {
        openvpnConfig_->localAddresses_.emplace_back(iNetAddr);
    }

    iRoute.iface_ = GetInterfaceName();
    iRoute.isDefaultRoute_ = true;
    iRoute.destination_ = destination;
    iRoute.gateway_ = gateway;
    vpnConfig_->routes_.emplace_back(iRoute);

    ProcessDnsConfig(jConfig);
}

int32_t OpenvpnCtl::ProcessDnsConfig(cJSON* jConfig)
{
    if (vpnConfig_ == nullptr) {
        NETMGR_EXT_LOG_E("ProcessDnsConfig vpnConfig_ is null");
        return NETMANAGER_EXT_ERR_INTERNAL;
    }

    for (auto it = vpnConfig_->dnsAddresses_.begin(); it != vpnConfig_->dnsAddresses_.end();) {
        if (it->empty()) {
            it = vpnConfig_->dnsAddresses_.erase(it);
        } else {
            ++it;
        }
    }
    cJSON *primaryObj = cJSON_GetObjectItem(jConfig, PRIMARY_DNS);
    if (primaryObj != nullptr && cJSON_IsString(primaryObj)) {
        std::string dnsPrimary = cJSON_GetStringValue(primaryObj);
        if (!dnsPrimary.empty()) {
            vpnConfig_->dnsAddresses_.emplace_back(dnsPrimary);
        }
    }

    cJSON *secondaryObj = cJSON_GetObjectItem(jConfig, SECONDARY_DNS);
    if (secondaryObj != nullptr && cJSON_IsString(secondaryObj)) {
        std::string dnsSecondary = cJSON_GetStringValue(secondaryObj);
        if (!dnsSecondary.empty()) {
            vpnConfig_->dnsAddresses_.emplace_back(dnsSecondary);
        }
    }
    return NETMANAGER_EXT_SUCCESS;
}

void OpenvpnCtl::UpdateOpenvpnState(const int32_t state)
{
    openvpnState_ = state;
    switch (state) {
        case OPENVPN_STATE_CONNECTED:
            NotifyConnectState(VpnConnectState::VPN_CONNECTED);
            break;
        case OPENVPN_STATE_DISCONNECTED:
        case OPENVPN_STATE_ERROR_PRIVATE_KEY:
        case OPENVPN_STATE_ERROR_CLIENT_CRT:
        case OPENVPN_STATE_ERROR_CA_CAT:
        case OPENVPN_STATE_ERROR_TIME_OUT:
            NotifyConnectState(VpnConnectState::VPN_DISCONNECTED);
            break;
        default:
            NETMGR_EXT_LOG_E("unknown openvpn state: %{public}d", state);
            break;
    }
}

int32_t OpenvpnCtl::GetSysVpnCertUri(const int32_t certType, std::string &certUri)
{
    if (openvpnConfig_ == nullptr) {
        NETMGR_EXT_LOG_E("StartOpenvpn openvpnConfig_ is null");
        return NETMANAGER_EXT_ERR_INTERNAL;
    }
    switch (certType) {
        case OpenVpnConfigType::OPENVPN_ASKPASS:
            certUri = openvpnConfig_->askpass_;
            break;
        case OpenVpnConfigType::OPENVPN_CONF:
            certUri = Base64::Decode(openvpnConfig_->ovpnConfig_);
            if (!certUri.empty() && !openvpnConfig_->askpass_.empty()) {
                certUri.append(OPENVPN_ASKPASS_PARAM);
            }
            break;
        default:
            NETMGR_EXT_LOG_E("unknown openvpn config type: %{public}d", certType);
            break;
    }
    return NETMANAGER_EXT_SUCCESS;
}

int32_t OpenvpnCtl::GetVpnCertData(const int32_t certType, std::vector<int8_t> &certData)
{
    return NETMANAGER_EXT_SUCCESS;
}

bool OpenvpnCtl::IsSystemVpn()
{
    return true;
}

sptr<SysVpnConfig> OpenvpnCtl::GetSysVpnConfig()
{
    return openvpnConfig_;
}

int32_t OpenvpnCtl::Destroy()
{
    const bool nativeSession = HasQemuSession();
    int32_t stopResult = StopOpenvpn();
    int32_t modeResult = NETMANAGER_EXT_SUCCESS;
    if (multiVpnInfo_ != nullptr) {
        modeResult = NetsysController::GetInstance().ProcessVpnStage(SysVpnStageCode::VPN_STAGE_SET_VPN_CALL_MODE,
            multiVpnInfo_->isVpnExtCall ? "0" : "1");
    }
    int result = !nativeSession || qemuNeedsCleanup_ ? NetVpnImpl::Destroy() : NETMANAGER_EXT_SUCCESS;
    if (result == NETMANAGER_EXT_SUCCESS) qemuNeedsCleanup_ = false;
    qemuConfigured_ = qemuTunReady_ = false;
    UpdateOpenvpnState(OPENVPN_STATE_DISCONNECTED);
    NETMGR_EXT_LOG_I("openvpn Destroy result %{public}d}", result);
    if (nativeSession && result == NETMANAGER_EXT_SUCCESS && stopResult == NETMANAGER_EXT_SUCCESS && modeResult == NETMANAGER_EXT_SUCCESS) {
        qemuGeneration_.clear(); qemuWorkerStart_.clear(); qemuSupervisor_ = -1;
        qemuBrokerStart_.clear(); qemuBroker_ = -1;
        if (multiVpnInfo_ != nullptr) MultiVpnHelper::GetInstance().DelMultiVpnInfo(multiVpnInfo_);
    }
    return result != NETMANAGER_EXT_SUCCESS ? result :
        (stopResult != NETMANAGER_EXT_SUCCESS ? stopResult : modeResult);
}

int32_t OpenvpnCtl::StopOpenvpn()
{
    if (HasQemuSession()) qemuStoppingRequested_ = true;
    if (HasQemuSession() && qemuWorkerStopped_) return NETMANAGER_EXT_SUCCESS;
    const std::string request = HasQemuSession() ? QemuBrokerMessage(false) : std::string {};
    if (HasQemuSession() && request.empty()) return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
    int32_t result = NetsysController::GetInstance().ProcessVpnStage(SysVpnStageCode::VPN_STAGE_OPENVPN_STOP, request);
    if (result != NETMANAGER_EXT_SUCCESS) {
        NETMGR_EXT_LOG_E("StopOpenvpn backend request failed: %{public}d", result);
        return NETMANAGER_EXT_ERR_INTERNAL;
    }
    qemuWorkerStopped_ = HasQemuSession();
    qemuWorkerStart_.clear();
    qemuSupervisor_ = -1;
    qemuConfigured_ = qemuTunReady_ = false;
    UpdateOpenvpnState(OPENVPN_STATE_DISCONNECTED);
    return NETMANAGER_EXT_SUCCESS;
}

bool OpenvpnCtl::IsOpenvpnConnected() const
{
    if (openvpnState_ != OPENVPN_STATE_CONNECTED) return false;
    if (!HasQemuSession()) return true;
    return !qemuWorkerStopped_ && qemuSupervisor_ > 1 && !qemuWorkerStart_.empty() &&
        OhosOpenvpn::ProcessStart(qemuSupervisor_) == qemuWorkerStart_ && qemuBroker_ > 1 &&
        !qemuBrokerStart_.empty() && OhosOpenvpn::ProcessStart(qemuBroker_) == qemuBrokerStart_;
}

bool OpenvpnCtl::QemuNeedsRecovery() const
{
    if (!HasQemuSession()) return false;
    if (qemuStoppingRequested_ || qemuWorkerStopped_) return true;
    if (qemuSupervisor_ <= 1) return std::chrono::steady_clock::now() >= qemuClaimDeadline_;
    return qemuWorkerStart_.empty() || OhosOpenvpn::ProcessStart(qemuSupervisor_) != qemuWorkerStart_ ||
        qemuBroker_ <= 1 || qemuBrokerStart_.empty() || OhosOpenvpn::ProcessStart(qemuBroker_) != qemuBrokerStart_;
}

int32_t OpenvpnCtl::GetConnectedSysVpnConfig(sptr<SysVpnConfig> &sysVpnConfig)
{
    sysVpnConfig = nullptr;
    if (IsOpenvpnConnected() && openvpnConfig_ != nullptr) {
        sysVpnConfig = openvpnConfig_;
    }
    return NETMANAGER_EXT_SUCCESS;
}

bool OpenvpnCtl::IsInternalVpn()
{
    return true;
}

namespace {
bool QemuInteger(cJSON *item, unsigned maximum, unsigned &result)
{
    if (!cJSON_IsNumber(item)) return false;
    double value = cJSON_GetNumberValue(item);
    if (!std::isfinite(value) || value < 0 || value > maximum || std::floor(value) != value) return false;
    result = static_cast<unsigned>(value); return true;
}
bool QemuString(cJSON *item, std::string &result)
{
    if (!cJSON_IsString(item) || !cJSON_GetStringValue(item)) return false;
    result = cJSON_GetStringValue(item); return result.size() <= 4096;
}
bool QemuAddress(cJSON *object, const char *key, INetAddr &address)
{
    std::string text; unsigned prefix = 0;
    if (!QemuString(cJSON_GetObjectItemCaseSensitive(object, key), text)) return false;
    const int family = OhosOpenvpn::IpFamily(text);
    if (!family || !QemuInteger(cJSON_GetObjectItemCaseSensitive(object, "prefix"), family == AF_INET ? 32 : 128, prefix)) return false;
    address.address_ = text;
    address.type_ = address.family_ = family == AF_INET ? INetAddr::IPV4 : INetAddr::IPV6;
    address.prefixlen_ = prefix;
    if (family == AF_INET) {
        in_addr mask {}; mask.s_addr = htonl(prefix ? 0xffffffffu << (32 - prefix) : 0);
        char textMask[INET_ADDRSTRLEN] {};
        if (!inet_ntop(AF_INET, &mask, textMask, sizeof(textMask))) return false;
        address.netMask_ = textMask;
    }
    return true;
}
}

bool OpenvpnCtl::InitQemuSession()
{
    qemuWorkerStart_.clear();
    qemuGeneration_.clear(); qemuSupervisor_ = -1;
    qemuWorkerStopped_ = qemuNeedsCleanup_ = qemuStoppingRequested_ = false;
    qemuBroker_ = -1; qemuBrokerStart_.clear();
    qemuClaimDeadline_ = std::chrono::steady_clock::now() + std::chrono::seconds(10);
    qemuConfigured_ = qemuTunReady_ = false; qemuLastConfig_.clear();
    if (access("/system/bin/qemu_openvpn_service", X_OK) != 0) return true;
    std::array<unsigned char, 16> random {};
    size_t offset = 0;
    while (offset < random.size()) {
        ssize_t count = getrandom(random.data() + offset, random.size() - offset, 0);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) return false;
        offset += static_cast<size_t>(count);
    }
    constexpr char hex[] = "0123456789abcdef";
    for (unsigned char byte : random) { qemuGeneration_ += hex[byte >> 4]; qemuGeneration_ += hex[byte & 15]; }
    return true;
}

std::string OpenvpnCtl::QemuBrokerMessage(bool start) const
{
    if (!multiVpnInfo_ || !openvpnConfig_) return {};
    OhosOpenvpn::BrokerCommand command;
    command.start = start;
    command.owner = {multiVpnInfo_->callingUid, multiVpnInfo_->userId, multiVpnInfo_->bundleName, multiVpnInfo_->vpnId};
    command.interfaceName = multiVpnInfo_->ifName;
    command.session.token = qemuGeneration_;
    if (start) {
        command.session.profile = Base64::Decode(openvpnConfig_->ovpnConfig_);
        command.session.password = openvpnConfig_->askpass_;
    }
    return OhosOpenvpn::EncodeBroker(command);
}

int32_t OpenvpnCtl::GetQemuSession(std::string &snapshot, int32_t caller)
{
    snapshot.clear();
    if (!HasQemuSession() || !openvpnConfig_ ||
        !OhosOpenvpn::Executable(caller, "/system/bin/qemu_openvpn_service") ||
        (qemuSupervisor_ > 0 && qemuSupervisor_ != caller)) return NETMANAGER_EXT_ERR_NOT_SYSTEM_CALL;
    OhosOpenvpn::SessionConfig config {qemuGeneration_, Base64::Decode(openvpnConfig_->ovpnConfig_), openvpnConfig_->askpass_};
    snapshot = OhosOpenvpn::EncodeSession(config);
    if (snapshot.empty()) return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
    qemuSupervisor_ = caller;
    return NETMANAGER_EXT_SUCCESS;
}

int32_t OpenvpnCtl::UpdateQemuConfig(cJSON *config)
{
    if (!vpnConfig_ || !openvpnConfig_ || !cJSON_IsObject(config) || cJSON_GetArraySize(config) != 5) return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
    unsigned mtu = 0;
    if (!QemuInteger(cJSON_GetObjectItemCaseSensitive(config, "mtu"), 65535, mtu) || mtu < 576) return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
    auto addresses = cJSON_GetObjectItemCaseSensitive(config, "addresses");
    auto routes = cJSON_GetObjectItemCaseSensitive(config, "routes");
    auto dns = cJSON_GetObjectItemCaseSensitive(config, "dns");
    auto domains = cJSON_GetObjectItemCaseSensitive(config, "domains");
    if (!cJSON_IsArray(addresses) || cJSON_GetArraySize(addresses) < 1 || cJSON_GetArraySize(addresses) > 2 ||
        !cJSON_IsArray(routes) || cJSON_GetArraySize(routes) < 1 || cJSON_GetArraySize(routes) > 520 ||
        !cJSON_IsArray(dns) || cJSON_GetArraySize(dns) > 16 || !cJSON_IsArray(domains) || cJSON_GetArraySize(domains) > 16) return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
    std::vector<INetAddr> nextAddresses; std::vector<Route> nextRoutes;
    std::vector<std::string> nextDns, nextDomains;
    bool ipv4 = false, ipv6 = false;
    cJSON *entry = nullptr;
    cJSON_ArrayForEach(entry, addresses) {
        INetAddr address;
        if (!cJSON_IsObject(entry) || cJSON_GetArraySize(entry) != 2 || !QemuAddress(entry, "address", address)) return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
        bool &present = address.type_ == INetAddr::IPV4 ? ipv4 : ipv6;
        if (present) return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
        present = true; nextAddresses.push_back(address);
    }
    if (ipv6 && mtu < 1280) return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
    cJSON_ArrayForEach(entry, routes) {
        Route route; std::string gateway;
        auto excluded = cJSON_GetObjectItemCaseSensitive(entry, "excluded");
        if (!cJSON_IsObject(entry) || cJSON_GetArraySize(entry) != 4 || !QemuAddress(entry, "network", route.destination_) ||
            !QemuString(cJSON_GetObjectItemCaseSensitive(entry, "gateway"), gateway) || !cJSON_IsBool(excluded)) return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
        const int family = OhosOpenvpn::IpFamily(gateway);
        if (family != (route.destination_.type_ == INetAddr::IPV4 ? AF_INET : AF_INET6) || (family == AF_INET ? !ipv4 : !ipv6)) return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
        route.gateway_.address_ = gateway; route.gateway_.family_ = route.gateway_.type_ = route.destination_.type_;
        route.iface_ = GetInterfaceName(); route.isExcludedRoute_ = cJSON_IsTrue(excluded);
        route.isDefaultRoute_ = route.destination_.prefixlen_ == 0;
        nextRoutes.push_back(route);
    }
    cJSON_ArrayForEach(entry, dns) {
        std::string address;
        if (!QemuString(entry, address)) return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
        const int family = OhosOpenvpn::IpFamily(address);
        if (!family || (family == AF_INET ? !ipv4 : !ipv6) || !OhosOpenvpn::AppendUnique(nextDns, address, 16)) return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
    }
    cJSON_ArrayForEach(entry, domains) {
        std::string domain;
        if (!QemuString(entry, domain) || !OhosOpenvpn::Domain(domain) || !OhosOpenvpn::AppendUnique(nextDomains, domain, 16)) return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
    }
    // Publish one fully checked snapshot; never append a new generation to old DNS/routes.
    vpnConfig_->mtu_ = mtu; vpnConfig_->isAcceptIPv4_ = ipv4; vpnConfig_->isAcceptIPv6_ = ipv6;
    vpnConfig_->addresses_ = nextAddresses; openvpnConfig_->localAddresses_ = nextAddresses;
    vpnConfig_->routes_ = std::move(nextRoutes); vpnConfig_->dnsAddresses_ = std::move(nextDns);
    vpnConfig_->searchDomains_ = std::move(nextDomains);
    qemuConfigured_ = true;
    return NETMANAGER_EXT_SUCCESS;
}

int32_t OpenvpnCtl::HandleQemuStage(const std::string &body, int32_t result, int32_t caller)
{
    if (result != NETMANAGER_EXT_SUCCESS) return NETMANAGER_EXT_ERR_INTERNAL;
    const char *end = nullptr;
    cJSON *message = cJSON_ParseWithOpts(body.c_str(), &end, true);
    if (!message) return NETMANAGER_EXT_ERR_PARAMETER_ERROR;
    if (qemuWorkerStopped_) { cJSON_Delete(message); return NETMANAGER_EXT_ERR_NOT_SYSTEM_CALL; }
    if (qemuSupervisor_ <= 1) {
        auto claim = cJSON_GetObjectItemCaseSensitive(message, "claim");
        const auto start = OhosOpenvpn::ProcessStart(caller);
        const bool valid = HasQemuSession() && cJSON_IsObject(message) && cJSON_GetArraySize(message) == 1 &&
            cJSON_IsObject(claim) && cJSON_GetArraySize(claim) == 0 && !start.empty() && OhosOpenvpn::WorkerProcess(caller) &&
            std::chrono::steady_clock::now() < qemuClaimDeadline_;
        cJSON_Delete(message);
        if (!valid) return NETMANAGER_EXT_ERR_NOT_SYSTEM_CALL;
        qemuSupervisor_ = caller; qemuWorkerStart_ = start;
        qemuBroker_ = OhosOpenvpn::Parent(caller); qemuBrokerStart_ = OhosOpenvpn::ProcessStart(qemuBroker_);
        return NETMANAGER_EXT_SUCCESS;
    }
    const auto role = OhosOpenvpn::CallerRole(caller, qemuSupervisor_, qemuWorkerStart_);
    if (role == OhosOpenvpn::SessionRole::Invalid) { cJSON_Delete(message); return NETMANAGER_EXT_ERR_NOT_SYSTEM_CALL; }
    int32_t response = NETMANAGER_EXT_ERR_PARAMETER_ERROR;
    if (cJSON_IsObject(message) && cJSON_GetArraySize(message) == 1) {
        auto config = cJSON_GetObjectItemCaseSensitive(message, "config");
        auto setup = cJSON_GetObjectItemCaseSensitive(message, "setupVpnTun");
        auto state = cJSON_GetObjectItemCaseSensitive(message, "updateState");
        auto reconnect = cJSON_GetObjectItemCaseSensitive(message, "reconnecting");
        const bool persistent = openvpnConfig_ && OhosOpenvpn::ProfileHasOption(
            Base64::Decode(openvpnConfig_->ovpnConfig_), "persist-tun");
        if (role == OhosOpenvpn::SessionRole::Bridge && config && (!qemuTunReady_ || persistent)) {
            char *printed = cJSON_PrintUnformatted(config);
            const std::string next = printed ? printed : ""; cJSON_free(printed);
            if (!next.empty() && next == qemuLastConfig_ && qemuConfigured_) response = NETMANAGER_EXT_SUCCESS;
            else if (!qemuTunReady_) {
                response = UpdateQemuConfig(config);
                if (response == NETMANAGER_EXT_SUCCESS) qemuLastConfig_ = next;
            } else if (!next.empty()) {
                // The enclosing service netVpnMutex_ serializes the whole
                // replacement. Parse every new field before removing old
                // routes/DNS; restore the old snapshot if any operation fails.
                const auto saved = *vpnConfig_;
                const auto savedLocal = openvpnConfig_->localAddresses_;
                response = UpdateQemuConfig(config);
                *vpnConfig_ = saved; openvpnConfig_->localAddresses_ = savedLocal;
                if (response == NETMANAGER_EXT_SUCCESS) {
                    response = NetVpnImpl::Destroy();
                    if (response == NETMANAGER_EXT_SUCCESS) {
                        qemuNeedsCleanup_ = false;
                        response = UpdateQemuConfig(config);
                        if (response == NETMANAGER_EXT_SUCCESS) {
                            qemuNeedsCleanup_ = true; response = NetVpnImpl::SetUp();
                        }
                        if (response == NETMANAGER_EXT_SUCCESS) qemuLastConfig_ = next;
                        else {
                            const int original = response;
                            const int clear = NetVpnImpl::Destroy();
                            *vpnConfig_ = saved; openvpnConfig_->localAddresses_ = savedLocal;
                            const int restored = clear == NETMANAGER_EXT_SUCCESS ? NetVpnImpl::SetUp() : clear;
                            qemuTunReady_ = restored == NETMANAGER_EXT_SUCCESS;
                            qemuNeedsCleanup_ = true;
                            NETMGR_EXT_LOG_E("QemuReconfigure rollback generation=%{public}s result=%{public}d restore=%{public}d",
                                qemuGeneration_.c_str(), original, restored);
                            response = original;
                        }
                    }
                }
                NETMGR_EXT_LOG_I("QemuReconfigure generation=%{public}s interface=%{public}s result=%{public}d",
                    qemuGeneration_.c_str(), GetInterfaceName().c_str(), response);
            }
        } else if (role == OhosOpenvpn::SessionRole::Bridge && cJSON_IsObject(setup) &&
            cJSON_GetArraySize(setup) == 0 && qemuConfigured_) {
            if (qemuTunReady_ && persistent) response = NETMANAGER_EXT_SUCCESS;
            else if (!qemuTunReady_) {
                qemuNeedsCleanup_ = true;
                response = SetUpVpnTun(); qemuTunReady_ = response == NETMANAGER_EXT_SUCCESS;
                if (response != NETMANAGER_EXT_SUCCESS) qemuNeedsCleanup_ = NetVpnImpl::Destroy() != NETMANAGER_EXT_SUCCESS;
            }
        } else if (role == OhosOpenvpn::SessionRole::Supervisor && cJSON_IsObject(reconnect) && cJSON_GetArraySize(reconnect) == 0) {
            const bool preserve = persistent && qemuTunReady_ && qemuConfigured_;
            response = !preserve && qemuNeedsCleanup_ ? NetVpnImpl::Destroy() : NETMANAGER_EXT_SUCCESS;
            if (!preserve && response == NETMANAGER_EXT_SUCCESS) qemuNeedsCleanup_ = false;
            qemuConfigured_ = qemuTunReady_ = preserve;
            NETMGR_EXT_LOG_I("QemuReconnect generation=%{public}s interface=%{public}s preserve=%{public}d result=%{public}d",
                qemuGeneration_.c_str(), GetInterfaceName().c_str(), preserve, response);
            UpdateOpenvpnState(OPENVPN_STATE_DISCONNECTED);
            if (response == NETMANAGER_EXT_SUCCESS) UpdateOpenvpnState(OPENVPN_STATE_STARTED);
        } else if (role == OhosOpenvpn::SessionRole::Supervisor && cJSON_IsObject(state) && cJSON_GetArraySize(state) == 1) {
            unsigned stage = 0;
            if (QemuInteger(cJSON_GetObjectItemCaseSensitive(state, "state"), OPENVPN_STATE_DISCONNECTED, stage)) {
                if (stage == OPENVPN_STATE_CONNECTED && qemuTunReady_) {
                    UpdateOpenvpnState(stage); response = NETMANAGER_EXT_SUCCESS;
                } else if (stage == OPENVPN_STATE_DISCONNECTED) {
                    response = qemuNeedsCleanup_ ? NetVpnImpl::Destroy() : NETMANAGER_EXT_SUCCESS;
                    if (response == NETMANAGER_EXT_SUCCESS) qemuNeedsCleanup_ = false;
                    qemuConfigured_ = qemuTunReady_ = false;
                    UpdateOpenvpnState(stage);
                    // Keep the capability until explicit STOP confirms actual
                    // worker exit and native descriptor binding removal. A
                    // cleanup error never keeps the connection state true.
                }
            }
        }
    }
    cJSON_Delete(message);
    return response;
}

std::string OpenvpnCtl::MaskOpenvpnMessage(const std::string &msg)
{
    if (msg.empty()) {
        NETMGR_EXT_LOG_E("msg is empty");
        return "";
    }
    std::string result = msg;
    size_t addressPos = result.find(OPENVPN_NODE_CONFIG);
    if (addressPos != std::string::npos) {
        size_t pos = addressPos + strlen(OPENVPN_NODE_CONFIG);
        size_t replaceLen = result.size() - pos;
        if (replaceLen > 0) {
            result.replace(pos, replaceLen, OPENVPN_MASK_TAG);
        }
        return result;
    }

    return msg;
}
} // namespace NetManagerStandard
} // namespace OHOS