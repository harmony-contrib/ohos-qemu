/*
 * Copyright (C) 2021-2022 Huawei Device Co., Ltd.
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

#ifndef INCLUDE_ROUTE_MANAGER_H
#define INCLUDE_ROUTE_MANAGER_H

#include <linux/netlink.h>
#include <map>
#include <netinet/in.h>
#include <cstdint>

#include "netlink_msg.h"
#include "network_permission.h"
#include "uid_range.h"
#include "route_type.h"

namespace OHOS {
namespace nmd {
constexpr uid_t INVALID_UID = static_cast<uid_t>(-1);
typedef struct RuleInfo {
    uint32_t ruleTable;
    uint32_t rulePriority;
    uint32_t ruleFwmark;
    uint32_t ruleMask;
    std::string ruleIif;
    std::string ruleOif;
    std::string ruleSrcIp;
    std::string ruleDstIp;
} RuleInfo;

typedef struct RouteInfo {
    uint32_t routeTable;
    std::string routeInterfaceName;
    std::string routeDestinationName;
    std::string routeNextHop;
    bool isExcludedRoute = false;
} RouteInfo;

typedef struct InetAddr {
    int32_t family;
    int32_t bitlen;
    int32_t prefixlen;
    uint8_t data[sizeof(struct in6_addr)];
} InetAddr;

class RouteManager {
public:
    RouteManager();
    ~RouteManager() = default;

    /**
     * Route table type
     *
     */
    enum TableType {
        INTERFACE,
        VPN_NETWORK,
        LOCAL_NETWORK,
        INTERNAL_DEFAULT,
        UNREACHABLE_NETWORK,
        TABLE_TYPE_BUTT,
    };

    /**
     * The interface is add route table
     *
     * @param tableType Route table type.Must be one of INTERFACE/VPN_NETWORK/LOCAL_NETWORK.
     * @param networkRouteInfo Route info
     * @return Returns 0, add route table successfully, otherwise it will fail
     */
    static int32_t AddRoute(TableType tableType, NetworkRouteInfo networkRouteInfo, bool& routeRepeat);

    /**
 	 * The interface is to add multiple routes to route table in batch
 	 *
 	 * @param tableType Route table type.Must be one of INTERFACE/VPN_NETWORK/LOCAL_NETWORK.
 	 * @param networkRouteInfos List of route info to be added
 	 * @return Returns 0, add multiple route tables successfully, otherwise it will fail
 	 */
    static int32_t AddRoutes(TableType tableType, std::vector<NetworkRouteInfo> networkRouteInfos);

    /**
     * The interface is remove route table
     *
     * @param tableType Route table type.Must be one of INTERFACE/VPN_NETWORK/LOCAL_NETWORK.
     * @param interfaceName Output network device name of the route item
     * @param destinationName Destination address of route item
     * @param nextHop Gateway address of the route item
     * @param isExcludedRoute Is excluded route
     * @return Returns 0, remove route table successfully, otherwise it will fail
     */
    static int32_t RemoveRoute(TableType tableType, const std::string &interfaceName,
        const std::string &destinationName, const std::string &nextHop, bool isExcludedRoute = false);

    /**
     * The interface is update route table
     *
     * @param tableType Route table type.Must be one of INTERFACE/VPN_NETWORK/LOCAL_NETWORK.
     * @param interfaceName Output network device name of the route item
     * @param destinationName Destination address of route item
     * @param nextHop Gateway address of the route item
     * @return Returns 0, update route table successfully, otherwise it will fail
     */
    static int32_t UpdateRoute(TableType tableType, const std::string &interfaceName,
                               const std::string &destinationName, const std::string &nextHop);

    /**
     * Add interface to default network
     *
     * @param interfaceName Output network device name of the route item
     * @param permission Network permission. Must be one of
     *        PERMISSION_NONE/PERMISSION_NETWORK/PERMISSION_SYSTEM.
     * @return Returns 0, add interface to default network successfully, otherwise it will fail
     */
    static int32_t AddInterfaceToDefaultNetwork(const std::string &interfaceName, NetworkPermission permission);

    /**
     * Remove interface from default network
     *
     * @param interfaceName Output network device name of the route item
     * @param permission Network permission. Must be one of
     *        PERMISSION_NONE/PERMISSION_NETWORK/PERMISSION_SYSTEM.
     * @return Returns 0, remove interface from default network  successfully, otherwise it will fail
     */
    static int32_t RemoveInterfaceFromDefaultNetwork(const std::string &interfaceName, NetworkPermission permission);

    /**
     * Add interface to physical network
     *
     * @param netId Network number
     * @param interfaceName Output network device name of the route item
     * @param permission Network permission. Must be one of
     *        PERMISSION_NONE/PERMISSION_NETWORK/PERMISSION_SYSTEM.
     * @return Returns 0, add interface to physical network successfully, otherwise it will fail
     */
    static int32_t AddInterfaceToPhysicalNetwork(uint16_t netId, const std::string &interfaceName,
                                                 NetworkPermission permission);

    /**
     * Remove interface from physical network
     *
     * @param netId Network number
     * @param interfaceName Output network device name of the route item
     * @param permission Network permission. Must be one of
     *        PERMISSION_NONE/PERMISSION_NETWORK/PERMISSION_SYSTEM.
     * @return Returns 0, remove interface from physical network successfully, otherwise it will fail
     */
    static int32_t RemoveInterfaceFromPhysicalNetwork(uint16_t netId, const std::string &interfaceName,
                                                      NetworkPermission permission);

    /**
     * Modify physical network permission
     *
     * @param netId Network number
     * @param interfaceName Output network device name of the route item
     * @param oldPermission Old network permission. Must be one of
     *        PERMISSION_NONE/PERMISSION_NETWORK/PERMISSION_SYSTEM.
     * @param newPermission New network permission. Must be one of
     *        PERMISSION_NONE/PERMISSION_NETWORK/PERMISSION_SYSTEM.
     * @return Returns 0, modify physical network permission successfully, otherwise it will fail
     */
    static int32_t ModifyPhysicalNetworkPermission(uint16_t netId, const std::string &interfaceName,
                                                   NetworkPermission oldPermission, NetworkPermission newPermission);

    /**
     * Add interface to virtual network
     *
     * @param netId Network number
     * @param interfaceName Output network device name of the route item
     * @return Returns 0, add interface to virtual network successfully, otherwise it will fail
     */
    static int32_t AddInterfaceToVirtualNetwork(int32_t netId, const std::string &interfaceName);

    /**
     * Remove interface from virtual network
     *
     * @param netId Network number
     * @param interfaceName Output network device name of the route item
     * @return Returns 0, remove interface from virtual network successfully, otherwise it will fail
     */
    static int32_t RemoveInterfaceFromVirtualNetwork(int32_t netId, const std::string &interfaceName);

    static int32_t AddUsersToVirtualNetwork(int32_t netId, const std::string &interfaceName,
                                            const std::vector<NetManagerStandard::UidRange> &uidRanges);

    static int32_t RemoveUsersFromVirtualNetwork(int32_t netId, const std::string &interfaceName,
                                                 const std::vector<NetManagerStandard::UidRange> &uidRanges);

    /**
     * Add interface to local network
     *
     * @param netId Network number
     * @param interfaceName Output network device name of the route item
     * @return Returns 0, add interface to local network successfully, otherwise it will fail
     */
    static int32_t AddInterfaceToLocalNetwork(uint16_t netId, const std::string &interfaceName);

    /**
     * Remove interface from local network
     *
     * @param netId Network number
     * @param interfaceName Output network device name of the route item
     * @return Returns 0, remove interface from local network successfully, otherwise it will fail
     */
    static int32_t RemoveInterfaceFromLocalNetwork(uint16_t netId, const std::string &interfaceName);

    /**
     * Enable sharing network
     *
     * @param inputInterface Input network device name of the route item
     * @param outputInterface Output network device name of the route item
     * @return Returns 0, enable sharing network successfully, otherwise it will fail
     */
    static int32_t EnableSharing(const std::string &inputInterface, const std::string &outputInterface);

    /**
     * Disable sharing network
     *
     * @param inputInterface Input network device name of the route item
     * @param outputInterface Output network device name of the route item
     * @return Returns 0, disable sharing network successfully, otherwise it will fail
     */
    static int32_t DisableSharing(const std::string &inputInterface, const std::string &outputInterface);

    /**
     * Parse destination address
     *
     * @param addr Address to be parse
     * @param res Parse result
     * @return Returns 0, parse destination address successfully, otherwise it will fail
     */
    static int32_t ReadAddr(const std::string &addr, InetAddr *res);

    /**
     * Parse gateway address
     *
     * @param addr Address to be parse
     * @param res Parse result
     * @return Returns 0, parse gateway address successfully, otherwise it will fail
     */
    static int32_t ReadAddrGw(const std::string &addr, InetAddr *res);

    /**
     * Update route for vnic interface
     *
     * @param interfaceName Output network device name of the route item
     * @param destinationName Destination address of route item
     * @param nextHop Gateway address of the route item
     * @param add add or delete route
     * @return Returns 0, Update route successfully, otherwise it will fail
     */
    static int32_t UpdateVnicRoute(const std::string &interfaceName, const std::string &destinationName,
                                      const std::string &nextHop, bool add);

    /**
     * Update uid ranges for vnic interface
     *
     * @param uidRanges uidRanges to update
     * @param add add or delete uid ranges
     * @return Returns 0, update UidRangesRules successfully, otherwise it will fail
     */
    static int32_t UpdateVnicUidRangesRule(const std::vector<NetManagerStandard::UidRange> &uidRanges, bool add);

    /**
     * Enable distribute client net: create virnic and config route
     *
     * @param virNicAddr virnic addr
     * @param iif iif name to config route
     * @return Returns 0, enable successfully, otherwise it will fail
     */
    static int32_t EnableDistributedClientNet(const std::string &virnicAddr,
        const std::string &virnicName, const std::string &iif);

    /**
     * Enable distribute client net: config route
     *
     * @param iif iif to config route
     * @param devIface dev Iface name to config route
     * @param dstAddr dstAddr to config route
     * @return Returns 0, enable successfully, otherwise it will fail
     */
    static int32_t EnableDistributedServerNet(const std::string &iif, const std::string &devIface,
                                              const std::string &dstAddr, const std::string &gw);

    /**
     * Disable distribute net: del route
     *
     * @param isServer true:server, false:client
     * @return Returns 0, disable successfully, otherwise it will fail
     */
    static int32_t DisableDistributedNet(bool isServer, const std::string &virnicName, const std::string &dstAddr);

