/*
 * Copyright (c) 2024 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "vpn_data_bean.h"
#include "vpn_network_config.h"
#include "netmgr_ext_log_wrapper.h"
#include "net_manager_ext_constants.h"

namespace OHOS {
namespace NetManagerStandard {
sptr<SysVpnConfig> VpnDataBean::ConvertVpnBeanToSysVpnConfig(sptr<VpnDataBean> &vpnBean)
{
    if (vpnBean == nullptr) {
        NETMGR_EXT_LOG_E("ConvertVpnBeanToSysVpnConfig vpnBean is null");
        return nullptr;
    }
    switch (vpnBean->vpnType_) {
        case VpnType::IKEV2_IPSEC_MSCHAPv2:
        case VpnType::IKEV2_IPSEC_PSK:
        case VpnType::IKEV2_IPSEC_RSA:
        case VpnType::IPSEC_XAUTH_PSK:
        case VpnType::IPSEC_XAUTH_RSA:
        case VpnType::IPSEC_HYBRID_RSA:
            return ConvertVpnBeanToIpsecVpnConfig(vpnBean);
        case VpnType::OPENVPN:
            return ConvertVpnBeanToOpenvpnConfig(vpnBean);
        case VpnType::L2TP:
        case VpnType::L2TP_IPSEC_PSK:
        case VpnType::L2TP_IPSEC_RSA:
            return ConvertVpnBeanToL2tpVpnConfig(vpnBean);
        default:
            NETMGR_EXT_LOG_E("ConvertVpnBeanToSysVpnConfig failed, invalid type=%{public}d", vpnBean->vpnType_);
            return nullptr;
    }
}

sptr<OpenvpnConfig> VpnDataBean::ConvertVpnBeanToOpenvpnConfig(sptr<VpnDataBean> vpnBean)
{
    if (vpnBean == nullptr) {
        NETMGR_EXT_LOG_E("ConvertVpnBeanToOpenvpnConfig vpnBean is null");
        return nullptr;
    }
    sptr<OpenvpnConfig> openvpnConfig = new (std::nothrow) OpenvpnConfig();
    if (openvpnConfig == nullptr) {
        NETMGR_EXT_LOG_E("ConvertVpnBeanToOpenvpnConfig openvpnConfig is null");
        return nullptr;
    }
    openvpnConfig->vpnId_ = vpnBean->vpnId_;
    openvpnConfig->vpnName_ = vpnBean->vpnName_;
    openvpnConfig->vpnType_ = vpnBean->vpnType_;
    openvpnConfig->userName_ = vpnBean->userName_;
    openvpnConfig->password_ = vpnBean->password_;
    openvpnConfig->userId_ = vpnBean->userId_;
    openvpnConfig->isLegacy_ = (vpnBean->isLegacy_) == 1;
    openvpnConfig->saveLogin_ = (vpnBean->saveLogin_) == 1;

    openvpnConfig->ovpnPort_ = vpnBean->ovpnPort_;
    openvpnConfig->ovpnProtocol_ = vpnBean->ovpnProtocol_;
    openvpnConfig->ovpnConfig_ = vpnBean->ovpnConfig_;
    openvpnConfig->ovpnAuthType_ = vpnBean->ovpnAuthType_;
    openvpnConfig->askpass_ = vpnBean->askpass_;
    openvpnConfig->ovpnConfigFilePath_ = vpnBean->ovpnConfigFilePath_;
    openvpnConfig->ovpnCaCertFilePath_ = vpnBean->ovpnCaCertFilePath_;
    openvpnConfig->ovpnUserCertFilePath_ = vpnBean->ovpnUserCertFilePath_;
    openvpnConfig->ovpnPrivateKeyFilePath_ = vpnBean->ovpnPrivateKeyFilePath_;

    if (!vpnBean->remoteAddr_.empty()) {
        openvpnConfig->remoteAddresses_.push_back(vpnBean->remoteAddr_);
    }

    if (!VpnNetworkStorage::Restore(vpnBean->networkConfig_, *openvpnConfig)) {
        NETMGR_EXT_LOG_E("Invalid OpenVPN network snapshot");
        return nullptr;
    }
    return openvpnConfig;
}

sptr<IpsecVpnConfig> VpnDataBean::ConvertVpnBeanToIpsecVpnConfig(sptr<VpnDataBean> &vpnBean)
{
    if (vpnBean == nullptr) {
        NETMGR_EXT_LOG_E("ConvertVpnBeanToIpsecVpnConfig vpnBean is null");
        return nullptr;
    }
    sptr<IpsecVpnConfig> ipsecVpnConfig = new (std::nothrow) IpsecVpnConfig();
    sptr<INetAddr> netAddr = new (std::nothrow) INetAddr();
    if (ipsecVpnConfig == nullptr || netAddr == nullptr) {
        NETMGR_EXT_LOG_E("ConvertVpnBeanToIpsecVpnConfig ipsecVpnConfig or netAddr is null");
        return nullptr;
    }
    ipsecVpnConfig->vpnId_ = vpnBean->vpnId_;
    ipsecVpnConfig->vpnName_ = vpnBean->vpnName_;
    ipsecVpnConfig->vpnType_ = vpnBean->vpnType_;
    netAddr->address_ = vpnBean->vpnAddress_;
    ipsecVpnConfig->addresses_.push_back(*netAddr);
    ipsecVpnConfig->userName_ = vpnBean->userName_;
    ipsecVpnConfig->password_ = vpnBean->password_;
    ipsecVpnConfig->userId_ = vpnBean->userId_;
    ipsecVpnConfig->isLegacy_ = (vpnBean->isLegacy_) == 1;
    ipsecVpnConfig->saveLogin_ = (vpnBean->saveLogin_) == 1;
    ipsecVpnConfig->forwardingRoutes_ = vpnBean->forwardingRoutes_;
    ipsecVpnConfig->dnsAddresses_.push_back(vpnBean->dnsAddresses_);
    ipsecVpnConfig->searchDomains_.push_back(vpnBean->searchDomains_);

    ipsecVpnConfig->ipsecPreSharedKey_ = vpnBean->ipsecPreSharedKey_;
    ipsecVpnConfig->ipsecIdentifier_ = vpnBean->ipsecIdentifier_;
    ipsecVpnConfig->ipsecCaCertConf_ = vpnBean->ipsecCaCertConf_;
    ipsecVpnConfig->ipsecPrivateUserCertConf_ = vpnBean->ipsecPrivateUserCertConf_;
    ipsecVpnConfig->ipsecPublicUserCertConf_ = vpnBean->ipsecPublicUserCertConf_;
    ipsecVpnConfig->ipsecPrivateServerCertConf_ = vpnBean->ipsecPrivateServerCertConf_;
    ipsecVpnConfig->ipsecPublicServerCertConf_ = vpnBean->ipsecPublicServerCertConf_;
    ipsecVpnConfig->ipsecCaCertFilePath_ = vpnBean->ipsecCaCertFilePath_;
    ipsecVpnConfig->ipsecPrivateUserCertFilePath_ = vpnBean->ipsecPrivateUserCertFilePath_;
    ipsecVpnConfig->ipsecPublicUserCertFilePath_ = vpnBean->ipsecPublicUserCertFilePath_;
    ipsecVpnConfig->ipsecPrivateServerCertFilePath_ = vpnBean->ipsecPrivateServerCertFilePath_;
    ipsecVpnConfig->ipsecPublicServerCertFilePath_ = vpnBean->ipsecPublicServerCertFilePath_;

    if (!vpnBean->remoteAddr_.empty()) {
        ipsecVpnConfig->remoteAddresses_.push_back(vpnBean->remoteAddr_);
    }
    if (!VpnNetworkStorage::Restore(vpnBean->networkConfig_, *ipsecVpnConfig)) {
        NETMGR_EXT_LOG_E("Invalid IPsec network snapshot");
        return nullptr;
    }
    return ipsecVpnConfig;
}

sptr<L2tpVpnConfig> VpnDataBean::ConvertVpnBeanToL2tpVpnConfig(sptr<VpnDataBean> &vpnBean)
{
    if (vpnBean == nullptr) {
        NETMGR_EXT_LOG_E("ConvertVpnBeanToL2tpVpnConfig vpnBean is null");
        return nullptr;
    }
    sptr<L2tpVpnConfig> l2tpVpnConfig = new (std::nothrow) L2tpVpnConfig();
    sptr<INetAddr> netAddr = new (std::nothrow) INetAddr();
    if (l2tpVpnConfig == nullptr || netAddr == nullptr) {
        NETMGR_EXT_LOG_E("ConvertVpnBeanToL2tpVpnConfig l2tpVpnConfig or netAddr is null");
        return nullptr;
    }
    l2tpVpnConfig->vpnId_ = vpnBean->vpnId_;
    l2tpVpnConfig->vpnName_ = vpnBean->vpnName_;
    l2tpVpnConfig->vpnType_ = vpnBean->vpnType_;
    netAddr->address_ = vpnBean->vpnAddress_;
    l2tpVpnConfig->addresses_.push_back(*netAddr);
    l2tpVpnConfig->userName_ = vpnBean->userName_;
    l2tpVpnConfig->password_ = vpnBean->password_;
    l2tpVpnConfig->userId_ = vpnBean->userId_;
    l2tpVpnConfig->isLegacy_ = (vpnBean->isLegacy_) == 1;
    l2tpVpnConfig->saveLogin_ = (vpnBean->saveLogin_) == 1;
    l2tpVpnConfig->forwardingRoutes_ = vpnBean->forwardingRoutes_;
    l2tpVpnConfig->dnsAddresses_.push_back(vpnBean->dnsAddresses_);
    l2tpVpnConfig->searchDomains_.push_back(vpnBean->searchDomains_);

    l2tpVpnConfig->ipsecPreSharedKey_ = vpnBean->ipsecPreSharedKey_;
    l2tpVpnConfig->ipsecIdentifier_ = vpnBean->ipsecIdentifier_;
    l2tpVpnConfig->ipsecCaCertConf_ = vpnBean->ipsecCaCertConf_;
    l2tpVpnConfig->ipsecPrivateUserCertConf_ = vpnBean->ipsecPrivateUserCertConf_;
    l2tpVpnConfig->ipsecPublicUserCertConf_ = vpnBean->ipsecPublicUserCertConf_;
    l2tpVpnConfig->ipsecPrivateServerCertConf_ = vpnBean->ipsecPrivateServerCertConf_;
    l2tpVpnConfig->ipsecPublicServerCertConf_ = vpnBean->ipsecPublicServerCertConf_;
    l2tpVpnConfig->ipsecCaCertFilePath_ = vpnBean->ipsecCaCertFilePath_;
    l2tpVpnConfig->ipsecPrivateUserCertFilePath_ = vpnBean->ipsecPrivateUserCertFilePath_;
    l2tpVpnConfig->ipsecPublicUserCertFilePath_ = vpnBean->ipsecPublicUserCertFilePath_;
    l2tpVpnConfig->ipsecPrivateServerCertFilePath_ = vpnBean->ipsecPrivateServerCertFilePath_;
    l2tpVpnConfig->ipsecPublicServerCertFilePath_ = vpnBean->ipsecPublicServerCertFilePath_;

    l2tpVpnConfig->l2tpSharedKey_ = vpnBean->l2tpSharedKey_;
    if (!vpnBean->remoteAddr_.empty()) {
        l2tpVpnConfig->remoteAddresses_.push_back(vpnBean->remoteAddr_);
    }
    if (!VpnNetworkStorage::Restore(vpnBean->networkConfig_, *l2tpVpnConfig)) {
        NETMGR_EXT_LOG_E("Invalid L2TP network snapshot");
        return nullptr;
    }
    return l2tpVpnConfig;
}

sptr<VpnDataBean> VpnDataBean::ConvertSysVpnConfigToVpnBean(const sptr<SysVpnConfig> &sysVpnConfig)
{
    if (sysVpnConfig == nullptr) {
        NETMGR_EXT_LOG_E("ConvertSysVpnConfigToVpnBean sysVpnConfig is null");
        return nullptr;
    }
    sptr<VpnDataBean> vpnBean = new (std::nothrow) VpnDataBean();
    if (vpnBean == nullptr) {
        NETMGR_EXT_LOG_E("ConvertSysVpnConfigToVpnBean vpnBean is null");
        return nullptr;
    }
    ConvertCommonVpnConfigToVpnBean(sysVpnConfig, vpnBean);
    if (!VpnNetworkStorage::Encode(*sysVpnConfig, vpnBean->networkConfig_)) {
        NETMGR_EXT_LOG_E("Cannot encode bounded VPN network snapshot");
        return nullptr;
    }
    switch (sysVpnConfig->vpnType_) {
        case VpnType::IKEV2_IPSEC_MSCHAPv2:
        case VpnType::IKEV2_IPSEC_PSK:
        case VpnType::IKEV2_IPSEC_RSA:
        case VpnType::IPSEC_XAUTH_PSK:
        case VpnType::IPSEC_XAUTH_RSA:
        case VpnType::IPSEC_HYBRID_RSA:
            ConvertIpsecVpnConfigToVpnBean(sysVpnConfig, vpnBean);
            break;
        case VpnType::L2TP:
        case VpnType::L2TP_IPSEC_PSK:
        case VpnType::L2TP_IPSEC_RSA:
            ConvertL2tpVpnConfigToVpnBean(sysVpnConfig, vpnBean);
            break;
        case VpnType::OPENVPN:
            ConvertOpenvpnConfigToVpnBean(sysVpnConfig, vpnBean);
            break;
        default:
            NETMGR_EXT_LOG_E("ConvertSysVpnConfigToVpnBean proxy vpn type is error");
            break;
    }
    return vpnBean;
}

void VpnDataBean::ConvertCommonVpnConfigToVpnBean(const sptr<SysVpnConfig> &sysVpnConfig, sptr<VpnDataBean> &vpnBean)
{
    if (vpnBean == nullptr || sysVpnConfig == nullptr) {
        NETMGR_EXT_LOG_E("ConvertCommonVpnConfigToVpnBean params is null");
        return;
    }
    vpnBean->vpnId_ = sysVpnConfig->vpnId_;
    vpnBean->vpnName_ = sysVpnConfig->vpnName_;
    vpnBean->vpnType_ = sysVpnConfig->vpnType_;
    std::vector<INetAddr> addresses = sysVpnConfig->addresses_;
    if (!addresses.empty()) {
        vpnBean->vpnAddress_ = addresses[0].address_;
    }
    if (!sysVpnConfig->remoteAddresses_.empty()) {
        vpnBean->remoteAddr_ = sysVpnConfig->remoteAddresses_[0];
    }
    vpnBean->userName_ = sysVpnConfig->userName_;
    vpnBean->password_ = sysVpnConfig->password_;
    vpnBean->userId_ = sysVpnConfig->userId_;
    vpnBean->isLegacy_ = sysVpnConfig->isLegacy_ ? 1 : 0;
    vpnBean->saveLogin_ = sysVpnConfig->saveLogin_ ? 1 : 0;
    vpnBean->forwardingRoutes_ = sysVpnConfig->forwardingRoutes_;
    std::vector<std::string> dnsAddresses = sysVpnConfig->dnsAddresses_;
    if (!dnsAddresses.empty()) {
        vpnBean->dnsAddresses_ = dnsAddresses[0];
    }
    std::vector<std::string> searchDomains = sysVpnConfig->searchDomains_;
    if (!searchDomains.empty()) {
        vpnBean->searchDomains_ = searchDomains[0];
    }
}

void VpnDataBean::ConvertOpenvpnConfigToVpnBean(const sptr<SysVpnConfig> sysVpnConfig, sptr<VpnDataBean> &vpnBean)
{
    if (vpnBean == nullptr || sysVpnConfig == nullptr) {
        NETMGR_EXT_LOG_E("ConvertOpenvpnConfigToVpnBean params is null");
        return;
    }
    OpenvpnConfig *openvpnConfig = static_cast<OpenvpnConfig *>(sysVpnConfig.GetRefPtr());
    if (openvpnConfig == nullptr) {
        NETMGR_EXT_LOG_E("ConvertOpenvpnConfigToVpnBean openvpnConfig is null");
        return;
    }
    vpnBean->ovpnPort_ = openvpnConfig->ovpnPort_;
    vpnBean->ovpnProtocol_ = openvpnConfig->ovpnProtocol_;
    vpnBean->ovpnConfig_ = openvpnConfig->ovpnConfig_;
    vpnBean->ovpnAuthType_ = openvpnConfig->ovpnAuthType_;
    vpnBean->askpass_ = openvpnConfig->askpass_;
    vpnBean->ovpnConfigFilePath_ = openvpnConfig->ovpnConfigFilePath_;
    vpnBean->ovpnCaCertFilePath_ = openvpnConfig->ovpnCaCertFilePath_;
    vpnBean->ovpnUserCertFilePath_ = openvpnConfig->ovpnUserCertFilePath_;
    vpnBean->ovpnPrivateKeyFilePath_ = openvpnConfig->ovpnPrivateKeyFilePath_;
    openvpnConfig = nullptr;
}

void VpnDataBean::ConvertIpsecVpnConfigToVpnBean(const sptr<SysVpnConfig> sysVpnConfig, sptr<VpnDataBean> &vpnBean)
{
    if (vpnBean == nullptr || sysVpnConfig == nullptr) {
        NETMGR_EXT_LOG_E("ConvertIpsecVpnConfigToVpnBean params is null");
        return;
    }
    IpsecVpnConfig *ipsecVpnConfig = static_cast<IpsecVpnConfig *>(sysVpnConfig.GetRefPtr());
    if (ipsecVpnConfig == nullptr) {
        NETMGR_EXT_LOG_E("ConvertIpsecVpnConfigToVpnBean ipsecVpnConfig is null");
        return;
    }
    vpnBean->ipsecPreSharedKey_ = ipsecVpnConfig->ipsecPreSharedKey_;
    vpnBean->ipsecIdentifier_ = ipsecVpnConfig->ipsecIdentifier_;
    vpnBean->ipsecCaCertConf_ = ipsecVpnConfig->ipsecCaCertConf_;
    vpnBean->ipsecPrivateUserCertConf_ = ipsecVpnConfig->ipsecPrivateUserCertConf_;
    vpnBean->ipsecPublicUserCertConf_ = ipsecVpnConfig->ipsecPublicUserCertConf_;
    vpnBean->ipsecPrivateServerCertConf_ = ipsecVpnConfig->ipsecPrivateServerCertConf_;
    vpnBean->ipsecPublicServerCertConf_ = ipsecVpnConfig->ipsecPublicServerCertConf_;
    vpnBean->ipsecCaCertFilePath_ = ipsecVpnConfig->ipsecCaCertFilePath_;
    vpnBean->ipsecPrivateUserCertFilePath_ = ipsecVpnConfig->ipsecPrivateUserCertFilePath_;
    vpnBean->ipsecPublicUserCertFilePath_ = ipsecVpnConfig->ipsecPublicUserCertFilePath_;
    vpnBean->ipsecPrivateServerCertFilePath_ = ipsecVpnConfig->ipsecPrivateServerCertFilePath_;
    vpnBean->ipsecPublicServerCertFilePath_ = ipsecVpnConfig->ipsecPublicServerCertFilePath_;
    ipsecVpnConfig = nullptr;
}

void VpnDataBean::ConvertL2tpVpnConfigToVpnBean(const sptr<SysVpnConfig> sysVpnConfig, sptr<VpnDataBean> &vpnBean)
{
    if (vpnBean == nullptr || sysVpnConfig == nullptr) {
        NETMGR_EXT_LOG_E("ConvertL2tpVpnConfigToVpnBean params is null");
        return;
    }
    L2tpVpnConfig *l2tpVpnConfig = static_cast<L2tpVpnConfig *>(sysVpnConfig.GetRefPtr());
    if (l2tpVpnConfig == nullptr) {
        NETMGR_EXT_LOG_E("ConvertL2tpVpnConfigToVpnBean l2tpVpnConfig is null");
        return;
    }
    vpnBean->ipsecPreSharedKey_ = l2tpVpnConfig->ipsecPreSharedKey_;
    vpnBean->ipsecIdentifier_ = l2tpVpnConfig->ipsecIdentifier_;
    vpnBean->ipsecCaCertConf_ = l2tpVpnConfig->ipsecCaCertConf_;
    vpnBean->ipsecPrivateUserCertConf_ = l2tpVpnConfig->ipsecPrivateUserCertConf_;
    vpnBean->ipsecPublicUserCertConf_ = l2tpVpnConfig->ipsecPublicUserCertConf_;
    vpnBean->ipsecPrivateServerCertConf_ = l2tpVpnConfig->ipsecPrivateServerCertConf_;
    vpnBean->ipsecPublicServerCertConf_ = l2tpVpnConfig->ipsecPublicServerCertConf_;
    vpnBean->ipsecCaCertFilePath_ = l2tpVpnConfig->ipsecCaCertFilePath_;
    vpnBean->ipsecPrivateUserCertFilePath_ = l2tpVpnConfig->ipsecPrivateUserCertFilePath_;
    vpnBean->ipsecPublicUserCertFilePath_ = l2tpVpnConfig->ipsecPublicUserCertFilePath_;
    vpnBean->ipsecPrivateServerCertFilePath_ = l2tpVpnConfig->ipsecPrivateServerCertFilePath_;
    vpnBean->ipsecPublicServerCertFilePath_ = l2tpVpnConfig->ipsecPublicServerCertFilePath_;
    vpnBean->l2tpSharedKey_ = l2tpVpnConfig->l2tpSharedKey_;
    l2tpVpnConfig = nullptr;
}
} // namespace NetManagerStandard
} // namespace OHOS
