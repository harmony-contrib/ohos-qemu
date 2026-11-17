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

#include "system_vpn_wrapper.h"

#include <unistd.h>
#ifdef OHOS_QEMU_OPENVPN
#include "service_control.h"
#include "../../../../../netmanager_ext/qemu_openvpn/broker_protocol.h"
#include <mutex>
#endif
#include "netnative_log_wrapper.h"
#include "netmanager_base_common_utils.h"
#include "net_manager_constants.h"
#include "multi_vpn_manager.h"

namespace OHOS {
namespace nmd {
using namespace NetManagerStandard;
// LCOV_EXCL_START
SystemVpnWrapper::SystemVpnWrapper()
{
    isIpSecAccess_ = access(IPSEC_CMD_PATH, F_OK) == 0;
    vpnFfrtQueue_ = std::make_shared<ffrt::queue>("SystemVpnWrapper");
}

SystemVpnWrapper::~SystemVpnWrapper()
{
    vpnFfrtQueue_.reset();
}

bool SystemVpnWrapper::PrepareUpdate(SysVpnStageCode stage, const std::string &message)
{
    NETNATIVE_LOGI("run ExtUpdateMessage stage %{public}d", stage);
    switch (stage) {
        case SysVpnStageCode::VPN_STAGE_CREATE_PPP_FD:
            MultiVpnManager::GetInstance().CreatePppFd(message);
            break;
        case SysVpnStageCode::VPN_STAGE_SET_XFRM_PHY_IFNAME:
            MultiVpnManager::GetInstance().SetXfrmPhyIfName(message);
            break;
        case SysVpnStageCode::VPN_STAGE_SET_VPN_CALL_MODE:
            MultiVpnManager::GetInstance().SetVpnCallMode(message);
            break;
        case SysVpnStageCode::VPN_STAGE_SET_VPN_REMOTE_ADDRESS:
            MultiVpnManager::GetInstance().SetVpnRemoteAddress(message);
            break;
        case SysVpnStageCode::VPN_STAGE_L2TP_STOP:
            MultiVpnManager::GetInstance().ClearPppFd(message);
            return false;
        default:
            return false;
    }
    return true;
}

void SystemVpnWrapper::ExecuteUpdate(SysVpnStageCode stage, const std::string &message)
{
    NETNATIVE_LOGI("run ExecuteUpdate stage %{public}d", stage);
    std::string param = std::string(IPSEC_CMD_PATH) + " ";
    switch (stage) {
        case SysVpnStageCode::VPN_STAGE_RESTART:
            param.append(VPN_STAGE_RESTART);
            break;
        case SysVpnStageCode::VPN_STAGE_UP_HOME:
            param.append(VPN_STAGE_UP_HOME).append(message.empty() ? "home" : message);
            break;
        case SysVpnStageCode::VPN_STAGE_SWANCTL_LOAD:
            param.append(VPN_STAGE_SWANCTL_LOAD).append(SWAN_CTL_FILE);
            break;
        case SysVpnStageCode::VPN_STAGE_L2TP_LOAD:
            param.append(VPN_STAGE_L2TP_LOAD).append(L2TP_CFG).append(IPSEC_L2TP_CTL);
            break;
        case SysVpnStageCode::VPN_STAGE_L2TP_CTL:
            param.append(VPN_STAGE_L2TP_CTL).append(message.empty() ? "myVPN" : message);
            break;
        case SysVpnStageCode::VPN_STAGE_DOWN_HOME:
            param.append(VPN_STAGE_DOWN_HOME).append(message.empty() ? "home" : message);
            break;
        case SysVpnStageCode::VPN_STAGE_STOP:
            param.append(VPN_STAGE_STOP);
            break;
        case SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART:
            param.append(VPN_STAGE_OPENVPN_RESTART).append(OPENVPN_CONFIG_FILE);
            break;
        case SysVpnStageCode::VPN_STAGE_OPENVPN_STOP:
            param.append(VPN_STAGE_OPENVPN_STOP);
            break;
        case SysVpnStageCode::VPN_STAGE_L2TP_STOP:
            param.append(VPN_STAGE_L2TP_STOP).append(message);
            break;
        case SysVpnStageCode::VPN_STAGE_SET_L2TP_CONF:
            param.append(VPN_STAGE_SET_L2TP_CONF).append(message);
            break;
        default:
            NETNATIVE_LOGE("run ExecuteUpdate failed, unknown stage %{public}d", stage);
            return;
    }
    if (CommonUtils::ForkExec(param) == NETMANAGER_ERROR) {
        NETNATIVE_LOGE("run ExecuteUpdate failed");
    }
}

int32_t SystemVpnWrapper::Update(NetsysNative::SysVpnStageCode stage, const std::string &message)
{
#ifdef OHOS_QEMU_OPENVPN
    if (stage == SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART || stage == SysVpnStageCode::VPN_STAGE_OPENVPN_STOP) {
        OhosOpenvpn::BrokerCommand command;
        if (!OhosOpenvpn::DecodeBroker(message, command) ||
            command.start != (stage == SysVpnStageCode::VPN_STAGE_OPENVPN_RESTART)) return NETMANAGER_ERROR;
        // Serialize native registration with the broker response; the service
        // continues to serialize the owning ctl/config through netVpnMutex_.
        static std::mutex brokerMutex;
        std::lock_guard<std::mutex> lock(brokerMutex);
        if (command.start && MultiVpnManager::GetInstance().HasQemuSession(command.session.token)) return NETMANAGER_ERROR;
        const bool recovering = !command.start && MultiVpnManager::GetInstance().QemuRecoveryReady(command);
        pid_t broker = -1;
        OhosOpenvpn::BrokerFd connection(OhosOpenvpn::ConnectBroker(broker));
        if (connection.value < 0 && (command.start || recovering)) {
            if (!MultiVpnManager::GetInstance().QemuCanStartBroker()) return NETMANAGER_ERROR;
            if (access("/system/bin/qemu_openvpn_service", X_OK) != 0 || ServiceControl("qemu_openvpn", START) != 0) return NETMANAGER_ERROR;
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
            do {
                connection.value = OhosOpenvpn::ConnectBroker(broker);
                if (connection.value >= 0) break;
                poll(nullptr, 0, 25);
            } while (std::chrono::steady_clock::now() < deadline);
        }
        if (connection.value < 0) return NETMANAGER_ERROR;
        const auto brokerStart = OhosOpenvpn::ProcessStart(broker);
        if (brokerStart.empty()) return NETMANAGER_ERROR;
        std::string reply;
        const bool exchanged = OhosOpenvpn::SendFrame(connection.value, message) &&
            OhosOpenvpn::ReadFrame(connection.value, reply, command.start ? 2000 : 7000);
        pid_t worker = -1; std::string workerStart;
        const bool acknowledged = command.start ? OhosOpenvpn::DecodeStartReply(reply, worker, workerStart) :
            (reply == "0" || (recovering && reply == std::to_string(ENOENT)));
        if (!exchanged || !acknowledged || OhosOpenvpn::ProcessStart(broker) != brokerStart) {
            if (command.start && !exchanged) {
                // A lost START response is an ambiguous accepted request.
                // Cancel only this capability; never stop/restart the broker.
                command.start = false; command.session.profile.clear(); command.session.password.clear();
                pid_t cleanupBroker = -1;
                OhosOpenvpn::BrokerFd cleanup(OhosOpenvpn::ConnectBroker(cleanupBroker));
                if (cleanup.value >= 0 && cleanupBroker == broker) {
                    OhosOpenvpn::SendFrame(cleanup.value, OhosOpenvpn::EncodeBroker(command));
                    OhosOpenvpn::ReadFrame(cleanup.value, reply, 7000);
                }
            }
            return NETMANAGER_ERROR;
        }
        if (command.start && MultiVpnManager::GetInstance().BindQemuSession(command, broker, brokerStart, worker, workerStart) != NETMANAGER_SUCCESS) {
            command.start = false; command.session.profile.clear(); command.session.password.clear();
            pid_t cleanupBroker = -1;
            OhosOpenvpn::BrokerFd cleanup(OhosOpenvpn::ConnectBroker(cleanupBroker));
            if (cleanup.value >= 0 && cleanupBroker == broker) {
                OhosOpenvpn::SendFrame(cleanup.value, OhosOpenvpn::EncodeBroker(command));
                OhosOpenvpn::ReadFrame(cleanup.value, reply, 7000);
            }
            return NETMANAGER_ERROR;
        }
        if (!command.start) MultiVpnManager::GetInstance().UnbindQemuSession(command.session.token);
        // START acknowledges an owned worker only; TLS/TUN prove CONNECTED.
        // STOP acknowledges actual exit of this worker's entire process group.
        return NetManagerStandard::NETMANAGER_SUCCESS;
    }
#endif

    if (PrepareUpdate(stage, message)) {
        return NetManagerStandard::NETMANAGER_SUCCESS;
    }
    if (!vpnFfrtQueue_) {
        NETNATIVE_LOGE("FFRT Init Fail");
        return NETMANAGER_ERROR;
    }

    if (!isIpSecAccess_) {
        NETNATIVE_LOGE("Update failed! exec program is not exist");
        return NETMANAGER_ERROR;
    }
#if UNITTEST_FORBID_FFRT // Forbid FFRT for unittest, which will cause crash in destructor process
    ExecuteUpdate(stage, message);
#else
    std::function<void()> update = std::bind(&SystemVpnWrapper::ExecuteUpdate, shared_from_this(), stage, message);
    vpnFfrtQueue_->submit(update);
#endif // UNITTEST_FORBID_FFRT
    return NetManagerStandard::NETMANAGER_SUCCESS;
}
// LCOV_EXCL_STOP
} // namespace nmd
} // namespace OHOS