#ifdef SUPPORT_SYSVPN
    /**
     * Set Vpn call mode
     *
     * @param message 1 is sysvpn, other extvpn
     * @return Returns 0, disable successfully, otherwise it will fail
     */
    static int32_t SetVpnCallMode(const std::string &message);

    /**
     * update vpn interface rules
     *
     * @param netId Network number
     * @param interface interface name
     * @param extMessages ext message
     * @param add true add, false remove
     * @return Returns 0, add network ip mark successfully, otherwise it will fail
     */
    static int32_t UpdateVpnRules(uint16_t netId, const std::string &interface,
                                  const std::vector<std::string> &extMessages, bool add);
#endif // SUPPORT_SYSVPN

#ifdef FEATURE_ENTERPRISE_ROUTE_CUSTOM
    /**
     * update enterprise route rules
     *
     * @param interfaceName Network if name
     * @param uid app uid
     * @param add true add, false remove
     * @return Returns 0, update successfully, otherwise it will fail
     */
    static int32_t UpdateEnterpriseRoute(const std::string &interfaceName, uint32_t uid, bool add);
#endif

    static int32_t SetSharingUnreachableIpRule(uint16_t action,
        const std::string &interfaceName, const std::string &forbidIp, uint8_t family);

private:
    static std::mutex interfaceToTableLock_;
    static std::map<std::string, uint32_t> interfaceToTable_;
    static std::string sharingTunv4Interface_;
    static uint32_t sharingTunv4TableId_;
#ifdef SUPPORT_SYSVPN
    enum VpnRuleIdType {
        VPN_OUTPUT_TO_LOCAL,
        VPN_SECURE,
        VPN_EXPLICIT_NETWORK,
        VPN_OUTPUT_IFACE,
        VPN_NETWORK_TABLE,
    };

    static bool vpnSysCall_;
    static std::string defauleNetWorkName_;

    static bool CheckSysVpnCall();
    static bool CheckTunVpnCall(const std::string &vpnName);
    static bool CheckMultiVpnCall(const std::string &vpnName);

    static int32_t UpdateVpnOutPutPenetrationRule(int32_t netId, const std::string &interfaceName,
                                                  const std::string &ruleDstIp, bool add);
    static uint32_t FindVpnIdByInterfacename(VpnRuleIdType type, const std::string &interfaceName);
    static uint32_t GetVpnInterffaceToId(const std::string &ifName);
#endif // SUPPORT_SYSVPN
    static uint16_t GetRuleFlag(uint32_t action);
    static int32_t Init();
    static int32_t ClearRules();
    static int32_t ClearRoutes(const std::string &interfaceName, int32_t netId = 0);
    static int32_t AddLocalNetworkRules();
    static int32_t UpdatePhysicalNetwork(uint16_t netId, const std::string &interfaceName, NetworkPermission permission,
                                         bool add);
    static int32_t UpdateVirtualNetwork(int32_t netId, const std::string &interfaceName,
                                        const std::vector<NetManagerStandard::UidRange> &uidRanges, bool add);
    static int32_t ModifyVirtualNetBasedRules(int32_t netId, const std::string &ifaceName, bool add);

    static int32_t UpdateLocalNetwork(uint16_t netId, const std::string &interfaceName, bool add);
    static int32_t UpdateIncomingPacketMark(uint16_t netId, const std::string &interfaceName,
                                            NetworkPermission permission, bool add);
    static int32_t UpdateExplicitNetworkRule(uint16_t netId, uint32_t table, NetworkPermission permission, bool add);
    static int32_t UpdateOutputInterfaceRules(const std::string &interfaceName, uint32_t table,
                                              NetworkPermission permission, bool add);
    static int32_t UpdateSharingNetwork(uint16_t action, const std::string &inputInterface,
                                        const std::string &outputInterface);
    static int32_t UpdateVpnOutputToLocalRule(const std::string &interfaceName, bool add);
    static int32_t UpdateVpnSystemPermissionRule(int32_t netId, uint32_t table, bool add,
                                                 const std::string &interfaceName = "");
    static int32_t UpdateVpnUidRangeRule(uint32_t table, uid_t uidStart, uid_t uidEnd, bool add,
                                         const std::string &interfaceName = "");
    static int32_t UpdateExplicitNetworkRuleWithUid(int32_t netId, uint32_t table, NetworkPermission permission,
                                                    uid_t uidStart, uid_t uidEnd, bool add,
                                                    const std::string &interfaceName = "");
    static int32_t UpdateOutputInterfaceRulesWithUid(const std::string &interface, uint32_t table,
                                                     NetworkPermission permission, uid_t uidStart, uid_t uidEnd,
                                                     bool add);
    static int32_t ClearSharingRules(const std::string &inputInterface);
    static int32_t UpdateRuleInfo(uint32_t action, uint8_t ruleType, RuleInfo ruleInfo, uid_t uidStart = INVALID_UID,
                                  uid_t uidEnd = INVALID_UID);
    static int32_t UpdateDistributedRule(uint32_t action, uint8_t ruleType, RuleInfo ruleInfo,
                                         uid_t uidStart, uid_t uidEnd);
    static int32_t SendRuleToKernel(uint32_t action, uint8_t family, uint8_t ruleType, RuleInfo ruleInfo,
                                    uid_t uidStart, uid_t uidEnd);
    static int32_t SendRuleToKernelEx(uint32_t action, uint8_t family, uint8_t ruleType, RuleInfo ruleInfo,
                                      uid_t uidStart, uid_t uidEnd);
    static int32_t UpdateRouteRule(uint16_t action, uint16_t flags, RouteInfo routeInfo);
    static int32_t SendRouteToKernel(uint16_t action, uint16_t routeFlag, rtmsg msg, RouteInfo routeInfo,
                                     uint32_t index);
    static uint32_t FindTableByInterfacename(const std::string &interfaceName, int32_t netId = 0);
    static uint32_t GetRouteTableFromType(TableType tableType, const std::string &interfaceName);
    static int32_t SetRouteInfo(TableType tableType, NetworkRouteInfo networkRouteInfo, RouteInfo &routeInfo);
    static int32_t AddServerUplinkRoute(const std::string &UplinkIif, const std::string &devIface,
                                        const std::string &gw);
    static int32_t AddServerDownlinkRoute(const std::string &UplinkIif, const std::string &dstAddr);
    static int32_t SetRuleMsgPriority(NetlinkMsg &nlmsg, RuleInfo &ruleInfo);
    static int32_t SetRuleMsgTable(NetlinkMsg &nlmsg, RuleInfo &ruleInfo);
    static int32_t SetRuleMsgFwmark(NetlinkMsg &nlmsg, RuleInfo &ruleInfo);
    static int32_t SetRuleMsgUidRange(NetlinkMsg &nlmsg, uid_t uidStart, uid_t uidEnd);
    static int32_t SetRuleMsgIfName(NetlinkMsg &nlmsg, std::string &ifName, uint16_t type);
    static int32_t SetRuleMsgIp(NetlinkMsg &nlmsg, std::string &ip, uint16_t type);
    static int32_t SendSharingForbidIpRuleToKernel(
        uint32_t action, uint8_t family, uint8_t ruleType, RuleInfo &ruleInfo);
    static int32_t PrepareRouteMessage(
        const RouteInfo &routeInfo, RouteInfo &routeInfoModify, struct rtmsg &msg, uint32_t &index);
    static int32_t ProcessAddressInfo(
        const RouteInfo &routeInfoModify, InetAddr &dst, InetAddr &gw, struct rtmsg &msg);
    static int32_t AddRouteAttributes(NetlinkMsg &nl, const RouteInfo &routeInfoModify, InetAddr &dst, InetAddr &gw,
        struct rtmsg msg, uint32_t index);
};
} // namespace nmd
} // namespace OHOS
#endif // INCLUDE_ROUTE_MANAGER_H
